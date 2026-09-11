"""BỘ ĐIỀU PHỐI vòng kín — V0.9, §5, §9, §11, §12, §13, §17, §21.

NÓ KHÔNG PHẢI MỘT BỘ LẬP LỊCH THỨ HAI. Router V4 vẫn lập lịch việc, vẫn dựng
worktree, vẫn giữ lease, vẫn chạy cổng kiểm định. Tệp này đứng TRÊN một tầng
và làm đúng thứ V4 cố ý không có: một MỤC TIÊU sống lâu hơn một việc, với kế
hoạch, cổng thẩm quyền, pha kiểm định và một đường lập lại kế hoạch CÓ TRẦN.

VÌ SAO NÓ NHẬN CALLABLE CHỨ KHÔNG NHẬN `ControlCenter`:

Bộ điều phối chạm vào đúng ba thứ bên ngoài — tạo một việc, dừng một việc,
đọc trạng thái một việc. Nhận cả `ControlCenter` sẽ kéo theo fabric, Leader,
provider, ký ức… và bài kiểm tất định của tầng này sẽ phải dựng cả ứng dụng.
Nhận ba hàm thì bài kiểm dựng ba hàm giả, và ĐÓ là lý do §26 kiểm được từng
tính chất một.

BỐN TÍNH CHẤT ĐƯỢC KHOÁ BẰNG BÀI KIỂM:

1. **Không `RUNNING -> DONE`.** Máy trạng thái cấm; ở đây mọi đường kết thúc
   đi qua `kiem_dinh()`.
2. **Không nhân đôi việc.** Một bước đã có `task_id` còn sống KHÔNG được tạo
   việc thứ hai — kể cả sau khi ứng dụng khởi động lại (§11).
3. **Trạng thái kết thúc NHẢ KHOÁ.** Mọi đường ra `KET_THUC` gọi
   `nha_tai_nguyen`.
4. **Huỷ KHÔNG xoá bằng chứng** (§13). `huy()` đổi trạng thái và ghi sự kiện;
   nó không đụng tới `execution_steps` hay `execution_events` đã có.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.chi_phi import (SoChiPhi, tu_ket_qua,
                                                      xet_ngan_sach)
from scripts.control_center.execution.ke_hoach import (BuocKeHoach,
                                                       KeHoachThucThi,
                                                       nhom_song_song,
                                                       so_sanh_ban)
from scripts.control_center.execution.kiem_dinh import (BaoCaoKiemDinh,
                                                        MoiGioiKiem,
                                                        kiem_dinh_buoc,
                                                        kiem_dinh_thuc_thi)
from scripts.control_center.execution.ket_qua import (HopDongKetQua,
                                                      TrangThaiXacMinh)
from scripts.control_center.execution.phuc_hoi import (ChanDoan,
                                                       HanhDongPhucHoi,
                                                       LoaiHong,
                                                       NganSachPhucHoi,
                                                       ap_tran, phan_loai_hong)
from scripts.control_center.execution.so import SoThucThi, tien_do
from scripts.control_center.execution.trang_thai import TrangThaiThucThi as TT
from scripts.control_center.execution.y_dinh import (TrangThaiDuyet,
                                                     YDinhThucThi,
                                                     cau_hoi_tham_quyen)


class TrangThaiBuoc(str, Enum):
    """Vòng đời một BƯỚC bên trong một lần thực thi.

    Tách khỏi `TaskState` có chủ đích: một bước có thể sống qua HAI việc
    (lần đầu hỏng, lần sửa), nên trạng thái của nó không phải trạng thái của
    một việc nào cả.
    """

    CHUA_CHAY = "CHUA_CHAY"
    DANG_CHAY = "RUNNING"
    CHO_KIEM = "CHO_KIEM"
    XONG = "DONE"
    HONG = "FAILED"
    BO_QUA = "BO_QUA"


#: Trần số bước chạy SONG SONG mặc định. Cùng con số với trần WRITE worker
#: của chính sách router toàn cục; bộ gọi truyền số thật từ fabric.
SONG_SONG_MAC_DINH = 3


@dataclass
class KetQuaTick:
    """Thứ MỘT nhịp điều phối đã làm. Dữ liệu, không phải log."""

    execution_id: str
    da_giao: Tuple[str, ...] = ()
    dang_chay: Tuple[str, ...] = ()
    trang_thai: str = ""
    ghi_chu: str = ""
    bao_cao: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {"execution_id": self.execution_id,
                "da_giao": list(self.da_giao),
                "dang_chay": list(self.dang_chay),
                "trang_thai": self.trang_thai, "ghi_chu": self.ghi_chu,
                "bao_cao": self.bao_cao}


class BoDieuPhoi:
    """Đẩy một lần thực thi đi tiếp. Không sở hữu luồng nào — bộ gọi gọi `tick`."""

    def __init__(self, so: SoThucThi, *,
                 tao_viec: Callable[[YDinhThucThi, BuocKeHoach, int], str],
                 trang_thai_viec: Callable[[str], str],
                 dung_viec: Optional[Callable[[str, str], None]] = None,
                 nha_tai_nguyen: Optional[Callable[[str, str], int]] = None,
                 moi_gioi: Optional[MoiGioiKiem] = None,
                 song_song: int = SONG_SONG_MAC_DINH) -> None:
        self.so = so
        self._tao_viec = tao_viec
        self._trang_thai_viec = trang_thai_viec
        self._dung_viec = dung_viec
        self._nha_tai_nguyen = nha_tai_nguyen
        self.moi_gioi = moi_gioi
        self.song_song = max(1, int(song_song or 1))
        self._chi_phi: Dict[str, SoChiPhi] = {}

    # ------------------------------------------------------------ khoi tao --

    def bat_dau(self, y: YDinhThucThi, kh: KeHoachThucThi) -> YDinhThucThi:
        """Lưu ý định + kế hoạch, rồi mở cổng thẩm quyền nếu cần.

        Ý định `NGOAI` KHÔNG vào `READY`. Cho nó `READY` rồi chặn ở bước sau
        là để một lỗi lập lịch duy nhất đủ để nó chạy — cùng lý do
        `engine.chat` tạo việc GATED ở `BLOCKED` chứ không `QUEUED`.
        """
        if kh.execution_id != y.execution_id:
            raise ValueError("kế hoạch không thuộc lần thực thi này")
        self.so.luu(y)
        self.so.luu_ke_hoach(kh)
        for b in kh.buoc:
            self.so.luu_buoc(y.execution_id, kh.phien_ban, b.buoc_id,
                             state=TrangThaiBuoc.CHUA_CHAY.value)
        self.so.ghi_su_kien(
            y.execution_id, "EXEC_CREATED", project_id=y.project_id,
            detail=(f"{len(kh.buoc)} bước, {len(kh.lop)} lớp, "
                    f"{len(kh.nghiem_thu)} tiêu chí nghiệm thu"),
            meta={"nguon_de_xuat": y.nguon_de_xuat,
                  "nguon_message_id": y.nguon_message_id,
                  "tham_quyen": y.tham_quyen.value})
        y = self.so.doi_trang_thai(y.execution_id, TT.PLANNED,
                                   pha="đã lập kế hoạch")
        if y.can_tham_quyen_moi:
            return self.so.doi_trang_thai(
                y.execution_id, TT.WAITING_AUTHORITY,
                ly_do=cau_hoi_tham_quyen(y), pha="chờ bạn cho phép")
        return self.so.doi_trang_thai(y.execution_id, TT.READY,
                                      pha="sẵn sàng chạy")

    def duyet(self, execution_id: str, *, boi: str = "user",
              dong_y: bool = True) -> YDinhThucThi:
        """NGƯỜI duyệt (hoặc từ chối) cổng thẩm quyền. Chỉ người gọi được.

        Không có đường tự động nào tới hàm này, cùng luật `engine.
        mo_khoa_gated`: để Leader gọi nó là tạo ra đúng đường mà một agent có
        thể tự duyệt cổng của chính nó.
        """
        y = self.so.dat_duyet(
            execution_id,
            TrangThaiDuyet.DA_DUYET if dong_y else TrangThaiDuyet.TU_CHOI,
            boi=boi)
        if not dong_y:
            return self._ket_thuc(y, TT.CANCELLED,
                                  f"{boi} từ chối cổng thẩm quyền")
        return self.so.doi_trang_thai(execution_id, TT.READY,
                                      pha="đã được duyệt — sẵn sàng chạy")

    # ----------------------------------------------------------------- tick --

    def tick(self, execution_id: str) -> KetQuaTick:
        """MỘT nhịp: giao những bước chạy được, hoặc chuyển pha."""
        y = self.so.y_dinh(execution_id)
        if y is None:
            return KetQuaTick(execution_id, ghi_chu="không có lần thực thi này")
        if y.trang_thai in (TT.PAUSED, TT.BLOCKED, TT.WAITING_AUTHORITY) \
                or y.trang_thai.ket_thuc:
            return KetQuaTick(execution_id, trang_thai=y.trang_thai.value,
                              ghi_chu=y.trang_thai.nhan)
        kh = self.so.ke_hoach(execution_id)
        if kh is None:
            return KetQuaTick(execution_id, trang_thai=y.trang_thai.value,
                              ghi_chu="chưa có kế hoạch")
        if y.can_tham_quyen_moi:
            self.so.doi_trang_thai(execution_id, TT.WAITING_AUTHORITY,
                                   ly_do=cau_hoi_tham_quyen(y))
            return KetQuaTick(execution_id, trang_thai=TT.WAITING_AUTHORITY.value,
                              ghi_chu="chạm ranh giới ngoài kho")

        bs = {b["buoc_id"]: b for b in self.so.buoc(execution_id, kh.phien_ban)}
        dang = [m for m, b in bs.items()
                if b["state"] == TrangThaiBuoc.DANG_CHAY.value]
        xong = {m for m, b in bs.items()
                if b["xac_minh"] in ("DAT", "SUY_GIAM")}
        hong = {m for m, b in bs.items()
                if b["state"] in (TrangThaiBuoc.HONG.value,
                                  TrangThaiBuoc.BO_QUA.value)}

        # PHU THUOC HONG -> BO QUA, KHONG treo mai o CHUA_CHAY.
        for b in kh.buoc:
            if b.buoc_id in xong or b.buoc_id in hong or b.buoc_id in dang:
                continue
            if set(b.phu_thuoc) & hong:
                self.so.luu_buoc(execution_id, kh.phien_ban, b.buoc_id,
                                 state=TrangThaiBuoc.BO_QUA.value)
                self.so.ghi_su_kien(
                    execution_id, "STEP_SKIPPED", project_id=y.project_id,
                    buoc_id=b.buoc_id, level="WARNING",
                    detail="bỏ qua: một phụ thuộc đã hỏng")
                hong.add(b.buoc_id)

        san = [m for m in kh.san_sang(xong)
               if m not in dang and m not in hong
               and bs.get(m, {}).get("state") == TrangThaiBuoc.CHUA_CHAY.value]
        if not san and not dang:
            return self._sang_kiem_dinh(y, kh, bs)

        con = max(0, self.song_song - len(dang))
        if not con or not san:
            return KetQuaTick(execution_id, dang_chay=tuple(dang),
                              trang_thai=y.trang_thai.value,
                              ghi_chu=(f"{len(dang)} bước đang chạy, "
                                       f"{len(san)} bước chờ chỗ"))

        # §17: READ/READ song song duoc; READ/WRITE va WRITE/WRITE thi khong.
        # Phai xet CA nhung buoc DANG chay, khong chi nhung buoc sap giao —
        # xet thieu la de hai agent giam chung mot cay.
        da_giu = [kh.buoc_theo_ma(m) for m in dang]
        chon = nhom_song_song(
            tuple(x for x in list(kh.buoc) if x.buoc_id in set(san)) +
            tuple(x for x in da_giu if x is not None),
            [b.buoc_id for b in da_giu if b is not None] + san,
            toi_da=len(dang) + con)
        chon = [m for m in chon if m in san][:con]

        giao: List[str] = []
        for m in chon:
            b = kh.buoc_theo_ma(m)
            if b is None:
                continue
            cu = bs.get(m) or {}
            # KHONG NHAN DOI VIEC (§11). Mot buoc da co task_id con song thi
            # khong bao gio duoc tao viec thu hai.
            if cu.get("task_id") and self._con_song(cu["task_id"]):
                continue
            try:
                tid = self._tao_viec(y, b, int(cu.get("so_lan_thu") or 0))
            except Exception as exc:                        # noqa: BLE001
                self.so.ghi_su_kien(
                    execution_id, "STEP_DISPATCH_ERROR",
                    project_id=y.project_id, buoc_id=m, level="ALERT",
                    detail=f"{type(exc).__name__}: {exc}"[:300])
                cd = ap_tran(phan_loai_hong(loi=f"{type(exc).__name__}: {exc}"),
                             self._ngan_sach(execution_id, kh), m)
                self._xu_ly_chan_doan(y, kh, m, cd)
                continue
            self.so.luu_buoc(execution_id, kh.phien_ban, m, task_id=tid,
                             state=TrangThaiBuoc.DANG_CHAY.value,
                             tang_lan_thu=True)
            self.so.ghi_su_kien(execution_id, "STEP_DISPATCHED",
                                project_id=y.project_id, buoc_id=m,
                                detail=f"giao việc {tid}",
                                meta={"task_id": tid,
                                      "che_do": b.che_do_ghi.value})
            giao.append(m)

        if giao and y.trang_thai is not TT.RUNNING:
            self.so.doi_trang_thai(execution_id, TT.RUNNING,
                                   pha=f"đang chạy {len(giao) + len(dang)} bước")
        return KetQuaTick(execution_id, da_giao=tuple(giao),
                          dang_chay=tuple(dang + giao),
                          trang_thai=TT.RUNNING.value if giao
                          else y.trang_thai.value,
                          ghi_chu=f"giao {len(giao)} bước")

    def _con_song(self, task_id: str) -> bool:
        try:
            return str(self._trang_thai_viec(task_id) or "").upper() in (
                "QUEUED", "WAITING", "RUNNING", "REVIEW", "PAUSED")
        except Exception:                                   # noqa: BLE001
            return False

    # ------------------------------------------------------------ ket qua ----

    def nhan_ket_qua(self, task_id: str, kq: HopDongKetQua, *,
                     premium_tier: int = 0) -> Optional[KetQuaTick]:
        """Một việc kết thúc -> chấm bước, rồi quyết đi tiếp hay sửa.

        Trả `None` khi việc này không thuộc lần thực thi nào — đường việc lẻ
        của V0.8 đi tiếp như cũ, không bị tầng này đụng vào.
        """
        st = self.so.buoc_theo_task(task_id)
        if st is None:
            return None
        eid, pb, m = st["execution_id"], int(st["phien_ban"]), st["buoc_id"]
        y = self.so.y_dinh(eid)
        kh = self.so.ke_hoach(eid, pb)
        if y is None or kh is None:
            return None
        b = kh.buoc_theo_ma(m)
        if b is None:
            return None

        kq.buoc_id = m
        self.so.luu_buoc(eid, pb, m, ket_qua=kq,
                         state=TrangThaiBuoc.CHO_KIEM.value)
        tt, ds = kiem_dinh_buoc(b, kq, moi_gioi=self.moi_gioi)
        self.so.luu_buoc(eid, pb, m, xac_minh=tt,
                         kiem=[k.to_dict() for k in ds])
        self._so_chi_phi(eid).them(
            tu_ket_qua(m, kq, premium_tier=premium_tier,
                       thanh_cong=tt.dat))

        if tt.dat:
            self.so.luu_buoc(eid, pb, m, state=TrangThaiBuoc.XONG.value)
            self.so.ghi_su_kien(
                eid, "STEP_VERIFIED", project_id=y.project_id, buoc_id=m,
                detail=f"{tt.value}: {len(ds)} phép kiểm",
                meta={"kiem": [k.to_dict() for k in ds]})
            return self.tick(eid)

        cd = ap_tran(
            phan_loai_hong(ket_qua=kq, xac_minh=tt,
                           phu_thuoc_hong=self._phu_thuoc_hong(eid, pb, b)),
            self._ngan_sach(eid, kh), m)
        self.so.ghi_su_kien(
            eid, "STEP_FAILED", project_id=y.project_id, buoc_id=m,
            level=("ALERT" if cd.loai.la_cau_hinh else "WARNING"),
            detail=f"{tt.value} -> {cd.loai.value}/{cd.hanh_dong.value}: "
                   f"{cd.ly_do}"[:400],
            meta={"chan_doan": cd.to_dict(),
                  "kiem": [k.to_dict() for k in ds]})
        return self._xu_ly_chan_doan(y, kh, m, cd)

    def _phu_thuoc_hong(self, eid: str, pb: int, b: BuocKeHoach) -> bool:
        bs = {x["buoc_id"]: x for x in self.so.buoc(eid, pb)}
        return any((bs.get(d) or {}).get("state") in
                   (TrangThaiBuoc.HONG.value, TrangThaiBuoc.BO_QUA.value)
                   for d in b.phu_thuoc)

    def _xu_ly_chan_doan(self, y: YDinhThucThi, kh: KeHoachThucThi,
                         buoc_id: str, cd: ChanDoan) -> KetQuaTick:
        eid, pb = y.execution_id, kh.phien_ban
        hd = cd.hanh_dong
        if hd in (HanhDongPhucHoi.THU_LAI, HanhDongPhucHoi.DINH_TUYEN_LAI,
                  HanhDongPhucHoi.TAO_VIEC_SUA):
            # Ve `CHUA_CHAY` de nhip sau giao lai. `task_id` bi XOA de
            # `_con_song` khong chan viec moi — nhung ban ghi ket qua cu VAN
            # con trong `ket_qua_json`, nen bang chung khong mat.
            self.so.luu_buoc(eid, pb, buoc_id, task_id="",
                             state=TrangThaiBuoc.CHUA_CHAY.value)
            self.so.dem_thu_lai(eid, tang=1)
            self.so.ghi_su_kien(
                eid, "STEP_RETRY", project_id=y.project_id, buoc_id=buoc_id,
                level="WARNING",
                detail=f"{hd.value} (còn {cd.con_lai} lượt): {cd.ly_do}"[:300])
            return self.tick(eid)
        if hd is HanhDongPhucHoi.LAP_LAI_KE_HOACH:
            self.so.luu_buoc(eid, pb, buoc_id, state=TrangThaiBuoc.HONG.value)
            self.so.doi_trang_thai(eid, TT.REPLANNING,
                                   ly_do=cd.ly_do, pha="lập lại kế hoạch")
            return KetQuaTick(eid, trang_thai=TT.REPLANNING.value,
                              ghi_chu=cd.ly_do)
        if hd is HanhDongPhucHoi.BO_QUA:
            self.so.luu_buoc(eid, pb, buoc_id, state=TrangThaiBuoc.BO_QUA.value)
            return self.tick(eid)
        # DUNG_CHO_NGUOI
        self.so.luu_buoc(eid, pb, buoc_id, state=TrangThaiBuoc.HONG.value)
        y2 = self.so.doi_trang_thai(
            eid, TT.BLOCKED,
            ly_do=(f"[{cd.loai.value}] {cd.ly_do}"
                   + (" — đây là lỗi CẤU HÌNH/QUYỀN, không phải lỗi việc"
                      if cd.loai.la_cau_hinh else "")),
            pha="cần bạn xem")
        self.nha_tai_nguyen(y2)
        return KetQuaTick(eid, trang_thai=TT.BLOCKED.value, ghi_chu=cd.ly_do)

    # ---------------------------------------------------------- kiem dinh ----

    def _sang_kiem_dinh(self, y: YDinhThucThi, kh: KeHoachThucThi,
                        bs: Dict[str, Dict]) -> KetQuaTick:
        chua = [m for m, b in bs.items()
                if b["state"] == TrangThaiBuoc.CHUA_CHAY.value]
        if chua:
            # Con buoc chua chay ma khong giao duoc -> phu thuoc chua xong
            # hoac tai nguyen ket. KHONG im lang: de o RUNNING va noi ro.
            return KetQuaTick(y.execution_id, trang_thai=y.trang_thai.value,
                              ghi_chu=f"{len(chua)} bước chờ phụ thuộc/tài nguyên")
        if y.trang_thai is not TT.VERIFYING:
            y = self.so.doi_trang_thai(y.execution_id, TT.VERIFYING,
                                       pha="đang kiểm định mục tiêu gốc")
        bc = self.kiem_dinh(y.execution_id)
        return KetQuaTick(y.execution_id,
                          trang_thai=(self.so.y_dinh(y.execution_id)
                                      or y).trang_thai.value,
                          ghi_chu=bc.ly_do if bc else "",
                          bao_cao=bc.to_dict() if bc else None)

    def kiem_dinh(self, execution_id: str, *,
                  phan_bien: Optional[Dict] = None
                  ) -> Optional[BaoCaoKiemDinh]:
        """Chấm CẢ lần thực thi theo mục tiêu gốc, rồi kết luận — §8."""
        y = self.so.y_dinh(execution_id)
        kh = self.so.ke_hoach(execution_id)
        if y is None or kh is None:
            return None
        kqb: Dict[str, Optional[HopDongKetQua]] = {}
        for st in self.so.buoc(execution_id, kh.phien_ban):
            d = st.get("ket_qua")
            kqb[st["buoc_id"]] = HopDongKetQua.tu_dict(d) if d else None
        bc = kiem_dinh_thuc_thi(y, kh, kqb, moi_gioi=self.moi_gioi,
                                phan_bien=phan_bien)
        self.so.ghi_su_kien(
            execution_id, "EXEC_VERIFIED", project_id=y.project_id,
            level=("INFO" if bc.dat else "WARNING"),
            detail=f"{bc.trang_thai.value}: {bc.ly_do}"[:400],
            meta=bc.to_dict())
        if bc.dat:
            self._ket_thuc(y, TT.DONE, bc.ly_do)
            return bc
        ns = self._ngan_sach(execution_id, kh)
        cd = ap_tran(ChanDoan(
            LoaiHong.LOI_HIEN_THUC
            if bc.trang_thai is TrangThaiXacMinh.KHONG_DAT
            else LoaiHong.THIEU_BANG_CHUNG,
            HanhDongPhucHoi.LAP_LAI_KE_HOACH,
            f"kiểm định mục tiêu gốc không đạt: {bc.ly_do}"), ns, "(nghiệm thu)")
        if cd.hanh_dong is HanhDongPhucHoi.LAP_LAI_KE_HOACH:
            self.so.doi_trang_thai(execution_id, TT.REPLANNING,
                                   ly_do=cd.ly_do, pha="lập lại kế hoạch")
        else:
            self._ket_thuc(y, TT.FAILED, cd.ly_do)
        return bc

    # ------------------------------------------------------------ lap lai ----

    def lap_lai_ke_hoach(self, execution_id: str,
                         buoc_moi: Sequence[BuocKeHoach], *, ly_do: str,
                         bang_chung: Sequence[str] = ()) -> KeHoachThucThi:
        """Bản kế hoạch kế tiếp. Bản cũ Ở LẠI — §10.

        Tiêu chí nghiệm thu được GIỮ NGUYÊN mặc định (`ban_moi`), nên không
        ai lập lại kế hoạch để đi vòng qua một tiêu chí đang hỏng.
        """
        y = self.so.y_dinh(execution_id)
        cu = self.so.ke_hoach(execution_id)
        if y is None or cu is None:
            raise KeyError(f"không có lần thực thi {execution_id!r}")
        if self._ngan_sach(execution_id, cu).con_lap_ke_hoach_duoc <= 0:
            raise RuntimeError(
                f"{execution_id}: đã cạn ngân sách lập lại kế hoạch — §9 cấm "
                f"lặp vô hạn; dừng để người xem")
        moi = cu.ban_moi(buoc=buoc_moi, ly_do=ly_do, bang_chung=bang_chung)
        moi = KeHoachThucThi(
            execution_id=moi.execution_id, phien_ban=moi.phien_ban,
            buoc=moi.buoc, nghiem_thu=moi.nghiem_thu, ly_do_sua=moi.ly_do_sua,
            thay_doi=tuple(so_sanh_ban(cu, moi)),
            bang_chung_gay_ra=moi.bang_chung_gay_ra, dang_hieu_luc=True)
        # QUA `REPLANNING` TRUOC. Di thang `READY -> PLANNED` la mot buoc
        # nhay nguoc ma bang chuyen cam — va nen cam: trang thai phai noi
        # duoc rang lan thuc thi nay DANG lap lai ke hoach, khong phai dang
        # cho chay.
        if y.trang_thai is not TT.REPLANNING:
            self.so.doi_trang_thai(execution_id, TT.REPLANNING, ly_do=ly_do,
                                   pha="lập lại kế hoạch")
        self.so.luu_ke_hoach(moi)
        for b in moi.buoc:
            self.so.luu_buoc(execution_id, moi.phien_ban, b.buoc_id,
                             state=TrangThaiBuoc.CHUA_CHAY.value)
        self.so.dem_lap_lai(execution_id, tang=1)
        self.so.ghi_su_kien(
            execution_id, "PLAN_REVISED", project_id=y.project_id,
            level="WARNING",
            detail=f"v{cu.phien_ban} -> v{moi.phien_ban}: {ly_do}"[:400],
            meta={"thay_doi": list(moi.thay_doi),
                  "bang_chung": list(moi.bang_chung_gay_ra)})
        self.so.doi_trang_thai(execution_id, TT.PLANNED,
                               pha=f"kế hoạch v{moi.phien_ban}")
        self.so.doi_trang_thai(execution_id, TT.READY, pha="sẵn sàng chạy lại")
        return moi

    # ----------------------------------------------------- nguoi dieu khien --

    def tam_dung(self, execution_id: str, *, ly_do: str = "người dùng dừng"
                 ) -> YDinhThucThi:
        """§13 `pause`. Lượt agent ĐANG BAY vẫn chạy nốt — xem `model.py`.

        Không giết tiến trình: `Executor.run` là đồng bộ, và cách duy nhất
        cắt một lượt đang bay là giết agent, đó là `huy`, không phải `pause`.
        """
        y = self.so.doi_trang_thai(execution_id, TT.PAUSED, ly_do=ly_do,
                                   pha="tạm dừng")
        self.so.ghi_su_kien(execution_id, "EXEC_PAUSED",
                            project_id=y.project_id, level="WARNING",
                            detail=ly_do)
        return y

    def tiep_tuc(self, execution_id: str) -> KetQuaTick:
        y = self.so.y_dinh(execution_id)
        if y is None:
            return KetQuaTick(execution_id, ghi_chu="không có lần thực thi này")
        if y.can_tham_quyen_moi:
            self.so.doi_trang_thai(execution_id, TT.WAITING_AUTHORITY,
                                   ly_do=cau_hoi_tham_quyen(y))
            return KetQuaTick(execution_id,
                              trang_thai=TT.WAITING_AUTHORITY.value,
                              ghi_chu="vẫn chờ bạn cho phép")
        self.so.doi_trang_thai(execution_id, TT.READY, pha="tiếp tục")
        self.so.ghi_su_kien(execution_id, "EXEC_RESUMED",
                            project_id=y.project_id, detail="người dùng tiếp tục")
        return self.tick(execution_id)

    def huy(self, execution_id: str, *, ly_do: str = "người dùng huỷ"
            ) -> YDinhThucThi:
        """§13 `cancel` — CÓ BIÊN và TRUY ĐƯỢC. KHÔNG xoá bằng chứng.

        Việc con đang bay được dừng (nếu bộ gọi cấp `dung_viec`), khoá được
        nhả, trạng thái về `CANCELLED`. `execution_steps` và
        `execution_events` KHÔNG bị đụng tới: lịch sử của một lần bị huỷ là
        thứ người ta đọc lại nhiều nhất.
        """
        y = self.so.y_dinh(execution_id)
        if y is None:
            raise KeyError(f"không có lần thực thi {execution_id!r}")
        kh = self.so.ke_hoach(execution_id)
        dung: List[str] = []
        if kh is not None and self._dung_viec is not None:
            for st in self.so.buoc(execution_id, kh.phien_ban):
                if st["state"] == TrangThaiBuoc.DANG_CHAY.value and st["task_id"]:
                    try:
                        self._dung_viec(st["task_id"], ly_do)
                        dung.append(st["task_id"])
                    except Exception as exc:                # noqa: BLE001
                        self.so.ghi_su_kien(
                            execution_id, "CANCEL_TASK_ERROR",
                            project_id=y.project_id, buoc_id=st["buoc_id"],
                            level="WARNING",
                            detail=f"{type(exc).__name__}: {exc}"[:200])
        y2 = self._ket_thuc(y, TT.CANCELLED, ly_do)
        self.so.ghi_su_kien(
            execution_id, "EXEC_CANCELLED", project_id=y.project_id,
            level="WARNING",
            detail=f"{ly_do}; dừng {len(dung)} việc con — bằng chứng GIỮ NGUYÊN",
            meta={"da_dung": dung})
        return y2

    # ------------------------------------------------------------- ket thuc --

    def _ket_thuc(self, y: YDinhThucThi, tt: TT, ly_do: str) -> YDinhThucThi:
        y2 = self.so.doi_trang_thai(y.execution_id, tt, ly_do=ly_do,
                                    pha=tt.nhan, force=True)
        self.nha_tai_nguyen(y2)
        return y2

    def nha_tai_nguyen(self, y: YDinhThucThi) -> int:
        """Nhả khoá của MỌI việc con. Gọi ở mọi đường ra trạng thái kết thúc."""
        if self._nha_tai_nguyen is None:
            return 0
        kh = self.so.ke_hoach(y.execution_id)
        if kh is None:
            return 0
        n = 0
        for st in self.so.buoc(y.execution_id, kh.phien_ban):
            if not st["task_id"]:
                continue
            try:
                n += int(self._nha_tai_nguyen(y.project_id, st["task_id"]) or 0)
            except Exception:                               # noqa: BLE001
                pass
        if n:
            self.so.ghi_su_kien(y.execution_id, "LOCKS_RELEASED",
                                project_id=y.project_id,
                                detail=f"nhả {n} khoá khi kết thúc")
        return n

    # ---------------------------------------------------------- khoi dong ----

    def doi_soat_khoi_dong(self) -> Dict:
        """§11 — đối soát sau khi ứng dụng khởi động lại. IDEMPOTENT.

        Ba tình huống, ba cách xử KHÁC NHAU, và gộp chúng là cách mất việc:

        * việc con VẪN SỐNG        -> để yên. Không tạo lại, không đánh hỏng.
        * việc con ĐÃ KẾT THÚC     -> bước về `CHUA_CHAY` để nhịp sau chấm
                                      lại từ hợp đồng kết quả đã lưu; nếu
                                      chưa có hợp đồng thì nó được giao lại.
        * việc con KHÔNG CÒN       -> `CHUA_CHAY`, giao lại (còn lượt) hoặc
                                      `BLOCKED`.

        KHÔNG có nhánh nào tạo việc ở đây. Tạo việc là của `tick`, và để
        `doi_soat_khoi_dong` cũng tạo việc là mở đúng cửa nhân đôi mà §11
        cấm.
        """
        bc: Dict = {"kiem": 0, "mo_coi": [], "con_song": [], "chan": []}
        for y in self.so.dang_chay():
            kh = self.so.ke_hoach(y.execution_id)
            if kh is None:
                continue
            for st in self.so.buoc(y.execution_id, kh.phien_ban):
                if st["state"] != TrangThaiBuoc.DANG_CHAY.value:
                    continue
                bc["kiem"] += 1
                tid = st["task_id"]
                if tid and self._con_song(tid):
                    bc["con_song"].append(tid)
                    continue
                self.so.luu_buoc(y.execution_id, kh.phien_ban, st["buoc_id"],
                                 task_id="",
                                 state=TrangThaiBuoc.CHUA_CHAY.value)
                bc["mo_coi"].append(f"{y.execution_id}/{st['buoc_id']}")
                self.so.ghi_su_kien(
                    y.execution_id, "STEP_ORPHAN", project_id=y.project_id,
                    buoc_id=st["buoc_id"], level="WARNING",
                    detail=(f"việc {tid or '(không có)'} không còn sau khởi "
                            f"động lại — đưa bước về hàng đợi, KHÔNG tạo "
                            f"việc mới ở đây"))
            # Mot lan thuc thi dang RUNNING ma khong con buoc nao chay -> de
            # `tick` quyet. KHONG tu dua ve DONE: do chinh la `RUNNING ->
            # DONE` di duong vong.
            if y.trang_thai is TT.RUNNING:
                bc["chan"].append(y.execution_id)
        self.so.ghi_su_kien(
            "", "EXEC_RECONCILED", level="WARNING",
            detail=(f"đối soát {bc['kiem']} bước đang chạy: "
                    f"{len(bc['con_song'])} còn sống, "
                    f"{len(bc['mo_coi'])} mồ côi"),
            meta=bc)
        return bc

    # --------------------------------------------------------------- so lieu --

    def _so_chi_phi(self, execution_id: str) -> SoChiPhi:
        s = self._chi_phi.get(execution_id)
        if s is None:
            s = SoChiPhi(execution_id=execution_id)
            self._chi_phi[execution_id] = s
        return s

    def chi_phi(self, execution_id: str) -> SoChiPhi:
        return self._so_chi_phi(execution_id)

    def _ngan_sach(self, execution_id: str,
                   kh: KeHoachThucThi) -> NganSachPhucHoi:
        """Ngân sách đọc TỪ SỔ, không từ bộ nhớ tiến trình.

        Đây là điều kiện để trần của §9 sống sót qua một lần khởi động lại:
        một bộ đếm trong RAM sẽ về 0 mỗi lần mở app, và trần 2 trở thành
        trần vô hạn với một người dùng hay tắt đi bật lại.
        """
        ns = NganSachPhucHoi(
            so_lan_lap_ke_hoach=max(0, kh.phien_ban - 1))
        for st in self.so.buoc(execution_id, kh.phien_ban):
            n = int(st.get("so_lan_thu") or 0)
            if n > 1:
                ns.so_lan_thu_theo_buoc[st["buoc_id"]] = n - 1
        return ns

    def ngan_sach(self, execution_id: str) -> Optional[NganSachPhucHoi]:
        kh = self.so.ke_hoach(execution_id)
        return self._ngan_sach(execution_id, kh) if kh else None


# ------------------------------------------------------- cau tra loi cho nguoi --

def cau_trang_thai(so: SoThucThi, project_id: str) -> str:
    """§12 — "xong chưa bro?" trả lời TỪ SỔ, 0 việc khảo sát.

    Hàm THUẦN trên sổ. Đây là điều kiện để §12 đúng: nếu câu trả lời phải đi
    qua một agent thì Leader vừa tạo thêm một việc chỉ để biết trạng thái của
    chính mình — đúng thứ yêu cầu cấm.
    """
    ds = so.dang_chay(project_id)
    if not ds:
        xong = so.danh_sach(project_id, dang_song=False, limit=3)
        if not xong:
            return "Hiện không có lần thực thi nào đang chạy."
        d = ["Không có lần thực thi nào đang chạy. Gần nhất:"]
        for y in xong:
            d.append(f"  • `{y.execution_id}` [{y.trang_thai.value}] "
                     f"{y.goal[:80]} — {y.ly_do_dung or y.ket_luan[:120]}")
        return "\n".join(d)
    d: List[str] = []
    for y in ds:
        kh = so.ke_hoach(y.execution_id)
        bs = {b["buoc_id"]: b for b in so.buoc(y.execution_id,
                                               kh.phien_ban if kh else 1)}
        td = tien_do(kh, bs)
        dong = (f"`{y.execution_id}` [{y.trang_thai.value}] {y.goal[:90]}\n"
                f"  kế hoạch v{y.ban_ke_hoach} — {td['xong']}/{td['tong']} "
                f"bước đã kiểm định xong ({td['phan_tram']}%)")
        if td["dang_chay"]:
            dang = [m for m, b in bs.items() if b["state"] == "RUNNING"]
            dong += f"\n  đang chạy: {', '.join(dang)}"
        if td["chua_kiem"]:
            dong += f"\n  chờ kiểm định: {td['chua_kiem']} bước"
        if td["hong"]:
            dong += f"\n  (!) {td['hong']} bước chưa đạt"
        if y.trang_thai.can_nguoi:
            dong += f"\n  (!) CẦN BẠN: {y.ly_do_dung[:200]}"
        d.append(dong)
    return "\n\n".join(d)


def cau_ket_thuc(y: YDinhThucThi, bc: Optional[BaoCaoKiemDinh], *,
                 ghi_nho: Sequence[Dict] = ()) -> str:
    """§21 — câu Leader tự nói khi việc xong. KHÔNG có suy luận thô.

    Bốn phần cố định: đã làm gì, kiểm định thế nào, hạn chế gì, đã lưu gì.
    Cố định vì §21 đòi Leader nói TIẾP mà không cần người hỏi, và một câu
    tổng hợp tự do sẽ bỏ phần "hạn chế" đầu tiên khi nó dài.
    """
    d: List[str] = []
    if y.trang_thai is TT.DONE:
        d.append("Xong rồi bro.")
    elif y.trang_thai is TT.CANCELLED:
        d.append("Đã huỷ theo yêu cầu.")
    elif y.trang_thai in (TT.BLOCKED, TT.WAITING_AUTHORITY):
        d.append("Mình dừng lại ở đây và cần bạn.")
    else:
        d.append("Lần thực thi này chưa đạt.")
    d.append(f"\nMục tiêu: {y.goal}")

    if bc is not None:
        if bc.buoc_dat:
            d.append("\nTôi đã làm:")
            d += [f"- {m}" for m in bc.buoc_dat]
        d.append(f"\nKiểm định: {bc.trang_thai.value} — {bc.ly_do}")
        for t in bc.tieu_chi:
            d.append(f"- [{t.trang_thai.value}] {t.mo_ta[:120]}")
        if bc.buoc_thieu_bang_chung:
            d.append("\nChưa chứng minh được: "
                     + ", ".join(bc.buoc_thieu_bang_chung))
        if bc.doc_lap is False:
            d.append("\nHạn chế: phản biện KHÔNG độc lập về họ model "
                     "(DEGRADED) — đừng coi là bằng chứng ngữ nghĩa.")
    if y.tac_dong_production:
        d.append("\nProduction: KHÔNG thay đổi gì — mọi thao tác chạm "
                 "production đều dừng ở cổng thẩm quyền.")
    if y.trang_thai.can_nguoi and y.ly_do_dung:
        d.append(f"\nCần bạn quyết: {y.ly_do_dung}")
    if ghi_nho:
        ten = [str(x.get("loai")) for x in ghi_nho if x.get("loai")]
        if ten:
            d.append(f"\nĐã lưu vào Ký ức dự án: {', '.join(sorted(set(ten)))}.")
    return "\n".join(d)

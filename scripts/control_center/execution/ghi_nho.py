"""KẾT QUẢ ĐÃ KIỂM ĐỊNH -> KÝ ỨC DỰ ÁN — V0.9, §14.

VÒNG KÍN CHỈ ĐÓNG KHI KẾT QUẢ QUAY VỀ KÝ ỨC. Không có bước này thì phiên sau
lại bắt đầu từ số không, và người dùng lại phải dán tay một bản bàn giao —
đúng thứ v0.9 tồn tại để bỏ đi.

MỘT LUẬT QUAN TRỌNG HƠN TẤT CẢ PHẦN CÒN LẠI, và §14 viết thẳng:

    *"Do NOT automatically promote every model recommendation to an
    authoritative Decision. User authority must remain distinct."*

Nên `phan_loai_ghi_nho` KHÔNG BAO GIỜ sinh ra một `decision` từ một đề xuất
của Strategist. Một quyết định chỉ ra đời khi NGƯỜI DÙNG đã duyệt tường minh
(`TrangThaiDuyet.DA_DUYET`, hoặc `tham_quyen_nguoi=True` do người bấm), và
lúc đó `tin_cay` là `ghi_nhan` — vẫn thấp hơn `user_explicit` mà `de_bat.py`
dành riêng cho câu người dùng tự gõ. Ba mức, ba nghĩa khác nhau, và gộp
chúng là cách một lời khuyên của model trở thành luật của dự án.

BẢNG ÁNH XẠ (§14), tất định:

    kiểm định ĐẠT              -> episodic (kết quả) + điểm dừng L3
    kiểm định ĐẠT + có bước    -> procedural (cách làm lặp lại được)
      quy trình tái dùng được
    hỏng THẬT                  -> incident
    người dùng duyệt kiến trúc -> decision   (CHỈ khi `tham_quyen_nguoi`)
    ràng buộc mới phát hiện    -> constraint (CHỈ khi người dùng nói)
    yêu cầu mới                -> requirement (CHỈ khi người dùng nói)
    số đo model/provider       -> benchmark vai (đường riêng, không qua đây)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.kiem_dinh import BaoCaoKiemDinh
from scripts.control_center.execution.ket_qua import TrangThaiXacMinh
from scripts.control_center.execution.y_dinh import (TrangThaiDuyet,
                                                     YDinhThucThi,
                                                     khong_suy_nghi)

#: Loại ký ức mà tầng này ĐƯỢC PHÉP tự ghi. Danh sách ĐÓNG, và `decision`
#: không có trong đó ở đường tự động — nó chỉ vào qua `de_xuat_quyet_dinh`,
#: cần một cờ thẩm quyền người dùng.
LOAI_TU_GHI: Tuple[str, ...] = ("episodic", "procedural", "incident")


@dataclass
class BanGhiDeXuat:
    """Một bản ghi ký ức ĐỀ NGHỊ. Chưa ghi — tầng trên quyết."""

    loai: str
    tieu_de: str
    noi_dung: str
    tin_cay: str = "do_duoc"
    quan_trong: int = 6
    the: Tuple[str, ...] = ()
    #: `True` thì bản ghi này CHỜ NGƯỜI. Dùng cho `decision`/`constraint`/
    #: `requirement` — xem docstring module.
    can_nguoi_duyet: bool = False
    ly_do: str = ""

    def __post_init__(self) -> None:
        self.tieu_de = khong_suy_nghi(self.tieu_de, toi_da=200)
        self.noi_dung = khong_suy_nghi(self.noi_dung, toi_da=4000)
        self.ly_do = khong_suy_nghi(self.ly_do, toi_da=800)

    def to_dict(self) -> Dict:
        return {"loai": self.loai, "tieu_de": self.tieu_de,
                "noi_dung": self.noi_dung, "tin_cay": self.tin_cay,
                "quan_trong": self.quan_trong, "the": list(self.the),
                "can_nguoi_duyet": self.can_nguoi_duyet, "ly_do": self.ly_do}


def _tom_tat_bang_chung(bc: BaoCaoKiemDinh, *, toi_da: int = 8) -> str:
    d: List[str] = []
    for t in bc.tieu_chi[:toi_da]:
        d.append(f"  [{t.trang_thai.value}] {t.mo_ta[:120]}")
        for k in t.kiem[:3]:
            d.append(f"      {'✓' if k.dat else '✗'} {k.cach}: "
                     f"{k.chi_tiet[:120]}")
    return "\n".join(d)


def phan_loai_ghi_nho(y: YDinhThucThi, bc: BaoCaoKiemDinh, *,
                      tep_da_sua: Sequence[str] = (),
                      quy_trinh: str = "") -> List[BanGhiDeXuat]:
    """Kết quả đã kiểm định -> danh sách bản ghi ĐỀ NGHỊ. Tất định.

    `quy_trinh` (tuỳ chọn): một mô tả cách làm có thể LẶP LẠI. Chỉ khi nó có
    thật mới sinh ra `procedural` — tự sinh một SOP từ một lần chạy may mắn
    là cách ký ức dự án đầy lên bằng thứ không dùng lại được.
    """
    ra: List[BanGhiDeXuat] = []
    tep = [str(x) for x in tep_da_sua if str(x or "").strip()][:30]
    dau = (f"Mục tiêu: {y.goal}\n"
           f"Thẩm quyền: {y.tham_quyen.value} ({y.duyet.value})\n"
           f"Kết luận kiểm định: {bc.trang_thai.value} — {bc.ly_do}")

    if bc.trang_thai.dat:
        noi = (f"{dau}\n"
               f"Bước đạt: {', '.join(bc.buoc_dat) or '(không có)'}\n"
               f"Tệp đã sửa ({len(tep)}): {', '.join(tep[:12]) or '(không)'}\n"
               f"Bằng chứng nghiệm thu:\n{_tom_tat_bang_chung(bc)}")
        if bc.trang_thai is TrangThaiXacMinh.SUY_GIAM:
            noi += ("\n\n(!) SUY GIẢM: đạt phép kiểm tất định nhưng không có "
                    "phản biện độc lập khác họ model — không coi đây là "
                    "bằng chứng ngữ nghĩa.")
        ra.append(BanGhiDeXuat(
            loai="episodic",
            tieu_de=f"Thực thi {y.execution_id}: {y.goal[:90]}",
            noi_dung=noi, tin_cay="do_duoc", quan_trong=7,
            the=("thuc_thi", "v09", bc.trang_thai.value.lower()),
            ly_do="kết quả đã kiểm định — bằng chứng trong chính bản ghi"))
        if quy_trinh.strip():
            ra.append(BanGhiDeXuat(
                loai="procedural",
                tieu_de=f"Cách làm: {y.goal[:90]}",
                noi_dung=khong_suy_nghi(quy_trinh, toi_da=3000),
                tin_cay="do_duoc", quan_trong=7,
                the=("quy_trinh", "thuc_thi"),
                ly_do="quy trình lặp lại được, rút từ một lần chạy đã kiểm"))
    else:
        # HONG THAT -> SU CO. Ke ca khi hong vi THIEU BANG CHUNG: mot lan
        # thuc thi khong chung minh duoc minh la mot su co that ve quy trinh,
        # va no la thu ta muon thay lai lan sau.
        ra.append(BanGhiDeXuat(
            loai="incident",
            tieu_de=f"Thực thi {y.execution_id} KHÔNG đạt: {y.goal[:80]}",
            noi_dung=(f"{dau}\n"
                      f"Bước hỏng: {', '.join(bc.buoc_hong) or '(không)'}\n"
                      f"Bước thiếu bằng chứng: "
                      f"{', '.join(bc.buoc_thieu_bang_chung) or '(không)'}\n"
                      f"Số lần thử lại: {y.so_lan_thu_lai}; "
                      f"số lần lập lại kế hoạch: {y.so_lan_lap_lai}\n"
                      f"Chi tiết:\n{_tom_tat_bang_chung(bc)}"),
            tin_cay="do_duoc", quan_trong=8,
            the=("su_co", "thuc_thi", "v09"),
            ly_do="kiểm định không đạt — ghi lại để lần sau không lặp"))
    return ra


def de_xuat_quyet_dinh(y: YDinhThucThi, *, noi_dung: str, ly_do: str = "",
                       tham_quyen_nguoi: bool = False
                       ) -> Optional[BanGhiDeXuat]:
    """Một QUYẾT ĐỊNH — và chỉ khi NGƯỜI đã duyệt. Xem docstring module.

    Trả `None` khi chưa có thẩm quyền người dùng. Không trả một bản ghi
    `can_nguoi_duyet=True` để tầng trên "ghi tạm": một quyết định tạm trong
    sổ vẫn đọc ra là một quyết định khi Leader tra ký ức ba tuần sau.
    """
    duyet = tham_quyen_nguoi or y.duyet is TrangThaiDuyet.DA_DUYET
    if not duyet:
        return None
    return BanGhiDeXuat(
        loai="decision",
        tieu_de=f"Quyết định từ thực thi {y.execution_id}",
        noi_dung=noi_dung,
        tin_cay="ghi_nhan",          # THAP HON `user_explicit` — co chu dich
        quan_trong=8, the=("quyet_dinh", "thuc_thi"),
        can_nguoi_duyet=False,
        ly_do=(ly_do or f"người dùng duyệt lần thực thi {y.execution_id} "
                        f"(bởi {y.duyet_boi or 'user'})"))


class GhiNhoThucThi:
    """Ghi bản ghi đề nghị vào ký ức dự án. Bọc `DichVuKyUc`, không thay nó."""

    def __init__(self, dv_ky_uc) -> None:
        self.dv = dv_ky_uc

    @property
    def dung_duoc(self) -> bool:
        return self.dv is not None and getattr(self.dv, "kich_hoat", False)

    def ghi(self, project_id: str, ds: Sequence[BanGhiDeXuat], *,
            ai: str = "router-v09") -> List[Dict]:
        """Ghi những bản ghi KHÔNG cần người duyệt. Trả về kết quả từng cái."""
        if not self.dung_duoc:
            return [{"loai": b.loai, "bo_qua": "ký ức dự án chưa bật"}
                    for b in ds]
        ra: List[Dict] = []
        for b in ds:
            if b.can_nguoi_duyet:
                ra.append({"loai": b.loai, "cho_nguoi": True,
                           "tieu_de": b.tieu_de})
                continue
            if b.loai == "decision":
                kq = self.dv.ghi_quyet_dinh(
                    project_id, b.noi_dung, ly_do=b.ly_do, tieu_de=b.tieu_de,
                    ai=ai, quan_trong=b.quan_trong, tin_cay=b.tin_cay)
            else:
                kq = self.dv.ghi_ky_uc(
                    project_id, b.loai, b.noi_dung, tieu_de=b.tieu_de,
                    quan_trong=b.quan_trong, the=b.the, tin_cay=b.tin_cay,
                    ai=ai, nguon_loai="thuc_thi_v09")
            ra.append({"loai": b.loai, "tieu_de": b.tieu_de, "ket_qua": kq})
        return ra

    def diem_dung(self, project_id: str, y: YDinhThucThi,
                  bc: BaoCaoKiemDinh) -> Optional[Dict]:
        """Điểm dừng L3 — thứ làm phiên SAU tiếp tục được mà không dán tay."""
        if not self.dung_duoc:
            return None
        dd = self.dv.diem_dung_tuong_minh(
            project_id,
            f"thực thi {y.execution_id} kết thúc: {bc.trang_thai.value}",
            {"muc_tieu": y.goal,
             "da_xong": list(bc.buoc_dat),
             "chua_xong": list(bc.buoc_hong) + list(bc.buoc_thieu_bang_chung),
             "kiem_thu": bc.ly_do,
             "gia_thuyet": "",
             "tep_da_sua": []})
        return dd.to_dict() if dd is not None else None

"""`DichVuKyUc` — mặt tiền duy nhất mà engine / Leader / API nhìn thấy.

Một dịch vụ cho cả Control Center, một provider cho mỗi dự án (dựng lười,
giữ lại). Mọi thứ đi ra ngoài đều đã là dict/chuỗi sạch; mọi lỗi bên
trong đều đã được nuốt và ghi lại — người gọi chỉ cần hỏi `san_sang()`.

BA VIỆC CHÍNH:

1. **Ghi** — `ghi_nhan` được cắm vào hai chốt của `ControlStore`
   (`dang_ky_nguoi_theo`), nên lịch sử L0 tự đầy lên mà engine không phải
   gọi gì. Quyết định/kiến trúc/quy trình thì ghi TƯỜNG MINH qua
   `ghi_quyet_dinh`/`ghi_ky_uc` — không tự suy từ chat.
2. **Đọc cho Leader** — `khoi_cho_leader(pid, câu)` trả về MỘT khối chữ
   có trần token, dựng bởi `BoMayNguCanh`. Engine dán khối này vào nhắc
   nhở SAU ảnh chụp tĩnh, kèm `leader.LUAT_KY_UC` ở MỌI lượt có khối.
3. **Tiếp tục** — `tiep_tuc(pid)` là thứ một phiên MỚI gọi: viên nang +
   điểm dừng gần nhất + quyết định hiệu lực. Không cần ai dán handoff.

ĐIỂM DỪNG TỰ ĐỘNG. `diem_dung_tu_dong()` dựng từ trạng thái THẬT trong
sổ chính (việc đang chạy/đã xong/còn chặn), không từ lời kể. Có khoảng
cách tối thiểu giữa hai điểm dừng (mặc định 20 s) để một loạt việc kết
thúc liên tiếp không sinh 30 điểm dừng gần giống nhau.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.control_center.memory import config as cf
from scripts.control_center.memory.ghi_nhan import NguoiGhi
from scripts.control_center.memory.goi_ngu_canh import (BoMayNguCanh, GoiNguCanh,
                                                        NganSach, tuoi_chu)
from scripts.control_center.memory.model import (BangChung, DiemDung, KyUc,
                                                 LoaiKyUc, QuyetDinh, SuKien,
                                                 TinCay, VienNang, tuoc_moc)
from scripts.control_center.memory.provider import LocalMemoryProvider
from scripts.control_center.memory.de_bat import chon_ban_bi_thay_the as DB_chon


def duong_goc_ky_uc(root: Path) -> Path:
    """`<gốc>/.router/memory` — cạnh `control.db`, cùng vòng đời với nó."""
    return Path(root) / ".router" / "memory"


class DichVuKyUc:
    def __init__(self, store, root: Path, *, cau_hinh: Optional[Dict] = None):
        self.store = store
        self.root = Path(root)
        self.goc = duong_goc_ky_uc(self.root)
        try:
            self.cau_hinh, self.duong_cau_hinh = (cau_hinh, "tham số") if cau_hinh \
                else cf.nap(goc=self.root)
            self.loi_cau_hinh = ""
        except cf.CauHinhLoi as exc:
            # Cau hinh hong -> dung MAC DINH va noi ro. Khong tat ky uc vi
            # mot tep cau hinh sai; nhung cung khong lang le dung tep do.
            self.cau_hinh, self.duong_cau_hinh = dict(cf.MAC_DINH), "mặc định (mã)"
            self.loi_cau_hinh = str(exc)
        ns = self.cau_hinh.get("ngan_sach") or {}
        self.ngan_sach = NganSach(**{k: int(v) for k, v in ns.items()
                                     if k in NganSach.__dataclass_fields__})
        self._providers: Dict[str, LocalMemoryProvider] = {}
        self._khoa = threading.Lock()
        self._diem_dung_cuoi: Dict[str, float] = {}
        #: (ma, loai, ts) vua de bat theo du an — de khoi Leader noi "vua
        #: ghi tu tin nhan nay: qd_0001".
        self._de_bat_gan_nhat: Dict[str, List[tuple]] = {}
        self.ghi_nhan = NguoiGhi(self)
        if hasattr(store, "dang_ky_nguoi_theo") and self.kich_hoat:
            store.dang_ky_nguoi_theo(self.ghi_nhan)

    @property
    def kich_hoat(self) -> bool:
        return bool(self.cau_hinh.get("kich_hoat", True))

    # -- provider -----------------------------------------------------------

    def provider(self, project_id: str) -> Optional[LocalMemoryProvider]:
        if not project_id or not self.kich_hoat:
            return None
        with self._khoa:
            p = self._providers.get(project_id)
            if p is None:
                p = LocalMemoryProvider(self.goc, project_id)
                self._providers[project_id] = p
            return p

    def san_sang(self, project_id: str) -> Dict[str, Any]:
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "ly_do": "ký ức tắt trong cấu hình"
                    if not self.kich_hoat else "thiếu project_id"}
        ok, ly = p.san_sang()
        return {"san_sang": ok, "ly_do": ly, "che_do_tim": ly if ok else "",
                "ns": p.ns, "loi_cuoi": p.loi_cuoi}

    # -- doc cho Leader -----------------------------------------------------

    def goi_ngu_canh(self, project_id: str, cau: str) -> Optional[GoiNguCanh]:
        p = self.provider(project_id)
        if p is None:
            return None
        return BoMayNguCanh(p, self.ngan_sach).dung(cau)

    def khoi_cho_leader(self, project_id: str, cau: str) -> str:
        """Khối chữ dán vào nhắc nhở, hoặc `""` nếu không có gì / không sẵn."""
        g = self.goi_ngu_canh(project_id, cau)
        if g is None:
            return ""
        van = g.render()
        vua = self._vua_de_bat(project_id)
        if not van.strip() and not vua:
            return ""
        dau = (f"KÝ ỨC DỰ ÁN (lịch sử đã ghi — {g.lich_su_so_su_kien} sự kiện "
               f"trong sổ, gói này {g.token_uoc}/{g.token_tran} token, "
               f"{len(g.chon)} bản ghi được chọn, {g.bo_qua} bỏ qua):")
        if vua:
            # Nguoi dung vua tuyen bo -> he thong DA ghi. Noi ro de Leader xac
            # nhan bang MA thay vi hua "toi se ghi nho" (mot loi hua khong co
            # ban ghi nao dung sau — dung khuyet tat nghiem thu V0.6).
            dau += ("\nVỪA GHI TỰ ĐỘNG TỪ TIN NHẮN NÀY (đã có bản ghi, hãy xác nhận "
                    "bằng mã, KHÔNG ghi lại): "
                    + ", ".join(f"{ma} ({loai})" for ma, loai, _ in vua))
        return dau + "\n" + van

    # -- de bat (V0.6.1) -----------------------------------------------------

    def de_bat_tu_chat(self, project_id: str, text: str, sk: SuKien) -> Optional[Dict]:
        """Tuyên bố tường minh trong MỘT tin nhắn người dùng -> bản ghi L1.

        Gọi từ người ghi ngay sau khi dòng L0 được lưu, nên bằng chứng là
        chính dòng đó (`sk.id`). Trả về dict bản ghi hoặc `None` nếu tin
        nhắn không phải một tuyên bố.
        """
        from scripts.control_center.memory import de_bat as DB
        kq = DB.xet(text)
        if kq is None:
            return None
        return self.de_bat(project_id, kq, su_kien_id=sk.id,
                           nguon_loai="chat_user", ts_su_kien=sk.ts,
                           tin_cay=TinCay.USER_EXPLICIT, ai="nguoi_dung")

    def de_bat(self, project_id: str, kq, *, su_kien_id: int, nguon_loai: str,
               ts_su_kien: float = 0.0, tin_cay: TinCay = TinCay.USER_EXPLICIT,
               ai: str = "") -> Optional[Dict]:
        """Ghi một `KetQuaDeBat` thành ký ức có cấu trúc + xử lý thay thế."""
        p = self.provider(project_id)
        if p is None:
            return None
        bc = (BangChung(su_kien_id=int(su_kien_id), ghi_chu=f"tuyên bố ({nguon_loai})"),) \
            if su_kien_id else ()
        k = KyUc(loai=kq.loai, noi_dung=kq.noi_dung, tieu_de=kq.tieu_de,
                 quan_trong=8 if kq.loai in (LoaiKyUc.DECISION, LoaiKyUc.CONSTRAINT,
                                             LoaiKyUc.INCIDENT) else 7,
                 tin_cay=tin_cay, ts_su_kien=ts_su_kien or 0.0,
                 the=(kq.loai.value, tin_cay.value), bang_chung=bc,
                 meta={"dau_hieu": list(kq.dau_hieu)[:6]},
                 nguon_loai=nguon_loai, nguon_id=str(su_kien_id or ""))
        # Thay the: CHI khi nguoi dung noi the (xem `de_bat.py`).
        bi_thay = ""
        if kq.muon_thay_the:
            # Ma `qd_*` nguoi dung neu -> quy ve ky uc dung sau (ung vien
            # mang ma `ku_*`, con nguoi thi nho ma `qd_*`).
            for ma in kq.thay_the_tuong_minh:
                if ma.startswith("qd_"):
                    q = p.quyet_dinh(ma)
                    if q is not None and q.hieu_luc and q.ky_uc_ma != k.ma:
                        bi_thay = q.ky_uc_ma
                        break
                elif ma.startswith("ku_") and p.ky_uc(ma) is not None and ma != k.ma:
                    bi_thay = ma
                    break
            if not bi_thay:
                ung = [x for x in p.liet_ke(loai=kq.loai, limit=200, chi_hieu_luc=True)
                       if x.ma != k.ma]
                bi_thay = DB_chon(kq, ung) or ""
        if kq.loai is LoaiKyUc.DECISION:
            qd = p.them_quyet_dinh(k, thay_the_cho=(bi_thay,) if bi_thay else (),
                                   ly_do=f"tuyên bố tường minh ({nguon_loai})", ai=ai)
            if qd is None:
                return {"loi": p.loi_cuoi}
            self._cap_nhat_vien_nang_tu_quyet_dinh(project_id, p, qd)
            ma_hien = qd.ma
        else:
            ra = p.luu_ky_uc(k, ai=ai)
            if ra is None:
                return {"loi": p.loi_cuoi}
            if bi_thay:
                p.thay_the(k.ma, bi_thay, ai=ai)
            ma_hien = k.ma
        with self._khoa:
            self._de_bat_gan_nhat.setdefault(project_id, []).append(
                (ma_hien, kq.loai.value, time.time()))
            self._de_bat_gan_nhat[project_id] = self._de_bat_gan_nhat[project_id][-5:]
        self._ghi_su_kien_noi_bo(
            project_id, "MEMORY_PROMOTED",
            f"{kq.loai.value} {ma_hien}: {kq.tieu_de[:90]}"
            + (f" (thay thế {bi_thay})" if bi_thay else ""),
            {"ma": ma_hien, "ky_uc_ma": k.ma, "loai": kq.loai.value,
             "nguon_loai": nguon_loai, "su_kien_id": su_kien_id,
             "thay_the": bi_thay, "dau_hieu": list(kq.dau_hieu)[:4]})
        d = k.to_dict()
        d["ma_hien"] = ma_hien
        d["thay_the"] = bi_thay
        return d

    def _vua_de_bat(self, project_id: str, trong_giay: float = 8.0) -> List[tuple]:
        now = time.time()
        with self._khoa:
            return [x for x in self._de_bat_gan_nhat.get(project_id, [])
                    if now - x[2] <= trong_giay]

    # -- tiep tuc phien -----------------------------------------------------

    def tiep_tuc(self, project_id: str) -> Dict[str, Any]:
        """Gói TIẾP TỤC cho một phiên mới. Không cần Claude nhớ gì."""
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "ly_do": "ký ức không sẵn"}
        ok, ly = p.san_sang()
        if not ok:
            return {"san_sang": False, "ly_do": ly}
        vn = p.vien_nang()
        dd = p.nap_diem_dung()
        qd = [q.to_dict() for q in p.cac_quyet_dinh(chi_hieu_luc=True, limit=10)]
        tk = p.thong_ke()
        return {"san_sang": True, "project_id": project_id,
                "vien_nang": vn.to_dict() if vn else None,
                "diem_dung": dd.to_dict() if dd else None,
                "quyet_dinh_hieu_luc": qd,
                "so_su_kien": (tk.get("dem") or {}).get("su_kien", 0),
                "so_ky_uc": (tk.get("dem") or {}).get("ky_uc", 0),
                "co_gi_de_tiep_tuc": bool(dd or (vn and not vn.rong()))}

    # -- diem dung ----------------------------------------------------------

    def diem_dung_tu_dong(self, project_id: str, ly_do: str, *,
                          task_id: str = "", session_id: str = "",
                          ep: bool = False) -> Optional[DiemDung]:
        """Điểm dừng dựng từ SỔ CHÍNH. Có khoảng cách tối thiểu, trừ khi `ep`."""
        p = self.provider(project_id)
        if p is None:
            return None
        cd = self.cau_hinh.get("diem_dung") or {}
        cach = float(cd.get("toi_thieu_cach_giay", 20))
        now = time.time()
        if not ep and now - self._diem_dung_cuoi.get(project_id, 0.0) < cach:
            return None
        try:
            tasks = self.store.tasks(project_id, limit=60)
        except Exception:                                   # noqa: BLE001
            tasks = []
        dang = [t for t in tasks if t.state.value in ("RUNNING", "WAITING", "REVIEW")]
        xong = [t for t in tasks if t.state.value == "DONE"]
        ket = [t for t in tasks if t.state.value in ("BLOCKED", "FAILED", "PAUSED")]
        muc_tieu = ""
        if task_id:
            t0 = next((t for t in tasks if t.task_id == task_id), None)
            if t0:
                muc_tieu = f"{t0.task_id}: {t0.title or t0.objective[:120]}"
        if not muc_tieu and dang:
            muc_tieu = f"{dang[0].task_id}: {dang[0].title or dang[0].objective[:120]}"
        bang_chung = []
        for sk in p.su_kien(limit=6):
            bang_chung.append(f"sk#{sk.id}")
        cu = p.nap_diem_dung()
        dd = DiemDung(
            project_id=project_id, ly_do=ly_do[:200], muc_tieu=muc_tieu[:300],
            da_xong=tuple(f"{t.task_id} {t.title}"[:120] for t in xong[:8]),
            chua_xong=tuple(f"{t.task_id} [{t.state.value}] {t.blocked_reason or t.title}"[:160]
                            for t in ket[:8]),
            kiem_thu="", tep_da_sua=(), session_id=session_id, task_id=task_id,
            bang_chung=tuple(bang_chung), tiep_tuc_tu=cu.ma if cu else "")
        ra = p.diem_dung(dd)
        if ra is not None:
            self._diem_dung_cuoi[project_id] = now
            self._ghi_su_kien_noi_bo(project_id, "MEMORY_CHECKPOINT",
                                     f"{dd.ma}: {ly_do}", {"ma": dd.ma})
        return ra

    def diem_dung_tuong_minh(self, project_id: str, ly_do: str,
                             noi_dung: Dict[str, Any], *,
                             session_id: str = "") -> Optional[DiemDung]:
        """Điểm dừng do NGƯỞI/Leader khai: mục tiêu, đã xong, giả thuyết…"""
        p = self.provider(project_id)
        if p is None:
            return None
        cu = p.nap_diem_dung()

        def _ds(k):
            v = noi_dung.get(k) or ()
            if isinstance(v, str):
                v = [x.strip() for x in v.split("\n") if x.strip()]
            return tuple(str(x)[:200] for x in v)[:12]

        dd = DiemDung(project_id=project_id, ly_do=(ly_do or "handoff")[:200],
                      muc_tieu=str(noi_dung.get("muc_tieu") or "")[:400],
                      da_xong=_ds("da_xong"),
                      gia_thuyet=str(noi_dung.get("gia_thuyet") or "")[:400],
                      tep_da_sua=_ds("tep_da_sua"),
                      kiem_thu=str(noi_dung.get("kiem_thu") or "")[:300],
                      chua_xong=_ds("chua_xong"), session_id=session_id,
                      task_id=str(noi_dung.get("task_id") or ""),
                      bang_chung=_ds("bang_chung"),
                      tiep_tuc_tu=cu.ma if cu else "")
        ra = p.diem_dung(dd)
        if ra is not None:
            self._diem_dung_cuoi[project_id] = time.time()
            self._ghi_su_kien_noi_bo(project_id, "MEMORY_CHECKPOINT",
                                     f"{dd.ma}: {dd.ly_do} (tường minh)",
                                     {"ma": dd.ma})
        return ra

    @staticmethod
    def _su_kien_ghi_tuong_minh(p, loai: str, noi_dung: str, *, ai: str,
                                meta: Dict) -> Optional[SuKien]:
        try:
            return p.ghi_su_kien(SuKien(loai=f"ghi_tuong_minh:{loai}",
                                        ts=time.time(), tom_tat=noi_dung,
                                        nguon="api", meta={"ai": ai, **meta}),
                                 noi_dung_day=noi_dung)
        except Exception:                                   # noqa: BLE001
            return None

    def _ghi_su_kien_noi_bo(self, project_id: str, kind: str, detail: str,
                            meta: Dict) -> None:
        try:
            self.store.ghi_su_kien(kind, project_id=project_id, detail=detail,
                                   meta=meta)
        except Exception:                                   # noqa: BLE001
            pass

    # -- ghi tuong minh -----------------------------------------------------

    def ghi_ky_uc(self, project_id: str, loai: str, noi_dung: str, *,
                  tieu_de: str = "", quan_trong: int = 6, the: Sequence[str] = (),
                  tin_cay: str = "ghi_nhan", ai: str = "",
                  bang_chung: Sequence[int] = (),
                  nguon_loai: str = "api") -> Optional[Dict]:
        p = self.provider(project_id)
        if p is None:
            return None
        # NGUON GOC CHO MOI BAN GHI TUONG MINH: ghi mot dong L0 truoc, roi
        # noi ky uc vao do. "Vi sao anh nho dieu nay?" -> "vi <ai> ghi luc
        # <ts> qua API", ke ca khi khong co su kien he thong nao dung sau.
        goc = self._su_kien_ghi_tuong_minh(p, "ky_uc", noi_dung, ai=ai,
                                           meta={"loai": loai, "tieu_de": tieu_de})
        try:
            bc = [BangChung(su_kien_id=int(x)) for x in bang_chung if int(x) > 0]
            if goc is not None:
                bc.append(BangChung(su_kien_id=goc.id, ghi_chu="ghi tường minh"))
            k = KyUc(loai=LoaiKyUc(loai), noi_dung=noi_dung, tieu_de=tieu_de,
                     quan_trong=int(quan_trong), tin_cay=TinCay(tin_cay),
                     the=tuple(the), bang_chung=tuple(bc),
                     nguon_loai=nguon_loai,
                     nguon_id=str(goc.id) if goc is not None else "")
        except (ValueError, TypeError) as exc:
            return {"loi": str(exc)}
        ra = p.luu_ky_uc(k, ai=ai)
        if ra is None:
            return {"loi": p.loi_cuoi}
        self._ghi_su_kien_noi_bo(project_id, "MEMORY_RECORDED",
                                 f"{ra.loai.value} {ra.ma}: {ra.tieu_de or ra.noi_dung[:80]}",
                                 {"ma": ra.ma, "loai": ra.loai.value})
        return ra.to_dict()

    def ghi_quyet_dinh(self, project_id: str, noi_dung: str, *, ly_do: str = "",
                       tieu_de: str = "", thay_the_cho: Sequence[str] = (),
                       ai: str = "", quan_trong: int = 8,
                       tin_cay: str = "ghi_nhan") -> Optional[Dict]:
        p = self.provider(project_id)
        if p is None:
            return None
        nguon_loai = "leader" if ai == "leader" else "api"
        goc = self._su_kien_ghi_tuong_minh(
            p, "quyet_dinh", noi_dung, ai=ai,
            meta={"ly_do": ly_do[:500], "tieu_de": tieu_de,
                  "thay_the_cho": list(thay_the_cho)})
        try:
            k = KyUc(loai=LoaiKyUc.DECISION, noi_dung=noi_dung, tieu_de=tieu_de,
                     quan_trong=int(quan_trong), tin_cay=TinCay(tin_cay),
                     the=("decision",), meta={"ly_do": ly_do[:1000]},
                     bang_chung=((BangChung(su_kien_id=goc.id,
                                            ghi_chu="ghi tường minh"),)
                                 if goc is not None else ()),
                     nguon_loai=nguon_loai,
                     nguon_id=str(goc.id) if goc is not None else "")
        except (ValueError, TypeError) as exc:
            return {"loi": str(exc)}
        qd = p.them_quyet_dinh(k, thay_the_cho=tuple(thay_the_cho), ly_do=ly_do,
                               ai=ai)
        if qd is None:
            return {"loi": p.loi_cuoi}
        # Vien nang: cap nhat danh sach quyet dinh hieu luc — co chu dich.
        self._cap_nhat_vien_nang_tu_quyet_dinh(project_id, p, qd)
        self._ghi_su_kien_noi_bo(project_id, "MEMORY_RECORDED",
                                 f"quyết định {qd.ma}: {tieu_de or noi_dung[:80]}",
                                 {"ma": qd.ma, "ky_uc_ma": qd.ky_uc_ma,
                                  "thay_the_cho": list(thay_the_cho)})
        d = qd.to_dict()
        d["ky_uc"] = k.to_dict()
        return d

    def _cap_nhat_vien_nang_tu_quyet_dinh(self, project_id: str, p, qd: QuyetDinh):
        vn = p.vien_nang() or VienNang(project_id=project_id)
        hieu_luc = [q.ma for q in p.cac_quyet_dinh(chi_hieu_luc=True, limit=20)]
        vn.quyet_dinh_hieu_luc = tuple(hieu_luc)
        vn.ly_do = f"quyết định {qd.ma}"
        vn.bang_chung = tuple(set(vn.bang_chung) | {qd.ky_uc_ma})
        p.cap_nhat_vien_nang(vn)

    def cap_nhat_vien_nang(self, project_id: str, thay_doi: Dict[str, Any], *,
                           ly_do: str = "") -> Optional[Dict]:
        """Cập nhật CÓ CHỦ ĐÍCH: chỉ trường được đưa, phiên bản tăng."""
        p = self.provider(project_id)
        if p is None:
            return None
        vn = p.vien_nang() or VienNang(project_id=project_id)
        cho_phep = {"muc_tieu", "kien_truc", "moc_hien_tai", "rang_buoc",
                    "van_de_da_biet", "moc_gan_day"}
        for k, v in (thay_doi or {}).items():
            if k not in cho_phep:
                continue
            if k in ("rang_buoc", "van_de_da_biet", "moc_gan_day"):
                if isinstance(v, str):
                    v = [x.strip() for x in v.split("\n") if x.strip()]
                setattr(vn, k, tuple(str(x)[:300] for x in (v or ()))[:12])
            else:
                setattr(vn, k, str(v or "")[:1200])
        vn.ly_do = (ly_do or "cập nhật tường minh")[:400]
        ra = p.cap_nhat_vien_nang(vn)
        return ra.to_dict() if ra else {"loi": p.loi_cuoi}

    # -- doc cho UI ---------------------------------------------------------

    def tim(self, project_id: str, cau: str, *, loai: str = "",
            limit: int = 30) -> Dict[str, Any]:
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "ket_qua": [], "su_kien": []}
        lo = LoaiKyUc(loai) if loai in LoaiKyUc._value2member_map_ else None
        ung = p.tim(cau, loai=lo, limit=limit * 2)
        xep = BoMayNguCanh(p, self.ngan_sach).cham_diem(ung)[:limit]
        sk = p.tim_su_kien(cau, limit=limit) if not loai else []
        return {"san_sang": True, "cau": cau, "che_do_tim": p.san_sang()[1],
                "ket_qua": [{**m.ky_uc.to_dict(), "diem": round(m.diem, 4),
                             "tuoi_chu": tuoi_chu(m.ky_uc.tuoi)} for m in xep],
                "su_kien": [{**s.to_dict(), "tuoi_chu": tuoi_chu(time.time() - s.ts)}
                            for s in sk]}

    def dong_thoi_gian(self, project_id: str, *, limit: int = 100,
                       truoc_id: int = 0, loai: str = "") -> Dict[str, Any]:
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "su_kien": []}
        ds = p.su_kien(limit=limit, truoc_id=truoc_id, loai=loai)
        return {"san_sang": True,
                "su_kien": [{**s.to_dict(), "tuoi_chu": tuoi_chu(time.time() - s.ts)}
                            for s in ds]}

    def liet_ke(self, project_id: str, loai: str, *, limit: int = 100) -> Dict:
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "ket_qua": []}
        if loai == "decision":
            qds = p.cac_quyet_dinh(limit=limit)
            ra = []
            for q in qds:
                k = p.ky_uc(q.ky_uc_ma)
                d = q.to_dict()
                d["ky_uc"] = k.to_dict() if k else None
                ra.append(d)
            return {"san_sang": True, "ket_qua": ra}
        if loai == "checkpoint":
            return {"san_sang": True,
                    "ket_qua": [d.to_dict() for d in p.cac_diem_dung(limit)]}
        lo = LoaiKyUc(loai) if loai in LoaiKyUc._value2member_map_ else None
        ds = p.liet_ke(loai=lo, limit=limit)
        return {"san_sang": True,
                "ket_qua": [{**k.to_dict(), "tuoi_chu": tuoi_chu(k.tuoi)}
                            for k in ds]}

    def ban_ghi(self, project_id: str, ma: str) -> Dict[str, Any]:
        """Một bản ghi + trạng thái thay thế + bằng chứng — 'vì sao nhớ?'."""
        p = self.provider(project_id)
        if p is None:
            return {"co": False, "ly_do": "ký ức không sẵn"}
        if ma.startswith("qd_"):
            q = p.quyet_dinh(ma)
            if not q:
                return {"co": False, "ly_do": f"không có quyết định {ma}"}
            k = p.ky_uc(q.ky_uc_ma)
            return {"co": True, "quyet_dinh": q.to_dict(),
                    "ky_uc": k.to_dict() if k else None,
                    "bang_chung": [p.bang_chung(su_kien_id=b.su_kien_id,
                                                blob_sha=b.blob_sha)
                                   for b in (k.bang_chung if k else ())]}
        if ma.startswith("dd_"):
            d = p.nap_diem_dung(ma)
            return {"co": bool(d), "diem_dung": d.to_dict() if d else None}
        if ma.startswith("sk#") or ma.isdigit():
            sid = int(ma.replace("sk#", ""))
            return {"co": True, **p.bang_chung(su_kien_id=sid)}
        k = p.ky_uc(ma)
        if not k:
            return {"co": False, "ly_do": f"không có ký ức {ma}"}
        p.cham(ma)
        qd = next((q for q in p.cac_quyet_dinh(limit=500) if q.ky_uc_ma == ma), None)
        return {"co": True, "ky_uc": k.to_dict(),
                "quyet_dinh": qd.to_dict() if qd else None,
                "bang_chung": [p.bang_chung(su_kien_id=b.su_kien_id,
                                            blob_sha=b.blob_sha)
                               for b in k.bang_chung]}

    def bang_chung(self, project_id: str, *, su_kien_id: int = 0,
                   blob_sha: str = "") -> Dict[str, Any]:
        p = self.provider(project_id)
        if p is None:
            return {"co": False, "ly_do": "ký ức không sẵn"}
        return p.bang_chung(su_kien_id=su_kien_id, blob_sha=blob_sha)

    # -- nhap khau lich su (V0.6.1) ----------------------------------------

    def _bo_nhap_khau(self, project_id: str, goc_claude=None):
        from scripts.control_center.memory.nhap_khau import (BoNhapKhau,
                                                             adapters_mac_dinh)
        p = self.provider(project_id)
        if p is None or not p.san_sang()[0]:
            return None
        du_an = None
        try:
            du_an = self.store.project(project_id)
        except Exception:                                   # noqa: BLE001
            du_an = None
        if du_an is None:
            return None
        return BoNhapKhau(p, adapters_mac_dinh(self.store, du_an, goc_claude=goc_claude))

    def nguon_nhap_khau(self, project_id: str, *, goc_claude=None) -> Dict[str, Any]:
        """Nguồn nào sẵn / đã nhập bao nhiêu / lần cuối — không ghi gì."""
        bo = self._bo_nhap_khau(project_id, goc_claude)
        if bo is None:
            return {"san_sang": False, "ly_do": "ký ức không sẵn hoặc không có dự án",
                    "nguon": []}
        try:
            return {"san_sang": True, "nguon": bo.trang_thai(),
                    "moc_ky_uc": bo.moc_ky_uc}
        except Exception as exc:                            # noqa: BLE001
            return {"san_sang": False, "ly_do": f"{type(exc).__name__}: {exc}"[:200],
                    "nguon": []}

    def nhap_khau(self, project_id: str, *, thu_kho: bool = False,
                  chi: Optional[Sequence[str]] = None, goc_claude=None) -> Dict[str, Any]:
        """Quét/nhập lịch sử. `thu_kho=True` chỉ đếm. Idempotent, resumable."""
        bo = self._bo_nhap_khau(project_id, goc_claude)
        if bo is None:
            return {"san_sang": False, "ly_do": "ký ức không sẵn hoặc không có dự án"}
        t0 = time.time()
        ds = bo.chay(thu_kho=thu_kho, chi=chi)
        tong = {"kham_pha": 0, "da_nhap": 0, "trung": 0, "bo_qua": 0, "da_loc": 0,
                "de_bat": 0, "con_lai": 0, "khong_san": 0}
        for tk in ds:
            for k in tong:
                if k == "khong_san":
                    tong[k] += 1 if tk.khong_san else 0
                else:
                    tong[k] += getattr(tk, k)
        if not thu_kho:
            self._ghi_su_kien_noi_bo(
                project_id, "MEMORY_BACKFILL",
                f"nhập {tong['da_nhap']} mục từ {len(ds)} nguồn · trùng {tong['trung']} "
                f"· đề bạt {tong['de_bat']} · không sẵn {tong['khong_san']}",
                {"thu_kho": thu_kho, "tong": tong, "nguon": [t.to_dict() for t in ds]})
            try:
                bo.p.kho.toi_uu()
            except Exception:                               # noqa: BLE001
                pass
        return {"san_sang": True, "thu_kho": thu_kho, "giay": round(time.time() - t0, 2),
                "tong": tong, "nguon": [t.to_dict() for t in ds],
                "moc_ky_uc": bo.moc_ky_uc}

    # -- thong ke -----------------------------------------------------------

    def thong_ke(self, project_id: str) -> Dict[str, Any]:
        p = self.provider(project_id)
        if p is None:
            return {"san_sang": False, "ly_do": "ký ức không sẵn"}
        tk = p.thong_ke()
        tk["cau_hinh"] = {"duong": self.duong_cau_hinh, "loi": self.loi_cau_hinh,
                          "ngan_sach": self.ngan_sach.__dict__}
        tk["ghi_nhan"] = {"so_ghi": self.ghi_nhan.so_ghi,
                          "so_loi": self.ghi_nhan.so_loi,
                          "loi_cuoi": self.ghi_nhan.loi_cuoi}
        return tk

    def thong_ke_toan_cuc(self) -> Dict[str, Any]:
        """Tổng trên MỌI thư mục dự án dưới gốc — đọc đĩa, không mở sổ lạ."""
        ra: Dict[str, Any] = {"goc": str(self.goc), "du_an": [], "tong_byte": 0}
        if not self.goc.is_dir():
            return ra
        for d in sorted(self.goc.iterdir()):
            if not d.is_dir():
                continue
            tong = 0
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        tong += f.stat().st_size
                    except OSError:
                        pass
            ra["du_an"].append({"ns": d.name, "byte": tong})
            ra["tong_byte"] += tong
        return ra

    def close(self) -> None:
        with self._khoa:
            for p in self._providers.values():
                p.close()

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
        if not van.strip():
            return ""
        return (f"KÝ ỨC DỰ ÁN (lịch sử đã ghi — {g.lich_su_so_su_kien} sự kiện "
                f"trong sổ, gói này {g.token_uoc}/{g.token_tran} token, "
                f"{len(g.chon)} bản ghi được chọn, {g.bo_qua} bỏ qua):\n" + van)

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
                  bang_chung: Sequence[int] = ()) -> Optional[Dict]:
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
                     the=tuple(the), bang_chung=tuple(bc))
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
                       ai: str = "", quan_trong: int = 8) -> Optional[Dict]:
        p = self.provider(project_id)
        if p is None:
            return None
        goc = self._su_kien_ghi_tuong_minh(
            p, "quyet_dinh", noi_dung, ai=ai,
            meta={"ly_do": ly_do[:500], "tieu_de": tieu_de,
                  "thay_the_cho": list(thay_the_cho)})
        try:
            k = KyUc(loai=LoaiKyUc.DECISION, noi_dung=noi_dung, tieu_de=tieu_de,
                     quan_trong=int(quan_trong), tin_cay=TinCay.GHI_NHAN,
                     the=("decision",), meta={"ly_do": ly_do[:1000]},
                     bang_chung=((BangChung(su_kien_id=goc.id,
                                            ghi_chu="ghi tường minh"),)
                                 if goc is not None else ()))
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

"""`DichVuQuanSat` — dựng provider theo cấu hình, chạy song song, có bộ đệm.

BA RÀNG BUỘC HIỆU NĂNG, và mỗi cái sửa một cách làm treo giao diện:

1. **Chạy song song, mỗi probe một trần thời gian riêng.** Một probe SSH
   mất 3–8s; chạy tuần tự bốn provider là 30s cho một tin nhắn chat.
2. **Bộ đệm + trả-cũ-rồi-làm-mới** (`stale-while-revalidate`). Câu hỏi
   thứ hai trong cùng một phút không được gọi SSH lần nữa: vừa chậm vừa
   là spam vào máy production.
3. **Không bao giờ ném.** Provider nào hỏng thì khối của nó mang
   `UNKNOWN` kèm lý do; lượt chat vẫn chạy. Một endpoint production chậm
   KHÔNG được làm vỡ hội thoại Router bình thường.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as HetHan
from typing import Any, Dict, List, Optional, Sequence

from scripts.control_center.observability import config as _cf
from scripts.control_center.observability.model import (AnhChupSong,
                                                        KhoiQuanSat, QuanSat,
                                                        TrangThai)
from scripts.control_center.observability.providers import (GitProvider,
                                                            ProbeChuaCoDuong,
                                                            RouterProvider,
                                                            SshServiceProvider)

#: Bao lau thi mot anh chup con duoc tra ngay (khong do lai).
TUOI_TUOI = 25.0
#: Bao lau thi mot anh chup cu VAN duoc tra ra kem nhan STALE, trong khi
#: mot lan do moi chay o luong nen. Qua nguong nay thi phai do dong bo.
TUOI_CON_DUNG = 180.0
#: Tran cho CA mot lan thu snapshot. Khong de mot provider treo lam ca
#: luot chat dung.
TRAN_TONG = 20.0


class DichVuQuanSat:
    """Một thực thể cho mỗi `ControlCenter`."""

    def __init__(self, store, *, cau_hinh: Optional[Dict] = None,
                 duong_cau_hinh=None):
        self.store = store
        self._loi_cau_hinh = ""
        if cau_hinh is not None:
            self._cf = _cf.kiem_cau_hinh(cau_hinh)
        else:
            # GHI LAI DUONG DAN DA DUNG. Khong co dong nay thi mot lan
            # "cau hinh khong an" khong the chan doan tu ben ngoai: hai
            # tep hop le nhu nhau, va anh chup khong noi no doc tep nao.
            # Da vap that o lan nghiem thu V0.5 dau tien.
            self._duong_da_dung = duong_cau_hinh or self._duong_ghi_de()
            try:
                self._cf = _cf.nap(self._duong_da_dung)
            except _cf.CauHinhLoi as exc:
                # Cau hinh sai KHONG duoc lam mat ca tinh nang: roi ve
                # quan sat chung, va noi ro vi sao o moi anh chup.
                self._cf = {"projects": {}}
                self._loi_cau_hinh = str(exc)
        if not hasattr(self, "_duong_da_dung"):
            self._duong_da_dung = None
        self._khoa = threading.Lock()
        self._dem: Dict[str, AnhChupSong] = {}
        self._dang_lam: Dict[str, bool] = {}

    def _duong_ghi_de(self):
        """Cấu hình RIÊNG CỦA MỘT BẢN CÀI, nếu có: `<gốc>/.router/
        observability.json`.

        VÌ SAO CẦN: cấu hình mặc định đi kèm trong gói EXE
        (`_internal/scripts/control_center/config/`), nên nó là thứ chung
        cho mọi bản cài. Một người dùng muốn khai host/khoá của CHÍNH máy
        họ thì không thể sửa vào trong gói — và cũng không nên, vì lần
        cập nhật sau sẽ ghi đè.

        Trả `None` khi không có, để `config.nap()` dùng đường mặc định.
        """
        try:
            goc = Path(self.store.path).resolve().parents[2]
        except Exception:                               # noqa: BLE001
            return None
        p = goc / ".router" / "observability.json"
        return p if p.is_file() else None

    # -- dung provider ------------------------------------------------------

    def _providers(self, project_id: str) -> List[Any]:
        """Provider cho MỘT dự án.

        `GenericProjectProvider` = Router + git, và mọi dự án đều có.
        Dự án nào khai thêm trong cấu hình thì được CỘNG vào, không phải
        thay thế — nên Fanfic chỉ là "chung + probe riêng", đúng như mục 8.
        """
        ds: List[Any] = [RouterProvider(), GitProvider()]
        c = (self._cf.get("projects") or {}).get(project_id) or {}
        for p in (c.get("providers") or []):
            loai = p.get("type")
            if loai in ("router", "git"):
                continue                        # da co o phan chung
            if loai == "ssh_service":
                ds.append(SshServiceProvider(p))
            elif loai == "unavailable":
                ds.append(ProbeChuaCoDuong(
                    ma=str(p["id"]), nhan=str(p.get("label") or p["id"]),
                    nhom=str(p.get("group") or "ung_dung"),
                    ly_do=str(p["reason"]),
                    kha_nang=tuple(p.get("capabilities") or ())))
        return ds

    def kha_nang(self, project_id: str) -> Dict[str, List[str]]:
        return {p.ma: list(p.kha_nang()) for p in self._providers(project_id)}

    # -- thu -----------------------------------------------------------------

    def _thu_that(self, project_id: str) -> AnhChupSong:
        ctx = {"store": self.store, "project_id": project_id,
               "repo_path": self._duong_kho(project_id)}
        provs = self._providers(project_id)
        a = AnhChupSong(project_id=project_id)
        nhat_ky: List[Dict] = []
        with ThreadPoolExecutor(max_workers=max(2, len(provs))) as bom:
            fut = {bom.submit(p.thu, ctx): p for p in provs}
            for f, p in fut.items():
                t0 = time.perf_counter()
                try:
                    k = f.result(timeout=max(p.han + 2.0, 5.0))
                except HetHan:
                    k = KhoiQuanSat(khoa=p.ma, nhan=p.nhan)
                    k.them(QuanSat(khoa="probe",
                                   trang_thai=TrangThai.UNKNOWN,
                                   nguon=p.ma,
                                   ly_do=f"quá hạn {p.han:.0f}s"))
                except Exception as exc:            # noqa: BLE001
                    k = KhoiQuanSat(khoa=p.ma, nhan=p.nhan)
                    k.them(QuanSat(khoa="probe",
                                   trang_thai=TrangThai.UNKNOWN,
                                   nguon=p.ma,
                                   ly_do=f"{type(exc).__name__}: {exc}"[:180]))
                getattr(a, p.nhom)[k.khoa] = k
                nhat_ky.append({
                    "provider": p.ma, "nhom": p.nhom,
                    "giay": round(time.perf_counter() - t0, 3),
                    "trang_thai": k.trang_thai.value})
        nhat_ky.append({
            "provider": "config", "nhom": "-", "giay": 0.0,
            "trang_thai": ("UNAVAILABLE" if self._loi_cau_hinh
                           else "ACTIVE"),
            "duong": str(self._duong_da_dung or _cf.DUONG_MAC_DINH),
            "ghi_de": self._duong_da_dung is not None,
            "ly_do": self._loi_cau_hinh})
        a.nhat_ky_provider = nhat_ky
        return a

    def _duong_kho(self, project_id: str) -> str:
        try:
            p = self.store.project(project_id)
        except Exception:                           # noqa: BLE001
            return ""
        return str(getattr(p, "repo_path", "") or "") if p else ""

    # -- bo dem --------------------------------------------------------------

    def anh_chup(self, project_id: str, *, buoc_moi: bool = False
                 ) -> AnhChupSong:
        """Ảnh chụp sống. Mặc định đi qua bộ đệm.

        `buoc_moi=True` cho nút "làm mới" của người dùng — một cú bấm
        tường minh thì phải đo lại thật, không trả bộ đệm.
        """
        if buoc_moi:
            a = self._thu_that(project_id)
            with self._khoa:
                self._dem[project_id] = a
            return a
        with self._khoa:
            cu = self._dem.get(project_id)
        if cu is not None and cu.tuoi <= TUOI_TUOI:
            return cu
        if cu is not None and cu.tuoi <= TUOI_CON_DUNG:
            # TRA CU RIGHT NOW, lam moi o luong nen. Nguoi dung thay so
            # kem nhan tuoi thay vi cho 8s.
            self._lam_moi_nen(project_id)
            return cu
        a = self._thu_that(project_id)
        with self._khoa:
            self._dem[project_id] = a
        return a

    def _lam_moi_nen(self, project_id: str) -> None:
        with self._khoa:
            if self._dang_lam.get(project_id):
                return
            self._dang_lam[project_id] = True

        def _chay():
            try:
                a = self._thu_that(project_id)
                with self._khoa:
                    self._dem[project_id] = a
            except Exception:                       # noqa: BLE001
                pass
            finally:
                with self._khoa:
                    self._dang_lam[project_id] = False

        threading.Thread(target=_chay, daemon=True).start()

    def tu_bo_dem(self, project_id: str) -> Optional[AnhChupSong]:
        with self._khoa:
            return self._dem.get(project_id)


def tom_tat_cho_leader(a: AnhChupSong, *, gioi_han: int = 1400) -> str:
    """Bản NGẮN, có nguồn gốc, để nhét vào ngữ cảnh Leader.

    Viết tách bạch hai phần và nói thẳng rằng chúng độc lập — vì chính
    chỗ gộp hai phần đó lại là lỗi mà V0.5 tồn tại để sửa.
    """
    d: List[str] = ["TRẠNG THÁI SỐNG (vừa đo, KHÔNG phải ký ức):"]
    r = a.router
    viec = r.get("router").lay("running_tasks") if r.get("router") else None
    agent = r.get("router").lay("live_agents") if r.get("router") else None
    d.append(f"  [ROUTER] việc đang chạy={viec.gia_tri if viec else '?'}"
             f" · agent sống={agent.gia_tri if agent else '?'}")
    d.append("  [NGOÀI]  (độc lập với Router — Router rảnh KHÔNG có nghĩa "
             "là dịch vụ ngoài đã dừng)")
    kh = a.khoi_ngoai()
    if not kh:
        d.append("    (dự án này chưa khai probe ngoài nào)")
    for k in kh:
        d.append(f"    {k.nhan or k.khoa}: {k.trang_thai.value}"
                 + (f" — {k.ly_do}" if k.ly_do else ""))
        for q in k.quan_sat:
            hl = q.hieu_luc()
            if hl.do_duoc and q.gia_tri is not None:
                d.append(f"      {q.nhan or q.khoa} = {q.gia_tri}"
                         f"  (nguồn {q.nguon}, {q.tuoi:.0f}s trước)")
            elif hl in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE,
                        TrangThai.STALE):
                d.append(f"      {q.nhan or q.khoa}: {hl.value}"
                         + (f" — {q.ly_do}" if q.ly_do else ""))
    d.append(f"  tổng thể phần NGOÀI: {a.trang_thai_chung.value}"
             f" · có bằng chứng sống: "
             f"{'CÓ' if a.co_bang_chung_song() else 'KHÔNG'}")
    van = "\n".join(d)
    return van[:gioi_han]

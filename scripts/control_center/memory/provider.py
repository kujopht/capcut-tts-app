"""`MemoryProvider` — giao diện mà Leader/engine phụ thuộc vào, và bản cục bộ.

VÌ SAO CÓ MỘT GIAO DIỆN. Quyết định V0.6 (xem báo cáo, mục TencentDB) là
**tự dựng lớp cục bộ** thay vì tích hợp TencentDB Agent Memory. Nhưng lý
do quyết định đó có thể đổi — một provider ngữ nghĩa, một provider đám
mây. Nên phần còn lại của Control Center chỉ được biết `MemoryProvider`;
`LocalMemoryProvider` là MỘT bản cài, không phải bản duy nhất có thể.

Ánh xạ với tên trong yêu cầu (§11):

    append_event            -> ghi_su_kien
    store_memory            -> luu_ky_uc
    retrieve                -> tim
    checkpoint              -> diem_dung
    load_checkpoint         -> nap_diem_dung
    get_project_capsule     -> vien_nang
    update_project_capsule  -> cap_nhat_vien_nang
    evidence                -> bang_chung
    stats                   -> thong_ke

HỢP ĐỒNG SỐ MỘT: **không phương thức nào ném.** Ký ức chạy trên đường của
một tin nhắn chat và của mọi sự kiện Router; một sổ hỏng không được làm
Router hỏng theo. Lỗi đi vào `loi_cuoi` và `san_sang()`; giá trị trả về là
`None`/rỗng, và người gọi được kỳ vọng nói "ký ức KHÔNG SẴN" chứ không đoán.

`KHONG_DUOC_CO`: từ vựng CẤM trong gói này, cùng cơ chế với
`observability.provider.KHONG_DUOC_CO` — có bài kiểm quét cả gói. Một lớp
ký ức không có đường tác động lên production, không có đường xoá lịch sử
L0, và không nói dối về usage. Từ khác `observability` có chủ ý: bảng đó
cấm `truncate`/`unlink`/`kill ` mà một sổ SQLite dùng tự nhiên; ở đây cấm
đúng thứ ký ức có thể làm sai.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from scripts.control_center.memory.blob import KhoBlob
from scripts.control_center.memory.kho import TRAN_TOM_TAT, KhoKyUc
from scripts.control_center.memory.model import (BangChung, DiemDung, KyUc,
                                                 LoaiKyUc, QuyetDinh, SuKien,
                                                 VienNang, khong_gian_ten)

#: Dong tu/cum KHONG BAO GIO duoc xuat hien trong ma cua goi nay.
#: (Xem docstring; bai kiem quet `scripts/control_center/memory/*.py`.)
KHONG_DUOC_CO: Sequence[str] = (
    "DELETE FROM su_kien", "DROP TABLE su_kien", "UPDATE su_kien",
    "DELETE FROM ky_uc", "DROP TABLE ky_uc",
    "systemctl restart", "systemctl stop", "systemctl start",
    "wrangler deploy", "wrangler delete", "aws s3 rm", "aws s3 cp",
    "appwrite databases delete", "drive.files.delete",
    "shutil.rmtree", "os.remove(", "os.unlink(", "rmdir(",
    # Hai chuoi "bo qua quyen" KHONG nam o day co chu dich: chinh chuoi
    # do da bi `test_control_center_core.TestRaoAnToanTinh` cam tren TOAN
    # goi control_center (quet de quy), nen liet ke chung o day la tu lam
    # do bai kiem do. Goi nay thua huong rao ay mien phi.
)


class MemoryProvider(Protocol):
    """Một nguồn ký ức cho MỘT dự án. Không phương thức nào ném."""

    ma: str
    nhan: str
    project_id: str

    def san_sang(self) -> Tuple[bool, str]: ...
    def ghi_su_kien(self, sk: SuKien, *,
                    noi_dung_day: str = "") -> Optional[SuKien]: ...
    def luu_ky_uc(self, k: KyUc, *, ai: str = "") -> Optional[KyUc]: ...
    def tim(self, cau: str, *, loai: Optional[LoaiKyUc] = None,
            limit: int = 50) -> List[Tuple[KyUc, float]]: ...
    def diem_dung(self, dd: DiemDung) -> Optional[DiemDung]: ...
    def nap_diem_dung(self, ma: str = "") -> Optional[DiemDung]: ...
    def vien_nang(self) -> Optional[VienNang]: ...
    def cap_nhat_vien_nang(self, vn: VienNang) -> Optional[VienNang]: ...
    def bang_chung(self, *, su_kien_id: int = 0,
                   blob_sha: str = "") -> Dict[str, Any]: ...
    def thong_ke(self) -> Dict[str, Any]: ...


class LocalMemoryProvider:
    """Sổ SQLite + kho blob cục bộ ở `<goc>/<ns>/`. Không ném."""

    ma = "local"
    nhan = "Ký ức cục bộ (SQLite + FTS5)"

    def __init__(self, goc: Path, project_id: str):
        self.project_id = project_id
        self.ns = khong_gian_ten(project_id)
        self.thu_muc = Path(goc) / self.ns
        self.loi_cuoi = ""
        self._kho: Optional[KhoKyUc] = None
        self._blob: Optional[KhoBlob] = None
        try:
            self._kho = KhoKyUc(self.thu_muc / "memory.db")
            self._blob = KhoBlob(self.thu_muc / "blobs")
        except Exception as exc:                            # noqa: BLE001
            self.loi_cuoi = f"mở sổ: {type(exc).__name__}: {exc}"[:300]

    # -- suc khoe -----------------------------------------------------------

    def san_sang(self) -> Tuple[bool, str]:
        if self._kho is None or self._blob is None:
            return False, self.loi_cuoi or "sổ chưa mở"
        return True, ("FTS5" if self._kho.co_fts
                      else f"LIKE dự phòng ({self._kho.ly_do_khong_fts})")

    @property
    def kho(self) -> Optional[KhoKyUc]:
        return self._kho

    @property
    def blob(self) -> Optional[KhoBlob]:
        return self._blob

    def _that_bai(self, viec: str, exc: BaseException) -> None:
        self.loi_cuoi = f"{viec}: {type(exc).__name__}: {exc}"[:300]

    # -- L0 ---------------------------------------------------------------

    def ghi_su_kien(self, sk: SuKien, *,
                    noi_dung_day: str = "") -> Optional[SuKien]:
        """Ghi một sự kiện. Nội dung dài đi vào blob, sổ giữ tóm tắt.

        `noi_dung_day` là bản đầy đủ (nếu khác `tom_tat`). Vượt trần inline
        thì blob giữ bản đầy đủ và `tom_tat` chỉ còn phần đầu — lịch sử
        LOGIC vẫn trọn vẹn, tra được qua `blob_sha`.
        """
        if self._kho is None or self._blob is None:
            return None
        try:
            day = noi_dung_day or ""
            if len(sk.tom_tat) > TRAN_TOM_TAT and not day:
                day = sk.tom_tat
            if day and (day != sk.tom_tat or len(day) > TRAN_TOM_TAT):
                sha, _, n = self._blob.ghi(day)
                sk.blob_sha = sha
                sk.da_loc += n
                sk.meta.setdefault("blob_byte", len(day.encode("utf-8")))
            if len(sk.tom_tat) > TRAN_TOM_TAT:
                sk.tom_tat = sk.tom_tat[:TRAN_TOM_TAT - 3] + "..."
            return self._kho.ghi_su_kien(sk)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("ghi sự kiện", exc)
            return None

    def su_kien(self, **kw) -> List[SuKien]:
        if self._kho is None:
            return []
        try:
            return self._kho.su_kien(**kw)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc sự kiện", exc)
            return []

    def su_kien_theo_id(self, sid: int) -> Optional[SuKien]:
        if self._kho is None:
            return None
        try:
            return self._kho.su_kien_theo_id(sid)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc sự kiện", exc)
            return None

    def tim_su_kien(self, cau: str, *, limit: int = 50) -> List[SuKien]:
        if self._kho is None:
            return []
        try:
            return self._kho.tim_su_kien(cau, limit=limit)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("tìm sự kiện", exc)
            return []

    # -- L1 ---------------------------------------------------------------

    def luu_ky_uc(self, k: KyUc, *, ai: str = "") -> Optional[KyUc]:
        if self._kho is None:
            return None
        try:
            return self._kho.luu_ky_uc(k, ai=ai)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("lưu ký ức", exc)
            return None

    def ky_uc(self, ma: str) -> Optional[KyUc]:
        if self._kho is None:
            return None
        try:
            return self._kho.ky_uc(ma)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc ký ức", exc)
            return None

    def cham(self, ma: str) -> None:
        if self._kho is not None:
            try:
                self._kho.cham(ma)
            except Exception:                               # noqa: BLE001
                pass

    def liet_ke(self, **kw) -> List[KyUc]:
        if self._kho is None:
            return []
        try:
            return self._kho.liet_ke_ky_uc(**kw)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("liệt kê ký ức", exc)
            return []

    def tim(self, cau: str, *, loai: Optional[LoaiKyUc] = None,
            limit: int = 50) -> List[Tuple[KyUc, float]]:
        if self._kho is None:
            return []
        try:
            return self._kho.tim_ky_uc(cau, loai=loai, limit=limit)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("tìm ký ức", exc)
            return []

    # -- quyet dinh -------------------------------------------------------

    def them_quyet_dinh(self, k: KyUc, *, thay_the_cho: Sequence[str] = (),
                        ly_do: str = "", ai: str = "") -> Optional[QuyetDinh]:
        if self._kho is None:
            return None
        try:
            return self._kho.them_quyet_dinh(k, thay_the_cho=thay_the_cho,
                                             ly_do=ly_do, ai=ai)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("ghi quyết định", exc)
            return None

    def cac_quyet_dinh(self, *, chi_hieu_luc: bool = False,
                       limit: int = 200) -> List[QuyetDinh]:
        if self._kho is None:
            return []
        try:
            return self._kho.cac_quyet_dinh(chi_hieu_luc=chi_hieu_luc,
                                            limit=limit)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc quyết định", exc)
            return []

    def quyet_dinh(self, ma: str) -> Optional[QuyetDinh]:
        if self._kho is None:
            return None
        try:
            return self._kho.quyet_dinh(ma)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc quyết định", exc)
            return None

    # -- L2 / L3 ----------------------------------------------------------

    def vien_nang(self) -> Optional[VienNang]:
        if self._kho is None:
            return None
        try:
            return self._kho.vien_nang(self.project_id)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc viên nang", exc)
            return None

    def cap_nhat_vien_nang(self, vn: VienNang) -> Optional[VienNang]:
        if self._kho is None:
            return None
        try:
            vn.project_id = vn.project_id or self.project_id
            return self._kho.luu_vien_nang(vn)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("lưu viên nang", exc)
            return None

    def cac_phien_ban_vien_nang(self, limit: int = 20) -> List[Dict]:
        if self._kho is None:
            return []
        try:
            return self._kho.cac_phien_ban_vien_nang(limit)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc phiên bản viên nang", exc)
            return []

    def diem_dung(self, dd: DiemDung) -> Optional[DiemDung]:
        if self._kho is None:
            return None
        try:
            return self._kho.luu_diem_dung(dd)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("lưu điểm dừng", exc)
            return None

    def nap_diem_dung(self, ma: str = "") -> Optional[DiemDung]:
        if self._kho is None:
            return None
        try:
            return self._kho.diem_dung(ma) if ma else self._kho.diem_dung_moi_nhat()
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("nạp điểm dừng", exc)
            return None

    def cac_diem_dung(self, limit: int = 50) -> List[DiemDung]:
        if self._kho is None:
            return []
        try:
            return self._kho.cac_diem_dung(limit)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc điểm dừng", exc)
            return []

    # -- bang chung -------------------------------------------------------

    def bang_chung(self, *, su_kien_id: int = 0,
                   blob_sha: str = "") -> Dict[str, Any]:
        """Lần về nguồn: sự kiện L0 và/hoặc nội dung blob đầy đủ.

        Thiếu gì thì NÓI thiếu (`co: False`, `ly_do`), không trả rỗng
        lặng lẽ — "vì sao anh nhớ điều này?" phải trả lời được kể cả khi
        câu trả lời là "bằng chứng đã mất".
        """
        ra: Dict[str, Any] = {"su_kien": None, "blob": None, "co": False,
                              "ly_do": ""}
        if self._kho is None or self._blob is None:
            ra["ly_do"] = self.loi_cuoi or "sổ chưa mở"
            return ra
        try:
            if su_kien_id:
                sk = self._kho.su_kien_theo_id(int(su_kien_id))
                ra["su_kien"] = sk.to_dict() if sk else None
                if sk and sk.blob_sha and not blob_sha:
                    blob_sha = sk.blob_sha
                if not sk:
                    ra["ly_do"] = f"không có sự kiện #{su_kien_id}"
            if blob_sha:
                van = self._blob.doc(blob_sha)
                if van is None:
                    ra["ly_do"] = (ra["ly_do"] + "; " if ra["ly_do"] else "") + \
                        f"blob {blob_sha[:12]} không còn trên đĩa"
                else:
                    ra["blob"] = {"sha": blob_sha, "noi_dung": van,
                                  "toan_ven": self._blob.kiem_toan_ven(blob_sha)}
            ra["co"] = bool(ra["su_kien"] or ra["blob"])
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("lấy bằng chứng", exc)
            ra["ly_do"] = self.loi_cuoi
        return ra

    def doc_blob(self, sha: str) -> Optional[str]:
        if self._blob is None:
            return None
        try:
            return self._blob.doc(sha)
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đọc blob", exc)
            return None

    # -- thong ke ---------------------------------------------------------

    def dem(self) -> Dict[str, int]:
        """Chỉ số lượng — RẺ. Dùng trên đường nóng (mỗi lượt Leader).

        `thong_ke()` còn chạy `quick_check` + FTS integrity-check, là hai
        phép quét cả sổ; chạy chúng mỗi lượt chat là biến một sổ 300 MB
        thành vài giây chờ trước mỗi câu trả lời.
        """
        if self._kho is None:
            return {}
        try:
            return self._kho.dem()
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("đếm", exc)
            return {}

    def thong_ke(self) -> Dict[str, Any]:
        ok, ly = self.san_sang()
        ra: Dict[str, Any] = {"project_id": self.project_id, "ns": self.ns,
                              "thu_muc": str(self.thu_muc), "san_sang": ok,
                              "che_do_tim": ly if ok else "",
                              "loi_cuoi": self.loi_cuoi, "ts": time.time()}
        if not ok or self._kho is None or self._blob is None:
            return ra
        try:
            ra["dem"] = self._kho.dem()
            b = self._kho.byte()
            bl = self._blob.thong_ke()
            ra["byte"] = {
                "lich_su_tho": b["tho_su_kien"],
                "bang_chung": bl["byte_tren_dia"],
                "co_cau_truc": b["co_cau_truc"],
                "chi_muc": b["chi_muc_fts"],
                "tep_db": b["tep_db"], "tep_wal": b["tep_wal"],
                "tong": b["tep_db"] + b["tep_wal"] + bl["byte_tren_dia"],
            }
            ra["so_blob"] = bl["so_blob"]
            ra["toan_ven"] = self._kho.kiem_toan_ven()
        except Exception as exc:                            # noqa: BLE001
            self._that_bai("thống kê", exc)
            ra["loi_cuoi"] = self.loi_cuoi
        return ra

    def close(self) -> None:
        if self._kho is not None:
            self._kho.close()

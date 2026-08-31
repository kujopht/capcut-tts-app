"""
Mo an toan mot file ZIP tai len (nen cua EPUB/DOCX/ZIP nguoi dung tu nop) —
dung CHUNG cho moi dinh dang dua tren ZIP trong `import_pipeline/`, mot cho
chan duy nhat thay vi lap lai kiem tra o tung noi.

HAI rui ro that voi ZIP tu nguoi dung, KHONG phai ly thuyet:
1. "Zip bomb" — vai KB nen thanh vai GB khi giai nen, lam day dia/RAM.
2. "Zip slip" — mot ten muc trong zip la duong dan tuyet doi hoac chua
   `../`, ghi de file NGOAI thu muc du dinh khi giai nen ngay nguyen.

Module nay KHONG BAO GIO giai nen ra dia — chi doc noi dung tung muc vao bo
nho (`ZipFile.read(name)`), da bi gioi han kich thuoc TRUOC do — nen "zip
slip" theo nghia ghi-de-file khong ap dung, nhung ten muc van duoc kiem cho
chac (phong truong hop ma goi sau nay doi sang ghi dia)."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Dict, List


class UnsafeZipError(Exception):
    """ZIP vuot gioi han an toan hoac chua duong dan dang ngo — tu choi
    truoc khi doc bat ky noi dung nao."""


#: Gioi han CO CHU DICH GIU THAP — day la truyen chu, khong phai kho luu
#: tru file da phuong tien. Mot EPUB/DOCX/ZIP that hiem khi vuot vai chuc MB.
MAX_ENTRIES = 2000
MAX_TOTAL_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_SINGLE_ENTRY_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
#: Ty le nen/giai nen bat thuong (vd 1KB -> 1GB) la dau hieu zip bomb kinh
#: dien, du tung tieu chi kich thuoc rieng le van duoi nguong o tren.
MAX_COMPRESSION_RATIO = 100


@dataclass
class SafeZipEntry:
    name: str
    uncompressed_size: int


def _kiem_tra_ten_an_toan(name: str) -> None:
    if name.startswith("/") or name.startswith("\\"):
        raise UnsafeZipError(f"Tên mục ZIP là đường dẫn tuyệt đối: {name!r}")
    if ".." in name.replace("\\", "/").split("/"):
        raise UnsafeZipError(f"Tên mục ZIP chứa '..': {name!r}")


def inspect_zip(data: bytes) -> List[SafeZipEntry]:
    """Kiem tra TOAN BO danh sach muc TRUOC khi doc bat ky noi dung nao —
    nem `UnsafeZipError` ro rang neu vuot gioi han, khong doc gi ca trong
    truong hop do."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeZipError(f"Không đọc được như ZIP hợp lệ: {exc}") from exc

    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise UnsafeZipError(
            f"ZIP có {len(infos)} mục, vượt giới hạn {MAX_ENTRIES}.")

    tong = 0
    ra: List[SafeZipEntry] = []
    for info in infos:
        if info.is_dir():
            continue
        _kiem_tra_ten_an_toan(info.filename)
        if info.file_size > MAX_SINGLE_ENTRY_UNCOMPRESSED_BYTES:
            raise UnsafeZipError(
                f"Mục {info.filename!r} giải nén {info.file_size} byte, "
                f"vượt giới hạn {MAX_SINGLE_ENTRY_UNCOMPRESSED_BYTES}.")
        if info.compress_size > 0:
            ty_le = info.file_size / max(info.compress_size, 1)
            if ty_le > MAX_COMPRESSION_RATIO:
                raise UnsafeZipError(
                    f"Mục {info.filename!r} có tỷ lệ nén bất thường "
                    f"({ty_le:.0f}x) — nghi là zip bomb.")
        tong += info.file_size
        if tong > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise UnsafeZipError(
                f"Tổng dung lượng giải nén vượt giới hạn "
                f"{MAX_TOTAL_UNCOMPRESSED_BYTES} byte.")
        ra.append(SafeZipEntry(name=info.filename, uncompressed_size=info.file_size))
    return ra


def read_all_safe(data: bytes) -> Dict[str, bytes]:
    """`inspect_zip` roi doc TOAN BO noi dung vao bo nho — chi dung cho ZIP
    da qua `inspect_zip` (goi lai o day de khong co duong nao bo qua kiem
    tra), tra ve `{ten_muc: noi_dung_byte}`."""
    entries = inspect_zip(data)
    zf = zipfile.ZipFile(io.BytesIO(data))
    return {e.name: zf.read(e.name) for e in entries}

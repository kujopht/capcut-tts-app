"""Mã hoá tệp profile Antigravity tại chỗ bằng DPAPI — Router V4.

VẤN ĐỀ: `saved_profiles/accN.bin` là JSON **thuần** chứa OAuth token dùng
lại được. `CredRead` trả blob **đã giải mã cho người dùng hiện tại**, nên
ghi nó ra tệp là **bóc lớp bảo vệ DPAPI** mà Windows vốn đã có. ACL siết lại
là lớp phòng thủ thứ nhất; nếu ACL bị đặt sai một lần (đã xảy ra thật) thì
không còn gì nữa cả.

CÁCH GIẢI, hẹp nhất có thể: bọc blob bằng `CryptProtectData` ở **phạm vi
NGƯỜI DÙNG**. Tệp trở thành:

    b"AGYP1\\x00" + <DPAPI ciphertext>

Chỉ **chính tài khoản Windows này** giải mã được. Một tài khoản khác — kể cả
`CodexSandboxOffline/Online` — đọc được byte cũng **không** dùng được, vì
khoá nằm trong dữ liệu bảo vệ của hồ sơ người dùng, không nằm trong tệp.

TƯƠNG THÍCH NGƯỢC LÀ BẮT BUỘC, không phải tuỳ chọn:

    `doc_blob()` nhìn magic header. Có header -> giải mã. KHÔNG có ->
    trả về nguyên văn (tệp cũ dạng thuần).

Nhờ vậy: trạng thái nửa-di-trú vẫn chạy, và **hoàn tác** chỉ là đặt lại tệp
cũ về chỗ. Không có "vực thẳm" nào giữa hai định dạng.

`ENTROPY` là entropy phụ CỐ ĐỊNH của ứng dụng. Nó KHÔNG phải bí mật (nó nằm
ngay trong mã) và không tự thêm sức mạnh mật mã; nó chỉ buộc bản mã gắn với
**định dạng này**, nên một blob DPAPI của ứng dụng khác cùng người dùng
không tình cờ giải mã lọt qua đây.

KHÔNG BAO GIỜ in bản rõ. Mọi hàm ở đây trả `bytes` cho người gọi; không hàm
nào `print` nội dung.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple

#: Nhan dinh dang. Doi nhan = doi dinh dang; giu 1 byte phien ban o cuoi de
#: mot dinh dang tuong lai phan biet duoc ma khong pha bo doc cu.
MAGIC = b"AGYP1\x00"

#: Entropy phu cua ung dung — xem docstring module: KHONG phai bi mat.
ENTROPY = b"fanfic-router-v4/agy-profile"

CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _lay(b: _BLOB) -> bytes:
    ra = ctypes.string_at(b.pbData, b.cbData)
    # `LocalFree` la bat buoc: CryptProtect/Unprotect cap phat bang LocalAlloc
    # va khong giai phong thi moi lan goi ro ri dung bang kich thuoc blob.
    ctypes.windll.kernel32.LocalFree(b.pbData)
    return ra


class CryptoError(RuntimeError):
    """Mã hoá/giải mã thất bại. KHÔNG BAO GIỜ nuốt — một lần giải mã hỏng
    mà bị bỏ qua sẽ biến thành 'profile trống' rồi 'chưa đăng nhập', và
    người vận hành đi tìm sai chỗ hoàn toàn."""


def kha_dung() -> bool:
    """DPAPI có dùng được trên nền tảng này không (chỉ Windows)."""
    try:
        return hasattr(ctypes, "windll") and bool(ctypes.windll.crypt32)
    except (AttributeError, OSError):
        return False


def ma_hoa(plain: bytes) -> bytes:
    """Bọc bằng DPAPI phạm vi NGƯỜI DÙNG. Trả về `MAGIC + ciphertext`."""
    if not kha_dung():
        raise CryptoError("DPAPI không có trên nền tảng này")
    din, dent, dout = _blob(plain), _blob(ENTROPY), _BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(din), None, ctypes.byref(dent), None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(dout))
    if not ok:
        raise CryptoError(
            f"CryptProtectData thất bại (GetLastError="
            f"{ctypes.windll.kernel32.GetLastError()})")
    return MAGIC + _lay(dout)


def giai_ma(raw: bytes) -> bytes:
    """Mở một tệp `MAGIC + ciphertext`. Ném nếu không đúng định dạng."""
    if not da_ma_hoa(raw):
        raise CryptoError("không phải blob đã mã hoá (thiếu magic header)")
    if not kha_dung():
        raise CryptoError("DPAPI không có trên nền tảng này")
    din, dent, dout = _blob(raw[len(MAGIC):]), _blob(ENTROPY), _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(din), None, ctypes.byref(dent), None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(dout))
    if not ok:
        raise CryptoError(
            f"CryptUnprotectData thất bại (GetLastError="
            f"{ctypes.windll.kernel32.GetLastError()}) — blob thuộc tài khoản "
            f"Windows KHÁC, hoặc tệp đã hỏng")
    return _lay(dout)


def da_ma_hoa(raw: bytes) -> bool:
    return raw[:len(MAGIC)] == MAGIC


def doc_blob(path: Path) -> bytes:
    """Đọc một tệp profile, tự nhận định dạng.

    ĐÂY là điểm tương thích ngược: tệp cũ dạng thuần đọc được y như trước,
    tệp mới được giải mã. Một trạng thái nửa-di-trú vẫn chạy đúng.
    """
    raw = Path(path).read_bytes()
    return giai_ma(raw) if da_ma_hoa(raw) else raw


def ghi_blob(path: Path, plain: bytes) -> None:
    """Ghi profile ở dạng ĐÃ MÃ HOÁ, nguyên tử.

    Ghi ra tệp tạm rồi `os.replace`: nếu tiến trình chết giữa lúc ghi, tệp
    cũ vẫn còn nguyên. Ghi trực tiếp có thể để lại một profile bị cắt nửa —
    và một profile hỏng nghĩa là mất quyền truy cập tài khoản đó.
    """
    import os
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(ma_hoa(plain))
    os.replace(tmp, p)


def trang_thai(path: Path) -> Tuple[bool, int]:
    """`(đã mã hoá?, số byte)` — không đọc bản rõ."""
    raw = Path(path).read_bytes()
    return da_ma_hoa(raw), len(raw)

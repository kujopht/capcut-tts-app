"""KHO BÍ MẬT — nơi DUY NHẤT giá trị credential của nhà cung cấp ngoài đi qua.

BA LUẬT, mỗi luật có bài kiểm ở `scripts/tests/test_provider_credentials_v061.py`:

  1. GIÁ TRỊ KHÔNG BAO GIỜ LÀ MỘT THUỘC TÍNH. `lay(ref)` trả một `BiMat` —
     tay cầm MỜ. Muốn dùng thì gọi `bi_mat.dung(fn)`: giá trị được đọc từ
     kho, đưa cho `fn`, rồi xoá tham chiếu. `repr(bi_mat)` chỉ có `ref`.
     Không pickle, không `json.dumps`, không `str()` ra giá trị.
  2. KHÔNG RƠI VỀ TỆP THƯỚNG. Không có Windows Credential Manager (máy khác,
     CI) thì `KhoBiMatTrong` nói "không sẵn" và `luu()` NÉM. Ghi bí mật ra
     `.json`/`.env` để "cho tiện" là đúng cái lỗ mà toàn bộ V0.6.1 tồn tại
     để bịt.
  3. MỘT VÙNG TÊN RIÊNG, KHÔNG LIỆT KÊ. Mọi mục nằm dưới `RouterCC/provider/`.
     Không gọi `CredEnumerate`; không đọc mục nào ngoài vùng — mục phiên
     `agy` của Antigravity ở cùng Credential Manager và không được chạm.

`KhoBiMatBoNho` chỉ cho kiểm thử: nó tự nhận `ben=False` và không bao giờ
được `mo_kho_bi_mat()` chọn.
"""
from __future__ import annotations

import re
import secrets
import sys
from typing import Callable, Dict, Optional, Tuple

#: Vung ten cua Router Control Center trong Credential Manager.
NAMESPACE = "RouterCC/provider/"
_MA_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
_TRAN_GIA_TRI = 4096


class LoiKhoBiMat(RuntimeError):
    """Lỗi kho bí mật. Thông điệp KHÔNG BAO GIỜ chứa giá trị."""


class KhongCoBiMat(LoiKhoBiMat):
    """`ref` không có trong kho."""


class KhoBiMatKhongSan(LoiKhoBiMat):
    """Máy này không có kho an toàn — và ta KHÔNG lưu xuống tệp thường."""


def kiem_ref(ref: str) -> str:
    if not isinstance(ref, str) or not _MA_REF.match(ref):
        raise LoiKhoBiMat("credential_ref không hợp lệ (chữ/số/._:- , 3..200 ký tự)")
    return ref


def kiem_gia_tri(gia_tri) -> str:
    """Giá trị phải là chuỗi một dòng, không rỗng, ≤ 4096. Không ghi lại nó."""
    if not isinstance(gia_tri, str):
        raise LoiKhoBiMat("giá trị credential phải là chuỗi")
    v = gia_tri.strip()
    if not v:
        raise LoiKhoBiMat("giá trị credential rỗng")
    if len(v) > _TRAN_GIA_TRI:
        raise LoiKhoBiMat(f"giá trị credential dài quá {_TRAN_GIA_TRI} ký tự")
    if any(ord(ch) < 32 for ch in v):
        raise LoiKhoBiMat("giá trị credential chứa ký tự điều khiển/xuống dòng")
    return v


def sinh_ref(provider_id: str, alias: str) -> str:
    """`<provider>.<alias-slug>.<8 hex ngẫu nhiên>` — ổn định, không đoán được."""
    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:32] or "x"
    return f"{_slug(provider_id)}.{_slug(alias)}.{secrets.token_hex(4)}"


class BiMat:
    """Tay cầm MỜ tới một credential. Chỉ `dung(fn)` mới thấy giá trị."""

    __slots__ = ("_ref", "_doc")

    def __init__(self, ref: str, doc: Callable[[], str]):
        self._ref = kiem_ref(ref)
        self._doc = doc

    @property
    def ref(self) -> str:
        return self._ref

    def dung(self, fn: Callable[[str], object]):
        """Gọi `fn(giá_trị)` và trả kết quả của `fn`. Giá trị KHÔNG được giữ."""
        gia_tri = self._doc()
        try:
            return fn(gia_tri)
        finally:
            del gia_tri

    def __repr__(self) -> str:
        return f"<BiMat ref={self._ref}>"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self):
        raise TypeError("BiMat không được pickle/sao chép — dùng credential_ref")

    def __getstate__(self):
        raise TypeError("BiMat không được tuần tự hoá")


class KhoBiMat:
    """Giao diện chung. Lớp con chỉ cài `_ghi/_doc/_xoa/_co/san`."""

    kieu = "co-so"
    ben = False           # bền qua khởi động lại?

    # -- API cong -------------------------------------------------------------

    def san(self) -> Tuple[bool, str]:
        return False, "chưa cài"

    def luu(self, ref: str, gia_tri) -> None:
        kiem_ref(ref)
        v = kiem_gia_tri(gia_tri)
        try:
            self._ghi(ref, v)
        finally:
            del v

    def lay(self, ref: str) -> BiMat:
        kiem_ref(ref)
        if not self.co(ref):
            raise KhongCoBiMat(f"không có credential {ref!r} trong kho {self.kieu}")
        return BiMat(ref, lambda: self._doc(ref))

    def co(self, ref: str) -> bool:
        kiem_ref(ref)
        return self._co(ref)

    def xoa(self, ref: str) -> bool:
        kiem_ref(ref)
        return self._xoa(ref)

    def mo_ta(self) -> Dict:
        ok, ct = self.san()
        return {"kieu": self.kieu, "ben": self.ben, "san": ok, "chi_tiet": ct,
                "vung_ten": NAMESPACE}

    # -- lop con --------------------------------------------------------------

    def _ghi(self, ref: str, gia_tri: str) -> None:          # pragma: no cover
        raise NotImplementedError

    def _doc(self, ref: str) -> str:                          # pragma: no cover
        raise NotImplementedError

    def _co(self, ref: str) -> bool:                          # pragma: no cover
        raise NotImplementedError

    def _xoa(self, ref: str) -> bool:                         # pragma: no cover
        raise NotImplementedError


class KhoBiMatBoNho(KhoBiMat):
    """CHỈ CHO KIỂM THỬ: sống trong tiến trình, mất khi tắt."""

    kieu = "bo-nho"
    ben = False

    def __init__(self):
        self._d: Dict[str, str] = {}

    def san(self) -> Tuple[bool, str]:
        return True, "chỉ trong tiến trình — dùng cho kiểm thử, KHÔNG bền"

    def _ghi(self, ref, gia_tri):
        self._d[ref] = gia_tri

    def _doc(self, ref):
        try:
            return self._d[ref]
        except KeyError:
            raise KhongCoBiMat(ref) from None

    def _co(self, ref):
        return ref in self._d

    def _xoa(self, ref):
        return self._d.pop(ref, None) is not None


class KhoBiMatTrong(KhoBiMat):
    """Không có kho an toàn. Mọi `luu()` NÉM — không rơi về tệp thường."""

    kieu = "khong-san"
    ben = False

    def __init__(self, ly_do: str = ""):
        self.ly_do = ly_do or "máy này không có Windows Credential Manager"

    def san(self) -> Tuple[bool, str]:
        return False, self.ly_do

    def _ghi(self, ref, gia_tri):
        raise KhoBiMatKhongSan(
            f"không lưu được credential: {self.ly_do}. Router Control Center "
            f"KHÔNG ghi bí mật xuống tệp thường — cấu hình một kho an toàn trước.")

    def _doc(self, ref):
        raise KhongCoBiMat(ref)

    def _co(self, ref):
        return False

    def _xoa(self, ref):
        return False


class KhoBiMatWindows(KhoBiMat):
    """Windows Credential Manager qua `advapi32` (CredWriteW/CredReadW/CredDeleteW).

    Đo thật 2026-09-10 trên máy người vận hành: ghi/đọc/xoá vòng tròn ĐẠT.
    Mục kiểu GENERIC, `Persist=LOCAL_MACHINE` (bền cho tài khoản Windows
    này), `UserName="router-cc"`. Không `CredEnumerate` — không bao giờ nhìn
    thấy mục nào ngoài `NAMESPACE`.
    """

    kieu = "windows-credential-manager"
    ben = True
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("chỉ có trên Windows")
        import ctypes
        from ctypes import wintypes
        self._ct = ctypes
        adv = ctypes.WinDLL("advapi32", use_last_error=True)

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self._CRED = CREDENTIAL
        self._PCRED = ctypes.POINTER(CREDENTIAL)
        adv.CredWriteW.argtypes = [self._PCRED, wintypes.DWORD]
        adv.CredWriteW.restype = wintypes.BOOL
        adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(self._PCRED)]
        adv.CredReadW.restype = wintypes.BOOL
        adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        adv.CredDeleteW.restype = wintypes.BOOL
        adv.CredFree.argtypes = [ctypes.c_void_p]
        self._adv = adv

    @staticmethod
    def _dich(ref: str) -> str:
        return NAMESPACE + ref

    def san(self) -> Tuple[bool, str]:
        # Doc mot muc CHAC CHAN khong ton tai trong vung ten: ky vong
        # ERROR_NOT_FOUND. Loi khac = API khong dung duoc.
        p = self._PCRED()
        ok = self._adv.CredReadW(self._dich("_probe.khong-ton-tai"), self._CRED_TYPE_GENERIC,
                                 0, self._ct.byref(p))
        if ok:
            self._adv.CredFree(p)
            return True, "advapi32 sẵn"
        err = self._ct.get_last_error()
        if err == self._ERROR_NOT_FOUND:
            return True, "advapi32 CredRead/CredWrite sẵn"
        return False, f"CredReadW lỗi {err}"

    def _ghi(self, ref, gia_tri):
        raw = gia_tri.encode("utf-16-le")
        blob = (self._ct.c_byte * len(raw)).from_buffer_copy(raw)
        c = self._CRED(Flags=0, Type=self._CRED_TYPE_GENERIC, TargetName=self._dich(ref),
                       Comment="Router Control Center — credential nhà cung cấp ngoài",
                       CredentialBlobSize=len(raw), CredentialBlob=blob,
                       Persist=self._CRED_PERSIST_LOCAL_MACHINE, AttributeCount=0,
                       Attributes=None, TargetAlias=None, UserName="router-cc")
        ok = self._adv.CredWriteW(self._ct.byref(c), 0)
        if not ok:
            raise LoiKhoBiMat(f"CredWriteW lỗi {self._ct.get_last_error()}")

    def _doc(self, ref):
        p = self._PCRED()
        ok = self._adv.CredReadW(self._dich(ref), self._CRED_TYPE_GENERIC, 0, self._ct.byref(p))
        if not ok:
            err = self._ct.get_last_error()
            if err == self._ERROR_NOT_FOUND:
                raise KhongCoBiMat(ref)
            raise LoiKhoBiMat(f"CredReadW lỗi {err}")
        try:
            n = p.contents.CredentialBlobSize
            return self._ct.string_at(p.contents.CredentialBlob, n).decode("utf-16-le")
        finally:
            self._adv.CredFree(p)

    def _co(self, ref):
        p = self._PCRED()
        ok = self._adv.CredReadW(self._dich(ref), self._CRED_TYPE_GENERIC, 0, self._ct.byref(p))
        if ok:
            self._adv.CredFree(p)
            return True
        return False

    def _xoa(self, ref):
        ok = self._adv.CredDeleteW(self._dich(ref), self._CRED_TYPE_GENERIC, 0)
        return bool(ok)


def mo_kho_bi_mat() -> KhoBiMat:
    """Kho an toàn của máy này, hoặc `KhoBiMatTrong` (không sẵn — KHÔNG rơi
    về tệp). Không bao giờ trả `KhoBiMatBoNho`."""
    if sys.platform == "win32":
        try:
            k = KhoBiMatWindows()
            ok, ct = k.san()
            if ok:
                return k
            return KhoBiMatTrong(f"Windows Credential Manager không dùng được: {ct}")
        except (OSError, AttributeError) as exc:
            return KhoBiMatTrong(f"không nạp được advapi32: {type(exc).__name__}")
    return KhoBiMatTrong(f"chưa có kho bí mật an toàn cho {sys.platform} — "
                         f"chỉ Windows Credential Manager được hỗ trợ ở V0.6.1")

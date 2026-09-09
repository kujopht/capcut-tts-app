"""Tìm một THÔNG DỊCH PYTHON THẬT — dùng được cả khi Router đã đóng gói.

VÌ SAO TỆP NÀY TỒN TẠI — một sự cố thật, và nó đáng kể lại đủ:

Người dùng gõ một việc vào `Router Control Center.exe`. Việc **HỎNG sau 3
lượt**, mỗi lượt trên một runtime khác (AG01 → AG02 → AG03), mỗi lượt chỉ
~2 giây. Sổ ghi:

    failure_reason: "no_session"
    summary       : "chưa start_session"

Lý do thật KHÔNG phải thế. Chuỗi thật là:

    switch(acc) chay:  [sys.executable, "agy_profile.py", "switch", "acc1"]
                    -> `start_session()` tra False
                    -> `send_task()` thay `_worker is None`
                    -> bao "no_session"

`sys.executable` là **"thông dịch đang chạy"**. Chạy từ mã nguồn thì đó là
`python.exe` và mọi thứ đúng. Nhưng trong bản PyInstaller đã đóng gói, nó
là **chính `Router Control Center.exe`**. Nên lệnh trên trở thành:

    "Router Control Center.exe" "agy_profile.py" switch acc1

Và ứng dụng desktop tự phân tích dòng lệnh đó rồi thoát mã 2:

    Router Control Center: error: unrecognized arguments: agy_profile.py …

Đo được, không suy đoán. Đó là toàn bộ sự cố: một tiến trình con lẽ ra nạp
credential thì thành một lần tự gọi lại chính mình.

BÀI HỌC RỘNG HƠN, và vì sao đây là module riêng chứ không phải một dòng
sửa tại chỗ: **`sys.executable` chỉ là Python khi chưa đóng gói.** Mọi chỗ
sinh một tiến trình con Python trên đường Router chạy đều dính cùng lỗi
này, và nó chỉ lộ ra ở bản EXE — chạy từ mã nguồn thì vĩnh viễn xanh.

PyInstaller `onedir` nhúng Python dưới dạng **DLL**, không phải một
`python.exe`. Nên trong gói **không có** thông dịch nào để gọi; phải tìm
một cái của hệ thống.

Thứ tự tìm, và lý do:

    1. chưa đóng gói        -> `sys.executable` (nó CHÍNH LÀ python)
    2. `ROUTER_PYTHON`      -> lối thoát tường minh cho người vận hành
    3. `python` trên PATH   -> cái người dùng vẫn gõ
    4. `py.exe`             -> bộ khởi chạy chuẩn của Windows
    5. thư mục cạnh EXE     -> trường hợp cài kèm

MỖI ứng viên đều được THỬ CHẠY (`--version`) trước khi tin. Lý do rất thực
tế trên Windows: `WindowsApps\\python.exe` là một **stub của Microsoft
Store** — nó nằm trên PATH, `which` thấy nó, nhưng chạy thì nó mở Store
chứ không thực thi gì. Tin `which` mà không thử là đổi một chế độ hỏng khó
hiểu này lấy một chế độ hỏng khó hiểu khác.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

#: Nhớ kết quả: phép dò có sinh tiến trình con, và nó không đổi giữa chừng.
_NHO: Optional[Tuple[List[str], str]] = None


def dang_dong_goi() -> bool:
    """Đang chạy trong bản đã đóng gói (PyInstaller) hay không."""
    return bool(getattr(sys, "frozen", False))


def _chay_duoc(argv: List[str]) -> bool:
    """Ứng viên có THẬT SỰ là một thông dịch Python 3 chạy được không.

    Dùng `--version` chứ không `-c`: rẻ hơn, và không cần bàn tới trích
    dẫn dòng lệnh. Stub của Microsoft Store trượt phép thử này.
    """
    try:
        p = subprocess.run(argv + ["--version"], capture_output=True,
                           timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    if p.returncode != 0:
        return False
    ra = ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "replace")
    return ra.strip().startswith("Python 3")


def _ung_vien() -> List[Tuple[List[str], str]]:
    """`[(argv, vì sao)]` theo thứ tự ưu tiên."""
    ds: List[Tuple[List[str], str]] = []

    bien = (os.environ.get("ROUTER_PYTHON") or "").strip()
    if bien:
        ds.append(([bien], "ROUTER_PYTHON"))

    for ten in ("python", "python3"):
        p = shutil.which(ten)
        if p:
            ds.append(([p], f"{ten} trên PATH"))

    py = shutil.which("py")
    if py:
        # `-3` tuong minh: khong de bo khoi chay chon Python 2 tren mot may
        # con cai ca hai.
        ds.append(([py, "-3"], "bộ khởi chạy py.exe"))

    if dang_dong_goi():
        canh = Path(sys.executable).resolve().parent
        for ten in ("python.exe", "python3.exe"):
            p = canh / ten
            if p.is_file():
                ds.append(([str(p)], "cạnh EXE"))
    return ds


def argv_python(*, lam_moi: bool = False) -> Tuple[List[str], str]:
    """`(argv mở đầu, lý do)` để chạy một kịch bản Python.

    Trả `([], lý do hỏng)` khi KHÔNG tìm được — và đó là một câu người đọc
    được, không phải một `False` trần. Chính chỗ nuốt lý do đã làm sự cố
    trên mất một buổi để tìm.

        argv, _ = argv_python()
        if not argv:
            ...  # bao loi CO LY DO
        subprocess.run(argv + [str(kich_ban), "switch", acc])
    """
    global _NHO
    if _NHO is not None and not lam_moi:
        return _NHO

    if not dang_dong_goi():
        # Chua dong goi: tien trinh nay CHINH LA mot python.
        _NHO = ([sys.executable], "sys.executable (chưa đóng gói)")
        return _NHO

    da_thu = []
    for argv, vi_sao in _ung_vien():
        if _chay_duoc(argv):
            _NHO = (argv, vi_sao)
            return _NHO
        da_thu.append(f"{argv[0]} ({vi_sao})")

    _NHO = ([], (
        "KHÔNG tìm thấy thông dịch Python nào chạy được. Bản đóng gói không "
        "kèm `python.exe` (PyInstaller nhúng Python dưới dạng DLL), nên "
        "Router cần một Python của hệ thống để chạy launcher tài khoản. "
        "Cài Python 3 rồi thêm vào PATH, hoặc đặt biến môi trường "
        "ROUTER_PYTHON trỏ vào `python.exe`."
        + (f" Đã thử: {', '.join(da_thu)}." if da_thu
           else " Không có ứng viên nào trên máy.")))
    return _NHO


def quen() -> None:
    """Quên kết quả đã nhớ — chỉ dùng trong bài kiểm."""
    global _NHO
    _NHO = None

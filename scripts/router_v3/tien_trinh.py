"""Sinh tiến trình con KHÔNG mở cửa sổ console. Một chỗ duy nhất.

VÌ SAO TỆP NÀY TỒN TẠI — một sự cố UX thật, và nó lộ ra đúng ở bản đóng
gói:

Người dùng báo: *"mỗi lần xử lý lại bật/tắt terminal window trên Windows,
rất khó chịu"*. Không phải một cửa sổ — hàng loạt cửa sổ nhấp nháy, và
chúng **giành focus**, nên đang gõ giữa câu thì con trỏ nhảy đi.

CƠ CHẾ. `Router Control Center.exe` được build `--noconsole`, tức tiến
trình không có console nào. Trên Windows, khi một tiến trình KHÔNG có
console sinh ra một ứng dụng **console** (`git.exe`, `agy.exe`,
`codex.exe`, `python.exe`, `icacls.exe`), hệ điều hành **cấp cho nó một
console mới** — và console mới thì có cửa sổ. Chạy từ mã nguồn thì cửa sổ
đó trùng với console sẵn có nên không ai thấy gì; chỉ bản `--noconsole`
mới nhấp nháy. Lại đúng một lớp lỗi "chỉ lộ ra ở EXE".

Số lần nhấp nháy tỉ lệ với số lệnh: `AnhChupDuAn` chạy khoảng sáu lệnh
`git` cho MỖI tin nhắn chat, nên một câu "ê bro" cũng đủ thấy.

CÁCH SỬA. `CREATE_NO_WINDOW` (0x08000000) khi sinh tiến trình. Nó nói với
Windows: cấp console cho tiến trình con, nhưng ĐỪNG tạo cửa sổ. Tiến trình
con vẫn có stdin/stdout/stderr bình thường, nên đường bắt log không đổi
một chút nào — và đó là điều kiện để bản sửa này không đánh đổi khả năng
chẩn đoán lấy sự yên tĩnh.

`STARTUPINFO(SW_HIDE)` cũng được thêm: hai cơ chế chồng nhau, và cái thứ
hai che những trình bao trung gian (`.cmd`, `.bat`) mà `CREATE_NO_WINDOW`
đôi khi không với tới.

KHÔNG áp cho tiến trình NGƯỜI DÙNG CỐ Ý MỞ. Khi ai đó bấm "mở terminal để
gỡ lỗi" thì cửa sổ là thứ họ muốn — dùng `AN_HIEN` cho đường đó.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict

#: `CREATE_NO_WINDOW`. Tự khai số thay vì tin thuộc tính có sẵn: nó chỉ
#: tồn tại trên Windows, và trên nền khác thì cả khối này là no-op.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
_SW_HIDE = 0


def _startupinfo():
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()               # type: ignore[attr-defined]
    si.dwFlags |= _STARTF_USESHOWWINDOW
    si.wShowWindow = _SW_HIDE
    return si


def an_cua_so() -> Dict[str, Any]:
    """Kwargs cho `subprocess.run`/`Popen` để KHÔNG có cửa sổ nào hiện ra.

        subprocess.run(argv, capture_output=True, **an_cua_so())

    Trên nền không phải Windows trả `{}` — không có khái niệm cửa sổ
    console, và thêm cờ lạ vào sẽ ném.
    """
    if sys.platform != "win32":
        return {}
    return {"creationflags": _CREATE_NO_WINDOW,
            "startupinfo": _startupinfo()}


#: Dùng khi NGƯỜI DÙNG CỐ Ý muốn thấy cửa sổ (nút "mở terminal gỡ lỗi").
#: Tồn tại để chỗ đó đọc ra rõ là một ngoại lệ CÓ Ý, không phải một chỗ bị
#: bỏ sót — và để bài kiểm chống-nhấp-nháy biết đường nào được miễn.
AN_HIEN: Dict[str, Any] = {}

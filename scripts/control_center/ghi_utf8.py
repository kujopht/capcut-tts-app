"""Ghi chẩn đoán bằng UTF-8 TƯỜNG MINH — không bao giờ qua codec của locale.

VÌ SAO TỆP NÀY TỒN TẠI — một sự cố thật, và nó đáng kể lại đủ:

`Router Control Center.exe` **chết ngay khi mở** trên máy Windows locale
Việt/Anh mặc định:

    Failed to execute script 'desktop' due to unhandled exception:
    UnicodeEncodeError: 'charmap' codec can't encode character '\\u01b0'

`U+01B0` là chữ **ư**. Dòng gây lỗi là một `print()` in ra câu
`"chưa có backend nào — tự chạy"`. Câu đó có bốn ký tự ngoài cp1252:
`ư` (U+01B0), `—` (U+2014), `ự` (U+1EF1), `ạ` (U+1EA1).

GỐC RỄ, nói cho đúng: `print()` giao chuỗi cho **tầng văn bản** của luồng,
và tầng đó dùng codec do **locale của Windows** quyết định — cp1252 ở đây.
cp1252 không có `ư`, nên nó nâng ngoại lệ. Không phải lỗi của Vietnamese,
không phải lỗi của console: lỗi là **để locale quyết định codec** cho dữ
liệu mà ta biết chắc là Unicode.

CÁCH SỬA Ở ĐÂY, và vì sao nó là gốc rễ chứ không phải băng dán:

Tự **mã hoá sang UTF-8 rồi ghi BYTE** vào tầng nhị phân của luồng. UTF-8
biểu diễn được mọi điểm mã Unicode, nên phép mã hoá này **không thể thất
bại** — không cần `errors=` gì cả, và không mất một byte tiếng Việt nào.

Những cách KHÔNG dùng, và vì sao:

    chcp 65001              đổi console của người dùng, không sửa mã
    đổi locale Windows       bắt người dùng đổi hệ thống vì lỗi của ta
    đòi PYTHONUTF8=1         một biến môi trường bị quên là lỗi quay lại;
                             và bấm đôi trong Explorer thì không có ai đặt
    bọc bằng .cmd            EXE phải tự đúng, launcher chỉ là tiện nghi
    errors="replace"/"ignore" biến `ư` thành `?` hoặc mất hẳn — đó là làm
                             hỏng dữ liệu để giấu lỗi
    bỏ dấu / phiên âm        văn bản tiếng Việt phải nguyên vẹn

Và một chi tiết thực tế của PyInstaller `--noconsole`: `sys.stdout` có thể
là `None`, hoặc là một đối tượng KHÔNG có `.buffer`. Nên tầng nhị phân
được lấy **một lần lúc dựng** và có thể vắng mặt — khi vắng, ta chỉ ghi ra
tệp nhật ký. Không có nhánh nào ở đây phụ thuộc vào locale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def duong_nhat_ky(goc: Path) -> Path:
    """Tệp nhật ký của vỏ desktop, cạnh sổ SQLite."""
    return Path(goc) / ".router" / "control_center" / "desktop.log"


def _tang_nhi_phan(luong) -> Optional[object]:
    """Tầng nhị phân của một luồng văn bản, hoặc `None`.

    `sys.stdout` trong một bản build `--noconsole` có thể là `None`, hoặc
    một đối tượng giả không có `.buffer`. Cả hai đều bình thường và không
    phải lỗi — chỉ nghĩa là không có chỗ nào để in ra.
    """
    if luong is None:
        return None
    b = getattr(luong, "buffer", None)
    if b is None or not hasattr(b, "write"):
        return None
    return b


class GhiUTF8:
    """Ghi từng dòng ra nhật ký UTF-8 và (nếu có) ra luồng, bằng BYTE.

    Gọi được như một hàm: `ghi("…")`. Không bao giờ nâng ngoại lệ ra ngoài
    — một dòng chẩn đoán không được phép hạ cả ứng dụng, và đó chính là
    điều đã xảy ra.
    """

    def __init__(self, tep: Optional[Path] = None, *, ra_luong: bool = True):
        self.tep = Path(tep) if tep else None
        self._nhi: List[object] = []
        if ra_luong:
            for luong in (sys.stdout, sys.stderr):
                b = _tang_nhi_phan(luong)
                if b is not None:
                    self._nhi.append(b)
                    break               # mot noi la du
        if self.tep is not None:
            try:
                self.tep.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.tep = None

    def dat_tep(self, tep) -> None:
        """Gắn tệp nhật ký MUỘN — sau khi thư mục gốc đã biết.

        Vỏ desktop chỉ biết thư mục gốc sau khi đã phân tích dòng lệnh,
        nhưng nó cần ghi được chẩn đoán TRƯỚC đó. Nên đối tượng ghi ra
        đời không tệp rồi nhận tệp ở đây — thay vì bên gọi phải
        `global` rồi gán lại, một hình dạng dễ quên và dễ sai.
        """
        moi = Path(tep) if tep else None
        if moi is not None:
            try:
                moi.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                moi = None
        self.tep = moi

    def __call__(self, dong: str) -> None:
        van = str(dong)
        # UTF-8 bieu dien duoc MOI diem ma Unicode, nen phep ma hoa nay
        # khong the that bai. Do la ly do KHONG can `errors=` gi ca.
        byte = (van + "\n").encode("utf-8")

        for b in self._nhi:
            try:
                b.write(byte)
                b.flush()
            except (OSError, ValueError):
                # Luong da dong (vd. tien trinh cha bien mat). Khong sao —
                # tep nhat ky ben duoi van con.
                pass

        if self.tep is not None:
            try:
                # Text mode voi `encoding` TUONG MINH, dung nhu yeu cau —
                # khong bao gio de mac dinh cua locale quyet dinh.
                with open(self.tep, "a", encoding="utf-8", newline="\n") as f:
                    f.write(van + "\n")
            except OSError:
                pass


class BoDocUTF8(argparse.ArgumentParser):
    """`ArgumentParser` in usage/help/lỗi bằng UTF-8, không qua locale.

    VÌ SAO CẦN — đây là chỗ THỨ HAI của đúng một sự cố. Sau khi sửa
    `print()` ở `desktop.py`, bản EXE đã đóng gói **vẫn** chết ở:

        Router Control Center.exe --help
        ...
        File "argparse.py", line 2627, in _print_message
        File "encodings/cp1252.py", line 19, in encode
        UnicodeEncodeError: 'charmap' codec can't encode character '\\u1ee9'

    `U+1EE9` là chữ **ứ**, tới từ `description="… ứng dụng desktop"`. Mọi
    chuỗi `help=` trong các điểm vào này là tiếng Việt, và `argparse` ghi
    chúng thẳng ra tầng **văn bản** của luồng — cùng một lỗi gốc, chỉ khác
    chỗ phát sinh. Nhánh `error()` thì tình cờ không vỡ vì câu của nó
    toàn ASCII; đó là may, không phải đúng.

    Lớp này giữ NGUYÊN việc help ra `stdout` và lỗi ra `stderr` — nó chỉ
    đổi *cách mã hoá*, không đổi luồng đích.
    """

    def __init__(self, *a, ghi: Optional["GhiUTF8"] = None, **kw):
        # Đặt trước `super().__init__`: `argparse` có thể in ngay trong đó.
        self._ghi = ghi or GhiUTF8()
        super().__init__(*a, **kw)

    def _print_message(self, message, file=None) -> None:   # noqa: N802
        if not message:
            return
        b = _tang_nhi_phan(file)
        if b is not None:
            try:
                b.write(message.encode("utf-8"))   # khong the that bai
                b.flush()
                return
            except (OSError, ValueError):
                pass
        # Không có tầng nhị phân (bản `--noconsole`): rơi về nhật ký tệp.
        self._ghi(message.rstrip("\n"))


def hop_thoai_loi(tieu_de: str, thong_diep: str) -> None:
    """Hộp thoại lỗi của Windows. `MessageBoxW` là API **wide** (UTF-16).

    Nên đường này mang được tiếng Việt nguyên vẹn, và nó là đường DUY NHẤT
    người dùng thấy được khi EXE chạy ở chế độ `--noconsole`: lúc đó không
    có console nào để đọc `stderr`.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # 0x10 = MB_ICONERROR. Ham `...W` nhan `wchar_t*`, nen ctypes tu
        # chuyen `str` sang UTF-16 — khong qua cp1252 o bat ky buoc nao.
        ctypes.windll.user32.MessageBoxW(None, str(thong_diep),
                                         str(tieu_de), 0x10)
    except Exception:                                       # noqa: BLE001
        pass

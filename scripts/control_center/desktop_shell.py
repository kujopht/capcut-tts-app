"""Vỏ desktop quanh giao diện web — MỎNG, và cố ý mỏng.

Tệp này KHÔNG chứa một dòng logic điều phối nào. Nó làm đúng sáu việc, và
mọi thứ khác vẫn nằm ở `engine.py`/Router V4:

    1. cưỡng chế MỘT thực thể (single instance)
    2. khởi động backend, HOẶC nối lại backend đang chạy
    3. cấp/dùng cổng trên 127.0.0.1
    4. chờ backend khoẻ
    5. mở cửa sổ WebView2
    6. đóng app thì tắt backend — TRỪ KHI tiến trình khác sở hữu nó

VÌ SAO TÁCH KHỎI `desktop.py`: phần trên đây thuần Python, không cần
WebView2, nên nó kiểm được trong `scripts/tests` và **CI cưỡng chế**. Việc
mở cửa sổ nằm ở `desktop.py`, nơi bắt buộc phải có GUI thật.

QUYỀN SỞ HỮU BACKEND — đây là phần dễ sai nhất, nên nói rõ:

Nếu người dùng đã chạy `router-cc-web.cmd` (đường gỡ lỗi) rồi bấm đôi
EXE, thì có MỘT backend và HAI người muốn nó. Vỏ desktop phải nối vào cái
đang chạy, và khi đóng cửa sổ thì **không được tắt** nó — vì nó không phải
của mình. Ngược lại nếu vỏ tự khởi động backend thì đóng cửa sổ phải tắt
sạch, không để lại một tiến trình mồ côi giữ cổng.

Ai sở hữu được ghi trong `.router/control_center/desktop.lock`. Tệp đó giữ
`pid`, `cong`, `token` — nên nó là **bí mật ở trạng thái nghỉ**, cùng cấp
với `control.db` bên cạnh nó. Không đưa token vào biến môi trường (nó lộ
ra `wmic`/Task Manager cho mọi tiến trình cùng phiên) và không đưa vào
dòng lệnh (lộ y như vậy).
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

DIA_CHI = "127.0.0.1"

#: Ten mutex toan he thong. Cuong che MOT thuc the o cap he dieu hanh, chu
#: khong chi bang tep khoa: mot tep khoa mo coi (may mat dien giua chung)
#: se chan lan mo sau, con mutex thi he dieu hanh tu nha khi tien trinh
#: chet. Dung ca hai: mutex de chan, tep khoa de BIET NOI MA NOI LAI.
TEN_MUTEX = "Global\\RouterControlCenter.Desktop.SingleInstance"


def ten_mutex_cua(goc) -> str:
    """Tên mutex cho MỘT thư mục gốc.

    "Một thực thể" phải hiểu theo NƠI LÀM VIỆC, không phải theo cả máy.
    Thứ cần chặn là hai tiến trình cùng giành MỘT sổ SQLite và MỘT tệp
    khoá; hai Control Center trỏ vào hai thư mục gốc khác nhau không tranh
    nhau thứ gì cả.

    Với người dùng thật thì KHÔNG có gì đổi: bấm đôi cùng một EXE luôn ra
    cùng một thư mục gốc (`_goc_mac_dinh()` = thư mục cạnh EXE), nên lần
    bấm thứ hai vẫn nhường đúng như trước.

    Đổi cái này vì một lý do cụ thể: một mutex TOÀN MÁY làm không thể mở
    một bản thứ hai trên một thư mục tạm để KIỂM trong khi bản của người
    dùng đang mở — tức là không chứng minh được điều phối trên chính bản
    đã đóng gói, mà không phải tắt ứng dụng của người khác.
    """
    return f"{TEN_MUTEX}.{_ma_goc(goc)}"


def _ma_goc(goc) -> str:
    import hashlib
    duong = str(Path(goc).resolve()).lower()
    return hashlib.sha256(duong.encode("utf-8")).hexdigest()[:16]


def duong_webview2(goc) -> Path:
    """Thư mục hồ sơ WebView2 cho MỘT thư mục gốc.

    VÌ SAO CẦN — một sự cố thật, đo được, trên bản đã đóng gói:

        pywebview WebView2 initialization failed with exception:
        (0x8007139F): The group or resource is not in the correct state
        to perform the requested operation.

    `pywebview` mặc định đặt hồ sơ WebView2 ở `%APPDATA%\\pywebview\\
    EBWebView` — **một thư mục DÙNG CHUNG cho mọi ứng dụng pywebview trên
    máy**. WebView2 cho nhiều tiến trình dùng chung một hồ sơ, nhưng CHỈ
    KHI `AdditionalBrowserArguments` giống nhau; khác một cờ là nó từ chối
    với đúng HRESULT ở trên. Nghĩa là:

    * mở bản thứ hai của app này với `--debug-cdp` trong khi bản của
      người dùng đang chạy -> KHÔNG mở được cửa sổ nào;
    * một ứng dụng pywebview KHÁC của bên thứ ba cũng đủ làm app này chết
      lúc mở, với một thông điệp không ai suy ra được nguyên nhân.

    Đây là ĐÚNG bất biến mà `ten_mutex_cua` đã chọn cho mutex: "một thực
    thể" tính theo **thư mục gốc**, không theo cả máy, để một bản KIỂM
    chạy được cạnh bản của người dùng mà không phải tắt ứng dụng của
    người khác. Hồ sơ WebView2 toàn máy phá lại đúng bảo đảm đó, nên nó
    được băm theo cùng một khoá.

    Không đặt dưới chính `goc`: WebView2 tạo cây thư mục sâu bên trong
    (`EBWebView/Default/...`), và một `goc` đã dài — ví dụ một thư mục
    tạm của bộ kiểm — sẽ đẩy tổng đường dẫn qua `MAX_PATH`. Đặt dưới
    `%LOCALAPPDATA%` cho đường ngắn và cố định, cùng quy ước với
    `router_v3/worker_identity.py`.

    KHÔNG cần di trú: app không giữ gì đáng kể trong hồ sơ WebView2 —
    token phiên nằm ở `sessionStorage` (mất khi đóng tab), mọi trạng thái
    thật nằm trong sổ SQLite. Đổi thư mục chỉ làm mất cache của trình
    duyệt nhúng.
    """
    base = Path(os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or str(Path.home()))
    return (base / "FanficAudioStudio" / "router" / "webview2"
            / _ma_goc(goc))

#: Cho backend khoe. 20s la du rong: khoi dong gom mo SQLite va doi soat
#: phuc hoi, va may cham thi cham hon may nay.
CHO_KHOE = 20.0


@dataclass
class ThongTinPhien:
    """Nội dung tệp khoá: ai đang chạy backend, ở cổng nào, token gì."""

    pid: int
    cong: int
    token: str
    bat_dau_luc: float = 0.0

    def to_dict(self) -> dict:
        return {"pid": self.pid, "cong": self.cong, "token": self.token,
                "bat_dau_luc": self.bat_dau_luc}

    @classmethod
    def from_dict(cls, d: dict) -> "ThongTinPhien":
        return cls(pid=int(d.get("pid") or 0),
                   cong=int(d.get("cong") or 0),
                   token=str(d.get("token") or ""),
                   bat_dau_luc=float(d.get("bat_dau_luc") or 0.0))


def duong_tep_khoa(goc: Path) -> Path:
    return Path(goc) / ".router" / "control_center" / "desktop.lock"


def cong_rong() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((DIA_CHI, 0))
        return int(s.getsockname()[1])


def ghi_tep_khoa(goc: Path, tt: ThongTinPhien) -> Path:
    """Ghi tệp khoá, và SIẾT QUYỀN nếu hệ điều hành cho.

    Tệp này giữ token, nên nó là bí mật ở trạng thái nghỉ. `0o600` không có
    ý nghĩa đầy đủ trên NTFS (ACL mới là thứ thật), nhưng đặt nó không tốn
    gì và đúng trên mọi nền khác.
    """
    p = duong_tep_khoa(goc)
    p.parent.mkdir(parents=True, exist_ok=True)
    tam = p.with_suffix(".lock.tmp")
    # `ensure_ascii=False` + `encoding="utf-8"` TUONG MINH: tep nay la
    # mot tep van ban Router so huu, va no phai doc duoc bang mat khi
    # go loi. Hom nay noi dung toan ASCII, nhung mot mac dinh dung
    # duoc dat bay gio thi khong ai phai nho lai no ve sau.
    tam.write_text(json.dumps(tt.to_dict(), ensure_ascii=False),
                   encoding="utf-8")
    try:
        os.chmod(tam, 0o600)
    except OSError:
        pass
    os.replace(tam, p)                  # doi ten NGUYEN TU
    return p


def doc_tep_khoa(goc: Path) -> Optional[ThongTinPhien]:
    p = duong_tep_khoa(goc)
    if not p.is_file():
        return None
    try:
        return ThongTinPhien.from_dict(
            json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        # Tep khoa hong (ghi do dang, may mat dien) — coi nhu khong co.
        # FAIL OPEN o day la dung: fail closed se chan nguoi dung mo app
        # vi mot tep rac, va tep nay khong phai mot rao an toan.
        return None


def xoa_tep_khoa(goc: Path) -> None:
    try:
        duong_tep_khoa(goc).unlink(missing_ok=True)
    except OSError:
        pass


def tien_trinh_con_song(pid: int) -> bool:
    """`pid` còn sống hay không. Không dùng `os.kill(pid, 0)` trên Windows.

    Trên Windows `os.kill` với signal 0 vẫn KẾT THÚC tiến trình (nó gọi
    `TerminateProcess`), nên dùng nó để "kiểm tra" là giết mất đúng cái
    backend mình đang định nối vào.
    """
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        # `OverflowError` (một `ArithmeticError`, KHÔNG phải `OSError`) khi
        # `pid` vượt `pid_t` 32-bit có dấu của POSIX — vd một PID Windows đọc
        # lại trên Linux. Cùng lỗi với `sessions.tien_trinh_con_song`; ở đây
        # nó sẽ làm hỏng lần nối vào backend thay vì chỉ báo "chưa chạy".
        except (OSError, ProcessLookupError, OverflowError, ValueError):
            return False
    import ctypes
    from ctypes import wintypes
    SYNCHRONIZE = 0x00100000
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(SYNCHRONIZE, False, wintypes.DWORD(pid))
    if not h:
        return False
    try:
        # 0x102 = WAIT_TIMEOUT => con song. 0 = WAIT_OBJECT_0 => da thoat.
        return k32.WaitForSingleObject(h, 0) == 0x00000102
    finally:
        k32.CloseHandle(h)


def backend_khoe(cong: int, token: str, *, timeout: float = 2.0) -> bool:
    """Backend ở cổng đó có phải CỦA TA và còn trả lời không?

    Cố ý gọi `/api/state` KÈM TOKEN thay vì thêm một endpoint `/health`
    không cần token. Lý do: bất biến "mọi `/api/` đòi token" đang được một
    bài kiểm khoá lại, và mở một lỗ miễn token — dù chỉ trả về một hằng số
    — là làm yếu đúng cái ranh giới đó. Ta đã có token (đọc từ tệp khoá),
    nên không cần lỗ nào.

    Đồng thời đây là phép kiểm DANH TÍNH: một tiến trình lạ tình cờ chiếm
    cổng đó sẽ không trả 200 cho token của ta.
    """
    if cong <= 0 or not token:
        return False
    r = urllib.request.Request(f"http://{DIA_CHI}:{cong}/api/state")
    r.add_header("X-CC-Token", token)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def cho_backend_khoe(cong: int, token: str, *,
                     han: float = CHO_KHOE) -> bool:
    het = time.time() + han
    while time.time() < het:
        if backend_khoe(cong, token, timeout=1.0):
            return True
        time.sleep(0.15)
    return False


class MotThucThe:
    """Mutex toàn hệ thống. `da_co` = có thực thể khác đang chạy.

    Dùng mutex CHỨ KHÔNG chỉ dùng tệp khoá: một tệp khoá mồ côi (mất điện,
    kill -9) sẽ chặn vĩnh viễn lần mở sau, còn mutex thì hệ điều hành tự
    nhả khi tiến trình chết. Tệp khoá vẫn cần — nhưng để biết *nối vào
    đâu*, không phải để chặn.
    """

    def __init__(self, ten: str = TEN_MUTEX):
        self.ten = ten
        self.da_co = False
        self._h = None
        if sys.platform != "win32":
            return
        import ctypes
        k32 = ctypes.windll.kernel32
        self._h = k32.CreateMutexW(None, False, ten)
        # 183 = ERROR_ALREADY_EXISTS
        self.da_co = (ctypes.get_last_error() == 183
                      or k32.GetLastError() == 183)

    def nha(self) -> None:
        if self._h and sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._h)
            self._h = None


@dataclass
class KeHoachKhoiDong:
    """Quyết định của bước khởi động, tách khỏi việc THỰC HIỆN nó.

    Tách ra để kiểm được: `quyet_dinh()` là hàm thuần trên trạng thái đĩa,
    nên bài kiểm dựng đúng mọi tình huống (không có tệp khoá, tệp khoá mồ
    côi, backend đang sống, cổng bị người khác chiếm) mà không phải khởi
    động một server thật nào.
    """

    #: `noi_lai` = da co backend song, dung lai. `tu_chay` = phai tu khoi
    #: dong. `nhuong` = co thuc the desktop khac, thoat.
    hanh_dong: str
    cong: int = 0
    token: str = ""
    #: Ta co SO HUU backend nay khong. Quyet dinh viec dong app co tat
    #: backend hay khong.
    so_huu: bool = False
    ly_do: str = ""


def quyet_dinh(goc: Path, *, co_thuc_the_khac: bool,
               cong_muon: int = 0) -> KeHoachKhoiDong:
    """Nên nối lại, tự chạy, hay nhường? Hàm THUẦN trên trạng thái đĩa."""
    cu = doc_tep_khoa(goc)

    if cu is not None and backend_khoe(cu.cong, cu.token):
        # Co backend SONG va la cua ta (token khop). Noi lai, va KHONG so
        # huu no — dong cua so khong duoc tat backend cua nguoi khac.
        return KeHoachKhoiDong(
            "noi_lai", cong=cu.cong, token=cu.token, so_huu=False,
            ly_do=f"backend đang chạy ở cổng {cu.cong} (pid {cu.pid})")

    if co_thuc_the_khac:
        # Mutex noi co thuc the desktop khac, nhung khong co backend song
        # de noi vao — nghia la cai kia dang o giua luc khoi dong. Nhuong
        # de khong dung hai backend cung luc.
        return KeHoachKhoiDong(
            "nhuong",
            ly_do="đã có một Router Control Center đang khởi động")

    if cu is not None and tien_trinh_con_song(cu.pid):
        # Tien trinh con song nhung backend khong tra loi token cua ta:
        # hoac no dang treo, hoac mot tien trinh LA chiem dung pid do sau
        # khi pid duoc tai su dung. Khong tat gi ca — chi dung cong khac.
        return KeHoachKhoiDong(
            "tu_chay", cong=cong_muon or cong_rong(),
            token=secrets.token_urlsafe(32), so_huu=True,
            ly_do=(f"tệp khoá trỏ pid {cu.pid} còn sống nhưng backend không "
                   f"trả lời — dùng cổng khác, KHÔNG tắt tiến trình đó"))

    return KeHoachKhoiDong(
        "tu_chay", cong=cong_muon or cong_rong(),
        token=secrets.token_urlsafe(32), so_huu=True,
        ly_do=("tệp khoá mồ côi — dọn và tự chạy" if cu is not None
               else "chưa có backend nào — tự chạy"))


def duong_giao_dien(cong: int, token: str) -> str:
    """URL để nạp vào WebView.

    Token nằm trong URL, và đó là cách duy nhất trao nó cho trang mà không
    ghi nó ra đâu cả. Cửa sổ WebView **không có thanh địa chỉ**, và frontend
    xoá token khỏi URL ngay khi nạp (`history.replaceState`), nên nó không
    hiện ở tiêu đề, không vào lịch sử, không vào `Referer`.
    """
    return f"http://{DIA_CHI}:{cong}/?t={token}"

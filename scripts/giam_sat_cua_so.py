"""Bắt MỌI cửa sổ được tạo ra trong lúc nghiệm thu — kể cả cửa sổ nhấp
lên rồi tắt trong vài chục mili-giây.

VÌ SAO KHÔNG PHẢI "NGỒI NHÌN MÀN HÌNH". Yêu cầu nghiệm thu V0.4 là *không
một cửa sổ console nào được xuất hiện*. Một cửa sổ `conhost` do
`git.exe` sinh ra sống khoảng 30–120ms; mắt người thấy nó như một cái
nhấp, nhưng **không** nói được nó thuộc tiến trình nào, xảy ra bao nhiêu
lần, hay có xảy ra ở lần chạy này không. Và một bài nghiệm thu "tôi không
thấy gì" thì không phải bằng chứng.

CƠ CHẾ ĐO. Hai lớp, cố ý dư:

1. **`SetWinEventHook`** với `EVENT_OBJECT_CREATE` + `EVENT_OBJECT_SHOW`.
   Đây là lớp CHÍNH và nó **hướng sự kiện**: hệ điều hành gọi lại ta cho
   MỌI cửa sổ được tạo trên desktop, nên một cửa sổ sống 5ms cũng không
   lọt. Một phép hỏi vòng (poll) 30ms thì lọt, và đó chính là lý do lớp
   này tồn tại.
2. **Poll 25ms** làm lớp phủ: nếu hook bị hệ thống ngắt (nó bị ngắt khi
   luồng không bơm hàng đợi thông điệp đủ nhanh) thì vẫn còn một phép đo.

`WINEVENT_SKIPOWNPROCESS` để cửa sổ của chính bộ giám sát không tự tính.

CÁI GÌ LÀ VI PHẠM, nói cho chính xác:

* Một cửa sổ thuộc **lớp console** (`ConsoleWindowClass`,
  `CASCADIA_HOSTING_WINDOW_CLASS`, `PseudoConsoleWindow`), **hiện**
  (`IsWindowVisible`), có kích thước khác 0, và **không có trong mốc nền
  chụp trước khi mở ứng dụng**.
* Mốc nền là bắt buộc: máy người dùng (và cả phiên bash đang chạy bộ
  nghiệm thu này) có sẵn cửa sổ console. Không trừ mốc nền thì bài kiểm
  đỏ ngay từ giây đầu và đỏ vì lý do sai.
* `conhost.exe` XUẤT HIỆN KHÔNG PHẢI VI PHẠM. `CREATE_NO_WINDOW` vẫn cấp
  cho tiến trình con một console — nó chỉ không cấp **cửa sổ**. Nên đếm
  tiến trình là một tín hiệu chẩn đoán, còn phép kiểm thật là *cửa sổ*.

BỘ ĐẾM TIẾN TRÌNH CON cũng được giữ, và nó là chứng cứ chống rỗng: nếu
`git.exe` được sinh 0 lần thì bài "không có cửa sổ" trở nên vô nghĩa —
không có gì để nhấp thì đương nhiên không nhấp. Báo cáo phải cho thấy
ứng dụng THẬT SỰ đã sinh tiến trình console trong lúc đo.
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

#: Lop cua so cua console tren Windows.
#:
#: `ConsoleWindowClass` la conhost co dien. `CASCADIA_HOSTING_WINDOW_CLASS`
#: la Windows Terminal khi no la terminal mac dinh — cung mot su co, mot
#: lop cua so khac, va bo qua no la de lot dung cau hinh mac dinh cua
#: Windows 11. `PseudoConsoleWindow` thuong AN (ConPTY), nen no chi tinh
#: khi thuc su hien.
LOP_CONSOLE = {
    "ConsoleWindowClass",
    "CASCADIA_HOSTING_WINDOW_CLASS",
    "PseudoConsoleWindow",
}

#: Ten tien trinh console ma ung dung nay co the sinh ra.
TIEN_TRINH_CONSOLE = {
    "git.exe", "agy.exe", "codex.exe", "python.exe", "py.exe",
    "icacls.exe", "conhost.exe", "cmd.exe", "powershell.exe",
    "pwsh.exe", "tasklist.exe", "where.exe",
}

_EVENT_OBJECT_CREATE = 0x8000
_EVENT_OBJECT_SHOW = 0x8002
_OBJID_WINDOW = 0
_WINEVENT_OUTOFCONTEXT = 0x0000
_WINEVENT_SKIPOWNPROCESS = 0x0002
_TH32CS_SNAPPROCESS = 0x00000002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

_ENUMWINDOWSPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def _lop(hwnd) -> str:
    dem = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, dem, 256)
    return dem.value


def _tieu_de(hwnd) -> str:
    dem = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, dem, 512)
    return dem.value


def _pid_cua(hwnd) -> int:
    p = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return int(p.value)


def _co(hwnd):
    r = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (0, 0)
    return (r.right - r.left, r.bottom - r.top)


def _anh_chup_tien_trinh() -> Dict[int, tuple]:
    """`{pid: (ppid, ten)}` cho mọi tiến trình đang sống."""
    ra: Dict[int, tuple] = {}
    h = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if h == -1:
        return ra
    try:
        e = _PROCESSENTRY32()
        e.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        if not _kernel32.Process32First(h, ctypes.byref(e)):
            return ra
        while True:
            ra[int(e.th32ProcessID)] = (
                int(e.th32ParentProcessID),
                e.szExeFile.decode("latin-1", "replace"))
            if not _kernel32.Process32Next(h, ctypes.byref(e)):
                break
    finally:
        _kernel32.CloseHandle(h)
    return ra


@dataclass
class SuKienCuaSo:
    luc: float
    hwnd: int
    lop: str
    pid: int
    ten_tt: str
    tieu_de: str
    hien: bool
    co: tuple
    nguon: str                      # "hook" | "poll"
    la_con: bool                    # PID thuoc cay tien trinh cua app
    #: Ung dung dang lam GI luc cua so xuat hien. Khong co nhan nay
    #: thi mot dong "1 cua so console luc 62.2s" khong dan tra ve
    #: duoc thao tac nao ca — tuc la khong sua duoc.
    pha: str = ""
    #: Chuoi to tien `[(pid, ten), ...]` giai NGAY luc phat hien — de
    #: BAO CAO, khong de phan xu. Xem `cua_app`.
    to_tien: List[tuple] = field(default_factory=list)
    #: `[(luc, pid, ten, la_cua_app)]` — tien trinh MOI xuat hien tren
    #: may quanh luc cua so hien ra (+-1.5s), bat ke cha la ai, KEM co
    #: "co phai con cua ung dung khong" giai NGAY luc do.
    #:
    #: VI SAO: chuoi to tien khong quy trach nhiem duoc (xem
    #: `cua_app`), va tien trinh gay ra console co the da chet truoc
    #: khi ta kip lay cha cua no. Danh sach "vua xuat hien" thi goi
    #: ten duoc thu that su da sinh ra — do la khac biet giua "co mot
    #: cua so o giay 35" va "`git.exe` o giay 35".
    tt_quanh: List[tuple] = field(default_factory=list)
    #: `True` neu chuoi to tien co chua PID goc cua app.
    #:
    #: ĐỪNG LỌC VI PHẠM BẰNG CỜ NÀY. Đo được, 6/6 lần, trên chính máy
    #: này: một tiến trình con sinh ra không có cờ ẩn thì cửa sổ console
    #: hiện lên KHÔNG thuộc cây tiến trình của app. Trên Windows 11 với
    #: Windows Terminal làm terminal mặc định, cửa sổ đó do một
    #: `WindowsTerminal.exe` DÙNG CHUNG CẢ PHIÊN làm chủ, và tổ tiên của
    #: nó là `svchost.exe <- services.exe <- wininit.exe` — console mới
    #: chỉ là một TAB dựng bên trong tiến trình sẵn có đó qua DCOM.
    #:
    #: Nên `cua_app` gần như LUÔN `False` kể cả với cửa sổ do chính app
    #: gây ra, và một phép kiểm lọc theo nó thì KHÔNG BAO GIỜ ĐỎ ĐƯỢC.
    #: Phép phân xử đúng là **mốc nền**: cửa sổ console nào KHÔNG có
    #: trước khi app mở thì tính là vi phạm.
    cua_app: bool = False


def vi_pham_cua_app(ds: List["SuKienCuaSo"]) -> List["SuKienCuaSo"]:
    """Loc ra nhung cua so console MA UNG DUNG gay ra.

    VI SAO PHEP LOC NAY LA MOT PHAN CUA PHEP DO, khong phai mot cach
    lam nhe bai kiem:

    Bo nghiem thu chay 90-150s tren mot may DANG DUOC DUNG. Do duoc:
    trong mot lan chay, cua so console xuat hien cung luc voi
    `bash.exe` x8 + `jq.exe` — tuc la cua chinh phien Claude Code va
    cac hook shell cua no, khong phai cua ung dung. Cung lan do ung
    dung sinh `git.exe` x45 ma khong mot cua so nao di kem.

    Khong the quy trach nhiem bang CHU cua cua so: tren Windows 11 cua
    so console do mot `WindowsTerminal.exe` dung chung ca phien lam chu
    (to tien `svchost <- services <- wininit`), nen chu cua so KHONG
    BAO GIO la ung dung. Xem `SuKienCuaSo.cua_app`.

    Nen phep quy trach nhiem la: trong chum tien trinh VUA XUAT HIEN
    quanh cua so do, co it nhat mot tien trinh la CON CUA UNG DUNG hay
    khong. Co - ung dung chiu; khong - moi truong.

    Phep loc nay VAN DO DUOC: bo kiem chung cu chong rong sinh
    `cmd.exe` khong co co an va bat duoc 6/6 lan.
    """
    return [v for v in ds
            if any(x[3] for x in v.tt_quanh) or v.cua_app]


@dataclass
class KetQuaGiamSat:
    #: Cua so LOP CONSOLE, HIEN, co kich thuoc, KHONG co trong moc nen.
    vi_pham: List[SuKienCuaSo] = field(default_factory=list)
    #: Cua so lop console nhung AN — ghi lai de chan doan, khong tinh la
    #: vi pham (ConPTY tao cua so an la binh thuong).
    console_an: List[SuKienCuaSo] = field(default_factory=list)
    #: Moi cua so do CAY TIEN TRINH cua app tao ra, bat ke lop.
    cua_so_cua_app: List[SuKienCuaSo] = field(default_factory=list)
    #: `{ten_tien_trinh: so_lan_thay}` trong cay tien trinh cua app.
    tien_trinh_con: Dict[str, int] = field(default_factory=dict)
    #: Focus bi giat sang mot tien trinh KHONG phai app.
    doi_focus: List[tuple] = field(default_factory=list)
    #: Hook co that su gan duoc khong. `False` = chi con lop poll.
    hook_song: bool = False
    giay_do: float = 0.0

    def tom_tat(self) -> str:
        tt = ", ".join(f"{k}×{v}" for k, v in
                       sorted(self.tien_trinh_con.items(),
                              key=lambda x: -x[1])[:8]) or "(không có)"
        return (f"{self.giay_do:.1f}s đo · hook={'sống' if self.hook_song else 'CHẾT'}"
                f" · vi phạm={len(self.vi_pham)}"
                f" · console ẩn={len(self.console_an)}"
                f" · cửa sổ do app tạo={len(self.cua_so_cua_app)}"
                f" · giật focus={len(self.doi_focus)}"
                f"{chr(10)}      tiến trình con: {tt}")


class GiamSatCuaSo:
    """Theo dõi cửa sổ + tiến trình con của một cây tiến trình.

    Dùng như context manager. `pid_goc` đặt được muộn (`theo(pid)`) vì
    ứng dụng chỉ có PID sau khi đã mở — nhưng phép đo phải bắt đầu TRƯỚC
    đó để mốc nền không lẫn cửa sổ của chính lần mở này.
    """

    def __init__(self):
        self._pid_goc: Optional[int] = None
        self._con: Set[int] = set()
        self._ten_pid: Dict[int, str] = {}
        self._moc: Set[int] = set()
        self._dung = threading.Event()
        self._khoa = threading.Lock()
        self._kq = KetQuaGiamSat()
        self._t0 = 0.0
        self._luong: List[threading.Thread] = []
        self._id_luong_hook = 0
        self._da_ghi: Set[tuple] = set()
        self._fg_cuoi = 0
        self._pha = "(chua bat dau)"
        #: `[(luc, pid, ten)]` moi tien trinh MOI thay tren may.
        self._tt_moi: List[tuple] = []
        self._tt_da_thay: Set[int] = set()

    # -- doi song -----------------------------------------------------------

    def __enter__(self) -> "GiamSatCuaSo":
        self._t0 = time.time()
        # MOC NEN: moi cua so lop console DANG CO truoc khi ung dung mo.
        # May nguoi dung — va ca phien bash dang chay bo nghiem thu nay —
        # co san cua so console. Khong tru moc nen thi bai kiem do ngay
        # tu giay dau, va do vi ly do sai.
        self._moc = {h for h, l in self._moi_cua_so() if l in LOP_CONSOLE}
        self._luong = [
            threading.Thread(target=self._chay_hook, daemon=True),
            threading.Thread(target=self._chay_poll, daemon=True),
            threading.Thread(target=self._chay_tien_trinh, daemon=True),
        ]
        for t in self._luong:
            t.start()
        time.sleep(0.35)                 # cho hook gan xong
        return self

    def __exit__(self, *a) -> None:
        self.dung()

    def dat_pha(self, nhan: str) -> None:
        """Ghi nhan ứng dụng đang làm gì, để quy trách nhiệm."""
        with self._khoa:
            self._pha = nhan

    def theo(self, pid: int) -> None:
        with self._khoa:
            self._pid_goc = int(pid)
            self._con.add(int(pid))

    def dung(self) -> KetQuaGiamSat:
        if self._dung.is_set():
            return self._kq
        self._dung.set()
        if self._id_luong_hook:
            # Danh thuc `GetMessageW` de luong hook thoat.
            _user32.PostThreadMessageW(self._id_luong_hook, 0x0012, 0, 0)
        for t in self._luong:
            t.join(timeout=3)
        self._kq.giay_do = time.time() - self._t0
        return self._kq

    @property
    def ket_qua(self) -> KetQuaGiamSat:
        self._kq.giay_do = time.time() - self._t0
        return self._kq

    # -- lop 1: WinEventHook ------------------------------------------------

    def _chay_hook(self) -> None:
        self._id_luong_hook = _kernel32.GetCurrentThreadId()

        def _goi(hook, su_kien, hwnd, id_obj, id_con, tid, luc):
            if id_obj != _OBJID_WINDOW or not hwnd:
                return
            try:
                self._xet(hwnd, "hook")
            except Exception:                               # noqa: BLE001
                pass

        cb = _WINEVENTPROC(_goi)
        h = _user32.SetWinEventHook(
            _EVENT_OBJECT_CREATE, _EVENT_OBJECT_SHOW, None, cb, 0, 0,
            _WINEVENT_OUTOFCONTEXT | _WINEVENT_SKIPOWNPROCESS)
        self._kq.hook_song = bool(h)
        if not h:
            return
        msg = wintypes.MSG()
        try:
            while not self._dung.is_set():
                # `GetMessageW` khoa cho tot cho CPU, va hook
                # OUTOFCONTEXT duoc giao qua hang doi thong diep cua
                # DUNG luong nay — nen vong lap nay khong phai tuy chon.
                r = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r in (0, -1):
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            _user32.UnhookWinEvent(h)

    # -- lop 2: poll --------------------------------------------------------

    def _moi_cua_so(self) -> List[tuple]:
        ra: List[tuple] = []

        def _goi(hwnd, _):
            try:
                ra.append((int(hwnd), _lop(hwnd)))
            except Exception:                               # noqa: BLE001
                pass
            return True

        _user32.EnumWindows(_ENUMWINDOWSPROC(_goi), 0)
        return ra

    def _chay_poll(self) -> None:
        while not self._dung.is_set():
            try:
                for hwnd, lop in self._moi_cua_so():
                    if lop in LOP_CONSOLE or hwnd not in self._moc:
                        self._xet(hwnd, "poll")
                self._xet_focus()
            except Exception:                               # noqa: BLE001
                pass
            time.sleep(0.025)

    def _xet_focus(self) -> None:
        fg = _user32.GetForegroundWindow()
        if not fg or fg == self._fg_cuoi:
            return
        self._fg_cuoi = fg
        pid = _pid_cua(fg)
        with self._khoa:
            la_con = pid in self._con
        if self._pid_goc is None:
            return
        # Cua so cua chinh bo nghiem thu / terminal dang chay no thi
        # khong tinh: bai kiem quan tam viec UNG DUNG giat focus.
        if _lop(fg) not in LOP_CONSOLE:
            return
        to_tien, cua_app = self._to_tien(pid)
        ten = self._ten_pid.get(pid) or (to_tien[0][1] if to_tien else "?")
        self._kq.doi_focus.append(
            (time.time() - self._t0, pid, ten, _lop(fg), _tieu_de(fg),
             bool(cua_app or la_con), self._pha))

    # -- lop 3: cay tien trinh ---------------------------------------------

    def _chay_tien_trinh(self) -> None:
        while not self._dung.is_set():
            try:
                ds = _anh_chup_tien_trinh()
                # MOI tien trinh moi tren may, khong chi con cua app:
                # thu gay ra console co the la chau, va cha cua no co
                # the da chet truoc khi ta kip nhin.
                luc = time.time() - self._t0
                with self._khoa:
                    goc0 = self._pid_goc
                    for pid, (_ppid, ten) in ds.items():
                        if pid not in self._tt_da_thay:
                            self._tt_da_thay.add(pid)
                            if luc > 0.5:      # bo qua anh chup dau tien
                                # Quy trach nhiem NGAY LUC NAY, khi tien
                                # trinh con song va chuoi cha con doc
                                # duoc. Doi den luc bao cao thi `git.exe`
                                # (~30ms) da chet va cha cua no khong
                                # con tra ve duoc.
                                cua_ta = False
                                cur, n_buoc = pid, 0
                                while cur in ds and n_buoc < 12:
                                    if goc0 is not None and cur == goc0:
                                        cua_ta = True
                                        break
                                    cur = ds[cur][0]
                                    n_buoc += 1
                                self._tt_moi.append(
                                    (luc, pid, ten, cua_ta))
                    if len(self._tt_moi) > 4000:
                        del self._tt_moi[:2000]
                if self._pid_goc is not None:
                    with self._khoa:
                        goc = self._pid_goc
                        # Lap toi khi khong con them: mot tien trinh con
                        # cua con cung la con.
                        doi = True
                        while doi:
                            doi = False
                            for pid, (ppid, ten) in ds.items():
                                if ppid in self._con and pid not in self._con:
                                    self._con.add(pid)
                                    self._ten_pid[pid] = ten
                                    self._kq.tien_trinh_con[ten] = (
                                        self._kq.tien_trinh_con.get(ten, 0) + 1)
                                    doi = True
                        self._con.add(goc)
            except Exception:                               # noqa: BLE001
                pass
            time.sleep(0.12)

    def _to_tien(self, pid: int):
        """Chuỗi tổ tiên của `pid`, giải NGAY lúc phát hiện.

        Trả `([(pid, tên), …], có_phải_của_app)`. Đi lên tối đa 12 bậc và
        chặn vòng lặp: `th32ParentProcessID` có thể trỏ tới một PID đã bị
        dùng lại cho tiến trình khác, nên một chuỗi vô hạn là chuyện có
        thể xảy ra thật.
        """
        ds = _anh_chup_tien_trinh()
        with self._khoa:
            goc = self._pid_goc
            con = set(self._con)
        chuoi: List[tuple] = []
        da_qua: Set[int] = set()
        cur = int(pid)
        for _ in range(12):
            if cur in da_qua or cur not in ds:
                break
            da_qua.add(cur)
            ppid, ten = ds[cur]
            chuoi.append((cur, ten))
            if goc is not None and cur == goc:
                return chuoi, True
            if cur in con:
                return chuoi, True
            cur = ppid
        cua_app = goc is not None and any(p == goc for p, _ in chuoi)
        return chuoi, cua_app

    # -- phan xu -----------------------------------------------------------

    def _xet(self, hwnd, nguon: str) -> None:
        hwnd = int(hwnd)
        lop = _lop(hwnd)
        if not lop:
            return
        pid = _pid_cua(hwnd)
        with self._khoa:
            la_con = pid in self._con
        la_console = lop in LOP_CONSOLE
        if not la_console and not la_con:
            return
        hien = bool(_user32.IsWindowVisible(hwnd))
        co = _co(hwnd)
        khoa = (hwnd, lop, hien, co)
        if khoa in self._da_ghi:
            return
        self._da_ghi.add(khoa)
        to_tien, cua_app = self._to_tien(pid)
        luc_nay = time.time() - self._t0
        with self._khoa:
            quanh = [x for x in self._tt_moi
                     if abs(x[0] - luc_nay) <= 1.5]
        sk = SuKienCuaSo(
            luc=time.time() - self._t0, hwnd=hwnd, lop=lop, pid=pid,
            ten_tt=self._ten_pid.get(pid) or (to_tien[0][1] if to_tien
                                              else "?"),
            tieu_de=_tieu_de(hwnd),
            hien=hien, co=co, nguon=nguon, la_con=la_con or cua_app,
            to_tien=to_tien, cua_app=cua_app, pha=self._pha,
            tt_quanh=quanh)
        if la_console:
            if hwnd in self._moc:
                return                  # da co truoc khi app mo
            if hien and co[0] > 0 and co[1] > 0:
                self._kq.vi_pham.append(sk)
            else:
                self._kq.console_an.append(sk)
        elif la_con:
            self._kq.cua_so_cua_app.append(sk)

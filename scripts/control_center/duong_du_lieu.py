# -*- coding: utf-8 -*-
"""GỐC DỮ LIỆU CHÍNH TẮC của Router Control Center — MỘT nơi định nghĩa.

KHUYẾT TẬT LIÊN TỤC (nghiệm thu tay 2026-09-10, đã chứng minh): danh tính dự án
thì ỔN ĐỊNH (`project_id="fanfic"` → namespace `fanfic-dcf29d1141` chỉ băm từ
project_id), nhưng CHỖ LƯU thì không:

    source-mode   <checkout>\\.router\\memory\\fanfic-dcf29d1141\\memory.db
    bản đóng gói  <cạnh EXE>\\.router\\memory\\fanfic-dcf29d1141\\memory.db

Cùng một `project_id` mà ra HAI quyển sổ độc lập về vật lý. Đó chính là lý do
tuyên bố "GPT-6 Astra…" gõ vào bản `dist-v06` không bao giờ hiện ra ở bản
source-mode. Lời khuyên vận hành "luôn mở bằng `router-cc-desktop.cmd`" chỉ là
băng dán, không phải kiến trúc.

LUẬT CỦA TỆP NÀY:

1. **Gốc dữ liệu KHÔNG BAO GIỜ suy từ `__file__`, `cwd`, `sys.executable`, hay
   thư mục dist.** Nó là một chỗ CỐ ĐỊNH theo NGƯỜI DÙNG:
   `%LOCALAPPDATA%\\RouterControlCenter`. Nhị phân/mã nguồn ở một nơi, dữ liệu
   bền ở một nơi khác — nên dựng lại, nâng cấp phiên bản, đổi thư mục cài, tự
   cập nhật, hay một worktree khác đều KHÔNG sinh sổ mới.
2. **Thứ tự quyết định** (cao xuống thấp): tham số tường minh (`--root`, dùng
   cho bài kiểm/nghiệm thu) → biến môi trường `ROUTER_CC_DATA_ROOT` → chính
   tắc. Không có nhánh nào đọc vị trí mã.
3. **Giữ tầng `.router/` bên trong gốc.** Mọi module hiện có (`store.py`,
   `memory/service.py`, `attachments.py`, `desktop_shell.py`, `ghi_utf8.py`)
   đã dựng đường từ `<gốc>/.router/...`; giữ nguyên tầng đó nghĩa là đổi gốc
   là đổi TẤT CẢ cùng lúc, và di trú chỉ là chuyển một cây thư mục.
4. **Phiên bản KHO tách khỏi phiên bản ỨNG DỤNG** (`PHIEN_BAN_KHO`). Mở sổ →
   đọc phiên bản → nâng nếu cần → chạy tiếp. Không bao giờ tạo sổ mới chỉ vì
   ứng dụng lên phiên bản. Sổ MỚI HƠN mã thì DỪNG, không hạ cấp âm thầm.
5. **Một người ghi.** Nhiều bản dựng nay trỏ cùng một sổ, nên `KhoaKho` là
   khoá OS độc quyền trên `<gốc>/.router/kho.lock`. Bản thứ hai KHÔNG mở sổ
   thứ hai — nó nhận câu nói rõ ràng "kho dữ liệu đang được dùng".

Bí mật KHÔNG nằm ở đây: khoá provider vẫn ở Windows Credential Manager
(`providers/kho_bi_mat.py`); sổ chỉ giữ `credential_ref`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

#: Tên thư mục dữ liệu theo người dùng.
TEN_UNG_DUNG = "RouterControlCenter"

#: Biến môi trường ghi đè gốc (cho vận hành/bài kiểm — KHÔNG phải vị trí mã).
BIEN_GOC = "ROUTER_CC_DATA_ROOT"

#: Phiên bản BỐ CỤC KHO. Tăng khi bố cục `.router/` đổi, KHÔNG theo app.
#:   1 = `.router/{control_center,memory,attachments,v4,worktrees}`
PHIEN_BAN_KHO = 1

#: Tên tệp mốc phiên bản kho + tệp khoá một-người-ghi.
TEN_MOC = "kho.json"
TEN_KHOA = "kho.lock"


class KhoLoi(RuntimeError):
    """Kho không mở được (phiên bản mới hơn mã, hoặc đang bị chiếm)."""


# ------------------------------------------------------------------ goc -----

def goc_chinh_tac() -> Path:
    """`%LOCALAPPDATA%\\RouterControlCenter` (hoặc tương đương ngoài Windows).

    KHÔNG đọc `__file__`/`cwd`/`sys.executable` — đó là cả điểm của hàm này.
    """
    la = (os.environ.get("LOCALAPPDATA") or "").strip()
    if la:
        return (Path(la) / TEN_UNG_DUNG).resolve()
    # Ngoai Windows / thieu bien: theo XDG roi ve thu muc nguoi dung.
    xdg = (os.environ.get("XDG_DATA_HOME") or "").strip()
    if xdg:
        return (Path(xdg) / TEN_UNG_DUNG).resolve()
    return (Path.home() / ".routercontrolcenter").resolve()


def goc_du_lieu(ep: Optional[object] = None) -> Path:
    """Gốc dữ liệu CHÍNH TẮC. `ep` = ghi đè tường minh (`--root`).

    Thứ tự: `ep` → `$ROUTER_CC_DATA_ROOT` → `goc_chinh_tac()`.
    """
    if ep:
        return Path(str(ep)).expanduser().resolve()
    env = (os.environ.get(BIEN_GOC) or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return goc_chinh_tac()


def duong_router(goc: Optional[object] = None) -> Path:
    """`<gốc>/.router` — nơi mọi sổ bền nằm."""
    return goc_du_lieu(goc) / ".router"


def duong_moc(goc: Optional[object] = None) -> Path:
    return duong_router(goc) / TEN_MOC


def duong_khoa(goc: Optional[object] = None) -> Path:
    return duong_router(goc) / TEN_KHOA


def duong_control_db(goc: Optional[object] = None) -> Path:
    return duong_router(goc) / "control_center" / "control.db"


def duong_memory(goc: Optional[object] = None) -> Path:
    return duong_router(goc) / "memory"


# ------------------------------------------------------- phien ban kho ------

def doc_moc(goc: Optional[object] = None) -> Dict:
    """Mốc kho, hoặc `{}` nếu chưa có/đọc không được."""
    try:
        return json.loads(duong_moc(goc).read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def phien_ban_kho(goc: Optional[object] = None) -> int:
    """Phiên bản kho trên đĩa. `0` = chưa có mốc (sổ cũ hoặc sổ mới)."""
    try:
        return int(doc_moc(goc).get("phien_ban_kho") or 0)
    except (TypeError, ValueError):
        return 0


def _ghi_moc(goc: Path, moc: Dict) -> None:
    """Ghi mốc NGUYÊN TỬ: ghi tệp tạm rồi `replace` — một lần cắt điện giữa
    lúc ghi không được để lại một mốc nửa vời."""
    p = duong_moc(goc)
    p.parent.mkdir(parents=True, exist_ok=True)
    tam = p.with_suffix(".json.tmp")
    tam.write_text(json.dumps(moc, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tam, p)


def dam_bao_kho(goc: Optional[object] = None, *, ung_dung: str = "") -> Dict:
    """Mở/dựng kho ở `goc`: tạo cây `.router/`, đặt hoặc NÂNG mốc phiên bản.

    Trả mốc sau cùng. Ném `KhoLoi` nếu sổ trên đĩa MỚI HƠN mã hiểu được —
    hạ cấp âm thầm là cách chắc nhất để mất dữ liệu.
    """
    g = goc_du_lieu(goc)
    r = duong_router(g)
    for ten in ("control_center", "memory", "attachments"):
        (r / ten).mkdir(parents=True, exist_ok=True)
    moc = doc_moc(g)
    tren_dia = int(moc.get("phien_ban_kho") or 0)
    if tren_dia > PHIEN_BAN_KHO:
        raise KhoLoi(
            f"kho ở {g} có phiên bản {tren_dia}, mã này chỉ hiểu tới "
            f"{PHIEN_BAN_KHO} — hãy cập nhật Router, KHÔNG mở bằng bản cũ")
    now = time.time()
    if tren_dia == 0:
        moc = {"phien_ban_kho": PHIEN_BAN_KHO, "tao_luc": now,
               "cap_nhat_luc": now, "ung_dung": ung_dung or "",
               "bo_cuc": ".router/{control_center,memory,attachments,v4,worktrees}"}
        _ghi_moc(g, moc)
        return moc
    if tren_dia < PHIEN_BAN_KHO:
        # NÂNG BỐ CỤC theo từng bậc. Hiện chỉ có bậc 1, nên nhánh này là chỗ
        # đặt sẵn cho bậc sau — có bậc mới thì thêm hàm `_nang_1_len_2(...)`
        # và gọi ở đây, mỗi bậc phải tự idempotent.
        moc["phien_ban_kho"] = PHIEN_BAN_KHO
        moc["cap_nhat_luc"] = now
        moc.setdefault("tao_luc", now)
        if ung_dung:
            moc["ung_dung"] = ung_dung
        _ghi_moc(g, moc)
        return moc
    # Dung phien ban — chi cap nhat dau vet ung dung.
    if ung_dung and moc.get("ung_dung") != ung_dung:
        moc["ung_dung"] = ung_dung
        moc["cap_nhat_luc"] = now
        _ghi_moc(g, moc)
    return moc


def co_du_lieu(goc: Optional[object] = None) -> bool:
    """Gốc này đã có sổ THẬT chưa (control.db hoặc một quyển ký ức)?"""
    g = goc_du_lieu(goc)
    if duong_control_db(g).is_file():
        return True
    m = duong_memory(g)
    return m.is_dir() and any(m.glob("*/memory.db"))


# --------------------------------------------------------- mot nguoi ghi ----

class KhoaKho:
    """Khoá ĐỘC QUYỀN trên một gốc dữ liệu — một người ghi tại một thời điểm.

    Vì sao cần khi đã có mutex + tệp khoá của desktop: `desktop_shell.
    quyet_dinh()` có một nhánh `tu_chay` chạy KHI tệp khoá trỏ một pid còn
    sống mà backend không trả lời token của ta (treo, hoặc pid bị tái dùng).
    Trước đây điều đó vô hại vì mỗi bản dựng có sổ RIÊNG. Nay mọi bản dựng
    trỏ CÙNG một sổ, nên đúng nhánh đó sẽ mở người ghi thứ hai trên một
    SQLite. `KhoaKho` đóng cửa sổ đó ở tầng OS.

    Dùng `msvcrt.locking` (Windows) / `fcntl.flock` (còn lại). Khoá gắn với
    HANDLE nên nó tự tan khi tiến trình chết — không để lại khoá mồ côi như
    một tệp pid.
    """

    def __init__(self, goc: Optional[object] = None):
        self.goc = goc_du_lieu(goc)
        self.duong = duong_khoa(self.goc)
        self._f = None
        self.giu = False
        self.chu = ""          # mô tả người đang giữ (nếu đọc được)

    def thu_giu(self) -> bool:
        """Thử giành khoá. `True` = ta giữ. Không ném."""
        if self.giu:
            return True
        try:
            self.duong.parent.mkdir(parents=True, exist_ok=True)
            # Tep khoa la BIA THUAN: bao dam co it nhat 1 byte de khoa, va
            # KHONG BAO GIO ghi/cat no sau khi khoa (cat mot tep dang khoa la
            # mot cua so loi rieng). Thong tin nguoi giu di sang `.info`.
            if not self.duong.is_file() or self.duong.stat().st_size < 1:
                with open(self.duong, "wb") as k:
                    k.write(b"\0")
            f = open(self.duong, "r+b")
        except OSError:
            # Khong mo duoc tep khoa: KHONG chan ung dung vi mot loi quyen
            # tren mot tep phu — nhung cung khong noi doi la da giu.
            return False
        try:
            if os.name == "nt":
                import msvcrt
                # PHAI `seek(0)` TRUOC KHI KHOA. `msvcrt.locking` khoa mot dai
                # BYTE tai VI TRI HIEN TAI cua handle; mo bang "a+" thi vi tri
                # la EOF, nen sau khi ban dau tien ghi JSON vao tep, ban thu
                # hai khoa mot byte KHAC va KHONG xung dot -> khoa vo dung.
                # Bai kiem `test_nguoi_ghi_thu_hai_bi_chan` bat duoc dieu nay.
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Khong giu duoc -> doc thong tin nguoi dang giu (neu co) de noi RO.
            try:
                self.chu = (self.duong.with_suffix(".lock.info")
                            .read_text(encoding="utf-8")[:300]).strip()
            except Exception:                               # noqa: BLE001
                self.chu = ""
            f.close()
            return False
        self._f = f
        self.giu = True
        try:
            self.duong.with_suffix(".lock.info").write_text(
                json.dumps({"pid": os.getpid(), "tu": time.time(),
                            "exe": Path(sys.executable).name},
                           ensure_ascii=False), encoding="utf-8")
        except Exception:                                   # noqa: BLE001
            pass
        return True

    def nha(self) -> None:
        if self._f is None:
            self.giu = False
            return
        try:
            if os.name == "nt":
                import msvcrt
                try:
                    self._f.seek(0)
                    msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                self._f.close()
            except Exception:                               # noqa: BLE001
                pass
            self._f = None
            self.giu = False

    def __enter__(self):
        self.thu_giu()
        return self

    def __exit__(self, *a):
        self.nha()
        return False

    def cau_bao_dang_dung(self) -> str:
        """Câu NÓI RÕ cho người dùng khi kho đang bị chiếm."""
        ai = ""
        try:
            d = json.loads(self.chu or "{}")
            if d.get("pid"):
                ai = f" (tiến trình {d.get('pid')}"
                if d.get("exe"):
                    ai += f", {d['exe']}"
                ai += ")"
        except Exception:                                   # noqa: BLE001
            ai = ""
        return (f"Kho dữ liệu Router đang được dùng{ai}.\n\n"
                f"Gốc dữ liệu: {self.goc}\n\n"
                "Mọi bản Router (mã nguồn hay đóng gói) nay dùng CHUNG một kho, "
                "nên chỉ một bản được mở sổ tại một thời điểm. Hãy đóng bản đang "
                "chạy rồi mở lại, hoặc dùng chính bản đó.")


def mo_ta(goc: Optional[object] = None) -> Dict:
    """Ảnh chụp gọn để chẩn đoán/nghiệm thu — không mở sổ nào."""
    g = goc_du_lieu(goc)
    return {"goc": str(g), "chinh_tac": str(goc_chinh_tac()),
            "la_chinh_tac": g == goc_chinh_tac(),
            "bien_moi_truong": (os.environ.get(BIEN_GOC) or ""),
            "router": str(duong_router(g)),
            "control_db": str(duong_control_db(g)),
            "memory": str(duong_memory(g)),
            "phien_ban_kho": phien_ban_kho(g),
            "phien_ban_ma": PHIEN_BAN_KHO,
            "co_du_lieu": co_du_lieu(g)}

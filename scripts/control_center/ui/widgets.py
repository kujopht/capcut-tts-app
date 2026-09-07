"""Widget của Control Center — Textual.

DÙNG LẠI NỀN ĐÃ CÓ. Kho này đã chạy một TUI Textual (`router_v3/
control_room/`) với `requirements-control-room.txt` riêng và một lối vào
`fanfic-ctl`. Dựng Control Center trên cùng nền đó là đúng luật "ưu tiên
stack sẵn có" — không kéo thêm Tauri/React/Node vào một kho vốn chạy bằng
Python.

MỘT LUẬT HIỂN THỊ, áp cho mọi widget ở đây:

    KHÔNG BAO GIỜ VẼ SỐ LIỆU CŨ MÀ TRÔNG NHƯ MỚI.

`control_room/app.py` đã học điều này bằng một lỗi thật: một
`except Exception: pass` trong vòng lặp làm mới khiến bảng điều khiển tiếp
tục vẽ khung hình trước trong khi việc đọc trạng thái đã hỏng từ lâu —
người vận hành ra quyết định trên số liệu chết mà không có dấu hiệu nào.
Ở đây mọi lỗi đọc đều đi lên thanh trạng thái.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (DataTable, Input, Label, ListItem, ListView,
                             RichLog, Static)

#: Mau theo TRANG THAI. Mot bang dieu khien doc luc 3 gio sang phai noi
#: duoc "co viec nao dang cho TOI khong" bang mau, truoc khi doc chu.
MAU_TRANG_THAI: Dict[str, str] = {
    "QUEUED": "cyan",
    "WAITING": "yellow",
    "RUNNING": "bold green",
    "BLOCKED": "bold red",        # CAN NGUOI — do dam, khong mau nao khac
    "REVIEW": "magenta",
    "DONE": "dim green",
    "FAILED": "red",
    "PAUSED": "dim",
}

MAU_PHIEN: Dict[str, str] = {
    "STARTING": "yellow", "IDLE": "cyan", "BUSY": "bold green",
    "DRAINING": "yellow", "STOPPED": "dim", "DEAD": "red",
}

MAU_MUC: Dict[str, str] = {
    "INFO": "dim", "WARNING": "yellow", "ERROR": "red", "ALERT": "bold red",
}


def _gio(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "—"


def _so(v) -> str:
    """Số cho người đọc: `5` chứ không phải `5.0`, `—` khi không đo được.

    `5.0` trong cột "việc đã tạo" trông như một phép đo dấu phẩy động của
    một thứ vốn là phép đếm — nhiễu nhỏ nhưng đọc suốt đêm thì mệt.
    """
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _ngan(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


class ProjectSidebar(ListView):
    """Thanh bên dự án — MÀN HÌNH 1.

    Dự án là thứ tồn tại lâu nhất trong cả hệ thống, nên nó ở chỗ cố định
    nhất của màn hình và không bao giờ bị tab nào che.
    """

    class Chosen(Message):
        def __init__(self, project_id: str) -> None:
            self.project_id = project_id
            super().__init__()

    def __init__(self, projects: Sequence[Dict], **kw):
        super().__init__(**kw)
        self._projects = list(projects)

    def compose(self) -> ComposeResult:
        for p in self._projects:
            yield ListItem(Label(p["name"]), id=f"pj-{p['project_id']}")

    def update_projects(self, projects: Sequence[Dict],
                        counts: Optional[Dict[str, Dict]] = None) -> None:
        moi = [p["project_id"] for p in projects]
        if moi != [p["project_id"] for p in self._projects]:
            self.clear()
            for p in projects:
                self.append(ListItem(Label(p["name"]),
                                     id=f"pj-{p['project_id']}"))
            self._projects = list(projects)

    def on_list_view_selected(self, ev: ListView.Selected) -> None:
        if ev.item.id and ev.item.id.startswith("pj-"):
            self.post_message(self.Chosen(ev.item.id[3:]))


class ChatPanel(Vertical):
    """MÀN HÌNH 2 — ô chat chính của dự án.

    Đây là CỔNG VÀO duy nhất người dùng cần: gõ mục tiêu, Router lo phần
    còn lại. Ô nhập luôn ở dưới cùng và luôn nhận được focus.
    """

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def compose(self) -> ComposeResult:
        yield RichLog(id="chat-log", wrap=True, markup=True, highlight=False)
        yield Input(placeholder="Nói mục tiêu của bạn… (Enter để giao cho Router)",
                    id="chat-input")

    def update_chat(self, tin: Sequence[Dict]) -> None:
        log = self.query_one("#chat-log", RichLog)
        moi = [m["message_id"] for m in tin]
        if moi == getattr(self, "_da_ve", None):
            return
        self._da_ve = moi
        log.clear()
        for m in tin:
            nhan = {"user": "[bold cyan]BẠN[/]",
                    "router": "[bold green]ROUTER[/]",
                    "system": "[dim]HỆ THỐNG[/]"}.get(m["role"], m["role"])
            log.write(f"[dim]{_gio(m['ts'])}[/] {nhan}")
            for dong in str(m["text"]).splitlines() or [""]:
                log.write("  " + dong)
            log.write("")

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        if ev.input.id != "chat-input":
            return
        van_ban = (ev.value or "").strip()
        if not van_ban:
            return
        ev.input.value = ""
        self.post_message(self.Submitted(van_ban))


class TaskTable(DataTable):
    """MÀN HÌNH 3 — bảng việc, cả tám trạng thái."""

    class Chosen(Message):
        def __init__(self, task_id: str) -> None:
            self.task_id = task_id
            super().__init__()

    COLS = ("VIỆC", "TRẠNG THÁI", "QUYỀN", "ƯU TIÊN", "PHIÊN", "PHỤ THUỘC",
            "CHẠY", "NHÁNH")

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        for c in self.COLS:
            self.add_column(c, key=c)

    def update_tasks(self, tasks: Sequence[Dict]) -> None:
        chon = self._task_dang_chon()
        self.clear()
        for t in tasks:
            tt = t["state"]
            self.add_row(
                Text(_ngan(t["title"] or t["task_id"], 38)),
                Text(tt, style=MAU_TRANG_THAI.get(tt, "")),
                Text(t["permission"],
                     style="bold red" if t["permission"] == "GATED" else "dim"),
                Text(str(t["priority"]), style="dim"),
                Text(_ngan(t["owner_session"] or "—", 14), style="dim"),
                Text(_ngan(", ".join(t["dependencies"]) or "—", 18), style="dim"),
                Text(f"{t['runtime_seconds']:.0f}s" if t["runtime_seconds"]
                     else "—", style="dim"),
                Text(_ngan(t["branch"] or "—", 26), style="dim"),
                key=t["task_id"])
        if chon is not None:
            try:
                self.move_cursor(row=self.get_row_index(chon))
            except Exception:                             # noqa: BLE001
                pass

    def _task_dang_chon(self) -> Optional[str]:
        try:
            return self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value
        except Exception:                                 # noqa: BLE001
            return None

    @property
    def selected_task(self) -> Optional[str]:
        return self._task_dang_chon()

    def on_data_table_row_selected(self, ev: DataTable.RowSelected) -> None:
        if ev.row_key and ev.row_key.value:
            self.post_message(self.Chosen(str(ev.row_key.value)))


class AgentTable(DataTable):
    """MÀN HÌNH 4 — theo dõi agent/phiên."""

    COLS = ("PHIÊN", "PROVIDER", "VỊ TRÍ", "TRẠNG THÁI", "VIỆC", "PID",
            "WORKTREE", "NHÁNH", "SỐ VIỆC", "RẢNH")

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        for c in self.COLS:
            self.add_column(c, key=c)

    def update_sessions(self, sessions: Sequence[Dict]) -> None:
        chon = self.selected_session
        self.clear()
        for s in sessions:
            tt = s["state"]
            self.add_row(
                Text(_ngan(s["session_id"], 14)),
                Text(s["provider"] or "—", style="dim"),
                Text(_ngan(s["placement"], 26)),
                Text(tt, style=MAU_PHIEN.get(tt, "")),
                Text(_ngan(s["current_task"] or "—", 22), style="dim"),
                # PID rong nghia la KHONG DO DUOC, khong phai la 0.
                Text(str(s["pid"]) if s["pid"] else "—", style="dim"),
                Text(_ngan(s["worktree"] or "—", 30), style="dim"),
                Text(_ngan(s["branch"] or "—", 24), style="dim"),
                Text(str(s["task_count"]), style="dim"),
                Text(f"{s['idle_seconds']:.0f}s", style="dim"),
                key=s["session_id"])
        if chon is not None:
            try:
                self.move_cursor(row=self.get_row_index(chon))
            except Exception:                             # noqa: BLE001
                pass

    @property
    def selected_session(self) -> Optional[str]:
        try:
            return self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value
        except Exception:                                 # noqa: BLE001
            return None


class LockPanel(Static):
    """Khoá tài nguyên + ai đang xếp hàng. Nhỏ nhưng không được giấu đi:
    "vì sao việc của tôi không chạy" gần như luôn có câu trả lời ở đây."""

    def update_locks(self, locks: Sequence[Dict]) -> None:
        if not locks:
            self.update("[dim]Không có khoá tài nguyên nào đang giữ.[/]")
            return
        d = ["[bold]KHOÁ TÀI NGUYÊN[/]"]
        for l in locks:
            mau = "bold red" if l["kind"] == "PRODUCTION" else "yellow"
            han = "" if l["live"] else "  [red](QUÁ HẠN)[/]"
            d.append(f"  [{mau}]{l['kind']:<10}[/] {_ngan(l['resource'], 34):<34} "
                     f"← {_ngan(l['holder_task'] or '—', 24)}{han}")
            if l["waiters"]:
                d.append(f"      [dim]đang chờ: {', '.join(l['waiters'])}[/]")
        self.update("\n".join(d))


class UsagePanel(VerticalScroll):
    """MÀN HÌNH 7 — usage, LUÔN kèm nhãn mức tin cậy.

    Không có ô nào hiện một con số trần. Mỗi số mang `[ACTUAL]`,
    `[ESTIMATED]`, hoặc hiện `— (KHÔNG ĐO ĐƯỢC)`.
    """

    def compose(self) -> ComposeResult:
        yield Static(id="usage-body")

    def update_usage(self, bc: Dict) -> None:
        d: List[str] = ["[bold]CONTROL CENTER TỰ ĐẾM[/]  [dim](ACTUAL — đếm "
                        "tại chỗ, không hỏi ai)[/]"]
        for m in bc.get("local", []):
            d.append(f"  {m['label']:<26} {_so(m['value'])}{m['unit']}"
                     f"  [dim][{m['confidence']}][/]")

        d += ["", "[bold]TÀI KHOẢN THẬT ĐÃ CẤP PHÁT[/]"]
        tk = bc.get("accounts", {})
        d.append("  " + (", ".join(f"{k}={v}" for k, v in tk.items())
                         if tk else "[dim]—[/]"))
        chua = [r for r in bc.get("runtimes", []) if not r["provisioned"]]
        if chua:
            d.append(f"  [yellow]chưa cấp phát: "
                     f"{', '.join(r['runtime_id'] for r in chua)}[/]")

        d += ["", "[bold]BỂ QUOTA[/]"]
        if not bc.get("pools"):
            d.append("  [dim]—[/]")
        for u in bc.get("pools", []):
            d.append(f"  [cyan]{u['account_id']}[/] · {u['provider']}")
            for m in u["metrics"]:
                gt = ("[dim]— (KHÔNG ĐO ĐƯỢC)[/]" if m["value"] is None
                      else f"{_so(m['value'])}{m['unit']}")
                mau = {"ACTUAL": "green", "ESTIMATED": "yellow",
                       "UNAVAILABLE": "dim"}[m["confidence"]]
                d.append(f"      {m['label']:<24} {gt}  "
                         f"[{mau}][{m['confidence']}][/]")

        d += ["", "[bold]NHÀ CUNG CẤP[/]"]
        if not bc.get("provider_probe_ran"):
            d.append("  [dim]chưa dò — bấm `u` để hỏi CLI nhà cung cấp.[/]")
            d.append(f"  [dim]{bc.get('note', '')}[/]")
        for u in bc.get("providers", []):
            d.append(f"  [cyan]{u['provider']}[/] · {u['account_id']}"
                     f"  [dim]{u['note']}[/]")
            for m in u["metrics"]:
                gt = ("[dim]— (KHÔNG ĐO ĐƯỢC)[/]" if m["value"] is None
                      else f"{_so(m['value'])}{m['unit']}")
                d.append(f"      {m['label']:<24} {gt}")
                if m["note"]:
                    d.append(f"        [dim]{m['note']}[/]")
        self.query_one("#usage-body", Static).update("\n".join(d))


class EventLog(RichLog):
    """MÀN HÌNH 6 — dòng sự kiện. Chỉ nối thêm, không vẽ lại."""

    def __init__(self, **kw):
        super().__init__(wrap=False, markup=True, highlight=False, **kw)
        self._id_cuoi = 0

    def update_events(self, events: Sequence[Dict]) -> None:
        moi = [e for e in reversed(events) if e["id"] > self._id_cuoi]
        for e in moi:
            self._id_cuoi = max(self._id_cuoi, e["id"])
            mau = MAU_MUC.get(e["level"], "")
            self.write(f"[dim]{_gio(e['ts'])}[/] [{mau}]{e['level']:<7}[/] "
                       f"{e['kind']:<20} {_ngan(e['detail'], 110)}")


class StatusBar(Static):
    """Một dòng SỰ THẬT về việc bảng này có đang đọc được dữ liệu không.

    Tồn tại vì lỗi thật ở `control_room/app.py`: bảng vẽ số liệu chết trông
    hệt số liệu sống. Một bảng nói "KHÔNG ĐỌC ĐƯỢC" hữu ích hơn nhiều một
    bảng nói dối.
    """

    def set_health(self, *, tasks: int = 0, running: int = 0, blocked: int = 0,
                   sessions: int = 0, failures: int = 0,
                   last_error: str = "") -> None:
        if failures:
            self.update(f"[bold red]KHÔNG ĐỌC ĐƯỢC TRẠNG THÁI[/] "
                        f"({failures} lần) — {_ngan(last_error, 90)}")
            return
        canh = (f"  [bold red]{blocked} CẦN BẠN[/]" if blocked else "")
        self.update(
            f"[green]●[/] đang đọc được  │  {tasks} việc  │  "
            f"[bold green]{running} đang chạy[/]  │  {sessions} phiên{canh}"
            f"  │  [dim]q thoát · enter chi tiết · p tạm dừng · s dừng · "
            f"r giao lại · g duyệt cổng · u đo usage[/]")

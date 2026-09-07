"""Ứng dụng Control Center — Textual. Bảy màn hình của V0.1.

    1 Projects      thanh bên trái, luôn hiện
    2 Project Chat  tab "Chat"
    3 Tasks         tab "Việc"
    4 Agents        tab "Agent"
    5 Task Detail   modal, mở bằng Enter từ bảng việc
    6 Logs          tab "Log"
    7 Usage         tab "Usage"

ĐÂY LÀ CÔNG CỤ VẬN HÀNH, KHÔNG PHẢI BẢN DỰNG HÌNH. Mọi nút đều gọi thẳng
`ControlCenter` thật; không có dữ liệu mẫu ở bất kỳ đâu trong tệp này.

HAI LUẬT AN TOÀN Ở TẦNG GIAO DIỆN:

1. **Thao tác phá được thì phải xác nhận.** `stop` giết tiến trình agent và
   mất kết quả lượt đang chạy; `duyệt cổng` cho một việc GATED chạy. Cả hai
   hỏi lại. `pause` thì không — nó hoàn tác được.
2. **Vòng lặp vẽ KHÔNG gọi mạng.** `snapshot()` chỉ đọc SQLite. Việc hỏi
   CLI nhà cung cấp (chậm, tốn một lượt) chỉ chạy khi người dùng bấm `u`.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Footer, Header, Label, Static,
                             TabbedContent, TabPane)

from scripts.control_center.engine import ControlCenter
from scripts.control_center.ui.widgets import (AgentTable, ChatPanel, EventLog,
                                               LockPanel, ProjectSidebar,
                                               StatusBar, TaskTable, UsagePanel,
                                               _gio, _ngan)


class XacNhan(ModalScreen[bool]):
    """Hỏi lại trước một thao tác không hoàn tác được."""

    BINDINGS = [Binding("escape", "huy", "Huỷ")]

    def __init__(self, tieu_de: str, noi_dung: str):
        super().__init__()
        self.tieu_de, self.noi_dung = tieu_de, noi_dung

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(f"[bold]{self.tieu_de}[/]", id="confirm-title")
            yield Static(self.noi_dung, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button("Huỷ", variant="primary", id="no")
                yield Button("Xác nhận", variant="error", id="yes")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "yes")

    def action_huy(self) -> None:
        self.dismiss(False)


class TaskDetail(ModalScreen[None]):
    """MÀN HÌNH 5 — chi tiết một việc, gồm cả log thô của agent."""

    BINDINGS = [Binding("escape,q", "dong", "Đóng")]

    def __init__(self, task: Dict, log: str):
        super().__init__()
        # KHONG dat ten `self.task` hay `self.log`: `MessagePump`/`DOMNode`
        # cua Textual da co CA HAI thuoc tinh do va ca hai chi doc, nen gan
        # de len chung nem `AttributeError` ngay luc mo modal. Va phai ca hai
        # lan dau chay bai kiem giao dien — day dung la loai loi chi lo ra
        # khi giao dien duoc mo that.
        self.viec, self.nhat_ky = task, log

    def compose(self) -> ComposeResult:
        t = self.viec
        d = [f"[bold]{t['task_id']}[/]  —  [bold]{t['state']}[/]",
             "",
             f"tiêu đề   : {t['title']}",
             f"quyền     : {t['permission']}"
             + (f"   [bold red]CỔNG: {t['gate_reason']}[/]"
                if t['permission'] == 'GATED' else ""),
             f"ưu tiên   : {t['priority']}",
             f"phiên     : {t['owner_session'] or '—'}",
             f"worktree  : {t['worktree'] or '—'}",
             f"nhánh     : {t['branch'] or '—'}",
             f"phụ thuộc : {', '.join(t['dependencies']) or '—'}",
             f"tài nguyên: {', '.join(t['resources']) or '—'}",
             f"lượt thử  : {t['attempts']}",
             f"tạo lúc   : {_gio(t['created_at'])}"
             f"   chạy: {t['runtime_seconds']:.0f}s"]
        if t["blocked_reason"]:
            d += ["", f"[bold red]LÝ DO CHẶN[/]", t["blocked_reason"]]
        d += ["", "[bold]MỤC TIÊU[/]", t["objective"]]
        kq = (t.get("result") or {}).get("envelope") or {}
        if kq:
            d += ["", "[bold]KẾT QUẢ[/]",
                  f"trạng thái: {kq.get('status')}   "
                  f"model: {kq.get('model')}   worker: {kq.get('worker')}",
                  f"tóm tắt   : {kq.get('summary', '')}"]
            for ten, khoa in (("tệp đổi", "changes"), ("phát hiện", "findings"),
                              ("rủi ro", "risks")):
                if kq.get(khoa):
                    d.append(f"{ten}:")
                    d += [f"  - {x}" for x in kq[khoa][:10]]
        d += ["", "[bold]NHẬT KÝ[/]", self.nhat_ky]
        with VerticalScroll(id="detail-box"):
            yield Static("\n".join(d))

    def action_dong(self) -> None:
        self.dismiss(None)


class ControlCenterApp(App):
    """Phòng điều khiển Router — V0.1."""

    TITLE = "ROUTER CONTROL CENTER"
    SUB_TITLE = "V0.1"

    CSS = """
    Screen { background: #16161e; color: #c0caf5; }
    #shell { height: 1fr; }
    #sidebar { width: 22; border-right: solid #2a2b3d; }
    #sidebar-title { padding: 0 1; color: #7aa2f7; text-style: bold; }
    #main { width: 1fr; }
    ProjectSidebar { height: 1fr; background: #16161e; }
    #chat-log { height: 1fr; border: none; }
    #chat-input { dock: bottom; border: tall #2a2b3d; }
    TaskTable, AgentTable { height: 1fr; }
    LockPanel { height: auto; max-height: 10; padding: 0 1;
                border-top: solid #2a2b3d; }
    StatusBar { dock: bottom; height: 1; padding: 0 1; background: #1a1b26; }
    #confirm-box { width: 70; height: auto; padding: 1 2; margin: 4 8;
                   border: thick #f7768e; background: #1a1b26; }
    #confirm-buttons { height: auto; align: right middle; padding-top: 1; }
    #confirm-buttons Button { margin-left: 2; }
    #detail-box { padding: 1 2; background: #1a1b26; border: thick #7aa2f7; }
    """

    BINDINGS = [
        Binding("q", "quit", "Thoát", priority=True),
        Binding("enter", "chi_tiet", "Chi tiết việc"),
        Binding("p", "tam_dung", "Tạm dừng"),
        Binding("o", "tiep_tuc", "Tiếp tục"),
        Binding("s", "dung_han", "Dừng hẳn"),
        Binding("r", "giao_lai", "Giao lại"),
        Binding("g", "duyet_cong", "Duyệt cổng"),
        Binding("u", "do_usage", "Đo usage"),
        Binding("f5", "lam_moi", "Làm mới"),
    ]

    def __init__(self, cc: ControlCenter, *, refresh_interval: float = 1.0,
                 autostart: bool = True, **kw):
        super().__init__(**kw)
        self.cc = cc
        #: Co tu chay vong lap dieu phoi khi mo khong. `False` bien giao dien
        #: thanh mot bang QUAN SAT thuan tuy — huu ich khi mot tien trinh
        #: Control Center KHAC dang cam nhip (hai vong lap cung giao viec la
        #: hai ben cung `claim`, va tuy `claim` nguyen tu nen khong hong,
        #: nhung no lam bang dieu khien tranh nhau vo ich).
        self.autostart = autostart
        self.refresh_interval = max(0.25, refresh_interval)
        self.project_id: str = ""
        self.snap: Dict = {}
        self._usage: Dict = {}
        self._doc_hong = 0
        self._loi_cuoi = ""

    # -- dung man hinh ------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="shell"):
            with Vertical(id="sidebar"):
                yield Label("DỰ ÁN", id="sidebar-title")
                yield ProjectSidebar([], id="projects")
            with Vertical(id="main"):
                with TabbedContent(id="tabs"):
                    with TabPane("Chat", id="tab-chat"):
                        yield ChatPanel(id="chat")
                    with TabPane("Việc", id="tab-tasks"):
                        yield TaskTable(id="tasks")
                        yield LockPanel(id="locks")
                    with TabPane("Agent", id="tab-agents"):
                        yield AgentTable(id="agents")
                    with TabPane("Log", id="tab-logs"):
                        yield EventLog(id="events")
                    with TabPane("Usage", id="tab-usage"):
                        yield UsagePanel(id="usage")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        ps = self.cc.projects()
        self.project_id = ps[0].project_id if ps else ""
        self.lam_moi()
        self.set_interval(self.refresh_interval, self.lam_moi)
        # Vong lap dieu phoi chay trong NEN. Giao dien chi quan sat va ra
        # lenh; no khong bao gio la thu giu nhip cho viec chay.
        if self.autostart:
            self.cc.start()

    def on_unmount(self) -> None:
        try:
            self.cc.shutdown()
        except Exception:                                 # noqa: BLE001
            pass

    # -- vong lap ve --------------------------------------------------------

    def lam_moi(self) -> None:
        try:
            self.snap = self.cc.snapshot(self.project_id)
            self.query_one("#projects", ProjectSidebar).update_projects(
                self.snap.get("projects", []))
            self.query_one("#chat", ChatPanel).update_chat(
                self.snap.get("chat", []))
            self.query_one("#tasks", TaskTable).update_tasks(
                self.snap.get("tasks", []))
            self.query_one("#locks", LockPanel).update_locks(
                self.snap.get("locks", []))
            self.query_one("#agents", AgentTable).update_sessions(
                self.snap.get("sessions", []))
            self.query_one("#events", EventLog).update_events(
                self.snap.get("events", []))
            # Phan RE cua usage (Control Center tu dem + be quota) doc tu
            # SQLite va tu fabric trong bo nho, nen tinh lai MOI nhip. Ban
            # dau doan nay chi tinh mot lan (`if not self._usage`), nen sau
            # khi tao viec thi bang usage van dung yen o so cu — dung cai
            # loi "ve so lieu chet ma trong nhu song" ma `StatusBar` ton tai
            # de chan.
            #
            # Phan DAT (goi CLI nha cung cap) thi KHONG: no cham vai giay va
            # ton mot luot quota moi lan. Ket qua do lan gan nhat duoc GIU
            # LAI va gan vao day, chi lam moi khi nguoi dung bam `u`.
            bc = self.cc.usage.report(self.project_id, probe_cli=False)
            if self._usage.get("provider_probe_ran"):
                bc["providers"] = self._usage.get("providers", [])
                bc["provider_probe_ran"] = True
            self._usage = bc
            self.query_one("#usage", UsagePanel).update_usage(self._usage)
            self._doc_hong = 0
            self._cap_nhat_thanh_trang_thai()
        except Exception as exc:                          # noqa: BLE001
            # GIU TUI SONG nhung KHONG BAO GIO im lang — xem docstring
            # `StatusBar`. Thong diep qua `redact` truoc khi len man hinh:
            # mot traceback co the mang duong dan hoac chuoi giong credential.
            from scripts.router_v3.packet import redact
            self._doc_hong += 1
            self._loi_cuoi = redact(f"{type(exc).__name__}: {exc}")[:200]
            try:
                self.query_one("#status", StatusBar).set_health(
                    failures=self._doc_hong, last_error=self._loi_cuoi)
            except Exception:                             # noqa: BLE001
                pass

    def _cap_nhat_thanh_trang_thai(self) -> None:
        ts = self.snap.get("tasks", [])
        self.query_one("#status", StatusBar).set_health(
            tasks=len(ts),
            running=sum(1 for t in ts if t["state"] == "RUNNING"),
            blocked=sum(1 for t in ts if t["state"] == "BLOCKED"),
            sessions=sum(1 for s in self.snap.get("sessions", [])
                         if s["state"] in ("IDLE", "BUSY", "STARTING")))

    # -- su kien ------------------------------------------------------------

    def on_project_sidebar_chosen(self, ev: ProjectSidebar.Chosen) -> None:
        if ev.project_id == self.project_id:
            return
        self.project_id = ev.project_id
        self._usage = {}
        self.query_one("#events", EventLog).clear()
        self.query_one("#events", EventLog)._id_cuoi = 0
        self.lam_moi()

    def on_chat_panel_submitted(self, ev: ChatPanel.Submitted) -> None:
        if not self.project_id:
            self.notify("Chưa chọn dự án", severity="warning")
            return
        try:
            kq = self.cc.chat(self.project_id, ev.text)
        except Exception as exc:                          # noqa: BLE001
            self.notify(f"Không phân rã được: {exc}", severity="error")
            return
        n = len(kq["tasks"])
        chan = sum(1 for t in kq["tasks"] if t["state"] == "BLOCKED")
        self.notify(
            f"Đã tạo {n} việc" + (f", {chan} CẦN BẠN DUYỆT" if chan else ""),
            severity="warning" if chan else "information")
        self.lam_moi()

    def on_task_table_chosen(self, ev: TaskTable.Chosen) -> None:
        self._mo_chi_tiet(ev.task_id)

    # -- hanh dong ----------------------------------------------------------

    def _viec_dang_chon(self) -> Optional[str]:
        """Việc mà các phím vận hành sẽ tác động — THEO TAB ĐANG MỞ.

        Ở tab Agent, người dùng đang nhìn một PHIÊN, không nhìn một việc.
        Nếu `p`/`s`/`r` cứ tác động lên con trỏ của bảng Việc (có thể đang
        ở một dòng hoàn toàn khác, thậm chí không nhìn thấy), thì người
        dùng dừng nhầm việc — và `s` thì giết tiến trình thật. Nên ở tab
        đó, phím tác động lên việc mà phiên ĐANG chạy.

        Phiên rảnh (`current_task` rỗng) trả `None`: không có việc nào để
        dừng, và đoán bừa một việc cũ của phiên đó còn tệ hơn.
        """
        try:
            tab = self.query_one("#tabs", TabbedContent).active
        except Exception:                                 # noqa: BLE001
            tab = ""
        if tab == "tab-agents":
            sid = self.query_one("#agents", AgentTable).selected_session
            s = next((x for x in self.snap.get("sessions", [])
                      if x["session_id"] == sid), None)
            return (s or {}).get("current_task") or None
        return self.query_one("#tasks", TaskTable).selected_task

    def _mo_chi_tiet(self, task_id: str) -> None:
        t = next((x for x in self.snap.get("tasks", [])
                  if x["task_id"] == task_id), None)
        if t is None:
            return
        self.push_screen(TaskDetail(t, self.cc.log_cua_viec(task_id)))

    def action_chi_tiet(self) -> None:
        tid = self._viec_dang_chon()
        if tid:
            self._mo_chi_tiet(tid)

    def action_lam_moi(self) -> None:
        self.lam_moi()

    def action_tam_dung(self) -> None:
        self._lam("tạm dừng", self.cc.pause)

    def action_tiep_tuc(self) -> None:
        self._lam("tiếp tục", self.cc.resume)

    def action_giao_lai(self) -> None:
        self._lam("giao lại", self.cc.reassign)

    def _lam(self, ten: str, ham) -> None:
        tid = self._viec_dang_chon()
        if not tid:
            self.notify("Chọn một việc trước", severity="warning")
            return
        try:
            ham(tid)
            self.notify(f"Đã {ten} {tid}")
        except Exception as exc:                          # noqa: BLE001
            self.notify(f"Không {ten} được: {exc}", severity="error")
        self.lam_moi()

    def action_dung_han(self) -> None:
        """Dừng hẳn — HỎI LẠI, vì nó giết tiến trình và mất kết quả."""
        tid = self._viec_dang_chon()
        if not tid:
            self.notify("Chọn một việc trước", severity="warning")
            return

        def _xong(dong_y: Optional[bool]) -> None:
            if not dong_y:
                return
            try:
                self.cc.stop(tid)
                self.notify(f"Đã dừng {tid}", severity="warning")
            except Exception as exc:                      # noqa: BLE001
                self.notify(f"Không dừng được: {exc}", severity="error")
            self.lam_moi()

        self.push_screen(XacNhan(
            "DỪNG HẲN VIỆC",
            f"Dừng {tid}?\n\nNếu agent đang chạy, tiến trình của nó sẽ bị "
            f"GIẾT và kết quả của lượt đang chạy sẽ MẤT.\nWorktree và nhánh "
            f"KHÔNG bị xoá."), _xong)

    def action_duyet_cong(self) -> None:
        """Duyệt một việc GATED — HỎI LẠI, và ghi lại ai duyệt."""
        tid = self._viec_dang_chon()
        t = next((x for x in self.snap.get("tasks", [])
                  if x["task_id"] == tid), None)
        if t is None:
            self.notify("Chọn một việc trước", severity="warning")
            return
        if t["permission"] != "GATED":
            self.notify("Việc này không bị chặn bởi cổng nào",
                        severity="information")
            return

        def _xong(dong_y: Optional[bool]) -> None:
            if not dong_y:
                return
            try:
                self.cc.mo_khoa_gated(tid, approved_by="tui")
                self.notify(f"Đã duyệt cổng cho {tid}", severity="warning")
            except Exception as exc:                      # noqa: BLE001
                self.notify(f"Không duyệt được: {exc}", severity="error")
            self.lam_moi()

        self.push_screen(XacNhan(
            "DUYỆT CỔNG AN TOÀN",
            f"{t['blocked_reason']}\n\nDuyệt nghĩa là việc này ĐƯỢC PHÉP chạy "
            f"thao tác đã bị chặn. Control Center sẽ ghi lại rằng bạn đã "
            f"duyệt."), _xong)

    def action_do_usage(self) -> None:
        """Hỏi CLI nhà cung cấp. CHẬM — nên nó là một phím bấm, không phải
        một nhịp của vòng lặp vẽ."""
        self.notify("Đang hỏi CLI nhà cung cấp… (vài giây)")

        def _do() -> None:
            try:
                bc = self.cc.usage.report(self.project_id, probe_cli=True)
            except Exception as exc:                      # noqa: BLE001
                self.call_from_thread(
                    self.notify, f"Không đo được usage: {exc}",
                    severity="error")
                return
            self._usage = bc
            self.call_from_thread(
                self.query_one("#usage", UsagePanel).update_usage, bc)
            self.call_from_thread(self.notify, "Đã cập nhật usage")

        self.run_worker(_do, thread=True, name="usage-probe")

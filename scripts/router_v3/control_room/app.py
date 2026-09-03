"""Ứng dụng phòng điều khiển TUI — Router V4 Control Room.

Giao diện vận hành trực tiếp bên trong Warp Terminal:
- Hiển thị bảng điều phối tập trung trong MỘT màn hình duy nhất.
- Tự động làm mới chu kỳ 1 giây, tải nhẹ, an toàn đồng thời.
- Hỗ trợ phím tắt và các màn hình pop-up xem chi tiết, log, giải thích định tuyến.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer

from scripts.router_v3.control_room.controls import SafeController
from scripts.router_v3.control_room.event_store import EventStore
from scripts.router_v3.control_room.screens import (
    ConfirmModal,
    ExplainModal,
    LogViewModal,
    TaskDetailModal,
    WorktreeModal,
)
from scripts.router_v3.control_room.state_reader import (
    ControlRoomSnapshot,
    StateReader,
    TaskDetailView,
    WorkerDetailView,
)
from scripts.router_v3.control_room.widgets import (
    ClaudeLeadWidget,
    EventsWidget,
    HeaderWidget,
    SelectedTaskWidget,
    StatusBarWidget,
    TaskDagWidget,
    WorkerPanelWidget,
)


class ControlRoomApp(App):
    """Ứng dụng TUI điều phối bể worker và Task DAG cho Fanfic World."""

    TITLE = "FANFIC WORLD CONTROL ROOM"
    CSS = """
    Screen {
        background: #1a1b26;
        color: #c0caf5;
    }
    #main-container {
        height: 100%;
        width: 100%;
    }
    #top-section {
        height: 5;
    }
    #middle-section {
        height: 1fr;
        min-height: 10;
    }
    #dag-column {
        width: 50%;
        height: 100%;
    }
    #worker-column {
        width: 50%;
        height: 100%;
    }
    #bottom-section {
        height: 16;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Thoát", priority=True),
        Binding("enter", "show_detail", "Chi tiết task"),
        Binding("e", "explain_routing", "Giải thích định tuyến"),
        Binding("l", "show_logs", "Xem logs"),
        Binding("d", "drain_worker", "Drain worker"),
        Binding("r", "retry_task", "Retry task"),
        Binding("p", "toggle_pause", "Tạm dừng/Tiếp tục"),
        Binding("w", "show_worktrees", "Xem worktree"),
        Binding("f", "cycle_filter", "Đổi bộ lọc sự kiện"),
    ]

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        run_id: Optional[str] = None,
        refresh_interval: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.root = Path(root) if root else Path.cwd()
        self.run_id = run_id
        self.refresh_interval = refresh_interval

        self.event_store = EventStore(root=self.root)
        self.state_reader = StateReader(root=self.root, event_store=self.event_store)
        self.controller = SafeController(
            root=self.root,
            event_store=self.event_store,
            state_reader=self.state_reader,
        )

        self.snapshot_data: Optional[ControlRoomSnapshot] = None
        self.selected_task: Optional[TaskDetailView] = None
        self.selected_worker: Optional[WorkerDetailView] = None
        self.current_event_filter = "ALL"

    #: Dem so lan DOC trang thai that bai, va loi gan nhat (da loc).
    #: Ton tai de thanh trang thai noi duoc "dang doc loi" thay vi
    #: ve lai so lieu cu mot cach im lang.
    _doc_that_bai: int = 0
    _loi_gan_nhat: str = ""
    #: Dem rieng cho truong hop "doc hong VA bao loi cung hong".
    _bao_loi_that_bai: int = 0

    def compose(self) -> ComposeResult:
        # Initial empty snapshot
        snap = self.state_reader.snapshot(run_id=self.run_id, event_category=self.current_event_filter)
        self.snapshot_data = snap
        self.selected_task = snap.tasks[0] if snap.tasks else None
        self.selected_worker = snap.workers[0] if snap.workers else None

        yield Vertical(
            Vertical(
                HeaderWidget(snap.mission, id="header-widget"),
                ClaudeLeadWidget(snap.claude_lead, id="lead-widget"),
                id="top-section",
            ),
            Horizontal(
                Vertical(TaskDagWidget(snap.tasks, id="dag-widget"), id="dag-column"),
                Vertical(WorkerPanelWidget(snap.workers, id="worker-widget"), id="worker-column"),
                id="middle-section",
            ),
            Vertical(
                SelectedTaskWidget(self.selected_task, id="detail-widget"),
                EventsWidget(snap.events, self.current_event_filter, id="events-widget"),
                StatusBarWidget(id="status-widget"),
                id="bottom-section",
            ),
            id="main-container",
        )

    def on_mount(self) -> None:
        # Thiết lập timer tự động cập nhật trạng thái
        self.set_interval(self.refresh_interval, self.refresh_state)

    def refresh_state(self) -> None:
        try:
            snap = self.state_reader.snapshot(
                run_id=self.run_id,
                event_category=self.current_event_filter,
            )
            self.snapshot_data = snap

            header = self.query_one("#header-widget", HeaderWidget)
            header.update_mission(snap.mission)

            lead = self.query_one("#lead-widget", ClaudeLeadWidget)
            lead.update_lead(snap.claude_lead)

            dag = self.query_one("#dag-widget", TaskDagWidget)
            dag.update_tasks(snap.tasks)

            wp = self.query_one("#worker-widget", WorkerPanelWidget)
            wp.update_workers(snap.workers)

            # Cập nhật task được chọn nếu còn tồn tại
            if self.selected_task:
                updated_t = next((t for t in snap.tasks if t.id == self.selected_task.id), None)
                if updated_t:
                    self.selected_task = updated_t
            elif snap.tasks:
                self.selected_task = snap.tasks[0]

            detail_w = self.query_one("#detail-widget", SelectedTaskWidget)
            detail_w.update_task(self.selected_task)

            events_w = self.query_one("#events-widget", EventsWidget)
            events_w.update_events(snap.events, self.current_event_filter)

            # Lỗi do TẦNG ĐỌC ghi nhận (vd dò fabric hỏng) vẫn phải hiện ra,
            # ngay cả khi khung hình này vẽ thành công.
            self._bao_loi(snap.errors, nguon=snap.worker_source)

        except Exception as exc:                          # noqa: BLE001
            # GIỮ TUI SỐNG, nhưng KHÔNG BAO GIỜ im lặng.
            #
            # Bản trước là `except Exception as e: pass`. Hậu quả thật: bảng
            # điều khiển tiếp tục vẽ SỐ LIỆU CŨ của khung hình trước và
            # trông hoàn toàn bình thường, trong khi việc đọc trạng thái đã
            # hỏng từ lâu. Người vận hành ra quyết định dựa trên số liệu
            # chết mà không có một dấu hiệu nào. Một bảng điều khiển nói
            # "KHÔNG ĐỌC ĐƯỢC" hữu ích hơn nhiều một bảng nói dối.
            #
            # Thông điệp đi qua `redact()` trước khi tới màn hình: một
            # traceback có thể mang đường dẫn hoặc chuỗi giống credential.
            self._doc_that_bai += 1
            from scripts.router_v3.packet import redact
            self._loi_gan_nhat = redact(
                f"{type(exc).__name__}: {exc}")[:160]
            try:
                self._bao_loi([self._loi_gan_nhat], nguon="")
            except Exception:                             # noqa: BLE001
                # Ngay cả đường BÁO LỖI cũng không được làm sập TUI — nhưng
                # nó cũng KHÔNG được im lặng. Một `pass` trơn ở đây nghĩa là
                # "đọc hỏng VÀ không báo được" trở thành vô hình, tức đúng
                # cái chế độ hỏng mà cả khối này tồn tại để chặn. Đếm lại để
                # bài kiểm bất biến "không nuốt Exception" đúng tuyệt đối và
                # để người vận hành thấy con số leo lên.
                self._bao_loi_that_bai += 1

    def _bao_loi(self, loi: list, *, nguon: str) -> None:
        """Đưa chỉ báo lỗi/nguồn dữ liệu lên thanh trạng thái.

        Đây là toàn bộ "chỉ báo" mà yêu cầu #5 nói tới: không popup, không
        chặn, chỉ một dòng luôn nhìn thấy được cho biết dữ liệu đang đọc
        được hay không và đến từ đâu.
        """
        sb = self.query_one("#status-widget", StatusBarWidget)
        sb.set_health(errors=list(loi or []),
                      failures=self._doc_that_bai,
                      source=nguon,
                      last_error=self._loi_gan_nhat)

    def on_task_dag_widget_task_selected(self, event: TaskDagWidget.TaskSelected) -> None:
        self.selected_task = event.task
        detail_w = self.query_one("#detail-widget", SelectedTaskWidget)
        detail_w.update_task(self.selected_task)

    def on_worker_panel_widget_worker_selected(self, event: WorkerPanelWidget.WorkerSelected) -> None:
        self.selected_worker = event.worker

    def action_show_detail(self) -> None:
        dag_w = self.query_one("#dag-widget", TaskDagWidget)
        task = dag_w.get_selected_task() or self.selected_task
        if task:
            self.push_screen(TaskDetailModal(task))

    def action_explain_routing(self) -> None:
        dag_w = self.query_one("#dag-widget", TaskDagWidget)
        task = dag_w.get_selected_task() or self.selected_task
        if task:
            exp = self.controller.explain_task(task.id, run_id=self.run_id)
            self.push_screen(ExplainModal(exp))

    def action_show_logs(self) -> None:
        dag_w = self.query_one("#dag-widget", TaskDagWidget)
        task = dag_w.get_selected_task() or self.selected_task
        task_id = task.id if task else "daemon"
        log_txt = self.controller.get_task_log(task_id)
        self.push_screen(LogViewModal(task_id, log_txt))

    def action_show_worktrees(self) -> None:
        wts = self.state_reader.get_worktrees()
        self.push_screen(WorktreeModal(wts))

    def action_cycle_filter(self) -> None:
        events_w = self.query_one("#events-widget", EventsWidget)
        self.current_event_filter = events_w.cycle_category()
        self.refresh_state()

    def action_drain_worker(self) -> None:
        wp = self.query_one("#worker-widget", WorkerPanelWidget)
        worker = wp.get_selected_worker() or self.selected_worker
        if not worker:
            self.notify("Vui lòng chọn một worker để drain", severity="warning")
            return

        def _on_confirm(yes: bool) -> None:
            if yes:
                res = self.controller.drain_worker(worker.id)
                if res.success:
                    self.notify(res.message, severity="information")
                    self.refresh_state()
                else:
                    self.notify(res.message, severity="error")

        self.push_screen(
            ConfirmModal(
                "XÁC NHẬN DRAIN WORKER",
                f"Bạn có chắc muốn drain worker [{worker.id}] không?\nWorker sẽ dừng nhận việc mới.",
            ),
            _on_confirm,
        )

    def action_retry_task(self) -> None:
        dag_w = self.query_one("#dag-widget", TaskDagWidget)
        task = dag_w.get_selected_task() or self.selected_task
        if not task:
            self.notify("Vui lòng chọn một task để retry", severity="warning")
            return

        def _on_confirm(yes: bool) -> None:
            if yes:
                res = self.controller.retry_task(task.id, run_id=self.run_id)
                if res.success:
                    self.notify(res.message, severity="information")
                    self.refresh_state()
                else:
                    self.notify(res.message, severity="error")

        self.push_screen(
            ConfirmModal(
                "XÁC NHẬN RETRY TASK",
                f"Bạn có chắc muốn đưa task [{task.id}] vào hàng đợi thử lại không?",
            ),
            _on_confirm,
        )

    def action_toggle_pause(self) -> None:
        if not self.snapshot_data or not self.snapshot_data.mission.run_id:
            self.notify("Không có mission đang hoạt động", severity="warning")
            return

        is_paused = self.snapshot_data.mission.status == "PAUSED"
        action_name = "tiếp tục" if is_paused else "tạm dừng"

        def _on_confirm(yes: bool) -> None:
            if yes:
                if is_paused:
                    res = self.controller.resume_mission(run_id=self.run_id)
                else:
                    res = self.controller.pause_mission(run_id=self.run_id)
                if res.success:
                    self.notify(res.message, severity="information")
                    self.refresh_state()
                else:
                    self.notify(res.message, severity="error")

        self.push_screen(
            ConfirmModal(
                f"XÁC NHẬN {action_name.upper()} MISSION",
                f"Bạn có chắc muốn {action_name} mission [{self.snapshot_data.mission.run_id}] không?",
            ),
            _on_confirm,
        )

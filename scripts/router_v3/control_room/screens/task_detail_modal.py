"""Màn hình chi tiết toàn diện công việc — Router V4 Control Room."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from scripts.router_v3.control_room.state_reader import TaskDetailView


class TaskDetailModal(ModalScreen):
    """Cửa sổ pop-up hiển thị đầy đủ thông số, phạm vi và kết quả của một task."""

    DEFAULT_CSS = """
    TaskDetailModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #detail-dialog {
        width: 85%;
        max-width: 110;
        height: 80%;
        background: #1a1b26;
        border: thick #9ece6a;
        padding: 1 2;
    }
    #detail-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    #detail-footer {
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Đóng"),
        Binding("q", "dismiss", "Đóng"),
        Binding("enter", "dismiss", "Đóng"),
    ]

    def __init__(self, task: TaskDetailView, **kwargs):
        super().__init__(**kwargs)
        self.task = task

    def compose(self) -> ComposeResult:
        yield Container(
            VerticalScroll(Static(id="detail-body"), id="detail-content"),
            Container(Button("Đóng (Esc/Enter)", variant="primary", id="close-btn"), id="detail-footer"),
            id="detail-dialog",
        )

    def on_mount(self) -> None:
        t = self.task
        table = Table.grid(padding=(1, 2))
        table.add_column(style="bold cyan", width=22)
        table.add_column(style="white")

        table.add_row("Task ID:", f"{t.id} (Trạng thái: {t.state.value})")
        table.add_row("Objective:", t.objective)
        table.add_row("Assigned Worker:", f"{t.worker_id or 'None'} (Model: {t.model or 'default'})")
        table.add_row("Dependencies:", ", ".join(t.dependencies) if t.dependencies else "(Root node)")
        table.add_row("Allowed Write Scope:", ", ".join(t.write_scope) if t.write_scope else "(Read-only)")
        table.add_row("Allowed Read Scope:", ", ".join(t.read_scope) if t.read_scope else "(Full read)")
        table.add_row("Required Capabilities:", ", ".join(t.required_capabilities) if t.required_capabilities else "any")
        table.add_row("Risk Class:", t.risk_class.upper())
        table.add_row("Attempt / Max:", f"{t.attempt} / {t.max_attempts}")
        table.add_row("Duration:", f"{t.elapsed_seconds:.1f}s")
        table.add_row("Tests Summary:", t.tests_summary)
        table.add_row("Artifacts Count:", str(t.artifacts_count))
        table.add_row("Log File Reference:", t.raw_log_ref)

        if t.failure_reason:
            table.add_row("Failure Reason:", Text(t.failure_reason, style="bold red"))

        body = self.query_one("#detail-body", Static)
        body.update(Panel(table, title=f"TASK SPECIFICATION: {t.id}", border_style="green"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()

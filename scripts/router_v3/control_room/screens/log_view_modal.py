"""Màn hình xem log tham chiếu an toàn — Router V4 Control Room."""
from __future__ import annotations

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class LogViewModal(ModalScreen):
    """Cửa sổ pop-up xem nhật ký log được lọc sạch bí mật."""

    DEFAULT_CSS = """
    LogViewModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #log-dialog {
        width: 90%;
        max-width: 130;
        height: 85%;
        background: #1a1b26;
        border: thick #e0af68;
        padding: 1 2;
    }
    #log-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    #log-footer {
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Đóng"),
        Binding("q", "dismiss", "Đóng"),
        Binding("l", "dismiss", "Đóng"),
    ]

    def __init__(self, task_id: str, log_content: str, **kwargs):
        super().__init__(**kwargs)
        self.task_id = task_id
        self.log_content = log_content

    def compose(self) -> ComposeResult:
        yield Container(
            VerticalScroll(Static(id="log-body"), id="log-content"),
            Container(Button("Đóng (Esc/L)", variant="primary", id="close-btn"), id="log-footer"),
            id="log-dialog",
        )

    def on_mount(self) -> None:
        body = self.query_one("#log-body", Static)
        body.update(Panel(Text(self.log_content, style="white"), title=f"TASK LOG: {self.task_id} (Đã lọc bí mật)", border_style="yellow"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()

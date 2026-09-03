"""Hộp thoại xác nhận an toàn trước hành động điều khiển — Router V4 Control Room."""
from __future__ import annotations

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """Cửa sổ xác nhận an toàn trước khi Drain, Pause hoặc Retry."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #confirm-dialog {
        width: 60;
        height: 14;
        background: #1a1b26;
        border: thick #f7768e;
        padding: 1 2;
    }
    #confirm-msg {
        height: 1fr;
        content-align: center middle;
    }
    #confirm-buttons {
        height: 3;
        align: center middle;
    }
    #btn-yes {
        margin-right: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Huỷ"),
        Binding("n", "cancel", "Không"),
        Binding("y", "confirm", "Có"),
    ]

    def __init__(self, title: str, message: str, **kwargs):
        super().__init__(**kwargs)
        self.dialog_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        yield Container(
            Static(Text(self.message, style="bold white"), id="confirm-msg"),
            Horizontal(
                Button("Có (Y)", variant="error", id="btn-yes"),
                Button("Huỷ (Esc/N)", variant="default", id="btn-no"),
                id="confirm-buttons",
            ),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

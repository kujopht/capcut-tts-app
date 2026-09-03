"""Màn hình danh sách worktree — Router V4 Control Room."""
from __future__ import annotations

from typing import Dict, List
from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class WorktreeModal(ModalScreen):
    """Cửa sổ pop-up hiển thị tất cả git worktree đang hoạt động."""

    DEFAULT_CSS = """
    WorktreeModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #wt-dialog {
        width: 85%;
        max-width: 110;
        height: 75%;
        background: #1a1b26;
        border: thick #bb9af7;
        padding: 1 2;
    }
    #wt-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    #wt-footer {
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Đóng"),
        Binding("q", "dismiss", "Đóng"),
        Binding("w", "dismiss", "Đóng"),
    ]

    def __init__(self, worktrees: List[Dict[str, str]], **kwargs):
        super().__init__(**kwargs)
        self.worktrees = worktrees

    def compose(self) -> ComposeResult:
        yield Container(
            VerticalScroll(Static(id="wt-body"), id="wt-content"),
            Container(Button("Đóng (Esc/W)", variant="primary", id="close-btn"), id="wt-footer"),
            id="wt-dialog",
        )

    def on_mount(self) -> None:
        table = Table(title="ACTIVE GIT WORKTREES", expand=True, border_style="magenta")
        table.add_column("Path", style="cyan")
        table.add_column("Branch", style="bold green", width=30)
        table.add_column("Base SHA", style="dim yellow", width=12)

        for wt in self.worktrees:
            table.add_row(wt.get("path", ""), wt.get("branch", ""), wt.get("sha", "")[:8])

        body = self.query_one("#wt-body", Static)
        body.update(table)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()

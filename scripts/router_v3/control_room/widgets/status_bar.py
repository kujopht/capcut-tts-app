"""Widget thanh trạng thái và phím tắt — Router V4 Control Room."""
from __future__ import annotations

from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget


class StatusBarWidget(Widget):
    """Thanh điều khiển nhanh dưới đáy màn hình."""

    DEFAULT_CSS = """
    StatusBarWidget {
        height: 1;
        dock: bottom;
        background: #1f2335;
        color: #c0caf5;
        padding: 0 1;
    }
    """

    def render(self) -> RenderResult:
        text = Text()
        bindings = [
            ("Enter", "detail"),
            ("E", "explain"),
            ("L", "logs"),
            ("D", "drain"),
            ("R", "retry"),
            ("P", "pause"),
            ("W", "worktrees"),
            ("F", "filter"),
            ("Tab", "focus"),
            ("Q", "quit"),
        ]
        for key, desc in bindings:
            text.append(f" {key} ", style="bold black on #7aa2f7")
            text.append(f" {desc}  ", style="white")
        return text

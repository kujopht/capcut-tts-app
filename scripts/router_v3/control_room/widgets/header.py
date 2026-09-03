"""Widget thanh tiêu đề — Router V4 Control Room."""
from __future__ import annotations

import time
from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget

from scripts.router_v3.control_room.state_reader import MissionView


def _format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    m = s // 60
    s = s % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


class HeaderWidget(Widget):
    """Thanh tiêu đề hiển thị tên mission, trạng thái và thời gian chạy."""

    DEFAULT_CSS = """
    HeaderWidget {
        height: 3;
        dock: top;
        background: $surface;
        color: $text;
        border-bottom: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, mission: MissionView, **kwargs):
        super().__init__(**kwargs)
        self.mission = mission

    def update_mission(self, mission: MissionView) -> None:
        self.mission = mission
        self.refresh()

    def render(self) -> RenderResult:
        m = self.mission
        text = Text()

        # Tiêu đề chính
        text.append("  FANFIC WORLD CONTROL ROOM  ", style="bold white on #1a1b26")
        text.append(" │ ", style="dim white")

        # Tên mission
        name_disp = (m.name[:35] + "...") if len(m.name) > 38 else m.name
        text.append("Mission: ", style="dim cyan")
        text.append(f"{name_disp:<38} ", style="bold cyan")

        # Trạng thái
        st = m.status
        st_style = "bold green" if st in ("RUNNING", "OK") else ("bold yellow" if st == "PAUSED" else "bold red")
        text.append(f" {st} ", style=f"{st_style} on #24283b")

        # Thời gian chạy
        text.append("  ⏱ ", style="dim yellow")
        text.append(_format_time(m.elapsed_seconds), style="bold yellow")

        # Tiến độ nút
        if m.total_tasks > 0:
            pct = int((m.completed_tasks / m.total_tasks) * 100)
            text.append(f"  [{m.completed_tasks}/{m.total_tasks} tasks ({pct}%)]", style="bold green")

        return text

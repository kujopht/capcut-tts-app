"""Widget dòng sự kiện điều phối — Router V4 Control Room."""
from __future__ import annotations

import datetime
from typing import List, Optional
from rich.panel import Panel
from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget

from scripts.router_v3.control_room.event_store import ControlRoomEvent, EventLevel


class EventsWidget(Widget):
    """Bảng hiển thị luồng sự kiện và cảnh báo trực tiếp từ Router."""

    DEFAULT_CSS = """
    EventsWidget {
        height: 8;
        border: solid #e0af68;
        background: #1a1b26;
        color: #c0caf5;
        padding: 0 1;
    }
    """

    CATEGORIES = ["ALL", "WARNINGS", "FAILURES", "ROUTING", "WORKERS"]

    def __init__(self, events: Optional[List[ControlRoomEvent]] = None, current_category: str = "ALL", **kwargs):
        super().__init__(**kwargs)
        self.events: List[ControlRoomEvent] = events or []
        self.category = current_category

    def update_events(self, events: List[ControlRoomEvent], category: Optional[str] = None) -> None:
        self.events = events
        if category:
            self.category = category
        self.refresh()

    def cycle_category(self) -> str:
        idx = self.CATEGORIES.index(self.category) if self.category in self.CATEGORIES else 0
        next_idx = (idx + 1) % len(self.CATEGORIES)
        self.category = self.CATEGORIES[next_idx]
        return self.category

    def render(self) -> RenderResult:
        cat_bar = " │ ".join(f"[{c}]" if c == self.category else c for c in self.CATEGORIES)
        title = f"EVENTS STREAM ({cat_bar}) [F to cycle filter]"

        if not self.events:
            return Panel(Text("  Chưa có sự kiện nào trong danh mục này.", style="dim italic white"), title=title, border_style="dim yellow")

        out = Text()
        # Hiển thị tối đa 5 sự kiện gần nhất
        recent = self.events[:5]
        for e in recent:
            t_str = datetime.datetime.fromtimestamp(e.ts).strftime("%H:%M:%S") if e.ts else "--:--:--"
            out.append(f"{t_str} ", style="dim yellow")

            # Kind & Worker
            kind_style = "bold red" if e.level in ("ERROR", "ALERT") else ("bold yellow" if e.level == "WARNING" else "cyan")
            out.append(f"{e.kind:<17} ", style=kind_style)

            if e.worker_id:
                out.append(f"[{e.worker_id}] ", style="bold magenta")
            elif e.task_id:
                out.append(f"[{e.task_id}] ", style="bold blue")

            # Detail
            detail_disp = e.detail[:65]
            out.append(f"{detail_disp}\n", style="white")

        return Panel(out, title=title, border_style="yellow")

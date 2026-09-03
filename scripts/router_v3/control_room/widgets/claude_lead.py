"""Widget Claude Lead — Router V4 Control Room."""
from __future__ import annotations

from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget

from scripts.router_v3.control_room.state_reader import ClaudeLeadView


class ClaudeLeadWidget(Widget):
    """Hiển thị trạng thái bộ điều phối Claude Lead."""

    DEFAULT_CSS = """
    ClaudeLeadWidget {
        height: 2;
        background: #16161e;
        color: #c0caf5;
        padding: 0 1;
        border-bottom: solid #414868;
    }
    """

    def __init__(self, lead: ClaudeLeadView, **kwargs):
        super().__init__(**kwargs)
        self.lead = lead

    def update_lead(self, lead: ClaudeLeadView) -> None:
        self.lead = lead
        self.refresh()

    def render(self) -> RenderResult:
        ld = self.lead
        text = Text()

        # Claude Lead header & Model
        text.append("👑 CLAUDE LEAD: ", style="bold #bb9af7")
        text.append(f"{ld.model} ", style="bold white")
        text.append("│ ", style="dim white")

        # State badge
        st = ld.state.upper()
        st_color = {
            "PLANNING": "cyan",
            "DELEGATING": "green",
            "WAITING_FOR_WORKERS": "yellow",
            "INTEGRATING": "magenta",
            "VERIFYING": "blue",
            "BLOCKED": "bold red",
            "COMPLETE": "bold green",
        }.get(st, "white")
        text.append("State: ", style="dim white")
        text.append(f"[{st}] ", style=f"bold {st_color}")
        text.append("│ ", style="dim white")

        # Branch
        text.append("Branch: ", style="dim white")
        text.append(f"{ld.branch} ", style="bold #7aa2f7")
        text.append("│ ", style="dim white")

        # Delegated / Running workers
        text.append(f"Delegated: {ld.delegated_count} ", style="white")
        text.append(f"Workers busy: {ld.running_workers} ", style="bold green" if ld.running_workers > 0 else "white")
        text.append("│ ", style="dim white")

        # Context usage
        text.append(f"Context: {ld.context_display} ", style="dim white" if ld.context_display == "UNKNOWN" else "bold yellow")

        # Warning
        if ld.heavy_work_warning:
            text.append(" ⚠ ORCHESTRATOR_HEAVY_WORK ", style="bold black on #f7768e")

        return text

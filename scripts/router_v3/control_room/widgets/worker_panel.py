"""Widget bảng Worker — Router V4 Control Room."""
from __future__ import annotations

from typing import List, Optional
from rich.text import Text
from textual.app import RenderResult
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from scripts.router_v3.control_room.state_reader import WorkerDetailView, WorkerState


class WorkerPanelWidget(OptionList):
    """Bảng hiển thị trạng thái và sức khoẻ tất cả worker trong bể."""

    DEFAULT_CSS = """
    WorkerPanelWidget {
        border: solid #2ac3de;
        background: #1a1b26;
        color: #c0caf5;
        height: 100%;
        scrollbar-size: 1 1;
    }
    WorkerPanelWidget:focus {
        border: double #7dcfff;
    }
    """

    class WorkerSelected(Message):
        def __init__(self, worker: WorkerDetailView):
            super().__init__()
            self.worker = worker

    def __init__(self, workers: Optional[List[WorkerDetailView]] = None, **kwargs):
        super().__init__(**kwargs)
        self.worker_items: List[WorkerDetailView] = workers or []
        self._sync_options()

    def update_workers(self, workers: List[WorkerDetailView]) -> None:
        curr_idx = self.highlighted if self.highlighted is not None else 0
        self.worker_items = workers
        self._sync_options()
        if self.worker_items:
            self.highlighted = min(curr_idx, len(self.worker_items) - 1)

    def _sync_options(self) -> None:
        self.clear_options()
        if not self.worker_items:
            self.add_option(Option(Text("  (Chưa có worker nào được nạp)", style="dim italic white")))
            return

        for w in self.worker_items:
            w_text = Text()

            # ID Worker
            w_text.append(f"{w.id:<11} ", style="bold white")

            # State badge
            st_color = {
                WorkerState.IDLE: "bold green",
                WorkerState.BUSY: "bold yellow on #24283b",
                WorkerState.COOLDOWN: "bold magenta",
                WorkerState.DEGRADED: "bold red",
                WorkerState.OFFLINE: "dim white",
                WorkerState.STARTING: "bold cyan",
            }.get(w.state, "white")
            w_text.append(f"{w.state.value:<9} ", style=st_color)

            # Model snippet
            model_short = w.model.replace("gemini-3.8-flash-", "gemini-").replace("claude-opus-4-6-", "opus-")
            model_disp = model_short[:14] if model_short else w.provider[:10]
            w_text.append(f"{model_disp:<14} ", style="cyan")

            # Task đang chạy nếu có
            if w.current_task:
                task_disp = w.current_task[:15]
                w_text.append(f"task:{task_disp} ", style="bold yellow")
            elif w.state == WorkerState.COOLDOWN:
                w_text.append("cooldown... ", style="dim magenta")
            else:
                w_text.append(f"rel:{w.reliability_pct:.0f}% ", style="dim green")

            # Quota
            if w.quota_display != "UNKNOWN":
                w_text.append(f"q:{w.quota_display} ", style="dim yellow")

            self.add_option(Option(w_text, id=w.id))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if 0 <= event.option_index < len(self.worker_items):
            self.post_message(self.WorkerSelected(self.worker_items[event.option_index]))

    def get_selected_worker(self) -> Optional[WorkerDetailView]:
        if self.highlighted is not None and 0 <= self.highlighted < len(self.worker_items):
            return self.worker_items[self.highlighted]
        if self.worker_items:
            return self.worker_items[0]
        return None

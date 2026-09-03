"""Widget danh sách DAG công việc — Router V4 Control Room."""
from __future__ import annotations

from typing import List, Optional
from rich.text import Text
from textual.app import RenderResult
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from scripts.router_v3.control_room.state_reader import TaskDetailView, TaskState


class TaskDagWidget(OptionList):
    """Bảng hiển thị cây DAG công việc với biểu tượng trạng thái trực quan."""

    DEFAULT_CSS = """
    TaskDagWidget {
        border: solid #7aa2f7;
        background: #1a1b26;
        color: #c0caf5;
        height: 100%;
        scrollbar-size: 1 1;
    }
    TaskDagWidget:focus {
        border: double #bb9af7;
    }
    """

    class TaskSelected(Message):
        """Sự kiện phát ra khi người dùng chọn một task."""

        def __init__(self, task: TaskDetailView):
            super().__init__()
            self.task = task

    def __init__(self, tasks: Optional[List[TaskDetailView]] = None, **kwargs):
        super().__init__(**kwargs)
        self.task_items: List[TaskDetailView] = tasks or []
        self._sync_options()

    @property
    def tasks(self) -> List[TaskDetailView]:
        return self.task_items

    def update_tasks(self, tasks: List[TaskDetailView]) -> None:
        current_idx = self.highlighted if self.highlighted is not None else 0
        self.task_items = tasks
        self._sync_options()
        if self.task_items:
            self.highlighted = min(current_idx, len(self.task_items) - 1)

    def _sync_options(self) -> None:
        self.clear_options()
        if not self.task_items:
            self.add_option(Option(Text("  (Chưa có công việc nào trong DAG)", style="dim italic white")))
            return

        for idx, t in enumerate(self.task_items):
            t_text = Text()

            # Phân cấp thụt lề cây
            indent = "  " * t.node_depth
            prefix = ""
            if t.node_depth > 0:
                prefix = "├─ " if idx < len(self.task_items) - 1 else "└─ "

            # Biểu tượng trạng thái theo đặc tả
            icon = t.state.icon
            icon_style = {
                TaskState.WAITING: "dim white",
                TaskState.READY: "bold yellow",
                TaskState.RUNNING: "bold cyan",
                TaskState.PASS: "bold green",
                TaskState.FAILED: "bold red",
                TaskState.RETRY: "bold magenta",
                TaskState.BLOCKED: "bold yellow on red",
            }.get(t.state, "white")

            t_text.append(f"{indent}{prefix}")
            t_text.append(f"{icon} ", style=icon_style)
            t_text.append(f"{t.id:<20} ", style="bold white")

            # Worker & Model nếu có
            if t.worker_id:
                t_text.append(f"[{t.worker_id}] ", style="dim cyan")

            # Mục tiêu vắn tắt
            obj_disp = t.objective[:28] + ("..." if len(t.objective) > 28 else "")
            t_text.append(f"{obj_disp} ", style="dim white")

            # Thời gian chạy nếu đang chạy
            if t.state == TaskState.RUNNING and t.elapsed_seconds > 0:
                t_text.append(f"⏱{int(t.elapsed_seconds)}s", style="bold yellow")

            self.add_option(Option(t_text, id=t.id))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if 0 <= event.option_index < len(self.task_items):
            self.post_message(self.TaskSelected(self.task_items[event.option_index]))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if 0 <= event.option_index < len(self.task_items):
            self.post_message(self.TaskSelected(self.task_items[event.option_index]))

    def get_selected_task(self) -> Optional[TaskDetailView]:
        if self.highlighted is not None and 0 <= self.highlighted < len(self.task_items):
            return self.task_items[self.highlighted]
        if self.task_items:
            return self.task_items[0]
        return None

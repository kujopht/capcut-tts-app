"""Widget hiển thị chi tiết nút công việc được chọn — Router V4 Control Room."""
from __future__ import annotations

from typing import Optional
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget

from scripts.router_v3.control_room.state_reader import TaskDetailView


class SelectedTaskWidget(Widget):
    """Hiển thị chi tiết mục tiêu, phạm vi và kết quả của task đang được chọn."""

    DEFAULT_CSS = """
    SelectedTaskWidget {
        height: 8;
        border: solid #9ece6a;
        background: #1a1b26;
        color: #c0caf5;
        padding: 0 1;
    }
    """

    def __init__(self, task: Optional[TaskDetailView] = None, **kwargs):
        super().__init__(**kwargs)
        self.task_detail = task

    def update_task(self, task: Optional[TaskDetailView]) -> None:
        self.task_detail = task
        self.refresh()

    def render(self) -> RenderResult:
        if not self.task_detail:
            return Panel(Text("Chọn một công việc trên cây DAG để xem thông số chi tiết.", style="dim italic white"), title="SELECTED TASK", border_style="dim green")

        t = self.task_detail
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", width=18)
        table.add_column(style="white")
        table.add_column(style="bold cyan", width=18)
        table.add_column(style="white")

        # Hàng 1: Worker/Model & Elapsed/Attempt
        w_info = f"{t.worker_id} ({t.model or 'default'})" if t.worker_id else "Chưa gán (Pending)"
        dur_str = f"{int(t.elapsed_seconds // 60):02d}:{int(t.elapsed_seconds % 60):02d}"
        table.add_row("Worker / Model:", w_info, "Elapsed / Attempt:", f"{dur_str} (lượt {t.attempt}/{t.max_attempts})")

        # Hàng 2: Objective & Tests/Artifacts
        obj_disp = t.objective[:55] + ("..." if len(t.objective) > 55 else "")
        table.add_row("Objective:", obj_disp, "Tests / Artifacts:", f"{t.tests_summary} │ {t.artifacts_count} artifacts")

        # Hàng 3: Phạm vi ghi & Rủi ro
        scope_str = ", ".join(t.write_scope) if t.write_scope else "Chỉ đọc (Read-only)"
        table.add_row("Write Scope:", scope_str[:45], "Risk / Caps:", f"{t.risk_class.upper()} │ {', '.join(t.required_capabilities) or 'any'}")

        # Hàng 4: Lỗi nếu có hoặc log ref
        if t.failure_reason:
            table.add_row("Failure Reason:", Text(t.failure_reason[:50], style="bold red"), "Log Ref:", t.raw_log_ref)
        else:
            deps_str = ", ".join(t.dependencies) if t.dependencies else "Không phụ thuộc (Root)"
            table.add_row("Dependencies:", deps_str[:50], "Log Ref:", t.raw_log_ref)

        return Panel(table, title=f"SELECTED TASK: {t.id} [{t.state.value}]", border_style="green")

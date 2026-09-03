"""Màn hình giải thích quyết định định tuyến — Router V4 Control Room."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from scripts.router_v3.control_room.state_reader import RoutingExplainView


class ExplainModal(ModalScreen):
    """Cửa sổ pop-up giải thích chi tiết điểm số và rào cản định tuyến."""

    DEFAULT_CSS = """
    ExplainModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #explain-dialog {
        width: 85%;
        max-width: 120;
        height: 80%;
        background: #1a1b26;
        border: thick #7aa2f7;
        padding: 1 2;
    }
    #explain-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    #explain-footer {
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Đóng"),
        Binding("q", "dismiss", "Đóng"),
        Binding("enter", "dismiss", "Đóng"),
    ]

    def __init__(self, explain_data: RoutingExplainView, **kwargs):
        super().__init__(**kwargs)
        self.data = explain_data

    def compose(self) -> ComposeResult:
        yield Container(
            VerticalScroll(Static(id="explain-body"), id="explain-content"),
            Container(Button("Đóng (Esc/Enter)", variant="primary", id="close-btn"), id="explain-footer"),
            id="explain-dialog",
        )

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        d = self.data
        table = Table(title=f"ROUTING EXPLAIN: {d.task_id}", expand=True, border_style="cyan")
        table.add_column("Worker", style="bold white", width=14)
        table.add_column("Status", width=12)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Capability", justify="right", width=10)
        table.add_column("Latency", justify="right", width=9)
        table.add_column("Quota", justify="right", width=8)
        table.add_column("Pref", justify="right", width=6)
        table.add_column("Details / Reason", style="dim white")

        for c in d.candidates:
            if c.excluded:
                table.add_row(
                    c.worker_id,
                    Text("EXCLUDED", style="bold red"),
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    Text(c.exclusion_reason or "Rào an toàn loại bỏ", style="red"),
                )
            else:
                st_text = Text("SELECTED ★", style="bold green") if c.selected else Text("ELIGIBLE", style="green")
                score_style = "bold green" if c.selected else "white"
                table.add_row(
                    c.worker_id,
                    st_text,
                    Text(f"{c.total_score:.1f}", style=score_style),
                    f"{c.dimensions.get('capability_fit', 0.0):.1f}",
                    f"{c.dimensions.get('expected_latency', 0.0):.1f}",
                    f"{c.dimensions.get('quota_remaining', 0.0):.1f}",
                    f"{c.dimensions.get('provider_preference', 0.0):.1f}",
                    "Fallback Candidate" if c.worker_id == d.fallback_candidate else "",
                )

        summary_text = Text()
        summary_text.append(f"\nObjective : {d.objective}\n", style="bold cyan")
        summary_text.append(f"Required  : {', '.join(d.required_capabilities) or 'None'}\n", style="white")
        summary_text.append(f"Risk Class: {d.risk_class.upper()}  │  ", style="yellow")
        summary_text.append(f"Selected Worker: {d.selected_worker or 'None'}  │  ", style="bold green")
        summary_text.append(f"Fallback: {d.fallback_candidate or 'None'}\n\n", style="dim cyan")

        body_widget = self.query_one("#explain-body", Static)
        body_widget.update(Panel(summary_text, border_style="dim white", subtitle="Quyết định định tuyến hoàn toàn giải thích được (Explainable)"))
        body_widget.update(table)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()

"""Widgets package for Fanfic Control Room."""
from scripts.router_v3.control_room.widgets.header import HeaderWidget
from scripts.router_v3.control_room.widgets.claude_lead import ClaudeLeadWidget
from scripts.router_v3.control_room.widgets.task_dag import TaskDagWidget
from scripts.router_v3.control_room.widgets.worker_panel import WorkerPanelWidget
from scripts.router_v3.control_room.widgets.task_detail import SelectedTaskWidget
from scripts.router_v3.control_room.widgets.events_panel import EventsWidget
from scripts.router_v3.control_room.widgets.status_bar import StatusBarWidget

__all__ = [
    "HeaderWidget",
    "ClaudeLeadWidget",
    "TaskDagWidget",
    "WorkerPanelWidget",
    "SelectedTaskWidget",
    "EventsWidget",
    "StatusBarWidget",
]

import threading
from typing import Dict, Sequence

from server.scraper.harvest_state import ErrorCategory, HarvestState, ItemProgress
from server.scraper.run_state import ScrapeItemStatus


class HarvestTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transitions: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}

    def record_transition(self, tu: HarvestState, den: HarvestState) -> None:
        # PHAI la dung enum, khong duoc chap nhan str: neu ai do vo tinh
        # truyen thang mot chuoi diagnostic hay item_id vao day thay vi
        # HarvestState, no se bi ghi thang vao telemetry — dung ep kieu de
        # chan tu goc, khong dua vao ky luat cua nguoi goi.
        if not isinstance(tu, HarvestState) or not isinstance(den, HarvestState):
            raise TypeError(
                "record_transition chi nhan HarvestState, khong nhan str — "
                "truyen thang van ban se ro ri item_id/diagnostic vao telemetry")
        key = f"{tu.value}->{den.value}"
        with self._lock:
            self._transitions[key] = self._transitions.get(key, 0) + 1

    def record_error(self, category: ErrorCategory) -> None:
        if not isinstance(category, ErrorCategory):
            raise TypeError(
                "record_error chi nhan ErrorCategory, khong nhan str — "
                "truyen thang van ban se ro ri diagnostic vao telemetry")
        with self._lock:
            self._errors[category.value] = self._errors.get(category.value, 0) + 1

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {
                "transitions": dict(self._transitions),
                "errors": dict(self._errors),
            }

    def reset(self) -> None:
        with self._lock:
            self._transitions.clear()
            self._errors.clear()


def summarize_run(items: Sequence[ItemProgress]) -> Dict[str, Dict[str, int]]:
    states: Dict[str, int] = {}
    persisted: Dict[str, int] = {}
    errors: Dict[str, int] = {}

    for item in items:
        # `.value` khong co fallback str(): ItemProgress.state/error_category
        # LA enum theo hop dong cua chinh dataclass do (xem harvest_state.py)
        # — mot fallback str() se am tham chap nhan va ro ri bat cu thu gi
        # neu hop dong do bi vi pham o dau khac.
        states[item.state.value] = states.get(item.state.value, 0) + 1
        persisted[item.persisted.value] = persisted.get(item.persisted.value, 0) + 1
        errors[item.error_category.value] = errors.get(item.error_category.value, 0) + 1

    return {
        "states": states,
        "persisted": persisted,
        "errors": errors,
    }

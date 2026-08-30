import threading
from typing import Dict, Sequence, Union

from server.scraper.harvest_state import ErrorCategory, HarvestState, ItemProgress
from server.scraper.run_state import ScrapeItemStatus


class HarvestTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transitions: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}

    def record_transition(
        self,
        tu: Union[HarvestState, str],
        den: Union[HarvestState, str],
    ) -> None:
        tu_val = tu.value if hasattr(tu, "value") else str(tu)
        den_val = den.value if hasattr(den, "value") else str(den)
        key = f"{tu_val}->{den_val}"

        with self._lock:
            self._transitions[key] = self._transitions.get(key, 0) + 1

    def record_error(self, category: Union[ErrorCategory, str]) -> None:
        cat_val = category.value if hasattr(category, "value") else str(category)
        with self._lock:
            self._errors[cat_val] = self._errors.get(cat_val, 0) + 1

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
        st = item.state.value if hasattr(item.state, "value") else str(item.state)
        states[st] = states.get(st, 0) + 1

        ps = item.persisted.value if hasattr(item.persisted, "value") else str(item.persisted)
        persisted[ps] = persisted.get(ps, 0) + 1

        err = item.error_category.value if hasattr(item.error_category, "value") else str(item.error_category)
        errors[err] = errors.get(err, 0) + 1

    return {
        "states": states,
        "persisted": persisted,
        "errors": errors,
    }

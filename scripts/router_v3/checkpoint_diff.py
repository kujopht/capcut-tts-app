from typing import Any, Dict, List


def diff(a: Any, b: Any) -> Dict[str, List[str]]:
    """Compare two Checkpoint objects (scripts.router_v3.checkpoint.Checkpoint).
    Returns {"newly_ok": [node_id...], "newly_failed": [node_id...],
    "still_pending": [node_id...]} comparing b against a: a node is
    "newly_ok" if its status in b is "ok" but was NOT "ok" in a (or absent
    from a). "newly_failed" analogously for any non-ok status that changed
    from "ok" or was newly introduced as failed/blocked. "still_pending" is
    any node_id present in b with status "pending" that was also pending
    or absent in a. Do not import anything beyond typing - keep it a pure
    function operating on .dag_state dicts (works on any object with a
    .dag_state attribute, so it doesn't need to import Checkpoint itself).
    """
    dag_a = getattr(a, "dag_state", {}) or {}
    dag_b = getattr(b, "dag_state", {}) or {}

    newly_ok = []
    newly_failed = []
    still_pending = []

    for node_id, status_b in dag_b.items():
        status_a = dag_a.get(node_id)
        if status_b == "ok":
            if status_a != "ok":
                newly_ok.append(node_id)
        elif status_b in ("failed", "blocked") or (status_a == "ok" and status_b != "ok"):
            if status_a == "ok" or status_a is None or (status_a != status_b and status_a not in ("failed", "blocked")):
                newly_failed.append(node_id)
        elif status_b == "pending":
            if status_a == "pending" or status_a is None:
                still_pending.append(node_id)

    return {
        "newly_ok": newly_ok,
        "newly_failed": newly_failed,
        "still_pending": still_pending,
    }

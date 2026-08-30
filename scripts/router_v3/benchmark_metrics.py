"""Utilization and coordination metrics for AI Router LTS benchmarks.

Given each worker's own task duration and the observed wall-clock time of a
concurrent batch, `compute` reports per-worker utilization, mean utilization,
coordination overhead (wall time beyond the slowest worker), and speedup
(sum of individual times over wall time).
"""


def compute(individual_seconds: dict, wall_seconds: float) -> dict:
    if not individual_seconds or wall_seconds == 0:
        return {
            "utilization": {wid: 0.0 for wid in individual_seconds},
            "average_utilization": 0.0,
            "coordination_overhead_seconds": 0.0,
            "speedup": 0.0,
        }

    utilization = {
        worker_id: duration / wall_seconds
        for worker_id, duration in individual_seconds.items()
    }
    values = list(utilization.values())
    return {
        "utilization": utilization,
        "average_utilization": sum(values) / len(values),
        "coordination_overhead_seconds": (
            wall_seconds - max(individual_seconds.values())
        ),
        "speedup": sum(individual_seconds.values()) / wall_seconds,
    }

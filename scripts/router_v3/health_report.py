def summarize(registry):
    """Take a scripts.router_v3.registry.WorkerRegistry. Returns a dict
    {"total": int, "by_health": {health_value: count}, "circuit_open_count": int}
    using registry.snapshot() (each row has "health" and "circuit_open"
    keys) - do not touch any private attributes, only the public
    snapshot()/ids() API.
    """
    rows = registry.snapshot()
    total = len(rows)
    by_health = {}
    circuit_open_count = 0
    for row in rows:
        h = row["health"]
        by_health[h] = by_health.get(h, 0) + 1
        if row.get("circuit_open"):
            circuit_open_count += 1
    return {
        "total": total,
        "by_health": by_health,
        "circuit_open_count": circuit_open_count,
    }

"""Đếm worker theo nhà cung cấp từ snapshot của WorkerRegistry."""


def count_by_provider(snapshot_rows):
    """snapshot_rows is a list of dicts like scripts.router_v3.registry.
    WorkerRegistry.snapshot() rows (each has a "provider" key). Return a
    dict mapping each distinct provider string to the count of rows with
    that provider. Pure function, standard library only.
    """
    counts = {}
    for row in snapshot_rows:
        provider = row["provider"]
        counts[provider] = counts.get(provider, 0) + 1
    return counts

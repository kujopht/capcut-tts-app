def rework_rate(records):
    """records is a list of dicts, each optionally having a
    "rework_required" key (bool). Return the fraction (float, 0.0-1.0) of
    records where record.get("rework_required") is truthy. Return 0.0 for
    an empty list. Pure function, standard library only.
    """
    if not records:
        return 0.0
    count = sum(1 for r in records if r.get("rework_required"))
    return count / len(records)

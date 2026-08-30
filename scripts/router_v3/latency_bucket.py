def bucket(seconds):
    """Given a duration in seconds (float or int), return "fast" if
    seconds < 30, "normal" if 30 <= seconds < 120, otherwise "slow". Pure
    function, standard library only.
    """
    if seconds < 30:
        return "fast"
    if seconds < 120:
        return "normal"
    return "slow"

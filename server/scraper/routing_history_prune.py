import os
import tempfile
from pathlib import Path


def prune(path, max_lines=5000):
    """Keep only the last `max_lines` lines of a JSONL file at `path`
    (a pathlib.Path or str). Writes atomically via a temp file + os.replace
    so a crash mid-write never leaves a truncated/corrupt file. If the
    file has max_lines or fewer lines, or does not exist, does nothing and
    returns 0. Returns the number of lines removed."""
    p = Path(path)
    if not p.exists():
        return 0

    with p.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) <= max_lines:
        return 0

    kept = lines[-max_lines:]
    removed = len(lines) - max_lines

    fd, tmp_path = tempfile.mkstemp(
        dir=str(p.parent), prefix=p.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(kept)
        os.replace(tmp_path, p)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return removed

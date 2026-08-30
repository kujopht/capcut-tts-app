def format_markdown_table(rows):
    """rows is a list of dicts, each with keys "worker", "task", "seconds".
    Return a GitHub-flavored Markdown table as a single string with header
    row "| Worker | Task | Time |" then a separator row, then one row per
    entry formatted as "| {worker} | {task} | {seconds:.2f}s |". Pure
    function, standard library only, no imports beyond typing if needed.
    """
    lines = [
        "| Worker | Task | Time |",
        "| --- | --- | --- |"
    ]
    for r in rows:
        lines.append(f"| {r['worker']} | {r['task']} | {float(r['seconds']):.2f}s |")
    return "\n".join(lines)

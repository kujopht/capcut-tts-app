"""THE AGPL BOUNDARY (mission requirement 6: "OpenMontage remains an
isolated worker/subprocess boundary. Do not copy AGPL code into Fanfic
World core."). This module NEVER imports any OpenMontage Python module.
It only shells out to the already-built Remotion CLI (`remotion.cmd
render ...`) with a JSON props file - the "aggregate under Section 5"
integration path confirmed by this session's own real archaeology of
OpenMontage's AGPL-3.0 license text (subprocess + file-based interchange,
no in-process dynamic linking).

Automates two real, previously-MANUAL Windows fixes discovered across
this session's earlier missions:
1. Windows MAX_PATH (260 char) limit breaking Chrome Headless Shell's
   spawn from deep temp paths - worked around with `subst` (a virtual
   drive letter), applied/removed automatically per render instead of by
   hand.
2. Chromium blocking `file://` asset loads from an `http://`-served
   render page - worked around by copying assets into the composer's
   `public/` folder (relative paths) instead of passing absolute paths,
   done automatically here instead of by hand per mission.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

OPENMONTAGE_REMOTION_DIR = Path(
    r"C:\Users\nguye\AppData\Local\Temp\claude\C--Users-nguye-Documents-CapCut-TTS-App"
    r"\9f89efae-a482-4002-af29-02601ce86985\scratchpad\openmontage-eval\OpenMontage\remotion-composer"
)


def _run_bat(script: str) -> None:
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False) as f:
        f.write(script)
        path = f.name
    subprocess.run([path], shell=False, check=False, capture_output=True)


def render_scene_video(*, props_json_path: str, output_mp4_path: str,
                        asset_files: list[str], asset_subfolder: str,
                        drive_letter: str = "O:", timeout_seconds: int = 900) -> dict:
    """Renders one AnimeScene/Explainer composition via the Remotion CLI
    subprocess. `asset_files` are copied into the composer's public/
    folder under `asset_subfolder` first (fix #2); the whole render runs
    through a short `subst` drive letter (fix #1). Returns a dict with
    `ok`, `wall_seconds`, `log_tail`, `output_path`.
    """
    t0 = time.monotonic()

    # Fix #2: copy assets into public/<asset_subfolder>/ so props can use
    # relative paths (resolveAsset.ts falls back to staticFile() for these).
    public_dir = OPENMONTAGE_REMOTION_DIR / "public" / asset_subfolder
    public_dir.mkdir(parents=True, exist_ok=True)
    for f in asset_files:
        shutil.copy2(f, public_dir / Path(f).name)

    # Fix #1: subst the scratchpad root to a short drive letter for this render.
    scratchpad_root = OPENMONTAGE_REMOTION_DIR.parents[2]  # .../scratchpad
    drive = drive_letter.rstrip(":") + ":"
    _run_bat(f'@echo off\r\nsubst {drive} /d\r\n')
    _run_bat(f'@echo off\r\nsubst {drive} "{scratchpad_root}"\r\n')

    try:
        rel_remotion_dir = str(OPENMONTAGE_REMOTION_DIR).replace(str(scratchpad_root), drive, 1)
        rel_props = str(props_json_path).replace(str(scratchpad_root), drive, 1) \
            if str(scratchpad_root) in str(props_json_path) else props_json_path
        rel_output = str(output_mp4_path).replace(str(scratchpad_root), drive, 1) \
            if str(scratchpad_root) in str(output_mp4_path) else output_mp4_path

        remotion_bin = str(Path(rel_remotion_dir) / "node_modules" / ".bin" / "remotion.cmd")
        log_path = Path(output_mp4_path).with_suffix(".render.log")

        cmd = [remotion_bin, "render", "src/index.tsx", "Explainer", rel_output,
               "--props", rel_props, "--codec", "h264"]
        with open(log_path, "w", encoding="utf-8", errors="replace") as logf:
            result = subprocess.run(cmd, cwd=rel_remotion_dir, stdout=logf, stderr=subprocess.STDOUT,
                                     timeout=timeout_seconds, shell=False)

        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
        wall = time.monotonic() - t0
        ok = result.returncode == 0 and Path(output_mp4_path).is_file()
        return {"ok": ok, "wall_seconds": round(wall, 1), "log_tail": log_tail,
                "output_path": output_mp4_path if ok else None, "returncode": result.returncode}
    finally:
        _run_bat(f'@echo off\r\nsubst {drive} /d\r\n')

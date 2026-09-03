"""Storage: Drive cold archive + R2 hot copy + manifest/checksum/
provenance (mission requirement 7). Mirrors the real, established
`archive_final_render()` pattern in scripts/chinese_media_pipeline.py
(sha256 + R2 hot copy + Drive cold copy via rclone) - reusing the SAME
R2StorageAdapter and rclone_archive_copy.py this repo already has, not a
new storage path.

Deliberately DOES NOT call `PATCH /api/novels/{id}/media-processing` -
that ties a render to a real Novel record in the live production
database, which is a further real content-publishing action outside this
worker's scope (see worker.py's module docstring for the full boundary
rationale). This module's output is a self-contained manifest.json plus
the archived files; wiring that into a real Novel record is a deliberate,
separate step for whoever reviews DRAFT_READY output.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rclone_copy(local_dir: str, remote_path: str, *, timeout: int = 300) -> dict:
    """Direct call into the existing, real, copy-only rclone wrapper."""
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.rclone_archive_copy import rclone_copy as _copy, rclone_verify as _verify
    copy_result = _copy(local_dir, remote_path, timeout=timeout)
    verify_result = _verify(local_dir, remote_path, timeout=timeout)
    ok = copy_result["exit_code"] == 0 and verify_result["check_exit_code"] == 0
    return {"ok": ok, "copy": copy_result, "verify": verify_result}


def upload_to_r2(key: str, local_path: str, content_type: str = "video/mp4") -> dict:
    os.environ.setdefault("FAS_ENV_FILE", str(REPO_ROOT / "server" / ".env.production"))
    sys.path.insert(0, str(REPO_ROOT))
    from server.config import get_settings
    from server.r2_adapter import R2StorageAdapter

    settings = get_settings()
    adapter = R2StorageAdapter(settings.r2)
    adapter.put_file(key, local_path, content_type)
    exists = adapter.exists(key)
    size = adapter.size(key) if exists else None
    local_size = Path(local_path).stat().st_size
    return {"ok": exists and size == local_size, "key": key, "remote_size": size, "local_size": local_size}


def build_manifest(*, job_id: str, title: str, characters: dict, scenes: list,
                    render_path: str, qa_result: str, costs: list, retry_count: int,
                    drive_remote_path: Optional[str] = None, r2_key: Optional[str] = None) -> dict:
    return {
        "job_id": job_id,
        "title": title,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generation_method": "layered_composition",  # frozen per mission requirement 4
        "characters": {name: {"reference_seed": c.get("reference_seed")} for name, c in characters.items()},
        "scenes": scenes,
        "render_sha256": sha256_of(render_path),
        "render_size_bytes": Path(render_path).stat().st_size,
        "qa_result": qa_result,
        "total_cost_usd": round(sum(c["cost_usd"] for c in costs), 5),
        "retry_count": retry_count,
        "drive_path": drive_remote_path,
        "r2_key": r2_key,
    }


def archive_job(*, job_id: str, render_path: str, manifest: dict, extra_files: list[str],
                 drive_remote_base: str = "fanfic-gdrive:FanficWorld/archive/animation-worker") -> dict:
    """Archives the FINAL rendered video + manifest to Drive cold storage,
    and (only if qa_result == QA_PASS) delivers the video to R2 hot
    storage - matching mission requirement 7's conditional exactly."""
    import tempfile
    spool = Path(tempfile.mkdtemp(prefix=f"animworker_{job_id}_"))
    (spool / Path(render_path).name).write_bytes(Path(render_path).read_bytes())
    (spool / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    for f in extra_files:
        (spool / Path(f).name).write_bytes(Path(f).read_bytes())

    drive_remote = f"{drive_remote_base}/{job_id}"
    drive_result = rclone_copy(str(spool), drive_remote)

    r2_result = None
    if manifest["qa_result"] == "QA_PASS":
        r2_key = f"animation-worker/{job_id}/{Path(render_path).name}"
        r2_result = upload_to_r2(r2_key, render_path)

    return {"drive_remote_path": drive_remote, "drive_result": drive_result, "r2_result": r2_result}

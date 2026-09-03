"""Job/checkpoint persistence (mission requirement 5) - a self-contained
JSON store, deliberately NOT wired into the production Appwrite-backed
TtsJob queue (server/adapters.py::MetadataStore). That queue is shared,
live infrastructure serving real narration jobs; adding a new job TYPE to
it is a schema/ops change that deserves its own explicit review, not an
autonomous side-effect of this mission. This worker's own jobs are fully
independent, file-based, and safe to delete/ignore without touching
anything else in Content Factory.

Resume semantics: `load_or_create(job_id, factory)` returns an existing
job's state if a checkpoint file is present (mid-pipeline), otherwise
builds a fresh one via `factory()`. `save(job)` is called after every
completed stage - never mid-stage - so a resumed job re-enters at the
start of its last INCOMPLETE stage rather than re-doing completed work.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable

from .models import (AnimationJob, CharacterSpec, JobCostRecord, JobStage,
                      RetryRecord, SceneAssetState, SceneSpec)
from .occupancy_qa import FailureType

JOBS_DIR = Path(__file__).parent / "jobs"


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _to_dict(job: AnimationJob) -> dict:
    d = dataclasses.asdict(job)
    d["stage"] = job.stage.value
    for scene_id, sa in d["scene_assets"].items():
        for r in sa["retries"]:
            r["failure"] = r["failure"].value if isinstance(r["failure"], FailureType) else r["failure"]
    return d


def _from_dict(d: dict) -> AnimationJob:
    characters = {k: CharacterSpec(**v) for k, v in d["characters"].items()}
    scenes = [SceneSpec(**s) for s in d["scenes"]]
    scene_assets = {}
    for scene_id, sa in d.get("scene_assets", {}).items():
        retries = [RetryRecord(scene_id=r["scene_id"], layer=r["layer"], attempt=r["attempt"],
                                failure=FailureType(r["failure"]), detail=r["detail"],
                                timestamp=r["timestamp"]) for r in sa.get("retries", [])]
        scene_assets[scene_id] = SceneAssetState(
            scene_id=sa["scene_id"], background_path=sa.get("background_path"),
            character_layers=sa.get("character_layers", {}), composite_path=sa.get("composite_path"),
            retries=retries, ok=sa.get("ok", False))
    costs = [JobCostRecord(**c) for c in d.get("costs", [])]
    return AnimationJob(
        job_id=d["job_id"], novel_id=d["novel_id"], chapter_id=d["chapter_id"], title=d["title"],
        characters=characters, scenes=scenes, narration_audio_path=d["narration_audio_path"],
        captions_path=d.get("captions_path"), stage=JobStage(d["stage"]), scene_assets=scene_assets,
        render_path=d.get("render_path"), qa_result=d.get("qa_result"), drive_path=d.get("drive_path"),
        r2_key=d.get("r2_key"), manifest_path=d.get("manifest_path"), costs=costs,
        retry_count=d.get("retry_count", 0), created_at=d["created_at"], updated_at=d["updated_at"],
    )


def save(job: AnimationJob) -> None:
    import time
    job.updated_at = time.time()
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _job_path(job.job_id).write_text(json.dumps(_to_dict(job), indent=2, ensure_ascii=False), encoding="utf-8")


def load(job_id: str) -> AnimationJob | None:
    p = _job_path(job_id)
    if not p.exists():
        return None
    return _from_dict(json.loads(p.read_text(encoding="utf-8")))


def load_or_create(job_id: str, factory: Callable[[], AnimationJob]) -> AnimationJob:
    existing = load(job_id)
    if existing is not None:
        return existing
    job = factory()
    save(job)
    return job

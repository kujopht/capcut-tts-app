"""Builds the Explainer/AnimeScene Remotion props JSON for one job -
subtitles + existing narration audio + the composited scene stills
(mission requirement 1's "AnimeScene/Remotion motion -> existing
narration -> subtitles" stages). Reuses the exact prop schema validated
across all three preceding OpenMontage missions this session."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import AnimationJob

ANIMATIONS = ["zoom-in", "pan-right", "ken-burns", "zoom-in", "drift-down"]


def build_props(job: AnimationJob, composite_paths: List[str], out_path: Path) -> None:
    captions = []
    if job.captions_path:
        captions = json.loads(Path(job.captions_path).read_text(encoding="utf-8"))

    audio_name = Path(job.narration_audio_path).name
    asset_subfolder = f"animworker-{job.job_id}"

    cuts = []
    for i, (scene, composite_path) in enumerate(zip(job.scenes, composite_paths)):
        cuts.append({
            "id": scene.scene_id,
            "source": "",
            "type": "anime_scene",
            "in_seconds": scene.in_seconds,
            "out_seconds": scene.out_seconds,
            "images": [f"{asset_subfolder}/{Path(composite_path).name}"],
            "animation": scene.animation or ANIMATIONS[i % len(ANIMATIONS)],
            "backgroundColor": "#D8DCE0",
            "vignette": True,
            "lightingFrom": "#E8ECF0",
            "lightingTo": "#C8CCD0",
            "sceneDurationSeconds": scene.duration,
        })

    props = {
        "theme": "flat-motion-graphics",
        "cuts": cuts,
        "overlays": [],
        "captions": captions,
        "audio": {"narration": {"src": f"{asset_subfolder}/{audio_name}", "volume": 1.0}},
    }
    out_path.write_text(json.dumps(props, indent=2, ensure_ascii=False), encoding="utf-8")

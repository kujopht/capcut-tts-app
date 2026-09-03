"""Data model for the AnimationWorker pipeline - provider-neutral, no
OpenMontage/AGPL types imported anywhere in this module or package (the
AGPL boundary is a subprocess call to the Remotion CLI in remotion_render.py,
never a Python import - see that module's docstring)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .occupancy_qa import FailureType  # re-exported for convenience


class JobStage(str, Enum):
    """Resume checkpoints, in pipeline order (mission requirement 5)."""
    PENDING = "PENDING"
    REFERENCES = "REFERENCES"
    SCENE_ASSETS = "SCENE_ASSETS"
    COMPOSITE = "COMPOSITE"
    RENDER = "RENDER"
    QA = "QA"
    ARCHIVE = "ARCHIVE"
    DRAFT_READY = "DRAFT_READY"
    FAILED = "FAILED"


@dataclass
class CharacterSpec:
    """One entry of the character bible - hair/eyes/face/outfit/
    accessories/proportions/negative constraints, per mission requirement.
    `reference_path` is set once a canonical portrait exists and is reused
    across the whole job (never regenerated unless flagged defective)."""
    name: str
    hair: str
    eyes: str
    face_traits: str
    outfit: str
    accessories: str
    body_proportions: str
    negative_identity_constraints: str
    count_tag: str = "1boy"  # "1boy" | "1girl" - real bug fixed here: this was
    # hardcoded to "1boy" in every generation prompt regardless of the
    # character's actual gender, fighting the model's own name/description
    # cues for any female character (e.g. Sakura) instead of reinforcing them.
    reference_path: Optional[str] = None
    reference_seed: Optional[int] = None
    reference_proxy_cutout_path: Optional[str] = None  # chroma-keyed proxy of the
    # reference portrait, for adaptive (alpha-bbox-based) hair-region sampling
    # instead of a blind fixed-fraction crop - see verify_identity's real fix.


@dataclass
class SceneSpec:
    scene_id: str
    in_seconds: float
    out_seconds: float
    expected_characters: List[str]  # names, matching CharacterSpec.name
    mood: str
    composition_hint: str
    animation: str = "zoom-in"

    @property
    def duration(self) -> float:
        return self.out_seconds - self.in_seconds


@dataclass
class RetryRecord:
    scene_id: str
    layer: str  # "background" | character name
    attempt: int
    failure: FailureType
    detail: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SceneAssetState:
    scene_id: str
    background_path: Optional[str] = None
    character_layers: Dict[str, str] = field(default_factory=dict)  # name -> cutout path
    composite_path: Optional[str] = None
    retries: List[RetryRecord] = field(default_factory=list)
    ok: bool = False


@dataclass
class JobCostRecord:
    label: str
    cost_usd: float
    wall_seconds: float


@dataclass
class AnimationJob:
    job_id: str
    novel_id: str
    chapter_id: str
    title: str
    characters: Dict[str, CharacterSpec]
    scenes: List[SceneSpec]
    narration_audio_path: str
    captions_path: Optional[str] = None
    stage: JobStage = JobStage.PENDING
    scene_assets: Dict[str, SceneAssetState] = field(default_factory=dict)
    render_path: Optional[str] = None
    qa_result: Optional[str] = None  # "QA_PASS" | "QA_FAIL" - matches Novel.qa_state convention
    drive_path: Optional[str] = None
    r2_key: Optional[str] = None
    manifest_path: Optional[str] = None
    costs: List[JobCostRecord] = field(default_factory=list)
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c.cost_usd for c in self.costs), 5)

"""AnimationWorker - the productized, unattended pipeline (mission:
"turn OpenMontage layered proof into an unattended animation worker").

Pipeline (mission requirement 1):
  story/chapter -> adaptation -> scene plan -> character bible ->
  canonical character references -> background generation ->
  per-character generation -> deterministic layered compositing ->
  AnimeScene/Remotion motion -> existing narration -> subtitles ->
  deterministic QA -> /watch visual QA -> Drive cold archive ->
  R2 hot delivery -> DRAFT_READY

Scope boundary (deliberate, not an oversight): this worker produces a
QA_PASS rendered video + manifest, archived to Drive/R2. It does NOT
autonomously create or publish a real Novel/Chapter draft record in the
live production database (POST/PATCH /api/novels, PATCH .../media-
processing) - that is a further real content-publishing action on shared
production state, and this mission's own risk posture (isolated Beam
endpoint, no AGPL code in core, no writes to the shared TtsJob queue)
argues for leaving that hookup as an explicit, separate, reviewed step
rather than an autonomous side-effect. "DRAFT_READY" here is this
worker's own job-stage value (see models.JobStage), not a live database
write.

The generation method is FROZEN (mission requirement 4: never returns to
one-pass dual-character generation) - every character layer in this file
is generated SOLO, always through layering.composite_scene() for assembly.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from . import archive, checkpoint, layering, remotion_render
from .image_provider import BeamAnimagineProvider, ImageProvider
from .models import (AnimationJob, CharacterSpec, JobCostRecord, JobStage,
                      RetryRecord, SceneAssetState, SceneSpec)
from .occupancy_qa import FailureType, verify_identity, verify_solo_occupancy

MAX_RETRIES_PER_LAYER = 3
# Bumped from 2 after real batch-proof data (Job 3/Sakura): a name-loaded
# character with a strong competing visual association (cherry blossoms)
# had a higher real failure rate on the solid-backdrop requirement than
# Naruto/Sasuke did - a real, observed calibration, not a guess.
WORK_DIR = Path(__file__).parent / "work"


class RetryBudgetExceeded(RuntimeError):
    def __init__(self, scene_id: str, layer: str, failure: FailureType, detail: str):
        super().__init__(f"[{scene_id}/{layer}] {failure.value} after {MAX_RETRIES_PER_LAYER} retries: {detail}")
        self.scene_id = scene_id
        self.layer = layer
        self.failure = failure


class AnimationWorker:
    def __init__(self, provider: Optional[ImageProvider] = None):
        self.provider = provider or BeamAnimagineProvider()

    # ---- stage: canonical references -------------------------------------

    def ensure_references(self, job: AnimationJob) -> None:
        job_dir = WORK_DIR / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        for name, spec in job.characters.items():
            if spec.reference_path and Path(spec.reference_path).is_file():
                continue  # reuse existing reference unless defective (mission requirement 3)

            last_detail = ""
            for attempt in range(MAX_RETRIES_PER_LAYER + 1):
                prompt = (
                    f"anime character, solo, {spec.count_tag}, only one person in frame, {name}, "
                    f"{spec.hair}, {spec.eyes}, {spec.face_traits}, {spec.outfit}, {spec.accessories}, "
                    "simple neutral gray background, front-facing portrait, waist-up shot, "
                    "detailed anime digital painting, high quality, no text, no watermark"
                )
                negative = (f"multiple people, crowd, duplicate character, extra person, "
                            f"cropped body parts of another person, second person, "
                            f"text, watermark, low quality, {spec.negative_identity_constraints}")
                seed = abs(hash((job.job_id, name, "ref", attempt))) % 90000 + 10000
                result = self.provider.generate(prompt=prompt, negative_prompt=negative, seed=seed,
                                                  width=1024, height=1024)
                ref_path = job_dir / f"ref_{name}_attempt{attempt}.png"
                ref_path.write_bytes(result.png_bytes)
                job.costs.append(JobCostRecord(label=f"ref:{name}", cost_usd=result.cost_usd,
                                                wall_seconds=result.wall_seconds))

                # Real bug fixed here: reference portraits were never
                # occupancy-checked (only per-scene character LAYERS were),
                # letting a reference with a second person's limb intruding
                # into frame through undetected in this mission's own first
                # run. A reference portrait is opaque (no chroma-key alpha),
                # so occupancy is checked via a quick keyed proxy instead.
                proxy_cutout = job_dir / f"ref_{name}_attempt{attempt}_proxy.png"
                layering.chromakey_extract(ref_path, proxy_cutout)
                # Blob-COUNT only (catches a real second-person-in-frame
                # defect) - the fill-ratio checks are skipped here since
                # reference portraits are never meant to have a clean,
                # keyable solid backdrop (see occupancy_qa's own docstring).
                occ = verify_solo_occupancy(proxy_cutout, min_area_fraction=0.03,
                                              max_canvas_fill_fraction=None, min_bbox_fill_ratio=None)
                if occ.ok:
                    spec.reference_path = str(ref_path)
                    spec.reference_seed = result.seed
                    spec.reference_proxy_cutout_path = str(proxy_cutout)
                    checkpoint.save(job)
                    break
                last_detail = occ.detail
                checkpoint.save(job)
            else:
                raise RetryBudgetExceeded(job.job_id, f"reference:{name}", FailureType.EXTRA_PERSON, last_detail)
        job.stage = JobStage.SCENE_ASSETS
        checkpoint.save(job)

    # ---- stage: per-scene assets (background + characters), verified ------

    def _generate_verified_character(self, job: AnimationJob, scene: SceneSpec,
                                       char_name: str, job_dir: Path) -> str:
        spec = job.characters[char_name]
        sa = job.scene_assets[scene.scene_id]
        base_seed = abs(hash((job.job_id, scene.scene_id, char_name))) % 90000 + 10000

        for attempt in range(MAX_RETRIES_PER_LAYER + 1):
            prompt = (
                f"anime character, solo, {spec.count_tag}, only one person, full body, {char_name}, "
                f"{spec.hair}, {spec.eyes}, {spec.outfit}, {spec.accessories}, "
                f"{scene.composition_hint} scene mood: {scene.mood}, dynamic pose, "
                "solid pure green background, chroma key green screen, flat uniform green backdrop, "
                "no scenery, no props, detailed anime digital painting, high quality, no text, no watermark"
            )
            negative = (
                "multiple people, crowd, two people, duplicate character, cloned face, extra person, "
                "third person, text, watermark, low quality, scenery, buildings, "
                "gradient background, horizon, ground plane, floor, two-tone background, "
                "sky, landscape, multiple colors in background, "
                f"{spec.negative_identity_constraints}"
            )
            ref_bytes = Path(spec.reference_path).read_bytes()
            t0 = time.monotonic()
            try:
                result = self.provider.generate(prompt=prompt, negative_prompt=negative,
                                                  seed=base_seed + attempt, width=1024, height=1536,
                                                  reference_image_png=ref_bytes, reference_strength=0.5)
            except Exception as exc:
                sa.retries.append(RetryRecord(scene_id=scene.scene_id, layer=char_name, attempt=attempt,
                                               failure=FailureType.GENERATION_FAIL, detail=str(exc)))
                checkpoint.save(job)
                continue

            job.costs.append(JobCostRecord(label=f"{scene.scene_id}:{char_name}",
                                            cost_usd=result.cost_usd, wall_seconds=result.wall_seconds))
            # Per-attempt filenames (real bug fixed here: a fixed filename
            # per scene+character was overwritten by every retry, destroying
            # the diagnostic evidence for earlier failed attempts).
            raw_path = job_dir / f"{scene.scene_id}_{char_name}_attempt{attempt}_raw.png"
            raw_path.write_bytes(result.png_bytes)
            cutout_path = job_dir / f"{scene.scene_id}_{char_name}_attempt{attempt}_cutout.png"
            layering.chromakey_extract(raw_path, cutout_path)

            occ = verify_solo_occupancy(cutout_path)
            if not occ.ok:
                sa.retries.append(RetryRecord(scene_id=scene.scene_id, layer=char_name, attempt=attempt,
                                               failure=occ.failure, detail=occ.detail))
                checkpoint.save(job)
                continue

            ident = verify_identity(cutout_path, spec.reference_path,
                                      reference_proxy_cutout_path=spec.reference_proxy_cutout_path)
            if not ident.ok:
                sa.retries.append(RetryRecord(scene_id=scene.scene_id, layer=char_name, attempt=attempt,
                                               failure=ident.failure, detail=ident.detail))
                checkpoint.save(job)
                continue

            return str(cutout_path)

        last = sa.retries[-1]
        raise RetryBudgetExceeded(scene.scene_id, char_name, last.failure, last.detail)

    def _generate_background(self, job: AnimationJob, scene: SceneSpec, job_dir: Path) -> str:
        sa = job.scene_assets[scene.scene_id]
        base_seed = abs(hash((job.job_id, scene.scene_id, "bg"))) % 90000 + 10000
        prompt = (f"anime background art, empty street scene, {scene.mood} atmosphere, "
                  "environment plate, no people, no characters, no human figures, "
                  "detailed anime digital painting, high quality, no text, no watermark")
        negative = "person, people, boy, girl, human, character, figure, text, watermark, low quality"
        for attempt in range(MAX_RETRIES_PER_LAYER + 1):
            try:
                result = self.provider.generate(prompt=prompt, negative_prompt=negative,
                                                  seed=base_seed + attempt, width=1344, height=768)
            except Exception as exc:
                sa.retries.append(RetryRecord(scene_id=scene.scene_id, layer="background", attempt=attempt,
                                               failure=FailureType.GENERATION_FAIL, detail=str(exc)))
                checkpoint.save(job)
                continue
            job.costs.append(JobCostRecord(label=f"{scene.scene_id}:background",
                                            cost_usd=result.cost_usd, wall_seconds=result.wall_seconds))
            bg_path = job_dir / f"{scene.scene_id}_bg.png"
            bg_path.write_bytes(result.png_bytes)
            return str(bg_path)
        last = sa.retries[-1]
        raise RetryBudgetExceeded(scene.scene_id, "background", last.failure, last.detail)

    def build_scene_assets(self, job: AnimationJob) -> None:
        job_dir = WORK_DIR / job.job_id
        for scene in job.scenes:
            sa = job.scene_assets.setdefault(scene.scene_id, SceneAssetState(scene_id=scene.scene_id))
            if sa.ok:
                continue  # resume: skip already-completed scenes

            if not sa.background_path:
                sa.background_path = self._generate_background(job, scene, job_dir)
                checkpoint.save(job)

            for char_name in scene.expected_characters:
                if char_name in sa.character_layers:
                    continue
                sa.character_layers[char_name] = self._generate_verified_character(job, scene, char_name, job_dir)
                checkpoint.save(job)

            composite_path = job_dir / f"{scene.scene_id}_composite.png"
            try:
                layers = [(name, sa.character_layers[name]) for name in scene.expected_characters]
                layering.composite_scene(sa.background_path, layers, composite_path)
            except Exception as exc:
                sa.retries.append(RetryRecord(scene_id=scene.scene_id, layer="composite", attempt=0,
                                               failure=FailureType.COMPOSITION_FAIL, detail=str(exc)))
                checkpoint.save(job)
                raise
            sa.composite_path = str(composite_path)
            sa.ok = True
            checkpoint.save(job)

        job.stage = JobStage.COMPOSITE
        checkpoint.save(job)

    # ---- stage: render, QA, archive ---------------------------------------

    def render(self, job: AnimationJob, *, build_props_fn) -> None:
        job_dir = WORK_DIR / job.job_id
        props_path = job_dir / "props.json"
        output_path = job_dir / f"{job.job_id}.mp4"
        composite_paths = [job.scene_assets[s.scene_id].composite_path for s in job.scenes]
        build_props_fn(job, composite_paths, props_path)

        asset_files = composite_paths + [job.narration_audio_path]
        result = remotion_render.render_scene_video(
            props_json_path=str(props_path), output_mp4_path=str(output_path),
            asset_files=asset_files, asset_subfolder=f"animworker-{job.job_id}")
        if not result["ok"]:
            raise RuntimeError(f"Render failed (GENERATION_FAIL, render stage): {result['log_tail'][-800:]}")
        job.render_path = result["output_path"]
        job.stage = JobStage.QA
        checkpoint.save(job)

    def run_deterministic_qa(self, job: AnimationJob) -> bool:
        sys.path.insert(0, r"C:\Users\nguye\Documents\CapCut-TTS-App")
        from scripts.visual_media_qa import deterministic_checks
        result = deterministic_checks(Path(job.render_path))
        job.qa_result = "QA_PASS" if result.ok and not result.hard_fail else "QA_FAIL"
        checkpoint.save(job)
        return job.qa_result == "QA_PASS"

    def archive_and_deliver(self, job: AnimationJob) -> dict:
        manifest = archive.build_manifest(
            job_id=job.job_id, title=job.title,
            characters={n: {"reference_seed": c.reference_seed} for n, c in job.characters.items()},
            scenes=[{"scene_id": s.scene_id, "in_seconds": s.in_seconds, "out_seconds": s.out_seconds,
                     "expected_characters": s.expected_characters} for s in job.scenes],
            render_path=job.render_path, qa_result=job.qa_result,
            costs=[{"label": c.label, "cost_usd": c.cost_usd} for c in job.costs],
            retry_count=sum(len(sa.retries) for sa in job.scene_assets.values()),
        )
        result = archive.archive_job(job_id=job.job_id, render_path=job.render_path, manifest=manifest,
                                       extra_files=[])
        job.drive_path = result["drive_remote_path"]
        if result["r2_result"]:
            job.r2_key = result["r2_result"]["key"]
        job.stage = JobStage.DRAFT_READY if job.qa_result == "QA_PASS" else JobStage.FAILED
        checkpoint.save(job)
        return result

    # ---- full pipeline, resumable ------------------------------------------

    @staticmethod
    def _resume_point(job: AnimationJob) -> JobStage:
        """Derives where to re-enter a FAILED job from its actual saved
        state, rather than trusting the terminal FAILED marker (a real bug
        fixed here: `run()` on a job whose `.stage` is literally FAILED
        matched none of the stage checks and silently did nothing on
        retry). Only used when `job.stage == JobStage.FAILED`."""
        if not job.render_path:
            return JobStage.SCENE_ASSETS if job.scene_assets else JobStage.REFERENCES
        if not job.qa_result:
            return JobStage.QA
        return JobStage.ARCHIVE

    def run(self, job: AnimationJob, *, build_props_fn) -> AnimationJob:
        """Resumable: re-entering with a checkpointed job skips already-
        completed stages (mission requirement 5). A RetryBudgetExceeded
        (bounded per-layer retries exhausted - mission requirement 3) or
        any other stage exception marks the job FAILED with the reason
        recorded, rather than crashing the caller - a real, unattended
        worker must produce a terminal status either way."""
        if job.stage == JobStage.FAILED:
            job.stage = self._resume_point(job)
            checkpoint.save(job)

        try:
            if job.stage in (JobStage.PENDING, JobStage.REFERENCES):
                self.ensure_references(job)
            if job.stage == JobStage.SCENE_ASSETS:
                self.build_scene_assets(job)
            if job.stage == JobStage.COMPOSITE:
                self.render(job, build_props_fn=build_props_fn)
            if job.stage == JobStage.QA:
                self.run_deterministic_qa(job)
                job.stage = JobStage.ARCHIVE
                checkpoint.save(job)
            if job.stage == JobStage.ARCHIVE:
                self.archive_and_deliver(job)
        except RetryBudgetExceeded as exc:
            job.stage = JobStage.FAILED
            job.qa_result = job.qa_result or f"FAILED:{exc.failure.value}"
            checkpoint.save(job)
        except Exception as exc:  # any other stage failure -> terminal FAILED, not a crash
            job.stage = JobStage.FAILED
            job.qa_result = job.qa_result or f"FAILED:{type(exc).__name__}:{exc}"
            checkpoint.save(job)
        return job

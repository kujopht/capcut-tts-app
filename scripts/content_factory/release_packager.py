"""
Normalized Release Packager — Content Factory v2.

Builds deterministic, normalized release packages under:
  raw_spool/release_packages/<work_id>/
    ├── manifest.json
    ├── chapters/
    │   ├── ch_0001.json
    │   └── ch_0002.json
    ├── cover.jpg (optional)
    ├── qa_report.json
    └── audio/ (optional async TTS audio)

Guarantees:
- Strictly maps to External Content Import Contract v1 (ExternalWorkImport).
- Separates text from audio: packages can be built, QA-passed, and published
  immediately as text-first while audio remains optional or TTS_PENDING.
- Supports both IMPORTED_FANFIC and AI_ORIGINAL provenance.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scripts.content_factory.provenance import (
    ProvenanceType,
    WorkProvenance,
    ChapterProvenance,
)
from server.crawler_intake_contract import compute_source_text_hash
from server.external_import_contract import (
    ContentType,
    ExternalAudio,
    ExternalChapter,
    ExternalCover,
    ExternalWorkImport,
    WorkStatus,
    PublicationMode,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_PACKAGES_DIR = PROJECT_ROOT / "raw_spool" / "release_packages"


class PackagedChapter(BaseModel):
    """Metadata and body for a single packaged chapter."""
    order: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=10)
    source_chapter_id: Optional[str] = None
    source_text_hash: str = ""
    word_count: int = 0
    audio_path: Optional[str] = None
    audio_duration_seconds: float = 0.0
    audio_size_bytes: int = 0
    audio_voice_name: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.source_text_hash:
            self.source_text_hash = compute_source_text_hash(self.content)
        if not self.word_count:
            self.word_count = len(self.content.split())


class QAReport(BaseModel):
    """Automated Quality Assurance report for a release package."""
    work_id: str
    passed: bool
    checks: Dict[str, bool] = Field(default_factory=dict)
    total_chapters: int = 0
    total_words: int = 0
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class ReleaseManifest(BaseModel):
    """Top-level release manifest for a packaged novel work."""
    work_id: str
    title: str
    author: str
    description: str = ""
    fandom: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    provenance: WorkProvenance
    status: str = "ready"  # ready, tts_pending, published
    total_chapters: int = 0
    total_words: int = 0
    cover_file: Optional[str] = None
    chapters: List[PackagedChapter] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class ReleasePackager:
    """Creates, validates, and manages normalized release packages."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or RELEASE_PACKAGES_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_package_dir(self, work_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", work_id.strip())
        return self.base_dir / safe_id

    def create_package(
        self,
        provenance: WorkProvenance,
        chapters: List[PackagedChapter],
        cover_path: Optional[Path] = None,
        tags: Optional[List[str]] = None,
        description: str = "",
        fandom: Optional[str] = None,
    ) -> Path:
        """
        Builds a full release package on disk and runs QA.
        """
        if not chapters:
            raise ValueError("Cannot create release package with 0 chapters.")

        # Re-sequence chapters consecutively 1..N
        sorted_ch = sorted(chapters, key=lambda c: c.order)
        for idx, ch in enumerate(sorted_ch, start=1):
            ch.order = idx

        work_id = provenance.source_work_id
        pkg_dir = self.get_package_dir(work_id)
        ch_dir = pkg_dir / "chapters"
        ch_dir.mkdir(parents=True, exist_ok=True)

        # Handle cover
        cover_file_rel = None
        if cover_path and cover_path.exists():
            target_cover = pkg_dir / "cover.jpg"
            shutil.copy2(cover_path, target_cover)
            cover_file_rel = "cover.jpg"

        total_words = sum(c.word_count for c in sorted_ch)

        manifest = ReleaseManifest(
            work_id=work_id,
            title=provenance.original_title,
            author=provenance.original_author,
            description=description,
            fandom=fandom,
            tags=tags or [],
            provenance=provenance,
            status="ready",
            total_chapters=len(sorted_ch),
            total_words=total_words,
            cover_file=cover_file_rel,
            chapters=sorted_ch,
        )

        # Write individual chapter JSON files
        for ch in sorted_ch:
            ch_path = ch_dir / f"ch_{ch.order:04d}.json"
            ch_path.write_text(
                json.dumps(ch.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        # Write manifest.json
        manifest_path = pkg_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Run QA and write qa_report.json
        qa = self.run_qa(manifest)
        qa_path = pkg_dir / "qa_report.json"
        qa_path.write_text(
            json.dumps(qa.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return pkg_dir

    def load_package(self, work_id: str) -> ReleaseManifest:
        """Loads release manifest from disk."""
        pkg_dir = self.get_package_dir(work_id)
        manifest_path = pkg_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Package manifest not found: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ReleaseManifest(**data)

    def run_qa(self, manifest: ReleaseManifest) -> QAReport:
        """
        Executes QA rules:
        1. Non-empty chapter list.
        2. Consecutive 1..N order.
        3. No empty titles or blank content.
        4. Valid text encoding (no raw replacement characters \ufffd).
        5. Minimum word count per chapter >= 50.
        6. Provenance URL sanity check.
        """
        checks: Dict[str, bool] = {}
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Non-empty
        checks["has_chapters"] = len(manifest.chapters) > 0
        if not checks["has_chapters"]:
            errors.append("Manifest has 0 chapters.")

        # 2. Consecutive order
        expected_orders = list(range(1, len(manifest.chapters) + 1))
        actual_orders = [c.order for c in manifest.chapters]
        checks["consecutive_order"] = (actual_orders == expected_orders)
        if not checks["consecutive_order"]:
            errors.append(f"Chapter orders are not consecutive 1..N: {actual_orders[:10]}...")

        # 3 & 4. Content sanity and encoding
        corrupt_chars = False
        short_chapters = 0
        for ch in manifest.chapters:
            if not ch.title.strip():
                errors.append(f"Chapter {ch.order} has empty title.")
            if len(ch.content.strip()) < 10:
                errors.append(f"Chapter {ch.order} has fewer than 10 characters.")
            if "\ufffd" in ch.content:
                corrupt_chars = True
            if ch.word_count < 50:
                short_chapters += 1

        checks["no_corrupt_encoding"] = not corrupt_chars
        if corrupt_chars:
            warnings.append("Detected Unicode replacement characters (\ufffd) in chapter content.")

        checks["acceptable_length"] = (short_chapters == 0)
        if short_chapters > 0:
            warnings.append(f"{short_chapters} chapter(s) have fewer than 50 words.")

        # 5. Provenance sanity
        checks["provenance_valid"] = True
        if manifest.provenance.provenance_type == ProvenanceType.IMPORTED_FANFIC:
            if not manifest.provenance.canonical_source_url:
                checks["provenance_valid"] = False
                errors.append("IMPORTED_FANFIC must have canonical_source_url.")
        elif manifest.provenance.provenance_type == ProvenanceType.AI_ORIGINAL:
            if manifest.provenance.canonical_source_url.startswith("http"):
                checks["provenance_valid"] = False
                errors.append("AI_ORIGINAL must not have external HTTP source URL.")

        passed = len(errors) == 0

        return QAReport(
            work_id=manifest.work_id,
            passed=passed,
            checks=checks,
            total_chapters=len(manifest.chapters),
            total_words=manifest.total_words,
            warnings=warnings,
            errors=errors,
        )

    def attach_audio_to_chapter(
        self,
        work_id: str,
        chapter_order: int,
        audio_file: Path,
        duration_seconds: float = 0.0,
        voice_name: str = "capcut_vi",
    ) -> None:
        """
        Attaches synthesized audio metadata to a packaged chapter without
        altering existing text or invalidating text hashes.
        """
        pkg_dir = self.get_package_dir(work_id)
        audio_dir = pkg_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        target_audio = audio_dir / f"ch_{chapter_order:04d}_{audio_file.name}"
        if audio_file.resolve() != target_audio.resolve():
            shutil.copy2(audio_file, target_audio)

        manifest = self.load_package(work_id)
        matched = False
        for ch in manifest.chapters:
            if ch.order == chapter_order:
                ch.audio_path = str(target_audio.relative_to(pkg_dir))
                ch.audio_duration_seconds = duration_seconds
                ch.audio_size_bytes = target_audio.stat().st_size
                ch.audio_voice_name = voice_name
                matched = True

                # Update individual chapter JSON
                ch_path = pkg_dir / "chapters" / f"ch_{ch.order:04d}.json"
                if ch_path.exists():
                    ch_path.write_text(
                        json.dumps(ch.model_dump(), ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                break

        if not matched:
            raise KeyError(f"Chapter order {chapter_order} not found in package {work_id}")

        # Update manifest
        manifest.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest_path = pkg_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def to_external_work_import(self, work_id: str) -> ExternalWorkImport:
        """
        Converts the normalized release package into an ExternalWorkImport
        and validates against the External Content Import Contract v1.
        """
        manifest = self.load_package(work_id)

        ext_chapters: List[ExternalChapter] = []
        for ch in manifest.chapters:
            audio_att = None
            if ch.audio_path:
                audio_att = ExternalAudio(
                    url=None,
                    key=ch.audio_path,
                    duration_seconds=ch.audio_duration_seconds,
                    size_bytes=ch.audio_size_bytes,
                    voice_name=ch.audio_voice_name or "external",
                )

            ext_chapters.append(
                ExternalChapter(
                    order=ch.order,
                    title=ch.title,
                    content=ch.content,
                    source_chapter_id=ch.source_chapter_id,
                    audio=audio_att,
                )
            )

        cover_spec = None
        if manifest.cover_file:
            cover_spec = ExternalCover(key=manifest.cover_file)

        return ExternalWorkImport(
            content_type=ContentType.FANFIC,
            source_id=manifest.work_id,
            source_url=manifest.provenance.canonical_source_url or None,
            title=manifest.title,
            author=manifest.author,
            description=manifest.description,
            cover=cover_spec,
            language="vi",
            status=WorkStatus.ONGOING if manifest.provenance.source_status == "ongoing" else WorkStatus.COMPLETED,
            publication_mode=PublicationMode.FULL_TEXT,
            tags=manifest.tags,
            fandom=manifest.fandom,
            chapters=ext_chapters,
        )

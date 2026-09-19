"""
External Content Import Service for Fanfic World.

Implements preview/dry-run, duplicate detection, and resumable execution
for External Content Import Contract v1.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from server.adapters import MetadataStore, StorageAdapter
from server.domain import AudioTrack, Chapter, Novel, NovelStatus, PublishState, now_iso
from server.external_import_contract import (
    ContentType,
    ExternalAudio,
    ExternalChapter,
    ExternalCover,
    ExternalWorkImport,
    clean_reader_tags,
    compute_work_fingerprint,
)
from server.fandom_registry import FandomRegistry, UnknownFandomError

logger = logging.getLogger(__name__)


@dataclass
class ChapterPreview:
    order: int
    title: str
    char_count: int
    has_audio: bool
    status: str                       # "new", "existing", "update"
    existing_chapter_id: Optional[str] = None


@dataclass
class ImportPreviewResult:
    valid: bool
    work_fingerprint: str
    target_novel_id: str
    is_duplicate: bool
    duplicate_reason: Optional[str]
    action: str                       # "create", "resume_append", "no_change"
    title: str
    content_type: str
    author: str
    language: str
    sanitized_tags: List[str]
    rejected_technical_tags: List[str]
    resolved_fandom_ids: List[str]
    unresolved_fandoms: List[str]
    total_chapters: int
    new_chapters_count: int
    existing_chapters_count: int
    audio_chapters_count: int
    total_characters: int
    has_cover: bool
    chapters_preview: List[Dict[str, Any]]
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChapterImportResult:
    chapter_id: str
    order_index: int
    title: str
    status: str                       # "created", "skipped_identical", "updated"
    has_audio: bool = False
    track_id: Optional[str] = None


@dataclass
class ImportExecutionResult:
    success: bool
    work_fingerprint: str
    novel_id: str
    title: str
    action_taken: str                 # "created", "resumed_appended", "updated_metadata_only"
    total_chapters: int
    chapters_created: int
    chapters_skipped: int
    audio_tracks_created: int
    cover_uploaded: bool
    errors: List[Dict[str, str]] = field(default_factory=list)
    chapters: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExternalImportService:
    """Service handling validation, preview, and execution of external imports."""

    def __init__(
        self,
        store: MetadataStore,
        storage: Optional[StorageAdapter] = None,
        fandom_reg: Optional[FandomRegistry] = None,
        default_owner_id: str = "svc_harvester"
    ):
        self.store = store
        self.storage = storage
        self.fandom_reg = fandom_reg
        self.default_owner_id = default_owner_id

    def find_existing_novel(self, work: ExternalWorkImport, fingerprint: str) -> Optional[Novel]:
        """
        Check if the work already exists in the store via multiple authority gates:
        1. Deterministic novel_id match (nov_ext_{fingerprint[:16]})
        2. Exact canonical external_source_url match
        3. Match on (normalized title, normalized author)
        """
        target_novel_id = f"nov_ext_{fingerprint[:16]}"
        try:
            existing = self.store.get_novel(target_novel_id)
            if existing:
                return existing
        except Exception:
            pass

        # Check by external_source_url
        if work.source_url:
            all_novels = self.store.list_novels()
            canon_src = work.source_url.strip()
            for n in all_novels:
                if n.external_source_url and n.external_source_url.strip() == canon_src:
                    return n

        # Check by Title and Author
        norm_title = work.title.strip().lower()
        norm_author = (work.author or "").strip().lower()
        if norm_title:
            all_novels = self.store.list_novels()
            for n in all_novels:
                n_title = (n.title or "").strip().lower()
                n_author = (n.external_author_name or "").strip().lower()
                if n_title == norm_title and (not norm_author or n_author == norm_author):
                    return n

        return None

    def resolve_fandoms(self, fandom_names: List[str]) -> Tuple[List[str], List[str]]:
        """Resolve fandom names against fandom registry, recording resolved and unresolved."""
        resolved: List[str] = []
        unresolved: List[str] = []
        if not self.fandom_reg:
            return resolved, unresolved

        for fname in fandom_names:
            if not fname:
                continue
            try:
                fnd = self.fandom_reg.resolve(fname)
                if fnd and fnd.fandom_id not in resolved:
                    resolved.append(fnd.fandom_id)
            except UnknownFandomError:
                unresolved.append(fname)
            except Exception:
                unresolved.append(fname)

        return resolved, unresolved

    def preview(self, work: ExternalWorkImport) -> ImportPreviewResult:
        """
        Perform a pure dry-run / preview of the import.
        Guarantees ZERO database mutations.
        """
        fingerprint = work.get_fingerprint()
        target_novel_id = f"nov_ext_{fingerprint[:16]}"
        existing_novel = self.find_existing_novel(work, fingerprint)

        clean_tags = work.tags
        rejected_tags = work.rejected_tags
        resolved_fandom_ids, unresolved_fandoms = self.resolve_fandoms(work.fandoms)

        existing_chapters: Dict[int, Chapter] = {}
        if existing_novel:
            try:
                chps = self.store.list_chapters(existing_novel.novel_id)
                for c in chps:
                    existing_chapters[c.order_index] = c
            except Exception:
                pass

        chapters_preview: List[ChapterPreview] = []
        new_count = 0
        existing_count = 0
        audio_count = 0
        total_chars = 0

        for ch in work.chapters:
            total_chars += len(ch.content)
            has_audio = ch.audio is not None and bool(ch.audio.url or ch.audio.base64 or ch.audio.key)
            if has_audio:
                audio_count += 1

            if ch.order in existing_chapters:
                existing_c = existing_chapters[ch.order]
                existing_count += 1
                status = "existing" if existing_c.content == ch.content else "update"
                chapters_preview.append(ChapterPreview(
                    order=ch.order,
                    title=ch.title,
                    char_count=len(ch.content),
                    has_audio=has_audio,
                    status=status,
                    existing_chapter_id=existing_c.chapter_id
                ))
            else:
                new_count += 1
                chapters_preview.append(ChapterPreview(
                    order=ch.order,
                    title=ch.title,
                    char_count=len(ch.content),
                    has_audio=has_audio,
                    status="new",
                    existing_chapter_id=None
                ))

        if existing_novel is None:
            action = "create"
            is_duplicate = False
            duplicate_reason = None
        elif new_count > 0:
            action = "resume_append"
            is_duplicate = True
            duplicate_reason = f"Work already exists as novel '{existing_novel.novel_id}'. Will append {new_count} new chapters."
        else:
            action = "no_change"
            is_duplicate = True
            duplicate_reason = f"Work already exists as novel '{existing_novel.novel_id}' with all {existing_count} chapters present."

        return ImportPreviewResult(
            valid=True,
            work_fingerprint=fingerprint,
            target_novel_id=existing_novel.novel_id if existing_novel else target_novel_id,
            is_duplicate=is_duplicate,
            duplicate_reason=duplicate_reason,
            action=action,
            title=work.title,
            content_type=work.content_type.value,
            author=work.author or "",
            language=work.language,
            sanitized_tags=clean_tags,
            rejected_technical_tags=rejected_tags,
            resolved_fandom_ids=resolved_fandom_ids,
            unresolved_fandoms=unresolved_fandoms,
            total_chapters=len(work.chapters),
            new_chapters_count=new_count,
            existing_chapters_count=existing_count,
            audio_chapters_count=audio_count,
            total_characters=total_chars,
            has_cover=work.cover is not None,
            chapters_preview=[asdict(cp) for cp in chapters_preview],
            errors=[]
        )

    def execute(
        self,
        work: ExternalWorkImport,
        owner_id: Optional[str] = None,
        dry_run: bool = False
    ) -> ImportExecutionResult:
        """
        Execute the import atomically per chapter, supporting resume/idempotency.
        If dry_run=True, delegates to preview without writing to store.
        """
        if dry_run:
            preview_res = self.preview(work)
            return ImportExecutionResult(
                success=preview_res.valid,
                work_fingerprint=preview_res.work_fingerprint,
                novel_id=preview_res.target_novel_id,
                title=preview_res.title,
                action_taken=f"dry_run_{preview_res.action}",
                total_chapters=preview_res.total_chapters,
                chapters_created=0,
                chapters_skipped=preview_res.existing_chapters_count,
                audio_tracks_created=0,
                cover_uploaded=False,
                errors=preview_res.errors,
                chapters=preview_res.chapters_preview
            )

        owner = owner_id or self.default_owner_id
        fingerprint = work.get_fingerprint()
        target_novel_id = f"nov_ext_{fingerprint[:16]}"

        existing_novel = self.find_existing_novel(work, fingerprint)
        resolved_fandoms, _ = self.resolve_fandoms(work.fandoms)
        clean_tags, _ = clean_reader_tags(work.tags)

        # 1. Process Cover image if provided
        cover_key: Optional[str] = None
        cover_uploaded = False
        if work.cover:
            cover_key, cover_uploaded = self._process_cover(
                work.cover, owner, existing_novel.novel_id if existing_novel else target_novel_id
            )

        # 2. Create or Update Novel entity
        if existing_novel is None:
            novel_to_create = Novel(
                novel_id=target_novel_id,
                owner_id=owner,
                title=work.title,
                description=work.description or "",
                cover_key=cover_key,
                state=PublishState.PUBLISHED,
                tags=clean_tags,
                fandom_ids=resolved_fandoms,
                external_author_name=work.author or "",
                external_source_url=work.source_url or "",
                external_chapter_count=len(work.chapters),
                language=work.language,
                status=NovelStatus(work.status.value),
                characters=list(work.characters),
                pairings=list(work.pairings)
            )
            saved_novel = self.store.create_novel(novel_to_create)
            active_novel_id = saved_novel.novel_id
            action_taken = "created"
        else:
            active_novel_id = existing_novel.novel_id
            action_taken = "resumed_appended"
            # Update cover if new cover uploaded and existing novel had none
            if cover_key and not existing_novel.cover_key:
                try:
                    self.store.set_novel_cover(active_novel_id, existing_novel.owner_id, cover_key)
                except Exception as e:
                    logger.warning(f"Could not update cover for {active_novel_id}: {e}")

        # 3. Ingest Chapters and Audios
        existing_chapters_by_order: Dict[int, Chapter] = {}
        try:
            for c in self.store.list_chapters(active_novel_id):
                existing_chapters_by_order[c.order_index] = c
        except Exception:
            pass

        created_count = 0
        skipped_count = 0
        audio_created_count = 0
        chapter_results: List[ChapterImportResult] = []

        for ch in work.chapters:
            deterministic_chp_id = f"chp_{fingerprint[:10]}_{ch.order:04d}"

            # Check if this order_index already exists
            if ch.order in existing_chapters_by_order:
                existing_c = existing_chapters_by_order[ch.order]
                # If content identical, skip creation
                if existing_c.content == ch.content:
                    skipped_count += 1
                    track_id = self._attach_audio_if_needed(
                        ch.audio, existing_c.chapter_id, owner, active_novel_id
                    )
                    if track_id:
                        audio_created_count += 1
                    chapter_results.append(ChapterImportResult(
                        chapter_id=existing_c.chapter_id,
                        order_index=ch.order,
                        title=existing_c.title,
                        status="skipped_identical",
                        has_audio=track_id is not None,
                        track_id=track_id
                    ))
                    continue

            # Create chapter
            new_chapter = Chapter(
                chapter_id=deterministic_chp_id,
                novel_id=active_novel_id,
                owner_id=owner,
                title=ch.title,
                content=ch.content,
                order_index=ch.order,
                state=PublishState.PUBLISHED
            )

            try:
                saved_ch = self.store.create_chapter(new_chapter)
                created_count += 1
            except Exception as e:
                # In case of idempotent 409 conflict, fetch existing
                logger.info(f"Chapter creation note for {deterministic_chp_id}: {e}")
                saved_ch = self.store.get_chapter(deterministic_chp_id)
                if not saved_ch:
                    raise

            # 4. Attach Audio if provided
            track_id = self._attach_audio_if_needed(
                ch.audio, saved_ch.chapter_id, owner, active_novel_id
            )
            if track_id:
                audio_created_count += 1

            chapter_results.append(ChapterImportResult(
                chapter_id=saved_ch.chapter_id,
                order_index=saved_ch.order_index,
                title=saved_ch.title,
                status="created",
                has_audio=track_id is not None,
                track_id=track_id
            ))

        return ImportExecutionResult(
            success=True,
            work_fingerprint=fingerprint,
            novel_id=active_novel_id,
            title=work.title,
            action_taken=action_taken if created_count > 0 else "no_new_chapters",
            total_chapters=len(work.chapters),
            chapters_created=created_count,
            chapters_skipped=skipped_count,
            audio_tracks_created=audio_created_count,
            cover_uploaded=cover_uploaded,
            errors=[],
            chapters=[asdict(cr) for cr in chapter_results]
        )

    def _process_cover(
        self,
        cover: ExternalCover,
        owner_id: str,
        novel_id: str
    ) -> Tuple[Optional[str], bool]:
        """Upload cover image if storage adapter is available and base64 provided."""
        if cover.key:
            return cover.key, False

        if not self.storage:
            return None, False

        if cover.base64:
            try:
                raw_bytes = base64.b64decode(cover.base64)
                mime = cover.mime or "image/jpeg"
                ext = mime.split("/")[-1] or "jpg"
                storage_key = f"covers/{owner_id}/{novel_id}.{ext}"
                self.storage.put(storage_key, raw_bytes, content_type=mime)
                return storage_key, True
            except Exception as e:
                logger.warning(f"Failed to upload base64 cover: {e}")

        return None, False

    def _attach_audio_if_needed(
        self,
        audio: Optional[ExternalAudio],
        chapter_id: str,
        owner_id: str,
        novel_id: str
    ) -> Optional[str]:
        """Attach AudioTrack to chapter if audio payload is present."""
        if not audio:
            return None

        # Check if track already exists for this chapter
        existing_track = self.store.track_for_chapter(chapter_id)
        if existing_track:
            return existing_track.track_id

        object_key = audio.key or f"audio/{novel_id}/{chapter_id}.mp3"
        content_hash = hashlib.sha256(f"{chapter_id}:{object_key}".encode("utf-8")).hexdigest()

        # If base64 audio provided and storage available, persist to storage
        if audio.base64 and self.storage and not audio.key:
            try:
                audio_bytes = base64.b64decode(audio.base64)
                self.storage.put(object_key, audio_bytes, content_type="audio/mpeg")
            except Exception as e:
                logger.warning(f"Failed to persist audio for chapter {chapter_id}: {e}")

        # Create AudioTrack in metadata store
        new_track = AudioTrack(
            chapter_id=chapter_id,
            owner_id=owner_id,
            voice_id=audio.voice_name or "external",
            object_key=object_key,
            content_hash=content_hash,
            duration_seconds=audio.duration_seconds or 0.0,
            size_bytes=audio.size_bytes or 0
        )
        saved_track = self.store.create_track(new_track)
        return saved_track.track_id

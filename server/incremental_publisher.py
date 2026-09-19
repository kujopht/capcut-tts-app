"""
Incremental Publisher — Fanfic Ingestion Pipeline v1.

Publishes translated chapters incrementally to Fanfic World via
External Content Import Contract v1 and ExternalImportService.

Guarantees & Constraints:
- Chapter 1 translated -> publish Chapter 1 immediately -> readers can read it immediately.
- Never waits for subsequent chapters (e.g. 500-chapter book) or for TTS synthesis.
- Strictly idempotent: Existing chapters are detected and skipped; new chapters are appended.
- Uses the approved downstream boundary: External Content Import Contract v1.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from server.domain import Chapter, Novel
from server.external_import_contract import (
    ContentType,
    ExternalAudio,
    ExternalChapter,
    ExternalCover,
    ExternalWorkImport,
    PublicationMode,
    WorkStatus,
    clean_reader_tags,
)
from server.external_import_service import ExternalImportService, ImportExecutionResult
from server.ingestion_state_machine import (
    AudioLifecycleState,
    ChapterCheckpoint,
    ChapterState,
    LocalStateStore,
    WorkCheckpoint,
    WorkState,
    now_iso,
)


class IncrementalPublisher:
    """
    Coordinates incremental publication of translated chapters into Fanfic World.
    """

    def __init__(
        self,
        import_service: ExternalImportService,
        state_store: LocalStateStore,
        default_owner_id: str = "usr_system",
    ):
        self.import_service = import_service
        self.state_store = state_store
        self.default_owner_id = default_owner_id

    def build_import_payload(
        self,
        work: WorkCheckpoint,
        chapters_to_publish: List[ChapterCheckpoint],
    ) -> ExternalWorkImport:
        """
        Converts internal WorkCheckpoint and ready chapters into ExternalWorkImport contract.
        """
        contract_chapters: List[ExternalChapter] = []
        for ch in sorted(chapters_to_publish, key=lambda c: c.source_order):
            audio_att = None
            if ch.audio_state == AudioLifecycleState.COMPLETE and ch.audio_object_key:
                audio_att = ExternalAudio(
                    key=ch.audio_object_key,
                    duration_seconds=ch.audio_duration,
                    size_bytes=ch.audio_size,
                    voice_name=ch.audio_voice_id or "external"
                )

            contract_chapters.append(
                ExternalChapter(
                    order=ch.source_order,
                    title=ch.translated_title or ch.source_title,
                    content=ch.translated_text or ch.source_text,
                    source_chapter_id=ch.source_chapter_id or f"src_ch_{ch.source_order}",
                    audio=audio_att,
                )
            )

        cover_att = None
        if work.cover_url:
            cover_att = ExternalCover(url=work.cover_url)

        return ExternalWorkImport(
            content_type=ContentType.FANFIC,
            source_id=work.source_id,
            source_url=work.source_url,
            title=work.title_vi or work.title_original,
            author=work.author or "Tác giả mạng",
            description=work.description or "",
            cover=cover_att,
            language="vi",
            status=WorkStatus.ONGOING,
            publication_mode=PublicationMode.FULL_TEXT,
            tags=list(work.tags),
            fandom=work.fandom,
            chapters=contract_chapters,
        )

    def publish_ready_chapters(
        self,
        work: WorkCheckpoint,
        owner_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> ImportExecutionResult:
        """
        Publishes any chapters currently in TEXT_READY or newly completed state.
        Guarantees that readers can immediately read published chapters while later
        chapters continue processing.
        """
        target_owner = owner_id or self.default_owner_id

        # Find all chapters that have translated text available
        eligible_chapters = [
            ch for ch in work.chapters.values()
            if ch.translated_text and ch.state in (
                ChapterState.TEXT_READY,
                ChapterState.PUBLISHED,
                ChapterState.AUDIO_READY,
                ChapterState.TTS_PENDING,
                ChapterState.TTS_RUNNING,
                ChapterState.TTS_FAILED,
            )
        ]

        if not eligible_chapters:
            return ImportExecutionResult(
                success=False,
                novel_id="",
                action="no_op",
                chapters_created=0,
                chapters_skipped=0,
                audio_tracks_created=0,
                cover_uploaded=False,
                errors=[{"error": "No translated chapters are ready for publication"}],
            )

        payload = self.build_import_payload(work, eligible_chapters)
        res = self.import_service.execute(payload, owner_id=target_owner, dry_run=dry_run)

        if res.success and not dry_run:
            work.published_novel_id = res.novel_id

            # Map published chapter IDs from execution result
            order_to_id = {
                c.get("order_index", c.get("order")): c["chapter_id"]
                for c in res.chapters
                if "chapter_id" in c and (c.get("order_index") is not None or c.get("order") is not None)
            }
            for ch in eligible_chapters:
                if ch.source_order in order_to_id:
                    ch.published_chapter_id = order_to_id[ch.source_order]

                # Update state: If it was TEXT_READY, it is now PUBLISHED!
                if ch.state == ChapterState.TEXT_READY:
                    ch.state = ChapterState.PUBLISHED
                    if ch.audio_state == AudioLifecycleState.NONE:
                        ch.audio_state = AudioLifecycleState.PENDING
                ch.updated_at = now_iso()

            work.refresh_work_state()
            self.state_store.save_work(work)

        return res

    def publish_single_chapter_immediately(
        self,
        work: WorkCheckpoint,
        chapter: ChapterCheckpoint,
        owner_id: Optional[str] = None,
    ) -> ImportExecutionResult:
        """
        Publishes a single translated chapter immediately upon translation completion.
        """
        if not chapter.translated_text:
            return ImportExecutionResult(
                success=False,
                novel_id="",
                action="no_op",
                chapters_created=0,
                chapters_skipped=0,
                audio_tracks_created=0,
                cover_uploaded=False,
                errors=[{"error": f"Chapter {chapter.source_order} has no translated text"}],
            )

        return self.publish_ready_chapters(work, owner_id=owner_id, dry_run=False)

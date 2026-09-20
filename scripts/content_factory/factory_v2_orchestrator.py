"""
Content Factory v2 Orchestrator.

Unifies:
1. Crawler Intake (BaseCrawlerAdapter / RoyalRoadAdapter) & AI Original Creation.
2. Translation Engine (Gemini multi-account rotation + Persistent Translation Glossary).
3. Local Spool Checkpoint / Cache (Never re-translate or re-synthesize matching content hashes).
4. Normalized Release Packager (External Content Import Contract compliant).
5. Production Diff Engine (Zero-write dry run, UNCHANGED skipping, cost projection).
6. One-Click Safe Publication Boundary (Isolated from text ingestion).
7. Decoupled Async TTS (Audio never blocks text publication).
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce silent subprocesses on Windows
import scripts.content_factory.silent_subprocess
from scripts.content_factory.provenance import (
    ProvenanceType,
    WorkProvenance,
    ChapterProvenance,
)
from scripts.content_factory.crawler_adapters.adapter_registry import get_adapter_for_url, get_adapter_by_platform
from scripts.content_factory.glossary_manager import GlossaryManager, NovelGlossary
from scripts.content_factory.release_packager import ReleasePackager, PackagedChapter, ReleaseManifest
from scripts.content_factory.production_diff_engine import ProductionDiffEngine, NovelDiffReport, DiffStatus, find_active_registry_db
from scripts.content_factory.content_classifier import ContentClassifier, EntryClassification
from scripts.content_factory.publish_quality_gate import PublishQualityGate, QualityGateResult
from server.crawler_intake_contract import RawCrawlerWork, RawCrawlerChapter, compute_source_text_hash

logger = logging.getLogger("ContentFactoryV2")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CACHE_DIR = PROJECT_ROOT / "raw_spool" / "translation_cache"


class ContentFactoryV2Orchestrator:
    """Master orchestrator for Content Factory v2."""

    def __init__(
        self,
        base_spool_dir: Optional[Path] = None,
        registry_db_path: Optional[Path] = None,
        classification_overrides_file: Optional[Path] = None,
    ):
        self.spool_dir = base_spool_dir or (PROJECT_ROOT / "raw_spool")
        self.cache_dir = self.spool_dir / "translation_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.classifier = ContentClassifier(classification_overrides_file or (PROJECT_ROOT / "scratch" / "hatake_upstream_classification.json"))
        self.quality_gate = PublishQualityGate()
        self.glossary_mgr = GlossaryManager(self.spool_dir / "glossaries")
        self.packager = ReleasePackager(self.spool_dir / "release_packages")
        self.diff_engine = ProductionDiffEngine(registry_db_path or find_active_registry_db())

    def crawl_work(self, url: str, max_chapters: Optional[int] = None) -> RawCrawlerWork:
        """Harvests a work via the appropriate registered crawler adapter."""
        adapter_cls = get_adapter_for_url(url)
        if not adapter_cls:
            raise ValueError(f"No crawler adapter registered for URL: {url}")
        adapter = adapter_cls()
        logger.info(f"Crawling {url} using {adapter_cls.PLATFORM_NAME} adapter...")
        return adapter.fetch_work(url, max_chapters=max_chapters)

    def translate_chapter(
        self,
        work_key: str,
        chapter: RawCrawlerChapter,
        fandom_hint: str = "",
        force_retranslate: bool = False,
    ) -> Dict[str, str]:
        """
        Translates a chapter with glossary injection and deterministic caching.
        Returns {'title_vi': ..., 'content_vi': ..., 'cached': bool}.
        """
        ch_hash = chapter.source_text_hash or compute_source_text_hash(chapter.source_text)
        work_cache_dir = self.cache_dir / work_key
        work_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = work_cache_dir / f"{ch_hash}.json"

        # Check cache (idempotence guarantee)
        if cache_file.exists() and not force_retranslate:
            try:
                cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                return {
                    "title_vi": cached_data["title_vi"],
                    "content_vi": cached_data["content_vi"],
                    "cached": True,
                }
            except Exception:
                pass

        # Prepare glossary context
        glossary_prompt = self.glossary_mgr.build_gemini_prompt_context(work_key)
        context_notes = f"Fandom: {fandom_hint}\n{glossary_prompt}".strip()

        # Import gemini_evaluator dynamically
        from scripts.content_factory.gemini_evaluator import translate_text

        logger.info(f"Translating Ch {chapter.source_order} '{chapter.source_title}' ({len(chapter.source_text)} chars)...")
        title_vi = translate_text(chapter.source_title, context_notes=f"Tiêu đề chương truyện. Fandom: {fandom_hint}")
        content_vi = translate_text(chapter.source_text, context_notes=context_notes)

        # Apply post-translation consistency
        content_vi = self.glossary_mgr.apply_post_translation_consistency(content_vi, work_key)

        result = {
            "title_vi": title_vi.strip(),
            "content_vi": content_vi.strip(),
            "cached": False,
            "source_hash": ch_hash,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Write to cache
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def build_package_from_work(
        self,
        raw_work: RawCrawlerWork,
        cover_path: Optional[Path] = None,
        dry_run_diff_first: bool = True,
    ) -> ReleaseManifest:
        """
        Translates missing chapters, normalizes, and packages into a release package.
        """
        work_key = raw_work.source_id
        provenance = WorkProvenance(
            provenance_type=ProvenanceType.IMPORTED_FANFIC,
            source_platform=detect_platform_from_url(raw_work.source_url),
            source_work_id=raw_work.source_id,
            canonical_source_url=raw_work.source_url,
            original_title=raw_work.title,
            original_author=raw_work.author or "Unknown",
            source_status="ongoing",
        )

        # 1. Classification MUST happen BEFORE translation
        classified_entries = []
        for ch in raw_work.chapters:
            decision = self.classifier.classify_entry(
                title=ch.source_title,
                content=ch.source_text,
                source_order=ch.source_order,
                work_id=work_key,
            )
            classified_entries.append((ch, decision))

        # Check production diff first to avoid translating UNCHANGED chapters
        diff_report = self.diff_engine.diff(raw_work, platform_hint=provenance.source_platform)
        unchanged_orders = {d.order for d in diff_report.chapter_diffs if d.status == DiffStatus.UNCHANGED}

        packaged_chapters: List[PackagedChapter] = []
        current_display_order = 1

        for ch, decision in classified_entries:
            # Never spend LLM or TTS resources on announcements by default
            if decision.entry_type in (EntryClassification.ANNOUNCEMENT, EntryClassification.AUTHOR_NOTE):
                logger.info(f"Entry {ch.source_order} is {decision.entry_type.value} ('{ch.source_title}') -> Skipping LLM/TTS translation (archived).")
                continue

            if decision.entry_type == EntryClassification.UNKNOWN:
                logger.warning(f"Entry {ch.source_order} has UNKNOWN classification -> Requires manual review.")

            display_order = current_display_order
            current_display_order += 1

            if ch.source_order in unchanged_orders:
                logger.info(f"Chapter {ch.source_order} is UNCHANGED in production -> skipping LLM translation.")
                packaged_chapters.append(PackagedChapter(
                    order=display_order,
                    title=ch.source_title,
                    content=ch.source_text,
                    source_chapter_id=ch.source_chapter_id,
                    source_text_hash=ch.source_text_hash,
                ))
            else:
                translated = self.translate_chapter(
                    work_key=work_key,
                    chapter=ch,
                    fandom_hint=raw_work.fandom or (raw_work.fandoms[0] if raw_work.fandoms else "")
                )
                vi_content = translated["content_vi"] or ch.source_text
                vi_title = translated["title_vi"] or ch.source_title

                # Format Extra label if classified as EXTRA
                if decision.entry_type == EntryClassification.EXTRA:
                    ex_num = decision.extra_number or 1
                    vi_title = f"Chương {display_order} (Ngoại Truyện {ex_num}): {vi_title}"

                # Run Permanent Publish Quality Gate Audit
                qg_result = self.quality_gate.audit_chapter(
                    chapter_id=f"chp_{work_key}_{ch.source_order:04d}",
                    source_order=ch.source_order,
                    display_order=display_order,
                    source_text=ch.source_text,
                    translated_text=vi_content,
                    classification=decision.entry_type,
                    source_chunks=[{"chunk_id": "c1", "text": ch.source_text}],
                    translated_chunks=[{"chunk_id": "c1", "text": vi_content}],
                )
                if not qg_result.publish_allowed:
                    logger.warning(f"Ch {ch.source_order} Quality Gate WARNING: {qg_result.blocking_reasons}")

                packaged_chapters.append(PackagedChapter(
                    order=display_order,
                    title=vi_title,
                    content=vi_content,
                    source_chapter_id=ch.source_chapter_id,
                    source_text_hash=ch.source_text_hash,
                ))

        pkg_dir = self.packager.create_package(
            provenance=provenance,
            chapters=packaged_chapters,
            cover_path=cover_path,
            tags=raw_work.tags,
            description=raw_work.description or "",
            fandom=raw_work.fandom,
        )
        logger.info(f"Successfully packaged work {work_key} into {pkg_dir}")
        return self.packager.load_package(work_key)

    def diff_package(self, work_id: str) -> NovelDiffReport:
        """Runs production diff on an existing release package."""
        manifest = self.packager.load_package(work_id)
        return self.diff_engine.diff(manifest)

    def publish_package_dry_run(self, work_id: str) -> NovelDiffReport:
        """Executes zero-write dry run publication check."""
        return self.diff_package(work_id)


def detect_platform_from_url(url: str) -> str:
    """Helper to deduce platform name from URL."""
    u = url.lower()
    if "royalroad.com" in u:
        return "royalroad"
    if "archiveofourown.org" in u:
        return "ao3"
    if "fanfiction.net" in u:
        return "ffnet"
    return "external"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content Factory v2 Orchestrator CLI")
    parser.add_argument("--action", choices=["crawl", "translate", "package", "diff", "publish"], default="diff")
    parser.add_argument("--url", help="Upstream source URL")
    parser.add_argument("--work-id", help="Work identifier")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Enforce dry run (no production writes)")

    args = parser.parse_args()
    orchestrator = ContentFactoryV2Orchestrator()

    if args.action == "diff" and args.work_id:
        report = orchestrator.diff_package(args.work_id)
        print("\n" + "=" * 60)
        print("PRODUCTION DIFF REPORT (DRY-RUN)")
        print("=" * 60)
        print(report.summary)
        for cd in report.chapter_diffs:
            print(f"  Ch {cd.order:02d}: {cd.status.value} -> {cd.action_preview}")
        print("=" * 60)
    else:
        print("Run with --action diff --work-id <id> or --action crawl --url <url>")

"""
Translation Scheduler & Multi-Account Pool Abstraction.

Coordinates chapter translation across a pool of LLM worker accounts (Gemini / Claude / GPT)
without hard-coding credentials or accounts.

Guarantees:
- Account pool abstraction with dynamic discovery, leasing, cooldown, and failover.
- Immediate retry on alternative account when encountering rate limits or quota errors.
- Checkpointing before and after each chapter: zero duplicate translations for identical source hashes.
- Credential isolation: Credentials never touched or stored in databases.
"""

from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set

from server.ingestion_state_machine import (
    ChapterCheckpoint,
    ChapterState,
    LocalStateStore,
    WorkCheckpoint,
    WorkState,
    now_iso,
)


class TranslationError(Exception):
    """Base exception for translation engine errors."""
    def __init__(self, message: str, is_rate_limit: bool = False):
        super().__init__(message)
        self.is_rate_limit = is_rate_limit


class ITranslationAccountPool(ABC):
    """Abstract interface for managing a fleet of translation accounts."""

    @abstractmethod
    def acquire_account(self, exclude: Optional[Set[str]] = None) -> Optional[str]:
        """Lease the most suitable available account, excluding specified accounts."""
        pass

    @abstractmethod
    def release_account(self, account_name: str, success: bool, error_message: str = "") -> None:
        """Return an account to the pool, reporting call outcome for cooldown/rate-limit tracking."""
        pass

    @abstractmethod
    def list_accounts(self) -> List[str]:
        """List all accounts currently managed by the pool."""
        pass


class MockAccountPool(ITranslationAccountPool):
    """In-memory account pool for unit tests and local simulation."""

    def __init__(self, account_names: Optional[List[str]] = None, cooldown_seconds: float = 300.0):
        self.accounts = account_names or [f"acc{i}" for i in range(1, 14)]
        self.cooldown_seconds = cooldown_seconds
        self.busy: Set[str] = set()
        self.cooldowns: Dict[str, float] = {}
        self.failures: Dict[str, int] = {acc: 0 for acc in self.accounts}
        self.successes: Dict[str, int] = {acc: 0 for acc in self.accounts}

    def acquire_account(self, exclude: Optional[Set[str]] = None) -> Optional[str]:
        now = time.time()
        excluded = exclude or set()
        for acc in self.accounts:
            if acc in excluded or acc in self.busy:
                continue
            if acc in self.cooldowns and self.cooldowns[acc] > now:
                continue
            self.busy.add(acc)
            return acc
        return None

    def release_account(self, account_name: str, success: bool, error_message: str = "") -> None:
        self.busy.discard(account_name)
        if success:
            self.successes[account_name] = self.successes.get(account_name, 0) + 1
            self.failures[account_name] = 0
            self.cooldowns.pop(account_name, None)
        else:
            self.failures[account_name] = self.failures.get(account_name, 0) + 1
            is_rate_limit = any(
                k in error_message.lower() for k in ("quota", "limit", "429", "resource_exhausted")
            )
            if is_rate_limit:
                self.cooldowns[account_name] = time.time() + self.cooldown_seconds

    def list_accounts(self) -> List[str]:
        return list(self.accounts)


class ITranslationEngine(ABC):
    """Interface for translating text chunks."""

    @abstractmethod
    def translate_chapter(
        self,
        text: str,
        title: str,
        source_lang: str,
        account_name: str
    ) -> tuple[str, str]:
        """
        Translates a single chapter body and title.
        Returns (translated_title, translated_text).
        Raises TranslationError on failure.
        """
        pass


class MockTranslationEngine(ITranslationEngine):
    """
    Deterministic mock translation engine for tests.
    Supports injecting artificial failure/rate limits on specific accounts.
    """

    def __init__(self, failing_accounts: Optional[Set[str]] = None):
        self.failing_accounts = failing_accounts or set()
        self.call_count = 0

    def translate_chapter(
        self,
        text: str,
        title: str,
        source_lang: str,
        account_name: str
    ) -> tuple[str, str]:
        self.call_count += 1
        if account_name in self.failing_accounts:
            raise TranslationError(
                f"Rate limit exceeded on {account_name}: 429 RESOURCE_EXHAUSTED",
                is_rate_limit=True
            )
        # Produce a clean Vietnamese mock translation
        vi_title = f"[Dịch] {title}"
        vi_text = f"Bản dịch tiếng Việt chuẩn: {text}"
        return vi_title, vi_text


class TranslationScheduler:
    """
    Coordinates translation of entire works chapter-by-chapter with
    failover, account rotation, and checkpoint deduplication.
    """

    def __init__(
        self,
        pool: ITranslationAccountPool,
        engine: ITranslationEngine,
        state_store: LocalStateStore,
    ):
        self.pool = pool
        self.engine = engine
        self.state_store = state_store

    def validate_vietnamese_output(self, text: str) -> tuple[bool, str]:
        """
        QA sanity check on translated text:
        - Must have content
        - Must not have significant residual Chinese/Han characters
        """
        if not text or len(text.strip()) < 10:
            return False, "Translated text is too short or empty"

        hanzi_count = sum(1 for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
        if hanzi_count > 15:
            return False, f"Translation contains {hanzi_count} un-translated Hanzi characters"

        return True, "OK"

    def translate_chapter(
        self,
        work_id: str,
        chapter: ChapterCheckpoint,
        source_lang: str = "zh",
        max_retries: int = 3,
    ) -> ChapterCheckpoint:
        """
        Translates a single chapter with multi-account failover and idempotency.
        """
        # 1. Deduplication: Check if already translated with same hash
        if self.state_store.has_translated_chapter(work_id, chapter.source_order, chapter.source_text_hash):
            return chapter

        tried_accounts: Set[str] = set()
        last_error = ""

        chapter.state = ChapterState.TRANSLATING
        chapter.updated_at = now_iso()

        for attempt in range(max_retries):
            acc = self.pool.acquire_account(exclude=tried_accounts)
            if not acc:
                last_error = "No available accounts in translation pool (all busy or in cooldown)"
                break

            tried_accounts.add(acc)
            chapter.translation_attempts += 1
            chapter.last_translation_account = acc

            try:
                vi_title, vi_text = self.engine.translate_chapter(
                    text=chapter.source_text,
                    title=chapter.source_title,
                    source_lang=source_lang,
                    account_name=acc
                )
                valid, qa_msg = self.validate_vietnamese_output(vi_text)
                if not valid:
                    raise TranslationError(f"QA check failed: {qa_msg}", is_rate_limit=False)

                # Translation succeeded
                self.pool.release_account(acc, success=True)
                chapter.translated_title = vi_title
                chapter.translated_text = vi_text
                chapter.translated_text_hash = hashlib.sha256(vi_text.encode("utf-8")).hexdigest()
                chapter.state = ChapterState.TEXT_READY
                chapter.error_message = None
                chapter.updated_at = now_iso()
                return chapter

            except TranslationError as exc:
                self.pool.release_account(acc, success=False, error_message=str(exc))
                last_error = str(exc)
                continue
            except Exception as exc:
                self.pool.release_account(acc, success=False, error_message=str(exc))
                last_error = f"Unexpected error on {acc}: {exc}"
                continue

        # All retries failed
        chapter.state = ChapterState.FAILED
        chapter.error_message = f"Translation failed after {chapter.translation_attempts} attempts. Last error: {last_error}"
        chapter.updated_at = now_iso()
        return chapter

    def translate_work(
        self,
        work: WorkCheckpoint,
        source_lang: str = "zh",
        max_retries_per_chapter: int = 3,
        chapter_callback: Optional[Callable[[ChapterCheckpoint], None]] = None
    ) -> WorkCheckpoint:
        """
        Translates all chapters of a work sequentially or incrementally.
        Updates and persists state checkpoint after every single chapter.
        """
        work.state = WorkState.TRANSLATING
        self.state_store.save_work(work)

        for order, ch in sorted(work.chapters.items(), key=lambda x: x[0]):
            updated_ch = self.translate_chapter(
                work_id=work.work_id,
                chapter=ch,
                source_lang=source_lang,
                max_retries=max_retries_per_chapter
            )
            work.chapters[order] = updated_ch
            self.state_store.save_work(work)

            if chapter_callback:
                chapter_callback(updated_ch)

        work.refresh_work_state()
        self.state_store.save_work(work)
        return work

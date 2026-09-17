"""
Kiem thu toan dien cho FANFIC WORLD — LONG-FORM STORY RELIABILITY V1.

Bao dam cac BAT BIEN cot loi:
1. TEXT INVARIANT:
   - Tac pham chi dat READY khi ban phuc vu chua day du 100% van ban goc (0 ky tu bi mat).
   - So chuong phuc vu > 0 va khong co chuong nao vuot FAS_MAX_CHAPTER_CHARS.
   - Khong co cat xen am tham (silent truncation).
2. ORPHAN INVARIANT:
   - Van ban rong hoac khong hop le bi tu choi TRUOC KHI tao ban ghi novel/chapter tren Appwrite.
   - Khong bao gio tao mot novel co 0 chuong.
3. IDEMPOTENCY INVARIANT:
   - Thu lai sau khi bi gian doan (interruption) khong sinh ban trung novel hay chapter.
   - Xuat ban do (partial) co the tiep tuc (resume) chu khong danh dau READY nua voi.
4. AUDIO INVARIANT:
   - Truyen nhieu chuong khong bao gio bi danh dau hoan tat audio chi vi chuong 1 co audio.
   - Text READY duoc tach biet khoi TTS completion.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional
import unittest
from unittest import mock

from server.farmer.canonical import (
    ARTIFACT_BACKGROUND,
    ARTIFACT_COVER,
    ARTIFACT_MANIFEST,
    ARTIFACT_TEXT,
    BUCKET_FANFIC_TTS,
    DECISION_APPROVE,
    PRODUCTION_ROOT,
    WorkManifest,
)
from server.farmer.covers import CoverGate
from server.farmer.dedup import DedupIndex, FARMER_OWNER, LANE_TEXT
from server.farmer.drive_archive import ARCHIVE_DONE, ArchiveOutcome
from server.farmer.loop import Candidate, ProductionFarmer
from server.farmer.metrics import MetricsWriter
from server.farmer.production_writer import ProductionWriter
from server.farmer.quotas import FarmerQuotas
from server.farmer.review import QualityReviewer
from server.farmer.review_provider import ReviewPending, ReviewProvider
from server.llm_gateway.provider import LLMCompletion
from server.farmer.story_text import (
    FetchedStoryText,
    PreflightError,
    PreparedChapter,
    PreparedStoryPlan,
    SourceChapter,
    prepare_story_plan,
    split_chapter_content,
    verify_served_novel,
    PRODUCTION_TEXT_EMPTY,
    PRODUCTION_CHAPTER_LIMIT_INVALID,
)
from server.story_limits import DEFAULT_MAX_CHAPTER_CHARS


class _MockProvider:
    """Provider danh gia luon approve."""

    def __init__(self, score: int = 85, verdict: str = "approve"):
        self.calls = 0
        self._score = score
        self._verdict = verdict

    def complete(self, *, system, user, model, max_output_tokens):
        self.calls += 1
        return LLMCompletion(
            text=f'{{"score": {self._score}, "verdict": "{self._verdict}",'
                 f' "reasons": ["mach lac", "du dai"], "language": "vi"}}',
            provider_name="gemini",
            model=model,
        )


def _mock_covers():
    gate = mock.Mock(spec=CoverGate)
    gate.ensure_cover.return_value = mock.Mock(asset_id="ast_mock", reused=False)
    gate.assert_publishable.return_value = "ast_mock"
    return gate


class _InMemoryStore:
    """Store gia lap Appwrite day du cho cac phep kiem truyen nhieu chuong va TTS."""

    def __init__(self):
        self.novels: List[Any] = []
        self.chapters: Dict[str, List[Any]] = {}  # novel_id -> list of chapters
        self.jobs: Dict[str, List[Any]] = {}      # chapter_id -> list of jobs
        self.queue: Dict[str, Any] = {}

    def get_queue_item(self, item_id):
        raise KeyError(item_id)

    def find_novels(self, owner_id=None, limit=None, **kw):
        filtered = [n for n in self.novels if owner_id is None or getattr(n, "owner_id", FARMER_OWNER) == owner_id]
        return list(filtered), len(filtered)

    def list_chapters(self, novel_id: str):
        return list(self.chapters.get(novel_id, []))

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None):
        if chapter_id:
            return list(self.jobs.get(chapter_id, []))
        all_jobs = []
        for j_list in self.jobs.values():
            all_jobs.extend(j_list)
        return all_jobs


class TestSplittingAndPreflight(unittest.TestCase):
    """Kiem thu thuat toan cat chuong va preflight validation."""

    def test_empty_or_whitespace_raises_preflight_error(self):
        with self.assertRaises(PreflightError) as ctx:
            prepare_story_plan(FetchedStoryText.from_plain_text("   \n\n  \t "), title="Truyen Rong")
        self.assertEqual(ctx.exception.code, PRODUCTION_TEXT_EMPTY)

    def test_single_chapter_within_limit_preserved_exactly(self):
        text = "Doan van mau 1.\n\nDoan van mau 2.\n\nKet thuc.\n"
        plan = prepare_story_plan(FetchedStoryText.from_plain_text(text), title="Truyen Ngan", max_chars=1000)
        self.assertEqual(len(plan.chapters), 1)
        self.assertEqual(plan.chapters[0].content, text)
        self.assertEqual(plan.chapters[0].order_index, 1)
        self.assertEqual(plan.total_chars, len(text))

    def test_exact_limit_not_split(self):
        limit = 500
        text = "A" * limit
        chunks = split_chapter_content(text, max_chars=limit)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_limit_plus_one_splits_cleanly_without_loss(self):
        limit = 80
        part1 = "Day la doan thu nhat cua cau chuyen rat dai."
        part2 = "Day la doan thu hai tiep tuc noi dung doan mot."
        full_text = f"{part1}\n\n{part2}"
        self.assertGreater(len(full_text), limit)

        chunks = split_chapter_content(full_text, max_chars=limit)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), full_text)
        for chk in chunks:
            self.assertLessEqual(len(chk), limit)

    def test_250k_chars_splits_safely_with_zero_loss(self):
        # Tao van ban dai 250.000 ky tu gom nhieu doan van va cau
        paragraph = "Day la mot doan van fanfic mau voi nhieu tinh tiet phong phu va loi van cuon hut. " * 10 + "\n\n"
        full_text = paragraph * 300  # khoang ~270.000 ky tu
        limit = 50_000

        chunks = split_chapter_content(full_text, max_chars=limit)
        self.assertGreater(len(chunks), 4)
        self.assertEqual("".join(chunks), full_text, "Khong duoc mat bat ky ky tu nao!")
        for i, chk in enumerate(chunks, 1):
            self.assertLessEqual(len(chk), limit, f"Chunk {i} vuot gioi han {limit} ky tu")

    def test_priority_cascade_preserves_structure(self):
        # 1. Paragraph boundary (\n\n)
        p1 = "Doan 1 gom vai cau."
        p2 = "Doan 2 gom vai cau nua."
        t1 = f"{p1}\n\n{p2}"
        c1 = split_chapter_content(t1, max_chars=len(p1) + 2)
        self.assertEqual("".join(c1), t1)

        # 2. Line boundary (\n)
        l1 = "Dong thu nhat."
        l2 = "Dong thu hai."
        t2 = f"{l1}\n{l2}"
        c2 = split_chapter_content(t2, max_chars=len(l1) + 2)
        self.assertEqual("".join(c2), t2)

        # 3. Sentence boundary (.!?)
        s1 = "Cau thu nhat rat dai va day du."
        s2 = "Cau thu hai cung rat day du va ro rang."
        t3 = f"{s1} {s2}"
        c3 = split_chapter_content(t3, max_chars=len(s1) + 2)
        self.assertEqual("".join(c3), t3)

        # 4. Hard character boundary
        t4 = "A" * 150
        c4 = split_chapter_content(t4, max_chars=60)
        self.assertEqual(len(c4), 3)
        self.assertEqual("".join(c4), t4)


    def test_invalid_max_chars_rejected(self):
        with self.assertRaises(PreflightError) as ctx:
            split_chapter_content("Nội dung", max_chars=0)
        self.assertEqual(ctx.exception.code, PRODUCTION_CHAPTER_LIMIT_INVALID)


class TestMultiChapterStoryPlan(unittest.TestCase):
    """Kiem thu ke hoach truyen nhieu chuong va FanFicFare integration."""

    def test_fanficfare_source_chapters_preserved(self):
        source_chapters = [
            SourceChapter(title="Hồi 1: Khởi đầu", content="Nội dung chương 1.", order_index=1),
            SourceChapter(title="Hồi 2: Biến cố", content="Nội dung chương 2.", order_index=2),
            SourceChapter(title="Hồi 3: Hồi kết", content="Nội dung chương 3.", order_index=3),
        ]
        fetched = FetchedStoryText.from_source_chapters(source_chapters)
        plan = prepare_story_plan(fetched, title="Đại Tác Phẩm", max_chars=10_000)

        self.assertEqual(len(plan.chapters), 3)
        self.assertEqual([c.title for c in plan.chapters],
                         ["Hồi 1: Khởi đầu", "Hồi 2: Biến cố", "Hồi 3: Hồi kết"])
        self.assertEqual([c.order_index for c in plan.chapters], [1, 2, 3])

    def test_oversized_source_chapter_splits_into_subchapters(self):
        c1 = SourceChapter(title="Chương 1", content="Nội dung bình thường\n", order_index=1)
        # c2 vuot gioi han 100 ky tu
        c2_text = "Nội dung phần đầu của chương 2 rất dài.\n\nNội dung phần sau của chương 2 cũng rất dài.\n"
        c2 = SourceChapter(title="Chương 2", content=c2_text, order_index=2)
        c3 = SourceChapter(title="Chương 3", content="Nội dung kết\n", order_index=3)

        fetched = FetchedStoryText.from_source_chapters([c1, c2, c3])
        plan = prepare_story_plan(fetched, title="Truyện Có Chương Dài", max_chars=60)

        self.assertGreater(len(plan.chapters), 3)
        self.assertEqual(plan.chapters[0].title, "Chương 1")
        self.assertEqual(plan.chapters[0].order_index, 1)

        # Chuong 2 phai duoc chia thanh 2 sub-chapters co danh so (1/2) va (2/2)
        self.assertTrue(plan.chapters[1].title.startswith("Chương 2 (1/"))
        self.assertTrue(plan.chapters[2].title.startswith("Chương 2 (2/"))
        self.assertEqual(plan.chapters[1].order_index, 2)
        self.assertEqual(plan.chapters[2].order_index, 3)

        # Chuong 3 phai co order_index tiep theo
        self.assertEqual(plan.chapters[3].title, "Chương 3")
        self.assertEqual(plan.chapters[3].order_index, 4)

        # Tong van ban khong he bi mat mot ky tu nao
        self.assertEqual(
            "".join(c.content for c in plan.chapters),
            f"{c1.content}{c2.content}{c3.content}",
        )

    def test_served_novel_verification(self):
        plan = PreparedStoryPlan(
            chapters=[
                PreparedChapter(title="Chương 1", content="Nội dung 1", order_index=1),
                PreparedChapter(title="Chương 2", content="Nội dung 2", order_index=2),
            ],
            total_chars=18,
            review_text="Nội dung 1\n\nNội dung 2",
        )

        # 1. Verification hop le
        valid_novel_data = {
            "novel": {"novel_id": "nov_123"},
            "chapters": [
                {"order_index": 1, "title": "Chương 1", "content": "Nội dung 1"},
                {"order_index": 2, "title": "Chương 2", "content": "Nội dung 2"},
            ],
        }
        # Khong nem loi
        verify_served_novel(valid_novel_data, plan, max_chars=100)

        # 2. Thieu chuong
        missing_chapter_data = {
            "chapters": [{"order_index": 1, "title": "Chương 1", "content": "Nội dung 1"}],
        }
        with self.assertRaises(PreflightError):
            verify_served_novel(missing_chapter_data, plan, max_chars=100)

        # 3. Noi dung bi cat xen
        truncated_data = {
            "chapters": [
                {"order_index": 1, "title": "Chương 1", "content": "Nội dung"},  # mat ' 1'
                {"order_index": 2, "title": "Chương 2", "content": "Nội dung 2"},
            ],
        }
        with self.assertRaises(PreflightError):
            verify_served_novel(truncated_data, plan, max_chars=100)

        # 4. Chuong vuot gioi han
        with self.assertRaises(PreflightError):
            verify_served_novel(valid_novel_data, plan, max_chars=5)


class TestCanonicalManifestInvariants(unittest.TestCase):
    """Kiem thu cac bat bien READY tren WorkManifest."""

    def _manifest_chuan(self, **kwargs) -> WorkManifest:
        base = {
            "work_id": "w_123",
            "bucket": BUCKET_FANFIC_TTS,
            "canonical_dir": f"{PRODUCTION_ROOT}/{BUCKET_FANFIC_TTS}/slug-w_123",
            "decision": DECISION_APPROVE,
            "artifacts": {
                ARTIFACT_COVER: "cover.webp",
                ARTIFACT_BACKGROUND: "bg.webp",
                ARTIFACT_TEXT: "text.txt",
            },
            "chapter_count": 1,
            "intended_chapter_count": 1,
            "served_verified": True,
            "audio_status": "pending",
        }
        base.update(kwargs)
        return WorkManifest(**base)

    def test_approved_with_artwork_and_zero_chapters_is_not_ready(self):
        """APPROVED + ARTWORK + NOVEL WITH ZERO CHAPTERS != READY"""
        man = self._manifest_chuan(chapter_count=0)
        self.assertFalse(man.publishable())

    def test_approved_with_artwork_and_partial_chapters_is_not_ready(self):
        """APPROVED + ARTWORK + PARTIAL CHAPTER SET != READY"""
        man = self._manifest_chuan(chapter_count=1, intended_chapter_count=3)
        self.assertFalse(man.publishable())

    def test_unverified_serving_is_not_ready(self):
        man = self._manifest_chuan(served_verified=False)
        self.assertFalse(man.publishable())

    def test_audio_decoupled_from_text_ready(self):
        """Multi-chapter text is READY even if audio is still pending."""
        man = self._manifest_chuan(chapter_count=3, intended_chapter_count=3, served_verified=True, audio_status="pending")
        self.assertTrue(man.publishable())

    def test_legacy_manifest_roundtrip_compatibility(self):
        """Manifest cu schema_version=1 khong co cac truong moi van load thanh cong."""
        legacy_data = {
            "schema_version": 1,
            "work_id": "w_legacy",
            "bucket": BUCKET_FANFIC_TTS,
            "canonical_dir": "FanficWorld/production/fanfic-tts/legacy-w_legacy",
            "decision": "approve",
            "ready": True,
            "artifacts": {
                "artwork/cover.webp": "...",
                "artwork/background.webp": "...",
            },
        }
        man = WorkManifest.from_dict(legacy_data)
        self.assertEqual(man.chapter_count, 1)
        self.assertEqual(man.intended_chapter_count, 1)
        self.assertTrue(man.served_verified)
        self.assertEqual(man.audio_status, "none")
        self.assertEqual(man.tts_job_ids, [])

    def test_new_manifest_serialization_preserves_multi_chapter_and_tts(self):
        man = self._manifest_chuan(
            chapter_count=5,
            intended_chapter_count=5,
            served_verified=True,
            tts_job_ids=["job_1", "job_2", "job_3", "job_4", "job_5"],
            audio_status="in_progress",
        )
        d = man.as_dict()
        self.assertEqual(d["serving"]["chapter_count"], 5)
        self.assertEqual(d["serving"]["intended_chapter_count"], 5)
        self.assertTrue(d["serving"]["served_verified"])
        self.assertEqual(d["serving"]["audio_status"], "in_progress")
        self.assertEqual(d["serving"]["tts_job_ids"], ["job_1", "job_2", "job_3", "job_4", "job_5"])

        roundtrip = WorkManifest.from_dict(d)
        self.assertEqual(roundtrip.chapter_count, 5)
        self.assertEqual(roundtrip.intended_chapter_count, 5)
        self.assertTrue(roundtrip.served_verified)
        self.assertEqual(roundtrip.audio_status, "in_progress")
        self.assertEqual(roundtrip.tts_job_ids, ["job_1", "job_2", "job_3", "job_4", "job_5"])


class TestDedupAndAudioMultiChapter(unittest.TestCase):
    """Kiem thu dedup logic va audio invariant cho truyen nhieu chuong."""

    def test_novel_needs_tts_multi_chapter(self):
        store = _InMemoryStore()
        dedup = DedupIndex(store)

        # Tao novel gom 2 chuong
        ch1 = mock.Mock(chapter_id="ch_1", order_index=1)
        ch2 = mock.Mock(chapter_id="ch_2", order_index=2)
        store.chapters["nov_mc"] = [ch1, ch2]

        # Chua co job nao -> needs_tts = True
        self.assertTrue(dedup.novel_needs_tts("nov_mc"))

        # Chi co job cho chuong 1 -> van needs_tts = True!
        job1 = mock.Mock(job_id="job_1", chapter_id="ch_1", status="running", output_key="")
        store.jobs["ch_1"] = [job1]
        self.assertTrue(dedup.novel_needs_tts("nov_mc"))

        # Ca hai chuong deu co job -> needs_tts = False
        job2 = mock.Mock(job_id="job_2", chapter_id="ch_2", status="pending", output_key="")
        store.jobs["ch_2"] = [job2]
        self.assertFalse(dedup.novel_needs_tts("nov_mc"))

    def test_finished_tts_output_key_requires_all_chapters(self):
        """Audio Invariant: Multi-chapter novels must never be marked full audio complete because chapter 1 has a job."""
        store = _InMemoryStore()
        dedup = DedupIndex(store)

        ch1 = mock.Mock(chapter_id="ch_1", order_index=1)
        ch2 = mock.Mock(chapter_id="ch_2", order_index=2)
        store.chapters["nov_mc"] = [ch1, ch2]

        # Chuong 1 completed co output_key, nhung chuong 2 chua xong
        job1 = mock.Mock(job_id="job_1", chapter_id="ch_1", status="completed", output_key="audio/ch1.mp3")
        job2 = mock.Mock(job_id="job_2", chapter_id="ch_2", status="running", output_key=None)
        store.jobs["ch_1"] = [job1]
        store.jobs["ch_2"] = [job2]

        # Phai tra ve None, tuyet doi khong tra ve audio/ch1.mp3!
        self.assertIsNone(dedup.finished_tts_output_key("nov_mc"))

        # Khi ca 2 deu completed -> tra ve output_key hop le
        job2.status = "completed"
        job2.output_key = "audio/ch2.mp3"
        self.assertIsNotNone(dedup.finished_tts_output_key("nov_mc"))


class TestFarmerLongformReliabilityLoop(unittest.TestCase):
    """Kiem thu tich hop loop.py voi cac kich ban Test A toi Test K."""

    def _tao_harness(self, tmp_dir: Path, store: Optional[_InMemoryStore] = None,
                     fetch_func=None, max_chars=1000):
        store = store or _InMemoryStore()
        provider = _MockProvider()
        covers = _mock_covers()
        quotas = FarmerQuotas(
            max_concurrent_downloads=5,
            max_review_requests=50,
            max_tts_jobs=50,
            min_free_disk_bytes=1,
            work_dir=str(tmp_dir),
        )
        metrics = MetricsWriter(tmp_dir / "status.json")

        objects: Dict[str, bytes] = {}

        def put(key, data, content_type="application/octet-stream"):
            objects[key] = data

        def get(key):
            return objects[key]

        def tai_xuong(key, dest):
            Path(dest).write_bytes(b"mock_audio")

        def sinh_tranh(wid):
            return (b"COVER_BYTES", b"BG_BYTES")

        def luu_tru(path, *, work_key, timeout=300):
            return ArchiveOutcome(ARCHIVE_DONE, remote_path=f"fanfic-gdrive:{work_key}")

        writer = ProductionWriter(
            put_object=put,
            get_object=get,
            download_object=tai_xuong,
            generate_artwork=sinh_tranh,
            archive_file=luu_tru,
        )

        published_chapters: List[Dict[str, Any]] = []
        tts_enqueued: List[str] = []

        def default_publish(c: Candidate, plan_or_body: Any, novel_id: str = ""):
            # Gia lap publisher thong minh
            if not novel_id:
                novel_id = f"nov_{len(store.novels) + 1}"
                store.novels.append(mock.Mock(novel_id=novel_id, external_source_url=c.url, owner_id=FARMER_OWNER))
                store.chapters[novel_id] = []

            chapters = getattr(plan_or_body, "chapters", None)
            if not chapters:
                chapters = [PreparedChapter(title=c.title or "Chương 1", content=str(plan_or_body), order_index=1)]

            existing_orders = {ch.order_index for ch in store.chapters[novel_id]}
            for ch in chapters:
                if ch.order_index not in existing_orders:
                    ch_mock = mock.Mock(
                        chapter_id=f"{novel_id}_ch_{ch.order_index}",
                        novel_id=novel_id,
                        title=ch.title,
                        content=ch.content,
                        order_index=ch.order_index,
                    )
                    store.chapters[novel_id].append(ch_mock)
                    published_chapters.append({
                        "novel_id": novel_id,
                        "chapter_id": ch_mock.chapter_id,
                        "order_index": ch.order_index,
                        "content": ch.content,
                    })
            return novel_id

        def default_enqueue_tts(novel_id: str):
            tts_enqueued.append(novel_id)
            job_ids = []
            for ch in store.chapters.get(novel_id, []):
                job_id = f"job_{ch.chapter_id}"
                if ch.chapter_id not in store.jobs:
                    store.jobs[ch.chapter_id] = [mock.Mock(job_id=job_id, status="pending", output_key="")]
                job_ids.append(job_id)
            return job_ids

        default_fetch = fetch_func or (lambda c: "Noi dung truyen dai hop le de duyet " * 10)

        farmer = ProductionFarmer(
            store=store,
            quotas=quotas,
            reviewer=QualityReviewer(provider, min_score=70),
            cover_gate=covers,
            metrics_writer=metrics,
            discover_audio=lambda n: [],
            discover_text=lambda n: [],
            fetch_text=default_fetch,
            publish_text=default_publish,
            enqueue_tts=default_enqueue_tts,
            enqueue_audio_item=lambda c: None,
            production_writer=writer,
            batch_per_lane=10,
            max_chapter_chars=max_chars,
        )

        return farmer, store, writer, objects, published_chapters, tts_enqueued

    def test_a_empty_text_creates_no_novel_and_no_ready(self):
        """Test A: Van ban rong bi chan ngay tu preflight, khong tao novel, khong co manifest."""
        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: "    \n\n\t   "
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/empty", title="Truyen Rong")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.failed, 1)
            self.assertEqual(m.produced, 0)
            self.assertEqual(m.published_candidates, 0)
            self.assertEqual(len(store.novels), 0, "Orphan Invariant: Khong duoc tao novel!")
            self.assertEqual(len(published_ch), 0)
            self.assertFalse(any(k.endswith("manifest.json") for k in objects))
            self.assertTrue(any("PRODUCTION_TEXT_EMPTY" in err for err in m.errors))

    def test_b_50k_characters_single_chapter_exact_content(self):
        """Test B: 50k ky tu (duoi tran 100k) xuat ban thanh 1 chuong, 100% ky tu bao toan."""
        from server.farmer.production_writer import normalize_text
        body = "Doan van mau cua tac pham fanfic chat luong cao.\n\n" * 1000  # ~49.000 ky tu
        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: body, max_chars=100_000
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/50k", title="Truyen 50k")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)
            self.assertEqual(len(store.novels), 1)
            self.assertEqual(len(published_ch), 1)
            self.assertEqual(published_ch[0]["content"], normalize_text(body))

            # Manifest phai hop le va READY
            manifest_keys = [k for k in objects if k.endswith("manifest.json") and "manifests/" not in k]
            self.assertEqual(len(manifest_keys), 1)
            man_data = json.loads(objects[manifest_keys[0]])
            self.assertTrue(man_data["ready"])
            self.assertEqual(man_data["serving"]["chapter_count"], 1)

    def test_c_exact_max_chapter_chars_accepted(self):
        """Test C: Dung FAS_MAX_CHAPTER_CHARS khong bi cat."""
        limit = 5000
        body = "A" * (limit - 1) + "\n"
        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: body, max_chars=limit
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/exact", title="Truyen Dung Tran")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(len(published_ch), 1)
            self.assertEqual(len(published_ch[0]["content"]), limit)

    def test_d_max_plus_one_splits_into_two_chapters_no_loss(self):
        """Test D: Tran + 1 ky tu -> chia thanh 2 chuong hop le, 0 ky tu bi mat."""
        from server.farmer.production_writer import normalize_text
        limit = 1000
        part1 = "Day la phan thu nhat cua chuong truyen. " * 20  # ~800 ky tu
        part2 = "Day la phan thu hai tiep noi cau chuyen. " * 10   # ~400 ky tu
        body = f"{part1}\n\n{part2}"
        self.assertGreater(len(body), limit)

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: body, max_chars=limit
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/split2", title="Truyen 2 Chuong")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)
            self.assertEqual(len(published_ch), 2)
            self.assertEqual(published_ch[0]["order_index"], 1)
            self.assertEqual(published_ch[1]["order_index"], 2)
            self.assertEqual("".join(c["content"] for c in published_ch), normalize_text(body))

            # Manifest phai ghi nhan chapter_count=2
            manifest_keys = [k for k in objects if k.endswith("manifest.json") and "manifests/" not in k]
            man_data = json.loads(objects[manifest_keys[0]])
            self.assertTrue(man_data["ready"])
            self.assertEqual(man_data["serving"]["chapter_count"], 2)
            self.assertEqual(man_data["serving"]["intended_chapter_count"], 2)

    def test_e_250k_chars_splits_into_multiple_chapters_safely(self):
        """Test E: 250k+ ky tu duoc chia thanh nhieu chuong <= limit, tat ca chuong duoc tao."""
        from server.farmer.production_writer import normalize_text
        paragraph = "Mot doan van mau rat dai ve chuyen luu lac cua nhan vat chinh trong the gioi fanfic. " * 5 + "\n\n"
        body = paragraph * 500  # ~240.000+ ky tu
        limit = 50_000

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: body, max_chars=limit
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/250k", title="Truyen Rat Dai")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)
            self.assertGreater(len(published_ch), 4)
            self.assertEqual("".join(c["content"] for c in published_ch), normalize_text(body))
            for c in published_ch:
                self.assertLessEqual(len(c["content"]), limit)

    def test_f_fanficfare_multichapter_preserves_boundaries(self):
        """Test F: Nguon FanFicFare co san nhieu chuong thi giu nguyen chuong goc."""
        source_chapters = [
            SourceChapter(title="Chương I", content="Nội dung chương một.", order_index=1),
            SourceChapter(title="Chương II", content="Nội dung chương hai.", order_index=2),
            SourceChapter(title="Chương III", content="Nội dung chương ba.", order_index=3),
        ]
        fetched = FetchedStoryText.from_source_chapters(source_chapters)

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: fetched, max_chars=10_000
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/fff_multi", title="Fanfic Da Chuong")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)
            self.assertEqual(len(published_ch), 3)
            self.assertEqual([c["content"] for c in published_ch],
                             ["Nội dung chương một.\n", "Nội dung chương hai.\n", "Nội dung chương ba.\n"])

    def test_g_oversized_source_chapter_splits_in_loop(self):
        """Test G: Chuong nguon vuot gioi han thi tu dong chia nho thanh subchapters trong vong lap."""
        c1 = SourceChapter(title="Chương 1", content="Nội dung chương 1.\n", order_index=1)
        c2 = SourceChapter(title="Chương 2", content="Phần một của chương hai rất dài.\n\nPhần hai của chương hai cũng rất dài.\n", order_index=2)
        fetched = FetchedStoryText.from_source_chapters([c1, c2])

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: fetched, max_chars=45
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/fff_split", title="Fanfic Chia Nho")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)
            self.assertEqual(len(published_ch), 3)
            self.assertEqual(published_ch[0]["order_index"], 1)
            self.assertEqual(published_ch[1]["order_index"], 2)
            self.assertEqual(published_ch[2]["order_index"], 3)
            self.assertTrue(published_ch[1]["content"].startswith("Phần một"))

    def test_h_and_j_interrupted_publication_resumes_cleanly(self):
        """Test H + J: Gian doan sau khi tao chuong K -> lan chay sau tiep tuc tu K+1 ma khong tao duplicate novel hay chapter."""
        body = "Doan 1 rat dai cua chuong 1.\n\nDoan 2 rat dai cua chuong 2.\n\nDoan 3 rat dai cua chuong 3."
        # Limit de chia thanh 3 chuong
        limit = 35

        store = _InMemoryStore()
        url = "https://e.com/resume_me"
        candidate = Candidate(lane=LANE_TEXT, url=url, title="Truyen Chay Tiep")

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), store=store, fetch_func=lambda c: body, max_chars=limit
            )
            farmer._discover_text = lambda n: [candidate]

            # Gia lap gian doan: lan 1 tao novel va chi moi tao chuong 1 roi nem loi mang
            novel_id = "nov_dang_do"
            store.novels.append(mock.Mock(novel_id=novel_id, external_source_url=url, owner_id=FARMER_OWNER))
            # Chuong 1 da co
            ch1_mock = mock.Mock(chapter_id="ch_1", novel_id=novel_id, title="Truyen Chay Tiep (1/3)", content="Doan 1 rat dai cua chuong 1.", order_index=1)
            store.chapters[novel_id] = [ch1_mock]

            # Chay text lane
            m = farmer.run_text_lane()

            # Phai nhan biet novel_dang_do, tiep tuc tao chuong 2 va 3
            self.assertEqual(m.resumed, 1)
            self.assertEqual(m.produced, 1)
            self.assertEqual(m.published_candidates, 1)

            # Kiem tra tong so chuong trong store la 3 (khong tao trung chuong 1)
            store_chapters = store.chapters[novel_id]
            self.assertEqual(len(store_chapters), 3)
            self.assertEqual([ch.order_index for ch in store_chapters], [1, 2, 3])

            # Novel chi co 1 trong store (khong tao novel moi)
            self.assertEqual(len(store.novels), 1)

    def test_i_existing_novel_with_zero_chapters_is_blocked(self):
        """Test I: Ban nhap cu ton tai nhung khong co chuong nao thi bi chan, khong duoc dat READY."""
        store = _InMemoryStore()
        url = "https://e.com/zero_ch"
        candidate = Candidate(lane=LANE_TEXT, url=url, title="Truyen Khong Chuong")

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), store=store, fetch_func=lambda c: "Noi dung hop le " * 10
            )
            farmer._discover_text = lambda n: [candidate]

            # Novel co san nhung chapters rong
            store.novels.append(mock.Mock(novel_id="nov_rong", external_source_url=url, owner_id=FARMER_OWNER))
            store.chapters["nov_rong"] = []

            m = farmer.run_text_lane()

            self.assertEqual(m.failed, 1)
            self.assertEqual(m.resumed, 0)
            self.assertEqual(m.published_candidates, 0)
            self.assertTrue(any("khong co chuong nao" in e for e in m.errors))
            self.assertFalse(any(k.endswith("manifest.json") for k in objects))

    def test_k_multi_chapter_tts_queues_all_chapters(self):
        """Test K: TTS cho truyen nhieu chuong phai tao job cho TAT CA cac chuong, khong chi chuong 1."""
        body = "Doan 1 cho chuong 1.\n\nDoan 2 cho chuong 2.\n\nDoan 3 cho chuong 3."
        limit = 25

        with TemporaryDirectory() as d:
            farmer, store, writer, objects, published_ch, tts = self._tao_harness(
                Path(d), fetch_func=lambda c: body, max_chars=limit
            )
            candidate = Candidate(lane=LANE_TEXT, url="https://e.com/multi_tts", title="Truyen Nhieu TTS")
            farmer._discover_text = lambda n: [candidate]

            m = farmer.run_text_lane()

            self.assertEqual(m.produced, 1)
            novel_id = store.novels[0].novel_id
            self.assertEqual(len(store.chapters[novel_id]), 3)

            # Kiem tra ca 3 chuong deu da duoc tao job TTS
            for ch in store.chapters[novel_id]:
                self.assertIn(ch.chapter_id, store.jobs)
                self.assertEqual(len(store.jobs[ch.chapter_id]), 1)


if __name__ == "__main__":
    unittest.main()

"""Chinese Media Orchestrator — ban tieu thu `content_queue`.

Khong Appwrite, khong R2, khong HTTP: store la ban gia trong bo nho, con moi
ham cong doan cua `chinese_media_pipeline` deu duoc mock theo dung quy uoc
hang xom (`mock.patch.object(<module>, ...)` tren ten o cap module — giong
`test_chinese_media_pipeline_ship_draft.py` va `test_chinese_media_dub_fix.py`).

Cac bat bien duoc bao ve o day, theo thu tu quan trong:

1. **ASR khong bao gio chay lai** khi `transcript_key` da co — day la ly do
   ton tai cua ca tep orchestrator.
2. **PENDING khac FAILED**: mot muc dung lai vi thieu media do nguoi van hanh
   cung cap KHONG bi cong `attempts` (neu cong, no se dung han im lang sau
   `--max-attempts` lan chay khong lam gi ca).
3. **Cong quyen render**: rights_mode khac REHOST_ALLOWED luon SKIPPED, khong
   co duong nao vong qua.
4. **Tien dieu kien**: khong cong doan nao chay truoc khi cong doan truoc no
   xong.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chinese_media_orchestrator as orch  # noqa: E402
import chinese_media_pipeline as pipeline  # noqa: E402
from server.domain import ChineseMediaQueueItem  # noqa: E402


class FakeStore:
    """Chi ba phuong thuc hang doi ma orchestrator dung, dung chu ky that cua
    `AppwriteMetadataStore`."""

    def __init__(self, items=()):
        self.items = {i.item_id: i for i in items}
        self.updates: list = []

    def list_queue_items_by_state(self, *, stage, state, limit=50, offset=0):
        out = [i for i in self.items.values() if getattr(i, stage) == state]
        return out[offset:offset + limit]

    def get_queue_item(self, item_id):
        return self.items[item_id]

    def update_queue_item(self, item_id, **fields):
        self.updates.append((item_id, dict(fields)))
        item = self.items[item_id]
        for key, value in fields.items():
            if hasattr(item, key):
                setattr(item, key, value)
        return item


def make_item(**overrides) -> ChineseMediaQueueItem:
    base = dict(
        item_id="cmq_test0001", source_id="bobo_manju", platform="youtube",
        series_slug="bobo_manju", episode_ref="vid123", title="Tap 1",
        source_url="https://www.youtube.com/watch?v=vid123",
        rights_mode="REFERENCE_ONLY",
    )
    base.update(overrides)
    return ChineseMediaQueueItem(**base)


def segments(n=2, translated=False):
    return [
        pipeline.Segment(start=float(i), end=float(i) + 1.0, zh_text=f"zh{i}",
                         vi_text=(f"vi{i}" if translated else ""))
        for i in range(n)
    ]


class TranscriptCheckpointTest(unittest.TestCase):
    """Bat bien #1 — cai dat gia nhat cua ca duong day khong duoc chay lai."""

    def test_existing_transcript_key_never_reruns_asr(self):
        item = make_item(transcript_key="transcripts/svc_harvester/cmq_test0001.json")
        ctx = orch.Context(store=FakeStore([item]))

        with mock.patch.object(pipeline, "transcribe_mandarin") as asr, \
             mock.patch.object(pipeline, "find_source_captions") as captions, \
             mock.patch.object(orch, "exists_in_r2") as exists:
            outcome = orch.precheck_transcript(ctx, item)

        self.assertEqual(outcome.state, "DONE")
        asr.assert_not_called()
        captions.assert_not_called()
        exists.assert_not_called()

    def test_orphaned_r2_checkpoint_is_recovered_instead_of_rerunning_asr(self):
        """Khe cua so that: ASR xong, transcript da len R2, tien trinh chet
        TRUOC khi ghi `transcript_key`. Vi khoa tat dinh, lan sau phai nhat
        lai chu khong duoc chay lai 35-90 phut ASR."""
        item = make_item()   # transcript_key rong
        ctx = orch.Context(store=FakeStore([item]))

        with mock.patch.object(orch, "exists_in_r2", return_value=True) as exists, \
             mock.patch.object(orch, "download_from_r2",
                               return_value=orch.segments_to_json(segments(5))), \
             mock.patch.object(pipeline, "transcribe_mandarin") as asr:
            outcome = orch.precheck_transcript(ctx, item)

        asr.assert_not_called()
        exists.assert_called_once_with("transcripts/svc_harvester/cmq_test0001.json")
        self.assertEqual(outcome.state, "DONE")
        self.assertEqual(outcome.fields["transcript_key"],
                         "transcripts/svc_harvester/cmq_test0001.json")

    def test_a_corrupt_r2_checkpoint_is_not_adopted(self):
        """Tin vao moi su TON TAI la mot cai bay khong loi ra: `transcript_key`
        duoc dat nen ASR khong bao gio chay lai, con moi cong doan sau deu chet
        khi doc object hong."""
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]),
                           audio={item.item_id: Path(__file__)})

        for label, payload in (("hong", b"khong-phai-json"),
                               ("rong", orch.segments_to_json([]))):
            with self.subTest(payload=label):
                with mock.patch.object(orch, "exists_in_r2", return_value=True), \
                     mock.patch.object(orch, "download_from_r2", return_value=payload):
                    outcome = orch.precheck_transcript(ctx, item)
                # Khong nhan bua la DONE -> duong ASR duoc mo lai.
                self.assertIsNone(outcome)

    def test_asr_result_is_checkpointed_to_transcript_key(self):
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]),
                           audio={item.item_id: Path(__file__)})  # tep that, ton tai

        with mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin",
                               return_value=segments(3)) as asr, \
             mock.patch.object(pipeline, "upload_to_r2") as up:
            outcome = orch.stage_transcript(ctx, item)

        asr.assert_called_once()
        self.assertEqual(outcome.state, "DONE")
        self.assertEqual(outcome.fields["transcript_key"],
                         "transcripts/svc_harvester/cmq_test0001.json")
        key, data, content_type = up.call_args[0]
        self.assertEqual(key, "transcripts/svc_harvester/cmq_test0001.json")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(len(json.loads(data.decode("utf-8"))["segments"]), 3)

    def test_checkpoint_roundtrip_preserves_timings_and_text(self):
        original = segments(4, translated=True)
        restored = orch.segments_from_json(orch.segments_to_json(original))
        self.assertEqual([(s.start, s.end, s.zh_text, s.vi_text) for s in restored],
                         [(s.start, s.end, s.zh_text, s.vi_text) for s in original])


class BlockedIsNotFailedTest(unittest.TestCase):
    """Bat bien #2 — cho dau vao nguoi van hanh khong duoc tieu mat lan thu."""

    def test_missing_operator_media_stays_pending_and_costs_no_attempt(self):
        item = make_item()
        store = FakeStore([item])
        ctx = orch.Context(store=store)

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin") as asr:
            record = orch.run_stage(ctx, item, "transcript")

        asr.assert_not_called()
        self.assertEqual(record["state"], "PENDING")
        self.assertTrue(record["blocked"])
        self.assertEqual(item.attempts, 0)
        written = [f for _, f in store.updates if "attempts" in f]
        self.assertEqual(written, [], "muc bi chan khong duoc cong attempts")

    def test_blocked_stage_is_never_marked_running(self):
        """Mot muc bi chan KHONG duoc di qua RUNNING: mot lan sap tien trinh o
        giua se de no ket RUNNING vinh vien du no chua he chay gi."""
        item = make_item()
        store = FakeStore([item])
        ctx = orch.Context(store=store)

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None):
            orch.run_stage(ctx, item, "transcript")

        states = [f.get("transcript_state") for _, f in store.updates]
        self.assertNotIn("RUNNING", states,
                         f"khong duoc ghi RUNNING cho muc bi chan, da ghi: {states}")

    def test_real_failure_does_increment_attempts(self):
        item = make_item()
        store = FakeStore([item])
        ctx = orch.Context(store=store, audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin", return_value=[]):
            record = orch.run_stage(ctx, item, "transcript")

        self.assertEqual(record["state"], "FAILED")
        self.assertEqual(item.attempts, 1)

    def test_exception_becomes_failed_not_a_crash(self):
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]), audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin",
                               side_effect=RuntimeError("mang hong")):
            record = orch.run_stage(ctx, item, "transcript")

        self.assertEqual(record["state"], "FAILED")
        self.assertIn("RuntimeError", record["note"])
        self.assertEqual(item.attempts, 1)

    def test_last_error_distinguishes_waiting_from_broken(self):
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]))
        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None):
            orch.run_stage(ctx, item, "transcript")
        self.assertTrue(item.last_error.startswith("transcript: CHO: "),
                        f"phai gan ten cong doan va tien to CHO:, "
                        f"dang la {item.last_error!r}")

    def test_success_clears_only_its_own_stale_error(self):
        item = make_item(last_error="transcript: loi cu tu lan chay truoc")
        ctx = orch.Context(store=FakeStore([item]), audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin", return_value=segments(2)), \
             mock.patch.object(pipeline, "upload_to_r2"):
            record = orch.run_stage(ctx, item, "transcript")

        self.assertEqual(record["state"], "DONE")
        self.assertEqual(item.last_error, "")

    def test_a_success_never_erases_another_stages_error(self):
        """`last_error` la truong CUA CA MUC. Danh dau `render=SKIPPED` ma xoa
        mat loi dich se de lai mot muc chet khong con dau vet chan doan nao."""
        item = make_item(last_error="translation: moi dich duoc 9/10 doan",
                         translation_state="FAILED", attempts=3)
        ctx = orch.Context(store=FakeStore([item]))

        orch.process_item(ctx, item)   # cong quyen se danh dau render=SKIPPED

        self.assertEqual(item.render_state, "SKIPPED")
        self.assertEqual(item.last_error, "translation: moi dich duoc 9/10 doan")

    def test_a_successful_stage_resets_the_consecutive_failure_budget(self):
        """`attempts` la ngan sach cua CA MUC. Neu khong dat lai sau moi cong
        doan xong, mot loi ASR som cong mot loi dich muon se giet mot muc dang
        tien trien binh thuong."""
        item = make_item(attempts=2)
        ctx = orch.Context(store=FakeStore([item]), audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin", return_value=segments(2)), \
             mock.patch.object(pipeline, "upload_to_r2"):
            orch.run_stage(ctx, item, "transcript")

        self.assertEqual(item.attempts, 0)

    def test_max_attempts_stops_further_work(self):
        item = make_item(attempts=3)
        ctx = orch.Context(store=FakeStore([item]), max_attempts=3)

        with mock.patch.object(pipeline, "find_source_captions") as captions, \
             mock.patch.object(orch, "exists_in_r2") as exists:
            record = orch.run_stage(ctx, item, "transcript")

        captions.assert_not_called()
        exists.assert_not_called()
        self.assertTrue(record["skipped_by_orchestrator"])

    def test_a_concurrent_state_change_aborts_the_claim(self):
        """Doc lai truoc khi gianh viec: khong dong duoc dua that su (Appwrite
        khong co cap nhat co dieu kien) nhung phai bo qua duoc truong hop da
        nhin thay ro rang."""
        item = make_item()
        store = FakeStore([item])
        ctx = orch.Context(store=store, audio={item.item_id: Path(__file__)})

        moved = make_item(transcript_state="DONE")
        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(store, "get_queue_item", return_value=moved), \
             mock.patch.object(pipeline, "transcribe_mandarin") as asr:
            record = orch.run_stage(ctx, item, "transcript")

        asr.assert_not_called()
        self.assertTrue(record["skipped_by_orchestrator"])
        self.assertEqual(store.updates, [])


class RightsGateTest(unittest.TestCase):
    """Bat bien #3 — cong quyen, khong co duong nao vong qua."""

    def test_non_rehost_rights_modes_are_always_skipped(self):
        for mode in ("REFERENCE_ONLY", "EMBED_ONLY"):
            with self.subTest(rights_mode=mode):
                item = make_item(rights_mode=mode)
                outcome = orch.stage_render(orch.Context(store=FakeStore([item])), item)
                self.assertEqual(outcome.state, "SKIPPED")
                self.assertIn(mode, outcome.note)

    def test_rehost_allowed_is_not_auto_rendered_either(self):
        item = make_item(rights_mode="REHOST_ALLOWED")
        outcome = orch.stage_render(orch.Context(store=FakeStore([item])), item)
        self.assertEqual(outcome.state, "PENDING")
        self.assertTrue(outcome.blocked)

    def test_orchestrator_never_calls_a_media_download_path(self):
        """Compose la ham DUY NHAT trong pipeline cham vao media goc; khong
        cong doan nao cua orchestrator duoc goi no."""
        item = make_item(rights_mode="REHOST_ALLOWED", subtitle_state="DONE",
                         translation_state="DONE", transcript_state="DONE",
                         transcript_key="transcripts/svc_harvester/cmq_test0001.json")
        ctx = orch.Context(store=FakeStore([item]))
        with mock.patch.object(pipeline, "compose_with_source") as compose:
            orch.process_item(ctx, item)
        compose.assert_not_called()

    def test_rights_skip_is_applied_even_when_the_pipeline_is_stuck_early(self):
        """Phan quyet ban quyen khong phu thuoc tien do. Mot muc dang cho
        `--audio` van phai hien ro `render=SKIPPED` — neu khong, chinh sach
        nhin nhu chua he duoc ap va giao dien web sau nay se hieu sai."""
        item = make_item()  # REFERENCE_ONLY, moi cong doan PENDING
        ctx = orch.Context(store=FakeStore([item]))

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None):
            report = orch.process_item(ctx, item)

        self.assertEqual(item.render_state, "SKIPPED")
        self.assertEqual(item.transcript_state, "PENDING")
        render_step = next(s for s in report["steps"] if s["stage"] == "render")
        self.assertEqual(render_step["state"], "SKIPPED")


class StagePreconditionTest(unittest.TestCase):
    """Bat bien #4 — khong cong doan nao chay som."""

    def test_translation_requires_transcript_done(self):
        item = make_item(transcript_state="PENDING")
        self.assertIsNotNone(orch.unmet_requirement(item, "translation"))

    def test_draft_waits_for_dub_to_settle(self):
        item = make_item(subtitle_state="DONE", dub_state="PENDING")
        self.assertIsNotNone(orch.unmet_requirement(item, "draft"))
        for settled in ("DONE", "SKIPPED"):
            with self.subTest(dub_state=settled):
                item.dub_state = settled
                self.assertIsNone(orch.unmet_requirement(item, "draft"))

    def test_process_item_stops_at_first_unfinished_stage(self):
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]))
        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "translate_zh_to_vi") as translate:
            report = orch.process_item(ctx, item)
        translate.assert_not_called()
        # `render` di truoc: phan quyet ban quyen khong cho duong day chay toi.
        self.assertEqual([s["stage"] for s in report["steps"]],
                         ["render", "transcript"])

    def test_running_stage_is_left_alone(self):
        item = make_item(transcript_state="RUNNING")
        ctx = orch.Context(store=FakeStore([item]))
        with mock.patch.object(pipeline, "find_source_captions") as captions:
            report = orch.process_item(ctx, item)
        captions.assert_not_called()
        step = next(s for s in report["steps"] if s["stage"] == "transcript")
        self.assertTrue(step["skipped_by_orchestrator"])


class TranslationStageTest(unittest.TestCase):
    def test_already_translated_transcript_is_not_retranslated(self):
        item = make_item(transcript_key="k")
        ctx = orch.Context(store=FakeStore([item]))
        with mock.patch.object(orch, "download_from_r2",
                               return_value=orch.segments_to_json(segments(2, True))), \
             mock.patch.object(pipeline, "translate_zh_to_vi") as translate:
            outcome = orch.stage_translation(ctx, item)
        translate.assert_not_called()
        self.assertEqual(outcome.state, "DONE")

    def test_translation_writes_back_to_the_same_key(self):
        item = make_item(transcript_key="transcripts/svc_harvester/cmq_test0001.json")
        ctx = orch.Context(store=FakeStore([item]))

        def fake_translate(segs, *a, **kw):
            for i, s in enumerate(segs):
                s.vi_text = f"vi{i}"

        with mock.patch.object(orch, "download_from_r2",
                               return_value=orch.segments_to_json(segments(2))), \
             mock.patch.object(pipeline, "translate_zh_to_vi", side_effect=fake_translate), \
             mock.patch.object(pipeline, "upload_to_r2") as up:
            outcome = orch.stage_translation(ctx, item)

        self.assertEqual(outcome.state, "DONE")
        self.assertEqual(up.call_args[0][0], item.transcript_key)
        # zh_text phai con nguyen sau khi ghi de — do la dieu kien de resume.
        stored = orch.segments_from_json(up.call_args[0][1])
        self.assertEqual([s.zh_text for s in stored], ["zh0", "zh1"])

    def test_partial_translation_is_not_reported_as_done(self):
        """Dich thieu KHONG phai la xong. Neu danh DONE, cong doan phu de se
        lang le loc bo cac doan chua dich va cho ra ban phu de THIEU NOI DUNG,
        con cong doan dich thi khong bao gio chay lai nua."""
        item = make_item(transcript_key="k")
        ctx = orch.Context(store=FakeStore([item]))

        def translate_all_but_one(segs, *a, **kw):
            for i, s in enumerate(segs[:-1]):
                s.vi_text = f"vi{i}"

        with mock.patch.object(orch, "download_from_r2",
                               return_value=orch.segments_to_json(segments(10))), \
             mock.patch.object(pipeline, "translate_zh_to_vi",
                               side_effect=translate_all_but_one), \
             mock.patch.object(pipeline, "upload_to_r2") as up:
            outcome = orch.stage_translation(ctx, item)

        self.assertEqual(outcome.state, "FAILED")
        self.assertIn("9/10", outcome.note)
        # ...nhung phan da dich VAN phai duoc luu, de lan sau dich tiep.
        up.assert_called_once()
        stored = orch.segments_from_json(up.call_args[0][1])
        self.assertEqual(sum(1 for s in stored if s.vi_text), 9)


class DubStageTest(unittest.TestCase):
    def test_dub_disabled_is_skipped_not_failed(self):
        item = make_item(transcript_key="k")
        outcome = orch.precheck_dub(
            orch.Context(store=FakeStore([item]), dub_enabled=False), item)
        self.assertEqual(outcome.state, "SKIPPED")

    def test_missing_ffmpeg_blocks_rather_than_fails(self):
        item = make_item(transcript_key="k")
        ctx = orch.Context(store=FakeStore([item]), dub_enabled=True, ffmpeg="")
        outcome = orch.precheck_dub(ctx, item)
        self.assertEqual(outcome.state, "PENDING")
        self.assertTrue(outcome.blocked)


class DraftStageTest(unittest.TestCase):
    def test_draft_passes_deterministic_keys_to_ship_draft(self):
        item = make_item(subtitle_state="DONE", dub_state="DONE",
                         transcript_key="k")
        ctx = orch.Context(store=FakeStore([item]), token="tok")

        with mock.patch.object(orch, "download_from_r2", return_value=b"x"), \
             mock.patch.object(pipeline, "ship_draft", return_value="nov_1") as ship:
            outcome = orch.stage_draft(ctx, item)

        kwargs = ship.call_args.kwargs
        self.assertEqual(kwargs["subtitle_key"], "subtitles/svc_harvester/cmq_test0001.srt")
        self.assertEqual(kwargs["dub_key"], "dub_audio/svc_harvester/cmq_test0001.mp3")
        self.assertEqual(kwargs["rights_mode"], "REFERENCE_ONLY")
        self.assertEqual(outcome.fields["novel_id"], "nov_1")

    def test_missing_token_blocks_rather_than_fails(self):
        item = make_item(subtitle_state="DONE", dub_state="SKIPPED")
        outcome = orch.precheck_draft(orch.Context(store=FakeStore([item]), token=""), item)
        self.assertEqual(outcome.state, "PENDING")
        self.assertTrue(outcome.blocked)


class WorkSelectionTest(unittest.TestCase):
    def test_collect_work_dedupes_items_pending_in_several_stages(self):
        item = make_item()  # moi cong doan deu PENDING
        found = orch.collect_work(FakeStore([item]), limit=10)
        self.assertEqual([i.item_id for i in found], ["cmq_test0001"])

    def test_collect_work_respects_limit(self):
        items = [make_item(item_id=f"cmq_{n:04d}") for n in range(5)]
        self.assertEqual(len(orch.collect_work(FakeStore(items), limit=2)), 2)

    def test_collect_work_never_asks_appwrite_for_more_than_one_page(self):
        """Quet rong hon `limit` de con cho loai muc het luot — nhung Appwrite
        chan mot trang o 100, nen khong duoc vuot qua."""
        store = FakeStore([])
        asked: list = []
        original = store.list_queue_items_by_state

        def spy(*, stage, state, limit=50, offset=0):
            asked.append(limit)
            return original(stage=stage, state=state, limit=limit, offset=offset)

        store.list_queue_items_by_state = spy
        orch.collect_work(store, limit=500)

        self.assertTrue(asked)
        self.assertLessEqual(max(asked), orch.QUERY_PAGE_SIZE)

    def test_exhausted_items_do_not_starve_the_queue(self):
        """Muc het luot thu VAN o trang thai PENDING. Neu loc sau khi ap
        `limit`, moi lan chay se chon dung chung, bo qua het, roi ve tay
        khong — con muc chay duoc nam ngay phia sau khong bao gio toi luot."""
        exhausted = [make_item(item_id=f"cmq_dead{n}", attempts=3) for n in range(10)]
        runnable = make_item(item_id="cmq_live0")
        found = orch.collect_work(FakeStore(exhausted + [runnable]),
                                  limit=3, max_attempts=3)
        self.assertEqual([i.item_id for i in found], ["cmq_live0"])

    def test_a_failed_last_stage_is_still_retryable(self):
        """TRANG THAI KHONG LOI RA. Mot muc co `draft=FAILED` va moi cong doan
        khac da ket thuc khong con cong doan `PENDING` nao. Neu hang doi chi
        truy van `PENDING`, no khong bao gio duoc chon lai — du `attempts` van
        con — va nam chet o do vinh vien."""
        stuck = make_item(transcript_state="DONE", translation_state="DONE",
                          subtitle_state="DONE", dub_state="SKIPPED",
                          render_state="SKIPPED", draft_state="FAILED",
                          attempts=1)
        found = orch.collect_work(FakeStore([stuck]), limit=10, max_attempts=3)
        self.assertEqual([i.item_id for i in found], ["cmq_test0001"])

    def test_a_failed_stage_past_its_budget_is_not_retried(self):
        dead = make_item(draft_state="FAILED", attempts=3,
                         transcript_state="DONE", translation_state="DONE",
                         subtitle_state="DONE", dub_state="SKIPPED",
                         render_state="SKIPPED")
        self.assertEqual(orch.collect_work(FakeStore([dead]), limit=10,
                                           max_attempts=3), [])

    def test_finished_items_are_not_picked_up(self):
        done = make_item(transcript_state="DONE", translation_state="DONE",
                         subtitle_state="DONE", dub_state="SKIPPED",
                         draft_state="DONE", render_state="SKIPPED")
        self.assertEqual(orch.collect_work(FakeStore([done]), limit=10), [])


class ReclaimStaleTest(unittest.TestCase):
    def test_only_old_running_stages_are_reclaimed(self):
        fresh = make_item(item_id="cmq_fresh", transcript_state="RUNNING",
                          updated_at=orch._now().isoformat())
        stale = make_item(item_id="cmq_stale", transcript_state="RUNNING",
                          updated_at="2020-01-01T00:00:00+00:00")
        store = FakeStore([fresh, stale])

        reclaimed = orch.reclaim_stale(store, minutes=60)

        self.assertEqual([r["item_id"] for r in reclaimed], ["cmq_stale"])
        self.assertEqual(store.items["cmq_stale"].transcript_state, "PENDING")
        self.assertEqual(store.items["cmq_fresh"].transcript_state, "RUNNING")

    def test_unparseable_timestamp_is_never_reclaimed(self):
        item = make_item(transcript_state="RUNNING", updated_at="khong-phai-ngay")
        store = FakeStore([item])
        self.assertEqual(orch.reclaim_stale(store, minutes=1), [])
        self.assertEqual(item.transcript_state, "RUNNING")

    def test_dry_run_reclaim_reports_without_writing(self):
        """`--dry-run --reclaim-stale` tung ghi that: nhanh reclaim khong he
        di qua cong dry-run."""
        item = make_item(transcript_state="RUNNING",
                         updated_at="2020-01-01T00:00:00+00:00")
        store = FakeStore([item])

        reclaimed = orch.reclaim_stale(store, minutes=60, dry_run=True)

        self.assertEqual([r["item_id"] for r in reclaimed], ["cmq_test0001"])
        self.assertTrue(reclaimed[0]["would_reclaim"])
        self.assertEqual(store.updates, [])
        self.assertEqual(item.transcript_state, "RUNNING")


class DryRunTest(unittest.TestCase):
    """`--dry-run` la LAP KE HOACH, khong phai "chay that roi vut ket qua".

    Neu no van goi ham cong doan, mot lan chay thu se tot 35-90 phut ASR hoac
    mot luot quota dich roi vut di — vi khong duoc phep ghi gi ca.
    """

    def test_dry_run_writes_nothing_to_the_store(self):
        item = make_item()
        store = FakeStore([item])
        ctx = orch.Context(store=store, dry_run=True,
                           audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "find_source_captions", return_value=None), \
             mock.patch.object(pipeline, "transcribe_mandarin", return_value=segments(2)), \
             mock.patch.object(pipeline, "upload_to_r2") as up:
            record = orch.run_stage(ctx, item, "transcript")

        self.assertEqual(store.updates, [], "dry-run khong duoc ghi gi, ke ca RUNNING")
        up.assert_not_called()
        self.assertTrue(record["would_run"])

    def test_dry_run_does_not_run_the_expensive_stage_at_all(self):
        item = make_item()
        ctx = orch.Context(store=FakeStore([item]), dry_run=True,
                           audio={item.item_id: Path(__file__)})

        with mock.patch.object(orch, "exists_in_r2", return_value=False), \
             mock.patch.object(pipeline, "transcribe_mandarin") as asr, \
             mock.patch.object(pipeline, "find_source_captions") as captions, \
             mock.patch.object(pipeline, "translate_zh_to_vi") as translate:
            orch.run_stage(ctx, item, "transcript")

        asr.assert_not_called()
        # Co media nguoi van hanh cung cap thi khong can hoi phu de goc nua.
        captions.assert_not_called()
        translate.assert_not_called()

    def test_dry_run_still_reports_unmet_preconditions(self):
        item = make_item(transcript_state="PENDING")
        ctx = orch.Context(store=FakeStore([item]), dry_run=True)
        record = orch.run_stage(ctx, item, "translation")
        self.assertTrue(record["skipped_by_orchestrator"])
        self.assertNotIn("would_run", record)


class QueueStatusTest(unittest.TestCase):
    def test_status_counts_every_stage_and_state(self):
        counts = orch.queue_status(FakeStore([make_item()]))
        self.assertEqual(set(counts), set(orch.STAGE_ORDER))
        self.assertEqual(counts["transcript"]["PENDING"], 1)
        self.assertEqual(counts["transcript"]["DONE"], 0)


if __name__ == "__main__":
    unittest.main()

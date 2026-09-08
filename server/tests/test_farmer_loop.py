"""Farmer — vong lap va THU TU cua hai lan.

Thu tu la thu de mat nhat khi ai do sua sau nay, va tung buoc sai thu tu deu
ton tien that:

    khu trung lap TRUOC khi tai   -> khong tai lai thu da co
    duyet TRUOC khi san xuat      -> khong tra tien TTS cho rac
    bia la cong CUOI va CUNG      -> khong xuat ban o trong

Cac bai o day dung phu thuoc TIEM VAO, khong cham Appwrite/R2/Gemini/Cloud
Run — do la ca ly do `ProductionFarmer` nhan moi thu qua tham so.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from server.farmer.covers import CoverGate, CoverRequired
from server.farmer.dedup import LANE_AUDIO, LANE_TEXT
from server.farmer.loop import Candidate, ProductionFarmer
from server.farmer.metrics import MetricsWriter
from server.farmer.drive_archive import ARCHIVE_DONE, ArchiveOutcome
from server.farmer.production_writer import ProductionWriter
from server.farmer.quotas import FarmerQuotas
from server.farmer.review import QualityReviewer
from server.llm_gateway.provider import LLMCompletion


class _NotFound(Exception):
    pass


_NotFound.__name__ = "NotFoundError"


class _Store:
    """Kho gia: hang doi rong, khong truyen nao — moi thu deu la moi."""

    def __init__(self, queue=None, novels=None):
        self.queue = queue or {}
        self.novels = novels or []

    def get_queue_item(self, item_id):
        if item_id not in self.queue:
            raise _NotFound("khong co")
        return self.queue[item_id]

    def find_novels(self, owner_id=None, limit=None, **kw):
        return list(self.novels), len(self.novels)


class _Provider:
    """Provider danh gia gia — luon duyet voi diem cao."""

    def __init__(self, score=90, verdict="approve"):
        self.calls = 0
        self._score, self._verdict = score, verdict

    def complete(self, *, system, user, model, max_output_tokens):
        self.calls += 1
        return LLMCompletion(
            text=f'{{"score": {self._score}, "verdict": "{self._verdict}",'
                 f' "reasons": [], "language": "vi"}}',
            provider_name="gemini", model=model)


def _covers_ok():
    """Cong bia luon thanh cong."""
    gate = mock.Mock(spec=CoverGate)
    gate.ensure_cover.return_value = mock.Mock(asset_id="ast_1", reused=False)
    gate.assert_publishable.return_value = "ast_1"
    return gate


def _covers_failing():
    gate = mock.Mock(spec=CoverGate)
    gate.ensure_cover.side_effect = CoverRequired("provider chet")
    return gate


class _Harness:
    """Dung mot farmer day du phu thuoc gia, quota rong rai."""

    def __init__(self, *, tmp: Path, store=None, covers=None, provider=None,
                 text_candidates=(), audio_candidates=(), quotas=None,
                 with_writer=True):
        self.store = store or _Store()
        self.provider = provider or _Provider()
        self.covers = covers or _covers_ok()
        self.fetched, self.published, self.tts, self.queued = [], [], [], []
        self.quotas = quotas or FarmerQuotas(
            max_concurrent_downloads=5, max_review_requests=50,
            max_tts_jobs=50, min_free_disk_bytes=1, work_dir=str(tmp))
        self.metrics = MetricsWriter(tmp / "status.json")

        def fetch(c):
            self.fetched.append(c.url)
            return "noi dung that su dai va mach lac " * 20

        def publish(c, body):
            self.published.append(c.url)
            return f"nov_{len(self.published)}"

        def enqueue_tts(novel_id):
            self.tts.append(novel_id)
            return "task_1"

        def enqueue_audio(c):
            self.queued.append(c.url)

        # Kho san xuat chinh tac, gia lap toan bo: R2 la mot dict, tranh la
        # hai chuoi byte, Drive la mot danh sach. Duong ma duoc chay THAT —
        # chi ba bien gioi ngoai la gia.
        self.objects, self.archived = {}, []

        def put(key, data, content_type="application/octet-stream"):
            self.objects[key] = data

        def get(key):
            return self.objects[key]

        def sinh_tranh(wid):
            return (b"COVER:" + wid.encode(), b"BG:" + wid.encode())

        def luu_tru(path, *, work_key, timeout=300):
            self.archived.append(work_key)
            return ArchiveOutcome(ARCHIVE_DONE,
                                  remote_path=f"fanfic-gdrive:{work_key}")

        self.writer = ProductionWriter(
            put_object=put, get_object=get, generate_artwork=sinh_tranh,
            archive_file=luu_tru) if with_writer else None

        self.farmer = ProductionFarmer(
            store=self.store, quotas=self.quotas,
            reviewer=QualityReviewer(self.provider, min_score=70),
            cover_gate=self.covers, metrics_writer=self.metrics,
            discover_audio=lambda n: list(audio_candidates)[:n],
            discover_text=lambda n: list(text_candidates)[:n],
            fetch_text=fetch, publish_text=publish,
            enqueue_tts=enqueue_tts, enqueue_audio_item=enqueue_audio,
            production_writer=self.writer, batch_per_lane=10)


def _text(url, title="Tieu de"):
    return Candidate(lane=LANE_TEXT, url=url, title=title)


def _audio(url, item_id):
    return Candidate(lane=LANE_AUDIO, url=url, queue_item_id=item_id)


class TextLaneOrderTest(unittest.TestCase):
    def test_a_good_work_goes_all_the_way_to_publish_candidate(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.approved, 1)
        self.assertEqual(m.produced, 1)
        self.assertEqual(m.published_candidates, 1)
        self.assertEqual(h.tts, ["nov_1"])

        # Cong READY moi: bo hien vat CHINH TAC phai co that, khong chi mot
        # bo dem tang len. Day la thu ma dot ra soat du dieu kien phat hien
        # la thieu — cac module da co nhung khong ai goi.
        khoa = sorted(h.objects)
        self.assertTrue(any(k.endswith("/text/normalized.txt") for k in khoa), khoa)
        self.assertTrue(any(k.endswith("/artwork/cover.webp") for k in khoa), khoa)
        self.assertTrue(any(k.endswith("/artwork/background.webp") for k in khoa), khoa)
        self.assertTrue(any(k.endswith("/manifest.json") for k in khoa), khoa)
        self.assertTrue(all(k.startswith("FanficWorld/production/") for k in khoa), khoa)
        # KHONG duoc cham vao cay legacy.
        self.assertFalse([k for k in khoa if k.startswith("FanficWorld/archive")])
        # Da guong len Drive.
        self.assertTrue(h.archived, "chua guong tep nao len Drive")

    def test_a_finished_work_is_never_fetched_again(self):
        """Khu trung lap dat TRUOC khi tai — khong tai lai thu da XONG.

        "Xong" duoc do bang HIEN VAT (manifest da READY), khong bang ban ghi
        novel. Xem `test_a_half_finished_work_is_resumed` ngay duoi de biet vi
        sao su khac biet do quan trong.
        """
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d),
                         text_candidates=[_text("https://e.com/a")])
            # Chay mot lan cho tac pham hoan tat that su...
            h.farmer.run_text_lane()
            self.assertEqual(h.fetched, ["https://e.com/a"])
            # ...roi chay lai: khong duoc cham vao no nua.
            m = h.farmer.run_text_lane()
        self.assertEqual(m.deduped, 1)
        self.assertEqual(h.fetched, ["https://e.com/a"])   # khong tai lan hai
        self.assertEqual(len(h.published), 1)              # khong tao ban trung

    def test_a_half_finished_work_is_resumed_not_skipped(self):
        """Co novel nhung CHUA co hien vat = DANG DO, phai chay tiep.

        Day la loi da khoa vinh vien bon tac pham fanfiction that tren may san
        xuat: chung tao novel, xep TTS, roi hong o buoc bia — sau do chinh
        novel cua chung lam chung "trung lap" voi chinh minh, mai mai.

        Chay tiep phai DUNG LAI ban nhap cu (khong POST novel thu hai) va
        KHONG xep lai TTS (lan truoc da xep).
        """
        class _CoNovel(_Store):
            def find_novels(self, owner_id=None, limit=None, **kw):
                n = mock.Mock(external_source_url="https://e.com/a",
                              novel_id="nov_cu")
                return [n], 1

        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), store=_CoNovel(),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()

        self.assertEqual(m.resumed, 1)
        self.assertEqual(m.deduped, 0)
        self.assertEqual(h.published, [])          # KHONG tao novel thu hai
        self.assertEqual(h.tts, [])                # KHONG xep lai TTS
        self.assertEqual(m.published_candidates, 1)
        # Hien vat duoc ghi duoi work_id cua nguon, gan voi novel DA CO.
        man = [k for k in h.objects if k.endswith("/manifest.json")]
        self.assertTrue(man, sorted(h.objects))
        import json as _json
        noi_dung = _json.loads(h.objects[
            [k for k in man if "/manifests/" not in k][0]])
        self.assertEqual(noi_dung["serving"]["novel_id"], "nov_cu")

    def test_a_rejected_work_never_reaches_tts(self):
        """Duyet dat TRUOC san xuat — khong tra tien TTS cho rac."""
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), provider=_Provider(verdict="reject", score=5),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.rejected, 1)
        self.assertEqual(h.published, [])
        self.assertEqual(h.tts, [])

    def test_review_failure_fails_closed(self):
        """Khong danh gia duoc -> khong san xuat. KHAC 'bi tu choi'."""
        class _Hong:
            def complete(self, **kw):
                raise RuntimeError("mang hong")

        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), provider=_Hong(),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.failed, 1)
        self.assertEqual(m.approved, 0)
        self.assertEqual(h.published, [])
        self.assertEqual(h.tts, [])

    def test_a_failing_serving_cover_no_longer_blocks_the_work(self):
        """Bia duong PHUC VU khong con la cong — va do la mot sua loi, khong
        phai mot lan noi long.

        `MediaAssetStore` la mot Protocol ma ban trien khai duy nhat la mock;
        `AppwriteMetadataStore` khong co `list_assets`. Tren may san xuat that
        buoc nay hong MOI LAN, va vong lap cu `continue` — nen hai tac pham
        duoc duyet 82 va 78 diem khong bao gio co lay mot hien vat nao, sau
        khi da tao novel va da xep TTS.

        Cong THAT ("phai co tranh truoc READY") nam o buoc kho chinh tac, tren
        hai tep co that. Xem `test_the_real_artwork_gate_still_blocks` ngay
        duoi.
        """
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), covers=_covers_failing(),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.produced, 1)
        self.assertEqual(m.published_candidates, 1)
        # Su co van duoc ghi lai — di tiep khong phai nuot im lang.
        self.assertTrue(any("bia duong phuc vu" in e for e in m.errors), m.errors)

    def test_the_real_artwork_gate_still_blocks(self):
        """Khong co tranh trong kho chinh tac thi KHONG phai ung vien xuat
        ban — cong nay van cung y nhu truoc."""
        from server.farmer.artwork import ArtworkError

        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d),
                         text_candidates=[_text("https://e.com/a")])

            def tranh_hong(wid):
                raise ArtworkError("ffmpeg vang mat")

            h.writer._art = tranh_hong
            m = h.farmer.run_text_lane()
        self.assertEqual(m.produced, 1)
        self.assertEqual(m.published_candidates, 0)
        self.assertEqual(m.blocked_no_cover, 1)

    def test_review_budget_stops_the_lane_without_killing_it(self):
        with TemporaryDirectory() as d:
            q = FarmerQuotas(max_concurrent_downloads=5, max_review_requests=1,
                             max_tts_jobs=5, min_free_disk_bytes=1, work_dir=d)
            h = _Harness(tmp=Path(d), quotas=q, text_candidates=[
                _text("https://e.com/a"), _text("https://e.com/b"),
                _text("https://e.com/c")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.reviewed, 1)
        self.assertEqual(m.skipped_quota, 2)
        self.assertEqual(h.provider.calls, 1)


class AudioLaneTest(unittest.TestCase):
    def test_new_source_is_enqueued_not_processed(self):
        """Farmer NAP hang doi; no khong chay ASR. Cong doan boc loi o
        0,96x thoi gian thuc se an tron mot trong hai vCPU cua may nay."""
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d),
                         audio_candidates=[_audio("https://y.com/1", "cmq_1")])
            m = h.farmer.run_audio_lane()
        self.assertEqual(m.produced, 1)
        self.assertEqual(h.queued, ["https://y.com/1"])

    def test_already_queued_source_is_skipped(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), store=_Store(queue={"cmq_1": object()}),
                         audio_candidates=[_audio("https://y.com/1", "cmq_1")])
            m = h.farmer.run_audio_lane()
        self.assertEqual(m.deduped, 1)
        self.assertEqual(h.queued, [])

    def test_a_candidate_without_a_queue_id_is_refused(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d),
                         audio_candidates=[_audio("https://y.com/1", "")])
            m = h.farmer.run_audio_lane()
        self.assertEqual(m.failed, 1)
        self.assertEqual(h.queued, [])


class RoundTest(unittest.TestCase):
    def test_a_full_disk_stops_every_lane_and_says_so(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), text_candidates=[_text("https://e.com/a")],
                         audio_candidates=[_audio("https://y.com/1", "cmq_1")])
            with mock.patch.object(FarmerQuotas, "free_disk_bytes", return_value=1):
                h.quotas.min_free_disk_bytes = 10 ** 12
                h.farmer.run_once()
            import json
            status = json.loads((Path(d) / "status.json").read_text("utf-8"))
        self.assertFalse(status["healthy"])
        self.assertIn("dia", status["unhealthy_reason"])
        self.assertEqual(h.fetched, [])
        self.assertEqual(h.queued, [])

    def test_status_file_is_written_and_readable(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), text_candidates=[_text("https://e.com/a")])
            h.farmer.run_once()
            import json
            status = json.loads((Path(d) / "status.json").read_text("utf-8"))
        self.assertEqual(status["schema_version"], 1)
        self.assertTrue(status["healthy"])
        self.assertEqual(status["lanes"][LANE_TEXT]["published_candidates"], 1)
        self.assertIn("limits", status["quotas"])
        self.assertEqual(status["round"]["number"], 1)

    def test_a_crashing_round_does_not_kill_the_farmer(self):
        """Farmer phai song qua duoc mot su co Appwrite hay mot lan mat
        mang — no la mot dich vu 24/7, khong phai mot lenh chay mot lan."""
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d))
            with mock.patch.object(ProductionFarmer, "run_once",
                                   side_effect=RuntimeError("Appwrite chet")):
                vong = h.farmer.run_forever(sleep_seconds=0, max_rounds=2)
        self.assertEqual(vong, 2)

    def test_usage_budget_resets_between_rounds(self):
        """HAI tac pham, han muc MOT lan danh gia moi vong.

        Phai dung hai nguon khac nhau chu khong lap lai mot nguon: khu trung
        lap se chan lan thu hai cua CUNG mot tac pham (dung y — no da xong),
        va luc do phep do se noi ve khu trung lap chu khong ve han muc.
        """
        with TemporaryDirectory() as d:
            q = FarmerQuotas(max_concurrent_downloads=5, max_review_requests=1,
                             max_tts_jobs=5, min_free_disk_bytes=1, work_dir=d)
            h = _Harness(tmp=Path(d), quotas=q,
                         text_candidates=[_text("https://e.com/a"),
                                          _text("https://e.com/b")])
            mot = h.farmer.run_once()
            hai = h.farmer.run_once()

        # Vong 1: mot cai qua duoc, cai kia het han muc.
        self.assertEqual(mot[LANE_TEXT].reviewed, 1)
        self.assertEqual(mot[LANE_TEXT].skipped_quota, 1)
        # Vong 2: cai da xong bi khu trung lap, cai con lai duoc danh gia —
        # tuc la han muc DA duoc dat lai.
        self.assertEqual(hai[LANE_TEXT].deduped, 1)
        self.assertEqual(hai[LANE_TEXT].reviewed, 1)
        self.assertEqual(h.provider.calls, 2)


if __name__ == "__main__":
    unittest.main()


class ResumeTtsTest(unittest.TestCase):
    """Lan chay tiep phai HOI xem da co job TTS chua, khong suy dien.

    Suy dien "dang chay tiep tuc la lan truoc da xep TTS" nghe hop ly nhung
    sai: xuat ban va TTS la hai buoc khac nhau. Hai tac pham that da READY
    ma khong he co job TTS nao — chung se cam lang vinh vien.
    """

    class _CoNovel(_Store):
        def __init__(self, jobs):
            super().__init__()
            self._jobs = jobs

        def find_novels(self, owner_id=None, limit=None, **kw):
            return [mock.Mock(external_source_url="https://e.com/a",
                              novel_id="nov_cu")], 1

        def list_chapters(self, novel_id):
            return [mock.Mock(chapter_id="ch_1")]

        def list_jobs(self, owner_id, chapter_id=None):
            return list(self._jobs)

    def test_resume_enqueues_tts_when_none_exists(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), store=self._CoNovel(jobs=[]),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.resumed, 1)
        self.assertEqual(h.tts, ["nov_cu"])          # DA xep
        self.assertEqual(m.published_candidates, 1)

    def test_resume_does_not_enqueue_a_second_tts_job(self):
        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d),
                         store=self._CoNovel(jobs=[mock.Mock(job_id="job_cu")]),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(m.resumed, 1)
        self.assertEqual(h.tts, [])                  # KHONG xep trung
        self.assertEqual(m.published_candidates, 1)

    def test_an_unreadable_job_list_defers_tts_instead_of_duplicating(self):
        class _Hong(self._CoNovel):
            def list_jobs(self, owner_id, chapter_id=None):
                raise RuntimeError("Appwrite tu choi")

        with TemporaryDirectory() as d:
            h = _Harness(tmp=Path(d), store=_Hong(jobs=[]),
                         text_candidates=[_text("https://e.com/a")])
            m = h.farmer.run_text_lane()
        self.assertEqual(h.tts, [])                  # hoan, khong doan
        self.assertEqual(m.skipped_quota, 0)         # KHONG phai het han muc
        self.assertTrue(any("hoan TTS" in e for e in m.errors), m.errors)

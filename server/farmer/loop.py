"""Hai lan san xuat + vong lap chinh cua farmer.

Vong lap CO Y nham. Moi vong: quet mot it, duyet mot it, san xuat mot it,
ghi trang thai, ngu. Khong co "chay het cong suat" — may nay dang cho hai
worker production o nho, va mot farmer tham an se lam do chung truoc khi no
kip san xuat duoc gi.

Thu tu trong ca hai lan la co chu dich:

    kham pha -> KHU TRUNG LAP -> lay noi dung -> DUYET -> ban nhap -> TTS ->
    bia -> KHO CHINH TAC (van ban + tranh + manifest + guong Drive) ->
    ung vien xuat ban

Khu trung lap dat TRUOC khi lay noi dung (dung tai ve thu ta da co), va duyet
dat TRUOC khi san xuat (dung tra tien TTS cho rac).

Cong READY nam o BUOC CUOI, tai `production_writer`, chu khong o buoc bia.
Do la mot su khac biet that: mot ban ghi novel co anh van co the thieu van ban
chuan hoa, thieu manifest, hoac chua len duoc kho luu tru. Truoc day day
chuyen dung o buoc bia va cac module kho chinh tac khong ai goi — chung duoc
xay xong roi de do.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from server.farmer.covers import CoverGate, CoverRequired
from server.farmer.dedup import (
    LANE_AUDIO, LANE_TEXT, DedupError, DedupIndex, work_key,
)
from server.farmer.metrics import LaneMetrics, MetricsWriter
from server.farmer.quotas import FarmerQuotas, QuotaExceeded
from server.farmer.review import QualityReviewer, ReviewUnavailable
from server.farmer.review_provider import ReviewPending, ReviewProvider


def _la_provider(obj: Any) -> bool:
    """Phan biet `ReviewProvider` (nhan mot `ReviewRequest`) voi
    `QualityReviewer` cu (nhan tham so roi)."""
    return isinstance(obj, ReviewProvider)


def _work_id_cho(bucket: str, url: str) -> str:
    from server.farmer.canonical import work_id

    return work_id(bucket, url)

#: Nghi giua hai vong. Mac dinh 15 phut: du thua de theo kip nguon dang
#: dang moi vai gio mot lan, va du thua de khong lam phien hai worker.
DEFAULT_ROUND_SLEEP_SECONDS = 900
ENV_ROUND_SLEEP = "FARMER_ROUND_SLEEP_SECONDS"

#: So muc toi da xu ly moi lan moi vong. Chan tren cua CONG VIEC, tach khoi
#: chan tren cua TAI NGUYEN o `quotas.py`.
DEFAULT_BATCH_PER_LANE = 3
ENV_BATCH = "FARMER_BATCH_PER_LANE"


@dataclass
class Candidate:
    """Mot ung vien da kham pha, truoc khi lay noi dung."""
    lane: str
    url: str
    title: str = ""
    #: Chi lan A: `item_id` cua `content_queue` (da tat dinh san).
    queue_item_id: str = ""
    #: Sieu du lieu tu do de lan tu dung — khong dinh nghia hinh dang cung o
    #: day vi hai lan can hai thu khac nhau.
    meta: Dict[str, Any] = None


class LaneResult:
    def __init__(self, metrics: LaneMetrics):
        self.metrics = metrics


def _int_env(name: str, mac_dinh: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return mac_dinh
    try:
        v = int(raw)
    except ValueError:
        return mac_dinh
    return v if v > 0 else mac_dinh


class ProductionFarmer:
    """Dieu phoi hai lan. KHONG chay suy dien, KHONG xay lai cong doan nao.

    Moi phu thuoc duoc TIEM VAO — do la ca ly do lop nay kiem thu duoc ma
    khong can Appwrite, R2, Gemini hay Cloud Run.
    """

    def __init__(self, *,
                 store: Any,
                 quotas: FarmerQuotas,
                 reviewer: QualityReviewer,
                 cover_gate: CoverGate,
                 metrics_writer: MetricsWriter,
                 discover_audio: Callable[[int], Sequence[Candidate]],
                 discover_text: Callable[[int], Sequence[Candidate]],
                 fetch_text: Callable[[Candidate], str],
                 publish_text: Callable[[Candidate, str], str],
                 enqueue_tts: Callable[[str], Optional[str]],
                 enqueue_audio_item: Callable[[Candidate], None],
                 production_writer: Any = None,
                 batch_per_lane: int = 0):
        self._store = store
        self._quotas = quotas
        self._reviewer = reviewer
        self._covers = cover_gate
        self._metrics = metrics_writer
        self._dedup = DedupIndex(store)
        self._discover_audio = discover_audio
        self._discover_text = discover_text
        self._fetch_text = fetch_text
        self._publish_text = publish_text
        self._enqueue_tts = enqueue_tts
        self._enqueue_audio_item = enqueue_audio_item
        #: Ghi bo hien vat CHINH TAC (van ban chuan hoa + tranh + manifest +
        #: guong Drive). `None` = khong ghi kho san xuat — chi hop le trong
        #: `--dry-run` va trong kiem thu; duong san xuat that LUON co.
        self._writer = production_writer
        self._batch = batch_per_lane or _int_env(ENV_BATCH, DEFAULT_BATCH_PER_LANE)
        #: Bao cao toan ven trinh thong dich — dien boi `__main__` luc khoi
        #: dong (noi da CHAN duoc neu khong dat). O day chi de bao cao lai.
        self._integrity: Dict[str, Any] = {}

    # -- LAN A: audio co san ------------------------------------------------
    def run_audio_lane(self) -> LaneMetrics:
        """Kham pha nguon audio va dua vao `content_queue`.

        CO Y dung o day. Farmer KHONG chay cac cong doan cua
        `chinese_media_orchestrator` — cong doan boc loi la ASR, va ASR o
        0,96x thoi gian thuc se an tron mot trong hai vCPU cua may nay hang
        gio. Farmer nap hang doi; mot worker khac (co the la chinh may nay
        luc ranh, co the la may khac) chay orchestrator.

        Day khong phai su thieu sot — day la yeu cau "may gat chi la nguoi
        gat, suy dien nang di noi khac" duoc ton trong.
        """
        m = LaneMetrics()
        try:
            ung_vien = list(self._discover_audio(self._batch))
        except Exception as exc:                                # noqa: BLE001
            m.note_error(f"kham pha lan audio that bai: "
                         f"{type(exc).__name__}: {exc}")
            m.failed += 1
            return m
        m.discovered = len(ung_vien)

        for c in ung_vien:
            try:
                if not c.queue_item_id:
                    m.note_error(f"ung vien audio thieu queue_item_id: {c.url}")
                    m.failed += 1
                    continue
                if self._dedup.audio_already_queued(c.queue_item_id):
                    m.deduped += 1
                    continue
            except DedupError as exc:
                # FAIL CLOSED — khong biet da gat chua thi khong gat.
                m.note_error(f"bo qua (khong kiem duoc trung lap): {exc}")
                m.skipped_quota += 1
                continue

            khe = self._quotas.try_slot(FarmerQuotas.DOWNLOAD, check_disk=True)
            if khe is None:
                m.skipped_quota += 1
                continue
            try:
                self._enqueue_audio_item(c)
                m.produced += 1
            except Exception as exc:                            # noqa: BLE001
                m.note_error(f"nap hang doi that bai cho {c.url}: "
                             f"{type(exc).__name__}: {exc}")
                m.failed += 1
            finally:
                khe.__exit__(None, None, None)
        return m

    # -- LAN B: truyen chu --------------------------------------------------
    def run_text_lane(self) -> LaneMetrics:
        """Duong san xuat THAT SU cho may nay: khong ASR, nen khong nghen."""
        m = LaneMetrics()
        try:
            ung_vien = list(self._discover_text(self._batch))
        except Exception as exc:                                # noqa: BLE001
            m.note_error(f"kham pha lan text that bai: "
                         f"{type(exc).__name__}: {exc}")
            m.failed += 1
            return m
        m.discovered = len(ung_vien)

        for c in ung_vien:
            try:
                khoa = work_key(LANE_TEXT, c.url)
            except ValueError as exc:
                m.note_error(f"URL khong dung duoc khoa: {c.url} ({exc})")
                m.failed += 1
                continue

            try:
                if self._dedup.text_already_farmed(khoa.canonical_url):
                    m.deduped += 1
                    continue
            except DedupError as exc:
                m.note_error(f"bo qua (khong kiem duoc trung lap): {exc}")
                m.skipped_quota += 1
                continue

            # 1. Lay noi dung — ghi ra dia, nen qua cong dia.
            khe_tai = self._quotas.try_slot(FarmerQuotas.DOWNLOAD, check_disk=True)
            if khe_tai is None:
                m.skipped_quota += 1
                continue
            try:
                body = self._fetch_text(c)
            except Exception as exc:                            # noqa: BLE001
                m.note_error(f"lay noi dung that bai {c.url}: "
                             f"{type(exc).__name__}: {exc}")
                m.failed += 1
                continue
            finally:
                khe_tai.__exit__(None, None, None)

            # 2. Duyet — TRUOC khi tieu bat ky dong nao cho san xuat.
            khe_duyet = self._quotas.try_slot(FarmerQuotas.REVIEW)
            if khe_duyet is None:
                m.skipped_quota += 1
                continue
            try:
                verdict = self._review(c, body)
            except ReviewPending as exc:
                # Da xep vao hang doi; may danh gia (laptop) chua tra ban an.
                # KHONG phai loi, va tuyet doi KHONG duoc coi la duyet — tac
                # pham cho vong sau. May danh gia tat = cho mai mai, dung y.
                m.review_pending += 1
                m.note_error(f"cho danh gia {c.url}: {exc}")
                continue
            except ReviewUnavailable as exc:
                # FAIL CLOSED: khong danh gia duoc thi KHONG duyet.
                m.note_error(f"khong danh gia duoc {c.url}: {exc}")
                m.failed += 1
                continue
            finally:
                khe_duyet.__exit__(None, None, None)

            m.reviewed += 1
            if not verdict.approved:
                m.rejected += 1
                # Ban an cua mot tac pham bi loai phai TIM LAI DUOC. Khong
                # ghi lai thi mot lan xem lai bang tay khong biet vi sao no
                # truot, va cung tac pham do se duoc lay ve o vong sau.
                self._ghi_ban_an(c, body, verdict, m)
                continue
            m.approved += 1

            # 3. Xuat ban thanh ban nhap (chua public).
            try:
                novel_id = self._publish_text(c, body)
            except Exception as exc:                            # noqa: BLE001
                m.note_error(f"tao ban nhap that bai {c.url}: "
                             f"{type(exc).__name__}: {exc}")
                m.failed += 1
                continue

            # 4. TTS qua Cloud Run — khong tong hop tren may nay.
            from server.farmer.canonical import bucket_for_lane

            bucket = bucket_for_lane(LANE_TEXT)
            tts_job_id = ""
            khe_tts = self._quotas.try_slot(FarmerQuotas.TTS)
            if khe_tts is not None:
                try:
                    tts_job_id = self._enqueue_tts(novel_id) or ""
                except Exception as exc:                        # noqa: BLE001
                    m.note_error(f"xep TTS that bai {novel_id}: "
                                 f"{type(exc).__name__}: {exc}")
                finally:
                    khe_tts.__exit__(None, None, None)
            else:
                m.skipped_quota += 1

            m.produced += 1

            # 5. Bia tren duong PHUC VU (MediaAsset cua Appwrite) — CO GANG,
            #    KHONG phai cong.
            #
            #    `MediaAssetStore` la mot Protocol ma ban trien khai DUY NHAT
            #    la `MockMediaAssetStore`; `AppwriteMetadataStore` khong co
            #    `list_assets`. Nen o may san xuat that, buoc nay nem
            #    `AttributeError` MOI LAN. Truoc day no `continue`, va do la
            #    ly do that su khien hai tac pham DA DUOC DUYET (82 va 78
            #    diem) khong bao gio co hien vat nao: chung dung o day, im
            #    lang, sau khi da tao novel va da xep TTS.
            #
            #    Yeu cau "phai co tranh truoc READY" KHONG bi noi long — no
            #    duoc cuong che o BUOC 6 bang `WorkManifest.publishable()`,
            #    tren hai tep `artwork/cover.webp` va `artwork/background.webp`
            #    co that trong kho chinh tac. Do la mot cong KIEM DUOC; buoc 5
            #    thi dang cho mot kho chua ton tai.
            try:
                self._covers.ensure_cover(novel_id=novel_id, title=c.title)
                self._covers.assert_publishable(novel_id)
            except Exception as exc:                            # noqa: BLE001
                # Ghi lai de khong mat dau vet, roi DI TIEP: cong that o buoc 6.
                m.note_error(f"bia duong phuc vu chua san sang {novel_id} "
                             f"(khong chan): {type(exc).__name__}: {exc}")

            # 6. KHO SAN XUAT CHINH TAC — van ban chuan hoa, tranh, manifest,
            #    guong Drive. Cong READY nam o day chu khong o buoc 5: mot
            #    tac pham chi la ung vien xuat ban khi bo hien vat cua no day
            #    du, chu khong khi rieng ban ghi novel co anh.
            if self._writer is None:
                m.note_error("khong co ProductionWriter — bo qua kho chinh tac")
                continue
            try:
                ket_qua = self._writer.write_approved(
                    bucket=bucket, url=c.url, title=c.title, body=body,
                    verdict=verdict, novel_id=novel_id, tts_job_id=tts_job_id,
                    source_meta=c.meta or {})
            except Exception as exc:                            # noqa: BLE001
                m.failed += 1
                m.note_error(f"ghi kho chinh tac that bai {c.url}: "
                             f"{type(exc).__name__}: {exc}")
                continue

            # Doc HANG SO chu khong chuoi tran: mot chuoi go tay o day se im
            # lang dem sai neu `drive_archive` doi ten trang thai.
            from server.farmer.drive_archive import ARCHIVE_DONE, ARCHIVE_PENDING

            if ket_qua.archive_status == ARCHIVE_DONE:
                m.archived += 1
            elif ket_qua.archive_status == ARCHIVE_PENDING:
                m.archive_pending += 1
            if ket_qua.ready:
                m.published_candidates += 1
            else:
                m.blocked_no_cover += 1
                m.note_error(f"chua READY {ket_qua.work_id}: "
                             f"{ket_qua.blocked_reason}")
        return m

    def _ghi_ban_an(self, c: Candidate, body: str, verdict: Any,
                    m: LaneMetrics) -> None:
        """Ghi manifest cho mot tac pham bi cach ly/loai. KHONG BAO GIO lam
        do mot vong: mot ban an khong ghi duoc la mat thong tin, khong phai
        mat san pham."""
        if self._writer is None:
            return
        try:
            from server.farmer.canonical import bucket_for_lane

            self._writer.write_holding(
                bucket=bucket_for_lane(LANE_TEXT), url=c.url, title=c.title,
                body=body, verdict=verdict, source_meta=c.meta or {})
        except Exception as exc:                                # noqa: BLE001
            m.note_error(f"khong ghi duoc ban an {c.url}: "
                         f"{type(exc).__name__}: {exc}")

    # -- vong lap -----------------------------------------------------------
    def run_once(self) -> Dict[str, LaneMetrics]:
        """MOT vong. Tach khoi `run_forever` de kiem thu duoc, va de mot lan
        chay co kiem soat (`--once`) dung duoc chinh duong nay."""
        bat_dau = self._metrics.begin_round()
        self._quotas.reset_usage()

        khoe, ly_do = True, ""
        try:
            self._quotas.check_disk()
        except QuotaExceeded as exc:
            khoe, ly_do = False, str(exc)

        if not khoe:
            # Dia gan day: KHONG chay lan nao. Ghi trang thai roi ve, de
            # nguoi van hanh (hoac Control Center) nhin thay ngay.
            lanes = {LANE_AUDIO: LaneMetrics(), LANE_TEXT: LaneMetrics()}
            self._metrics.write(
                lanes=lanes, quotas=self._quotas.snapshot().as_dict(),
                round_started=bat_dau, healthy=False, unhealthy_reason=ly_do,
                archive=self._archive_status(), integrity=self._integrity)
            return lanes

        lanes = {
            LANE_AUDIO: self.run_audio_lane(),
            LANE_TEXT: self.run_text_lane(),
        }
        co_loi = any(l.failed for l in lanes.values())
        self._metrics.write(
            lanes=lanes, quotas=self._quotas.snapshot().as_dict(),
            round_started=bat_dau, healthy=not co_loi,
            unhealthy_reason="co cong doan that bai trong vong nay" if co_loi else "",
            archive=self._archive_status(), integrity=self._integrity)
        return lanes

    def _review(self, c: Candidate, body: str):
        """Goi cong danh gia.

        Ho tro CA HAI hinh dang: `ReviewProvider` moi (nhan mot
        `ReviewRequest`) va `QualityReviewer` cu (nhan tham so roi). Giu ca
        hai de mot ban trien khai dang chay khong vo khi doi nha cung cap.
        """
        if hasattr(self._reviewer, "review") and _la_provider(self._reviewer):
            from server.farmer.canonical import bucket_for_lane
            from server.farmer.review_provider import ReviewRequest

            bucket = bucket_for_lane(LANE_TEXT)
            return self._reviewer.review(ReviewRequest(
                work_id=_work_id_cho(bucket, c.url), bucket=bucket,
                lane=LANE_TEXT, title=c.title, body=body, source_url=c.url))
        return self._reviewer.review(
            title=c.title, body=body, lane=LANE_TEXT, source_url=c.url)

    def _archive_status(self) -> Dict[str, Any]:
        """Tinh trang Drive cho `status.json`. CHI DOC, va khong bao gio lam
        do mot vong: mot su co Drive la thong tin, khong phai loi san xuat."""
        try:
            from server.farmer import drive_archive

            return drive_archive.probe()
        except Exception as exc:                                # noqa: BLE001
            return {"status": "ARCHIVE_UNAVAILABLE",
                    "detail": f"{type(exc).__name__}: {exc}"[:300]}

    def run_forever(self, *, sleep_seconds: Optional[int] = None,
                    max_rounds: int = 0) -> int:
        """Chay mai. `max_rounds` chi de kiem thu; 0 = khong gioi han.

        `sleep_seconds=None` nghia la "lay tu cau hinh"; `0` nghia la KHONG
        nghi. Dung `or` o day se bien `0` thanh "chua dat" va cho ngu 15 phut
        giua hai vong cua mot bai test.
        """
        nghi = (sleep_seconds if sleep_seconds is not None
                else _int_env(ENV_ROUND_SLEEP, DEFAULT_ROUND_SLEEP_SECONDS))
        vong = 0
        while True:
            try:
                self.run_once()
            except Exception as exc:                            # noqa: BLE001
                # Mot vong hong KHONG duoc giet farmer — no phai song qua
                # duoc mot su co Appwrite hay mot lan mat mang.
                try:
                    self._metrics.write(
                        lanes={}, quotas=self._quotas.snapshot().as_dict(),
                        round_started=time.monotonic(), healthy=False,
                        unhealthy_reason=f"{type(exc).__name__}: {exc}")
                except Exception:                               # noqa: BLE001
                    pass
            vong += 1
            if max_rounds and vong >= max_rounds:
                return vong
            time.sleep(nghi)

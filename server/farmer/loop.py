"""Hai lan san xuat + vong lap chinh cua farmer.

Vong lap CO Y nham. Moi vong: quet mot it, duyet mot it, san xuat mot it,
ghi trang thai, ngu. Khong co "chay het cong suat" — may nay dang cho hai
worker production o nho, va mot farmer tham an se lam do chung truoc khi no
kip san xuat duoc gi.

Thu tu trong ca hai lan la co chu dich:

    kham pha -> KHU TRUNG LAP -> lay noi dung -> DUYET -> san xuat -> BIA ->
    ung vien xuat ban

Khu trung lap dat TRUOC khi lay noi dung (dung tai ve thu ta da co), va duyet
dat TRUOC khi san xuat (dung tra tien TTS cho rac). Bia la cong CUOI, va no
la cong CUNG: khong bia thi khong ung vien.
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
        self._batch = batch_per_lane or _int_env(ENV_BATCH, DEFAULT_BATCH_PER_LANE)

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
                verdict = self._reviewer.review(
                    title=c.title, body=body, lane=LANE_TEXT, source_url=c.url)
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
            khe_tts = self._quotas.try_slot(FarmerQuotas.TTS)
            if khe_tts is not None:
                try:
                    self._enqueue_tts(novel_id)
                except Exception as exc:                        # noqa: BLE001
                    m.note_error(f"xep TTS that bai {novel_id}: "
                                 f"{type(exc).__name__}: {exc}")
                finally:
                    khe_tts.__exit__(None, None, None)
            else:
                m.skipped_quota += 1

            m.produced += 1

            # 5. CONG BIA — cung, va cuoi cung.
            try:
                self._covers.ensure_cover(novel_id=novel_id, title=c.title)
                self._covers.assert_publishable(novel_id)
                m.published_candidates += 1
            except CoverRequired as exc:
                # Tac pham VAN ton tai o trang thai nhap; no chi khong duoc
                # gan nhan ung vien xuat ban. Vong sau se thu sinh bia lai.
                m.blocked_no_cover += 1
                m.note_error(f"chan xuat ban (chua co bia) {novel_id}: {exc}")
            except Exception as exc:                            # noqa: BLE001
                m.blocked_no_cover += 1
                m.note_error(f"loi cong bia {novel_id}: "
                             f"{type(exc).__name__}: {exc}")
        return m

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
                round_started=bat_dau, healthy=False, unhealthy_reason=ly_do)
            return lanes

        lanes = {
            LANE_AUDIO: self.run_audio_lane(),
            LANE_TEXT: self.run_text_lane(),
        }
        co_loi = any(l.failed for l in lanes.values())
        self._metrics.write(
            lanes=lanes, quotas=self._quotas.snapshot().as_dict(),
            round_started=bat_dau, healthy=not co_loi,
            unhealthy_reason="co cong doan that bai trong vong nay" if co_loi else "")
        return lanes

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

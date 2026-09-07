"""Ranh gioi DANH GIA — mot truu tuong, hai hien thuc, khong roi ve am tham.

## Vi sao co truu tuong nay

Cong danh gia la cho DUY NHAT trong farmer can mot model. Boc no lai thanh
mot giao dien de doi duoc nguon suy dien ma khong dong toi bat cu cong doan
nao khac: R2, Appwrite, TTS, Drive, cong quyen, cong bia — tat ca khong biet
danh gia chay o dau.

## Hai hien thuc

    QueuedReviewProvider   (MAC DINH SAN XUAT)
        Xep mot cong viec vao hang doi Appwrite dung chung, roi TRA VE
        `REVIEW_PENDING`. Mot may khac (laptop, co Router V4 + pool
        Antigravity da dang nhap) poll RA NGOAI, gianh viec, chay, va ghi ban
        an nguoc lai. Laptop khong mo cong nao.

    DirectGeminiReviewProvider   (TUY CHON, KHONG phai mac dinh)
        Goi thang Gemini API. Chi dung khi duoc bat TUONG MINH.

## Khong bao gio roi ve am tham

Neu hang doi khong dung duoc, provider **fail closed**: `REVIEW_PENDING`
hoac loi. No KHONG tu chuyen sang Gemini API — mot ban roi ve am tham sang
mot han muc CO TRA PHI la dung thu ma nguoi van hanh da noi khong.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from server.farmer.review import ReviewUnavailable, ReviewVerdict

#: Ket qua "chua co ban an" — KHAC voi "da danh gia va bi tu choi".
REVIEW_PENDING = "REVIEW_PENDING"

ENV_PROVIDER = "FARMER_REVIEW_PROVIDER"
PROVIDER_QUEUE = "queue"
PROVIDER_GEMINI = "gemini_direct"

#: Muc noi dung gui di danh gia — cat o day, mot cho.
MAX_SAMPLE_CHARS = 6000


class ReviewPending(RuntimeError):
    """Cong viec da duoc xep, ban an chua co. KHONG phai loi.

    Nguoi goi phai de tac pham o trang thai cho va thu lai vong sau — tuyet
    doi khong duoc coi la duyet.
    """


@dataclass
class ReviewRequest:
    work_id: str
    bucket: str
    lane: str
    title: str
    body: str
    source_url: str = ""


class ReviewProvider(ABC):
    """Mot nguon danh gia. Tra ban an, hoac nem — khong bao gio doan."""

    name: str = "unknown"

    @abstractmethod
    def review(self, request: ReviewRequest) -> ReviewVerdict:
        """Nem `ReviewPending` khi chua co ban an; `ReviewUnavailable` khi
        khong danh gia duoc. KHONG BAO GIO tra ve mot ban an bia ra."""

    def metrics(self) -> Dict[str, Any]:
        """So lieu DOC LAP voi nha cung cap/tai khoan.

        Co y khong lo tai khoan Antigravity nao da chay: do la viec cua
        Router V4, va farmer khong duoc biet.
        """
        return {"provider": self.name}


def _sample(text: str, gioi_han: int = MAX_SAMPLE_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= gioi_han:
        return text
    nua = gioi_han // 2
    giua = len(text) // 2
    return text[:nua] + "\n[...]\n" + text[giua:giua + (gioi_han - nua)]


class QueuedReviewProvider(ReviewProvider):
    """MAC DINH SAN XUAT — hang doi Appwrite + may danh gia o xa.

    Luong mot tac pham di qua, tinh theo VONG cua farmer:

        vong 1   xep viec -> `REVIEW_PENDING`
        (laptop poll, gianh, chay Antigravity, ghi ban an)
        vong 2   doc ban an -> approve/quarantine/reject

    Neu laptop tat: cong viec o lai `PENDING` mai mai va farmer khong san
    xuat gi. Do la hanh vi DUNG — fail closed.
    """

    name = "queue_antigravity"

    def __init__(self, store: Any, *, upload_sample, download_verdict,
                 sample_key_for, verdict_key_for):
        self._store = store
        self._upload_sample = upload_sample
        self._download_verdict = download_verdict
        self._sample_key_for = sample_key_for
        self._verdict_key_for = verdict_key_for
        self._enqueued = 0
        self._verdicts = 0
        self._pending_seen = 0

    def review(self, request: ReviewRequest) -> ReviewVerdict:
        from server.domain import ReviewJob

        job_id = request.work_id

        # 1. Ban an da co chua?
        try:
            job = self._store.get_review_job(job_id)
        except Exception:
            job = None

        if job is not None and job.status == "DONE" and job.verdict_key:
            self._verdicts += 1
            return self._read_verdict(job)

        if job is not None and job.status == "FAILED":
            raise ReviewUnavailable(
                f"danh gia that bai o may danh gia: {job.last_error[:200]}")

        if job is not None:
            # Da xep roi, chua xong.
            self._pending_seen += 1
            raise ReviewPending(
                f"{job_id} dang cho danh gia (status={job.status}, "
                f"attempts={job.attempts})")

        # 2. Chua co -> xep viec. Mau noi dung di len R2, khong vao bang.
        sample_key = self._sample_key_for(request.work_id)
        try:
            self._upload_sample(sample_key, json.dumps({
                "work_id": request.work_id,
                "title": request.title,
                "lane": request.lane,
                "source_url": request.source_url,
                "body": _sample(request.body),
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as exc:                                # noqa: BLE001
            raise ReviewUnavailable(
                f"khong tai duoc mau noi dung len R2: "
                f"{type(exc).__name__}: {exc}") from exc

        _, moi = self._store.create_review_job_once(ReviewJob(
            job_id=job_id, work_id=request.work_id, bucket=request.bucket,
            lane=request.lane, source_url=request.source_url,
            title=request.title[:300], sample_key=sample_key))
        if moi:
            self._enqueued += 1
        self._pending_seen += 1
        raise ReviewPending(f"{job_id} vua duoc xep vao hang doi danh gia")

    def _read_verdict(self, job) -> ReviewVerdict:
        try:
            data = json.loads(self._download_verdict(job.verdict_key)
                              .decode("utf-8"))
        except Exception as exc:                                # noqa: BLE001
            raise ReviewUnavailable(
                f"ban an cua {job.job_id} khong doc duoc: "
                f"{type(exc).__name__}: {exc}") from exc

        decision = str(data.get("decision") or "reject")
        return ReviewVerdict(
            approved=decision == "approve",
            decision=decision,
            score=int(data.get("score") or 0),
            reasons=tuple(str(r)[:200] for r in (data.get("reasons") or [])[:5]),
            language=str(data.get("language") or "")[:16],
            # TEN NHA CUNG CAP, khong phai tai khoan.
            model=str(data.get("provider") or job.reviewed_by_provider or ""),
            canonical_title=str(data.get("canonical_title") or "")[:300],
            display_title=str(data.get("display_title") or "")[:300],
            fandom=str(data.get("fandom") or "")[:300],
            category=str(data.get("category") or "")[:300],
            author=str(data.get("author") or "")[:300],
            content_type=str(data.get("content_type") or "")[:300],
            completeness=str(data.get("completeness") or "")[:300],
            tags=tuple(str(t)[:60] for t in (data.get("tags") or [])[:12]),
        )

    def metrics(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "enqueued": self._enqueued,
            "verdicts_read": self._verdicts,
            "pending_seen": self._pending_seen,
        }


class DirectGeminiReviewProvider(ReviewProvider):
    """TUY CHON. Chi duoc dung khi bat TUONG MINH — khong bao gio la ban roi
    ve tu dong cua `QueuedReviewProvider`."""

    name = "gemini_direct"

    def __init__(self, reviewer: Any):
        self._reviewer = reviewer
        self._calls = 0

    def review(self, request: ReviewRequest) -> ReviewVerdict:
        self._calls += 1
        return self._reviewer.review(
            title=request.title, body=request.body, lane=request.lane,
            source_url=request.source_url)

    def metrics(self) -> Dict[str, Any]:
        return {"provider": self.name, "calls": self._calls}


def build_review_provider(store: Any, **kwargs) -> ReviewProvider:
    """Chon nha cung cap danh gia. MAC DINH la hang doi.

    `FARMER_REVIEW_PROVIDER=gemini_direct` bat Gemini — TUONG MINH, va no se
    nem neu thieu khoa thay vi im lang bo qua cong danh gia.
    """
    che_do = (os.environ.get(ENV_PROVIDER) or PROVIDER_QUEUE).strip()

    if che_do == PROVIDER_GEMINI:
        from server.farmer.review import build_reviewer

        return DirectGeminiReviewProvider(build_reviewer())

    if che_do != PROVIDER_QUEUE:
        raise ReviewUnavailable(
            f"{ENV_PROVIDER}={che_do!r} khong hop le — "
            f"chon {PROVIDER_QUEUE!r} hoac {PROVIDER_GEMINI!r}. "
            "Khong doan, khong roi ve.")

    return QueuedReviewProvider(store, **kwargs)

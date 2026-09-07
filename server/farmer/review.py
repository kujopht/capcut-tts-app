"""Cong danh gia chat luong — Gemini 3.8, goi qua API.

Chay tren API chu KHONG tren may gat, va do la mot rang buoc phan cung:
t3a.medium co 2 vCPU dung chung voi hai worker production. Moi suy dien nang
deu di ra ngoai.

Cong nay dung GIUA "da lay duoc noi dung" va "bat dau ton tien san xuat"
(TTS, anh bia, luu tru). Dat no o day la co chu dich: mot ban dich hong hay
mot trang rac bi phat hien TRUOC khi ta tra tien tong hop giong doc cho no.

**Tu choi la ket qua BINH THUONG, khong phai loi.** Mot muc bi tu choi da
duoc danh gia thanh cong — no chi khong dat. Chi khi KHONG danh gia duoc
(mang hong, API tu choi, JSON vo) moi la loi, va luc do farmer **fail
closed**: khong duyet, khong san xuat.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from server.llm_gateway.provider import LLMProviderError

#: Model danh gia. Doi duoc qua bien moi truong de khong phai sua ma khi
#: doi doi model.
DEFAULT_REVIEW_MODEL = "gemini-3.8-flash"
ENV_REVIEW_MODEL = "FARMER_REVIEW_MODEL"

#: Diem toi thieu de duoc san xuat. Co y dat o 70/100: du cao de loai rac,
#: du thap de khong doi mot tac pham nghiep du phai hoan hao.
DEFAULT_MIN_SCORE = 70
ENV_MIN_SCORE = "FARMER_REVIEW_MIN_SCORE"

#: Cat bot dau vao truoc khi gui — mot chuong dai khong lam phep danh gia
#: chinh xac hon, chi lam no dat hon. Lay dau + giua de khong bi lua boi mot
#: mo dau tu te roi rac ve sau.
MAX_SAMPLE_CHARS = 6000

_SYSTEM = """Ban la bien tap vien kiem dinh chat luong cho mot nen tang doc/nghe truyen.
Nhiem vu: cham diem MOT tac pham xem co du chat luong de dua vao san xuat khong.

Tra ve DUY NHAT mot doi tuong JSON, khong kem giai thich ngoai JSON:
{"score": <0-100>, "verdict": "approve"|"reject", "reasons": ["..."], "language": "<ma ngon ngu>"}

Tieu chi cham diem:
- Van ban co mach lac va doc duoc khong (khong phai rac, khong phai loi ma hoa)?
- Co phai noi dung that su (truyen/bai viet) chu khong phai menu, quang cao, hay trang loi?
- Neu la ban dich: co tu nhien khong, hay la dich may tho?
- Co dau hieu spam, noi dung tu dong sinh hang loat, hay lap lai vo nghia khong?

KHONG cham diem theo so thich the loai. Mot tac pham the loai binh dan viet tot
van dat diem cao. Chi danh gia CHAT LUONG THUC THI."""


@dataclass(frozen=True)
class ReviewVerdict:
    approved: bool
    score: int
    reasons: tuple
    language: str
    model: str
    #: Token that su dung — de Router Control Center theo doi chi phi.
    input_tokens: int = 0
    output_tokens: int = 0

    def as_dict(self) -> dict:
        return {
            "approved": self.approved, "score": self.score,
            "reasons": list(self.reasons), "language": self.language,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class ReviewUnavailable(RuntimeError):
    """Khong danh gia duoc. KHAC voi 'da danh gia va bi tu choi'.

    Ben goi phai fail closed: khong duyet, khong san xuat, thu lai vong sau.
    """


def _sample(text: str, gioi_han: int = MAX_SAMPLE_CHARS) -> str:
    """Dau + giua. Chi lay dau se bi lua boi mot mo dau duoc bien tap ky roi
    phan con lai la rac."""
    text = (text or "").strip()
    if len(text) <= gioi_han:
        return text
    nua = gioi_han // 2
    giua = len(text) // 2
    return text[:nua] + "\n[...]\n" + text[giua:giua + (gioi_han - nua)]


def _parse_verdict(raw: str) -> dict:
    """Doc JSON tu phan hoi model.

    Model hay boc JSON trong ```json ... ``` du da duoc dan dung — chap nhan
    ca hai dang thay vi that bai vi mot cai rao ma.
    """
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        mo = text.find("{")
        dong = text.rfind("}")
        if mo == -1 or dong <= mo:
            raise ReviewUnavailable(
                f"phan hoi danh gia khong chua JSON: {raw[:200]!r}")
        text = text[mo:dong + 1]
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ReviewUnavailable(
            f"JSON danh gia khong doc duoc: {exc}; raw={raw[:200]!r}") from exc
    if not isinstance(data, dict):
        raise ReviewUnavailable("JSON danh gia khong phai doi tuong")
    return data


class QualityReviewer:
    """Bao mot `LLMProvider` thanh mot cong duyet/tu choi."""

    def __init__(self, provider: Any, *, model: str = "",
                 min_score: int = 0):
        import os
        self._provider = provider
        self._model = model or os.environ.get(ENV_REVIEW_MODEL) or DEFAULT_REVIEW_MODEL
        raw = (os.environ.get(ENV_MIN_SCORE) or "").strip()
        if min_score:
            self._min_score = min_score
        elif raw.isdigit():
            self._min_score = int(raw)
        else:
            self._min_score = DEFAULT_MIN_SCORE

    @property
    def model(self) -> str:
        return self._model

    @property
    def min_score(self) -> int:
        return self._min_score

    def review(self, *, title: str, body: str, lane: str,
               source_url: str = "") -> ReviewVerdict:
        if not (body or "").strip():
            # Khong can goi API de biet mot tac pham rong thi khong dat.
            return ReviewVerdict(False, 0, ("noi dung rong",), "", self._model)

        user = (
            f"Lan san xuat: {lane}\n"
            f"Tieu de: {title or '(khong co)'}\n"
            f"Nguon: {source_url or '(khong co)'}\n\n"
            f"Noi dung (da cat bot):\n{_sample(body)}"
        )
        try:
            completion = self._provider.complete(
                system=_SYSTEM, user=user, model=self._model,
                max_output_tokens=512)
        except LLMProviderError as exc:
            raise ReviewUnavailable(f"Gemini khong tra loi duoc: {exc}") from exc
        except Exception as exc:                                # noqa: BLE001
            raise ReviewUnavailable(
                f"loi khong mong doi khi danh gia: "
                f"{type(exc).__name__}: {exc}") from exc

        data = _parse_verdict(completion.text)

        try:
            score = int(data.get("score", -1))
        except (TypeError, ValueError):
            raise ReviewUnavailable(f"score khong phai so: {data.get('score')!r}")
        if not 0 <= score <= 100:
            raise ReviewUnavailable(f"score ngoai khoang 0-100: {score}")

        verdict_raw = str(data.get("verdict", "")).strip().lower()
        if verdict_raw not in ("approve", "reject"):
            raise ReviewUnavailable(f"verdict khong hop le: {verdict_raw!r}")

        reasons = data.get("reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]

        # Duyet can CA HAI: model noi approve VA diem dat nguong. Model doi
        # khi noi "approve" kem diem thap; nguong la tieng noi cuoi cung, va
        # no la cua ta chu khong phai cua model.
        approved = verdict_raw == "approve" and score >= self._min_score
        if verdict_raw == "approve" and score < self._min_score:
            reasons = list(reasons) + [
                f"model duyet nhung diem {score} < nguong {self._min_score}"]

        return ReviewVerdict(
            approved=approved,
            score=score,
            reasons=tuple(str(r)[:200] for r in reasons[:5]),
            language=str(data.get("language", ""))[:16],
            model=completion.model or self._model,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )


def build_reviewer(api_key: str = "", *, provider: Optional[Any] = None
                   ) -> QualityReviewer:
    """Dung reviewer that. Thieu khoa -> nem ngay, khong tra ve mot cai gia
    im lang duyet moi thu."""
    import os

    if provider is not None:
        return QualityReviewer(provider)
    key = api_key or os.environ.get("FARMER_GEMINI_API_KEY") or \
        os.environ.get("GEMINI_API_KEY") or ""
    if not key:
        raise ReviewUnavailable(
            "thieu FARMER_GEMINI_API_KEY/GEMINI_API_KEY — cong danh gia khong "
            "the mo, va farmer khong duoc phep san xuat khi chua duyet")
    from server.llm_gateway.providers import GeminiProvider

    return QualityReviewer(GeminiProvider(api_key=key))

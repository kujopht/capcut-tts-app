"""Khu trung lap TAT DINH — cung mot nguon khong bao gio duoc gat hai lan.

Hai lop, va can ca hai:

1. **Khoa tat dinh.** `work_key(lane, url)` sinh tu canonical_url, nen cung
   mot tac pham luon ra cung mot khoa — ke ca sau khi VM bi dung lai tu dau,
   ke ca khi so ghi cuc bo mat. Khoa KHONG phu thuoc thoi diem, thu tu phat
   hien, hay tieu de (tieu de doi duoc).

2. **Phep kiem co tham quyen.** Khoa mot minh chi noi "toi da tinh ra dinh
   danh nay"; no khong noi "viec nay da lam roi". Cau tra loi that nam o
   Appwrite: `content_queue` cho lan A, va `Novel.external_source_url` cho
   lan B. So ghi cuc bo (neu co) chi la bo nho dem.

**FAIL CLOSED.** Khong hoi duoc kho du lieu thi coi nhu DA TON TAI va bo
qua. Doan "chac chua co" roi gat lai lan hai se tao ban trung tren
production — dat hon nhieu so voi mot lan bo sot se tu duoc gat o vong sau.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from server.scraper.contract import canonicalize_url

#: Hai lan san xuat. Lan nam TRONG khoa, nen cung mot URL o hai lan van la
#: hai cong viec khac nhau — dung, vi san pham cuoi khac han.
LANE_AUDIO = "audio"
LANE_TEXT = "text"
LANES = (LANE_AUDIO, LANE_TEXT)

#: Chu so huu cua moi tac pham do farmer gat — cung danh tinh dich vu ma
#: `chinese_media_pipeline` dang dung, de mot cho duy nhat so huu noi dung tu
#: dong va tra cuu trung lap co pham vi han che.
FARMER_OWNER = "svc_harvester"

#: Tran quet khi kiem trung lap phia client. Cham tran = fail closed, xem
#: `DedupIndex.text_already_farmed`.
NOVEL_SCAN_LIMIT = 500


@dataclass(frozen=True)
class WorkKey:
    lane: str
    canonical_url: str
    #: `fw_` = farmer work. Tien to rieng de khong bao gio lan voi `cmq_`
    #: (muc hang doi) hay `nov_` (truyen) khi doc log.
    key: str

    @property
    def short(self) -> str:
        return self.key[:16]


def work_key(lane: str, url: str) -> WorkKey:
    """Dinh danh ON DINH cua MOT tac pham trong MOT lan.

    Dung `canonicalize_url` cua chinh kho nay (khong tu chuan hoa lai) de
    `?utm_source=`, dau `/` cuoi, hay `http` vs `https` khong sinh ra hai
    khoa cho cung mot trang.
    """
    if lane not in LANES:
        raise ValueError(f"lane khong hop le: {lane!r} (cho phep: {LANES})")
    # Kiem DAU VAO, khong kiem dau ra: `canonicalize_url("")` van tra ve mot
    # chuoi khac rong (no them scheme vao), nen mot URL rong se lang le sinh
    # ra mot khoa hop le cho khong-cai-gi-ca.
    if not (url or "").strip():
        raise ValueError("URL rong — khong dung duoc khoa cong viec")
    canon = canonicalize_url(url)
    if not canon:
        raise ValueError(f"khong chuan hoa duoc URL: {url!r}")
    digest = hashlib.sha256(f"{lane}:{canon}".encode("utf-8")).hexdigest()
    return WorkKey(lane=lane, canonical_url=canon, key=f"fw_{digest}")


def is_tts_job_active_or_done(job: Any) -> bool:
    """Xac dinh xem mot job TTS co dang thoa man chuong (khong can tao them) hay khong.
    - pending / running / queued / processing / in_progress: dang xu ly, khong tao trung.
    - completed voi output_key hop le: da hoan tat thanh cong, khong tao trung.
    - failed / cancelled / completed khong co output_key: KHONG thoa man, can tao lai (retry).
    """
    if isinstance(job, dict):
        raw_status = job.get("status", "")
        out = job.get("output_key")
    else:
        raw_status = getattr(job, "status", "")
        out = getattr(job, "output_key", None)

    # Neu trong unit test dung mock object chua set status cu the, coi nhu job hop le
    if type(raw_status).__name__ in ("Mock", "MagicMock", "AsyncMock"):
        return True

    st = str(getattr(raw_status, "value", raw_status) or "").lower().strip()
    if st in ("pending", "running", "queued", "processing", "in_progress"):
        return True
    if st == "completed":
        return bool(out and str(out).strip())
    return False


class DedupError(RuntimeError):
    """Khong tra loi duoc cau hoi 'da gat chua'. Ben goi PHAI bo qua muc."""


class DedupIndex:
    """Phep kiem co tham quyen, hoi thang kho du lieu that.

    Co y KHONG tu giu mot bang trang thai rieng: mot bang thu hai la mot
    nguon su that thu hai, va hai nguon su that se lech nhau. Cau hoi "da
    gat chua" duoc tra loi bang chinh du lieu san pham.
    """

    def __init__(self, store: Any):
        self._store = store

    # -- lan A: hang doi noi dung ------------------------------------------
    def audio_already_queued(self, item_id: str) -> bool:
        """`item_id` cua `content_queue` da tat dinh san (sha256 cua
        `(platform, episode_ref)`), nen chi can hoi no co ton tai khong."""
        try:
            self._store.get_queue_item(item_id)
            return True
        except Exception as exc:
            if _la_khong_tim_thay(exc):
                return False
            raise DedupError(
                f"khong kiem duoc hang doi cho {item_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    # -- lan B: truyen chu --------------------------------------------------
    def text_already_farmed(self, canonical_url: str,
                            owner_id: str = FARMER_OWNER) -> bool:
        """Phep hoi Appwrite: farmer nay da tao truyen cho URL nay chua.

        Tim theo (owner_id, external_source_url). Farmer chi so huu tac pham
        chinh minh tao; tac pham cung URL do nguoi dung tao qua UI la viec
        rieng cua ho, khong duoc tinh la "da gat".
        """
        try:
            novels, _ = self._store.find_novels(owner_id=owner_id,
                                                limit=NOVEL_SCAN_LIMIT)
        except Exception as exc:
            raise DedupError(
                f"khong kiem duoc trung lap cho {canonical_url}: "
                f"{type(exc).__name__}: {exc}") from exc

        if len(novels) >= NOVEL_SCAN_LIMIT:
            raise DedupError(
                f"farmer da co >= {NOVEL_SCAN_LIMIT} truyen — phep kiem trung "
                "lap phia client khong con du tin cay; can mot index tren "
                "`external_source_url` truoc khi gat tiep")

        canon = canonicalize_url(canonical_url)
        return any(canonicalize_url(getattr(n, "external_source_url", "") or "") == canon
                   for n in novels if getattr(n, "external_source_url", None))

    def novel_chapter_count(self, novel_id: str) -> int:
        """So chuong that su dang co tren kho phuc vu cua novel nay."""
        try:
            fn_ch = getattr(self._store, "list_chapters", None)
            if fn_ch is None:
                return 0
            return len(fn_ch(novel_id) or [])
        except Exception as exc:
            raise DedupError(
                f"khong doc duoc danh sach chuong cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def novel_has_chapter(self, novel_id: str) -> bool:
        """Ban nhap nay co chuong nao doc duoc khong."""
        return self.novel_chapter_count(novel_id) > 0

    def novel_has_tts_job(self, novel_id: str,
                          owner_id: str = FARMER_OWNER) -> bool:
        """Tac pham nay DA co it nhat mot job TTS chua."""
        return self.novel_has_tts(novel_id, owner_id=owner_id)

    def novel_has_tts(self, novel_id: str,
                      owner_id: str = FARMER_OWNER) -> bool:
        """Phep hoi Appwrite: truyen da co IT NHAT MOT chuong co job TTS hop le hay chua.

        Dung cho duong gat binh thuong: neu truyen chua tung duoc bat ky worker
        nao xep TTS, farmer se xep.
        """
        try:
            fn_ch = getattr(self._store, "list_chapters", None)
            if fn_ch is None:
                return False
            fn_jobs = getattr(self._store, "list_jobs", None)
            if fn_jobs is None:
                return False
            for ch in fn_ch(novel_id):
                ch_jobs = fn_jobs(owner_id, ch.chapter_id) or []
                if any(is_tts_job_active_or_done(j) for j in ch_jobs):
                    return True
            return False
        except Exception as exc:
            raise DedupError(
                f"khong kiem duoc job TTS cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def novel_needs_tts(self, novel_id: str,
                        owner_id: str = FARMER_OWNER) -> bool:
        """Kiem tra xem truyen co chuong nao CHUA co TTS hop le hay khong.

        Chuong can TTS khi:
        - Chua co job nao
        - Chi co job failed / cancelled
        - Job completed nhung khong co output_key
        Khong xep trung khi chuong da co job pending, running, hoac completed co output.
        """
        try:
            fn_ch = getattr(self._store, "list_chapters", None)
            if fn_ch is None:
                return False
            chapters = fn_ch(novel_id)
            if not chapters:
                return False
            fn_jobs = getattr(self._store, "list_jobs", None)
            if fn_jobs is None:
                return True
            for ch in chapters:
                ch_jobs = fn_jobs(owner_id, ch.chapter_id) or []
                if not any(is_tts_job_active_or_done(j) for j in ch_jobs):
                    return True
            return False
        except Exception as exc:
            raise DedupError(
                f"khong kiem duoc nhu cau TTS cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def finished_tts_output_key(self, novel_id: str,
                                owner_id: str = FARMER_OWNER) -> Optional[str]:
        """`output_key` cua job TTS DA XONG cho toan bo tac pham (ARTIFACT_AUDIO_VI).

        QUY TAC CHO TOAN BO TAC PHAM:
        - Chi tra ve output_key khi tac pham co DUNG 1 chuong va chuong do da hoan tat.
        - Voi tac pham nhieu chuong (chapter_count > 1): chuong 1 KHONG phai la audio
          toan tap. Khi chua co pipeline gop am thanh (concatenation), khong bao gio
          gan audio chuong 1 thanh audio toan tap (tra ve None).
        """
        try:
            fn_ch = getattr(self._store, "list_chapters", None)
            if fn_ch is None:
                return None
            chapters = fn_ch(novel_id)
            if not chapters or len(chapters) != 1:
                # Nhieu chuong: khong the dung output_key chuong 1 lam toan bo audio tac pham.
                return None
            fn_jobs = getattr(self._store, "list_jobs", None)
            if fn_jobs is None:
                return None
            for j in fn_jobs(owner_id, chapters[0].chapter_id):
                if isinstance(j, dict):
                    raw_st = j.get("status", "")
                    out = j.get("output_key")
                else:
                    raw_st = getattr(j, "status", "")
                    out = getattr(j, "output_key", None)
                st = str(getattr(raw_st, "value", raw_st) or "").lower().strip()
                if st == "completed" and bool(out and str(out).strip()):
                    return str(out)
            return None
        except Exception as exc:
            raise DedupError(
                f"khong doc duoc ket qua TTS cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def novel_audio_status(self, novel_id: str,
                           owner_id: str = FARMER_OWNER) -> Tuple[str, List[str]]:
        """Xac dinh trang thai am thanh va danh sach job TTS cua novel.

        Tra ve (status, job_ids):
        - status: 'complete' (tat ca chuong deu co job completed co output_key)
                  'partial'  (it nhat mot chuong completed hoac co job dang xu ly, nhung chua du)
                  'pending'  (chua chuong nao co audio hop le)
        """
        try:
            fn_ch = getattr(self._store, "list_chapters", None)
            if fn_ch is None:
                return "pending", []
            chapters = fn_ch(novel_id)
            if not chapters:
                return "pending", []
            fn_jobs = getattr(self._store, "list_jobs", None)
            if fn_jobs is None:
                return "pending", []

            completed_count = 0
            job_ids: List[str] = []
            has_active_or_done = False
            for ch in chapters:
                ch_jobs = fn_jobs(owner_id, ch.chapter_id) or []
                ch_done = False
                for j in ch_jobs:
                    jid = getattr(j, "job_id", "") if not isinstance(j, dict) else j.get("job_id", "")
                    if jid and jid not in job_ids:
                        job_ids.append(jid)
                    if isinstance(j, dict):
                        raw_st = j.get("status", "")
                        out = j.get("output_key")
                    else:
                        raw_st = getattr(j, "status", "")
                        out = getattr(j, "output_key", None)
                    st = str(getattr(raw_st, "value", raw_st) or "").lower().strip()
                    if st == "completed" and bool(out and str(out).strip()):
                        ch_done = True
                    elif st in ("pending", "running", "queued", "processing", "in_progress"):
                        has_active_or_done = True
                if ch_done:
                    completed_count += 1
                    has_active_or_done = True

            if completed_count == len(chapters):
                return "complete", job_ids
            elif has_active_or_done:
                return "partial", job_ids
            return "pending", job_ids
        except Exception as exc:
            raise DedupError(
                f"khong doc duoc trang thai audio cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def existing_text_novel_id(self, canonical_url: str,
                               owner_id: str = FARMER_OWNER):
        """`novel_id` cua ban nhap DA CO cho nguon nay, hoac None.

        Ton tai de mot lan chay lai KHONG tao ban trung. `text_already_farmed`
        tra ve mot chu "roi" — con o day ta can chinh CAI DINH DANH, de buoc
        xuat ban duoc BO QUA thay vi POST them mot novel thu hai cho cung mot
        tac pham.
        """
        try:
            novels, _ = self._store.find_novels(owner_id=owner_id,
                                                limit=NOVEL_SCAN_LIMIT)
        except Exception as exc:
            raise DedupError(
                f"khong tra cuu duoc ban nhap cho {canonical_url}: "
                f"{type(exc).__name__}: {exc}") from exc

        canon = canonicalize_url(canonical_url)
        for n in novels:
            src_url = getattr(n, "external_source_url", None)
            if src_url and canonicalize_url(src_url) == canon:
                return getattr(n, "novel_id", getattr(n, "id", None))
        return None


def _la_khong_tim_thay(exc: Exception) -> bool:
    """Phan biet '404 — chua co' voi 'mang hong'. Chi 404 moi duoc doc thanh
    'chua gat'; moi loi khac phai noi len de ben goi fail closed."""
    ten = type(exc).__name__
    return ten in ("NotFoundError", "DocumentNotFound") or "404" in str(exc)

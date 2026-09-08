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
from typing import Any, Optional

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
        """`external_source_url` la dinh danh chinh tac cua nguon trong ca kho
        nay — cung truong ma `chinese_media_pipeline.ship_draft` dung de khong
        POST trung.

        Appwrite khong co index cho truong nay, va kho chua co ham tra cuu
        chuyen dung, nen loc phia client tren danh sach truyen CUA CHINH
        farmer (`owner_id`) — cung ky thuat `ship_draft` dang dung, chi khac
        la gioi han theo chu so huu thay vi keo ca bang ve.
        """
        try:
            novels, _ = self._store.find_novels(owner_id=owner_id,
                                                limit=NOVEL_SCAN_LIMIT)
        except Exception as exc:
            raise DedupError(
                f"khong kiem duoc trung lap cho {canonical_url}: "
                f"{type(exc).__name__}: {exc}") from exc

        if len(novels) >= NOVEL_SCAN_LIMIT:
            # Da cham tran quet: mot ban ghi cu hon tran co the ton tai ma
            # khong nhin thay. Fail closed thay vi tao ban trung am tham.
            raise DedupError(
                f"farmer da co >= {NOVEL_SCAN_LIMIT} truyen — phep kiem trung "
                "lap phia client khong con du tin cay; can mot index tren "
                "`external_source_url` truoc khi gat tiep")

        canon = canonicalize_url(canonical_url)
        return any(canonicalize_url(n.external_source_url or "") == canon
                   for n in novels if n.external_source_url)

    def novel_has_tts_job(self, novel_id: str,
                          owner_id: str = FARMER_OWNER) -> bool:
        """Tac pham nay DA co job TTS chua — hoi kho, khong suy dien.

        Can cho lan chay tiep. Suy dien "dang chay tiep tuc la lan truoc da
        xep TTS roi" NGHE hop ly nhung SAI: buoc xuat ban va buoc TTS la hai
        buoc khac nhau, va mot tac pham co the da co ban nhap ma chua bao gio
        xep duoc TTS (vd loi mang dung giua hai buoc). Suy dien nhu vay se de
        no CAM LANG vinh vien — cung hinh dang loi voi cai vua sua o tren,
        chi khac cho.

        `DedupError` khi khong hoi duoc. Ben goi BO QUA TTS vong nay roi thu
        lai vong sau: mot su co Appwrite la tam thoi, con mot job TTS trung
        la tien tinh that cho cung mot ban thu am.
        """
        try:
            for ch in self._store.list_chapters(novel_id):
                if self._store.list_jobs(owner_id, ch.chapter_id):
                    return True
            return False
        except Exception as exc:
            raise DedupError(
                f"khong kiem duoc job TTS cua {novel_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def existing_text_novel_id(self, canonical_url: str,
                               owner_id: str = FARMER_OWNER):
        """`novel_id` cua ban nhap DA CO cho nguon nay, hoac None.

        Ton tai de mot lan chay lai KHONG tao ban trung. `text_already_farmed`
        tra ve mot chu "roi" — con o day ta can chinh CAI DINH DANH, de buoc
        xuat ban duoc BO QUA thay vi POST them mot novel thu hai cho cung mot
        tac pham.

        Do la khac biet giua "da gat roi" va "da gat DEN DAU". Mot tac pham co
        ban ghi novel nhung chua co hien vat la mot tac pham DANG DO, khong
        phai mot tac pham xong.
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
            if n.external_source_url and \
                    canonicalize_url(n.external_source_url) == canon:
                return n.novel_id
        return None


def _la_khong_tim_thay(exc: Exception) -> bool:
    """Phan biet '404 — chua co' voi 'mang hong'. Chi 404 moi duoc doc thanh
    'chua gat'; moi loi khac phai noi len de ben goi fail closed."""
    ten = type(exc).__name__
    return ten in ("NotFoundError", "DocumentNotFound") or "404" in str(exc)

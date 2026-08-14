"""
Doi tuong du lieu cua Novel Translation Studio (V5).

Tach khoi `server/translation.py` (chinh sach thuan) va `server/domain.py`
(doi tuong cua san pham audio) vi day la MOT subsystem rieng — khong dung
chung bang voi `tts_jobs`/`Novel`/`Chapter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from server.translation import (
    GenrePreset,
    NamingMode,
    QualityMode,
    TranslationJobStatus,
)


def _id(tien_to: str) -> str:
    import secrets

    return f"{tien_to}_{secrets.token_hex(8)}"


@dataclass
class TranslationProject:
    """
    Mot du an dich — MOT tac pham nguon (co the nhieu chuong).

    `source_text` giu NGUYEN VAN goc: can lai de doi chieu QA / dich lai mot
    chuong / xuat song ngu sau nay. Khong xoa sau khi dich xong.
    """

    owner_id: str
    title: str
    source_text: str
    source_language: str = "zh"
    target_language: str = "vi"
    genre: GenrePreset = GenrePreset.AUTO
    naming_mode: NamingMode = NamingMode.AUTO
    quality_mode: QualityMode = QualityMode.CAN_BANG
    custom_instruction: str = ""
    #: Ten tep goc, neu tai len (khong phai dan/paste) — chi de hien thi.
    source_filename: str = ""
    #: Tom tat NGAN moi chuong da dich — "rolling memory", xem yeu cau muc 7.
    #: Danh sach, chi so khop voi chi so chuong trong `chapters`.
    chapter_summaries: List[str] = field(default_factory=list)
    #: Ban dich hoan chinh moi chuong, dien dan khi job chay. Rong = chua dich.
    translated_chapters: List[str] = field(default_factory=list)
    #: Da nhap vao truyen nao roi (novel_id) — chan nhap trung. Rong = chua.
    imported_to_novel_id: str = ""
    project_id: str = field(default_factory=lambda: _id("trp"))
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        from server.translation import GENRE_LABELS, NAMING_LABELS, tach_chuong

        return {
            "project_id": self.project_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "genre": self.genre.value,
            "genre_label": GENRE_LABELS.get(self.genre.value, self.genre.value),
            "naming_mode": self.naming_mode.value,
            "naming_mode_label": NAMING_LABELS.get(self.naming_mode.value,
                                                   self.naming_mode.value),
            "quality_mode": self.quality_mode.value,
            "custom_instruction": self.custom_instruction,
            "source_filename": self.source_filename,
            "chapter_count": len(tach_chuong(self.source_text)),
            "translated_chapter_count": len(
                [c for c in self.translated_chapters if c]),
            "imported_to_novel_id": self.imported_to_novel_id or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class TranslationJob:
    """
    Mot lan chay dich cho MOT `TranslationProject`.

    So voi `TtsJob`: them `current_step`/`current_chapter`/`total_chapters` vi
    nguoi dung can biet DANG O BUOC NAO (Phase 12 UI: "Đang biên tập...",
    khong chi mot % chung chung).

    Phan claim/lease (`attempts`/`lease_owner`/`lease_expires_at`) CUNG KHUON
    voi `TtsJob` (`server/domain.py`) — mot worker rieng
    (`server/translation_worker.py`) co the nhan/gia han/nha job nay bang
    dung logic CAS da chung minh o pipeline audio, tren BANG RIENG
    (`translation_jobs`/`translation_job_claims`), khong dung chung voi
    `tts_jobs`/`job_claims`.
    """

    project_id: str
    owner_id: str
    status: TranslationJobStatus = TranslationJobStatus.QUEUED
    current_chapter: int = 0
    total_chapters: int = 0
    #: Doan da xu ly / tong so doan CUA CHUONG DANG CHAY — tien do min hon.
    current_chapter_done_segments: int = 0
    current_chapter_total_segments: int = 0
    #: Vai tro provider dang chay NGAY LUC NAY trong chuong hien tai
    #: ("translator"/"editor"/"qa"), rong khi job chua chay/da ket thuc. Chi
    #: la thong tin hien thi (UI: "Đang biên tập văn học...") — KHONG dung de
    #: re nhanh logic, `status` moi la nguon that cho may trang thai.
    current_pass: str = ""
    #: Fencing token — TANG MOI LAN mot worker claim job nay THANH CONG.
    #: Truoc day ten la `retry_count` nhung KHONG bao gio duoc dung (khong
    #: worker nao, khong claim nao) — doi ten cho dung vai tro that: day la
    #: token CAS, cung khuon voi `TtsJob.attempts`.
    attempts: int = 0
    #: Ai dang giu job nay — rong khi khong ai giu (queued/da ket thuc).
    lease_owner: str = ""
    #: Lease het han luc nao (ISO 8601). Rong = khong co lease.
    lease_expires_at: str = ""
    #: Da lam sach (khong lo chi tiet noi bo/stack trace) — xem
    #: `TranslationService._loi_an_toan`.
    error: str = ""
    job_id: str = field(default_factory=lambda: _id("trj"))
    created_at: str = ""
    updated_at: str = ""
    finished_at: str = ""

    def progress_percent(self) -> int:
        """Uoc luong % TOAN job, khong chi chuong dang chay."""
        if self.status is TranslationJobStatus.COMPLETED:
            return 100
        if self.total_chapters <= 0:
            return 0
        moi_chuong = 100.0 / self.total_chapters
        da_xong = max(0, self.current_chapter - 1) * moi_chuong
        trong_chuong_nay = 0.0
        if self.current_chapter_total_segments > 0:
            trong_chuong_nay = (
                self.current_chapter_done_segments
                / self.current_chapter_total_segments) * moi_chuong
        return min(100, int(da_xong + trong_chuong_nay))

    def lease_is_live(self, now: Optional[datetime] = None) -> bool:
        """
        Con worker nao dang thuc su giu job nay hay khong.

        Cung logic voi `TtsJob.lease_is_live` — khong co lease thi coi la
        KHONG con song (job cu truoc khi co lease, hoac da nha lease khi
        xong, deu roi vao day dung y muon).
        """
        if not self.lease_expires_at:
            return False
        moment = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(self.lease_expires_at)
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > moment

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
            "current_pass": self.current_pass or None,
            "progress": self.progress_percent(),
            "attempts": self.attempts,
            "error": self.error or None,
            "last_error": self.error or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at or None,
        }

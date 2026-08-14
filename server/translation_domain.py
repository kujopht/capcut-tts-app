"""
Doi tuong du lieu cua Novel Translation Studio (V5).

Tach khoi `server/translation.py` (chinh sach thuan) va `server/domain.py`
(doi tuong cua san pham audio) vi day la MOT subsystem rieng — khong dung
chung bang voi `tts_jobs`/`Novel`/`Chapter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """

    project_id: str
    owner_id: str
    status: TranslationJobStatus = TranslationJobStatus.QUEUED
    current_chapter: int = 0
    total_chapters: int = 0
    #: Doan da xu ly / tong so doan CUA CHUONG DANG CHAY — tien do min hon.
    current_chapter_done_segments: int = 0
    current_chapter_total_segments: int = 0
    retry_count: int = 0
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
            "progress": self.progress_percent(),
            "retry_count": self.retry_count,
            "error": self.error or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at or None,
        }

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
    #: Canh bao QA THAT phat hien duoc cho tung chuong da dich — chi so khop
    #: voi `translated_chapters` (Part N muc 18). Xem
    #: `translation.phat_hien_canh_bao` — hien chi kiem tra con sot ky tu Han
    #: trong ban dich, MOT tin hieu that, khong bia dat.
    chapter_warnings: List[List[str]] = field(default_factory=list)
    #: Part Q3 — AUTO ("auto") hay MANUAL ("manual") chon provider. Rong tuong
    #: duong "auto" (chua ai chon).
    provider_mode: str = "auto"
    #: Provider da chon THU CONG — chi co y nghia khi `provider_mode="manual"`.
    selected_provider_id: str = ""
    #: MANUAL + fallback BAT: het han muc thi thu provider MIEN PHI khac.
    #: MANUAL + fallback TAT: het han muc thi cho (`waiting_for_provider`),
    #: KHONG tu doi model. AUTO luon coi nhu fallback BAT (bo qua co nay).
    allow_fallback: bool = True
    #: V5.1 Part F — "Ưu tiên API key cá nhân". False (mac dinh): thu tu
    #: THUONG (Fanfic chung TRUOC, ca nhan sau). True: dao nguoc — ca nhan
    #: TRUOC, Fanfic chung la du phong. KHONG anh huong gi neu nguoi dung
    #: chua ket noi provider ca nhan nao (danh sach ca nhan rong -> hanh vi
    #: y het truoc day).
    prefer_personal_provider: bool = False
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
            "provider_mode": self.provider_mode,
            "selected_provider_id": self.selected_provider_id or None,
            "allow_fallback": self.allow_fallback,
            "prefer_personal_provider": self.prefer_personal_provider,
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
    #: Part Q4 — moc thoi gian (ISO) job co the duoc thu lai, CHI co y nghia
    #: khi `status is WAITING_FOR_PROVIDER`. Rong = khong biet moc chinh xac
    #: (hien UI: "Đang chờ nhà cung cấp mở lại hạn mức", KHONG bia gio).
    waiting_retry_at: str = ""
    #: V5.1 Part G — LY DO AN TOAN (khong lo chi tiet noi bo) cho frontend
    #: quyet dinh hien CTA nao. "shared_free_quota_exhausted" (nguoi dung
    #: CHUA co ket noi ca nhan nao — moi CTA "kết nối Groq cá nhân") hoac
    #: "personal_quota_exhausted"/"" (da co ket noi ca nhan nhung CUNG het
    #: han muc — chi con cho). Rong = job khong o waiting_for_provider.
    waiting_reason: str = ""
    #: HANH DONG AN TOAN goi y cho frontend — "connect_personal_provider"
    #: hoac rong (khong co hanh dong nao khac ngoai cho).
    waiting_action: str = ""
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
            "waiting_retry_at": self.waiting_retry_at or None,
            "waiting_reason": self.waiting_reason or None,
            "waiting_action": self.waiting_action or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at or None,
        }


@dataclass
class TranslationVersion:
    """
    MOT ban ghi lich su cho MOT chuong (Part O) — dich nhe, KHONG git.

    Moi lan tao/ghi de noi dung dich (tu dong luc chay job, dich lai mot
    doan/chuong, chay rieng mot pass, hoac nguoi dung tu sua) deu tao THEM
    mot ban ghi — KHONG BAO GIO sua/xoa ban ghi cu, chi them (`additive`).
    Phuc hoi (`restore`) ghi mot ban ghi MOI voi `operation="restore"", KHONG
    quay lai xoa lich su sau diem do — giu dung tinh chat "them, khong bao
    gio mat".
    """

    project_id: str
    chapter_index: int
    #: "auto_translate" | "manual_edit" | "regenerate_paragraph" |
    #: "regenerate_chapter" | "rerun_pass" | "restore"
    operation: str
    #: "translator" | "editor" | "qa" | "manual"
    pass_type: str
    previous_text: str
    new_text: str
    actor_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    #: None = ca chuong. Co gia tri = chi mot doan cu the (regen doan).
    paragraph_index: Optional[int] = None
    version_id: str = field(default_factory=lambda: _id("trv"))
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "chapter_index": self.chapter_index,
            "paragraph_index": self.paragraph_index,
            "operation": self.operation,
            "pass_type": self.pass_type,
            "previous_text": self.previous_text,
            "new_text": self.new_text,
            "actor_id": self.actor_id or None,
            "provider_id": self.provider_id or None,
            "model_id": self.model_id or None,
            "created_at": self.created_at,
        }


def id_ket_noi_provider(user_id: str, provider_id: str) -> str:
    """
    ID TAT DINH tu (user_id, provider_id) — KHONG ngau nhien.

    MOI nguoi dung CHI co MOT ket noi cho MOI provider: "kien" lai (goi
    connect lan hai voi cung provider) tu nhien GHI DE dung ban ghi cu
    (cung id) thay vi tao ban ghi thu hai mo côi — dung y voi tinh chat
    upsert cua "Lưu kết nối"/"Thay API key" (Part J).
    """
    return f"pc_{abs(hash((user_id, provider_id))) % (10 ** 12):012x}"


@dataclass
class ProviderConnection:
    """
    Ket noi provider AI CA NHAN cua MOT nguoi dung (V5.1, BYOK).

    `encrypted_secret` LA CHUOI DA MA HOA (xem `translation_byok_crypto.py`)
    — KHONG BAO GIO la api key ro. Entity nay VA `to_dict()` cua no la RANH
    GIOI AN TOAN duy nhat: bat ky noi nao tra `to_dict()` ra ngoai (route,
    log) deu KHONG THE lam lo bi mat, vi truong do khong ton tai trong dict.
    """

    user_id: str
    provider_id: str
    #: Chuoi da ma hoa (dinh dang `byok.v1.<nonce>.<ciphertext>`) — KHONG
    #: BAO GIO xuat hien trong `to_dict()`.
    encrypted_secret: str
    #: 4 ky tu cuoi cua key that — CHI de hien thi ("••••••••AB42"), khong du
    #: de doan lai key (xem `translation_byok_crypto.lay_4_ky_tu_cuoi`).
    last4: str
    #: Gia tri cua `ProviderStatus` (xem `translation_provider_registry.py`)
    #: — "unknown" cho den lan kiem tra dau tien.
    status: str = "unknown"
    selected_model: str = ""
    connection_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    #: Lan gan nhat kiem tra ket noi THANH CONG (khong phai lan tao). Rong =
    #: chua tung kiem tra thanh cong.
    last_verified_at: str = ""

    def __post_init__(self) -> None:
        if not self.connection_id:
            self.connection_id = id_ket_noi_provider(self.user_id, self.provider_id)

    def to_dict(self) -> Dict[str, Any]:
        """AN TOAN de tra ve qua API — xem docstring dau class. Danh sach
        truong o day LA TOAN BO nhung gi frontend duoc phep thay."""
        return {
            "provider_id": self.provider_id,
            "connected": True,
            "last4": self.last4,
            "status": self.status,
            "selected_model": self.selected_model or None,
            "last_verified_at": self.last_verified_at or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

"""
Dataclass, enum va ham tro giup dung chung cho Fanfic Audio Studio.

Module nay khong import PySide6 va khong goi mang, nen co the unit test doc lap.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# -----------------------------------------------------------------------------
# Hang so hanh vi API (giu nguyen tu ban Gradio da kiem chung)
# -----------------------------------------------------------------------------

CONNECT_TIMEOUT = 8.0
READ_TIMEOUT_CREATE = 20.0
READ_TIMEOUT_QUERY = 12.0
READ_TIMEOUT_DOWNLOAD = 30.0

POLL_TOTAL_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 3.0

DONE_STATUSES = {"success", "succeed", "completed", "done"}
FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}

SHARK_MARKERS = ("shark", "verify_center", "secsdk", "captcha", "risk_control")

# HTTP 429: backoff + thu lai toi da 3 lan
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = (5.0, 15.0, 30.0)

# Nghi giua cac request de khong spam API
GAP_BETWEEN_JOBS = 5.0
GAP_BETWEEN_PARTS = 2.0

DEFAULT_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 5000

MAX_WORKERS = 2
JOB_COUNT_CONFIRM_THRESHOLD = 50

SUPPORTED_EXTENSIONS = (".txt", ".md", ".docx")


# -----------------------------------------------------------------------------
# Enum trang thai
# -----------------------------------------------------------------------------


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"      # mot so part xong, mot so that bai
    FAILED = "failed"
    STOPPED = "stopped"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in (
            JobState.SUCCESS,
            JobState.PARTIAL,
            JobState.FAILED,
            JobState.STOPPED,
            JobState.SKIPPED,
        )

    @property
    def is_retryable(self) -> bool:
        return self in (JobState.FAILED, JobState.PARTIAL, JobState.STOPPED)


class PartState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class QueueState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    BLOCKED = "blocked"      # 403 / shark: dung han de khong spam API
    FINISHED = "finished"


class ErrorKind(str, Enum):
    """Phan loai loi de hien thi va ghi report."""

    CONNECT_TIMEOUT = "connect_timeout"
    READ_TIMEOUT = "read_timeout"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    SSL_ERROR = "ssl_error"
    PROXY_ERROR = "proxy_error"
    REQUEST_ERROR = "request_error"
    HTTP_403 = "http_403"
    HTTP_429 = "http_429"
    HTTP_ERROR = "http_error"
    SHARK_BLOCK = "shark_block"
    BAD_RESPONSE = "bad_response"
    API_ERROR = "api_error"
    NO_TASK = "no_task"
    TASK_MISSING_FIELDS = "task_missing_fields"
    TASK_FAILED = "task_failed"
    POLL_TIMEOUT = "poll_timeout"
    NO_AUDIO_URL = "no_audio_url"
    DOWNLOAD_ERROR = "download_error"
    EMPTY_AUDIO = "empty_audio"
    DISK_ERROR = "disk_error"
    EMPTY_TEXT = "empty_text"
    READ_FILE_ERROR = "read_file_error"
    MERGE_FFMPEG_MISSING = "merge_ffmpeg_missing"
    MERGE_ERROR = "merge_error"
    STOPPED = "stopped"
    UNEXPECTED = "unexpected"

    @property
    def is_fatal_for_queue(self) -> bool:
        """403 va shark block: phai dung hang doi, khong gui tiep hang loat."""
        return self in (ErrorKind.HTTP_403, ErrorKind.SHARK_BLOCK)


#: Mo ta tieng Viet cho tung loai loi (dung trong bang loi cua giao dien)
ERROR_HINTS: Dict[str, str] = {
    ErrorKind.CONNECT_TIMEOUT: "Không kết nối được máy chủ trong 8s. Kiểm tra internet/VPN/firewall.",
    ErrorKind.READ_TIMEOUT: "Máy chủ không trả lời kịp. Thử lại hoặc chia nhỏ văn bản.",
    ErrorKind.TIMEOUT: "Hết thời gian chờ.",
    ErrorKind.NETWORK_ERROR: "Lỗi mạng/DNS. Kiểm tra kết nối.",
    ErrorKind.SSL_ERROR: "Lỗi SSL. Kiểm tra proxy/chứng chỉ.",
    ErrorKind.PROXY_ERROR: "Lỗi proxy.",
    ErrorKind.REQUEST_ERROR: "Lỗi request.",
    ErrorKind.HTTP_403: "HTTP 403 — request bị từ chối. device/sign có thể đã hết hiệu lực.",
    ErrorKind.HTTP_429: "HTTP 429 — bị giới hạn tần suất. Đã tự backoff và thử lại.",
    ErrorKind.HTTP_ERROR: "Máy chủ trả về mã lỗi HTTP.",
    ErrorKind.SHARK_BLOCK: "Bị hệ thống bảo vệ (shark/captcha) chặn. Hàng đợi đã dừng.",
    ErrorKind.BAD_RESPONSE: "Phản hồi không phải JSON hợp lệ.",
    ErrorKind.API_ERROR: "API báo lỗi (ret khác 0).",
    ErrorKind.NO_TASK: "API không trả về task nào.",
    ErrorKind.TASK_MISSING_FIELDS: "Task thiếu id hoặc token.",
    ErrorKind.TASK_FAILED: "Task bị báo thất bại.",
    ErrorKind.POLL_TIMEOUT: "Hết 60s chờ mà task chưa xong.",
    ErrorKind.NO_AUDIO_URL: "Task thành công nhưng phản hồi không có URL audio.",
    ErrorKind.DOWNLOAD_ERROR: "Lỗi khi tải file audio.",
    ErrorKind.EMPTY_AUDIO: "File audio tải về rỗng.",
    ErrorKind.DISK_ERROR: "Không ghi được file xuống đĩa.",
    ErrorKind.EMPTY_TEXT: "Văn bản rỗng.",
    ErrorKind.READ_FILE_ERROR: "Không đọc được file nguồn.",
    ErrorKind.MERGE_FFMPEG_MISSING: "Không tìm thấy ffmpeg nên chưa ghép được file full. Các part vẫn còn nguyên.",
    ErrorKind.MERGE_ERROR: "Lỗi khi ghép file MP3.",
    ErrorKind.STOPPED: "Đã dừng theo yêu cầu người dùng.",
    ErrorKind.UNEXPECTED: "Lỗi ngoài dự kiến.",
}


# -----------------------------------------------------------------------------
# Ham tro giup
# -----------------------------------------------------------------------------

_DIACRITIC_MAP = str.maketrans({"đ": "d", "Đ": "D", "ð": "d", "Ð": "D"})


def slugify(value: str, fallback: str = "input", max_length: int = 60) -> str:
    """
    Chuyen ten tieng Viet thanh ten thu muc/file an toan cho Windows.
    Vi du: "Nhỏ Ngọt Ngào" -> "nho_ngot_ngao"
    """
    text = (value or "").strip().translate(_DIACRITIC_MAP)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return fallback
    return text[:max_length].strip("_") or fallback


def content_hash(text: str) -> str:
    """SHA-256 cua noi dung van ban (dung de nhan dien/resume)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def mask_secret(value: Optional[str], keep: int = 4) -> Optional[str]:
    """
    Che gia tri nhay cam truoc khi ghi ra manifest/log.
    Chi giu vai ky tu dau + do dai, khong bao gio ghi token day du.
    """
    if not value:
        return None
    text = str(value)
    if len(text) <= keep:
        return "*" * len(text)
    return f"{text[:keep]}…({len(text)} ký tự, đã che)"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def human_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


# -----------------------------------------------------------------------------
# Voice
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceEntry:
    """
    Mot giong doc trong Voice.json.

    Schema thuc te cua Voice.json: lan, lang, voice_type, display_name,
    resource_id, captured_at. Moi field deu co the thieu o cac ban catalog khac,
    nen tat ca dung Optional/default va giao dien chi hien khi co du lieu.
    """

    voice_type: str
    display_name: str = ""
    resource_id: str = ""
    lang: str = ""
    lan: str = ""
    captured_at: str = ""
    extra: Dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def uid(self) -> str:
        """
        Khoa duy nhat. Voice.json thuc te co 2 voice_type bi trung lap,
        nen phai ghep them resource_id de khong nhap nhang khi chon.
        """
        return f"{self.voice_type}|{self.resource_id}"

    @property
    def label(self) -> str:
        return self.display_name or self.voice_type

    @property
    def language(self) -> str:
        """Ngon ngu de hien thi/loc: uu tien `lang`, du phong `lan`."""
        return self.lang or self.lan or ""

    @property
    def slug(self) -> str:
        return slugify(self.display_name or self.voice_type, fallback="voice")

    def matches(self, needle: str) -> bool:
        """Tim kiem theo ten hien thi va voice_type (khong phan biet hoa/thuong, bo dau)."""
        if not needle:
            return True
        needle = needle.strip().lower()
        haystacks = [
            (self.display_name or "").lower(),
            (self.voice_type or "").lower(),
            slugify(self.display_name or ""),
            (self.resource_id or "").lower(),
            (self.language or "").lower(),
        ]
        needle_slug = slugify(needle, fallback="")
        for hay in haystacks:
            if needle in hay:
                return True
            if needle_slug and needle_slug in hay:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "voice_type": self.voice_type,
            "display_name": self.display_name,
            "resource_id": self.resource_id,
            "lang": self.lang,
            "lan": self.lan,
        }
        if self.captured_at:
            data["captured_at"] = self.captured_at
        return data

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["VoiceEntry"]:
        """Tao VoiceEntry tu 1 phan tu Voice.json. Tra None neu thieu voice_type."""
        if not isinstance(raw, dict):
            return None
        voice_type = str(raw.get("voice_type") or "").strip()
        if not voice_type:
            return None
        known = {"voice_type", "display_name", "resource_id", "lang", "lan", "captured_at"}
        return cls(
            voice_type=voice_type,
            display_name=str(raw.get("display_name") or "").strip(),
            resource_id=str(raw.get("resource_id") or "").strip(),
            lang=str(raw.get("lang") or "").strip(),
            lan=str(raw.get("lan") or "").strip(),
            captured_at=str(raw.get("captured_at") or "").strip(),
            extra={k: v for k, v in raw.items() if k not in known},
        )


# -----------------------------------------------------------------------------
# Input (van ban truc tiep hoac file)
# -----------------------------------------------------------------------------


class InputKind(str, Enum):
    TEXT = "text"
    FILE = "file"


@dataclass
class InputItem:
    """Mot nguon van ban: nhap truc tiep hoac mot file."""

    name: str
    text: str = ""
    kind: InputKind = InputKind.TEXT
    path: Optional[str] = None
    voice_uids: List[str] = field(default_factory=list)
    error: str = ""
    error_kind: Optional[str] = None
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def char_count(self) -> int:
        return len(self.text or "")

    @property
    def slug(self) -> str:
        base = self.name
        if self.kind == InputKind.FILE and self.path:
            base = Path(self.path).stem or self.name
        return slugify(base, fallback="input")

    @property
    def is_valid(self) -> bool:
        return not self.error and bool((self.text or "").strip())

    @property
    def status_text(self) -> str:
        if self.error:
            return f"Lỗi: {self.error}"
        if not (self.text or "").strip():
            return "Lỗi: nội dung rỗng"
        return "Sẵn sàng"

    def source_label(self) -> str:
        if self.kind == InputKind.FILE and self.path:
            return self.path
        return "(nhập trực tiếp)"


# -----------------------------------------------------------------------------
# Job va part
# -----------------------------------------------------------------------------


@dataclass
class JobPart:
    """Mot phan cua job (van ban dai bi chia nhieu part)."""

    index: int                       # bat dau tu 1
    text: str
    state: PartState = PartState.PENDING
    file_path: Optional[str] = None
    file_size: int = 0
    task_id: Optional[str] = None
    token_masked: Optional[str] = None
    audio_url_host: Optional[str] = None
    error_kind: Optional[str] = None
    error_message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    attempts: int = 0

    @property
    def file_name(self) -> str:
        return f"part_{self.index:03d}.mp3"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "file": self.file_name,
            "state": self.state.value,
            "chars": len(self.text or ""),
            "size_bytes": self.file_size,
            "task_id": self.task_id,
            "token": self.token_masked,     # da che, khong bao gio ghi token that
            "audio_host": self.audio_url_host,
            "attempts": self.attempts,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_kind": self.error_kind,
            "error_message": self.error_message[:500] if self.error_message else "",
        }


@dataclass
class Job:
    """Mot cap (input x voice). Cac part cua cung job luon chay tuan tu."""

    input_name: str
    input_slug: str
    voice: VoiceEntry
    text: str
    rate: str = "1.0"
    chunk_chars: int = DEFAULT_CHUNK_CHARS
    input_kind: InputKind = InputKind.TEXT
    input_path: Optional[str] = None
    parts: List[JobPart] = field(default_factory=list)
    state: JobState = JobState.PENDING
    message: str = "Chờ trong hàng đợi"
    error_kind: Optional[str] = None
    error_detail: str = ""
    job_dir: Optional[str] = None
    full_path: Optional[str] = None
    merge_note: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def label(self) -> str:
        return f"{self.input_name} → {self.voice.label}"

    @property
    def content_hash(self) -> str:
        return content_hash(self.text)

    @property
    def total_parts(self) -> int:
        return len(self.parts)

    @property
    def done_parts(self) -> int:
        return sum(1 for p in self.parts if p.state == PartState.SUCCESS)

    @property
    def failed_parts(self) -> int:
        return sum(1 for p in self.parts if p.state == PartState.FAILED)

    @property
    def progress_percent(self) -> int:
        if not self.parts:
            return 0
        return int(round(100.0 * self.done_parts / len(self.parts)))

    def pending_parts(self) -> List[JobPart]:
        """Cac part chua thanh cong — dung cho resume va retry."""
        return [p for p in self.parts if p.state != PartState.SUCCESS]

    def reset_for_retry(self) -> None:
        """Chuan bi chay lai: chi reset part chua thanh cong (giu checkpoint)."""
        for part in self.parts:
            if part.state != PartState.SUCCESS:
                part.state = PartState.PENDING
                part.error_kind = None
                part.error_message = ""
        self.state = JobState.PENDING
        self.error_kind = None
        self.error_detail = ""
        self.message = "Chờ chạy lại"
        self.finished_at = None

    def to_manifest(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "input_name": self.input_name,
            "input_kind": self.input_kind.value,
            "source_file": self.input_path,
            "content_sha256": self.content_hash,
            "text_length": len(self.text or ""),
            "voice_display_name": self.voice.display_name,
            "voice_type": self.voice.voice_type,
            "resource_id": self.voice.resource_id,
            "language": self.voice.language,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "state": self.state.value,
            "message": self.message,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail[:1000] if self.error_detail else "",
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "job_dir": self.job_dir,
            "full_audio": self.full_path,
            "merge_note": self.merge_note,
            "parts": [p.to_dict() for p in self.parts],
        }

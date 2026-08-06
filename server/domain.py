"""
Mo hinh du lieu cua nen tang web.

Thiet ke SAN cho cac tinh nang giai doan sau (draft/published, quota, tier,
lich su nghe, moderation) nhung giai doan nay CHUA trien khai thanh toan hay
he thong phap ly nao.

Module nay la Python thuan: khong FastAPI, khong Qt, khong mang.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# -----------------------------------------------------------------------------
# Enum
# -----------------------------------------------------------------------------


class PublishState(str, Enum):
    """Da chuan bi cho luong xuat ban, giai doan nay chi dung DRAFT/PUBLISHED."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Tier(str, Enum):
    """Cac goi du kien. CHUA co thanh toan trong giai doan nay."""

    FREE = "free"
    LISTENER_PRO = "listener_pro"
    CREATOR_PRO = "creator_pro"
    ULTRA = "ultra"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED)


# -----------------------------------------------------------------------------
# Ban ghi
# -----------------------------------------------------------------------------


@dataclass
class Profile:
    user_id: str
    email: str
    display_name: str = ""
    tier: Tier = Tier.FREE
    #: Han muc - theo doi san, CHUA tru quota that trong MVP.
    listened_minutes: int = 0
    tts_characters_used: int = 0
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name or self.email.split("@")[0],
            "tier": self.tier.value,
            "listened_minutes": self.listened_minutes,
            "tts_characters_used": self.tts_characters_used,
            "created_at": self.created_at,
        }


@dataclass
class Novel:
    owner_id: str
    title: str
    description: str = ""
    cover_key: Optional[str] = None          # object key trong R2, khong phai binary
    state: PublishState = PublishState.DRAFT
    tags: List[str] = field(default_factory=list)
    novel_id: str = field(default_factory=lambda: new_id("nov"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "description": self.description,
            "cover_key": self.cover_key,
            "state": self.state.value,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Chapter:
    novel_id: str
    owner_id: str
    title: str
    content: str = ""
    order_index: int = 1
    state: PublishState = PublishState.DRAFT
    chapter_id: str = field(default_factory=lambda: new_id("chp"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @property
    def char_count(self) -> int:
        return len(self.content or "")

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        data = {
            "chapter_id": self.chapter_id,
            "novel_id": self.novel_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "order_index": self.order_index,
            "state": self.state.value,
            "char_count": self.char_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_content:
            data["content"] = self.content
        return data


@dataclass
class TtsJob:
    owner_id: str
    chapter_id: str
    voice_id: str
    content_hash: str
    status: JobStatus = JobStatus.PENDING
    output_key: Optional[str] = None         # object key cua audio trong kho
    error_kind: Optional[str] = None
    error_message: str = ""
    total_parts: int = 0
    done_parts: int = 0
    rate: str = "1.0"
    chunk_chars: int = 2000
    job_id: str = field(default_factory=lambda: new_id("job"))
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @property
    def progress_percent(self) -> int:
        if not self.total_parts:
            return 0
        return int(round(100.0 * self.done_parts / self.total_parts))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "owner_id": self.owner_id,
            "chapter_id": self.chapter_id,
            "voice_id": self.voice_id,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "progress": self.progress_percent,
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "output_key": self.output_key,
            "error_kind": self.error_kind,
            "error_message": self.error_message,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class AudioTrack:
    """Audio da hoan tat cua mot chuong."""

    chapter_id: str
    owner_id: str
    voice_id: str
    object_key: str
    content_hash: str
    duration_seconds: float = 0.0
    size_bytes: int = 0
    track_id: str = field(default_factory=lambda: new_id("trk"))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "chapter_id": self.chapter_id,
            "owner_id": self.owner_id,
            "voice_id": self.voice_id,
            "object_key": self.object_key,
            "content_hash": self.content_hash,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
        }


def job_fingerprint(content: str, voice_id: str, rate: str, chunk_chars: int) -> str:
    """
    Dau van tay dung cho IDEMPOTENCY.

    Cung noi dung + cung giong + cung thiet lap => cung mot job, khong tao lai.
    """
    from desktop_app.models import content_hash

    payload = f"{content}\x1f{voice_id}\x1f{rate}\x1f{chunk_chars}"
    return content_hash(payload)

"""
Giao diện và luồng xử lý tạo ảnh bìa tiểu thuyết (Cover Generation Job Interface).

Module này đóng vai trò hợp đồng (contract) và quản lý trạng thái công việc (job bookkeeping)
để sinh ảnh bìa từ siêu dữ liệu tiểu thuyết.

Tuân thủ nguyên tắc không phụ thuộc vào bất kỳ thư viện GPU/AI hoặc thư viện xử lý ảnh (Pillow)
nào ở giai đoạn này (tương tự như DriveArchiveBackend trong storage_backend.py).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Protocol

from server.domain import (
    MediaAsset,
    MediaProcessingState,
    MediaType,
    StorageTier,
    new_id,
    now_iso,
)


@dataclass
class CoverGenerationRequest:
    """
    Yêu cầu sinh ảnh bìa với đầy đủ thông tin ngữ cảnh của tiểu thuyết.
    """

    novel_id: str
    fandom: str
    title: str
    summary: str
    characters: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    mood: str = ""
    visual_style: str = ""


class CoverProvider(Protocol):
    """
    Giao thức chuẩn cho các provider sinh ảnh bìa.
    """

    provider_name: str

    def generate(self, request: CoverGenerationRequest) -> bytes:
        """
        Sinh ảnh thô từ yêu cầu và trả về mảng bytes của ảnh.
        """
        ...


class NotConfiguredCoverProvider:
    """
    Provider mặc định khi chưa tích hợp hoặc cấu hình mô hình sinh ảnh bìa thực tế.
    Giữ đúng hợp đồng interface và từ chối thực thi với thông báo rõ ràng.
    """

    provider_name: str = "not_configured"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        raise NotImplementedError(
            "Cover generation model has not been chosen or deployed yet."
        )


class CoverJobStatus(str, Enum):
    """
    Trạng thái vòng đời của một công việc sinh ảnh bìa.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class CoverJob:
    """
    Bản ghi quản lý vòng đời của một tác vụ sinh ảnh bìa.
    """

    novel_id: str
    request: CoverGenerationRequest
    job_id: str = field(default_factory=lambda: new_id("cvj"))
    status: CoverJobStatus = CoverJobStatus.PENDING
    provider_name: str = ""
    media_asset_id: Optional[str] = None
    error_message: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class CoverPipelineService:
    """
    Dịch vụ điều phối luồng sinh ảnh bìa và lưu trữ kết quả dưới dạng MediaAsset.
    """

    def __init__(self, media_asset_store: Any, provider: CoverProvider):
        self._media_asset_store = media_asset_store
        self._provider = provider

    def render_deterministic_overlay(self, base_image: bytes, title: str) -> bytes:
        """
        Ghi đè tiêu đề một cách tất định lên ảnh bìa gốc.

        Không phụ thuộc vào mô hình AI để render chữ nhằm tránh lỗi chính tả.
        Do chưa tích hợp thư viện xử lý ảnh (ví dụ: Pillow), phương thức này giữ nguyên
        hợp đồng giao diện: trả về ảnh gốc nếu tiêu đề rỗng, hoặc raise NotImplementedError.
        """
        if not title:
            return base_image
        raise NotImplementedError(
            "Text overlay rendering requires an image manipulation library decision (e.g. Pillow) which has not yet been made."
        )

    def run_job(self, job: CoverJob) -> CoverJob:
        """
        Thực thi một tác vụ sinh ảnh bìa:
        1. Gọi provider sinh ảnh.
        2. Áp dụng overlay tiêu đề tất định.
        3. Tạo MediaAsset tương ứng trong kho lưu trữ.
        4. Cập nhật trạng thái DONE hoặc FAILED (kèm thông báo lỗi nếu có).
        """
        job.status = CoverJobStatus.RUNNING
        job.provider_name = (
            getattr(self._provider, "provider_name", "")
            or self._provider.__class__.__name__
        )
        job.updated_at = now_iso()

        try:
            raw_bytes = self._provider.generate(job.request)
            final_bytes = self.render_deterministic_overlay(
                raw_bytes, job.request.title
            )

            content_hash = hashlib.sha256(final_bytes).hexdigest()
            object_key = f"covers/{job.novel_id}/{job.job_id}.png"

            asset = MediaAsset(
                owner_id=job.novel_id,
                media_type=MediaType.IMAGE,
                storage_tier=StorageTier.HOT,
                object_key=object_key,
                content_hash=content_hash,
                source=job.provider_name or "cover_pipeline",
                size_bytes=len(final_bytes),
                processing_state=MediaProcessingState.READY,
            )
            created_asset = self._media_asset_store.create_asset(asset)
            job.media_asset_id = created_asset.asset_id
            job.status = CoverJobStatus.DONE
            job.error_message = ""
        except Exception as exc:
            job.status = CoverJobStatus.FAILED
            job.error_message = str(exc)
        finally:
            job.updated_at = now_iso()

        return job

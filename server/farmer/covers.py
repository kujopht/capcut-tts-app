"""Cong anh bia — KHONG co bia thi KHONG duoc len READY/PUBLISHED.

Day la mot dieu kien CUNG, khong phai mot buoc "nen co". Ly do la san pham:
mot tac pham khong co bia hien ra tren trang nhu mot o trong, va mot trang
day o trong trong nhu mot trang hong — du am thanh ben trong hoan hao.

Nen cong nay duoc viet nhu mot phep KIEM (`assert_publishable`) chu khong
chi mot buoc trong day chuyen. Mot lan sua sau nay lam roi buoc sinh bia se
lam do phep kiem, chu khong lang le xuat ban mot o trong.

Dung lai `CoverPipelineService` da co — khong sinh anh o day, va khong sinh
anh tren may gat: provider la mot dich vu HTTP ben ngoai.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from server.cover_pipeline import (
    CoverGenerationRequest, CoverJob, CoverJobStatus, CoverPipelineService,
)
from server.domain import MediaType


#: Endpoint sinh anh THAT (self-hosted Illustrious/SDXL). Trong = dung nen
#: tat dinh.
ENV_COVER_URL = "FARMER_COVER_ENDPOINT_URL"
ENV_COVER_KEY = "FARMER_COVER_API_KEY"
ENV_COVER_STYLE = "FARMER_COVER_API_STYLE"


def build_cover_provider():
    """Chon provider sinh bia — endpoint that neu duoc cau hinh, khong thi
    nen SVG tat dinh.

    Nen SVG **van la mot anh bia sinh ra**: no tat dinh theo hash cua
    fandom/mood, va `CoverPipelineService` chen tieu de len tren. No khong
    dep bang mot model sinh anh, nhung no thoa dung dieu kien "moi tac pham
    xuat ban phai co bia" — va no khong bao gio hong, khong ton tien, khong
    chay tren may gat.

    Roi ve nen tat dinh la CO CHU DICH chu khong phai giau loi: mot farmer
    dung han vi endpoint sinh anh chet se khong san xuat duoc gi ca, trong
    khi mot bia don gian van dua duoc tac pham len trang.
    """
    import os

    from server.cover_pipeline import HttpImageCoverProvider, PlaceholderCoverProvider

    url = (os.environ.get(ENV_COVER_URL) or "").strip()
    if not url:
        return PlaceholderCoverProvider()
    style = (os.environ.get(ENV_COVER_STYLE) or "simple").strip()
    return HttpImageCoverProvider(
        base_url=url,
        api_key=(os.environ.get(ENV_COVER_KEY) or "").strip(),
        api_style="a1111" if style == "a1111" else "simple",
    )


class CoverRequired(RuntimeError):
    """Chan xuat ban vi thieu bia. KHONG phai loi ky thuat — la cong."""


@dataclass(frozen=True)
class CoverOutcome:
    asset_id: str
    provider: str
    reused: bool

    def as_dict(self) -> dict:
        return {"asset_id": self.asset_id, "provider": self.provider,
                "reused": self.reused}


class CoverGate:
    def __init__(self, pipeline: CoverPipelineService, media_asset_store: Any):
        self._pipeline = pipeline
        self._store = media_asset_store

    def existing_cover_asset_id(self, novel_id: str) -> Optional[str]:
        """Bia da co chua. Tra None khi chua — moi loi khac PHAI noi len:
        doc nham 'khong hoi duoc kho' thanh 'chua co bia' se sinh mot bia thu
        hai moi vong, va tra tien cho no moi lan."""
        for asset in self._store.list_assets(novel_id):
            # `covers/` la tien to ma chinh `CoverPipelineService.run_job` dat
            # ra — kiem ca `media_type` lan tien to khoa de mot tai san anh
            # khac (vd minh hoa trong chuong) khong bi doc nham thanh bia.
            if asset.media_type is not MediaType.IMAGE:
                continue
            if (asset.object_key or "").startswith("covers/"):
                return getattr(asset, "asset_id", "") or None
        return None

    def ensure_cover(self, *, novel_id: str, title: str,
                     description: str = "") -> CoverOutcome:
        """Bao dam co bia. Idempotent: da co thi dung lai, khong sinh moi."""
        san_co = self.existing_cover_asset_id(novel_id)
        if san_co:
            return CoverOutcome(asset_id=san_co, provider="reused", reused=True)

        # `CoverGenerationRequest` doi bon truong bat buoc. Farmer chi biet
        # chac hai trong so do; `fandom` de rong co y — doan bua mot fandom se
        # dieu khien prompt ve anh sai huong, te hon la khong noi gi.
        job = CoverJob(
            novel_id=novel_id,
            request=CoverGenerationRequest(
                novel_id=novel_id, fandom="", title=title,
                summary=description),
        )
        job = self._pipeline.run_job(job)
        if job.status is not CoverJobStatus.DONE or not job.media_asset_id:
            raise CoverRequired(
                f"sinh bia that bai cho {novel_id}: "
                f"{job.error_message or job.status}")
        return CoverOutcome(asset_id=job.media_asset_id,
                            provider=job.provider_name, reused=False)

    def assert_publishable(self, novel_id: str) -> str:
        """Cong CUNG truoc READY/PUBLISHED. Nem `CoverRequired` neu chua co
        bia — ben goi KHONG duoc bat roi di tiep."""
        asset_id = self.existing_cover_asset_id(novel_id)
        if not asset_id:
            raise CoverRequired(
                f"{novel_id} chua co anh bia — khong duoc vao READY/PUBLISHED")
        return asset_id

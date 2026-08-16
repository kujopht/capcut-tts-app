"""
Truu tuong hoa nha cung cap phan tich LUU LUONG TRUY CAP (visits/pageviews/
top paths/quoc gia/thiet bi) — TACH BACH voi "phan tich san pham" (dang ky/
DAU/WAU/MAU/luot doc/luot xem...), noi song truc tiep trong cac collection
Appwrite hien co (xem `admin_overview` o server/main.py).

VI SAO TACH RIENG: hai loai phan tich nay co NGUON SU THAT khac nhau hoan
toan. Luu luong truy cap (ai vao trang, tu dau, bang gi) la thu chi mot proxy
o BIEN (Cloudflare) moi thay duoc dung — backend cua Fanfic khong bao gio
nhan duoc request truoc khi no qua Cloudflare. Ghi MOT document Appwrite cho
MOI luot xem trang an danh (spec A6 CAM RO) se la hang chuc nghin ban ghi
mot ngay chi de dem lai thu Cloudflare da dem san, mien phi, tot hon.

TRANG THAI HIEN TAI (Admin Control Center V2, Phase 2): CHUA co credential
Cloudflare nao duoc cau hinh trong du an nay (xac nhan qua audit Phase 0) —
class duoi day CHI la KHUNG (interface + kiem tra "co cau hinh khong"),
CHUA goi GraphQL Analytics API that. Khi nguoi dung cung cap
CLOUDFLARE_ANALYTICS_ZONE_ID + CLOUDFLARE_ANALYTICS_API_TOKEN that, phan
`_fetch_real` moi duoc hien thuc va KIEM THU that — viet code goi mot API
chua co credential de thu se khong the xac minh dung/sai, chi la doan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TrafficOverview:
    configured: bool
    #: Chi co gia tri khi `configured=True`. Rong = dang cho hien thuc that.
    visits_7d: Optional[int] = None
    pageviews_7d: Optional[int] = None
    visits_30d: Optional[int] = None
    pageviews_30d: Optional[int] = None
    top_paths: Optional[List[Dict[str, Any]]] = None
    #: Thong diep AN TOAN cho giao dien — khong bao gio la mot traceback.
    message: str = ""


class CloudflareTrafficProvider:
    """
    Nha cung cap THAT (Cloudflare Web/Zone Analytics qua GraphQL Analytics
    API) — TUY CHON. Doc hai bien moi truong RIENG cho phan tich luu luong,
    TACH voi `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` da dung cho
    Workers AI (server/translation_providers.py): hai san pham Cloudflare
    khac nhau, hai token voi pham vi khac nhau, tron chung mot bien la mot
    thu doi quyen am tham khi mot ben doi cau hinh.
    """

    ZONE_ID_ENV = "CLOUDFLARE_ANALYTICS_ZONE_ID"
    API_TOKEN_ENV = "CLOUDFLARE_ANALYTICS_API_TOKEN"

    def __init__(self) -> None:
        self._zone_id = os.environ.get(self.ZONE_ID_ENV, "").strip()
        self._api_token = os.environ.get(self.API_TOKEN_ENV, "").strip()

    @property
    def configured(self) -> bool:
        return bool(self._zone_id and self._api_token)

    def overview(self) -> TrafficOverview:
        if not self.configured:
            return TrafficOverview(
                configured=False,
                message="Traffic analytics not configured",
            )
        # CHUA hien thuc: khong co credential that de kiem thu lan goi GraphQL
        # nay, va viet code goi mot API khong the xac minh la doan, khong
        # phai ky thuat. Khi co credential that, thay doan nay bang mot lan
        # goi POST toi https://api.cloudflare.com/client/v4/graphql voi
        # query rumPerformance/httpRequests1dGroups cho `self._zone_id`, va
        # THEM test that xac nhan hinh dang phan hoi.
        return TrafficOverview(
            configured=True,
            message=(
                "Đã cấu hình nhưng chưa triển khai truy vấn GraphQL thật — "
                "cần credential thật để kiểm thử trước khi bật."
            ),
        )


#: Instance dung chung — cung mot kieu voi cac singleton khac trong server/main.py
#: (vd `image_spending_guard`). Doc bien moi truong MOT LAN luc import la du:
#: doi cau hinh quan tri can khoi dong lai tien trinh, cung triet ly voi
#: `FAS_ADMIN_USER_IDS` (xem docs/ADMIN.md).
provider = CloudflareTrafficProvider()


def overview() -> Dict[str, Any]:
    """Ham tien ich cho route quan tri — tra ve dict JSON-hoa duoc thang."""
    o = provider.overview()
    return {
        "configured": o.configured,
        "visits_7d": o.visits_7d,
        "pageviews_7d": o.pageviews_7d,
        "visits_30d": o.visits_30d,
        "pageviews_30d": o.pageviews_30d,
        "top_paths": o.top_paths,
        "message": o.message,
    }

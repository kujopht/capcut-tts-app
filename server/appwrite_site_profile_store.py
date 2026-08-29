"""
Kho `SiteProfile` ben vung tren Appwrite — cung giao dien voi
`MockSiteProfileStore` (`server/scraper/site_profile.py`), cung mau voi
`appwrite_scrape_run_store.py` (doc file do cho ly do cua bon diem: 409
rieng khoi 404/AppwriteUnavailableError, doc truc tiep tu response PATCH
khong GET lai, ...). MOT collection: `site_profiles`, khoa tu nhien la
`domain` (khong dinh danh tach rieng — xem docstring `site_profile.py`).
"""
from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Dict, Optional

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError, raise_for_appwrite_404
from server.config import AppwriteSettings
from server.scraper.site_profile import ProfileStatus, SiteProfile, _now_utc_iso
from server.secret_redaction import thong_diep_loi_an_toan

COL_PROFILES = "site_profiles"

PERSISTED_FIELDS = (
    "domain", "status", "revision", "canonical_pattern", "index_pattern",
    "chapter_pattern", "toc_fingerprint", "content_fingerprint",
    "pagination_strategy", "next_page_pattern", "fetch_tier",
    "rate_limit_seconds", "last_verified_at", "last_success_at",
    "consecutive_failures", "success_count", "created_at", "updated_at",
    "adaptive_fingerprint_json",
)
_DATETIME_FIELDS = ("last_verified_at", "last_success_at")

REQUEST_TIMEOUT = 15.0


class _ConflictError(Exception):
    """Xem `appwrite_scrape_run_store._ConflictError` — cung nguyen tac."""


def _float_or_default(value: Any, mac_dinh: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return mac_dinh


def _int(value: Any, mac_dinh: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return mac_dinh


def _profile_from_doc(doc: Dict[str, Any]) -> SiteProfile:
    mac_dinh = SiteProfile(domain="")
    return SiteProfile(
        domain=str(doc.get("domain") or doc.get("$id") or ""),
        status=ProfileStatus(doc.get("status") or ProfileStatus.LEARNING.value),
        revision=_int(doc.get("revision"), 1),
        canonical_pattern=str(doc.get("canonical_pattern") or ""),
        index_pattern=str(doc.get("index_pattern") or ""),
        chapter_pattern=str(doc.get("chapter_pattern") or ""),
        toc_fingerprint=str(doc.get("toc_fingerprint") or ""),
        content_fingerprint=str(doc.get("content_fingerprint") or ""),
        pagination_strategy=str(doc.get("pagination_strategy") or mac_dinh.pagination_strategy),
        next_page_pattern=str(doc.get("next_page_pattern") or ""),
        fetch_tier=str(doc.get("fetch_tier") or mac_dinh.fetch_tier),
        rate_limit_seconds=_float_or_default(
            doc.get("rate_limit_seconds"), mac_dinh.rate_limit_seconds),
        last_verified_at=str(doc.get("last_verified_at") or ""),
        last_success_at=str(doc.get("last_success_at") or ""),
        consecutive_failures=_int(doc.get("consecutive_failures")),
        success_count=_int(doc.get("success_count")),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
        adaptive_fingerprint_json=str(doc.get("adaptive_fingerprint_json") or ""),
    )


#: Tran cua `adaptive_fingerprint_json` trong `scripts/setup_appwrite.py`.
_TRAN_DAU_VAN_TAY = 2000


def _profile_to_data(profile: SiteProfile) -> Dict[str, Any]:
    data = {f: getattr(profile, f) for f in PERSISTED_FIELDS if f != "status"}
    data["status"] = profile.status.value
    # Dau van tay thich ung la JSON. Qua tran thi BO HAN, khong cat ngan:
    # mot chuoi JSON bi cat la JSON HONG, va nguoi doc no (`scrapling_
    # relocation`) se vap khi phan tich — te hon han so voi khong co dau van
    # tay, truong hop da duoc luong truoc (truong nay von la tuy chon, ""
    # nghia la "chua hoc duoc gi").
    #
    # Khong bo qua im lang: neu de nguyen, Appwrite tra HTTP 400 va lam chet
    # ca luot cap nhat ho so, chu khong chi mat rieng dau van tay.
    dau = data.get("adaptive_fingerprint_json")
    if isinstance(dau, str) and len(dau) > _TRAN_DAU_VAN_TAY:
        data["adaptive_fingerprint_json"] = ""
    return data


class AppwriteSiteProfileStore:
    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None,
                 now_fn=_now_utc_iso):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho SiteProfile. Cần cả bốn "
                "biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, "
                "APPWRITE_API_KEY, APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._now = now_fn
        self._attrs_cache: Optional[set] = None
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    def now(self) -> str:
        return self._now()

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _http(self) -> httpx.Client:
        if self._pool is None:
            self._pool = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._pool

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            response = self._http().request(method, url, json=payload,
                                            params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AppwriteUnavailableError(
                f"Không kết nối được Appwrite: {exc}") from exc
        if response.status_code == 404:
            # Phan biet "thieu collection" voi "thieu ban ghi" — xem
            # `adapters.raise_for_appwrite_404`.
            raise_for_appwrite_404(response, path)
        if response.status_code == 409:
            raise _ConflictError("Đã tồn tại bản ghi này.")
        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            raise AppwriteUnavailableError(
                thong_diep_loi_an_toan(body, status_code=response.status_code))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self) -> str:
        return f"/v1/databases/{self._db}/collections/{COL_PROFILES}/documents"

    def _supported_fields(self) -> Optional[set]:
        with self._lock:
            if self._attrs_cache is not None:
                return self._attrs_cache or None
        try:
            meta = self._call(
                "GET", f"/v1/databases/{self._db}/collections/{COL_PROFILES}")
        except Exception:
            return None
        names = {a.get("key") for a in (meta.get("attributes") or []) if a.get("key")}
        with self._lock:
            self._attrs_cache = names
        return names or None

    def _writable(self, data: Dict[str, Any]) -> Dict[str, Any]:
        fields = {k: v for k, v in data.items() if k in PERSISTED_FIELDS}
        for ten in _DATETIME_FIELDS:
            if fields.get(ten) == "":
                fields[ten] = None
        available = self._supported_fields()
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def get(self, domain: str) -> Optional[SiteProfile]:
        try:
            return _profile_from_doc(self._call("GET", f"{self._docs()}/{domain}"))
        except NotFoundError:
            return None

    def upsert(self, profile: SiteProfile) -> SiteProfile:
        moc = profile.created_at or self._now()
        data = _profile_to_data(replace(
            profile, created_at=moc, updated_at=profile.updated_at or moc))
        try:
            self._call("POST", self._docs(), payload={
                "documentId": profile.domain,
                "data": self._writable(data),
                "permissions": [],
            })
            return _profile_from_doc({**data, "domain": profile.domain})
        except _ConflictError:
            doc = self._call("PATCH", f"{self._docs()}/{profile.domain}",
                             payload={"data": self._writable(data)})
            return _profile_from_doc(doc)

    def save(self, domain: str, **fields: Any) -> SiteProfile:
        if "status" in fields and isinstance(fields["status"], ProfileStatus):
            fields["status"] = fields["status"].value
        fields.setdefault("updated_at", self._now())
        doc = self._call("PATCH", f"{self._docs()}/{domain}",
                         payload={"data": self._writable(fields)})
        return _profile_from_doc(doc)

    def record_success(self, domain: str) -> SiteProfile:
        """GIOI HAN DA BIET, CHUA XU LY (phat hien qua review doc lap,
        Codex): GET-roi-PATCH o day KHONG nguyen tu — hai lan goi
        `record_success`/`record_failure` dong thoi cho CUNG domain co the
        cung doc mot `hien_tai` cu, roi lan PATCH SAU de ghi de mat cap
        nhat cua lan TRUOC (vd mot `record_failure` dong thoi voi thao tac
        DISABLED thu cong cua operator co the "hoi sinh" trang thai da tat
        mot cach am tham). Day la mau HIEN CO trong TOAN BO cac kho Appwrite
        cua du an nay (xem `appwrite_scrape_run_store.py::save_run`/
        `save_item` — cung mau GET/PATCH khong khoa) — KHONG PHAI rieng
        file nay them ra, va sua dung dan (them truong version + PATCH co
        dieu kien) la mot thay doi CO HE THONG tren nhieu kho, ngoai pham
        vi PR nay."""
        hien_tai = self.get(domain)
        if hien_tai is None:
            raise ValueError(f"Chưa có SiteProfile cho domain: {domain}")
        trang_thai_moi = (ProfileStatus.VERIFIED
                          if hien_tai.status == ProfileStatus.LEARNING
                          else hien_tai.status)
        return self.save(
            domain, status=trang_thai_moi, consecutive_failures=0,
            success_count=hien_tai.success_count + 1, last_success_at=self._now())

    def record_failure(self, domain: str) -> SiteProfile:
        hien_tai = self.get(domain)
        if hien_tai is None:
            raise ValueError(f"Chưa có SiteProfile cho domain: {domain}")
        loi_lien_tiep = hien_tai.consecutive_failures + 1
        from server.scraper.site_profile import CONSECUTIVE_FAILURE_THRESHOLD
        if hien_tai.status == ProfileStatus.DISABLED:
            trang_thai_moi = ProfileStatus.DISABLED
        elif loi_lien_tiep >= CONSECUTIVE_FAILURE_THRESHOLD:
            trang_thai_moi = ProfileStatus.DEGRADED
        else:
            trang_thai_moi = hien_tai.status
        return self.save(domain, status=trang_thai_moi, consecutive_failures=loi_lien_tiep)


def build_site_profile_store(settings: Any):
    """Chon kho theo `DATA_BACKEND` — cung mau voi `build_scrape_run_store`.
    KHONG bat `AppwriteConfigError`, cung ly do: `DATA_BACKEND=appwrite`
    thieu bien cau hinh PHAI CHET NGAY, khong am tham lui ve bo nho."""
    from server.scraper.site_profile import MockSiteProfileStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteSiteProfileStore(settings.appwrite)
    return MockSiteProfileStore()

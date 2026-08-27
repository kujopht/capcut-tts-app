"""
Kiem thu `server/appwrite_site_profile_store.py` — KHONG cham Appwrite
that, dung fake client HTTP + kiem hop dong schema. Cung mau voi
`test_appwrite_scrape_run_store.py`.
"""
from __future__ import annotations

import json as _json
import threading
import unittest
from typing import Any, Dict, Optional

from server.adapters import AppwriteUnavailableError, NotFoundError
from server.appwrite_site_profile_store import (
    COL_PROFILES,
    PERSISTED_FIELDS,
    AppwriteSiteProfileStore,
    _ConflictError,
)
from server.scraper.site_profile import ProfileStatus, SiteProfile


class SchemaContractTest(unittest.TestCase):
    def test_khop_schema_setup_appwrite(self) -> None:
        from scripts.setup_appwrite import SCHEMA

        schema_fields = {key for key, *_ in SCHEMA[COL_PROFILES]["attributes"]}
        self.assertEqual(set(PERSISTED_FIELDS), schema_fields,
                         "PERSISTED_FIELDS lệch với scripts/setup_appwrite.py")


class _FakeAppwriteClient:
    def __init__(self, *, force_error_status: Optional[int] = None) -> None:
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._force_error_status = force_error_status

    def request(self, method: str, url: str, *, json: Optional[Dict] = None,
               params: Optional[Dict] = None, headers=None):
        if self._force_error_status == 404:
            raise NotFoundError("giả lập 404")
        if self._force_error_status == 409:
            raise _ConflictError("giả lập 409")
        if self._force_error_status is not None:
            raise AppwriteUnavailableError(f"giả lập {self._force_error_status}")

        with self.lock:
            if method == "GET" and f"/{COL_PROFILES}/documents/" in url:
                doc_id = url.rsplit("/", 1)[-1]
                if doc_id not in self.docs:
                    raise NotFoundError("Không tìm thấy bản ghi.")
                return dict(self.docs[doc_id])
            if method == "GET":
                return {"attributes": []}  # "khong hoi duoc schema" -> gui het
            if method == "POST":
                doc_id = json["documentId"]
                if doc_id in self.docs:
                    raise _ConflictError("already exists")
                doc = dict(json["data"])
                doc["$id"] = doc_id
                self.docs[doc_id] = doc
                return dict(doc)
            if method == "PATCH":
                doc_id = url.rsplit("/", 1)[-1]
                if doc_id not in self.docs:
                    raise NotFoundError("Không tìm thấy bản ghi.")
                self.docs[doc_id].update(json["data"])
                return dict(self.docs[doc_id])
        raise AssertionError(f"unhandled {method} {url}")


def _settings():
    from server.config import AppwriteSettings

    return AppwriteSettings(
        endpoint="https://fake.appwrite.local/v1", project_id="p", api_key="k",
        database_id="db")


class RoundTripTest(unittest.TestCase):
    def _store(self, *, force_error_status: Optional[int] = None) -> AppwriteSiteProfileStore:
        client = _FakeAppwriteClient(force_error_status=force_error_status)
        kho = AppwriteSiteProfileStore(
            _settings(), client=client, now_fn=lambda: "2026-08-27T00:00:00+00:00")
        kho._attrs_cache = set()  # "không hỏi được" -> gửi hết
        return kho

    def test_upsert_lan_dau_tao_moi(self) -> None:
        kho = self._store()
        profile = SiteProfile(domain="vidu.test", chapter_pattern=r"/chuong-\d+")
        saved = kho.upsert(profile)
        self.assertEqual(saved.domain, "vidu.test")
        self.assertEqual(saved.status, ProfileStatus.LEARNING)
        self.assertEqual(kho.get("vidu.test").chapter_pattern, r"/chuong-\d+")

    def test_upsert_lai_PATCH_khong_loi_409(self) -> None:
        kho = self._store()
        profile = SiteProfile(domain="vidu.test", chapter_pattern=r"/chuong-\d+")
        kho.upsert(profile)
        updated = kho.upsert(SiteProfile(domain="vidu.test", chapter_pattern=r"/ch-\d+",
                                         revision=2))
        self.assertEqual(updated.chapter_pattern, r"/ch-\d+")
        self.assertEqual(updated.revision, 2)

    def test_get_domain_khong_ton_tai_tra_None(self) -> None:
        kho = self._store()
        self.assertIsNone(kho.get("khong-ton-tai.test"))

    def test_record_success_dau_tien_chuyen_LEARNING_sang_VERIFIED(self) -> None:
        kho = self._store()
        kho.upsert(SiteProfile(domain="vidu.test"))
        updated = kho.record_success("vidu.test")
        self.assertEqual(updated.status, ProfileStatus.VERIFIED)
        self.assertEqual(updated.success_count, 1)

    def test_record_failure_vuot_nguong_chuyen_DEGRADED(self) -> None:
        kho = self._store()
        kho.upsert(SiteProfile(domain="vidu.test"))
        kho.record_success("vidu.test")
        for _ in range(3):
            updated = kho.record_failure("vidu.test")
        self.assertEqual(updated.status, ProfileStatus.DEGRADED)


class ErrorMappingTest(unittest.TestCase):
    def test_loi_401_khong_bi_nuot_thanh_None(self) -> None:
        client = _FakeAppwriteClient(force_error_status=401)
        kho = AppwriteSiteProfileStore(_settings(), client=client)
        with self.assertRaises(AppwriteUnavailableError):
            kho.get("vidu.test")

    def test_loi_404_that_su_tra_ve_None(self) -> None:
        client = _FakeAppwriteClient(force_error_status=404)
        kho = AppwriteSiteProfileStore(_settings(), client=client)
        self.assertIsNone(kho.get("vidu.test"))

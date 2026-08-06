"""
Giao thuc goi Appwrite - cac loi CHI lo ra khi chay that.

Bon loi duoi day deu do live smoke test tren Appwrite Cloud 1.9.6 phat hien.
Bo test nay bat chung ngay khi chay offline.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from server.appwrite_store import (
    AppwriteMetadataStore,
    q_equal,
    q_limit,
    q_order_asc,
    q_order_desc,
)
from server.config import AppwriteSettings

SETTINGS = AppwriteSettings(
    endpoint="https://sgp.khong-co-that.example/v1",
    project_id="du-an-gia", api_key="khoa-gia", database_id="db-gia",
)


class _Recorder:
    """Client gia lap, ghi lai URL va tham so. Khong cham mang."""

    def __init__(self, documents: Optional[List[Dict[str, Any]]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.documents = documents or []

    def request(self, method, url, json=None, params=None, headers=None):
        self.calls.append({"method": method, "url": url,
                           "params": params, "payload": json})
        return {"total": len(self.documents), "documents": list(self.documents)}


class TestEndpointHasNoDuplicateV1(unittest.TestCase):
    """
    `APPWRITE_ENDPOINT` cua Appwrite luon kem san `/v1`.

    Ghep thang voi cac path (cung bat dau bang `/v1/`) se ra `/v1/v1/...` va
    Appwrite tra ve mot trang 404 HTML - dung loi da gap khi chay that.
    """

    def test_api_base_strips_trailing_v1(self):
        self.assertEqual(
            AppwriteSettings(endpoint="https://a.example/v1").api_base,
            "https://a.example",
        )

    def test_api_base_accepts_endpoint_without_v1(self):
        self.assertEqual(
            AppwriteSettings(endpoint="https://a.example").api_base,
            "https://a.example",
        )

    def test_api_base_tolerates_trailing_slash(self):
        for raw in ("https://a.example/v1/", "https://a.example/", "  https://a.example/v1  "):
            self.assertEqual(AppwriteSettings(endpoint=raw).api_base, "https://a.example")

    def test_store_never_builds_a_double_v1_url(self):
        fake = _Recorder()
        store = AppwriteMetadataStore(SETTINGS, client=fake)
        store.list_novels()
        url = fake.calls[0]["url"]
        self.assertNotIn("/v1/v1/", url)
        self.assertEqual(url.count("/v1/"), 1, url)

    def test_identity_adapter_never_builds_a_double_v1_url(self):
        from server.appwrite_adapter import AppwriteIdentityAdapter

        adapter = AppwriteIdentityAdapter(SETTINGS)
        self.assertEqual(adapter._endpoint, "https://sgp.khong-co-that.example")
        self.assertNotIn("/v1", adapter._endpoint)


class TestQueriesUseJsonFormat(unittest.TestCase):
    """
    Appwrite tu 1.5 CHI nhan query dang JSON qua tham so `queries[]`.

    Cu phap chuoi cu (`equal("owner_id", ["x"])`) tra ve 400 "Invalid query:
    Syntax error" - da kiem chung tren 1.9.6.
    """

    def test_helpers_emit_json_objects(self):
        self.assertEqual(json.loads(q_equal("owner_id", "usr_1")),
                         {"method": "equal", "attribute": "owner_id",
                          "values": ["usr_1"]})
        self.assertEqual(json.loads(q_order_desc("created_at")),
                         {"method": "orderDesc", "attribute": "created_at"})
        self.assertEqual(json.loads(q_order_asc("order_index")),
                         {"method": "orderAsc", "attribute": "order_index"})
        self.assertEqual(json.loads(q_limit(1)),
                         {"method": "limit", "values": [1]})

    def test_queries_are_sent_under_the_bracket_param(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).list_novels(owner_id="usr_1")
        params = fake.calls[0]["params"]
        self.assertIn("queries[]", params)
        self.assertNotIn("queries", params, "tên tham số cũ không còn được chấp nhận")

    def test_no_legacy_string_query_syntax_remains(self):
        fake = _Recorder()
        store = AppwriteMetadataStore(SETTINGS, client=fake)
        store.list_novels(owner_id="usr_1", published_only=True)
        store.list_chapters("nov_1")
        store.list_jobs("usr_1", chapter_id="chp_1")
        store.find_job_by_fingerprint("usr_1", "chp_1", "h")
        store.track_for_chapter("chp_1")

        for call in fake.calls:
            for query in call["params"]["queries[]"]:
                parsed = json.loads(query)          # phai la JSON hop le
                self.assertIn("method", parsed)

    def test_values_are_json_encoded_so_injection_is_impossible(self):
        """Truoc day gia tri duoc noi suy thang vao chuoi query."""
        nasty = 'usr"]) || equal("state", ["published'
        parsed = json.loads(q_equal("owner_id", nasty))
        self.assertEqual(parsed["values"], [nasty])
        self.assertEqual(parsed["attribute"], "owner_id")

    def test_injection_attempt_stays_inside_one_value(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).list_novels(
            owner_id='x"]) || equal("state", ["published'
        )
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        equals = [q for q in queries if q["method"] == "equal"]
        self.assertEqual(len(equals), 1, "chỉ được sinh đúng một điều kiện equal")
        self.assertEqual(equals[0]["attribute"], "owner_id")


class TestSessionAuthentication(unittest.TestCase):
    """
    Session secret KHONG phai JWT.

    Gui session secret qua header `X-Appwrite-JWT` bi Appwrite tu choi:
    "Failed to verify JWT. Invalid token: Incomplete segments".
    """

    def _adapter(self):
        from server.appwrite_adapter import AppwriteIdentityAdapter

        return AppwriteIdentityAdapter(SETTINGS)

    def test_user_requests_use_the_session_header(self):
        headers = self._adapter()._headers(session="bi-mat-phien")
        self.assertEqual(headers["X-Appwrite-Session"], "bi-mat-phien")
        self.assertNotIn("X-Appwrite-JWT", headers)

    def test_user_requests_never_carry_the_api_key(self):
        headers = self._adapter()._headers(session="bi-mat-phien")
        self.assertNotIn("X-Appwrite-Key", headers)
        self.assertNotIn("khoa-gia", str(headers))

    def test_server_requests_carry_the_api_key(self):
        headers = self._adapter()._headers(admin=True)
        self.assertIn("X-Appwrite-Key", headers)
        self.assertNotIn("X-Appwrite-Session", headers)

    def test_login_requires_a_real_secret_and_never_falls_back_to_id(self):
        """
        `$id` la ma dinh danh phien, KHONG phai credential.

        Appwrite chi tra ve `secret` khi request kem API key; khong kem key thi
        `secret` rong va truoc day code lay nham `$id`.
        """
        import inspect

        from server import appwrite_adapter

        source = inspect.getsource(appwrite_adapter.AppwriteIdentityAdapter.login)
        self.assertNotIn('data.get("$id")', source,
                         "không được fallback sang $id")
        self.assertIn('data.get("secret")', source)
        self.assertNotIn("admin=False", source,
                         "login phải gọi kèm API key thì Appwrite mới trả secret")

    def test_profile_lookup_uses_session_not_jwt(self):
        import inspect

        from server import appwrite_adapter

        source = inspect.getsource(
            appwrite_adapter.AppwriteIdentityAdapter.profile_from_token)
        self.assertIn("session=", source)
        self.assertNotIn("jwt=", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

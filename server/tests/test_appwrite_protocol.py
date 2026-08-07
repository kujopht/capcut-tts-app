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


class _PagingRecorder:
    """Client gia lap co lat trang that, de kiem tra vong lap offset."""

    def __init__(self, documents: List[Dict[str, Any]]):
        self.calls: List[Dict[str, Any]] = []
        self.documents = documents

    def request(self, method, url, json=None, params=None, headers=None):
        import json as _json

        self.calls.append({"method": method, "url": url, "params": params})
        limit, offset, wanted = 25, 0, None
        for raw in (params or {}).get("queries[]", []):
            q = _json.loads(raw)
            if q["method"] == "limit":
                limit = q["values"][0]
            elif q["method"] == "offset":
                offset = q["values"][0]
            elif q["method"] == "equal" and q["attribute"] == "chapter_id":
                wanted = set(q["values"])
            elif q["method"] == "select" and not q.get("values"):
                # Appwrite that tu choi truy van select rong
                raise AssertionError("Invalid query: No attributes selected")
        docs = [d for d in self.documents
                if wanted is None or d["chapter_id"] in wanted]
        page = docs[offset:offset + limit]
        return {"total": len(docs), "documents": page}


class TestBatchedAudioLookup(unittest.TestCase):
    """
    `audio_by_chapter` phai hoi theo LO, khong phai moi chuong mot truy van.

    Day la ly do ky thuat cua ca thay doi nay: truoc kia trang chi tiet truyen
    goi `/api/chapters/{id}` cho tung chuong.
    """

    def test_thirty_chapters_cost_one_request(self):
        ids = [f"chp_{i}" for i in range(30)]
        fake = _PagingRecorder([{"chapter_id": i} for i in ids])
        store = AppwriteMetadataStore(SETTINGS, client=fake)

        found = store.audio_by_chapter(ids)

        self.assertEqual(set(found), set(ids))
        self.assertEqual(len(fake.calls), 1, "30 chương chỉ được tốn 1 request")

    def test_request_count_does_not_grow_with_chapter_count(self):
        def calls_for(count: int) -> int:
            ids = [f"chp_{i}" for i in range(count)]
            fake = _PagingRecorder([{"chapter_id": i} for i in ids])
            AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(ids)
            return len(fake.calls)

        self.assertEqual(calls_for(1), 1)
        self.assertEqual(calls_for(25), 1)
        self.assertEqual(calls_for(50), 1)

    def test_it_is_an_in_query_not_one_equal_per_chapter(self):
        ids = ["chp_a", "chp_b", "chp_c"]
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(ids)

        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        equals = [q for q in queries if q["method"] == "equal"]
        self.assertEqual(len(equals), 1)
        self.assertEqual(equals[0]["values"], ids)

    def test_explicit_limit_beats_the_appwrite_default_of_25(self):
        """Khong dat limit thi truyen tren 25 chuong bi cat am tham."""
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(["chp_1"])
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        limits = [q["values"][0] for q in queries if q["method"] == "limit"]
        self.assertEqual(len(limits), 1)
        self.assertGreater(limits[0], 25)

    def test_it_pages_when_one_chapter_has_many_tracks(self):
        """Moi lan tao lai audio la mot ban ghi -> so track > so chuong."""
        from server.appwrite_store import PAGE_SIZE

        ids = ["chp_1", "chp_2"]
        docs = [{"chapter_id": "chp_1"} for _ in range(PAGE_SIZE + 5)]
        docs.append({"chapter_id": "chp_2"})
        fake = _PagingRecorder(docs)

        found = AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(ids)

        self.assertEqual(set(found), {"chp_1", "chp_2"})
        self.assertEqual(len(fake.calls), 2, "phải lật sang trang thứ hai")

    def test_large_novel_is_split_into_batches_not_one_giant_query(self):
        from server.appwrite_store import BATCH_IDS

        ids = [f"chp_{i}" for i in range(BATCH_IDS * 3)]
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(ids)

        self.assertEqual(len(fake.calls), 3)
        for call in fake.calls:
            queries = [json.loads(q) for q in call["params"]["queries[]"]]
            equals = [q for q in queries if q["method"] == "equal"][0]
            self.assertLessEqual(len(equals["values"]), BATCH_IDS)

    def test_empty_input_touches_the_network_not_at_all(self):
        fake = _PagingRecorder([{"chapter_id": "chp_1"}])
        found = AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter([])
        self.assertEqual(found, {})
        self.assertEqual(fake.calls, [])

    def test_it_does_not_select_attributes(self):
        """
        CO Y khong dung `q_select` o day.

        `rate` va `chunk_chars` la thuoc tinh moi. Neu truy van liet ke ten thuoc
        tinh thi no phu thuoc vao viec migration da chay chua, va trien khai code
        truoc migration se lam ca trang truyen do. Lay ca document thi khong co
        rang buoc thu tu do.
        """
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(["chp_1"])
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        selects = [q for q in queries if q["method"] == "select"]
        self.assertEqual(selects, [], "khong duoc rang buoc vao ten thuoc tinh")

    def test_it_returns_the_newest_track_per_chapter(self):
        """Chuong tao lai audio nhieu lan -> phai lay ban MOI NHAT."""
        fake = _PagingRecorder([
            {"chapter_id": "chp_1", "created_at": "2026-08-01T00:00:00+00:00",
             "content_hash": "cu", "voice_id": "v", "rate": "1.0", "chunk_chars": 2000},
            {"chapter_id": "chp_1", "created_at": "2026-08-05T00:00:00+00:00",
             "content_hash": "moi", "voice_id": "v", "rate": "1.0", "chunk_chars": 2000},
            {"chapter_id": "chp_1", "created_at": "2026-08-03T00:00:00+00:00",
             "content_hash": "giua", "voice_id": "v", "rate": "1.0", "chunk_chars": 2000},
        ])
        found = AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(["chp_1"])
        self.assertEqual(found["chp_1"].created_at, "2026-08-05T00:00:00+00:00")
        self.assertEqual(found["chp_1"].content_hash, "moi")

    def test_old_track_without_the_new_fields_stays_unverifiable(self):
        """Track cu -> `can_verify` False, tang tren tu quay ve so moc thoi gian."""
        fake = _PagingRecorder([
            {"chapter_id": "chp_1", "created_at": "2026-08-01T00:00:00+00:00",
             "content_hash": "h", "voice_id": "v"},      # khong co rate/chunk_chars
        ])
        found = AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(["chp_1"])
        self.assertIsNone(found["chp_1"].rate)
        self.assertIsNone(found["chp_1"].chunk_chars)
        self.assertFalse(found["chp_1"].can_verify)

    def test_select_puts_attributes_under_values_not_attributes(self):
        """
        Dat duoi khoa `attributes` thi Appwrite tra ve:
            Invalid query: No attributes selected
        Da gap that tren Appwrite Cloud 1.9.6 — khoa dung la `values`.
        """
        from server.appwrite_store import q_select

        parsed = json.loads(q_select("chapter_id"))
        self.assertEqual(parsed, {"method": "select", "values": ["chapter_id"]})
        self.assertNotIn("attributes", parsed)

    def test_chapters_without_audio_are_simply_absent(self):
        fake = _PagingRecorder([{"chapter_id": "chp_2"}])
        found = AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(
            ["chp_1", "chp_2", "chp_3"])
        self.assertEqual(set(found), {"chp_2"})

    def test_duplicate_ids_do_not_multiply_the_query(self):
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).audio_by_chapter(
            ["chp_1", "chp_1", "chp_1"])
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        equals = [q for q in queries if q["method"] == "equal"][0]
        self.assertEqual(equals["values"], ["chp_1"])

    def test_a_long_novel_does_not_lose_chapters_to_the_default_limit(self):
        """
        Appwrite mac dinh chi tra 25 document. Khong lat trang thi truyen 40
        chuong chi hien 25 — thieu du lieu ma khong co loi nao bao.
        """
        docs = [{"chapter_id": f"chp_{i}", "novel_id": "nov_1", "owner_id": "u",
                 "title": f"C{i}", "content": "", "order_index": i,
                 "state": "draft", "created_at": "", "updated_at": ""}
                for i in range(140)]
        fake = _PagingRecorder(docs)

        chapters = AppwriteMetadataStore(SETTINGS, client=fake).list_chapters("nov_1")

        self.assertEqual(len(chapters), 140, "mất chương vì không lật trang")
        self.assertGreater(len(fake.calls), 1, "phải gọi nhiều trang")

    def test_every_page_asks_for_an_explicit_limit(self):
        fake = _PagingRecorder([])
        AppwriteMetadataStore(SETTINGS, client=fake).list_chapters("nov_1")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        methods = [q["method"] for q in queries]
        self.assertIn("limit", methods)
        self.assertIn("offset", methods)

    def test_both_stores_offer_the_same_method(self):
        """Mock va Appwrite phai cung giao dien — `main.py` khong duoc biet."""
        import inspect

        from server.adapters import MockMetadataStore

        for cls in (MockMetadataStore, AppwriteMetadataStore):
            method = getattr(cls, "audio_by_chapter", None)
            self.assertTrue(callable(method), f"{cls.__name__} thiếu phương thức")
            self.assertEqual(
                list(inspect.signature(method).parameters), ["self", "chapter_ids"])


class TestBrowseQuerySyntax(unittest.TestCase):
    """
    Cu phap truy van cho tim kiem va loc — ba dieu chi lo ra khi chay that,
    da do truc tiep tren Appwrite Cloud 1.9.6.
    """

    def test_tag_filter_uses_contains_not_equal(self):
        """
        `equal` tren thuoc tinh MANG bi tu choi:
            Cannot query equal on attribute "tags" because it is an array
        """
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(tag="one piece")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        tag_queries = [q for q in queries
                       if q.get("attribute") == "tags"]
        self.assertEqual(len(tag_queries), 1)
        self.assertEqual(tag_queries[0]["method"], "contains")
        self.assertNotEqual(tag_queries[0]["method"], "equal")

    def test_search_uses_contains_not_search(self):
        """
        `search` doi index fulltext ma schema khong co:
            Searching by attribute "title" requires a fulltext index
        """
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(query="Luffy")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        methods = [q["method"] for q in queries]
        self.assertNotIn("search", methods)
        self.assertIn("or", methods)

    def test_or_nests_objects_not_json_strings(self):
        """Long dang chuoi JSON thi Appwrite tra 'Server Error'."""
        from server.appwrite_store import q_contains, q_or

        parsed = json.loads(q_or(q_contains("title", "x"),
                                 q_contains("description", "x")))
        self.assertEqual(parsed["method"], "or")
        self.assertEqual(len(parsed["values"]), 2)
        for condition in parsed["values"]:
            self.assertIsInstance(condition, dict,
                                  "dieu kien phai la doi tuong, khong phai chuoi")
            self.assertEqual(condition["method"], "contains")

    def test_search_covers_both_title_and_description(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(query="Luffy")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        or_query = next(q for q in queries if q["method"] == "or")
        attrs = sorted(c["attribute"] for c in or_query["values"])
        self.assertEqual(attrs, ["description", "title"])

    def test_paging_sends_limit_and_offset(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(limit=10, offset=20)
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        limits = [q["values"][0] for q in queries if q["method"] == "limit"]
        offsets = [q["values"][0] for q in queries if q["method"] == "offset"]
        self.assertEqual(limits, [10])
        self.assertEqual(offsets, [20])

    def test_total_comes_from_appwrite_not_from_the_page_length(self):
        """Appwrite tra `total` doc lap voi `limit` — da kiem chung khi chay."""
        class TotalRecorder:
            def request(self, method, url, json=None, params=None, headers=None):
                return {"total": 137, "documents": [{
                    "novel_id": "nov_1", "owner_id": "u", "title": "T",
                    "description": "", "cover_key": None, "state": "published",
                    "tags": [], "created_at": "", "updated_at": "",
                }]}

        items, total = AppwriteMetadataStore(
            SETTINGS, client=TotalRecorder()).find_novels(limit=1)
        self.assertEqual(len(items), 1)
        self.assertEqual(total, 137, "khong duoc lay do dai trang lam tong")

    def test_no_paging_means_fetch_everything_with_pagination(self):
        """`limit=None` phai lat trang, neu khong bi cat o 25 ban ghi."""
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels()
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        methods = [q["method"] for q in queries]
        self.assertIn("limit", methods)
        self.assertIn("offset", methods)

    def test_tag_list_only_asks_for_the_tags_attribute(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).novel_tags()
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        selects = [q for q in queries if q["method"] == "select"]
        self.assertEqual(selects[0]["values"], ["tags"])

    def test_published_filter_survives_search_and_tag(self):
        """Tim kiem khong duoc lam mat dieu kien `state = published`."""
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(
            published_only=True, query="x", tag="y")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        state = [q for q in queries
                 if q["method"] == "equal" and q.get("attribute") == "state"]
        self.assertEqual(len(state), 1)
        self.assertEqual(state[0]["values"], ["published"])

    def test_owner_filter_survives_search(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(
            owner_id="usr_1", query="x")
        queries = [json.loads(q) for q in fake.calls[0]["params"]["queries[]"]]
        owner = [q for q in queries
                 if q["method"] == "equal" and q.get("attribute") == "owner_id"]
        self.assertEqual(owner[0]["values"], ["usr_1"])

    def test_every_query_is_valid_json(self):
        fake = _Recorder()
        AppwriteMetadataStore(SETTINGS, client=fake).find_novels(
            owner_id="usr_1", published_only=True, query="Luffy",
            tag="one piece", limit=10, offset=10)
        for raw in fake.calls[0]["params"]["queries[]"]:
            parsed = json.loads(raw)      # phai la JSON hop le
            self.assertIn("method", parsed)


class TestNoQueryStopsAt25(unittest.TestCase):
    """
    Bien 25 la gioi han MAC DINH CUA APPWRITE, khong phai cua code ta.

    Kiem dieu nay o tang mock la vo nghia: `MockMetadataStore` loc bang Python nen
    khong bao gio cat o 25. `_PagingRecorder` mo phong dung hanh vi that — khong
    co truy van `limit` thi chi tra 25 document.
    """

    def docs(self, count: int, **extra):
        return [{"$id": f"d{i:04d}", **extra} for i in range(count)]

    def job_docs(self, count: int):
        return [{
            "job_id": f"job_{i:04d}", "owner_id": "usr_1", "chapter_id": "chp_1",
            "voice_id": "v", "content_hash": f"h{i:04d}", "status": "completed",
            "rate": "1.0", "chunk_chars": 2000,
            "created_at": f"2026-08-07T00:{i // 60:02d}:{i % 60:02d}+00:00",
        } for i in range(count)]

    def track_docs(self, count: int):
        return [{
            "track_id": f"trk_{i:04d}", "chapter_id": "chp_1", "owner_id": "usr_1",
            "voice_id": "v", "object_key": f"audio/{i}.mp3",
            "content_hash": f"h{i:04d}", "size_bytes": 1,
            "created_at": f"2026-08-07T00:{i // 60:02d}:{i % 60:02d}+00:00",
        } for i in range(count)]

    def test_the_fake_client_really_caps_at_25_without_a_limit(self):
        """Neu cho nay sai thi moi test duoi day dat mot cach vo nghia."""
        fake = _PagingRecorder(self.docs(40))
        data = fake.request("GET", "/x", params={"queries[]": []})
        self.assertEqual(len(data["documents"]), 25)
        self.assertEqual(data["total"], 40)

    def test_list_jobs_returns_every_job_past_25(self):
        for count in (0, 1, 25, 26, 60, 137):
            with self.subTest(count=count):
                fake = _PagingRecorder(self.job_docs(count))
                jobs = AppwriteMetadataStore(SETTINGS, client=fake).list_jobs("usr_1")
                self.assertEqual(len(jobs), count)

    def test_tracks_for_chapter_returns_every_track_past_25(self):
        for count in (0, 1, 25, 26, 60):
            with self.subTest(count=count):
                fake = _PagingRecorder(self.track_docs(count))
                tracks = AppwriteMetadataStore(
                    SETTINGS, client=fake).tracks_for_chapter("chp_1")
                self.assertEqual(len(tracks), count)

    def test_find_job_by_fingerprint_looks_past_25_failed_attempts(self):
        """
        Job `completed` nam sau 25 job `failed` cung dau van tay van phai tim ra.

        Khong thi he thong render lai audio da co — ton tien va thoi gian.
        """
        docs = self.job_docs(26)
        for doc in docs[:25]:
            doc["status"] = "failed"
        for doc in docs:
            doc["content_hash"] = "cung-mot-dau-van-tay"
        docs[25]["status"] = "completed"
        fake = _PagingRecorder(docs)

        found = AppwriteMetadataStore(SETTINGS, client=fake).find_job_by_fingerprint(
            "usr_1", "chp_1", "cung-mot-dau-van-tay")
        self.assertIsNotNone(found, "bo sot job completed nam sau 25 job failed")
        self.assertEqual(found.status.value, "completed")

    def test_list_novels_returns_every_novel_past_25(self):
        novel_docs = [{
            "novel_id": f"nov_{i:04d}", "owner_id": "usr_1", "title": f"T{i}",
            "description": "", "cover_key": None, "state": "published",
            "tags": [], "created_at": "", "updated_at": "",
        } for i in range(26)]
        fake = _PagingRecorder(novel_docs)
        items = AppwriteMetadataStore(SETTINGS, client=fake).list_novels(owner_id="usr_1")
        self.assertEqual(len(items), 26)

    def test_chapters_for_owner_returns_every_chapter_past_25(self):
        chapter_docs = [{
            "chapter_id": f"chp_{i:04d}", "novel_id": "nov_1", "owner_id": "usr_1",
            "title": f"C{i}", "content": "", "order_index": i,
            "state": "draft", "created_at": "", "updated_at": "",
        } for i in range(26)]
        fake = _PagingRecorder(chapter_docs)
        items = AppwriteMetadataStore(
            SETTINGS, client=fake).chapters_for_owner("usr_1")
        self.assertEqual(len(items), 26)

    def test_job_settings_returns_every_match_past_25(self):
        fake = _PagingRecorder(self.job_docs(30))
        found = AppwriteMetadataStore(SETTINGS, client=fake).job_settings(
            "usr_1", [f"h{i:04d}" for i in range(30)])
        self.assertEqual(len(found), 30)

    def test_paging_keeps_the_order_the_query_asked_for(self):
        fake = _PagingRecorder(self.job_docs(30))
        jobs = AppwriteMetadataStore(SETTINGS, client=fake).list_jobs("usr_1")
        ids = [j.job_id for j in jobs]
        self.assertEqual(ids, sorted(ids), "lat trang khong duoc dao lon thu tu")

    def test_paging_never_repeats_a_record(self):
        fake = _PagingRecorder(self.job_docs(137))
        jobs = AppwriteMetadataStore(SETTINGS, client=fake).list_jobs("usr_1")
        self.assertEqual(len(jobs), len(set(j.job_id for j in jobs)))


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

"""
L2 — tim kiem, loc the va phan trang phai do KHO lam, khong phai trinh duyet.

Dieu bo test nay giu chat nhat: khi client xin mot trang, kho KHONG duoc tai het
ban ghi ve roi cat. Co test dem so ban ghi thuc su di qua tang kho.

Va tuong thich nguoc: khong truyen `limit` thi hanh vi y nhu truoc.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import Novel


class CountingStore(MockMetadataStore):
    """Ghi lai moi lan `find_novels` duoc goi va no tra ve bao nhieu ban ghi."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: List[Dict] = []

    def find_novels(self, owner_id=None, published_only=False, query="",
                    tag="", limit=None, offset=0) -> Tuple[List[Novel], int]:
        page, total = super().find_novels(
            owner_id=owner_id, published_only=published_only, query=query,
            tag=tag, limit=limit, offset=offset)
        self.calls.append({
            "limit": limit, "offset": offset, "query": query, "tag": tag,
            "tra_ve": len(page), "tong": total,
        })
        return page, total


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = CountingStore()
        server_main.store = self.store
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    # -- tien ich ------------------------------------------------------------

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def make(self, token: str, title: str, description: str = "",
             tags: Optional[List[str]] = None, publish: bool = True) -> str:
        novel_id = self.client.post(
            "/api/novels",
            json={"title": title, "description": description, "tags": tags or []},
            headers=self.auth(token),
        ).json()["novel"]["novel_id"]
        if publish:
            self.client.post(f"/api/novels/{novel_id}/publish",
                             headers=self.auth(token))
        return novel_id

    def seed(self, token: str, count: int, prefix: str = "Truyện") -> List[str]:
        return [self.make(token, f"{prefix} {i:02d}") for i in range(1, count + 1)]

    def browse(self, **params):
        return self.client.get("/api/novels", params=params)

    def titles(self, body) -> List[str]:
        return [n["title"] for n in body["novels"]]


# ==================================================== phan trang


class TestPaging(Base):
    def test_first_page(self):
        token = self.user()
        self.seed(token, 25)
        body = self.browse(limit=10, offset=0).json()
        self.assertEqual(body["count"], 10)
        self.assertEqual(body["total"], 25)
        self.assertEqual(body["offset"], 0)
        self.assertTrue(body["has_more"])

    def test_last_page_is_partial_and_has_no_more(self):
        token = self.user()
        self.seed(token, 25)
        body = self.browse(limit=10, offset=20).json()
        self.assertEqual(body["count"], 5)
        self.assertEqual(body["total"], 25)
        self.assertFalse(body["has_more"])

    def test_offset_past_the_end_is_empty_not_an_error(self):
        token = self.user()
        self.seed(token, 5)
        r = self.browse(limit=10, offset=100)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["novels"], [])
        self.assertEqual(body["total"], 5)
        self.assertFalse(body["has_more"])

    def test_pages_do_not_overlap_and_cover_everything(self):
        token = self.user()
        self.seed(token, 23)
        seen: List[str] = []
        offset = 0
        while True:
            body = self.browse(limit=10, offset=offset).json()
            seen.extend(n["novel_id"] for n in body["novels"])
            if not body["has_more"]:
                break
            offset += 10
        self.assertEqual(len(seen), 23)
        self.assertEqual(len(set(seen)), 23, "khong duoc lap ban ghi giua cac trang")

    def test_store_only_returns_one_page_not_everything(self):
        """Diem cot yeu cua L2: khong tai het roi cat o tang tren."""
        token = self.user()
        self.seed(token, 40)
        self.store.calls.clear()
        self.browse(limit=10, offset=0)
        self.assertEqual(len(self.store.calls), 1)
        self.assertEqual(self.store.calls[0]["tra_ve"], 10,
                         "kho phai tra ve dung mot trang")
        self.assertEqual(self.store.calls[0]["limit"], 10)

    def test_page_size_is_capped(self):
        token = self.user()
        self.seed(token, 3)
        body = self.browse(limit=100000).json()
        self.assertLessEqual(body["limit"], server_main.MAX_PAGE_SIZE)

    def test_negative_offset_is_treated_as_zero(self):
        token = self.user()
        self.seed(token, 5)
        body = self.browse(limit=2, offset=-10).json()
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["count"], 2)

    def test_zero_limit_does_not_divide_by_zero_or_return_everything(self):
        token = self.user()
        self.seed(token, 5)
        body = self.browse(limit=0).json()
        self.assertGreaterEqual(body["limit"], 1)
        self.assertLessEqual(body["count"], body["limit"])


# ==================================================== tim kiem


class TestSearch(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.make(self.token, "Hải Tặc Mũ Rơm", "Luffy và đồng đội",
                  ["one piece"])
        self.make(self.token, "Ký ức mùa hạ", "Chuyện học đường", ["thanh xuân"])
        self.make(self.token, "Thợ săn bóng đêm", "Luffy không có ở đây", ["hành động"])

    def test_search_matches_the_title(self):
        body = self.browse(q="Hải Tặc", limit=10).json()
        self.assertEqual(self.titles(body), ["Hải Tặc Mũ Rơm"])
        self.assertEqual(body["total"], 1)

    def test_search_matches_the_description_too(self):
        body = self.browse(q="Luffy", limit=10).json()
        self.assertEqual(body["total"], 2, "phai tim ca trong mo ta")

    def test_search_ignores_case(self):
        body = self.browse(q="hải tặc", limit=10).json()
        self.assertEqual(body["total"], 1)

    def test_empty_query_returns_everything(self):
        body = self.browse(q="", limit=10).json()
        self.assertEqual(body["total"], 3)

    def test_whitespace_only_query_returns_everything(self):
        body = self.browse(q="   ", limit=10).json()
        self.assertEqual(body["total"], 3)

    def test_no_result_is_an_empty_page_not_an_error(self):
        r = self.browse(q="khong-co-truyen-nao-nhu-vay", limit=10)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["novels"], [])
        self.assertEqual(body["total"], 0)
        self.assertFalse(body["has_more"])

    def test_search_is_done_by_the_store_not_by_the_route(self):
        self.store.calls.clear()
        self.browse(q="Luffy", limit=10)
        self.assertEqual(self.store.calls[0]["query"], "Luffy")
        self.assertEqual(self.store.calls[0]["tra_ve"], 2,
                         "kho phai tra ve ket qua DA loc")

    def test_search_combines_with_paging(self):
        for i in range(15):
            self.make(self.token, f"Luffy tập {i:02d}")
        body = self.browse(q="Luffy", limit=5, offset=0).json()
        self.assertEqual(body["count"], 5)
        self.assertEqual(body["total"], 17)     # 15 moi + 2 cu
        self.assertTrue(body["has_more"])


# ==================================================== loc the


class TestTagFilter(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.make(self.token, "A", tags=["one piece", "phiêu lưu"])
        self.make(self.token, "B", tags=["one piece"])
        self.make(self.token, "C", tags=["thanh xuân"])

    def test_tag_filters(self):
        body = self.browse(tag="one piece", limit=10).json()
        self.assertEqual(sorted(self.titles(body)), ["A", "B"])
        self.assertEqual(body["total"], 2)

    def test_unknown_tag_gives_an_empty_page(self):
        body = self.browse(tag="khong-co-the-nay", limit=10).json()
        self.assertEqual(body["novels"], [])
        self.assertEqual(body["total"], 0)

    def test_tag_and_search_are_combined(self):
        body = self.browse(tag="one piece", q="A", limit=10).json()
        self.assertEqual(self.titles(body), ["A"])

    def test_tag_filter_is_done_by_the_store(self):
        self.store.calls.clear()
        self.browse(tag="one piece", limit=10)
        self.assertEqual(self.store.calls[0]["tag"], "one piece")
        self.assertEqual(self.store.calls[0]["tra_ve"], 2)

    def test_tag_list_endpoint(self):
        body = self.client.get("/api/novels/tags").json()
        self.assertEqual(body["tags"], ["one piece", "phiêu lưu", "thanh xuân"])
        self.assertEqual(body["count"], 3)

    def test_tag_list_route_is_not_swallowed_by_the_novel_id_route(self):
        """`/api/novels/tags` phai khai bao TRUOC `/api/novels/{novel_id}`."""
        r = self.client.get("/api/novels/tags")
        self.assertEqual(r.status_code, 200)
        self.assertIn("tags", r.json())
        self.assertNotIn("novel", r.json(), "bi route dong an mat")

    def test_tag_list_only_covers_published_novels(self):
        self.make(self.token, "Nháp", tags=["the-bi-mat"], publish=False)
        self.assertNotIn("the-bi-mat", self.client.get("/api/novels/tags").json()["tags"])


# ==================================================== quyen


class TestBrowseAuthorization(Base):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("chu@example.com")
        self.other = self.user("nguoila@example.com")
        self.make(self.owner, "Đã xuất bản", tags=["cong-khai"])
        self.make(self.owner, "Bản nháp", tags=["rieng-tu"], publish=False)

    def test_anonymous_sees_only_published(self):
        body = self.browse(limit=10).json()
        self.assertEqual(self.titles(body), ["Đã xuất bản"])
        self.assertEqual(body["total"], 1)

    def test_another_user_sees_only_published(self):
        body = self.client.get("/api/novels", params={"limit": 10},
                               headers=self.auth(self.other)).json()
        self.assertEqual(self.titles(body), ["Đã xuất bản"])

    def test_search_cannot_reach_a_draft(self):
        """Tim dung ten truyen nhap cung khong duoc ra."""
        body = self.browse(q="Bản nháp", limit=10).json()
        self.assertEqual(body["novels"], [])
        self.assertEqual(body["total"], 0)

    def test_tag_filter_cannot_reach_a_draft(self):
        body = self.browse(tag="rieng-tu", limit=10).json()
        self.assertEqual(body["novels"], [])

    def test_mine_needs_a_token(self):
        r = self.browse(mine="true", limit=10)
        self.assertEqual(r.status_code, 401)

    def test_mine_shows_own_drafts(self):
        body = self.client.get("/api/novels",
                               params={"mine": "true", "limit": 10},
                               headers=self.auth(self.owner)).json()
        self.assertEqual(sorted(self.titles(body)), ["Bản nháp", "Đã xuất bản"])

    def test_mine_never_shows_another_users_novels(self):
        self.make(self.other, "Của người khác")
        body = self.client.get("/api/novels",
                               params={"mine": "true", "limit": 10},
                               headers=self.auth(self.owner)).json()
        self.assertNotIn("Của người khác", self.titles(body))

    def test_search_within_mine_stays_within_mine(self):
        self.make(self.other, "Bản nháp của người khác", publish=False)
        body = self.client.get("/api/novels",
                               params={"mine": "true", "q": "Bản nháp", "limit": 10},
                               headers=self.auth(self.owner)).json()
        self.assertEqual(self.titles(body), ["Bản nháp"])


# ==================================================== tuong thich nguoc


class TestBackwardCompatible(Base):
    def test_no_limit_returns_everything_like_before(self):
        token = self.user()
        self.seed(token, 30)
        body = self.browse().json()
        self.assertEqual(body["count"], 30)
        self.assertEqual(len(body["novels"]), 30)
        self.assertIsNone(body["limit"])
        self.assertFalse(body["has_more"])

    def test_count_still_means_records_in_this_response(self):
        token = self.user()
        self.seed(token, 30)
        self.assertEqual(self.browse().json()["count"], 30)
        self.assertEqual(self.browse(limit=10).json()["count"], 10)

    def test_only_additive_keys_were_added(self):
        token = self.user()
        self.seed(token, 1)
        body = self.browse().json()
        self.assertEqual(set(body) - {"novels", "count"},
                         {"total", "limit", "offset", "has_more"})

    def test_mine_without_limit_is_unchanged(self):
        token = self.user()
        self.seed(token, 30)
        body = self.client.get("/api/novels", params={"mine": "true"},
                               headers=self.auth(token)).json()
        self.assertEqual(body["count"], 30)

    def test_list_novels_helper_still_returns_a_plain_list(self):
        token = self.user()
        self.seed(token, 3)
        items = self.store.list_novels(published_only=True)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)

    def test_both_stores_offer_the_same_new_methods(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        for name in ("find_novels", "novel_tags"):
            for cls in (MockMetadataStore, AppwriteMetadataStore):
                method = getattr(cls, name, None)
                self.assertTrue(callable(method), f"{cls.__name__} thiếu {name}()")
            self.assertEqual(
                list(inspect.signature(getattr(MockMetadataStore, name)).parameters),
                list(inspect.signature(getattr(AppwriteMetadataStore, name)).parameters),
                f"{name}: hai kho phải cùng chữ ký",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

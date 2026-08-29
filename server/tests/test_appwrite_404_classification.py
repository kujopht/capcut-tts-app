"""Phan loai 404 cua Appwrite: thieu COLLECTION vs thieu BAN GHI.

Su co that (2026-08-29, Story Harvester Phase 15 tren san xuat): collection
`scrape_run_items` chua duoc cap phat. Lenh LIET KE tai lieu tra 404, va
`_call` dich thanh `NotFoundError("Khong tim thay ban ghi")`. Thong bao do
NOI DOI — no bao thieu MOT BAN GHI trong khi thieu ca CAI HOP — khong route
nao bat, thanh 500 chung chung, va cuoc dieu tra bat dau tu sai cho.

Bon kich ban bat buoc, dung theo yeu cau van hanh.
"""
from __future__ import annotations

import unittest

from server.adapters import (
    AppwriteSchemaMissingError,
    AppwriteUnavailableError,
    NotFoundError,
    raise_for_appwrite_404,
)

DOCS = "/v1/databases/db/collections/scrape_run_items/documents"
ONE_DOC = DOCS + "/doc_abc"


class _HttpResp:
    """Phan hoi HTTP gia: co `status_code` va `.json()` nhu httpx."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = b"x"

    def json(self):
        return self._body


def _bare_store(store_mod, http_client):
    """Store di qua DUONG HTTP THAT cua `_call`.

    Co y KHONG dung `store._client` (duong tiem cho test): duong do thoat
    ngay truoc khi `_call` doc `status_code`, nen mot bai test dung no khong
    he cham vao logic phan loai 404 ma no tuyen bo dang kiem.
    """
    import types

    store = store_mod.AppwriteScrapeRunStore.__new__(store_mod.AppwriteScrapeRunStore)
    store._client = None
    store._pool = http_client
    store._endpoint = "https://appwrite.test"
    store._settings = types.SimpleNamespace(project_id="proj", api_key="k",
                                            database_id="db")
    return store


class _Resp:
    """Phan hoi gia toi thieu: chi can `.json()`."""

    def __init__(self, body=None, boom=False):
        self._body = body or {}
        self._boom = boom

    def json(self):
        if self._boom:
            raise ValueError("khong phai JSON")
        return self._body


class MissingCollectionTest(unittest.TestCase):
    """Kich ban 2 — collection bat buoc khong ton tai."""

    def test_list_call_404_is_schema_error_not_record_missing(self):
        with self.assertRaises(AppwriteSchemaMissingError):
            raise_for_appwrite_404(_Resp(), DOCS)

    def test_appwrite_type_field_is_honoured(self):
        with self.assertRaises(AppwriteSchemaMissingError):
            raise_for_appwrite_404(_Resp({"type": "collection_not_found"}), ONE_DOC)

    def test_missing_database_is_also_schema_error(self):
        with self.assertRaises(AppwriteSchemaMissingError):
            raise_for_appwrite_404(_Resp({"type": "database_not_found"}), ONE_DOC)

    def test_schema_error_surfaces_as_503_family_not_404(self):
        """Phai la con cua `AppwriteUnavailableError` de luoi an toan chung o
        main.py bien no thanh 503 — loi trien khai, khong phai loi nguoi goi."""
        self.assertTrue(issubclass(AppwriteSchemaMissingError, AppwriteUnavailableError))
        with self.assertRaises(AppwriteUnavailableError):
            raise_for_appwrite_404(_Resp(), DOCS)

    def test_message_never_leaks_the_raw_appwrite_body(self):
        noi_bo = "internal-cluster-host-9f3a.appwrite.local"
        with self.assertRaises(AppwriteSchemaMissingError) as ctx:
            raise_for_appwrite_404(
                _Resp({"type": "collection_not_found", "message": noi_bo}), DOCS)
        self.assertNotIn(noi_bo, str(ctx.exception))


class MissingDocumentTest(unittest.TestCase):
    """Kich ban 1 — collection CO, ban ghi khong co. Van la 404 binh thuong."""

    def test_document_call_404_stays_not_found(self):
        with self.assertRaises(NotFoundError):
            raise_for_appwrite_404(_Resp({"type": "document_not_found"}), ONE_DOC)

    def test_document_404_without_type_field_stays_not_found(self):
        with self.assertRaises(NotFoundError):
            raise_for_appwrite_404(_Resp(), ONE_DOC)

    def test_document_not_found_is_not_a_schema_error(self):
        with self.assertRaises(NotFoundError) as ctx:
            raise_for_appwrite_404(_Resp(), ONE_DOC)
        self.assertNotIsInstance(ctx.exception, AppwriteSchemaMissingError)

    def test_collection_and_document_both_named_awkwardly(self):
        """Ca `{col}` lan `{id}` deu co the la "collections"/"documents".
        Doi chieu theo duoi duong dan se sai o day; doi chieu theo vi tri thi
        khong. Neu ra qua review thuong doc lap."""
        khoai = "/v1/databases/db/collections/collections/documents/documents"
        with self.assertRaises(NotFoundError):
            raise_for_appwrite_404(_Resp(), khoai)
        # ...trong khi lenh liet ke that tren cung collection do van dung.
        with self.assertRaises(AppwriteSchemaMissingError):
            raise_for_appwrite_404(_Resp(), "/v1/databases/db/collections/collections/documents")

    def test_document_whose_id_is_literally_documents(self):
        """Appwrite cho phep ID tuy chon. Mot tai lieu ten "documents" tao ra
        duong `.../documents/documents`, va mot phep `endswith` se hieu nham
        no la lenh liet ke — bien 404 "thieu ban ghi" that thanh 503.
        Neu ra qua review bao mat doc lap."""
        with self.assertRaises(NotFoundError):
            raise_for_appwrite_404(_Resp(), DOCS + "/documents")

    def test_message_does_not_name_the_backend_concept(self):
        """Thong bao khong duoc he lo kho du lieu dang gi."""
        with self.assertRaises(AppwriteSchemaMissingError) as ctx:
            raise_for_appwrite_404(_Resp(), DOCS)
        self.assertNotIn("collection", str(ctx.exception).lower())

    def test_unparseable_body_falls_back_to_path_shape(self):
        with self.assertRaises(NotFoundError):
            raise_for_appwrite_404(_Resp(boom=True), ONE_DOC)
        with self.assertRaises(AppwriteSchemaMissingError):
            raise_for_appwrite_404(_Resp(boom=True), DOCS)


class HealthyCollectionTest(unittest.TestCase):
    """Kich ban 3 va 4 — collection RONG va collection CO du lieu.

    Ca hai deu tra 200, nen `raise_for_appwrite_404` KHONG duoc goi toi. Bai
    nay khoa dung dieu do: mot collection rong KHONG duoc bi hieu thanh
    collection thieu, vi do chinh la nham lan da gay ra su co.
    """

    def test_empty_collection_returns_200_and_is_never_classified(self):
        from server import appwrite_scrape_run_store as store_mod

        called = []

        class FakeClient:
            def request(self, method, url, json=None, params=None, headers=None):
                called.append((method, url))
                return _HttpResp(200, {"documents": [], "total": 0})

        store = _bare_store(store_mod, FakeClient())
        data = store._call("GET", DOCS)
        self.assertEqual(data["documents"], [], "collection rong la 200, khong phai 404")
        self.assertEqual(data["total"], 0)
        self.assertTrue(called)

    def test_collection_with_data_returns_rows(self):
        from server import appwrite_scrape_run_store as store_mod

        class FakeClient:
            def request(self, method, url, json=None, params=None, headers=None):
                return _HttpResp(200, {"documents": [{"$id": "d1"}, {"$id": "d2"}],
                                       "total": 2})

        store = _bare_store(store_mod, FakeClient())
        data = store._call("GET", DOCS)
        self.assertEqual(len(data["documents"]), 2)


class EndToEndThroughCallTest(unittest.TestCase):
    """Noi day toan tuyen: `_call` -> `raise_for_appwrite_404`.

    Cac bai o tren goi thang ham phan loai, nen chung dung ngay ca khi
    `_call` QUEN goi no. Bai nay bat dung truong hop do: chay qua duong
    HTTP that voi ma trang thai 404 that.
    """

    def _store_returning(self, status, body):
        from server import appwrite_scrape_run_store as store_mod

        class FakeClient:
            def request(self, method, url, json=None, params=None, headers=None):
                return _HttpResp(status, body)

        return _bare_store(store_mod, FakeClient())

    def test_list_404_reaches_schema_error_through_call(self):
        store = self._store_returning(404, {})
        with self.assertRaises(AppwriteSchemaMissingError):
            store._call("GET", DOCS)

    def test_document_404_reaches_not_found_through_call(self):
        store = self._store_returning(404, {"type": "document_not_found"})
        with self.assertRaises(NotFoundError) as ctx:
            store._call("GET", ONE_DOC)
        self.assertNotIsInstance(ctx.exception, AppwriteSchemaMissingError)


if __name__ == "__main__":
    unittest.main()

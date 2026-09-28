"""
Lop dich Databases -> TablesDB CHI cho Appwrite staging (`server/appwrite_tablesdb_compat.py`).

Hai dieu quan trong nhat, deu co bai canh:
  * PRODUCTION KHONG BAO GIO cai lop dich (project khac, khong co APPWRITE_ENV=staging), va bat
    lop dich voi project production thi tien trinh CHET luc khoi dong;
  * o tang transport, request KHONG phai cua project staging di NGUYEN VEN (khong doi byte nao).
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

import httpx

from scripts.ops.cutover_target import PROD_APPWRITE_ENDPOINT, PROD_APPWRITE_PROJECT_ID
from server import appwrite_tablesdb_compat as lop
from server.appwrite_tablesdb_compat import STAGING_ENDPOINT, STAGING_PROJECT_ID, LopDichStagingBiTuChoi


def _settings(pid, ep, environment="staging"):
    return SimpleNamespace(appwrite=SimpleNamespace(project_id=pid, endpoint=ep), environment=environment,
                           data_backend="appwrite")


class KichHoatTest(unittest.TestCase):
    def test_production_khong_bao_gio_bat(self):
        self.assertFalse(lop.can_kich_hoat(PROD_APPWRITE_PROJECT_ID, PROD_APPWRITE_ENDPOINT, "production", env={}))
        self.assertFalse(lop.can_kich_hoat("", "", "development", env={}))
        truoc = httpx.HTTPTransport.handle_request
        self.assertFalse(lop.kich_hoat_neu_staging(_settings(PROD_APPWRITE_PROJECT_ID, PROD_APPWRITE_ENDPOINT,
                                                             "production"), env={}))
        self.assertIs(httpx.HTTPTransport.handle_request, truoc)

    def test_bat_voi_sai_dich_thi_chet_luc_khoi_dong(self):
        sai = [
            (PROD_APPWRITE_PROJECT_ID, PROD_APPWRITE_ENDPOINT, "staging", {"APPWRITE_ENV": "staging"}),
            ("project-khac", STAGING_ENDPOINT, "staging", {"APPWRITE_ENV": "staging"}),
            (STAGING_PROJECT_ID, "https://fra.cloud.appwrite.io/v1", "staging", {}),
            (STAGING_PROJECT_ID, PROD_APPWRITE_ENDPOINT, "staging", {}),
            (STAGING_PROJECT_ID, STAGING_ENDPOINT, "production", {}),
            ("", "", "development", {"APPWRITE_ENV": "Staging"}),
        ]
        for pid, ep, moi_truong, env in sai:
            with self.subTest(pid=pid, ep=ep, env=env):
                with self.assertRaises(LopDichStagingBiTuChoi):
                    lop.can_kich_hoat(pid, ep, moi_truong, env=env)

    def test_dung_project_staging_thi_bat(self):
        self.assertTrue(lop.can_kich_hoat(STAGING_PROJECT_ID, STAGING_ENDPOINT + "/", "staging", env={}))
        self.assertTrue(lop.can_kich_hoat(STAGING_PROJECT_ID, STAGING_ENDPOINT, "staging",
                                          env={"APPWRITE_ENV": "staging"}))

    def test_import_backend_mac_dinh_khong_cai_lop_dich(self):
        from server import main  # noqa: F401 — chinh lan import nay goi kich_hoat_neu_staging

        self.assertFalse(getattr(httpx.HTTPTransport.handle_request, "__fanfic_lop_dich_staging__", False))


class AnhXaTest(unittest.TestCase):
    def test_duong(self):
        bang = {
            "/databases": ("/tablesdb", "databases"),
            "/databases/db1": ("/tablesdb/db1", "database"),
            "/databases/db1/collections": ("/tablesdb/db1/tables", "collections"),
            "/databases/db1/collections/posts": ("/tablesdb/db1/tables/posts", "collection"),
            "/databases/db1/collections/posts/attributes/string": ("/tablesdb/db1/tables/posts/columns/string", "attribute"),
            "/databases/db1/collections/posts/attributes/enum/kind": ("/tablesdb/db1/tables/posts/columns/enum/kind", "attribute"),
            "/databases/db1/collections/posts/indexes": ("/tablesdb/db1/tables/posts/indexes", "index"),
            "/databases/db1/collections/posts/documents": ("/tablesdb/db1/tables/posts/rows", "documents"),
            "/databases/db1/collections/posts/documents/p1": ("/tablesdb/db1/tables/posts/rows/p1", "document"),
            "/databases/db1/collections/posts/documents/p1/like_count/increment":
                ("/tablesdb/db1/tables/posts/rows/p1/like_count/increment", "document"),
        }
        for cu, moi in bang.items():
            self.assertEqual(lop.dich_duong(cu), moi, cu)
        self.assertIsNone(lop.dich_duong("/users"))
        self.assertIsNone(lop.dich_duong("/tablesdb/transactions"))
        self.assertIsNone(lop.dich_duong("/databasesx"))

    def test_than_yeu_cau(self):
        self.assertEqual(lop.dich_than_yeu_cau({"collectionId": "p", "name": "P", "documentSecurity": True,
                                                "permissions": []}, "collections"),
                         {"tableId": "p", "name": "P", "rowSecurity": True, "permissions": []})
        self.assertEqual(lop.dich_than_yeu_cau({"documentId": "x", "data": {"a": 1}}, "documents"),
                         {"rowId": "x", "data": {"a": 1}})
        self.assertEqual(lop.dich_than_yeu_cau({"key": "i", "type": "key", "attributes": ["a"], "orders": ["ASC"]},
                                               "index"), {"key": "i", "type": "key", "columns": ["a"], "orders": ["ASC"]})

    def test_phan_hoi(self):
        ds = lop.dich_than_phan_hoi({"total": 1, "rows": [{"$id": "p1", "$tableId": "posts", "text": "x"}]},
                                    "documents", 200)
        self.assertEqual(ds["documents"][0]["$collectionId"], "posts")
        self.assertNotIn("rows", ds)
        # MOT dong vua tao co COT ten `rows` (game_runs: so hang luoi) — khong duoc coi la danh sach.
        dong = lop.dich_than_phan_hoi({"$id": "mr_1", "$tableId": "game_runs", "rows": 3, "cols": 4},
                                      "documents", 201)
        self.assertEqual((dong["rows"], dong["$collectionId"]), (3, "game_runs"))
        t = lop.dich_than_phan_hoi({"$id": "posts", "columns": [{"key": "a", "status": "available"}],
                                    "indexes": [{"key": "i", "columns": ["a"]}], "rowSecurity": True}, "collection", 200)
        self.assertEqual(t["attributes"][0]["key"], "a")
        self.assertEqual(t["indexes"][0]["attributes"], ["a"])
        self.assertTrue(t["documentSecurity"])
        loi = lop.dich_than_phan_hoi({"type": "row_not_found", "message": "Row ..."}, "document", 404)
        self.assertEqual(loi["type"], "document_not_found")
        loi = lop.dich_than_phan_hoi({"type": "index_already_exists",
                                      "message": "There is already an index with the same columns"}, "index", 400)
        self.assertIn("already an index with the same attributes", loi["message"])


class TransportTest(unittest.TestCase):
    """Cai lop dich len mot handler GIA (thay vi mang that) — kiem dung tang httpx that dung."""

    def setUp(self):
        self.goi = []
        self._that = httpx.HTTPTransport.handle_request

        def gia(_self, request):
            self.goi.append((request.method, str(request.url), request.content))
            if "/tablesdb/" in request.url.path and request.url.path.endswith("/rows"):
                body = {"total": 1, "rows": [{"$id": "p1", "$tableId": "posts"}]}
            else:
                body = {"ok": True}
            return httpx.Response(200, json=body)

        httpx.HTTPTransport.handle_request = gia
        lop.cai_dat()

    def tearDown(self):
        lop.go_bo()
        httpx.HTTPTransport.handle_request = self._that

    def test_request_cua_staging_duoc_dich_hai_chieu(self):
        with httpx.Client() as c:
            r = c.post(f"{STAGING_ENDPOINT}/databases/db1/collections/posts/documents",
                       headers={"X-Appwrite-Project": STAGING_PROJECT_ID}, json={"documentId": "p1", "data": {}})
        self.assertEqual(r.json()["documents"][0]["$collectionId"], "posts")
        method, url, content = self.goi[-1]
        self.assertEqual(url, f"{STAGING_ENDPOINT}/tablesdb/db1/tables/posts/rows")
        self.assertEqual(json.loads(content), {"rowId": "p1", "data": {}})

    def test_request_khac_di_nguyen_ven(self):
        with httpx.Client() as c:
            c.post(f"{STAGING_ENDPOINT}/databases/db1/collections/posts/documents",
                   headers={"X-Appwrite-Project": PROD_APPWRITE_PROJECT_ID}, json={"documentId": "p1"})
            c.post(f"{PROD_APPWRITE_ENDPOINT}/databases/db1/collections/posts/documents",
                   headers={"X-Appwrite-Project": STAGING_PROJECT_ID}, json={"documentId": "p1"})
            c.get(f"{STAGING_ENDPOINT}/databases", headers={"X-Appwrite-Project": STAGING_PROJECT_ID})
        urls = [u for _, u, _ in self.goi]
        self.assertEqual(urls, [f"{STAGING_ENDPOINT}/databases/db1/collections/posts/documents",
                                f"{PROD_APPWRITE_ENDPOINT}/databases/db1/collections/posts/documents",
                                f"{STAGING_ENDPOINT}/databases"])
        self.assertEqual([json.loads(b) for _, _, b in self.goi[:2]], [{"documentId": "p1"}] * 2)


if __name__ == "__main__":
    unittest.main()

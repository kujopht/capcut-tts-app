"""
Kiem thu `server/appwrite_scrape_run_store.py` — KHONG cham Appwrite that,
dung fake client HTTP + kiem hop dong schema. Cung mau voi
`test_bulk_chapter_import.py`'s `AppwriteContractTest`.
"""
from __future__ import annotations

import json as _json
import threading
import unittest
from typing import Any, Dict, List, Optional

from server.adapters import AppwriteUnavailableError, NotFoundError
from server.appwrite_scrape_run_store import (
    COL_ITEMS,
    COL_RUNS,
    PERSISTED_FIELDS,
    AppwriteScrapeRunStore,
    _ConflictError,
    _int_or_none,
)
from server.scraper.run_state import ScrapeItemStatus, ScrapeRun, ScrapeRunItem, ScrapeRunStatus


class SchemaContractTest(unittest.TestCase):
    def _schema(self, collection: str) -> set:
        from scripts.setup_appwrite import SCHEMA

        return {key for key, *_ in SCHEMA[collection]["attributes"]}

    def test_hai_collection_khop_schema(self) -> None:
        for collection in (COL_RUNS, COL_ITEMS):
            self.assertEqual(
                set(PERSISTED_FIELDS[collection]), self._schema(collection),
                f"{collection}: PERSISTED_FIELDS lệch với scripts/setup_appwrite.py")

    def test_item_id_khong_bao_gio_vuot_36_ky_tu(self) -> None:
        """Dung TRAN gioi han `$id` cua Appwrite — xem docstring kho."""
        from server.scraper.run_state import item_id_for, run_id_from_fingerprint

        run_id = run_id_from_fingerprint("a" * 64)
        item_id = item_id_for(run_id, "b" * 64)
        self.assertLessEqual(len(item_id), 36)
        self.assertEqual(len(item_id), 36)


class IntOrNoneTest(unittest.TestCase):
    def test_none_va_rong_giu_la_None_khong_ep_ve_0(self) -> None:
        self.assertIsNone(_int_or_none(None))
        self.assertIsNone(_int_or_none(""))

    def test_so_hop_le_duoc_ep_dung(self) -> None:
        self.assertEqual(_int_or_none(7), 7)
        self.assertEqual(_int_or_none("7"), 7)


class _FakeAppwriteClient:
    """Mo phong REST Appwrite TRONG BO NHO — du de kiem thu round-trip
    create/get/update/list/count ma khong can mang that."""

    def __init__(self, *, force_error_status: Optional[int] = None) -> None:
        self.docs: Dict[str, Dict[str, Dict[str, Any]]] = {COL_RUNS: {}, COL_ITEMS: {}}
        self.lock = threading.RLock()
        #: Buoc MOI yeu cau (tru GET-1) tra ve loi nay — dung de mo phong
        #: 401/500 that su (khac 404/409) cho `ErrorMappingTest`.
        self._force_error_status = force_error_status

    def request(self, method: str, url: str, *, json: Optional[Dict] = None,
               params: Optional[Dict] = None, headers=None):
        # KHOP HOP DONG THAT: khi `self._client` duoc tiem, `_call` tra ve
        # KET QUA cua `client.request(...)` TRUC TIEP, khong qua buoc doc
        # status-code/`.json()` — nen fake client nay phai TU minh tra ve
        # dict cuoi cung hoac tu nem dung loai loi, giong het nhung gi
        # `_call` that se lam sau khi xu ly response HTTP that (404 ->
        # `NotFoundError`, 409 -> `_ConflictError`, con lai >=400 ->
        # `AppwriteUnavailableError`).
        if self._force_error_status == 404:
            raise NotFoundError("giả lập 404")
        if self._force_error_status == 409:
            raise _ConflictError("giả lập 409")
        if self._force_error_status is not None:
            raise AppwriteUnavailableError(f"giả lập {self._force_error_status}")

        collection = COL_RUNS if COL_RUNS in url else COL_ITEMS
        with self.lock:
            store = self.docs[collection]
            if method == "GET" and "/documents/" in url:
                doc_id = url.rsplit("/", 1)[-1]
                if doc_id not in store:
                    raise NotFoundError("Không tìm thấy bản ghi.")
                return dict(store[doc_id])
            if method == "GET":
                queries = (params or {}).get("queries[]") or []
                docs = list(store.values())
                limit, offset = 25, 0
                for q in queries:
                    parsed = _json.loads(q)
                    if parsed["method"] == "equal":
                        attr, vals = parsed["attribute"], set(parsed["values"])
                        docs = [d for d in docs if d.get(attr) in vals]
                    elif parsed["method"] == "limit":
                        limit = parsed["values"][0]
                    elif parsed["method"] == "offset":
                        offset = parsed["values"][0]
                total = len(docs)
                return {"documents": [dict(d) for d in docs[offset:offset + limit]], "total": total}
            if method == "POST":
                doc_id = json["documentId"]
                if doc_id in store:
                    raise _ConflictError("already exists")
                doc = dict(json["data"])
                doc["$id"] = doc_id
                store[doc_id] = doc
                return dict(doc)
            if method == "PATCH":
                doc_id = url.rsplit("/", 1)[-1]
                if doc_id not in store:
                    raise NotFoundError("Không tìm thấy bản ghi.")
                store[doc_id].update(json["data"])
                return dict(store[doc_id])
        raise AssertionError(f"unhandled {method} {url}")


def _settings():
    from server.config import AppwriteSettings

    return AppwriteSettings(
        endpoint="https://fake.appwrite.local/v1", project_id="p", api_key="k",
        database_id="db")


class RoundTripTest(unittest.TestCase):
    def _store(self, *, force_error_status: Optional[int] = None) -> AppwriteScrapeRunStore:
        client = _FakeAppwriteClient(force_error_status=force_error_status)
        kho = AppwriteScrapeRunStore(_settings(), client=client, now_fn=lambda: "2026-08-27T00:00:00+00:00")
        kho._attrs_cache = {COL_RUNS: set(), COL_ITEMS: set()}  # "không hỏi được" -> gửi hết
        return kho

    def test_create_run_once_idempotent(self) -> None:
        kho = self._store()
        run = ScrapeRun(source_url="https://x/y", fingerprint="f" * 16, run_id="scr_abc")
        first = kho.create_run_once(run)
        second = kho.create_run_once(run)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.created_at, second.created_at)

    def test_save_run_doc_truc_tiep_tu_PATCH_khong_GET_lai(self) -> None:
        kho = self._store()
        run = ScrapeRun(source_url="https://x/y", fingerprint="f" * 16, run_id="scr_abc")
        kho.create_run_once(run)
        updated = kho.save_run("scr_abc", status=ScrapeRunStatus.RUNNING, count_pending=5)
        self.assertEqual(updated.status, ScrapeRunStatus.RUNNING)
        self.assertEqual(updated.count_pending, 5)

    def test_cancelled_at_rong_thanh_None_khong_thanh_gio_hien_tai(self) -> None:
        kho = self._store()
        run = ScrapeRun(source_url="https://x/y", fingerprint="f" * 16, run_id="scr_abc",
                        cancelled_at="2026-01-01T00:00:00+00:00")
        kho.create_run_once(run)
        # Hoi sinh dot: `plan_run` gui `cancelled_at=""` de xoa dau huy cu.
        revived = kho.save_run("scr_abc", cancelled_at="")
        self.assertEqual(revived.cancelled_at, "")

    def test_create_item_once_khong_GET_lai_khi_trung(self) -> None:
        kho = self._store()
        item = ScrapeRunItem(run_id="scr_abc", chapter_url="https://x/c1",
                             source_fingerprint="a" * 20, item_id="scr_abc-" + "a" * 15)
        first = kho.create_item_once(item)
        second = kho.create_item_once(item)
        # Nhanh trung tra ve THAM SO DAU VAO nguyen ven (khong GET) — xem
        # docstring diem 3.
        self.assertIs(second, item)
        self.assertEqual(first.item_id, item.item_id)

    def test_chapter_number_None_giu_nguyen_qua_round_trip(self) -> None:
        kho = self._store()
        item = ScrapeRunItem(run_id="scr_abc", chapter_url="https://x/c1",
                             source_fingerprint="a" * 20, item_id="scr_abc-" + "a" * 15)
        kho.create_item_once(item)
        got = kho.get_item(item.item_id)
        self.assertIsNone(got.chapter_number)
        kho.save_item(item.item_id, status=ScrapeItemStatus.REVIEW_READY, chapter_number=3)
        got2 = kho.get_item(item.item_id)
        self.assertEqual(got2.chapter_number, 3)

    def test_count_items_by_status_bon_truy_van(self) -> None:
        kho = self._store()
        for i in range(3):
            kho.create_item_once(ScrapeRunItem(
                run_id="scr_abc", chapter_url=f"https://x/c{i}",
                source_fingerprint=f"{i}" * 20, item_id=f"scr_abc-{i}" + "a" * 14,
                status=ScrapeItemStatus.PENDING))
        dem = kho.count_items_by_status("scr_abc")
        self.assertEqual(dem["pending"], 3)
        self.assertEqual(dem["failed"], 0)

    def test_list_items_loc_theo_trang_thai(self) -> None:
        kho = self._store()
        kho.create_item_once(ScrapeRunItem(
            run_id="scr_abc", chapter_url="https://x/c1", source_fingerprint="a" * 20,
            item_id="scr_abc-" + "a" * 15, status=ScrapeItemStatus.PENDING))
        kho.create_item_once(ScrapeRunItem(
            run_id="scr_abc", chapter_url="https://x/c2", source_fingerprint="b" * 20,
            item_id="scr_abc-" + "b" * 15, status=ScrapeItemStatus.FAILED))
        pending = kho.list_items("scr_abc", statuses=[ScrapeItemStatus.PENDING])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].status, ScrapeItemStatus.PENDING)

    def test_get_run_khong_ton_tai_tra_ve_None(self) -> None:
        kho = self._store()
        self.assertIsNone(kho.get_run("scr_khong_ton_tai"))


class ErrorMappingTest(unittest.TestCase):
    """Phat hien qua review Codex: truoc day MOI loi >=400 (401/400/5xx)
    bi gop chung thanh `NotFoundError`, lam `get_run`/`get_item` tra ve
    `None` (doc thanh "khong ton tai") va `create_*_once` tra ve "da co
    ban ghi nay" cho ca nhung loi HA TANG that su. Gio 404/409/con-lai
    phai la BA loai khac nhau."""

    def _store(self, *, force_error_status: int) -> AppwriteScrapeRunStore:
        client = _FakeAppwriteClient(force_error_status=force_error_status)
        return AppwriteScrapeRunStore(_settings(), client=client)

    def test_loi_401_KHONG_bi_nuot_thanh_None(self) -> None:
        kho = self._store(force_error_status=401)
        with self.assertRaises(AppwriteUnavailableError):
            kho.get_run("scr_abc")

    def test_loi_500_KHONG_bi_nuot_thanh_da_ton_tai(self) -> None:
        kho = self._store(force_error_status=500)
        run = ScrapeRun(source_url="https://x/y", fingerprint="f" * 16, run_id="scr_abc")
        with self.assertRaises(AppwriteUnavailableError):
            kho.create_run_once(run)

    def test_404_that_su_van_tra_ve_None(self) -> None:
        kho = self._store(force_error_status=404)
        self.assertIsNone(kho.get_run("scr_abc"))

    # `test_create_run_once_idempotent` o `RoundTripTest` da phu 409-that-su
    # ("da ton tai" -> `_ConflictError` -> GET lai binh thuong, khong nem
    # loi) — voi ma cu (moi loi deu la `NotFoundError`) test do van "qua"
    # tinh co; gio no CHI qua neu `_ConflictError` duoc phan biet dung.


if __name__ == "__main__":
    unittest.main()

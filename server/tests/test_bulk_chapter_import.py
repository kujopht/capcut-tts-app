"""
Nhap chuong HANG LOAT — bo test.

Nam dieu bo test nay giu chat nhat, va tat ca deu la thu se lo ra o quy mo 500
chuong chu khong o quy mo 3:

  1. THU TU la thu tu dau vao, va no khong bi day di khi truyen da co chuong.
  2. GUI LAI CUNG MOT DAU VAO khong tao chuong trung, khong tao audio trung —
     ke ca khi lan truoc bi cat giua chung o dung khoanh khac te nhat (chuong da
     tao xong nhung muc chua kip ghi `chapter_id`).
  3. THU LAI MOT MUC khong chay lai ca lo.
  4. HUY dung xep viec MOI nhung KHONG bo job dang bay.
  5. QUYEN la chu-so-huu-truyen, va nguoi khac khong doc/ghi duoc gi.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.bulk_import_domain import (
    BatchStatus,
    BulkImportFormatError,
    ImportBatch,
    ImportItem,
    ItemStatus,
    ParsedChapter,
    batch_fingerprint,
    batch_id_from_fingerprint,
    chapter_id_for,
    item_id_for,
    parse_input,
    parse_json,
    parse_txt,
    validate_chapters,
)
from server.bulk_import_store import MockBulkImportStore
from server.tests.voice_stub import dung_registry_gia


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xf3d" + b"\x00" * 4093)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id,
            "provider": "mock"}


# =============================================================================
# Doc dau vao
# =============================================================================


class DocVanBanTho(unittest.TestCase):
    def test_tach_theo_dong_tieu_de(self) -> None:
        ds = parse_txt("=== Chương 1 ===\nMột.\n\n=== Chương 2 ===\nHai.\n")
        self.assertEqual([m.title for m in ds], ["Chương 1", "Chương 2"])
        self.assertEqual([m.content for m in ds], ["Một.", "Hai."])

    def test_thu_tu_giu_nguyen_thu_tu_tep(self) -> None:
        tho = "".join(f"=== C{i} ===\nnội dung {i}\n" for i in range(1, 21))
        ds = parse_txt(tho)
        self.assertEqual([m.title for m in ds], [f"C{i}" for i in range(1, 21)])

    def test_dong_gach_ngang_tran_KHONG_phai_ranh_gioi_chuong(self) -> None:
        """
        Mot dong `====` tran la dau ngat canh rat pho bien trong fanfic.

        Coi no la ranh gioi chuong se bam mot chuong thanh hang chuc "chuong"
        rong — day la ly do quy uoc doi dau `=` o CA HAI BEN mot tieu de.
        """
        ds = parse_txt("=== Chương 1 ===\nMở đầu.\n====\nCảnh sau.\n"
                       "======\nCảnh nữa.\n")
        self.assertEqual(len(ds), 1)
        self.assertIn("====", ds[0].content)
        self.assertIn("Cảnh nữa.", ds[0].content)

    def test_van_ban_truoc_tieu_de_dau_tien_bi_tu_choi(self) -> None:
        """Bo qua am tham thi mot tep thieu dong tieu de dau se MAT chuong mot
        ma khong ai thay."""
        with self.assertRaises(BulkImportFormatError) as ctx:
            parse_txt("Lời tựa bị bỏ quên.\n=== Chương 1 ===\nNội dung.")
        self.assertIn("trước tiêu đề", str(ctx.exception))

    def test_dong_trong_truoc_tieu_de_dau_tien_khong_sao(self) -> None:
        ds = parse_txt("\n\n   \n=== Chương 1 ===\nNội dung.")
        self.assertEqual(len(ds), 1)

    def test_khong_co_tieu_de_nao_thi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            parse_txt("Chỉ là văn bản thường, không có tiêu đề.")

    def test_khong_can_khoang_trang_quanh_tieu_de(self) -> None:
        ds = parse_txt("===Chương 1===\nNội dung.")
        self.assertEqual(ds[0].title, "Chương 1")


class DocJson(unittest.TestCase):
    def test_mang_truc_tiep(self) -> None:
        ds = parse_json('[{"title": "A", "content": "a"},'
                        ' {"title": "B", "content": "b"}]')
        self.assertEqual([m.title for m in ds], ["A", "B"])

    def test_doi_tuong_co_khoa_chapters(self) -> None:
        ds = parse_json('{"chapters": [{"title": "A", "content": "a"}]}')
        self.assertEqual(len(ds), 1)

    def test_thieu_khoa_thi_bao_ro_o_phan_tu_nao(self) -> None:
        with self.assertRaises(BulkImportFormatError) as ctx:
            parse_json('[{"title": "A", "content": "a"}, {"title": "B"}]')
        self.assertIn("thứ 2", str(ctx.exception))

    def test_json_hong_bi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            parse_json("{khong phai json}")

    def test_dinh_dang_la_bi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            parse_input("bất kỳ", "yaml")


class KiemHanMuc(unittest.TestCase):
    def _ds(self, n: int, chars: int = 10) -> List[ParsedChapter]:
        return [ParsedChapter(title=f"C{i}", content="x" * chars)
                for i in range(1, n + 1)]

    def test_qua_nhieu_chuong_thi_tu_choi_CA_lo(self) -> None:
        with self.assertRaises(BulkImportFormatError) as ctx:
            validate_chapters(self._ds(6), max_items=5,
                              max_chars_per_item=100, max_total_chars=10_000)
        self.assertIn("tối đa 5", str(ctx.exception))

    def test_chuong_qua_dai_thi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            validate_chapters(self._ds(1, chars=200), max_items=5,
                              max_chars_per_item=100, max_total_chars=10_000)

    def test_tong_qua_lon_thi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            validate_chapters(self._ds(5, chars=100), max_items=5,
                              max_chars_per_item=100, max_total_chars=200)

    def test_chuong_rong_thi_tu_choi(self) -> None:
        with self.assertRaises(BulkImportFormatError):
            validate_chapters([ParsedChapter(title="C", content="   ")],
                              max_items=5, max_chars_per_item=100,
                              max_total_chars=10_000)


class HanMucGiaoDienKhopMayChu(unittest.TestCase):
    """
    `web/src/lib/limits.ts` chep lai han muc de giao dien noi truoc.

    CUNG co che doi soat voi `MAX_CHAPTER_CHARS` (xem
    `server/tests/test_limits.py`): hai con so trong hai ngon ngu se troi khoi
    nhau neu khong ai giu, va hau qua o day khong on ao — giao dien noi "còn
    chỗ", tac gia dan 600 chuong, roi mat ca thao tac vao mot loi 400.
    """

    def _so_o_giao_dien(self, ten: str) -> int:
        import re

        duong = (Path(__file__).resolve().parents[2]
                 / "web" / "src" / "lib" / "limits.ts")
        self.assertTrue(duong.is_file(), "thiếu web/src/lib/limits.ts")
        khop = re.search(rf"{ten}\s*=\s*(\d+)", duong.read_text(encoding="utf-8"))
        self.assertIsNotNone(khop, f"không đọc được {ten} ở giao diện")
        return int(khop.group(1))

    def test_so_chuong_toi_da_moi_lo(self) -> None:
        self.assertEqual(self._so_o_giao_dien("MAX_IMPORT_ITEMS"),
                         server_main.MAX_IMPORT_ITEMS)

    def test_tong_ky_tu_toi_da_moi_lo(self) -> None:
        self.assertEqual(self._so_o_giao_dien("MAX_IMPORT_TOTAL_CHARS"),
                         server_main.MAX_IMPORT_TOTAL_CHARS)

    def test_doi_duoc_bang_bien_moi_truong(self) -> None:
        import inspect

        nguon = inspect.getsource(server_main)
        self.assertIn('os.environ.get("FAS_MAX_IMPORT_ITEMS"', nguon)
        self.assertIn('os.environ.get("FAS_MAX_IMPORT_TOTAL_CHARS"', nguon)


class DauVanTay(unittest.TestCase):
    def test_CRLF_va_LF_cho_CUNG_mot_dau_van_tay(self) -> None:
        """
        Cung mot tep di qua hai he dieu hanh khac nhau phai ra cung mot lo.

        Neu khong, "gui lai cung tep" se tao mot lo MOI va nhan doi 500 chuong —
        dung cai ma tinh idempotent phai chan.
        """
        a = parse_txt("=== C1 ===\r\nMột.\r\n\r\n=== C2 ===\r\nHai.\r\n")
        b = parse_txt("=== C1 ===\nMột.\n\n=== C2 ===\nHai.\n")
        self.assertEqual(batch_fingerprint("u", "n", a),
                         batch_fingerprint("u", "n", b))

    def test_giong_doc_KHONG_nam_trong_dau_van_tay(self) -> None:
        """Gom giong vao dau van tay thi "gui lai cung tep voi giong khac" se
        tao lo moi va nhan doi chuong. Xem `batch_fingerprint`."""
        ds = [ParsedChapter(title="C", content="x")]
        self.assertEqual(batch_fingerprint("u", "n", ds),
                         batch_fingerprint("u", "n", list(ds)))

    def test_doi_chu_hoac_doi_truyen_la_doi_lo(self) -> None:
        ds = [ParsedChapter(title="C", content="x")]
        self.assertNotEqual(batch_fingerprint("u1", "n", ds),
                            batch_fingerprint("u2", "n", ds))
        self.assertNotEqual(batch_fingerprint("u", "n1", ds),
                            batch_fingerprint("u", "n2", ds))

    def test_doi_thu_tu_la_doi_lo(self) -> None:
        a = [ParsedChapter("A", "a"), ParsedChapter("B", "b")]
        b = [ParsedChapter("B", "b"), ParsedChapter("A", "a")]
        self.assertNotEqual(batch_fingerprint("u", "n", a),
                            batch_fingerprint("u", "n", b))

    def test_dinh_danh_vua_tran_36_ky_tu_cua_appwrite(self) -> None:
        """Appwrite gioi han `documentId` o 36 ky tu. Vuot tran la moi lan ghi
        deu 400, va chi lo ra o moi truong that."""
        batch_id = batch_id_from_fingerprint("f" * 64)
        self.assertLessEqual(len(batch_id), 36)
        item_id = item_id_for(batch_id, 9999)
        self.assertLessEqual(len(item_id), 36)
        self.assertLessEqual(len(chapter_id_for(item_id)), 36)

    def test_chapter_id_giong_dinh_dang_chuong_binh_thuong(self) -> None:
        """Chuong nhap hang loat KHONG phai mot loai chuong khac."""
        cid = chapter_id_for(item_id_for("imb_" + "a" * 24, 1))
        self.assertTrue(cid.startswith("chp_"))
        self.assertEqual(len(cid), 20)


# =============================================================================
# Hop dong schema
# =============================================================================


class HopDongSchema(unittest.TestCase):
    """`PERSISTED_FIELDS` phai khop CHINH XAC schema ma script setup tao ra —
    cung mau voi `server/tests/test_appwrite_schema_contract.py`."""

    def _schema(self, collection: str) -> set:
        from scripts.setup_appwrite import SCHEMA

        return {key for key, *_ in SCHEMA[collection]["attributes"]}

    def test_hai_collection_khop_schema(self) -> None:
        from server.appwrite_bulk_import_store import (
            COL_BATCHES, COL_ITEMS, PERSISTED_FIELDS)

        for collection in (COL_BATCHES, COL_ITEMS):
            self.assertEqual(set(PERSISTED_FIELDS[collection]),
                             self._schema(collection),
                             f"{collection}: PERSISTED_FIELDS lệch với "
                             "scripts/setup_appwrite.py")

    def test_domain_sinh_ra_dung_cac_truong_duoc_luu(self) -> None:
        from server.appwrite_bulk_import_store import (
            COL_BATCHES, COL_ITEMS, PERSISTED_FIELDS)

        lo = ImportBatch(owner_id="u", novel_id="n", fingerprint="f" * 64,
                         total_items=1).to_dict()
        self.assertEqual(set(lo), set(PERSISTED_FIELDS[COL_BATCHES]))
        muc = ImportItem(batch_id="imb_" + "a" * 24, owner_id="u", novel_id="n",
                         item_index=1, title="C",
                         content="x").to_dict(include_content=True)
        self.assertEqual(set(muc), set(PERSISTED_FIELDS[COL_ITEMS]))

    def test_hinh_dang_API_cua_muc_KHONG_kem_noi_dung(self) -> None:
        muc = ImportItem(batch_id="imb_" + "a" * 24, owner_id="u", novel_id="n",
                         item_index=1, title="C", content="x" * 50)
        api = muc.to_dict()
        self.assertNotIn("content", api)
        self.assertEqual(api["char_count"], 50)

    def test_moc_thoi_gian_rong_thanh_None_khi_ghi(self) -> None:
        """Appwrite tu dien GIO HIEN TAI khi nhan `""` cho mot datetime khong
        bat buoc — moi lo MOI se trong nhu da huy va da ket thuc."""
        from server.appwrite_bulk_import_store import (
            COL_BATCHES, AppwriteBulkImportStore)

        kho = AppwriteBulkImportStore.__new__(AppwriteBulkImportStore)
        kho._attrs_cache = {COL_BATCHES: set()}   # "khong hoi duoc" -> gui het
        import threading as _t
        kho._lock = _t.RLock()
        ra = AppwriteBulkImportStore._writable(
            kho, COL_BATCHES,
            ImportBatch(owner_id="u", novel_id="n", fingerprint="f",
                        total_items=1).to_dict())
        self.assertIsNone(ra["cancelled_at"])
        self.assertIsNone(ra["finished_at"])


# =============================================================================
# API + bo dieu phoi
# =============================================================================


class Base(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self.bulk = MockBulkImportStore()
        self._bulk_that = server_main.bulk_import_store
        server_main.bulk_import_store = self.bulk
        self._storage_that = server_main.storage
        self.root = Path(tempfile.mkdtemp())
        server_main.storage = LocalStorageAdapter(self.root)
        self._synth_that = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        # Job phai THUC SU chay trong tien trinh test, neu khong bo dieu phoi se
        # ket o `job_queued` vinh vien va khong test duoc gi ve doi soat.
        self._can_run_that = server_main._CAN_RUN_JOBS
        server_main._CAN_RUN_JOBS = True
        # Phanh nghi cua bo dieu phoi la trang thai o CAP MODULE. Mot bai test
        # ket thuc luc rong viec se dat phanh 30 giay va lam bai KE TIEP nhin
        # nhu bo dieu phoi chet — nen phai xoa o day, khong phai o tearDown.
        server_main.reset_import_backoff()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._synth_that
        server_main.storage = self._storage_that
        server_main.bulk_import_store = self._bulk_that
        server_main._CAN_RUN_JOBS = self._can_run_that
        server_main.reset_import_backoff()

    # -- tien ich -------------------------------------------------------------

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def owner_id(self, token: str) -> str:
        return self.client.get(
            "/api/auth/me", headers=self.auth(token)).json()["profile"]["user_id"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post("/api/novels", json={"title": title},
                                headers=self.auth(token)).json()["novel"]["novel_id"]

    def txt(self, n: int, prefix: str = "Chương") -> str:
        return "".join(f"=== {prefix} {i} ===\nNội dung của chương {i}.\n\n"
                       for i in range(1, n + 1))

    def nhap(self, token: str, novel_id: str, *, text: str = "",
             voice_id: str = "mock:v1", **extra) -> Dict[str, Any]:
        r = self.client.post(
            f"/api/novels/{novel_id}/chapter-imports",
            json={"text": text, "format": "txt", "voice_id": voice_id, **extra},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 201, r.text[:400])
        return r.json()

    def cho_ghi_xong(self, batch_id: str, timeout: float = 10.0) -> ImportBatch:
        """Doi thread ghi danh sach muc chuyen lo `preparing` -> `running`."""
        han = time.monotonic() + timeout
        while time.monotonic() < han:
            lo = self.bulk.get_batch(batch_id)
            if lo.status is not BatchStatus.PREPARING:
                return lo
            time.sleep(0.01)
        self.fail("lô không rời khỏi trạng thái `preparing`")

    def mot_chu_ky_worker(self) -> None:
        """
        MOT chu ky quet cua `server/worker.py` — CA HAI viec no lam.

        Phai co `recover_stale_jobs`, khong chi `drive_chapter_imports`: job
        `pending` khong duoc khoi dong ngay (vi du luc tao job tien trinh chua
        duoc phep chay job) chi nhich len nho bo quet do. Bo no ra thi bo test
        mo phong mot worker KHONG ton tai trong thuc te.
        """
        try:
            server_main.recover_stale_jobs(pending_min_age_seconds=0)
        except Exception:
            pass
        server_main.drive_chapter_imports()

    def chay_den_khi_ket(self, batch_id: str,
                         timeout: float = 30.0) -> ImportBatch:
        """Goi bo dieu phoi den khi lo ket. Mo phong vong quet cua worker."""
        self.cho_ghi_xong(batch_id)
        han = time.monotonic() + timeout
        while time.monotonic() < han:
            self.mot_chu_ky_worker()
            lo = self.bulk.get_batch(batch_id)
            if lo.is_terminal:
                return lo
            time.sleep(0.02)
        self.fail(f"lô không kết: {self.bulk.get_batch(batch_id)}")

    def tieu_de_chuong(self, novel_id: str) -> List[str]:
        return [c.title for c in self.store.list_chapters(novel_id)]


class NhapCoBan(Base):
    def test_xem_truoc_khong_ghi_gi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports/preview",
            json={"text": self.txt(3), "format": "txt"},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        d = r.json()
        self.assertEqual(d["count"], 3)
        self.assertEqual([c["title"] for c in d["chapters"]],
                         ["Chương 1", "Chương 2", "Chương 3"])
        self.assertFalse(d["already_imported"])
        # KHONG ghi gi ca — day la diem chinh cua route xem truoc.
        self.assertEqual(self.bulk.batches, {})
        self.assertEqual(self.store.list_chapters(nid), [])

    def test_xem_truoc_bao_lo_da_ton_tai(self) -> None:
        token, = (self.user(),)
        nid = self.novel(token)
        tho = self.txt(2)
        self.nhap(token, nid, text=tho)
        r = self.client.post(f"/api/novels/{nid}/chapter-imports/preview",
                             json={"text": tho, "format": "txt"},
                             headers=self.auth(token))
        self.assertTrue(r.json()["already_imported"])

    def test_nhap_tao_du_chuong_dung_thu_tu(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(6))
        self.assertTrue(d["created"])
        self.assertEqual(d["batch"]["total_items"], 6)
        lo = self.chay_den_khi_ket(d["batch"]["batch_id"])
        self.assertIs(lo.status, BatchStatus.COMPLETED)
        self.assertEqual(self.tieu_de_chuong(nid),
                         [f"Chương {i}" for i in range(1, 7)])
        # Moi chuong co audio thuc su.
        for chuong in self.store.list_chapters(nid):
            self.assertIsNotNone(self.store.track_for_chapter(chuong.chapter_id),
                                 f"{chuong.title} không có audio")

    def test_thu_tu_NOI_TIEP_chuong_da_co(self) -> None:
        """`order_base` phai la `order_index` lon nhat dang co, neu khong lo moi
        se chen len truoc chuong cu."""
        token = self.user()
        nid = self.novel(token)
        self.client.post("/api/chapters",
                         json={"novel_id": nid, "title": "Mở đầu",
                               "content": "x", "order_index": 1},
                         headers=self.auth(token))
        d = self.nhap(token, nid, text=self.txt(3), voice_id="")
        self.chay_den_khi_ket(d["batch"]["batch_id"])
        self.assertEqual(self.tieu_de_chuong(nid),
                         ["Mở đầu", "Chương 1", "Chương 2", "Chương 3"])

    def test_lo_KHONG_giong_chi_tao_chuong(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(3), voice_id="")
        lo = self.chay_den_khi_ket(d["batch"]["batch_id"])
        self.assertIs(lo.status, BatchStatus.COMPLETED)
        self.assertEqual(len(self.store.list_chapters(nid)), 3)
        self.assertEqual(self.store.jobs, {}, "lô không giọng không được tạo job")

    def test_dinh_dang_json_cung_duoc(self) -> None:
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports",
            json={"text": '[{"title": "A", "content": "a"},'
                          ' {"title": "B", "content": "b"}]',
                  "format": "json", "voice_id": ""},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 201, r.text[:300])
        self.chay_den_khi_ket(r.json()["batch"]["batch_id"])
        self.assertEqual(self.tieu_de_chuong(nid), ["A", "B"])

    def test_danh_sach_co_cau_truc_cung_duoc(self) -> None:
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports",
            json={"chapters": [{"title": "A", "content": "a"},
                               {"title": "B", "content": "b"}],
                  "voice_id": ""},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 201, r.text[:300])
        self.chay_den_khi_ket(r.json()["batch"]["batch_id"])
        self.assertEqual(self.tieu_de_chuong(nid), ["A", "B"])

    def test_gui_ca_hai_duong_dau_vao_bi_tu_choi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports",
            json={"text": self.txt(1), "format": "txt",
                  "chapters": [{"title": "A", "content": "a"}]},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 400, r.text[:300])

    def test_giong_sai_bi_tu_choi_TRUOC_khi_ghi_hang_nao(self) -> None:
        """Phat hien giong sai o chuong thu 300 la mot lo nua voi va 300 muc
        `failed` giong nhau."""
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports",
            json={"text": self.txt(3), "format": "txt",
                  "voice_id": "khong:ton-tai"},
            headers=self.auth(token))
        self.assertEqual(r.status_code, 400, r.text[:300])
        self.assertEqual(self.bulk.batches, {})

    def test_van_ban_rong_bi_tu_choi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        r = self.client.post(f"/api/novels/{nid}/chapter-imports",
                             json={"voice_id": ""}, headers=self.auth(token))
        self.assertEqual(r.status_code, 400, r.text[:300])

    def test_tien_do_dem_dung(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(4))
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        r = self.client.get(f"/api/novels/{nid}/chapter-imports/{bid}",
                            headers=self.auth(token))
        tien_do = r.json()["progress"]
        self.assertEqual(tien_do["total"], 4)
        self.assertEqual(tien_do["chapters_created"], 4)
        self.assertEqual(tien_do["jobs_queued"], 4)
        self.assertEqual(tien_do["completed"], 4)
        self.assertEqual(tien_do["failed"], 0)
        self.assertEqual(tien_do["percent"], 100)
        self.assertEqual(r.json()["count"], 4)
        self.assertEqual([m["item_index"] for m in r.json()["items"]],
                         [1, 2, 3, 4])
        self.assertNotIn("content", r.json()["items"][0],
                         "duong doc cua API khong duoc keo noi dung chuong ve")


class TinhIdempotent(Base):
    def test_gui_lai_cung_tep_KHONG_nhan_doi_chuong(self) -> None:
        token = self.user()
        nid = self.novel(token)
        tho = self.txt(5)
        d1 = self.nhap(token, nid, text=tho)
        self.chay_den_khi_ket(d1["batch"]["batch_id"])
        d2 = self.nhap(token, nid, text=tho)
        self.assertFalse(d2["created"])
        self.assertEqual(d1["batch"]["batch_id"], d2["batch"]["batch_id"])
        self.chay_den_khi_ket(d2["batch"]["batch_id"])
        self.assertEqual(len(self.store.list_chapters(nid)), 5)
        self.assertEqual(len(self.bulk.items), 5)
        # Va khong co job/track nao bi tao lai.
        self.assertEqual(len(self.store.tracks), 5)

    def test_gui_lai_giua_luc_dang_chay_khong_tao_lo_thu_hai(self) -> None:
        token = self.user()
        nid = self.novel(token)
        tho = self.txt(8)
        d1 = self.nhap(token, nid, text=tho)
        self.cho_ghi_xong(d1["batch"]["batch_id"])
        server_main.drive_chapter_imports()          # moi tao vai chuong
        d2 = self.nhap(token, nid, text=tho)
        self.assertEqual(d1["batch"]["batch_id"], d2["batch"]["batch_id"])
        self.assertEqual(len(self.bulk.batches), 1)
        self.chay_den_khi_ket(d1["batch"]["batch_id"])
        self.assertEqual(len(self.store.list_chapters(nid)), 8)

    def test_chuong_da_tao_nhung_muc_chua_kip_ghi_id(self) -> None:
        """
        KHOANH KHAC TE NHAT: chuong tao xong, tien trinh chet TRUOC khi kip ghi
        `chapter_id` vao muc.

        Day la ly do `chapter_id` phai TAT DINH. Cach lam "chi tao khi
        chapter_id con rong" khong dong duoc khe ho nay — lan chay sau se tao
        MOT chuong nua voi mot id ngau nhien khac.
        """
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(3), voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        server_main.drive_chapter_imports()
        self.assertEqual(len(self.store.list_chapters(nid)), 3)

        # Quay dong ho: moi muc ve `pending`, xoa `chapter_id` — dung trang thai
        # sau mot lan chet giua chung.
        for muc in list(self.bulk.items.values()):
            self.bulk.save_item(muc.item_id, {"status": ItemStatus.PENDING,
                                              "chapter_id": ""})
        self.bulk.save_batch(bid, {"status": BatchStatus.RUNNING,
                                   "finished_at": "", "count_pending": 3,
                                   "count_chapter_created": 0,
                                   "count_job_queued": 0,
                                   "count_completed": 0, "count_failed": 0})

        self.chay_den_khi_ket(bid)
        self.assertEqual(len(self.store.list_chapters(nid)), 3,
                         "chạy lại đã tạo chương trùng")
        self.assertEqual(self.tieu_de_chuong(nid),
                         ["Chương 1", "Chương 2", "Chương 3"])

    def test_chay_lai_KHONG_ghi_de_noi_dung_tac_gia_da_sua(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(2), voice_id="")
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        chuong = self.store.list_chapters(nid)[0]
        self.store.update_chapter(chuong.chapter_id, self.owner_id(token),
                                  {"content": "Bản tác giả đã sửa tay."})

        for muc in list(self.bulk.items.values()):
            self.bulk.save_item(muc.item_id, {"status": ItemStatus.PENDING})
        self.bulk.save_batch(bid, {"status": BatchStatus.RUNNING,
                                   "finished_at": "", "count_pending": 2,
                                   "count_completed": 0})
        self.chay_den_khi_ket(bid)
        self.assertEqual(self.store.get_chapter(chuong.chapter_id).content,
                         "Bản tác giả đã sửa tay.")

    def test_KHONG_tao_lai_audio_cho_chuong_da_co_ban_hoan_tat(self) -> None:
        """
        Chuong da co audio (giong nao cung vay) KHONG duoc tong hop lai.

        Dau van tay cua `POST /api/jobs` chi bao ve truong hop CUNG giong; mot
        ban audio giong KHAC van se bi ghi de neu bo dieu phoi khong tu chan.
        """
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(2), voice_id="mock:v1")
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        so_track = len(self.store.tracks)
        so_job = len(self.store.jobs)

        # Dua lo ve dau, doi giong sang `mock:v2` — mo phong dung tinh huong
        # "chay lai lo voi giong khac".
        for muc in list(self.bulk.items.values()):
            self.bulk.save_item(muc.item_id,
                                {"status": ItemStatus.CHAPTER_CREATED,
                                 "job_id": ""})
        self.bulk.save_batch(bid, {"status": BatchStatus.RUNNING,
                                   "voice_id": "mock:v2", "finished_at": "",
                                   "count_chapter_created": 2,
                                   "count_completed": 0})
        self.chay_den_khi_ket(bid)
        self.assertEqual(len(self.store.tracks), so_track,
                         "audio đã bị tổng hợp lại")
        self.assertEqual(len(self.store.jobs), so_job,
                         "job mới đã được xếp cho chương đã có audio")


class ThuLaiMotMuc(Base):
    def _lo_co_mot_muc_loi(self, token: str, nid: str):
        d = self.nhap(token, nid, text=self.txt(3), voice_id="")
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        muc = sorted(self.bulk.items.values(), key=lambda m: m.item_index)[1]
        self.bulk.save_item(muc.item_id, {"status": ItemStatus.FAILED,
                                          "error_message": "lỗi giả"})
        self.bulk.save_batch(bid, {"status": BatchStatus.PARTIAL,
                                   "count_completed": 2, "count_failed": 1})
        return bid, muc

    def test_thu_lai_MOT_muc_khong_chay_lai_ca_lo(self) -> None:
        token = self.user()
        nid = self.novel(token)
        bid, muc = self._lo_co_mot_muc_loi(token, nid)
        khac = [m for m in self.bulk.items.values() if m.item_id != muc.item_id]
        moc_cu = {m.item_id: m.updated_at for m in khac}

        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports/{bid}/items/{muc.item_id}/retry",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["retried"], 1)
        self.assertEqual(r.json()["batch"]["status"], "running")
        for item_id, moc in moc_cu.items():
            self.assertEqual(self.bulk.get_item(item_id).updated_at, moc,
                             "thử lại một mục đã ghi lại cả lô")

        lo = self.chay_den_khi_ket(bid)
        self.assertIs(lo.status, BatchStatus.COMPLETED)
        self.assertEqual(len(self.store.list_chapters(nid)), 3)

    def test_thu_lai_muc_khong_loi_bi_tu_choi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        bid, _ = self._lo_co_mot_muc_loi(token, nid)
        xong = [m for m in self.bulk.items.values()
                if m.status is ItemStatus.COMPLETED][0]
        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports/{bid}/items/{xong.item_id}/retry",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 409, r.text[:300])

    def test_thu_lai_TAT_CA_muc_loi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        bid, _ = self._lo_co_mot_muc_loi(token, nid)
        r = self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/retry",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["retried"], 1)

    def test_thu_lai_tang_so_lan_thu(self) -> None:
        token = self.user()
        nid = self.novel(token)
        bid, muc = self._lo_co_mot_muc_loi(token, nid)
        self.client.post(
            f"/api/novels/{nid}/chapter-imports/{bid}/items/{muc.item_id}/retry",
            headers=self.auth(token))
        self.assertEqual(self.bulk.get_item(muc.item_id).attempts,
                         muc.attempts + 1)


class HuyLo(Base):
    def test_huy_dung_xep_viec_MOI(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(10), voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        server_main.drive_chapter_imports()
        da_tao = len(self.store.list_chapters(nid))
        self.assertGreater(da_tao, 0)
        self.assertLess(da_tao, 10)

        r = self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertTrue(r.json()["cancelled"])

        for _ in range(5):
            server_main.drive_chapter_imports()
        self.assertEqual(len(self.store.list_chapters(nid)), da_tao,
                         "sau khi huỷ vẫn còn tạo chương mới")
        self.assertIs(self.bulk.get_batch(bid).status, BatchStatus.CANCELLED)

    def test_huy_KHONG_bo_job_dang_bay(self) -> None:
        """
        Muc `job_queued` van duoc doi soat sau khi huy.

        Bo audio da tong hop xong chi vi chu bam "huy" la nem di dung phan viec
        dat nhat — day la yeu cau tuong minh, khong phai chi tiet cai dat.
        """
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(6), voice_id="mock:v1")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        server_main.drive_chapter_imports()      # tao chuong + xep job

        dang_bay = [m for m in self.bulk.items.values()
                    if m.status is ItemStatus.JOB_QUEUED]
        self.assertTrue(dang_bay, "chưa có job nào bay thì test này vô nghĩa")

        r = self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                             headers=self.auth(token))
        self.assertEqual(r.json()["batch"]["status"], "cancelling")

        han = time.monotonic() + 20
        while time.monotonic() < han:
            server_main.drive_chapter_imports()
            if self.bulk.get_batch(bid).status is BatchStatus.CANCELLED:
                break
            time.sleep(0.02)
        self.assertIs(self.bulk.get_batch(bid).status, BatchStatus.CANCELLED)
        for muc in dang_bay:
            self.assertIs(self.bulk.get_item(muc.item_id).status,
                          ItemStatus.COMPLETED,
                          "audio đã xong nhưng không được ghi nhận")

    def test_gui_lai_cung_tep_HOI_SINH_lo_da_huy(self) -> None:
        token = self.user()
        nid = self.novel(token)
        tho = self.txt(8)
        d = self.nhap(token, nid, text=tho, voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        server_main.drive_chapter_imports()
        self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                         headers=self.auth(token))

        d2 = self.nhap(token, nid, text=tho, voice_id="")
        self.assertTrue(d2["resumed"])
        self.assertEqual(d2["batch"]["batch_id"], bid)
        self.chay_den_khi_ket(bid)
        self.assertEqual(len(self.store.list_chapters(nid)), 8)

    def test_gui_lai_lo_DA_XONG_khong_lam_gi_ca(self) -> None:
        token = self.user()
        nid = self.novel(token)
        tho = self.txt(3)
        d = self.nhap(token, nid, text=tho, voice_id="")
        self.chay_den_khi_ket(d["batch"]["batch_id"])
        d2 = self.nhap(token, nid, text=tho, voice_id="")
        self.assertFalse(d2["created"])
        self.assertFalse(d2["resumed"])
        self.assertEqual(d2["batch"]["status"], "completed")

    def test_huy_lo_da_ket_la_khong_lam_gi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(2), voice_id="")
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        r = self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["cancelled"])
        self.assertTrue(r.json()["already_finished"])

    def test_thu_lai_tren_lo_da_huy_bi_tu_choi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(4), voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                         headers=self.auth(token))
        r = self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/retry",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 409, r.text[:300])


class GioiHanDongThoi(Base):
    def test_khong_vuot_tran_MAX_ACTIVE_JOBS(self) -> None:
        """
        Gioi han dong thoi phai la co che DA CO (`MAX_ACTIVE_JOBS`), khong phai
        mot bo dieu tiet moi. Do bang cach chan `_tao_job_cho_chuong` khong cho
        job chay, roi dem so job dang xep hang.
        """
        token = self.user()
        nid = self.novel(token)
        server_main._CAN_RUN_JOBS = False        # job nam `pending`, khong chay
        d = self.nhap(token, nid, text=self.txt(12), voice_id="mock:v1")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        for _ in range(10):
            server_main.drive_chapter_imports()
        dang_xep = [j for j in self.store.jobs.values()
                    if j.status.value in ("pending", "running")]
        self.assertLessEqual(len(dang_xep), server_main.MAX_ACTIVE_JOBS,
                             "bộ điều phối đã vượt trần job đang xếp hàng")
        # ...nhung CHUONG thi khong bi tran job chan lai: tac gia can van ban
        # hien ra som, audio nho giot ve sau.
        self.assertEqual(len(self.store.list_chapters(nid)), 12)


class PhanhNghiKhiRongViec(Base):
    """
    Bo dieu phoi khong duoc goi Appwrite moi 3 giay khi KHONG co lo nao.

    Han muc doc cua Appwrite da mot lan can kiet tren production (20/08), nen
    mot duong poll moi phai co phanh. Nhung phanh chi duoc dap khi RONG VIEC:
    luc dang co lo chay, nguoi dung dang xem tien do va do tre co y nghia.
    """

    def test_rong_viec_thi_nghi_va_khong_hoi_kho_nua(self) -> None:
        dem = {"n": 0}
        that = self.bulk.list_batches

        def dem_lai(*a, **k):
            dem["n"] += 1
            return that(*a, **k)

        self.bulk.list_batches = dem_lai            # type: ignore[method-assign]
        server_main.drive_chapter_imports()
        self.assertEqual(dem["n"], 1)
        for _ in range(5):
            self.assertEqual(server_main.drive_chapter_imports(), {"nghi": 1})
        self.assertEqual(dem["n"], 1, "vẫn hỏi kho dù đang nghỉ")

    def test_dang_co_lo_thi_KHONG_nghi(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(6), voice_id="")
        self.cho_ghi_xong(d["batch"]["batch_id"])
        for _ in range(3):
            self.assertNotIn("nghi", server_main.drive_chapter_imports())

    def test_mo_lo_moi_bo_phanh_ngay(self) -> None:
        """Chủ vừa bấm nút thì phải thấy chương hiện ra trong một chu kỳ quét,
        không phải sau nửa phút."""
        server_main.drive_chapter_imports()         # rong viec -> dat phanh
        self.assertEqual(server_main.drive_chapter_imports(), {"nghi": 1})
        token = self.user()
        nid = self.novel(token)
        self.nhap(token, nid, text=self.txt(2), voice_id="")
        self.assertNotIn("nghi", server_main.drive_chapter_imports())

    def test_thu_lai_cung_bo_phanh(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(2), voice_id="")
        bid = d["batch"]["batch_id"]
        self.chay_den_khi_ket(bid)
        muc = sorted(self.bulk.items.values(), key=lambda m: m.item_index)[0]
        self.bulk.save_item(muc.item_id, {"status": ItemStatus.FAILED,
                                          "error_message": "lỗi giả"})
        self.bulk.save_batch(bid, {"status": BatchStatus.PARTIAL,
                                   "count_completed": 1, "count_failed": 1})
        server_main.drive_chapter_imports()         # rong viec -> dat phanh
        self.assertEqual(server_main.drive_chapter_imports(), {"nghi": 1})
        self.client.post(f"/api/novels/{nid}/chapter-imports/{bid}/retry",
                         headers=self.auth(token))
        self.assertNotIn("nghi", server_main.drive_chapter_imports())

    def test_dat_0_la_tat_phanh(self) -> None:
        that = server_main.IMPORT_IDLE_BACKOFF_SECONDS
        server_main.IMPORT_IDLE_BACKOFF_SECONDS = 0.0
        try:
            for _ in range(3):
                self.assertNotIn("nghi", server_main.drive_chapter_imports())
        finally:
            server_main.IMPORT_IDLE_BACKOFF_SECONDS = that


class PhanQuyen(Base):
    def _lo_cua_nguoi_khac(self):
        chu = self.user("chu@example.com")
        nid = self.novel(chu)
        d = self.nhap(chu, nid, text=self.txt(2), voice_id="")
        return chu, nid, d["batch"]["batch_id"]

    def test_nguoi_la_khong_tao_duoc_lo(self) -> None:
        _, nid, _ = self._lo_cua_nguoi_khac()
        la = self.user("la@example.com")
        r = self.client.post(f"/api/novels/{nid}/chapter-imports",
                             json={"text": self.txt(1), "format": "txt"},
                             headers=self.auth(la))
        self.assertEqual(r.status_code, 403, r.text[:200])

    def test_nguoi_la_khong_doc_duoc_lo(self) -> None:
        _, nid, bid = self._lo_cua_nguoi_khac()
        la = self.user("la@example.com")
        for duong in (f"/api/novels/{nid}/chapter-imports",
                      f"/api/novels/{nid}/chapter-imports/{bid}"):
            r = self.client.get(duong, headers=self.auth(la))
            self.assertEqual(r.status_code, 403, duong)

    def test_nguoi_la_khong_huy_hay_thu_lai_duoc(self) -> None:
        _, nid, bid = self._lo_cua_nguoi_khac()
        la = self.user("la@example.com")
        for duong in (f"/api/novels/{nid}/chapter-imports/{bid}/cancel",
                      f"/api/novels/{nid}/chapter-imports/{bid}/retry"):
            r = self.client.post(duong, headers=self.auth(la))
            self.assertEqual(r.status_code, 403, duong)

    def test_lo_khong_thuoc_truyen_trong_URL_thi_404(self) -> None:
        """`batch_id` doan duoc (bam tu noi dung), nen mot lo phai tu chung
        minh no thuoc dung truyen — khong dua vao duong URL."""
        chu, nid, bid = self._lo_cua_nguoi_khac()
        nid2 = self.novel(chu, "Truyện khác")
        r = self.client.get(f"/api/novels/{nid2}/chapter-imports/{bid}",
                            headers=self.auth(chu))
        self.assertEqual(r.status_code, 404, r.text[:200])

    def test_khong_dang_nhap_thi_401(self) -> None:
        _, nid, bid = self._lo_cua_nguoi_khac()
        self.assertEqual(
            self.client.get(f"/api/novels/{nid}/chapter-imports").status_code, 401)
        self.assertEqual(
            self.client.post(f"/api/novels/{nid}/chapter-imports",
                             json={"text": "x", "format": "txt"}).status_code, 401)


class LoLoi(Base):
    def test_truyen_bi_xoa_thi_lo_that_bai_co_ly_do(self) -> None:
        """Khong chan o day thi moi muc that bai lien tuc mai mai."""
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(4), voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        self.client.delete(f"/api/novels/{nid}", headers=self.auth(token))
        server_main.drive_chapter_imports()
        lo = self.bulk.get_batch(bid)
        self.assertIs(lo.status, BatchStatus.FAILED)
        self.assertIn("truyện", lo.last_error.lower())

    def test_lo_ket_o_preparing_qua_lau_thi_that_bai_ro_rang(self) -> None:
        token = self.user()
        nid = self.novel(token)
        owner = self.owner_id(token)
        lo = ImportBatch(owner_id=owner, novel_id=nid, fingerprint="f" * 64,
                         total_items=3, created_at="2020-01-01T00:00:00+00:00")
        self.bulk.create_batch_once(lo)
        server_main.drive_chapter_imports()
        sau = self.bulk.get_batch(lo.batch_id)
        self.assertIs(sau.status, BatchStatus.FAILED)
        self.assertIn("gửi lại", sau.last_error.lower())

    def test_muc_loi_lam_lo_thanh_partial_chu_khong_completed(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(3), voice_id="")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        muc = sorted(self.bulk.items.values(), key=lambda m: m.item_index)[0]
        # Chuong nay se khong tao duoc: xoa noi dung de `POST /api/jobs` tu
        # choi... nhung lo nay khong co giong, nen mo phong truc tiep.
        self.bulk.save_item(muc.item_id, {"status": ItemStatus.FAILED,
                                          "error_message": "lỗi giả"})
        self.bulk.save_batch(bid, {"count_pending": 2, "count_failed": 1})
        lo = self.chay_den_khi_ket(bid)
        self.assertIs(lo.status, BatchStatus.PARTIAL)
        self.assertEqual(lo.progress()["failed"], 1)


class KhongTU_PHUC_HOI_NoiDung(Base):
    """
    Bộ điều phối KHÔNG BAO GIỜ tự quyết định phục hồi nội dung.

    `chapter_id` là TẤT ĐỊNH, nên một mục quay về `pending` sẽ làm chương được
    TẠO LẠI. Nếu chủ vừa xoá chương đó thì một vòng quét nền vừa âm thầm hoàn
    tác thao tác xoá của họ — đúng loại lỗi không ai để ý cho tới khi nó xảy ra
    ở quy mô 500 chương. Chỉ `retry` (hành động tường minh) được tạo lại.
    """

    def _lo_dang_bay(self, token: str, nid: str):
        d = self.nhap(token, nid, text=self.txt(4), voice_id="mock:v1")
        bid = d["batch"]["batch_id"]
        self.cho_ghi_xong(bid)
        server_main._CAN_RUN_JOBS = False   # job nằm `pending`, không chạy
        server_main.drive_chapter_imports()
        dang_bay = [m for m in self.bulk.items.values()
                    if m.status is ItemStatus.JOB_QUEUED]
        self.assertTrue(dang_bay, "chưa có mục nào `job_queued`")
        return bid, dang_bay[0]

    def test_chuong_bi_xoa_giua_dot_nhap_KHONG_bi_tao_lai(self) -> None:
        token = self.user()
        nid = self.novel(token)
        bid, muc = self._lo_dang_bay(token, nid)
        con_lai = len(self.store.list_chapters(nid)) - 1

        # Xoá chương -> `_purge_chapter` dọn luôn job của nó.
        r = self.client.delete(f"/api/chapters/{muc.chapter_id}",
                               headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:200])

        for _ in range(3):
            server_main.drive_chapter_imports()
        self.assertEqual(len(self.store.list_chapters(nid)), con_lai,
                         "chương đã xoá bị bộ điều phối tạo lại")
        sau = self.bulk.get_item(muc.item_id)
        self.assertIs(sau.status, ItemStatus.FAILED)
        self.assertIn("không còn tồn tại", sau.error_message)

    def test_job_mat_nhung_chuong_con_thi_xep_lai_job(self) -> None:
        """Mất job mà chương còn là chuyện KHÁC — xếp lại job, không đánh lỗi."""
        token = self.user()
        nid = self.novel(token)
        bid, muc = self._lo_dang_bay(token, nid)
        self.store.delete_job(muc.job_id)           # chỉ job biến mất
        server_main.drive_chapter_imports()
        sau = self.bulk.get_item(muc.item_id)
        self.assertIn(sau.status,
                      (ItemStatus.CHAPTER_CREATED, ItemStatus.JOB_QUEUED))
        self.assertEqual(sau.error_message, "")

    def test_thu_lai_TUONG_MINH_thi_duoc_tao_lai_chuong(self) -> None:
        """Chủ bấm “thử lại” là ý muốn tường minh — lúc đó tạo lại là đúng."""
        token = self.user()
        nid = self.novel(token)
        bid, muc = self._lo_dang_bay(token, nid)
        self.client.delete(f"/api/chapters/{muc.chapter_id}",
                           headers=self.auth(token))
        con_lai = len(self.store.list_chapters(nid))
        server_main.drive_chapter_imports()          # -> mục thành `failed`
        server_main._CAN_RUN_JOBS = True

        r = self.client.post(
            f"/api/novels/{nid}/chapter-imports/{bid}/items/{muc.item_id}/retry",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.chay_den_khi_ket(bid)
        self.assertEqual(len(self.store.list_chapters(nid)), con_lai + 1)


class LocTrangThaiSai(Base):
    def test_trang_thai_la_tra_400_chu_khong_500(self) -> None:
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(2), voice_id="")
        bid = d["batch"]["batch_id"]
        r = self.client.get(
            f"/api/novels/{nid}/chapter-imports/{bid}?status_filter=bay-dat",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 400, r.text[:300])
        self.assertIn("bay-dat", r.json()["detail"])


class XuatBanSauKhiNhap(Base):
    def test_xuat_ban_dung_route_DA_CO(self) -> None:
        """Khong co route "xuat ban hang loat": nhap xong thi goi dung
        `POST /api/novels/{id}/publish` — publish von la cap TRUYEN."""
        token = self.user()
        nid = self.novel(token)
        d = self.nhap(token, nid, text=self.txt(4), voice_id="")
        self.chay_den_khi_ket(d["batch"]["batch_id"])
        r = self.client.post(f"/api/novels/{nid}/publish",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["novel"]["state"], "published")
        cong_khai = self.client.get(f"/api/novels/{nid}").json()
        self.assertEqual([c["title"] for c in cong_khai["chapters"]],
                         [f"Chương {i}" for i in range(1, 5)])


class KhongBanThongBao(Base):
    """
    Nhap 500 chuong vao truyen DA XUAT BAN se ban 500 thong bao cho TUNG nguoi
    theo doi. Do khong phai "dung lai co che da co" ma la lam dung no.

    Do bang cach dem so lan `_bao_chuong_moi` duoc goi, KHONG qua
    `/api/notifications`: `server_main.social` la mot the hien o cap module giu
    tham chieu tra ve kho THAT, nen o bo test no khong doc cung kho voi
    `server_main.store`. Dem tai diem goi la phep do dung cho ca hai duong.
    """

    def setUp(self) -> None:
        super().setUp()
        self.da_bao: List[str] = []
        self._bao_that = server_main._bao_chuong_moi
        server_main._bao_chuong_moi = lambda chapter: self.da_bao.append(
            chapter.chapter_id)

    def tearDown(self) -> None:
        server_main._bao_chuong_moi = self._bao_that
        super().tearDown()

    def test_nhap_hang_loat_KHONG_ban_thong_bao_tung_chuong(self) -> None:
        chu = self.user("chu@example.com")
        nid = self.novel(chu)
        self.client.post(f"/api/novels/{nid}/publish", headers=self.auth(chu))

        d = self.nhap(chu, nid, text=self.txt(4), voice_id="")
        self.chay_den_khi_ket(d["batch"]["batch_id"])
        self.assertEqual(self.da_bao, [],
                         "nhập hàng loạt đã bắn thông báo từng chương")

    def test_duong_DON_CHUONG_van_bao_binh_thuong(self) -> None:
        """Khong duoc lam yeu duong cu de duong moi gon hon."""
        chu = self.user("chu@example.com")
        nid = self.novel(chu)
        self.client.post(f"/api/novels/{nid}/publish", headers=self.auth(chu))
        r = self.client.post("/api/chapters",
                             json={"novel_id": nid, "title": "Chương tay",
                                   "content": "x"}, headers=self.auth(chu))
        self.assertEqual(self.da_bao, [r.json()["chapter"]["chapter_id"]])

    def test_chay_lai_KHONG_bao_lan_thu_hai(self) -> None:
        """`vua_tao=False` phai chan MOI tac dung phu chi duoc chay mot lan."""
        chu = self.user("chu@example.com")
        nid = self.novel(chu)
        r = self.client.post("/api/chapters",
                             json={"novel_id": nid, "title": "C", "content": "x"},
                             headers=self.auth(chu))
        cid = r.json()["chapter"]["chapter_id"]
        self.da_bao.clear()
        novel = self.store.get_novel(nid)
        chuong, vua_tao = server_main._tao_chuong_cho_truyen(
            novel=novel, owner_id=self.owner_id(chu), title="C",
            content="x", order_index=1, chapter_id=cid)
        self.assertFalse(vua_tao)
        self.assertEqual(chuong.chapter_id, cid)
        self.assertEqual(self.da_bao, [])


class DungLaiDuongDaCo(unittest.TestCase):
    """
    Rang buoc KIEN TRUC: bo dieu phoi khong duoc co ban sao thu hai cua logic
    tao chuong / tao job.

    Doc thang tu nguon. Mot bai test hanh vi khong bat duoc viec ai do sao chep
    logic — no chi bat duoc luc hai ban sao da lech nhau.
    """

    def test_service_khong_tu_goi_store_tao_chuong_hay_job(self) -> None:
        import inspect

        from server import bulk_import_service

        nguon = inspect.getsource(bulk_import_service)
        for cam in ("create_chapter", "create_job", "synthesize_chapter",
                    "job_fingerprint"):
            self.assertNotIn(f"_store.{cam}", nguon,
                             f"bộ điều phối tự gọi `{cam}` thay vì dùng lại "
                             "đường đã có")

    def test_route_tao_chuong_uy_quyen_cho_chinh_than(self) -> None:
        import inspect

        self.assertIn("_tao_chuong_cho_truyen",
                      inspect.getsource(server_main.create_chapter))
        self.assertIn("_tao_chuong_cho_truyen",
                      inspect.getsource(server_main._bulk_tao_chuong))

    def test_duong_hang_loat_dung_dung_ham_tao_job_cua_route(self) -> None:
        import inspect

        self.assertIn("_tao_job_cho_chuong",
                      inspect.getsource(server_main._bulk_tao_job))
        # ...va phan biet 429 (tran dong thoi, thu lai) voi tu choi vinh vien.
        nguon = inspect.getsource(server_main._bulk_tao_job)
        self.assertIn("HTTP_429_TOO_MANY_REQUESTS", nguon)
        self.assertIn("JobQueueFull", nguon)
        self.assertIn("ChapterJobRejected", nguon)

    def test_worker_goi_bo_dieu_phoi_trong_vong_quet(self) -> None:
        import inspect

        from server import worker

        nguon = inspect.getsource(worker.chay)
        self.assertIn("drive_chapter_imports", nguon)
        # Khoi try RIENG: mot lo nhap loi khong duoc lam mat recovery job TTS.
        self.assertNotIn("recover_stale_jobs()\n            nhap", nguon)


if __name__ == "__main__":
    unittest.main(verbosity=2)

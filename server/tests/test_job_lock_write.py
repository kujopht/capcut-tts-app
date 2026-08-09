"""
Giao dich tao khoa job phai GUI DUNG THU Appwrite nhan duoc.

BA LOI DUOI DAY DA LOT QUA CI VA LEN PRODUCTION. Bo test cu chi kiem HANH VI
qua kho gia (`MockMetadataStore`), noi moi payload deu hop le vi khong co
schema nao ca — nen khong bai nao nhin vao thu THAT SU duoc gui di.

  1. Payload hang job gui `to_dict()` THO, kem `progress` — mot thuoc tinh dan
     xuat khong co cot. Appwrite tu choi ca giao dich, loi bi nuot o `except`,
     va he thong lang le lui ve duong cu. Bang chung tren production: 44 job,
     0 hang `job_locks`.
  2. Op tao hang thieu `permissions`, trong khi moi duong ghi khac deu gan
     quyen chu so huu. Voi rowSecurity bat, chinh chu so huu doc khong ra.
  3. `_job_lock_ready` khoi tao `True` mot cach lac quan, nen `/api/health`
     bao "san sang" ngay sau deploy trong khi duong khoa chua he duoc thu.

Cach kiem o day khac han: dung mot client gia GHI LAI payload, roi soi chinh
cai payload do.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

from server.appwrite_store import (
    COL_JOBS,
    COL_JOB_LOCKS,
    PERSISTED_FIELDS,
    AppwriteMetadataStore,
    _job_lock_id,
)
from server.config import AppwriteSettings
from server.domain import JobStatus, TtsJob

SETTINGS = AppwriteSettings(
    endpoint="https://sgp.khong-co-that.example/v1",
    project_id="du-an-gia", api_key="khoa-gia", database_id="db-gia",
)


class ClientGia:
    """
    Ghi lai moi lot goi. `commit` tra ve ket qua do bai test quyet dinh.

    KHONG kiem tra schema — viec cua bo test la soi payload, khong phai gia lap
    Appwrite. Nhung phai gia lap DUNG hinh dang phan hoi cua transaction, neu
    khong thi ma nguon se di nham nhanh.
    """

    def __init__(self, commit_status: str = "committed",
                 rows: Optional[Dict[str, Dict[str, Any]]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.commit_status = commit_status
        self.rows = rows or {}

    def request(self, method, url, json=None, params=None, headers=None):
        self.calls.append({"method": method, "url": url, "payload": json})
        if "/transactions" in url and method == "POST" and "operations" not in url:
            return {"$id": "tx-gia"}
        if "/transactions" in url and method == "PATCH":
            if self.commit_status == "no":
                raise RuntimeError("Unknown attribute: progress")
            return {"status": self.commit_status}
        # GET mot hang cu the
        for rid, row in self.rows.items():
            if url.endswith(f"/{rid}"):
                return row
        if method == "GET":
            raise RuntimeError("404")
        return {}

    # -- tien ich cho bai test ------------------------------------------------

    def cac_op(self) -> List[Dict[str, Any]]:
        for c in self.calls:
            if "operations" in c["url"]:
                return c["payload"]["operations"]
        return []

    def op_cua(self, table: str) -> Optional[Dict[str, Any]]:
        for op in self.cac_op():
            if op.get("tableId") == table:
                return op
        return None


def mot_job() -> TtsJob:
    return TtsJob(owner_id="usr_1", chapter_id="chp_1", voice_id="mock:v1",
                  content_hash="fp-1")


class PayloadHangJob(unittest.TestCase):

    def setUp(self) -> None:
        self.client = ClientGia()
        self.store = AppwriteMetadataStore(SETTINGS, client=self.client)
        self.job = mot_job()
        self.store.create_job_once(self.job, "fp-1")

    def test_KHONG_gui_truong_ngoai_schema(self) -> None:
        """
        `progress` la thuoc tinh DAN XUAT. Gui no len la ca giao dich hong.
        """
        op = self.client.op_cua(COL_JOBS)
        self.assertIsNotNone(op, "không có op tạo hàng job")
        self.assertNotIn("progress", op["data"])

    def test_moi_truong_gui_di_deu_co_cot_tuong_ung(self) -> None:
        """Kiem CA BO, khong chi rieng `progress` — de lan sau them truong tinh
        toan nao nua thi bai nay do ngay."""
        op = self.client.op_cua(COL_JOBS)
        thua = set(op["data"]) - set(PERSISTED_FIELDS[COL_JOBS])
        self.assertEqual(thua, set(), f"gửi trường không có cột: {sorted(thua)}")

    def test_van_gui_du_cac_truong_can_thiet(self) -> None:
        """Loc khong duoc loc nham: job phai co du thong tin de worker nhan."""
        data = self.client.op_cua(COL_JOBS)["data"]
        for k in ("job_id", "owner_id", "chapter_id", "voice_id",
                  "content_hash", "status"):
            self.assertIn(k, data)
        self.assertEqual(data["status"], JobStatus.PENDING.value)

    def test_hang_job_co_quyen_chu_so_huu(self) -> None:
        op = self.client.op_cua(COL_JOBS)
        self.assertIn("permissions", op, "thiếu permissions — rowSecurity sẽ chặn")
        self.assertTrue(op["permissions"])
        gop = " ".join(op["permissions"])
        self.assertIn("usr_1", gop)

    def test_KHONG_mo_quyen_cong_khai(self) -> None:
        op = self.client.op_cua(COL_JOBS)
        gop = " ".join(op["permissions"]).lower()
        for cam in ('"any"', "any)", "users)", "guests"):
            self.assertNotIn(cam, gop, f"quyền công khai lọt vào: {cam}")

    def test_hang_khoa_cung_co_quyen(self) -> None:
        op = self.client.op_cua(COL_JOB_LOCKS)
        self.assertIsNotNone(op)
        self.assertTrue(op.get("permissions"))

    def test_rowId_cua_khoa_la_TAT_DINH(self) -> None:
        op = self.client.op_cua(COL_JOB_LOCKS)
        self.assertEqual(op["rowId"], _job_lock_id("usr_1", "chp_1", "fp-1"))

    def test_HAI_op_trong_MOT_giao_dich(self) -> None:
        """
        Tach ra hai lan goi la mo lai dung khe ho ma khoa sinh ra de dong.
        """
        ops = self.client.cac_op()
        self.assertEqual(len(ops), 2)
        self.assertEqual({o["tableId"] for o in ops}, {COL_JOBS, COL_JOB_LOCKS})
        self.assertTrue(all(o["action"] == "create" for o in ops))


class CoSanSang(unittest.TestCase):
    """
    `/api/health` doc co nay. Mot co tien kiem chi dung SAU khi da hong thi vo
    dung dung o luc can no nhat.
    """

    def test_chua_thu_thi_la_None_chu_khong_phai_True(self) -> None:
        store = AppwriteMetadataStore(SETTINGS, client=ClientGia())
        self.assertIsNone(store._job_lock_ready)

    def test_commit_thanh_cong_moi_dat_True(self) -> None:
        store = AppwriteMetadataStore(SETTINGS, client=ClientGia())
        job, moi = store.create_job_once(mot_job(), "fp-1")
        self.assertTrue(moi)
        self.assertTrue(store._job_lock_ready)

    def test_khong_ghi_duoc_va_khong_doc_duoc_thi_False(self) -> None:
        """Bang chua ton tai: lui ve duong cu, va phai NOI RA."""
        store = AppwriteMetadataStore(SETTINGS, client=ClientGia(commit_status="no"))
        job, moi = store.create_job_once(mot_job(), "fp-1")
        self.assertTrue(moi, "vẫn phải tạo được job, chỉ là không có khoá")
        self.assertIs(store._job_lock_ready, False)

    def test_THUA_CUOC_la_bang_chung_khoa_DANG_CHAY(self) -> None:
        """
        Thua mot cuoc dua nghia la ai do da ghi duoc hang khoa — do la duong
        khoa hoat dong dung thiet ke, khong phai su co. Ha co o day se bao
        dong gia moi lan hai tab cung bam.
        """
        rid = _job_lock_id("usr_1", "chp_1", "fp-1")
        client = ClientGia(commit_status="no",
                           rows={rid: {"job_id": "job_nguoi_thang"},
                                 "job_nguoi_thang": {
                                     "job_id": "job_nguoi_thang",
                                     "owner_id": "usr_1", "chapter_id": "chp_1",
                                     "voice_id": "mock:v1", "content_hash": "fp-1",
                                     "status": "running"}})
        store = AppwriteMetadataStore(SETTINGS, client=client)
        job, moi = store.create_job_once(mot_job(), "fp-1")
        self.assertFalse(moi, "phải nhận job của người thắng")
        self.assertEqual(job.job_id, "job_nguoi_thang")
        self.assertIs(store._job_lock_ready, True)


class HealthBaoRaBaTrangThai(unittest.TestCase):

    def test_health_khong_ep_ve_bool(self) -> None:
        """
        Ep `bool(None)` lam "chưa biết" hien ra thanh `false` — mot cau tra loi
        khac han, va nguoi van hanh se di sua mot thu khong hong.
        """
        import inspect

        from server import main as server_main

        nguon = inspect.getsource(server_main.health)
        self.assertIn('getattr(store, "_job_lock_ready", None)', nguon)
        self.assertNotIn('bool(getattr(store, "_job_lock_ready"', nguon)


if __name__ == "__main__":
    unittest.main()

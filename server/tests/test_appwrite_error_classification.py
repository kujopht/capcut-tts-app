"""
Phan biet loi ha tang TAM THOI (het han muc/rate limit Appwrite) voi loi
"ban ghi that su khong ton tai".

BOI CANH: canary staging that (2026-08-23) phat hien Appwrite Cloud het han
muc DOC ("Database reads limit for the current billing cycle has been
exceeded..."). `appwrite_store.py::_call()` truoc day doi MOI response
>= 400 thanh `NotFoundError`, nen mot truyen VUA TAO THANH CONG (201) bi bao
404 khi doc lai ngay lap tuc de tao chuong, va `/api/ready` bao sai
"loai_loi: NotFoundError" cho mot su co han muc chu khong phai ban ghi
thieu that.

Hai lop test:
1. `_la_loi_ha_tang_tam_thoi` + `_call` — logic phan loai o tang kho du lieu.
2. `TestLuoiAnToanToanCuc` — chung minh route `create_chapter` (chua TUNG bat
   rieng `AppwriteUnavailableError`) van tra 503 nho luoi an toan chung o
   `server/main.py`, khong phai 500 chung chung.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import (
    AppwriteUnavailableError,
    MockIdentityAdapter,
    MockMetadataStore,
    NotFoundError,
)
from server.appwrite_store import AppwriteMetadataStore, _la_loi_ha_tang_tam_thoi
from server.config import AppwriteSettings

SETTINGS = AppwriteSettings(
    endpoint="https://sgp.khong-co-that.example/v1",
    project_id="du-an-gia", api_key="khoa-gia", database_id="db-gia",
)

#: Nguyen van THAT tu Appwrite Cloud, bat qua canary staging 2026-08-23.
_THONG_DIEP_HET_HAN_MUC = (
    "Database reads limit for the current billing cycle has been exceeded. "
    "Please upgrade to a higher plan or update your budget cap.")


class _PhanHoiGia:
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self._body = body
        self.content = b"1" if body is not None else b""

    def json(self):
        if self._body is None:
            raise ValueError("khong co JSON")
        return self._body


class _ClientTraVe:
    def __init__(self, phan_hoi: _PhanHoiGia):
        self._phan_hoi = phan_hoi

    def request(self, method, url, json=None, params=None, headers=None):
        return self._phan_hoi


class NhanDienCumTuHetHanMucTest(unittest.TestCase):

    def test_cum_tu_billing_cycle_duoc_nhan_dien(self):
        self.assertTrue(_la_loi_ha_tang_tam_thoi(
            {"message": _THONG_DIEP_HET_HAN_MUC}))

    def test_khong_phan_biet_hoa_thuong(self):
        self.assertTrue(_la_loi_ha_tang_tam_thoi(
            {"message": "DATABASE WRITES LIMIT FOR THE CURRENT BILLING CYCLE..."}))

    def test_rate_limit_cung_duoc_nhan_dien(self):
        self.assertTrue(_la_loi_ha_tang_tam_thoi(
            {"message": "You have hit the rate limit for this resource."}))

    def test_thong_diep_khac_KHONG_bi_nhan_nham(self):
        self.assertFalse(_la_loi_ha_tang_tam_thoi(
            {"message": "Document with the requested ID could not be found."}))

    def test_body_rong_hoac_sai_dinh_dang_KHONG_crash(self):
        self.assertFalse(_la_loi_ha_tang_tam_thoi(None))
        self.assertFalse(_la_loi_ha_tang_tam_thoi({}))
        self.assertFalse(_la_loi_ha_tang_tam_thoi("khong phai dict"))
        self.assertFalse(_la_loi_ha_tang_tam_thoi({"message": None}))


class CallPhanLoaiLoiTest(unittest.TestCase):
    """`AppwriteMetadataStore._call()` — kiem THAT qua duong http gia lap,
    khong qua nhanh `_client` tiem san (nhanh do bo qua toan bo logic doc
    status_code dang can kiem o day)."""

    def _kho(self, phan_hoi: _PhanHoiGia) -> AppwriteMetadataStore:
        kho = AppwriteMetadataStore(SETTINGS)
        kho._pool = _ClientTraVe(phan_hoi)  # bo qua tao httpx.Client that
        return kho

    def test_het_han_muc_thanh_AppwriteUnavailableError_khong_phai_NotFoundError(self):
        kho = self._kho(_PhanHoiGia(400, {"message": _THONG_DIEP_HET_HAN_MUC}))
        with self.assertRaises(AppwriteUnavailableError) as ctx:
            kho._call("GET", "/some/path")
        self.assertIn("billing cycle", str(ctx.exception))

    def test_het_han_muc_DU_status_code_la_404_van_thanh_unavailable(self):
        """Khong gia dinh Appwrite dung ma cu the nao cho loi han muc — chi
        thong diep moi dang tin. Neu Appwrite tra 404 phong thu cho mot truy
        van bi chan boi han muc, van phai la 503, khong phai 404 that."""
        kho = self._kho(_PhanHoiGia(404, {"message": _THONG_DIEP_HET_HAN_MUC}))
        with self.assertRaises(AppwriteUnavailableError):
            kho._call("GET", "/some/path")

    def test_404_THAT_van_la_NotFoundError_khong_hoi_quy(self):
        kho = self._kho(_PhanHoiGia(
            404, {"message": "Document with the requested ID could not be found."}))
        with self.assertRaises(NotFoundError):
            kho._call("GET", "/some/path")

    def test_400_validation_thuong_van_la_NotFoundError_khong_hoi_quy(self):
        """Hanh vi CU van giu nguyen cho loi 4xx KHONG phai han muc — chi
        them MOT nhanh moi, khong doi hanh vi cac loi khac."""
        kho = self._kho(_PhanHoiGia(
            400, {"message": "Invalid `title` param: Value must be a string."}))
        with self.assertRaises(NotFoundError):
            kho._call("GET", "/some/path")

    def test_khong_doc_duoc_JSON_van_an_toan(self):
        kho = self._kho(_PhanHoiGia(500, None))
        with self.assertRaises(NotFoundError):
            kho._call("GET", "/some/path")


class _KhoHetHanMuc:
    """Gia lap toi thieu: CHI `owned_novel` nem `AppwriteUnavailableError`,
    dung nhu that tren staging khi doc mot truyen vua tao xong."""

    def owned_novel(self, novel_id: str, owner_id: str):
        raise AppwriteUnavailableError(_THONG_DIEP_HET_HAN_MUC)


class TestLuoiAnToanToanCuc(unittest.TestCase):
    """`create_chapter` CHUA TUNG bat rieng `AppwriteUnavailableError` (chi
    bat `NotFoundError`/`PermissionDenied`) — chung minh luoi an toan chung o
    `server/main.py` (`_appwrite_unavailable_handler`) van bien no thanh 503,
    khong phai 500 chung chung ma FastAPI se tra neu khong co luoi nay."""

    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.client = TestClient(server_main.app)
        r = self.client.post("/api/auth/register",
                             json={"email": "luoi-an-toan@example.test",
                                   "password": "matkhau123"})
        self.token = r.json()["token"]

    def tearDown(self) -> None:
        server_main.store = MockMetadataStore()

    def _auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def test_su_co_han_muc_luc_tao_chuong_tra_503_khong_phai_500(self):
        cu = server_main.store
        server_main.store = _KhoHetHanMuc()
        try:
            r = self.client.post(
                "/api/chapters",
                json={"novel_id": "nov_bat_ky", "title": "C1",
                     "content": "Noi dung.", "order_index": 1},
                headers=self._auth())
        finally:
            server_main.store = cu

        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(r.headers.get("X-Error-Code"), "appwrite_unavailable")

    def test_ma_loi_on_dinh_khong_lo_thong_diep_tieng_Viet_ra_ngoai_hop_dong(self):
        """`X-Error-Code` la truong ON DINH de cong cu giam sat doc — kiem
        rieng de khong ai vo tinh doi gia tri chuoi nay sau nay."""
        cu = server_main.store
        server_main.store = _KhoHetHanMuc()
        try:
            r = self.client.post(
                "/api/chapters",
                json={"novel_id": "nov_bat_ky", "title": "C1",
                     "content": "Noi dung.", "order_index": 1},
                headers=self._auth())
        finally:
            server_main.store = cu
        self.assertEqual(r.headers["X-Error-Code"], "appwrite_unavailable")


if __name__ == "__main__":
    unittest.main()

"""
`server/image_community_catalogue.py` — kham pha model anh cong dong MIEN
PHI THAT SU (gia == 0), tach biet voi Quick Free (an danh, khong biet model).

Moi test dung `httpx.MockTransport` — KHONG goi mang that.
"""

from __future__ import annotations

import json
import unittest

import httpx

from server.image_community_catalogue import (
    CommunityCatalogueCache,
    CommunityCatalogueError,
    _gia_bang_khong,
    _loc_mien_phi,
)


def _client_tra_ve(payload, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(payload, (list, dict)):
            return httpx.Response(status_code, json=payload)
        return httpx.Response(status_code, content=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


class GiaBangKhongTest(unittest.TestCase):
    def test_tat_ca_truong_gia_bang_khong_thi_true(self):
        self.assertTrue(_gia_bang_khong({"currency": "pollen", "completionImageTokens": "0"}))

    def test_mot_truong_khac_khong_thi_false(self):
        self.assertFalse(_gia_bang_khong({"currency": "pollen", "completionImageTokens": "0.004"}))

    def test_khong_co_truong_gia_nao_thi_khong_xac_dinh_tra_false(self):
        """Thieu hoan toan `pricing` (chi co currency, hoac rong) KHONG duoc
        suy dien la mien phi — day la yeu cau bat buoc cua ADDENDUM."""
        self.assertFalse(_gia_bang_khong({"currency": "pollen"}))
        self.assertFalse(_gia_bang_khong({}))

    def test_gia_tri_khong_doc_duoc_thi_false(self):
        self.assertFalse(_gia_bang_khong({"currency": "pollen", "completionImageTokens": "N/A"}))


class LocMienPhiTest(unittest.TestCase):
    def test_loc_dung_model_anh_gia_khong(self):
        entries = [
            {"name": "flux", "title": "Flux", "output_modalities": ["image"],
             "pricing": {"currency": "pollen", "completionImageTokens": "0.002"}},
            {"name": "vendouple/free-test", "title": "Free Test",
             "output_modalities": ["image"], "per_user_rpm": 10,
             "pricing": {"currency": "pollen", "completionImageTokens": "0"},
             "description": "self hosted, may get removed"},
        ]
        ra = _loc_mien_phi(entries)
        self.assertEqual(len(ra), 1)
        self.assertEqual(ra[0].model_id, "vendouple/free-test")
        self.assertEqual(ra[0].provider_badge, "vendouple")
        self.assertFalse(ra[0].is_official)
        self.assertEqual(ra[0].per_user_rpm, 10)
        self.assertTrue(ra[0].alpha_hint)

    def test_muse_glimmer_kieu_output_text_bi_loai_du_gia_khong(self):
        """Yeu cau bat buoc ADDENDUM #5: model chi accept anh dau vao (KHONG
        phai output anh) khong duoc lot vao Cong Free du gia co la 0."""
        entries = [
            {"name": "muse-glimmer", "title": "Muse Glimmer",
             "output_modalities": ["text"], "input_modalities": ["text", "image"],
             "pricing": {"currency": "pollen", "completionTextTokens": "0"}},
        ]
        self.assertEqual(_loc_mien_phi(entries), [])

    def test_model_chinh_thuc_khong_co_dau_gach_cheo(self):
        entries = [
            {"name": "flux", "title": "Flux", "output_modalities": ["image"],
             "pricing": {"currency": "pollen", "completionImageTokens": "0"}},
        ]
        ra = _loc_mien_phi(entries)
        self.assertEqual(ra[0].provider_badge, "")
        self.assertTrue(ra[0].is_official)

    def test_danh_sach_rong_neu_khong_model_nao_dat(self):
        entries = [
            {"name": "flux", "output_modalities": ["image"],
             "pricing": {"currency": "pollen", "completionImageTokens": "0.002"}},
        ]
        self.assertEqual(_loc_mien_phi(entries), [])


class CommunityCatalogueCacheTest(unittest.TestCase):
    def test_goi_that_thanh_cong_tra_ve_danh_sach_da_loc(self):
        payload = [
            {"name": "zimage", "output_modalities": ["image"],
             "pricing": {"currency": "pollen", "completionImageTokens": "0.004"}},
            {"name": "vendouple/free-one", "title": "Free One",
             "output_modalities": ["image"],
             "pricing": {"currency": "pollen", "completionImageTokens": "0"}},
        ]
        cache = CommunityCatalogueCache(http_client=_client_tra_ve(payload))
        ra = cache.lay_danh_sach()
        self.assertEqual([m.model_id for m in ra], ["vendouple/free-one"])

    def test_khong_phai_list_thi_nem_loi_an_toan(self):
        cache = CommunityCatalogueCache(http_client=_client_tra_ve({"khong": "phai list"}))
        with self.assertRaises(CommunityCatalogueError):
            cache.lay_danh_sach()

    def test_http_loi_thi_nem_loi_an_toan(self):
        cache = CommunityCatalogueCache(http_client=_client_tra_ve([], status_code=500))
        with self.assertRaises(CommunityCatalogueError):
            cache.lay_danh_sach()

    def test_cache_khong_goi_lai_trong_ttl(self):
        so_lan_goi = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi["n"] += 1
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cache = CommunityCatalogueCache(http_client=client, ttl_seconds=999.0)
        cache.lay_danh_sach()
        cache.lay_danh_sach()
        cache.lay_danh_sach()
        self.assertEqual(so_lan_goi["n"], 1)

    def test_force_refresh_bo_qua_ttl(self):
        so_lan_goi = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi["n"] += 1
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cache = CommunityCatalogueCache(http_client=client, ttl_seconds=999.0)
        cache.lay_danh_sach()
        cache.lay_danh_sach(force_refresh=True)
        self.assertEqual(so_lan_goi["n"], 2)

    def test_loi_mang_giu_du_lieu_cu_thay_vi_xoa_trang(self):
        trang_thai = {"loi": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if trang_thai["loi"]:
                return httpx.Response(500)
            return httpx.Response(200, json=[
                {"name": "vendouple/free-one", "output_modalities": ["image"],
                 "pricing": {"currency": "pollen", "completionImageTokens": "0"}},
            ])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cache = CommunityCatalogueCache(http_client=client, ttl_seconds=0.0)
        dau_tien = cache.lay_danh_sach()
        self.assertEqual(len(dau_tien), 1)
        trang_thai["loi"] = True
        sau_loi = cache.lay_danh_sach(force_refresh=True)
        self.assertEqual(sau_loi, dau_tien)
        self.assertTrue(cache.loi_gan_nhat())


if __name__ == "__main__":
    unittest.main()

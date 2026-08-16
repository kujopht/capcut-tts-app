"""
HOP DONG giua kho mock va kho Appwrite cho Trusted Video Sources (Phase 5).

Cung ly do ton tai voi `test_animation_contract.py`: dung lai
`FakeAppwrite`/`_bo_client` cua `test_appwrite_v2_contract.py`.
"""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError
from server.appwrite_trusted_source_store import AppwriteTrustedSourceStore
from server.config import AppwriteSettings
from server.trusted_source_domain import (
    ImportStatus,
    SeriesMapping,
    TrustedSource,
    TrustedSourceType,
    VideoImport,
)
from server.trusted_source_store import MockTrustedSourceStore
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteTrustedSourceStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteTrustedSourceStore(cfg, client=_bo_client(fake))
    kho._attrs_cache = {}
    return kho


class HopDongTrustedSourceTest(unittest.TestCase):
    def _cac_kho(self):
        return [("mock", MockTrustedSourceStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # ===================================================== trusted source

    def test_tao_va_doc_lai_nguon(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_source(TrustedSource(
                    source_type=TrustedSourceType.YOUTUBE_CHANNEL,
                    youtube_channel_id="UC123", display_name="Kênh A"))
                lai = kho.get_source(s.source_id)
                self.assertEqual(lai.display_name, "Kênh A", ten)
                self.assertTrue(lai.enabled, ten)

    def test_nguon_khong_ton_tai_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_source("khong_co")

    def test_update_source_chi_truong_cho_phep(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_source(TrustedSource(
                    youtube_channel_id="UC1", display_name="Cũ"))
                updated = kho.update_source(s.source_id, {
                    "display_name": "Mới", "enabled": False,
                    "auto_import": True, "minimum_confidence": 0.5,
                    # KHONG duoc phep sua qua day.
                    "youtube_channel_id": "UC_KHAC",
                })
                self.assertEqual(updated.display_name, "Mới", ten)
                self.assertFalse(updated.enabled, ten)
                self.assertTrue(updated.auto_import, ten)
                self.assertEqual(updated.minimum_confidence, 0.5, ten)
                self.assertEqual(updated.youtube_channel_id, "UC1", ten)

    def test_delete_source_xoa_ca_anh_xa_con_lai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_source(TrustedSource(youtube_channel_id="UC1"))
                m = kho.create_mapping(SeriesMapping(
                    trusted_source_id=s.source_id, animation_series_id="ani_1"))
                kho.delete_source(s.source_id)
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_source(s.source_id)
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_mapping(m.mapping_id)

    def test_find_sources_loc_va_tim(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                a = kho.create_source(TrustedSource(
                    youtube_channel_id="UC1", display_name="Kênh Một"))
                kho.create_source(TrustedSource(
                    youtube_channel_id="UC2", display_name="Kênh Hai"))
                kho.update_source(a.source_id, {"enabled": False})

                bat, tong = kho.find_sources(enabled=True)
                self.assertEqual(tong, 1, ten)

                tim, _ = kho.find_sources(query="Một")
                self.assertEqual(len(tim), 1, ten)

    def test_find_sources_phan_trang(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(5):
                    kho.create_source(TrustedSource(
                        youtube_channel_id=f"UC{i}", display_name=f"K{i}"))
                trang1, tong = kho.find_sources(limit=2, offset=0)
                self.assertEqual(len(trang1), 2, ten)
                self.assertEqual(tong, 5, ten)

    def test_record_scan_result_thanh_cong_va_that_bai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_source(TrustedSource(youtube_channel_id="UC1"))
                ok = kho.record_scan_result(s.source_id, success=True)
                self.assertTrue(ok.last_scan_at, ten)
                self.assertTrue(ok.last_success_at, ten)

                loi = kho.record_scan_result(
                    s.source_id, success=False, error_message="Hết hạn mức API")
                self.assertTrue(loi.last_error_at, ten)
                self.assertEqual(loi.last_error_message, "Hết hạn mức API", ten)

    # ===================================================== series mapping

    def test_tao_va_liet_ke_anh_xa(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_source(TrustedSource(youtube_channel_id="UC1"))
                kho.create_mapping(SeriesMapping(
                    trusted_source_id=s.source_id, animation_series_id="ani_1",
                    aliases=["a", "b"]))
                ds = kho.list_mappings(s.source_id)
                self.assertEqual(len(ds), 1, ten)
                self.assertEqual(ds[0].aliases, ["a", "b"], ten)

    def test_update_mapping_chi_truong_cho_phep(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                m = kho.create_mapping(SeriesMapping(
                    trusted_source_id="tsrc_1", animation_series_id="ani_1"))
                updated = kho.update_mapping(m.mapping_id, {
                    "aliases": ["x"], "minimum_confidence": 0.8,
                    "animation_series_id": "ani_KHAC",
                })
                self.assertEqual(updated.aliases, ["x"], ten)
                self.assertEqual(updated.minimum_confidence, 0.8, ten)
                self.assertEqual(updated.animation_series_id, "ani_1", ten)

    def test_delete_mapping(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                m = kho.create_mapping(SeriesMapping(
                    trusted_source_id="tsrc_1", animation_series_id="ani_1"))
                kho.delete_mapping(m.mapping_id)
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_mapping(m.mapping_id)

    def test_mapping_counts_nhieu_nguon(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_mapping(SeriesMapping(
                    trusted_source_id="tsrc_1", animation_series_id="ani_1"))
                kho.create_mapping(SeriesMapping(
                    trusted_source_id="tsrc_1", animation_series_id="ani_2"))
                kho.create_mapping(SeriesMapping(
                    trusted_source_id="tsrc_2", animation_series_id="ani_3"))
                dem = kho.mapping_counts(["tsrc_1", "tsrc_2", "khong_co"])
                self.assertEqual(dem["tsrc_1"], 2, ten)
                self.assertEqual(dem["tsrc_2"], 1, ten)
                self.assertEqual(dem["khong_co"], 0, ten)

    # ===================================================== video import

    def test_create_import_once_khong_trung(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                v1, moi1 = kho.create_import_once(VideoImport(
                    youtube_video_id="abc12345678", title="Tập 1"))
                v2, moi2 = kho.create_import_once(VideoImport(
                    youtube_video_id="abc12345678", title="Tập 1 (khác import_id)"))
                self.assertTrue(moi1, ten)
                self.assertFalse(moi2, ten)
                self.assertEqual(v1.import_id, v2.import_id, ten)
                self.assertEqual(v2.title, "Tập 1", ten)  # BAN GHI CU, khong ghi de

    def test_get_import_by_video_id(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_import_once(VideoImport(youtube_video_id="vid1"))
                tim = kho.get_import_by_video_id("vid1")
                self.assertIsNotNone(tim, ten)
                self.assertIsNone(kho.get_import_by_video_id("khong_co"), ten)

    def test_imports_by_video_ids_theo_lo(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_import_once(VideoImport(youtube_video_id="v1"))
                kho.create_import_once(VideoImport(youtube_video_id="v2"))
                dem = kho.imports_by_video_ids(["v1", "v2", "v3"])
                self.assertEqual(set(dem.keys()), {"v1", "v2"}, ten)

    def test_find_imports_loc_theo_status_va_nguon(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                v1, _ = kho.create_import_once(VideoImport(
                    trusted_source_id="s1", youtube_video_id="v1",
                    status=ImportStatus.PENDING))
                kho.create_import_once(VideoImport(
                    trusted_source_id="s2", youtube_video_id="v2",
                    status=ImportStatus.NEW))
                cho, tong = kho.find_imports(status="pending")
                self.assertEqual(tong, 1, ten)
                self.assertEqual(cho[0].import_id, v1.import_id, ten)

                cua_s1, _ = kho.find_imports(trusted_source_id="s1")
                self.assertEqual(len(cua_s1), 1, ten)

    def test_update_import(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                v, _ = kho.create_import_once(VideoImport(youtube_video_id="v1"))
                updated = kho.update_import(v.import_id, {
                    "status": ImportStatus.IMPORTED.value,
                    "created_episode_id": "anep_x",
                })
                self.assertEqual(updated.status, ImportStatus.IMPORTED, ten)
                self.assertEqual(updated.created_episode_id, "anep_x", ten)


class BuildTrustedSourceStoreTest(unittest.TestCase):
    def test_mac_dinh_mock(self):
        from server.appwrite_trusted_source_store import build_trusted_source_store

        class GiaSettings:
            data_backend = "mock"

        self.assertIsInstance(build_trusted_source_store(GiaSettings()),
                              MockTrustedSourceStore)

    def test_appwrite_thieu_cau_hinh_nem_loi_ngay(self):
        from server.appwrite_adapter import AppwriteConfigError
        from server.appwrite_trusted_source_store import build_trusted_source_store

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AppwriteSettings(endpoint="", project_id="",
                                        api_key="", database_id="")

        with self.assertRaises(AppwriteConfigError):
            build_trusted_source_store(GiaSettings())

    def test_appwrite_du_cau_hinh_tra_dung_lop(self):
        from server.appwrite_trusted_source_store import build_trusted_source_store

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AppwriteSettings(endpoint="https://x.invalid/v1",
                                        project_id="p", api_key="k",
                                        database_id="db")

        self.assertIsInstance(build_trusted_source_store(GiaSettings()),
                              AppwriteTrustedSourceStore)


if __name__ == "__main__":
    unittest.main()

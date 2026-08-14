"""
HOP DONG giua kho mock va kho Appwrite cho Animation (V6, overnight Phase 5).

Cung ly do ton tai voi `test_gamification_contract.py`: dung lai
`FakeAppwrite`/`_bo_client` cua `test_appwrite_v2_contract.py`, khong xay lai
tu dau.
"""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError, PermissionDenied
from server.animation_domain import AnimationEpisode, AnimationSeries
from server.animation_store import MockAnimationStore
from server.appwrite_animation_store import AppwriteAnimationStore
from server.config import AppwriteSettings
from server.domain import PublishState
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteAnimationStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteAnimationStore(cfg, client=_bo_client(fake))
    kho._attrs_cache = {}
    return kho


class HopDongAnimationTest(unittest.TestCase):
    """Moi bai duoi day chay tren CA HAI kho — `ten` bao ro ban nao lech."""

    def _cac_kho(self):
        return [("mock", MockAnimationStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # ===================================================== series

    def test_create_va_get_series(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(
                    owner_id="u1", title="Series A"))
                lai = kho.get_series(s.series_id)
                self.assertEqual(lai.title, "Series A", ten)
                self.assertEqual(lai.state, PublishState.DRAFT, ten)

    def test_get_series_khong_ton_tai_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_series("khong_ton_tai")

    def test_owned_series_sai_chu_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                with self.assertRaises(PermissionDenied, msg=ten):
                    kho.owned_series(s.series_id, "u2")

    def test_publish_series_idempotent_va_mo_doc_cong_khai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                p1 = kho.publish_series(s.series_id, "u1")
                self.assertEqual(p1.state, PublishState.PUBLISHED, ten)
                # Idempotent — goi lai khong loi, khong doi gi.
                p2 = kho.publish_series(s.series_id, "u1")
                self.assertEqual(p2.state, PublishState.PUBLISHED, ten)

    def test_publish_series_sai_chu_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                with self.assertRaises(PermissionDenied, msg=ten):
                    kho.publish_series(s.series_id, "u2")

    def test_unpublish_series_idempotent(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                kho.publish_series(s.series_id, "u1")
                r1 = kho.unpublish_series(s.series_id, "u1")
                self.assertEqual(r1.state, PublishState.DRAFT, ten)
                r2 = kho.unpublish_series(s.series_id, "u1")
                self.assertEqual(r2.state, PublishState.DRAFT, ten)

    def test_update_series_chi_truong_cho_phep(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                updated = kho.update_series(s.series_id, "u1", {
                    "title": "Ten moi", "description": "Mo ta moi",
                    "tags": ["a", "b"], "related_novel_id": "nov_x",
                    # Truong KHONG duoc phep sua qua day — phai bi loc bo.
                    "owner_id": "ke_khac", "state": "published",
                })
                self.assertEqual(updated.title, "Ten moi", ten)
                self.assertEqual(updated.tags, ["a", "b"], ten)
                self.assertEqual(updated.related_novel_id, "nov_x", ten)
                self.assertEqual(updated.owner_id, "u1", ten)
                self.assertEqual(updated.state, PublishState.DRAFT, ten)

    def test_delete_series(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                kho.delete_series(s.series_id, "u1")
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_series(s.series_id)

    def test_find_series_loc_theo_chu_va_trang_thai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                a = kho.create_series(AnimationSeries(owner_id="u1", title="A"))
                kho.create_series(AnimationSeries(owner_id="u1", title="B"))
                kho.create_series(AnimationSeries(owner_id="u2", title="C"))
                kho.publish_series(a.series_id, "u1")

                cua_u1, tong = kho.find_series(owner_id="u1")
                self.assertEqual(len(cua_u1), 2, ten)
                self.assertEqual(tong, 2, ten)

                da_xuat_ban, tong2 = kho.find_series(published_only=True)
                self.assertEqual([s.series_id for s in da_xuat_ban],
                                 [a.series_id], ten)
                self.assertEqual(tong2, 1, ten)

    def test_find_series_tim_theo_tu_khoa(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_series(AnimationSeries(
                    owner_id="u1", title="Hải Tặc Vùng Đông", state=PublishState.PUBLISHED))
                kho.create_series(AnimationSeries(
                    owner_id="u1", title="Không khớp", state=PublishState.PUBLISHED))
                ds, _ = kho.find_series(published_only=True, query="Hải Tặc")
                self.assertEqual(len(ds), 1, ten)

    def test_series_tags_bo_trung_va_chi_da_xuat_ban(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                a = kho.create_series(AnimationSeries(
                    owner_id="u1", title="A", tags=["hanh_dong", "vien_tuong"]))
                kho.create_series(AnimationSeries(
                    owner_id="u1", title="B", tags=["hanh_dong"]))
                kho.publish_series(a.series_id, "u1")
                tags = kho.series_tags(published_only=True)
                self.assertEqual(tags, ["hanh_dong", "vien_tuong"], ten)

    def test_find_series_phan_trang(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(5):
                    kho.create_series(AnimationSeries(
                        owner_id="u1", title=f"S{i}", state=PublishState.PUBLISHED))
                trang1, tong = kho.find_series(published_only=True, limit=2, offset=0)
                self.assertEqual(len(trang1), 2, ten)
                self.assertEqual(tong, 5, ten)

    # ===================================================== episode

    def test_create_va_list_episodes_sap_theo_order_index(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 2",
                    external_id="a" * 11, order_index=2))
                kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="b" * 11, order_index=1))
                ds = kho.list_episodes(s.series_id)
                self.assertEqual([e.title for e in ds], ["Tap 1", "Tap 2"], ten)

    def test_owned_episode_sai_chu_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                e = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="a" * 11))
                with self.assertRaises(PermissionDenied, msg=ten):
                    kho.owned_episode(e.episode_id, "u2")

    def test_update_episode_chi_truong_cho_phep(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                e = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="a" * 11))
                updated = kho.update_episode(e.episode_id, "u1", {
                    "title": "Ten moi", "external_id": "c" * 11,
                    "order_index": 5, "duration_seconds": 120.0,
                    # Khong duoc phep sua qua day.
                    "owner_id": "ke_khac", "series_id": "series_khac",
                })
                self.assertEqual(updated.title, "Ten moi", ten)
                self.assertEqual(updated.external_id, "c" * 11, ten)
                self.assertEqual(updated.duration_seconds, 120.0, ten)
                self.assertEqual(updated.owner_id, "u1", ten)
                self.assertEqual(updated.series_id, s.series_id, ten)

    def test_delete_episode(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                e = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="a" * 11))
                kho.delete_episode(e.episode_id, "u1")
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_episode(e.episode_id)

    def test_reorder_episodes_dung(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                e1 = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="a" * 11, order_index=1))
                e2 = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 2",
                    external_id="b" * 11, order_index=2))
                ds = kho.reorder_episodes(
                    s.series_id, "u1", [e2.episode_id, e1.episode_id])
                self.assertEqual([e.episode_id for e in ds],
                                 [e2.episode_id, e1.episode_id], ten)
                self.assertEqual(kho.get_episode(e2.episode_id).order_index, 1, ten)
                self.assertEqual(kho.get_episode(e1.episode_id).order_index, 2, ten)

    def test_reorder_episodes_thieu_mot_tap_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                e1 = kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 1",
                    external_id="a" * 11))
                kho.create_episode(AnimationEpisode(
                    series_id=s.series_id, owner_id="u1", title="Tap 2",
                    external_id="b" * 11))
                with self.assertRaises(ValueError, msg=ten):
                    kho.reorder_episodes(s.series_id, "u1", [e1.episode_id])

    def test_reorder_episodes_sai_chu_series_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                s = kho.create_series(AnimationSeries(owner_id="u1", title="T"))
                with self.assertRaises(PermissionDenied, msg=ten):
                    kho.reorder_episodes(s.series_id, "u2", [])


class BuildAnimationStoreTest(unittest.TestCase):
    """`build_animation_store` phai chon dung kho theo `DATA_BACKEND`, va
    KHONG bao gio am tham lui ve mock khi da khai bao Appwrite."""

    def test_mac_dinh_mock(self):
        from server.appwrite_animation_store import build_animation_store

        class GiaSettings:
            data_backend = "mock"

        self.assertIsInstance(build_animation_store(GiaSettings()),
                              MockAnimationStore)

    def test_appwrite_thieu_cau_hinh_nem_loi_ngay(self):
        from server.appwrite_adapter import AppwriteConfigError
        from server.appwrite_animation_store import build_animation_store

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AppwriteSettings(endpoint="", project_id="",
                                        api_key="", database_id="")

        with self.assertRaises(AppwriteConfigError):
            build_animation_store(GiaSettings())

    def test_appwrite_du_cau_hinh_tra_dung_lop(self):
        from server.appwrite_animation_store import build_animation_store

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AppwriteSettings(endpoint="https://x.invalid/v1",
                                        project_id="p", api_key="k",
                                        database_id="db")

        self.assertIsInstance(build_animation_store(GiaSettings()),
                              AppwriteAnimationStore)


if __name__ == "__main__":
    unittest.main()

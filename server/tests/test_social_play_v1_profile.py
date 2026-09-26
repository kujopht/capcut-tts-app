"""
Social Play V1 — ho so cong khai (`server/creator_service.py`) va sua ho so
ca nhan (`SocialService.update_profile`, `server/image_normalize.py`).
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.appwrite_social import COL_POSTS
from server.creator_service import CreatorService
from server.domain import Profile
from server.gamification_domain import CosmeticInventoryItem
from server.gamification_store import MockGamificationStore
from server.social import CAPABILITY_KEYS, ACCENT_PRESETS, CapabilityDisabled, SocialError
from server.social_service import SocialService
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _kho_appwrite


def _tat_ca_bat() -> dict:
    return {k: True for k in CAPABILITY_KEYS}


def _png_b64(size=(300, 300), color=(10, 20, 30)) -> str:
    import base64

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        self.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.gamification = MockGamificationStore()
        self.social = SocialService(self.identity, self.store, self.storage,
                                   gamification_store=self.gamification,
                                   capabilities=_tat_ca_bat())
        self.creators = CreatorService(self.identity, self.store, self.storage)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")
        self.an.username = "an"
        self.identity.save_profile(self.an)


class PublicProfileTest(Nen):
    def test_theo_username(self):
        goi = self.creators.public_profile_by_username("an")
        self.assertEqual(goi["user_id"], self.an.user_id)
        self.assertNotIn("email", goi)

    def test_theo_user_id_khi_chua_chon_username(self):
        goi = self.creators.public_profile_by_id(self.binh.user_id)
        self.assertIsNotNone(goi)
        self.assertEqual(goi["user_id"], self.binh.user_id)

    def test_khong_ton_tai_tra_none(self):
        self.assertIsNone(self.creators.public_profile_by_username("khong-ai"))
        self.assertIsNone(self.creators.public_profile_by_id("usr_khong_ton_tai"))

    def test_khong_ro_ri_truong_rieng_tu(self):
        goi = self.creators.public_profile_by_username("an")
        for khoa_cam in ("email", "tier", "tts_characters_used", "author_status"):
            self.assertNotIn(khoa_cam, goi)

    def test_co_banner_url_accent_fandom_ids(self):
        goi = self.creators.public_profile_by_username("an")
        for khoa in ("banner_url", "accent", "fandom_ids"):
            self.assertIn(khoa, goi)

    def test_viewer_relation_chi_hien_khi_dang_nhap_xem_nguoi_khac(self):
        goi_social = self.social.profile_social(self.an, viewer=None)
        self.assertNotIn("viewer_relation", goi_social)
        goi_social = self.social.profile_social(self.an, viewer=self.an)
        self.assertNotIn("viewer_relation", goi_social)


class UpdateProfileCoBanTest(Nen):
    def test_sua_bio_va_fandom(self):
        updated = self.social.update_profile(
            self.an, bio="Xin chào", fandom_ids=["naruto", "one-piece"])
        self.assertEqual(updated.bio, "Xin chào")
        self.assertEqual(updated.fandom_ids, ["naruto", "one-piece"])

    def test_vuot_qua_so_fandom_toi_da_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.update_profile(
                self.an, fandom_ids=["naruto", "one-piece", "conan",
                                     "genshin-impact", "fairy-tail", "bong-ro"])

    def test_fandom_khong_hop_le_bi_tu_choi_KHONG_ghi_gi(self):
        truoc = self.an.bio
        with self.assertRaises(SocialError):
            self.social.update_profile(self.an, bio="Sẽ không được lưu",
                                       fandom_ids=["khong-ton-tai"])
        self.assertEqual(self.identity.get_profile(self.an.user_id).bio, truoc)

    def test_accent_hop_le(self):
        updated = self.social.update_profile(self.an, accent=ACCENT_PRESETS[0])
        self.assertEqual(updated.accent, ACCENT_PRESETS[0])

    def test_accent_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.update_profile(self.an, accent="mau-khong-ton-tai")

    def test_accent_rong_la_xoa_ve_mac_dinh(self):
        self.social.update_profile(self.an, accent=ACCENT_PRESETS[0])
        updated = self.social.update_profile(self.an, accent="")
        self.assertEqual(updated.accent, "")

    def test_truong_khong_nhac_den_giu_nguyen(self):
        self.social.update_profile(self.an, bio="Giữ nguyên cái này")
        updated = self.social.update_profile(self.an, accent=ACCENT_PRESETS[1])
        self.assertEqual(updated.bio, "Giữ nguyên cái này")


class UpdateProfileAnhTest(Nen):
    def test_avatar_hop_le_duoc_ghi_va_khoa_dung_khong_gian_ten(self):
        updated = self.social.update_profile(
            self.an, avatar={"data": _png_b64(), "mime": "image/png"})
        self.assertTrue(updated.avatar_key.startswith(f"avatars/{self.an.user_id}/"))
        self.assertTrue(updated.avatar_key.endswith(".webp"))
        self.assertTrue(self.storage.exists(updated.avatar_key))

    def test_du_lieu_rac_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.update_profile(
                self.an, avatar={"data": "cmFj", "mime": "image/png"})

    def test_banner_doi_hoi_nang_luc(self):
        tat = SocialService(self.identity, self.store, self.storage,
                            gamification_store=self.gamification,
                            capabilities={k: False for k in CAPABILITY_KEYS})
        with self.assertRaises(CapabilityDisabled):
            tat.update_profile(self.an, banner={"data": _png_b64(), "mime": "image/png"})

    def test_xoa_anh_cu_CHI_SAU_khi_ghi_ho_so_thanh_cong(self):
        b64 = _png_b64()
        u1 = self.social.update_profile(self.an, avatar={"data": b64, "mime": "image/png"})
        khoa_cu = u1.avatar_key
        self.assertTrue(self.storage.exists(khoa_cu))

        b64_khac = _png_b64(color=(99, 88, 77))  # noi dung KHAC -> hash khac -> khoa khac
        u2 = self.social.update_profile(self.an, avatar={"data": b64_khac, "mime": "image/png"})
        self.assertNotEqual(u2.avatar_key, khoa_cu)
        self.assertFalse(self.storage.exists(khoa_cu))          # da xoa
        self.assertTrue(self.storage.exists(u2.avatar_key))      # anh moi con

    def test_that_bai_ghi_ho_so_don_anh_moi_vua_tai(self):
        class HoSoHong(Exception):
            pass

        class IdentityHong:
            def save_profile(self, profile):
                raise HoSoHong("gia lap hong")

        social_hong = SocialService(IdentityHong(), self.store, self.storage,
                                    gamification_store=self.gamification,
                                    capabilities=_tat_ca_bat())
        truoc = set(o.key for o in self.storage.list_objects())
        with self.assertRaises(Exception):
            social_hong.update_profile(
                self.an, avatar={"data": _png_b64(), "mime": "image/png"})
        sau = set(o.key for o in self.storage.list_objects())
        self.assertEqual(truoc, sau)   # khong con anh mo coi nao

    def test_go_avatar(self):
        self.social.update_profile(self.an, avatar={"data": _png_b64(), "mime": "image/png"})
        updated = self.social.update_profile(self.an, avatar={"remove": True})
        self.assertEqual(updated.avatar_key, "")


class UpdateProfileKhungTest(Nen):
    def setUp(self) -> None:
        super().setUp()
        self.gamification.grant_cosmetic(
            CosmeticInventoryItem(user_id=self.an.user_id, cosmetic_key="khung_go"))

    def test_trang_bi_khung_da_so_huu(self):
        updated = self.social.update_profile(self.an, frame="khung_go")
        muc = self.gamification.get_cosmetic(self.an.user_id, "khung_go")
        self.assertTrue(muc.equipped)

    def test_khung_chua_so_huu_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.update_profile(self.an, frame="khung_vang")

    def test_vat_pham_khong_phai_khung_bi_tu_choi(self):
        self.gamification.grant_cosmetic(
            CosmeticInventoryItem(user_id=self.an.user_id, cosmetic_key="huy_hieu_but_long"))
        with self.assertRaises(SocialError):
            self.social.update_profile(self.an, frame="huy_hieu_but_long")

    def test_frame_null_bo_trang_bi(self):
        self.social.update_profile(self.an, frame="khung_go")
        self.social.update_profile(self.an, frame=None)
        muc = self.gamification.get_cosmetic(self.an.user_id, "khung_go")
        self.assertFalse(muc.equipped)


class GoogleReloginTest(Nen):
    def test_ensure_profile_khong_ghi_de_avatar_banner_bio(self):
        self.social.update_profile(self.an, bio="Tôi tự viết", accent="jade",
                                   avatar={"data": _png_b64(), "mime": "image/png"})
        truoc = self.identity.get_profile(self.an.user_id)

        # Gia lap dang nhap lai bang Google: `ensure_profile` goi VOI mot
        # Profile "moi" tu OAuth (khong mang bio/avatar), nhung phai TRA VE
        # ban DA CO nguyen ven — TIM-HOAC-TAO, khong ghi de.
        gia_ho_so_oauth = Profile(user_id=self.an.user_id, email=self.an.email,
                                  display_name="Tên từ Google")
        lai = self.identity.ensure_profile(gia_ho_so_oauth)

        self.assertEqual(lai.bio, truoc.bio)
        self.assertEqual(lai.accent, truoc.accent)
        self.assertEqual(lai.avatar_key, truoc.avatar_key)


class AppwriteCapabilityPayloadTest(unittest.TestCase):
    """Kho Appwrite KHONG BAO GIO gui `fandom_id`/`edited_at` khi Appwrite
    THAT SU chua co thuoc tinh do trong schema — bat ke co `social_v1_schema`
    hay khong, day la lop phong thu THU HAI (`_supported_fields`, xem ghi chu
    o `appwrite_social.SOCIAL_PERSISTED_FIELDS`)."""

    def test_truong_moi_bi_loc_khi_schema_chua_co(self):
        kho = _kho_appwrite(FakeAppwrite())
        # Gia lap schema THAT: collection `posts` CHUA co ba truong V1.
        kho._attrs_cache[COL_POSTS] = {
            "post_id", "author_user_id", "kind", "novel_id", "text",
            "state", "like_count", "comment_count", "removed_by",
            "removed_reason", "created_at", "updated_at", "images_json",
            "image_key", "image_mime", "image_width", "image_height",
            "image_bytes",
        }
        data = kho._writable(COL_POSTS, {
            "post_id": "pst_x", "author_user_id": "u1", "kind": "post",
            "novel_id": "", "text": "hi", "state": "visible",
            "like_count": 0, "comment_count": 0, "removed_by": "",
            "removed_reason": "", "created_at": "t", "updated_at": "t",
            "spoiler": True, "fandom_id": "naruto", "edited_at": "t2",
        })
        for khoa in ("spoiler", "fandom_id", "edited_at"):
            self.assertNotIn(khoa, data)

    def test_truong_moi_duoc_gui_khi_schema_da_co(self):
        kho = _kho_appwrite(FakeAppwrite())
        kho._attrs_cache[COL_POSTS] = {
            "post_id", "author_user_id", "kind", "novel_id", "text",
            "state", "like_count", "comment_count", "removed_by",
            "removed_reason", "created_at", "updated_at",
            "spoiler", "fandom_id", "edited_at",
        }
        data = kho._writable(COL_POSTS, {
            "post_id": "pst_x", "author_user_id": "u1", "kind": "post",
            "novel_id": "", "text": "hi", "state": "visible",
            "like_count": 0, "comment_count": 0, "removed_by": "",
            "removed_reason": "", "created_at": "t", "updated_at": "t",
            "spoiler": True, "fandom_id": "naruto", "edited_at": "t2",
        })
        self.assertEqual(data["fandom_id"], "naruto")


if __name__ == "__main__":
    unittest.main()

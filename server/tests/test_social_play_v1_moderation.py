"""
Social Play V1 — chan/tat tieng nguoi dung va bao cao "user".

Chay tren kho MOCK. `test_social_play_v1_contract.py` doi soat cac ham kho
moi (`add_user_block`/`hidden_authors_for_viewer`/...) giua mock va Appwrite.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore, PermissionDenied
from server.social import CAPABILITY_KEYS, CapabilityDisabled, SocialError
from server.social_service import SocialService


def _tat_ca_bat() -> dict:
    return {k: True for k in CAPABILITY_KEYS}


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        self.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.social = SocialService(self.identity, self.store, self.storage,
                                   capabilities=_tat_ca_bat())
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")
        self.cuc = self.identity.register("cuc@vidu.vn", "MatKhau123", "Cúc")


class CapabilityTatTest(Nen):
    def test_chan_bi_tu_choi_khi_tat_nang_luc(self):
        tat = SocialService(self.identity, self.store, self.storage,
                            capabilities={k: False for k in CAPABILITY_KEYS})
        with self.assertRaises(CapabilityDisabled):
            tat.block_user(self.an, self.binh.user_id)


class BlockCoBanTest(Nen):
    def test_chan_roi_bo_chan(self):
        ra = self.social.block_user(self.an, self.binh.user_id)
        self.assertTrue(ra["blocked"])
        self.assertFalse(ra["muted"])
        ra = self.social.unblock_user(self.an, self.binh.user_id)
        self.assertFalse(ra["blocked"])

    def test_tu_chan_minh_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.block_user(self.an, self.an.user_id)

    def test_chan_nguoi_khong_ton_tai_404(self):
        from server.adapters import NotFoundError
        with self.assertRaises(NotFoundError):
            self.social.block_user(self.an, "usr_khong_ton_tai")

    def test_chan_xoa_canh_theo_doi_ca_hai_chieu(self):
        self.social.follow_user(self.an, self.binh.user_id)
        self.social.follow_user(self.binh, self.an.user_id)
        self.social.block_user(self.an, self.binh.user_id)
        self.assertFalse(self.social.profile_social(self.binh, self.an)["following"])
        self.assertFalse(self.social.profile_social(self.an, self.binh)["following"])

    def test_khong_lo_ai_da_chan_ai_o_ca_hai_phia(self):
        """`viewer_relation` CHI phan anh CHINH nguoi xem co chan/tat tieng
        hay khong — nguoi BI chan xem trang cua nguoi da chan minh KHONG
        duoc thay bit nao noi ho dang bi chan."""
        self.social.block_user(self.an, self.binh.user_id)
        # An xem trang cua Binh: An biet minh da chan Binh.
        goi_an = self.social.profile_social(self.binh, self.an)
        self.assertTrue(goi_an["viewer_relation"]["blocked"])
        # Binh xem trang cua An: Binh KHONG duoc biet minh dang bi chan.
        goi_binh = self.social.profile_social(self.an, self.binh)
        self.assertNotIn("blocked_by", goi_binh)
        self.assertFalse(goi_binh.get("viewer_relation", {}).get("blocked", False))


class BlockTuongTacTest(Nen):
    def test_theo_doi_bi_tu_choi_khi_co_canh_chan(self):
        self.social.block_user(self.an, self.binh.user_id)
        with self.assertRaises(PermissionDenied):
            self.social.follow_user(self.binh, self.an.user_id)
        with self.assertRaises(PermissionDenied):
            self.social.follow_user(self.an, self.binh.user_id)

    def test_thich_bi_tu_choi_khi_co_canh_chan(self):
        bai = self.social.create_post(self.an, text="Bài của An")
        self.social.block_user(self.an, self.binh.user_id)
        with self.assertRaises(PermissionDenied):
            self.social.like_post(self.binh, bai["post_id"])

    def test_binh_luan_bi_tu_choi_khi_co_canh_chan(self):
        bai = self.social.create_post(self.an, text="Bài của An")
        self.social.block_user(self.binh, self.an.user_id)
        with self.assertRaises(PermissionDenied):
            self.social.create_comment(self.binh, bai["post_id"], text="Xin chào")

    def test_tat_tieng_KHONG_chan_tuong_tac(self):
        bai = self.social.create_post(self.an, text="Bài của An")
        self.social.mute_user(self.binh, self.an.user_id)
        # Binh da tat tieng An nhung van thich/binh luan duoc bai cua An.
        self.social.like_post(self.binh, bai["post_id"])
        self.social.create_comment(self.binh, bai["post_id"], text="Vẫn được")


class BlockLocBangTinTest(Nen):
    def test_chan_an_bai_khoi_nguoi_da_chan(self):
        self.social.create_post(self.binh, text="Bài của Bình")
        self.social.block_user(self.an, self.binh.user_id)
        ra = self.social.feed_v2(self.an, scope="latest", limit=10)
        self.assertEqual(ra["items"], [])

    def test_bi_chan_cung_bi_an_khoi_nguoi_da_chan_minh(self):
        """Chieu NGUOC: nguoi BI chan cung khong thay bai cua nguoi DA chan
        minh (xem `hidden_authors_for_viewer`)."""
        self.social.create_post(self.an, text="Bài của An")
        self.social.block_user(self.an, self.binh.user_id)
        ra = self.social.feed_v2(self.binh, scope="latest", limit=10)
        self.assertEqual(ra["items"], [])

    def test_tat_tieng_chi_an_mot_chieu(self):
        self.social.create_post(self.an, text="Bài của An")
        self.social.mute_user(self.binh, self.an.user_id)
        # Binh (nguoi tat tieng) khong thay bai cua An.
        self.assertEqual(self.social.feed_v2(self.binh, scope="latest", limit=10)["items"], [])
        # An (nguoi bi tat tieng) VAN thay binh thuong — tat tieng khong anh
        # huong nguoc lai.
        self.assertEqual(len(self.social.feed_v2(self.an, scope="latest", limit=10)["items"]), 1)

    def test_binh_luan_va_xem_truoc_cung_bi_loc(self):
        bai = self.social.create_post(self.an, text="Bài của An")
        self.social.create_comment(self.binh, bai["post_id"], text="Chào")
        self.social.block_user(self.an, self.binh.user_id)
        ket = self.social.comments(bai["post_id"], viewer=self.an)
        self.assertEqual(ket["items"], [])

    def test_khong_can_thong_bao_giua_hai_nguoi_bi_chan(self):
        self.social.follow_user(self.binh, self.an.user_id)
        self.social.block_user(self.an, self.binh.user_id)
        bai = self.social.create_post(self.an, text="Bài sau khi chặn")
        # Khong nem loi va khong tao thong bao follow/post moi cho Binh (da
        # bi go canh theo doi luc chan).
        thong_bao = self.social.notifications(self.binh)
        self.assertEqual(thong_bao["total"], 0)


class MyBlocksTest(Nen):
    def test_danh_sach_chan_va_tat_tieng(self):
        self.social.block_user(self.an, self.binh.user_id)
        self.social.mute_user(self.an, self.cuc.user_id)
        ra = self.social.my_blocks(self.an)
        self.assertEqual([t["user_id"] for t in ra["blocked"]], [self.binh.user_id])
        self.assertEqual([t["user_id"] for t in ra["muted"]], [self.cuc.user_id])
        # The tac gia CONG KHAI — khong lo email.
        self.assertNotIn("email", ra["blocked"][0])


class UserReportTest(Nen):
    def test_bao_cao_nguoi_dung(self):
        ra = self.social.report(self.an, target_kind="user",
                                target_id=self.binh.user_id, reason="harassment")
        self.assertTrue(ra["reported"])

    def test_tu_bao_cao_minh_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.report(self.an, target_kind="user",
                              target_id=self.an.user_id, reason="spam")

    def test_bao_cao_nguoi_dung_bi_tu_choi_khi_tat_nang_luc(self):
        tat = SocialService(self.identity, self.store, self.storage,
                            capabilities={k: False for k in CAPABILITY_KEYS})
        with self.assertRaises(CapabilityDisabled):
            tat.report(self.an, target_kind="user", target_id=self.binh.user_id,
                      reason="spam")


if __name__ == "__main__":
    unittest.main()

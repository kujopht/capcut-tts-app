"""
Social Play V1 — bang tin: pham vi (scope), cursor, loc fandom, tran do sau,
va idempotency cua bai dang/binh luan (`server/social_service.py`).

Chay tren kho MOCK, giong `test_social_service.py`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import Novel, Post, PublishState
from server.social import (
    CAPABILITY_KEYS,
    FEED_MAX_DEPTH,
    CapabilityDisabled,
    SocialError,
    decode_feed_cursor,
    encode_feed_cursor,
)
from server.social_service import SocialService


def _tat_ca_bat() -> dict:
    return {k: True for k in CAPABILITY_KEYS}


def _tat_ca_tat() -> dict:
    return {k: False for k in CAPABILITY_KEYS}


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        self.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.social = SocialService(self.identity, self.store, self.storage,
                                   capabilities=_tat_ca_bat())
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")


class CapabilityGateTest(Nen):
    def test_spoiler_bi_tu_choi_409_khi_tat(self):
        social_tat = SocialService(self.identity, self.store, self.storage,
                                   capabilities=_tat_ca_tat())
        with self.assertRaises(CapabilityDisabled):
            social_tat.create_post(self.an, text="Bí mật", spoiler=True)

    def test_fandom_bi_tu_choi_409_khi_tat(self):
        social_tat = SocialService(self.identity, self.store, self.storage,
                                   capabilities=_tat_ca_tat())
        with self.assertRaises(CapabilityDisabled):
            social_tat.create_post(self.an, text="X", fandom_id="naruto")

    def test_spoiler_va_fandom_hoat_dong_khi_bat(self):
        ra = self.social.create_post(self.an, text="X", spoiler=True,
                                     fandom_id="naruto")
        self.assertTrue(ra["spoiler"])
        self.assertEqual(ra["fandom_id"], "naruto")

    def test_fandom_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="X", fandom_id="khong-ton-tai")


class IdempotentPostTest(Nen):
    def test_cung_client_key_tra_ve_cung_bai_kem_replayed(self):
        a = self.social.create_post(self.an, text="Lần 1", client_key="abc12345")
        self.assertFalse(a["replayed"])
        b = self.social.create_post(self.an, text="Lần 2 (khác hẳn)",
                                    client_key="abc12345")
        self.assertTrue(b["replayed"])
        self.assertEqual(a["post_id"], b["post_id"])
        # Noi dung la cua LAN DAU, khong bi ghi de boi lan goi lai.
        self.assertEqual(b["text"], "Lần 1")
        self.assertEqual(self.store.list_posts(limit=100)[1], 1)

    def test_khac_tac_gia_cung_client_key_khong_va_cham(self):
        a = self.social.create_post(self.an, text="Của An", client_key="xyz98765")
        b = self.social.create_post(self.binh, text="Của Bình", client_key="xyz98765")
        self.assertNotEqual(a["post_id"], b["post_id"])
        self.assertFalse(b["replayed"])

    def test_client_key_sai_dinh_dang_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="X", client_key="ngắn")

    def test_replay_khong_chay_lai_han_muc(self):
        """Bam lai CUNG client_key nhieu lan khong duoc tinh vao han muc dang
        bai — chi lan tao THAT SU moi tinh."""
        han_muc_chat = SocialService(
            self.identity, self.store, self.storage,
            han_muc={"post": __import__("server.social", fromlist=["HanMuc"]).HanMuc(so_lan=1, phut=60)},
            capabilities=_tat_ca_bat())
        han_muc_chat.create_post(self.an, text="Lần 1", client_key="rep00001")
        for _ in range(5):
            ra = han_muc_chat.create_post(self.an, text="Lần 1", client_key="rep00001")
            self.assertTrue(ra["replayed"])


class IdempotentCommentTest(Nen):
    def test_cung_client_key_tra_ve_cung_binh_luan(self):
        bai = self.social.create_post(self.an, text="Bài gốc")
        a = self.social.create_comment(self.binh, bai["post_id"], text="Cmt 1",
                                       client_key="cmtkey01")
        b = self.social.create_comment(self.binh, bai["post_id"], text="Khác",
                                       client_key="cmtkey01")
        self.assertTrue(b["replayed"])
        self.assertEqual(a["comment_id"], b["comment_id"])
        # comment_count CHI tang mot lan.
        lam_moi = self.social.post_detail(bai["post_id"])
        self.assertEqual(lam_moi["comment_count"], 1)


class FeedV2ScopeTest(Nen):
    def test_scope_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.feed_v2(self.an, scope="tuong_lai")

    def test_following_doi_dang_nhap(self):
        from server.adapters import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.social.feed_v2(None, scope="following")

    def test_scope_latest_thay_moi_bai(self):
        self.social.create_post(self.an, text="1")
        self.social.create_post(self.binh, text="2")
        ra = self.social.feed_v2(None, scope="latest", limit=10)
        self.assertEqual(len(ra["items"]), 2)
        self.assertEqual(ra["scope"], "latest")
        self.assertIsNone(ra["next_cursor"])
        self.assertFalse(ra["depth_capped"])

    def test_scope_following_chi_thay_nguoi_dang_theo_doi(self):
        self.social.create_post(self.an, text="của An")
        self.social.create_post(self.binh, text="của Bình")
        self.social.follow_user(self.binh, self.an.user_id)
        ra = self.social.feed_v2(self.binh, scope="following", limit=10)
        self.assertEqual(len(ra["items"]), 1)
        self.assertEqual(ra["items"][0]["author_user_id"], self.an.user_id)

    def test_scope_following_rong_khi_chua_theo_doi_ai(self):
        ra = self.social.feed_v2(self.binh, scope="following", limit=10)
        self.assertEqual(ra["items"], [])
        self.assertIsNone(ra["next_cursor"])


class FeedV2CursorTest(Nen):
    def _them_bai_tho(self, tac_gia, created_at: str) -> Post:
        bai = Post(author_user_id=tac_gia.user_id, text=f"bai-{created_at}",
                  created_at=created_at, updated_at=created_at)
        self.store.create_post(bai)
        return bai

    def test_khong_lap_khong_thieu_khi_trung_created_at(self):
        """Ba bai CUNG mot moc `created_at` (mot cuoc dua that trong mot
        micro giay) — cursor phai phan biet bang `post_id`, khong bo sot
        hay lap lai bai nao qua nhieu trang."""
        moc = "2026-01-01T00:00:00.000000+00:00"
        ds = sorted([self._them_bai_tho(self.an, moc) for _ in range(3)],
                   key=lambda p: p.post_id, reverse=True)

        trang1 = self.social.feed_v2(None, scope="latest", limit=2)
        self.assertEqual(len(trang1["items"]), 2)
        self.assertIsNotNone(trang1["next_cursor"])

        trang2 = self.social.feed_v2(None, scope="latest", limit=2,
                                     cursor=trang1["next_cursor"])
        lay_id = lambda t: [m["post_id"] for m in t["items"]]
        tat_ca = lay_id(trang1) + lay_id(trang2)
        self.assertEqual(sorted(tat_ca), sorted(p.post_id for p in ds))
        self.assertEqual(len(set(tat_ca)), 3)  # khong trung

    def test_cursor_hong_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.feed_v2(None, scope="latest", cursor="###khong-hop-le###")

    def test_encode_decode_cursor_khop_nhau(self):
        ma = encode_feed_cursor("2026-01-01T00:00:00.000000+00:00", "pst_abc123")
        self.assertEqual(decode_feed_cursor(ma),
                        ("2026-01-01T00:00:00.000000+00:00", "pst_abc123"))


class FeedV2DepthCapTest(Nen):
    def test_tran_do_sau_khi_chan_rat_nhieu_nguoi(self):
        """Chan `FEED_MAX_DEPTH + 5` tac gia rieng biet, moi nguoi mot bai —
        vong lap phai DUNG dung luc va bao `depth_capped=True` thay vi quet
        vo han."""
        for i in range(FEED_MAX_DEPTH + 5):
            ho_so = self.identity.register(f"chan{i}@vidu.vn", "MatKhau123",
                                           f"Chặn {i}")
            self.social.create_post(ho_so, text=f"bài {i}")
            self.social.block_user(self.binh, ho_so.user_id)
        # Mot bai KHONG bi chan, nhung nam SAU tat ca bai bi chan trong thu
        # tu thoi gian (tao SAU CUNG -> moi nhat -> len dau) — de dam bao no
        # KHONG bi vuot qua truoc khi tran kich hoat, tao no truoc thay vi
        # sau: dat o DAU danh sach (cu nhat) nen se la MUC CUOI CUNG duoc xet.
        ra = self.social.feed_v2(self.binh, scope="latest", limit=5)
        self.assertEqual(ra["items"], [])
        self.assertTrue(ra["depth_capped"])
        self.assertIsNone(ra["next_cursor"])


class FeedV2FandomTest(Nen):
    def test_loc_theo_fandom_slug_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.feed_v2(None, scope="latest", fandom="khong-ton-tai")

    def test_loc_theo_fandom_id_cua_bai(self):
        self.social.create_post(self.an, text="Naruto", fandom_id="naruto")
        self.social.create_post(self.an, text="One Piece", fandom_id="one-piece")
        ra = self.social.feed_v2(None, scope="latest", fandom="naruto", limit=10)
        self.assertEqual(len(ra["items"]), 1)
        self.assertEqual(ra["items"][0]["fandom_id"], "naruto")

    def test_loc_theo_fandom_cua_truyen_story_update(self):
        truyen = self.store.create_novel(Novel(
            owner_id=self.an.user_id, title="Naruto: Hành Trình Mới",
            state=PublishState.PUBLISHED, fandom_ids=["naruto"]))
        self.an.author_status = __import__(
            "server.domain", fromlist=["AuthorStatus"]).AuthorStatus.APPROVED
        self.identity.save_profile(self.an)
        self.social.create_post(self.an, text="Chương mới!", kind="story_update",
                                novel_id=truyen.novel_id)
        ra = self.social.feed_v2(None, scope="latest", fandom="naruto", limit=10)
        self.assertEqual(len(ra["items"]), 1)
        self.assertEqual(ra["items"][0]["kind"], "story_update")


if __name__ == "__main__":
    unittest.main()

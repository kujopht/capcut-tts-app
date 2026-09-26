"""
Social Play V1 — TRIEN KHAI MA TRUOC MIGRATION: moi nang luc TAT (`FAS_SOCIAL_V1_SCHEMA`
chua bat tren Appwrite) thi ma moi KHONG duoc cham collection `user_blocks` hay cot
`posts.fandom_id` — chung CHUA TON TAI tren production cho toi khi migration duoc duyet.

Neu cham: Appwrite tu choi truy van, va MOI bang tin (ca bang tin cu), theo doi, thich,
binh luan cua moi nguoi da dang nhap hong ngay khi ban deploy len — truoc ca khi ai bat
tinh nang nao. Kho gia duoi day NEM LOI moi khi bi hoi toi cac thu chua ton tai do.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import Novel
from server.social import CAPABILITY_KEYS
from server.social_service import SocialService


class KhoChuaMigrate(MockMetadataStore):
    """Kho mock nhung collection `user_blocks` va cot `fandom_id` 'chua ton tai'."""

    def _chua_co(self, *a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("cham collection user_blocks CHUA TON TAI tren production")

    add_user_block = remove_user_block = list_user_blocks = _chua_co
    is_blocked_either_direction = hidden_authors_for_viewer = _chua_co

    def list_feed_posts(self, **kw):  # type: ignore[override]
        if kw.get("fandom_id"):
            raise AssertionError("truy van cot posts.fandom_id CHUA TON TAI tren production")
        return super().list_feed_posts(**kw)


class TrienKhaiTruocMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.store = KhoChuaMigrate()
        self.social = SocialService(self.identity, self.store,
                                    LocalStorageAdapter(Path(tempfile.mkdtemp())),
                                    capabilities={k: False for k in CAPABILITY_KEYS})
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")

    def test_bang_tin_cu_va_moi_khong_cham_user_blocks(self):
        bai = self.social.create_post(self.binh, text="Chào")
        self.assertEqual(len(self.social.feed(self.an)["items"]), 1)
        self.assertEqual(len(self.social.feed_v2(self.an, scope="latest")["items"]), 1)
        self.assertEqual(self.social.post_detail(bai["post_id"], self.an)["post_id"], bai["post_id"])
        self.social.search_posts("Chào", viewer=self.an)

    def test_theo_doi_thich_binh_luan_khong_cham_user_blocks(self):
        bai = self.social.create_post(self.binh, text="Chào")
        self.social.follow_user(self.an, self.binh.user_id)
        self.social.like_post(self.an, bai["post_id"])
        cm = self.social.create_comment(self.an, bai["post_id"], text="Hay quá")
        self.social.comments(bai["post_id"], viewer=self.binh)
        self.social.replies(cm["comment_id"], viewer=self.binh)
        self.assertEqual(len(self.social.feed_v2(self.an, scope="following")["items"]), 1)

    def test_ho_so_cong_khai_khong_cham_user_blocks(self):
        self.social.profile_social(self.binh, viewer=self.an)

    def test_loc_fandom_chi_theo_truyen_khi_post_fandom_tat(self):
        truyen = self.store.create_novel(Novel(owner_id=self.binh.user_id, title="T",
                                               fandom_ids=[], tags=["fandom:Naruto"]))
        self.store.publish_novel(truyen.novel_id, self.binh.user_id)
        self.social.create_post(self.binh, text="Không fandom")
        ra = self.social.feed_v2(self.an, scope="latest", fandom="naruto")
        # Khong bao gio roi ve "tat ca bai": bai khong gan truyen fandom do khong duoc hien.
        self.assertEqual(ra["items"], [])
        self.assertEqual(ra["fandom"], "naruto")


if __name__ == "__main__":
    unittest.main()

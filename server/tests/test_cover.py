"""
Truong anh bia trong phan hoi API.

Hai dieu quan trong nhat:
- CHI THEM truong, khong doi ten va khong bo truong nao -> client cu van chay;
- khong co bia thi tra `null`, KHONG bao gio bia ra mot URL anh gia.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore

#: PNG 1x1 diem anh hop le — anh dung thu nho nhat co the, dung o nhieu test.
PNG_1X1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
          "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class SignedStorage(LocalStorageAdapter):
    """Gia lap kho co URL ky (nhu R2)."""

    mode = "r2"

    def signed_url(self, key, expires_seconds=3600, download_name=None):
        return f"https://khong-co-that.example/{key}?X-Amz-Signature=gia-lap"


class CoverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post("/api/novels", json={"title": title},
                                headers=self.auth(token)).json()["novel"]["novel_id"]

    def chapter(self, token: str, novel_id: str) -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C1", "content": "Nội dung."},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def set_cover(self, novel_id: str, key: Optional[str]) -> None:
        """Dat `cover_key` thang qua kho — chua co duong upload bia."""
        from dataclasses import replace

        store = server_main.store
        store.novels[novel_id] = replace(store.novels[novel_id], cover_key=key)


# ============================================================ novel


class TestNovelCoverField(CoverTestCase):
    def test_novel_response_has_cover_url(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIn("cover_url", body)

    def test_no_cover_means_null_not_a_fake_image(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIsNone(body["cover_url"])
        self.assertIsNone(body["cover_key"])

    def test_cover_url_is_signed_when_storage_can_sign(self):
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        token = self.user()
        novel_id = self.novel(token)
        self.set_cover(novel_id, "covers/abc.jpg")

        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIn("X-Amz-Signature", body["cover_url"])
        self.assertIn("covers/abc.jpg", body["cover_url"])

    def test_local_storage_without_signing_returns_null(self):
        """Kho khong ky duoc thi tra null — giao dien dung anh du phong."""
        token = self.user()
        novel_id = self.novel(token)
        self.set_cover(novel_id, "covers/abc.jpg")
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIsNone(body["cover_url"])
        self.assertEqual(body["cover_key"], "covers/abc.jpg")

    def test_cover_url_present_in_every_novel_response(self):
        token = self.user()
        novel_id = self.novel(token)
        self.chapter(token, novel_id)

        places = {
            "tao moi": self.client.post("/api/novels", json={"title": "T2"},
                                        headers=self.auth(token)).json()["novel"],
            "chi tiet": self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"],
            "danh sach cua toi":
                self.client.get("/api/novels?mine=true",
                                headers=self.auth(token)).json()["novels"][0],
            "sua": self.client.patch(f"/api/novels/{novel_id}", json={"title": "T3"},
                                     headers=self.auth(token)).json()["novel"],
            "xuat ban": self.client.post(f"/api/novels/{novel_id}/publish",
                                         headers=self.auth(token)).json()["novel"],
            "go xuat ban": self.client.post(f"/api/novels/{novel_id}/unpublish",
                                            headers=self.auth(token)).json()["novel"],
        }
        for where, body in places.items():
            self.assertIn("cover_url", body, f"{where}: thiếu cover_url")

        published = self.client.post(f"/api/novels/{novel_id}/publish",
                                     headers=self.auth(token))
        self.assertIn("cover_url", self.client.get("/api/novels").json()["novels"][0])
        self.assertEqual(published.status_code, 200)


class TestBackwardCompatible(CoverTestCase):
    """CHI THEM truong. Client cu doc cac truong cu phai khong doi gi."""

    OLD_NOVEL_FIELDS = {
        "novel_id", "owner_id", "title", "description", "cover_key",
        "state", "tags", "created_at", "updated_at",
    }

    def test_no_old_novel_field_was_removed_or_renamed(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        missing = self.OLD_NOVEL_FIELDS - set(body)
        self.assertEqual(missing, set(), f"mất trường cũ: {missing}")

    #: Anime Fanfic Production Canary: them fandom + provenance nguon ngoai
    #: len `Novel` (`domain.py`) — CO CHU Y ghi ro o day, khong am tham noi
    #: rong `OLD_NOVEL_FIELDS`, de lan them truong SAU nay van bi bat neu
    #: khong duoc xac nhan tuong tu.
    NEW_FANDOM_FIELDS = {
        "publication_mode", "fandom_ids", "external_author_name",
        "external_source_url", "external_chapter_count",
        "external_updated_at", "language",
    }
    NEW_TAXONOMY_FIELDS = {
        "characters", "pairings", "status",
    }
    #: Mission "SHIP 3 CHINESE AI-ANIMATION VIDEO DRAFTS" (2026-09-01):
    #: reuses Novel/METADATA_ONLY for video drafts instead of a new
    #: collection — see Novel's own docstring. Same explicit-confirmation
    #: discipline as the two sets above.
    NEW_VIDEO_DRAFT_FIELDS = {
        "platform", "rights_mode", "subtitle_status", "embed_ref",
    }

    def test_only_cover_url_was_added(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertEqual(
            set(body) - self.OLD_NOVEL_FIELDS,
            {"cover_url"} | self.NEW_FANDOM_FIELDS | self.NEW_TAXONOMY_FIELDS
            | self.NEW_VIDEO_DRAFT_FIELDS)

    def test_chapter_response_keeps_its_old_shape(self):
        token = self.user()
        chapter_id = self.chapter(token, self.novel(token))
        body = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()
        self.assertIn("chapter", body)
        self.assertIn("audio", body)          # van con, du la None
        self.assertEqual(set(body) - {"chapter", "audio"},
                         {"novel", "audio_outdated"})

    def test_cover_field_is_not_persisted_as_an_unknown_attribute(self):
        """`cover_url` la truong tinh — khong duoc gui len Appwrite."""
        from server.appwrite_store import PERSISTED_FIELDS, COL_NOVELS, persistable

        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertNotIn("cover_url", PERSISTED_FIELDS[COL_NOVELS])
        self.assertNotIn("cover_url", persistable(COL_NOVELS, body))


# ============================================================ chapter


class TestChapterCarriesItsNovel(CoverTestCase):
    """Luong nghe can bia va ten truyen ngay trong phan hoi cua chuong."""

    def test_chapter_response_includes_its_novel(self):
        token = self.user()
        novel_id = self.novel(token, "Hải Tặc Mũ Rơm")
        chapter_id = self.chapter(token, novel_id)

        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertEqual(novel["novel_id"], novel_id)
        self.assertEqual(novel["title"], "Hải Tặc Mũ Rơm")
        self.assertEqual(novel["state"], "draft")
        self.assertIn("cover_url", novel)
        self.assertIn("cover_key", novel)

    def test_chapter_novel_carries_the_signed_cover(self):
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.set_cover(novel_id, "covers/bia.png")

        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertIn("covers/bia.png", novel["cover_url"])

    def test_chapter_novel_is_a_summary_not_the_whole_record(self):
        """Chi vua du: khong ro ri `owner_id` hay mo ta dai."""
        token = self.user()
        chapter_id = self.chapter(token, self.novel(token))
        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertEqual(
            set(novel), {"novel_id", "title", "state", "cover_key", "cover_url"}
        )
        self.assertNotIn("owner_id", novel)

    def test_missing_parent_novel_does_not_break_the_chapter(self):
        """
        Mat truyen cha thi chuong van tra ve duoc, `novel` la None.

        Goi bang token cua CHU SO HUU: khong co truyen cha thi khong xac minh
        duoc trang thai xuat ban, nen route chi cho chu so huu doc. Phan quyen
        do co bo test rieng o `test_chapter_list_batching.py`.
        """
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        server_main.store.novels.pop(novel_id)      # mo phong du lieu le loi

        body = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token))
        self.assertEqual(body.status_code, 200)
        self.assertIsNone(body.json()["novel"])
        self.assertIsNotNone(body.json()["chapter"])

    def test_publishing_is_reflected_in_the_chapter_response(self):
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]["state"],
            "published",
        )


class TestNoFakeCover(CoverTestCase):
    """Backend khong bao gio tu bia ra mot duong dan anh."""

    def test_cover_url_never_invented_from_thin_air(self):
        import inspect

        source = inspect.getsource(server_main._cover_url)
        self.assertIn("if not novel.cover_key", source)
        self.assertIn("return None", source)
        # Khong co chuoi URL nao duoc viet cung trong ham
        self.assertNotIn("http", source.split('"""')[-1])


class TestNovelCoverUpload(CoverTestCase):
    """
    Duong TAI anh bia that (V4 Phase 5) — trai voi `set_cover()` cua
    `CoverTestCase`, vong qua thang kho de dung khi cac test kia CHI can doc
    `cover_url`. O day ta kiem CHINH duong ghi.
    """

    def test_tai_len_dat_cover_key_va_luu_object(self):
        token = self.user()
        novel_id = self.novel(token)
        r = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png",
                                  "width": 1, "height": 1})
        self.assertEqual(r.status_code, 200, r.text)
        khoa = r.json()["novel"]["cover_key"]
        self.assertTrue(khoa)
        self.assertTrue(khoa.startswith("covers/"))
        self.assertTrue(server_main.storage._path(khoa).is_file())

    def test_khoa_doi_tuong_tat_dinh_theo_chu_va_truyen_khong_co_email(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        r = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png"})
        khoa = r.json()["novel"]["cover_key"]
        self.assertNotIn("@", khoa)
        self.assertNotIn("example.com", khoa)
        self.assertIn(novel_id, khoa)

    def test_nguoi_khong_so_huu_bi_tu_choi_403(self):
        chu_token = self.user("chu@example.com")
        novel_id = self.novel(chu_token)
        ke_khac = self.user("khac@example.com")
        r = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(ke_khac),
                            json={"base64": PNG_1X1, "mime": "image/png"})
        self.assertEqual(r.status_code, 403)

    def test_truyen_khong_ton_tai_tra_404(self):
        token = self.user()
        r = self.client.put("/api/novels/khong-ton-tai/cover", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png"})
        self.assertEqual(r.status_code, 404)

    def test_dinh_dang_khong_hop_le_bi_tu_choi_400(self):
        token = self.user()
        novel_id = self.novel(token)
        r = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "application/pdf"})
        self.assertEqual(r.status_code, 400)
        # Kiem TRUOC khi cham kho: khong co object rac nao duoc tao.
        self.assertEqual(server_main.store.novels[novel_id].cover_key, None)

    def test_base64_hong_tra_400_khong_phai_500(self):
        token = self.user()
        novel_id = self.novel(token)
        r = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                            json={"base64": "***khong-phai-base64***",
                                  "mime": "image/png"})
        self.assertEqual(r.status_code, 400)

    def test_thay_bia_moi_xoa_object_cu_khi_doi_duoi(self):
        """
        Khoa tat dinh theo (chu, truyen) nhung DUOI co the doi giua cac lan
        tai (vd .jpg -> .png) — anh cu voi duoi khac phai duoc xoa, khong thi
        no mo coi vinh vien trong kho.
        """
        token = self.user()
        novel_id = self.novel(token)
        r1 = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                             json={"base64": PNG_1X1, "mime": "image/jpeg"})
        khoa_cu = r1.json()["novel"]["cover_key"]
        self.assertTrue(server_main.storage._path(khoa_cu).is_file())

        r2 = self.client.put(f"/api/novels/{novel_id}/cover", headers=self.auth(token),
                             json={"base64": PNG_1X1, "mime": "image/png"})
        khoa_moi = r2.json()["novel"]["cover_key"]
        self.assertNotEqual(khoa_cu, khoa_moi)
        self.assertFalse(server_main.storage._path(khoa_cu).is_file(),
                         "anh bia cũ (đuôi khác) phải bị xoá sau khi thay")
        self.assertTrue(server_main.storage._path(khoa_moi).is_file())

    def test_go_bia_xoa_ca_khoa_lan_object(self):
        token = self.user()
        novel_id = self.novel(token)
        khoa = self.client.put(
            f"/api/novels/{novel_id}/cover", headers=self.auth(token),
            json={"base64": PNG_1X1, "mime": "image/png"},
        ).json()["novel"]["cover_key"]

        r = self.client.delete(f"/api/novels/{novel_id}/cover", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["novel"]["cover_key"])
        self.assertFalse(server_main.storage._path(khoa).is_file())

    def test_go_bia_khi_chua_co_bia_khong_loi(self):
        """Idempotent: bam Xoá khi chưa từng có bìa không được nem lỗi."""
        token = self.user()
        novel_id = self.novel(token)
        r = self.client.delete(f"/api/novels/{novel_id}/cover", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["novel"]["cover_key"])

    def test_go_bia_khong_phai_chu_bi_tu_choi_403(self):
        chu_token = self.user("chu@example.com")
        novel_id = self.novel(chu_token)
        ke_khac = self.user("khac@example.com")
        r = self.client.delete(f"/api/novels/{novel_id}/cover", headers=self.auth(ke_khac))
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)

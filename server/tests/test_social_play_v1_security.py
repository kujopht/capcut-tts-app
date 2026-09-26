"""
Social Play V1 — cac diem gia co sau review bao mat CHEO HO (Antigravity Claude Opus):

  * `LocalStorageAdapter._path` tu choi khoa TUYET DOI (Windows: `root / "C:/x"` bo qua root);
  * `update_profile` HOAN TAC doi tuong Profile trong bo nho khi ghi ho so hong;
  * `capabilities` thieu khoa nao thi khoa do la TAT (khong "bat" roi doc collection chua ton tai).
"""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.social import CAPABILITY_KEYS
from server.social_service import SocialService


def _png_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 200, 90)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class DuongDanTuyetDoiTest(unittest.TestCase):
    def test_khoa_tuyet_doi_va_unc_bi_tu_choi(self):
        goc = Path(tempfile.mkdtemp())
        kho = LocalStorageAdapter(goc)
        for khoa in ("C:/Windows/win.ini", "C:\\Windows\\win.ini", "a/../../b"):
            with self.assertRaises(ValueError, msg=khoa):
                kho._path(khoa)
        # "//host/share/x" bi `lstrip("/")` bien thanh duong TUONG DOI -> van nam trong goc.
        self.assertIn(goc.resolve(), kho._path("//host/share/x").resolve().parents)
        # Khoa binh thuong van dung.
        self.assertTrue(str(kho._path("avatars/usr_1/ab.webp")).endswith("ab.webp"))


class IdentityGhiHong(MockIdentityAdapter):
    def save_profile(self, profile):  # noqa: ANN001
        raise RuntimeError("Appwrite het thoi gian")


class HoanTacProfileTest(unittest.TestCase):
    def test_ghi_ho_so_hong_thi_profile_trong_bo_nho_duoc_hoan_tac_va_anh_moi_bi_don(self):
        identity = IdentityGhiHong()
        kho_anh = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        social = SocialService(identity, MockMetadataStore(), kho_anh,
                               capabilities={k: True for k in CAPABILITY_KEYS})
        an = identity.register("an@vidu.vn", "MatKhau123", "An")
        truoc = (an.bio, list(an.fandom_ids or []), an.accent, an.avatar_key, an.banner_key)
        with self.assertRaises(RuntimeError):
            social.update_profile(an, bio="Bio moi", accent="jade", fandom_ids=["naruto"],
                                  avatar={"data": _png_b64(), "mime": "image/png"})
        sau = (an.bio, list(an.fandom_ids or []), an.accent, an.avatar_key, an.banner_key)
        self.assertEqual(sau, truoc)
        self.assertEqual(list(kho_anh.list_objects("avatars/")), [], "anh moi phai bi don")


class CapabilityThieuKhoaTest(unittest.TestCase):
    def test_thieu_khoa_la_tat(self):
        social = SocialService(MockIdentityAdapter(), MockMetadataStore(),
                               LocalStorageAdapter(Path(tempfile.mkdtemp())),
                               capabilities={"post_spoiler": True})
        self.assertTrue(social._cap["post_spoiler"])
        self.assertFalse(social._cap["blocks"])
        self.assertEqual(set(social._cap), set(CAPABILITY_KEYS))


if __name__ == "__main__":
    unittest.main()

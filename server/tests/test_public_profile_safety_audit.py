"""
Overnight Phase 1B — kiem toan an toan trang cong khai `/api/users/{username}`.

KHAC voi `test_public_profile_gamification.py` (chi kiem phan gamification):
bai nay quet DE QUY toan bo response — profile + social + gamification cong
lai — de bat truong hop MOT truong moi duoc them vao BAT KY mapper nao trong
tuong lai ma vo tinh lo du lieu rieng tu. Danh sach cam duoi day PHAI khop voi
loi hua trong docstring `creator.public_profile()`: "KHONG bao gio ra ngoai:
email, tier, quota da dung, va trang thai duyet."
"""

from __future__ import annotations

import unittest
from typing import Any, Iterable

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import Chapter, Novel, PublishState
from server.gamification_store import MockGamificationStore

#: Khoa KHONG duoc phep xuat hien o BAT KY dau trong response — dai dien cho
#: du lieu rieng tu/noi bo theo dung liet ke trong dac ta overnight Phan 1B.
_KHOA_CAM = {
    "email", "tier", "tts_characters_used", "listened_minutes",
    "author_status", "avatar_key", "api_key", "encrypted_secret",
    "moderation", "pending_reward_packs", "xp", "next_level_xp",
    "current_level_xp", "progress_percent", "goi_thuong_dang_cho",
    "last_read_novel_id", "last_read_chapter_id", "last_listen_novel_id",
    "last_listen_chapter_id", "last_listen_position_seconds",
    "google_id", "facebook_id", "password", "password_hash", "secret",
}


def _quet_khoa_cam(node: Any, duong_dan: str = "$") -> Iterable[str]:
    """Sinh ra danh sach `duong_dan` cho MOI khoa cam tim thay, de loi bao
    kiem duoc dung cho nao trong cay JSON thay vi chi noi "co gi do sai"."""
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in _KHOA_CAM:
                yield f"{duong_dan}.{k}"
            yield from _quet_khoa_cam(v, f"{duong_dan}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _quet_khoa_cam(v, f"{duong_dan}[{i}]")


class PublicProfileSafetyAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        self.client = TestClient(server_main.app)

    def _tao_nguoi_dung_that(self) -> str:
        resp = self.client.post("/api/auth/register", json={
            "email": "audit-1b@example.com", "password": "MatKhauManh123!",
            "display_name": "Kiểm Toán An Toàn",
        })
        tok = resp.json()["token"]
        self.client.put("/api/creator/username",
                        headers={"Authorization": f"Bearer {tok}"},
                        json={"username": "kiemtoan1b"})
        return tok

    def test_khong_lo_khoa_cam_o_bat_ky_dau_trong_response(self):
        tok = self._tao_nguoi_dung_that()
        # Xuat ban that mot truyen + chuong de kich hoat toi da cac nhanh du
        # lieu (thanh tuu, gamification, social, novels) trong MOT lan quet.
        novel = self.client.post(
            "/api/novels", headers={"Authorization": f"Bearer {tok}"},
            json={"title": "Truyện Kiểm Toán", "description": "x",
                  "tags": ["qa"]}).json()["novel"]
        self.client.post(
            "/api/chapters", headers={"Authorization": f"Bearer {tok}"},
            json={"novel_id": novel["novel_id"], "title": "C1",
                  "content": "Nội dung kiểm toán."})
        self.client.post(f"/api/novels/{novel['novel_id']}/publish",
                         headers={"Authorization": f"Bearer {tok}"})

        resp = self.client.get("/api/users/kiemtoan1b")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        vi_pham = list(_quet_khoa_cam(body))
        self.assertEqual(vi_pham, [],
                         f"Response /api/users/{{username}} lộ khoá riêng tư: {vi_pham}")

        # Xac nhan gia tri EMAIL that su (khong chi ten khoa) khong xuat hien
        # o bat ky dau trong body — phong truong hop mot mapper doi ten khoa
        # nhung van nhet gia tri email vao mot truong khac.
        self.assertNotIn("audit-1b@example.com", str(body))

    def test_nguoi_xem_khach_van_khong_lo_gi_them(self):
        self._tao_nguoi_dung_that()
        # KHONG kem Authorization — nguoi xem la khach vang lai.
        resp = self.client.get("/api/users/kiemtoan1b")
        self.assertEqual(resp.status_code, 200)
        vi_pham = list(_quet_khoa_cam(resp.json()))
        self.assertEqual(vi_pham, [])


if __name__ == "__main__":
    unittest.main()

"""ship_draft() idempotency — the real fix for the disclosed duplicate
Appwrite `Novel` document this mission hit in production.

Before this fix, `ship_draft()` unconditionally POSTed a brand new Novel
even when a placeholder for the exact same `external_source_url` already
existed (e.g. created earlier by `ship_video_drafts_runner.py` with
`subtitle_status=PENDING_SOURCE`). These tests mock `goi()` — same mocking
convention as `test_chinese_media_dub_fix.py` in this same neighborhood,
i.e. `mock.patch.object(cmp, ...)` on the module-level name — to verify:

- an existing novel found by `external_source_url` -> PATCH
  .../media-processing is called, POST /api/novels is NOT called;
- no existing novel found -> POST /api/novels is called exactly as before,
  PATCH .../media-processing is NOT called.

No real HTTP, no real R2 upload: `goi` and `upload_to_r2` are both mocked.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chinese_media_pipeline as cmp  # noqa: E402


SOURCE_URL = "https://www.youtube.com/watch?v=existing123"


def _fake_goi_with_existing(calls):
    def fake_goi(api, method, path, payload=None, token=None, timeout=60):
        calls.append((method, path, payload))
        if method == "GET" and path.startswith("/api/novels?mine=true"):
            return 200, {"novels": [
                {"novel_id": "nov_existing", "external_source_url": SOURCE_URL,
                 "subtitle_status": "PENDING_SOURCE"},
            ]}
        if method == "PATCH" and path == "/api/novels/nov_existing/media-processing":
            return 200, {"novel": {"novel_id": "nov_existing", **(payload or {})}}
        raise AssertionError(f"unexpected goi() call: {method} {path}")
    return fake_goi


def _fake_goi_without_existing(calls):
    def fake_goi(api, method, path, payload=None, token=None, timeout=60):
        calls.append((method, path, payload))
        if method == "GET" and path.startswith("/api/novels?mine=true"):
            return 200, {"novels": []}
        if method == "POST" and path == "/api/novels":
            return 201, {"novel": {"novel_id": "nov_new", **(payload or {})}}
        raise AssertionError(f"unexpected goi() call: {method} {path}")
    return fake_goi


class ShipDraftIdempotencyTest(unittest.TestCase):
    def _run_ship_draft(self, fake_goi):
        calls: list = []
        with mock.patch.object(cmp, "goi", side_effect=fake_goi(calls)), \
             mock.patch.object(cmp, "upload_to_r2"):
            novel_id = cmp.ship_draft(
                title="Tieu de", source_url=SOURCE_URL, author="tac gia",
                rights_mode="REFERENCE_ONLY", platform="youtube", embed_ref="existing123",
                srt_bytes=b"1\n00:00:00,000 --> 00:00:01,000\nxin chao\n",
                dub_bytes=None, token="fake-token",
            )
        return novel_id, calls

    def test_novel_da_ton_tai_thi_goi_patch_khong_goi_post(self):
        novel_id, calls = self._run_ship_draft(_fake_goi_with_existing)

        self.assertEqual(novel_id, "nov_existing")
        methods_paths = [(m, p) for m, p, _ in calls]
        self.assertIn(("PATCH", "/api/novels/nov_existing/media-processing"), methods_paths)
        self.assertNotIn(("POST", "/api/novels"), methods_paths)

        patch_call = next(c for c in calls if c[0] == "PATCH")
        payload = patch_call[2]
        self.assertEqual(payload["subtitle_status"], "READY")
        self.assertIn("subtitle_key", payload)
        self.assertIn("dub_audio_key", payload)

    def test_khong_co_novel_cu_thi_goi_post_nhu_truoc(self):
        novel_id, calls = self._run_ship_draft(_fake_goi_without_existing)

        self.assertEqual(novel_id, "nov_new")
        methods_paths = [(m, p) for m, p, _ in calls]
        self.assertIn(("POST", "/api/novels"), methods_paths)
        self.assertFalse(any(m == "PATCH" for m, _, _ in calls))

        post_call = next(c for c in calls if c[0] == "POST")
        payload = post_call[2]
        self.assertEqual(payload["external_source_url"], SOURCE_URL)
        self.assertEqual(payload["subtitle_status"], "READY")


class ShipDraftKeyTest(unittest.TestCase):
    """Khoa R2 cua phu de/dub (2026-09-07).

    Hai loi that o day, ca hai deu KHONG bi bat boi cac bai tren vi chung
    khong he nhin vao khoa duoc dung de tai len:

    1. `subtitle_key.replace("/subtitles/", "/dub_audio/")` — khoa KHONG co
       dau "/" o dau, nen phep thay the khong bao gio khop va ban dub bi ghi
       vao chinh tien to `subtitles/`.
    2. Khoa mac dinh chua `os.urandom(4)`, nen moi lan chay lai bo lai mot
       object mo coi. `chinese_media_orchestrator.py` truyen khoa tat dinh de
       tranh dieu do; duong mac dinh giu nguyen hanh vi cu.
    """

    def _upload_keys(self, **kwargs):
        kwargs.setdefault("dub_bytes", None)
        uploads: list = []
        with mock.patch.object(cmp, "goi", side_effect=_fake_goi_without_existing([])), \
             mock.patch.object(cmp, "upload_to_r2",
                               side_effect=lambda k, d, c: uploads.append((k, c))):
            cmp.ship_draft(
                title="Tieu de", source_url=SOURCE_URL, author="tac gia",
                rights_mode="REFERENCE_ONLY", platform="youtube",
                embed_ref="existing123", srt_bytes=b"srt", token="fake-token",
                **kwargs,
            )
        return uploads

    def test_dub_khong_bao_gio_bi_ghi_vao_tien_to_subtitles(self):
        uploads = self._upload_keys(dub_bytes=b"mp3")
        dub_uploads = [(k, c) for k, c in uploads if c == "audio/mpeg"]

        self.assertEqual(len(dub_uploads), 1)
        dub_k = dub_uploads[0][0]
        self.assertTrue(dub_k.startswith("dub_audio/"),
                        f"dub phai nam duoi dub_audio/, dang o: {dub_k}")
        self.assertFalse(dub_k.startswith("subtitles/"))
        self.assertTrue(dub_k.endswith(".mp3"))

    def test_khoa_tuong_minh_duoc_dung_nguyen_van(self):
        uploads = self._upload_keys(
            dub_bytes=b"mp3",
            subtitle_key="subtitles/svc_harvester/cmq_abc.srt",
            dub_key="dub_audio/svc_harvester/cmq_abc.mp3",
        )
        self.assertEqual(sorted(k for k, _ in uploads),
                         ["dub_audio/svc_harvester/cmq_abc.mp3",
                          "subtitles/svc_harvester/cmq_abc.srt"])

    def test_khoa_tuong_minh_lap_lai_y_het_qua_nhieu_lan_chay(self):
        first = self._upload_keys(subtitle_key="subtitles/svc_harvester/cmq_abc.srt")
        second = self._upload_keys(subtitle_key="subtitles/svc_harvester/cmq_abc.srt")
        self.assertEqual(first, second)

    def test_khoa_mac_dinh_giu_nguyen_hanh_vi_cu(self):
        uploads = self._upload_keys()
        self.assertEqual(len(uploads), 1)
        key, content_type = uploads[0]
        self.assertTrue(key.startswith("subtitles/svc_harvester/"))
        self.assertTrue(key.endswith(".srt"))
        self.assertEqual(content_type, "text/srt")

    def test_khong_co_dub_thi_khong_tai_len_gi_ngoai_phu_de(self):
        uploads = self._upload_keys(dub_bytes=None)
        self.assertEqual([c for _, c in uploads], ["text/srt"])


if __name__ == "__main__":
    unittest.main()

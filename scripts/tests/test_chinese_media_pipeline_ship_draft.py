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


if __name__ == "__main__":
    unittest.main()

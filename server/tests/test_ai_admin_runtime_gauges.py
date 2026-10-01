"""
`/api/admin/ai/overview` -> `runtime`: những thứ Owner cần thấy khi chẩn đoán mà không nằm trong kho cấu hình — khán giả đang
áp (`FAS_AI_AUDIENCE`), RPM/người, và SỐ LUỒNG SSE ĐANG CHẠY trên instance (trần `FAS_AI_MAX_STREAMS`; chạm trần = người dùng
nhận 503 `ai_busy`). Chỉ số đo thôi: không ID người dùng, không khoá, không danh sách.
"""
from __future__ import annotations

import json
import time
import unittest
from dataclasses import replace

import httpx

from server.ai_assistant.runtime import build_ai_runtime
from server.config import AiAssistantSettings, Settings
from server.tests.test_ai_admin_api import make_plane
from server.tests.test_ai_control_plane import slot
from server.tests.test_ai_e2e_regression import World, _LiveServer

OWNER = {"Authorization": "Bearer owner"}


class TestOverviewRuntimeGauges(unittest.TestCase):
    def test_reports_audience_rpm_and_the_live_stream_count(self) -> None:
        w = World(slots=1)  # audience=all, rpm=1000, max_streams=8
        ov = w.c.get("/api/admin/ai/overview", headers=OWNER).json()
        self.assertEqual(ov["runtime"], {"audience": "all", "rpm_per_user": 1000, "streams_active": 0, "streams_max": 8})
        w.rt.stream_guard.acquire("u1")
        w.rt.stream_guard.acquire("u2")
        self.assertEqual(w.c.get("/api/admin/ai/overview", headers=OWNER).json()["runtime"]["streams_active"], 2)
        w.rt.stream_guard.release("u1")
        self.assertEqual(w.c.get("/api/admin/ai/overview", headers=OWNER).json()["runtime"]["streams_active"], 1)

    def test_a_reader_admin_sees_it_too_but_a_normal_user_cannot_read_the_overview(self) -> None:
        w = World(slots=1)
        self.assertIn("runtime", w.c.get("/api/admin/ai/overview", headers={"Authorization": "Bearer admin"}).json())
        self.assertEqual(w.c.get("/api/admin/ai/overview", headers={"Authorization": "Bearer user"}).status_code, 403)
        self.assertEqual(w.c.get("/api/admin/ai/overview").status_code, 401)

    def test_no_user_ids_or_lists_leak_into_the_overview_for_a_beta_audience(self) -> None:
        plane = make_plane([slot("gemini-01")])
        ai = AiAssistantSettings(enabled=True, providers=("mock",), audience="beta",
                                 beta_users=("tester_01", "tester_02"), canary_users=("canary_01",))
        settings = replace(Settings(), owner_user_ids=("user_owner",), ai_assistant=ai)
        build_ai_runtime(settings, control=plane)
        ov = plane.overview()
        self.assertEqual(ov["runtime"]["audience"], "beta")
        blob = json.dumps(ov)
        for secret in ("tester_01", "tester_02", "canary_01", "user_owner"):
            self.assertNotIn(secret, blob)
        self.assertEqual(set(ov["runtime"]), {"audience", "rpm_per_user", "streams_active", "streams_max"})

    def test_is_null_when_no_runtime_is_attached(self) -> None:
        self.assertIsNone(make_plane([slot("gemini-01")]).overview()["runtime"])

    def test_a_failing_callback_never_breaks_the_overview(self) -> None:
        plane = make_plane([slot("gemini-01")])

        def boom() -> dict:
            raise RuntimeError("lỗi đo")

        plane.attach_usage_sources(runtime_info_fn=boom)
        ov = plane.overview()
        self.assertIsNone(ov["runtime"])
        self.assertIn("requests", ov)

    def test_the_gauge_follows_a_real_streaming_turn_and_returns_to_zero(self) -> None:
        w = World(slots=1, delay=0.25, words=12)
        live = _LiveServer(w.app)
        try:
            tok = "gauge"
            cid = httpx.post(f"{live.base}/api/ai/conversations", headers=w.hdr(tok), json={"mode": "general"}, timeout=10).json()["conversation_id"]
            seen = []

            def poll() -> None:
                end = time.time() + 6
                while time.time() < end:
                    seen.append(w.c.get("/api/admin/ai/overview", headers=OWNER).json()["runtime"]["streams_active"])
                    time.sleep(0.1)

            import threading
            t = threading.Thread(target=poll, daemon=True)
            t.start()
            r = httpx.post(f"{live.base}/api/ai/conversations/{cid}/messages", headers=w.hdr(tok),
                           json={"content": "đo luồng", "client_id": "g1"}, timeout=20)
            self.assertEqual(r.status_code, 200)
            t.join()
            self.assertIn(1, seen, "trong lúc stream, đồng hồ đo phải là 1")
            self.assertEqual(seen[-1], 0, "sau khi xong, về 0")
        finally:
            live.close()


if __name__ == "__main__":
    unittest.main()

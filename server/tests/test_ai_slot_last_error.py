"""
Phan loai loi provider da lam sach trong health tung slot (`last_error_code`,
`last_error_category`, `last_error_at`). Khong bao gio luu thong diep/than phan
hoi cua nha cung cap. Khoa gia dung luc chay (quy uoc gitleaks cua kho).
"""
from __future__ import annotations

import json
import unittest

import httpx

from server.ai_assistant.control.router import ControlledGateway
from server.llm_gateway.chat_provider import ChatTurn, GenerateRequest, ProviderError
from server.llm_gateway.chat_providers import ERROR_BODY_PEEK_BYTES, OpenAICompatChatProvider, error_category
from server.tests.test_ai_control_plane import Clock, Scripted, plane_with, run, slot

FAKE_KEY = "AQ." + "lasterror" * 5 + "Xy"


def _google(status: str, code: int, *, reason: str = "", message: str = "", wrap: bool = True) -> bytes:
    err = {"error": {"code": code, "message": message or f"models/x is not found ({FAKE_KEY})", "status": status}}
    if reason:
        err["error"]["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason,
                                    "metadata": {"consumer": "projects/123456789", "key": FAKE_KEY}}]
    return json.dumps([err] if wrap else err).encode()


class TestErrorCategory(unittest.TestCase):
    def test_google_status_from_list_wrapped_body(self) -> None:
        self.assertEqual(error_category(_google("NOT_FOUND", 404)), "NOT_FOUND")

    def test_google_status_with_error_info_reason(self) -> None:
        self.assertEqual(error_category(_google("PERMISSION_DENIED", 403, reason="SERVICE_DISABLED")),
                         "PERMISSION_DENIED:SERVICE_DISABLED")

    def test_reason_with_digits_or_lowercase_is_dropped(self) -> None:
        self.assertEqual(error_category(_google("PERMISSION_DENIED", 403, reason="projects/123")), "PERMISSION_DENIED")
        self.assertEqual(error_category(_google("PERMISSION_DENIED", 403, reason=FAKE_KEY)), "PERMISSION_DENIED")

    def test_unknown_status_is_dropped(self) -> None:
        self.assertIsNone(error_category(_google("SECRET_LEAK_" + "A" * 5, 400)))

    def test_openai_shapes(self) -> None:
        body = json.dumps({"error": {"message": f"bad {FAKE_KEY}", "type": "invalid_request_error",
                                     "code": "model_not_found"}}).encode()
        self.assertEqual(error_category(body), "model_not_found")
        self.assertIsNone(error_category(json.dumps({"error": {"code": FAKE_KEY}}).encode()))

    def test_never_returns_message_key_or_project(self) -> None:
        for raw in (_google("NOT_FOUND", 404, reason="API_KEY_INVALID"), _google("INVALID_ARGUMENT", 400, wrap=False)):
            out = error_category(raw) or ""
            self.assertNotIn(FAKE_KEY, out)
            self.assertNotIn("123456789", out)
            self.assertNotIn("not found", out)

    def test_garbage_and_oversized(self) -> None:
        self.assertIsNone(error_category(b"<html>502</html>"))
        self.assertIsNone(error_category(b""))
        self.assertIsNone(error_category(b'{"error": {"status": "NOT_FOUND", "pad": "' + b"x" * ERROR_BODY_PEEK_BYTES + b'"}}'))


class TestProviderAttachesCategory(unittest.TestCase):
    def _provider(self, status: int, body: bytes) -> OpenAICompatChatProvider:
        transport = httpx.MockTransport(lambda req: httpx.Response(status, content=body,
                                                                   headers={"content-type": "application/json"}))
        return OpenAICompatChatProvider(name="gemini-01", base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                                        api_key=FAKE_KEY, client=httpx.Client(transport=transport,
                                                                             base_url="https://generativelanguage.googleapis.com/v1beta/openai"))

    def _req(self) -> GenerateRequest:
        return GenerateRequest(messages=[ChatTurn(role="user", content="hi")], model="gemini-3.8-flash",
                               max_output_tokens=64)

    def test_stream_404_carries_code_and_category_but_not_body(self) -> None:
        p = self._provider(404, _google("NOT_FOUND", 404))
        with self.assertRaises(ProviderError) as cm:
            list(p.stream(self._req()))
        self.assertEqual(cm.exception.code, "provider_http_404")
        self.assertEqual(cm.exception.category, "NOT_FOUND")
        self.assertNotIn(FAKE_KEY, str(cm.exception))
        self.assertNotIn("not found", str(cm.exception))

    def test_generate_403_service_disabled(self) -> None:
        p = self._provider(403, _google("PERMISSION_DENIED", 403, reason="SERVICE_DISABLED"))
        with self.assertRaises(ProviderError) as cm:
            p.generate(self._req())
        self.assertEqual((cm.exception.code, cm.exception.category), ("provider_http_403", "PERMISSION_DENIED:SERVICE_DISABLED"))

    def test_non_json_error_has_no_category(self) -> None:
        p = self._provider(502, b"<html>bad gateway</html>")
        with self.assertRaises(ProviderError) as cm:
            list(p.stream(self._req()))
        self.assertEqual(cm.exception.code, "provider_http_502")
        self.assertIsNone(cm.exception.category)


class TestSlotHealthLastError(unittest.TestCase):
    def _health(self, plane, sid):
        return next(s for s in plane.config_view()["slots"] if s["slot_id"] == sid)["health"]

    def test_failover_records_last_error_on_the_failing_slot_only(self) -> None:
        a, b = slot("gemini-01", priority=10), slot("gemini-02", priority=20)
        bad = ProviderError("Google trả lỗi 404.", code="provider_http_404", category="NOT_FOUND", transient=False)
        plane = plane_with([a, b], providers={"gemini-01": Scripted("gemini-01", fail=bad), "gemini-02": Scripted("gemini-02")})
        evs = run(plane)
        self.assertTrue(any(getattr(e, "provider_name", "") == "gemini-02" for e in evs))
        h1, h2 = self._health(plane, "gemini-01"), self._health(plane, "gemini-02")
        self.assertEqual((h1["last_error_code"], h1["last_error_category"]), ("provider_http_404", "NOT_FOUND"))
        self.assertTrue(h1["last_error_at"])
        self.assertIsNone(h2["last_error_code"])
        self.assertEqual(h1["usage_today"]["errors"], 1)

    def test_429_is_recorded_with_cooldown(self) -> None:
        a = slot("gemini-01")
        rl = ProviderError("429", code="provider_http_429", retry_after_s=30, category="RESOURCE_EXHAUSTED")
        plane = plane_with([a], providers={"gemini-01": Scripted("gemini-01", fail=rl)}, clock=Clock())
        run(plane)
        h = self._health(plane, "gemini-01")
        self.assertEqual((h["last_error_code"], h["last_error_category"], h["status"]),
                         ("provider_http_429", "RESOURCE_EXHAUSTED", "COOLDOWN"))
        self.assertEqual(h["usage_today"]["rate_limited"], 1)

    def test_mid_stream_failure_is_classified(self) -> None:
        a = slot("gemini-01")
        cut = ProviderError("cut", code="provider_network_error")
        plane = plane_with([a], providers={"gemini-01": Scripted("gemini-01", fail=cut, fail_after_delta=True)})
        run(plane)
        self.assertEqual(self._health(plane, "gemini-01")["last_error_code"], "provider_network_error")

    def test_free_text_never_reaches_health(self) -> None:
        a = slot("gemini-01")
        weird = ProviderError("x", code=f"provider_http_404 {FAKE_KEY}", category=f"NOT_FOUND {FAKE_KEY}")
        plane = plane_with([a], providers={"gemini-01": Scripted("gemini-01", fail=weird)})
        run(plane)
        h = self._health(plane, "gemini-01")
        self.assertEqual(h["last_error_code"], "provider_error")
        self.assertIsNone(h["last_error_category"])
        self.assertNotIn(FAKE_KEY, json.dumps(plane.config_view()))

    def test_unexpected_exception_class(self) -> None:
        class Boom(Scripted):
            def stream(self, req):  # noqa: D401
                raise RuntimeError(f"boom {FAKE_KEY}")
                yield  # pragma: no cover
        a = slot("gemini-01")
        plane = plane_with([a], providers={"gemini-01": Boom("gemini-01")})
        list(ControlledGateway(plane).stream([ChatTurn(role="user", content="hi")], mode="general"))
        h = self._health(plane, "gemini-01")
        self.assertEqual(h["last_error_code"], "provider_unexpected_error")
        self.assertNotIn(FAKE_KEY, json.dumps(plane.config_view()))


if __name__ == "__main__":
    unittest.main()

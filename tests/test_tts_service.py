"""
Test tang goi API: timeout, HTTP 403/429, shark block, task that bai,
thieu audio URL, thieu id/token...

KHONG co request that nao duoc gui: `requests.Session` duoc thay bang FakeSession.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from desktop_app.models import (
    CONNECT_TIMEOUT,
    READ_TIMEOUT_CREATE,
    READ_TIMEOUT_DOWNLOAD,
    READ_TIMEOUT_QUERY,
    ErrorKind,
)
from desktop_app.tts_service import (
    CancelToken,
    StopRequested,
    TtsError,
    TtsService,
    find_audio_url,
    safe_url_label,
    shark_marker,
)
from tests.mocks import (
    FAKE_MP3,
    FakeCapCutClient,
    FakeResponse,
    FakeSession,
    created_response,
    make_voice,
    query_response,
)


class ServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.voice = make_voice()
        self.cancel = CancelToken()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_service(self, post_script, get_script=None) -> TtsService:
        session = FakeSession(post_script, get_script)
        service = TtsService(session=session)
        service._client = FakeCapCutClient()
        self.session = session
        return service

    def synth(self, service: TtsService, name: str = "part_001.mp3"):
        return service.synthesize(
            text="Xin chào, đây là văn bản tiếng Việt.",
            voice=self.voice,
            dest=self.dir / name,
            cancel=self.cancel,
        )


class TestHappyPath(ServiceTestBase):
    def test_success_writes_file(self) -> None:
        service = self.make_service(
            [created_response(), query_response("processing"), query_response("success")]
        )
        with mock.patch("desktop_app.tts_service.POLL_INTERVAL_SECONDS", 0.01):
            result = self.synth(service)
        self.assertTrue(Path(result.file_path).is_file())
        self.assertEqual(Path(result.file_path).read_bytes(), FAKE_MP3)
        self.assertEqual(result.file_size, len(FAKE_MP3))
        self.assertEqual(result.task_id, "task-1234567890")

    def test_token_is_masked_never_raw(self) -> None:
        service = self.make_service([created_response(token="tok-secret-value"),
                                     query_response("success")])
        result = self.synth(service)
        self.assertIsNotNone(result.token_masked)
        self.assertNotIn("secret", result.token_masked)
        self.assertNotEqual(result.token_masked, "tok-secret-value")

    def test_audio_url_query_string_not_stored(self) -> None:
        service = self.make_service(
            [created_response(),
             query_response("success", url="https://cdn.fake/a/out.mp3?token=SUPERSECRET&x=1")]
        )
        result = self.synth(service)
        self.assertNotIn("SUPERSECRET", result.audio_host or "")
        self.assertEqual(result.audio_host, "cdn.fake/a/out.mp3")

    def test_all_done_statuses_accepted(self) -> None:
        for status in ("success", "succeed", "completed", "done", "SUCCESS", " Done "):
            with self.subTest(status=status):
                service = self.make_service([created_response(), query_response(status)])
                result = self.synth(service, name=f"p_{status.strip().lower()}.mp3")
                self.assertTrue(Path(result.file_path).is_file())

    def test_timeouts_passed_to_session(self) -> None:
        service = self.make_service([created_response(), query_response("success")])
        self.synth(service)
        self.assertEqual(
            self.session.post_calls[0]["timeout"], (CONNECT_TIMEOUT, READ_TIMEOUT_CREATE)
        )
        self.assertEqual(
            self.session.post_calls[1]["timeout"], (CONNECT_TIMEOUT, READ_TIMEOUT_QUERY)
        )
        self.assertEqual(
            self.session.get_calls[0]["timeout"], (CONNECT_TIMEOUT, READ_TIMEOUT_DOWNLOAD)
        )


class TestErrorClassification(ServiceTestBase):
    def _expect(self, post_script, kind: ErrorKind, get_script=None):
        service = self.make_service(post_script, get_script)
        with mock.patch("desktop_app.tts_service.POLL_INTERVAL_SECONDS", 0.01), \
             mock.patch("desktop_app.tts_service.POLL_TOTAL_SECONDS", 0.05), \
             mock.patch("desktop_app.tts_service.RATE_LIMIT_BACKOFF_SECONDS", (0.001,) * 3):
            with self.assertRaises(TtsError) as ctx:
                self.synth(service)
        self.assertEqual(ctx.exception.kind, kind, ctx.exception.message)
        return ctx.exception

    def test_connect_timeout(self) -> None:
        exc = self._expect([requests.exceptions.ConnectTimeout("boom")], ErrorKind.CONNECT_TIMEOUT)
        self.assertIn("ConnectTimeout", exc.message)

    def test_read_timeout(self) -> None:
        exc = self._expect([requests.exceptions.ReadTimeout("boom")], ErrorKind.READ_TIMEOUT)
        self.assertIn("ReadTimeout", exc.message)

    def test_network_error(self) -> None:
        self._expect([requests.exceptions.ConnectionError("dns")], ErrorKind.NETWORK_ERROR)

    def test_ssl_error(self) -> None:
        self._expect([requests.exceptions.SSLError("ssl")], ErrorKind.SSL_ERROR)

    def test_proxy_error(self) -> None:
        self._expect([requests.exceptions.ProxyError("proxy")], ErrorKind.PROXY_ERROR)

    def test_http_403_is_fatal_for_queue(self) -> None:
        exc = self._expect([FakeResponse(403, None, '{"message":"forbidden"}')], ErrorKind.HTTP_403)
        self.assertTrue(exc.is_fatal_for_queue)

    def test_shark_block_is_fatal_for_queue(self) -> None:
        exc = self._expect(
            [FakeResponse(200, None, '{"message":"shark decision: block"}')],
            ErrorKind.SHARK_BLOCK,
        )
        self.assertTrue(exc.is_fatal_for_queue)

    def test_shark_marker_inside_error_body(self) -> None:
        exc = self._expect(
            [FakeResponse(400, None, "verify_center required")], ErrorKind.SHARK_BLOCK
        )
        self.assertIn("verify_center", exc.detail)

    def test_other_http_error_is_not_fatal(self) -> None:
        exc = self._expect([FakeResponse(500, None, "boom")], ErrorKind.HTTP_ERROR)
        self.assertFalse(exc.is_fatal_for_queue)

    def test_non_json_response(self) -> None:
        self._expect([FakeResponse(200, None, "<html>not json</html>")], ErrorKind.BAD_RESPONSE)

    def test_no_task_returned(self) -> None:
        self._expect([FakeResponse(200, {"ret": "0", "data": {"tasks": []}})], ErrorKind.NO_TASK)

    def test_api_error_with_ret_code(self) -> None:
        exc = self._expect(
            [FakeResponse(200, {"ret": "1005", "errmsg": "quota exceeded", "data": {}})],
            ErrorKind.API_ERROR,
        )
        self.assertIn("1005", exc.message)
        self.assertIn("quota exceeded", exc.message)

    def test_task_missing_token(self) -> None:
        exc = self._expect(
            [FakeResponse(200, {"ret": "0", "data": {"tasks": [{"id": "abc"}]}})],
            ErrorKind.TASK_MISSING_FIELDS,
        )
        self.assertIn("token", exc.message)

    def test_task_missing_id(self) -> None:
        exc = self._expect(
            [FakeResponse(200, {"ret": "0", "data": {"tasks": [{"token": "t"}]}})],
            ErrorKind.TASK_MISSING_FIELDS,
        )
        self.assertIn("id", exc.message)

    def test_task_failed_statuses(self) -> None:
        for status in ("failed", "error", "cancelled", "canceled", "FAILED"):
            with self.subTest(status=status):
                self._expect(
                    [created_response(), query_response(status)], ErrorKind.TASK_FAILED
                )

    def test_poll_timeout(self) -> None:
        exc = self._expect(
            [created_response(), query_response("queueing")], ErrorKind.POLL_TIMEOUT
        )
        self.assertIn("queueing", exc.message)

    def test_success_but_no_audio_url(self) -> None:
        exc = self._expect(
            [created_response(), query_response("success", url=None)], ErrorKind.NO_AUDIO_URL
        )
        self.assertIn("không tìm thấy URL audio", exc.message)

    def test_download_http_error(self) -> None:
        self._expect(
            [created_response(), query_response("success")],
            ErrorKind.HTTP_ERROR,
            get_script=[FakeResponse(502, None, "bad gateway")],
        )

    def test_download_read_timeout(self) -> None:
        self._expect(
            [created_response(), query_response("success")],
            ErrorKind.READ_TIMEOUT,
            get_script=[requests.exceptions.ReadTimeout("slow")],
        )

    def test_empty_audio_download(self) -> None:
        self._expect(
            [created_response(), query_response("success")],
            ErrorKind.EMPTY_AUDIO,
            get_script=[FakeResponse(200, None, "", b"")],
        )

    def test_empty_text_rejected_before_request(self) -> None:
        service = self.make_service([created_response()])
        with self.assertRaises(TtsError) as ctx:
            service.synthesize(
                text="   ", voice=self.voice, dest=self.dir / "x.mp3", cancel=self.cancel
            )
        self.assertEqual(ctx.exception.kind, ErrorKind.EMPTY_TEXT)
        self.assertEqual(len(self.session.post_calls), 0, "Không được gửi request khi text rỗng")

    def test_partial_file_removed_on_failure(self) -> None:
        service = self.make_service(
            [created_response(), query_response("success")],
            get_script=[requests.exceptions.ReadTimeout("slow")],
        )
        with self.assertRaises(TtsError):
            self.synth(service)
        self.assertFalse((self.dir / "part_001.mp3").exists())
        self.assertFalse((self.dir / "part_001.mp3.part").exists())


class TestRateLimitBackoff(ServiceTestBase):
    def test_429_retries_three_times_then_fails(self) -> None:
        script = [FakeResponse(429, None, "slow down")] * 10
        service = self.make_service(script)
        messages = []
        with mock.patch("desktop_app.tts_service.RATE_LIMIT_BACKOFF_SECONDS", (0.001, 0.001, 0.001)):
            with self.assertRaises(TtsError) as ctx:
                service.synthesize(
                    text="xin chào", voice=self.voice, dest=self.dir / "a.mp3",
                    cancel=self.cancel, progress=messages.append,
                )
        self.assertEqual(ctx.exception.kind, ErrorKind.HTTP_429)
        # 1 lan dau + 3 lan thu lai = 4 request, khong spam vo han
        self.assertEqual(len(self.session.post_calls), 4)
        self.assertTrue(any("429" in m for m in messages))
        self.assertFalse(ctx.exception.is_fatal_for_queue)

    def test_429_then_success(self) -> None:
        service = self.make_service(
            [FakeResponse(429, None, "slow"), created_response(), query_response("success")]
        )
        with mock.patch("desktop_app.tts_service.RATE_LIMIT_BACKOFF_SECONDS", (0.001, 0.001, 0.001)):
            result = self.synth(service)
        self.assertTrue(Path(result.file_path).is_file())
        self.assertGreaterEqual(result.attempts, 2)

    def test_request_is_resigned_on_each_retry(self) -> None:
        """Chu ky chua device-time nen phai dung lai request moi lan thu."""
        service = self.make_service([FakeResponse(429, None, "slow")] * 6)
        with mock.patch("desktop_app.tts_service.RATE_LIMIT_BACKOFF_SECONDS", (0.001,) * 3):
            with self.assertRaises(TtsError):
                self.synth(service)
        self.assertEqual(len(service._client.tts_calls), 4)

    def test_stop_during_backoff(self) -> None:
        service = self.make_service([FakeResponse(429, None, "slow")] * 6)
        self.cancel.set()
        with mock.patch("desktop_app.tts_service.RATE_LIMIT_BACKOFF_SECONDS", (0.001,) * 3):
            with self.assertRaises(StopRequested):
                self.synth(service)


class TestCancelToken(ServiceTestBase):
    def test_stop_before_first_request(self) -> None:
        service = self.make_service([created_response(), query_response("success")])
        self.cancel.set()
        with self.assertRaises(StopRequested):
            self.synth(service)
        self.assertEqual(len(self.session.post_calls), 0)

    def test_stop_during_polling(self) -> None:
        service = self.make_service([created_response(), query_response("processing")])
        original_wait = self.cancel.wait

        def wait_then_stop(seconds):
            self.cancel.set()
            return original_wait(0)

        with mock.patch.object(self.cancel, "wait", side_effect=wait_then_stop):
            with self.assertRaises(StopRequested):
                self.synth(service)

    def test_wait_returns_true_when_set(self) -> None:
        token = CancelToken()
        self.assertFalse(token.wait(0.001))
        token.set()
        self.assertTrue(token.wait(0.001))
        token.clear()
        self.assertFalse(token.is_set())


class TestAudioUrlExtraction(unittest.TestCase):
    def test_direct_key(self) -> None:
        self.assertEqual(find_audio_url({"tts_url": "https://a/b.mp3"}), "https://a/b.mp3")

    def test_nested_dict(self) -> None:
        payload = {"data": {"audio": {"url": "https://a/x.mp3"}}, "cover": "https://a/i.png"}
        self.assertEqual(find_audio_url(payload), "https://a/x.mp3")

    def test_inside_list(self) -> None:
        self.assertEqual(
            find_audio_url({"items": [{"audio_url": "https://a/1.m4a"}]}), "https://a/1.m4a"
        )

    def test_nested_json_string(self) -> None:
        payload = {"payload": json.dumps({"deep": {"mp3_url": "https://a/n.mp3"}})}
        self.assertEqual(find_audio_url(payload), "https://a/n.mp3")

    def test_prefers_mp3_over_image(self) -> None:
        payload = {"thumbnail": "https://a/cover.png", "misc": "https://a/audio.mp3"}
        self.assertEqual(find_audio_url(payload), "https://a/audio.mp3")

    def test_none_when_absent(self) -> None:
        self.assertIsNone(find_audio_url({"duration": 5, "status": "ok"}))
        self.assertIsNone(find_audio_url(None))
        self.assertIsNone(find_audio_url("chuỗi thường"))

    def test_deep_recursion_guard(self) -> None:
        node: dict = {"url": "https://a/deep.mp3"}
        for _ in range(40):
            node = {"child": node}
        self.assertIsNone(find_audio_url(node))    # vuot do sau cho phep -> khong treo

    def test_safe_url_label(self) -> None:
        self.assertEqual(safe_url_label("https://h/p/a.mp3?sig=x"), "h/p/a.mp3")
        self.assertIsNone(safe_url_label(None))

    def test_shark_marker_detection(self) -> None:
        self.assertEqual(shark_marker("SHARK block"), "shark")
        self.assertEqual(shark_marker("please solve captcha"), "captcha")
        self.assertIsNone(shark_marker("mọi thứ đều ổn"))
        self.assertIsNone(shark_marker(""))


class TestRealClientBuildsRequest(unittest.TestCase):
    """
    Kiem tra viec tai su dung CapCutClient goc de dung request (khong gui di).
    Day la diem noi voi package goc — phai khong bi vo.
    """

    def test_build_request_via_real_client(self) -> None:
        service = TtsService(session=FakeSession([created_response(), query_response("success")]))
        client = service.client            # CapCutClient that
        url, headers, body = client.build_tts_new_request(
            texts="Xin chào Việt Nam", voice="BV421_vivn_streaming", rate="1.0"
        )
        self.assertIn("common_task/new", url)
        self.assertIn("sign", {k.lower() for k in headers})
        payload = json.loads(body)
        self.assertIn("tasks", payload)
        service.close()

    def test_build_query_via_real_client(self) -> None:
        service = TtsService(session=FakeSession([created_response()]))
        url, headers, body = service.client.build_query_request("id1", "tok1", mode="tts")
        self.assertIn("common_task/query", url)
        self.assertIn("id1", body)
        service.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

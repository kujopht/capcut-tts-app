"""
Router / pool hardening (audit D): phân loại lỗi cuối cùng theo nguyên nhân THẬT, ngân sách thời gian chuyển slot, tín hiệu
huỷ khi không còn ai đọc, kẹp `Retry-After`, bộ ngắt an toàn đa luồng, bộ đếm theo slot không mất lần đếm, và hành vi của
một pool giống production (8 slot khoẻ + 1 slot tắt). Mọi thứ tất định: đồng hồ giả, nhà cung cấp giả, không gọi Google.
"""
from __future__ import annotations

import threading
import time
import unittest
from typing import Any, Dict, List, Optional

import httpx

from server.ai_assistant.control.router import (
    COOLDOWN_MAX_S, FAILOVER_BUDGET_S, ControlledGateway, _clamp_cooldown, exhausted_event,
)
from server.ai_assistant.control.service import today_utc
from server.ai_assistant.control.store import AppwriteControlStore
from server.ai_assistant.gateway import AiGateway, ErrorEvent, ProviderServed
from server.llm_gateway.chat_provider import Delta, ProviderError
from server.llm_gateway.usage_limits import CircuitBreaker
from server.tests.test_ai_control_plane import Clock, Scripted, _FakeAppwrite, plane_with, run, slot, turns
from server.tests.test_ai_e2e_regression import World, _LiveServer, detail, ev


def last_error(events: List[Any]) -> Optional[ErrorEvent]:
    errs = [e for e in events if isinstance(e, ErrorEvent)]
    return errs[-1] if errs else None


# ======================================================================================== lỗi cuối cùng theo nguyên nhân

class TestFinalErrorReflectsTheRealCause(unittest.TestCase):
    """Trước đây RPM/TPM soft cap được báo là `ai_budget_exhausted` (route gắn scope=global + reset lúc nửa đêm: giao diện
    bảo "công suất chung đã hết, chờ tới ngày mai" cho một tình trạng tự hết sau 60 giây), còn cooldown thì thành
    `ai_no_provider` (bị coi như AI tắt hẳn)."""

    def _all(self, **slot_kw: Any):
        return plane_with([slot("gemini-01", **slot_kw), slot("gemini-02", **slot_kw)])

    def test_rpm_window_full_on_every_slot_is_busy_not_a_daily_quota(self) -> None:
        p = self._all(rpm_soft_cap=1)
        for s in p.snapshot().slots.values():
            p.note_attempt(s, 1)
        e = last_error(run(p))
        self.assertEqual(e.code, "ai_busy")
        self.assertNotIn("hạn mức", e.message)

    def test_tpm_window_full_on_every_slot_is_busy(self) -> None:
        p = self._all(tpm_soft_cap=50)
        for s in p.snapshot().slots.values():
            p.note_attempt(s, 49)
        self.assertEqual(last_error(run(p)).code, "ai_busy")

    def test_the_window_slides_so_the_same_pool_serves_again_a_minute_later(self) -> None:
        clk = Clock()
        p = plane_with([slot("gemini-01", rpm_soft_cap=1)], clock=clk)
        p.note_attempt(p.snapshot().slots["gemini-01"], 1)
        self.assertEqual(last_error(run(p)).code, "ai_busy")
        clk.t += 61
        self.assertIsNone(last_error(run(p)))

    def test_every_slot_cooling_down_is_unavailable_not_no_provider(self) -> None:
        p = self._all()
        for sid in ("gemini-01", "gemini-02"):
            p.breaker.cool_down(sid, 90)
        events = run(p)
        self.assertEqual(last_error(events).code, "ai_provider_unavailable")
        self.assertFalse([e for e in events if isinstance(e, ProviderServed)])

    def test_a_pool_that_is_only_cooling_or_windowed_never_reports_a_daily_quota(self) -> None:
        a, b = slot("gemini-01", daily_request_cap=1), slot("gemini-02")
        p = plane_with([a, b])
        p.store.add_usage("gemini-01", today_utc(), requests=1)
        p.breaker.cool_down("gemini-02", 90)
        self.assertEqual(last_error(run(p)).code, "ai_provider_unavailable",
                         "slot 02 sẽ quay lại sau cooldown nên không được báo như hết hạn ngày")

    def test_daily_caps_alone_still_report_budget_exhausted(self) -> None:
        a = slot("gemini-01", daily_request_cap=1)
        p = plane_with([a])
        p.store.add_usage("gemini-01", today_utc(), requests=1)
        self.assertEqual(last_error(run(p)).code, "ai_budget_exhausted")
        b = slot("gemini-01", daily_token_cap=10)
        p2 = plane_with([b])
        p2.store.add_usage("gemini-01", today_utc(), input_tokens=8, output_tokens=5)
        self.assertEqual(last_error(run(p2)).code, "ai_budget_exhausted")

    def test_nothing_configured_or_everything_disabled_is_no_provider(self) -> None:
        p = plane_with([slot("gemini-01", enabled=False), slot("gemini-02", workloads=("writer",))])
        self.assertEqual(last_error(run(p)).code, "ai_no_provider")
        self.assertEqual(last_error(run(plane_with([]))).code, "ai_no_provider")

    def test_exhausted_event_is_a_pure_function_of_the_skip_reasons(self) -> None:
        s = slot("gemini-01")
        cases = [
            ([(s, "cooldown")], "ai_provider_unavailable"),
            ([(s, "rpm_soft_cap"), (s, "tpm_soft_cap")], "ai_busy"),
            ([(s, "rpm_soft_cap"), (s, "cooldown")], "ai_provider_unavailable"),
            ([(s, "request_cap"), (s, "rpm_soft_cap")], "ai_busy"),
            ([(s, "request_cap"), (s, "token_cap")], "ai_budget_exhausted"),
            ([(s, "slot_disabled"), (s, "missing_secret"), (s, "type_disabled")], "ai_no_provider"),
            ([], "ai_no_provider"),
        ]
        for reasons, code in cases:
            with self.subTest(reasons=[r for _, r in reasons]):
                self.assertEqual(exhausted_event(reasons).code, code)

    def test_http_layer_gives_busy_without_a_scope_or_reset_time(self) -> None:
        w = World(slots=2, slot_kw={"rpm_soft_cap": 1})
        for s in w.plane.snapshot().slots.values():
            w.plane.note_attempt(s, 1)
        _, r = w.ask("alice")
        self.assertEqual(r.status_code, 200)
        e = ev(r, "error")[0]
        self.assertEqual(e["code"], "ai_busy")
        self.assertNotIn("scope", e)
        self.assertNotIn("reset_at", e)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0, "bận tạm thời là miễn phí cho người dùng")
        self.assertEqual(w.calls(), {})

    def test_http_layer_daily_slot_cap_is_still_global_scoped_with_a_reset_time(self) -> None:
        w = World(slots=1, slot_kw={"daily_request_cap": 1})
        w.plane.store.add_usage("gemini-01", today_utc(), requests=1)
        w.plane.invalidate()
        w.plane._usage_at = -1e9  # noqa: SLF001 — ép đọc lại sổ
        _, r = w.ask("alice")
        e = ev(r, "error")[0]
        self.assertEqual((e["code"], e["scope"]), ("ai_budget_exhausted", "global"))
        self.assertTrue(e["reset_at"])


# ======================================================================================== ngân sách chuyển slot + huỷ

class _AdvancingProvider(Scripted):
    """Mỗi lần gọi "tốn" `cost` giây (đồng hồ giả) rồi lỗi TRƯỚC delta đầu — mô phỏng nhà cung cấp treo tới timeout."""

    def __init__(self, name: str, clock: Clock, cost: float, *, error: Optional[ProviderError] = None) -> None:
        super().__init__(name)
        self._clock, self._cost = clock, cost
        self._error = error or ProviderError("timeout", code="provider_timeout")

    def stream(self, req):  # type: ignore[override]
        self.calls += 1
        self._clock.t += self._cost
        raise self._error
        yield  # pragma: no cover — làm đây là generator


class TestFailoverBudgetAndCancellation(unittest.TestCase):
    def _plane(self, provs: Dict[str, Any], clk: Clock):
        slots = [slot(f"gemini-0{i}", priority=i) for i in range(1, len(provs) + 1)]
        return plane_with(slots, providers=provs, clock=clk)

    def test_slow_failures_stop_trying_new_slots_once_the_budget_is_spent(self) -> None:
        clk = Clock()
        provs = {f"gemini-0{i}": _AdvancingProvider(f"gemini-0{i}", clk, cost=FAILOVER_BUDGET_S + 5) for i in (1, 2, 3, 4)}
        events = run(self._plane(provs, clk))
        self.assertEqual(last_error(events).code, "ai_provider_unavailable")
        self.assertEqual(sum(p.calls for p in provs.values()), 1, "sau một lần treo quá ngân sách thì không thử thêm slot nào")

    def test_fast_failures_still_walk_the_whole_pool(self) -> None:
        clk = Clock()
        provs = {f"gemini-0{i}": _AdvancingProvider(f"gemini-0{i}", clk, cost=0.2) for i in (1, 2, 3, 4)}
        events = run(self._plane(provs, clk))
        self.assertEqual(last_error(events).code, "ai_provider_unavailable")
        self.assertEqual([p.calls for p in provs.values()], [1, 1, 1, 1], "lỗi nhanh thì vẫn thử đủ từng slot một lần")

    def test_the_budget_does_not_block_the_first_attempt_or_a_later_success_inside_it(self) -> None:
        clk = Clock()
        provs = {"gemini-01": _AdvancingProvider("gemini-01", clk, cost=FAILOVER_BUDGET_S - 5),
                 "gemini-02": Scripted("gemini-02")}
        events = run(self._plane(provs, clk))
        self.assertIsNone(last_error(events))
        self.assertEqual([e.provider_name for e in events if isinstance(e, ProviderServed)], ["gemini-02"])

    def test_cancel_before_the_first_attempt_calls_no_provider_and_yields_nothing(self) -> None:
        clk = Clock()
        provs = {f"gemini-0{i}": Scripted(f"gemini-0{i}") for i in (1, 2)}
        events = list(ControlledGateway(self._plane(provs, clk)).stream(turns(), mode="general", cancel=lambda: True))
        self.assertEqual(events, [])
        self.assertEqual(sum(p.calls for p in provs.values()), 0)

    def test_cancel_between_attempts_stops_the_walk(self) -> None:
        clk = Clock()
        gone = threading.Event()

        class _FailThenLeave(_AdvancingProvider):
            def stream(self, req):  # type: ignore[override]
                gone.set()  # người dùng bỏ đi trong lúc lần thử đầu còn đang treo
                yield from super().stream(req)

        provs = {"gemini-01": _FailThenLeave("gemini-01", clk, cost=1.0), "gemini-02": Scripted("gemini-02"),
                 "gemini-03": Scripted("gemini-03")}
        events = list(ControlledGateway(self._plane(provs, clk)).stream(turns(), mode="general", cancel=gone.is_set))
        self.assertEqual((provs["gemini-02"].calls, provs["gemini-03"].calls), (0, 0), "không gọi thêm slot nào cho lượt đã bị bỏ")
        self.assertEqual([e for e in events if isinstance(e, ProviderServed)], [])

    def test_a_cancel_that_never_fires_changes_nothing(self) -> None:
        clk = Clock()
        provs = {"gemini-01": Scripted("gemini-01")}
        events = list(ControlledGateway(self._plane(provs, clk)).stream(turns(), mode="general", cancel=lambda: False))
        self.assertTrue([e for e in events if isinstance(e, Delta)])

    def test_legacy_gateway_honours_cancel_too(self) -> None:
        a, b = Scripted("a", fail=ProviderError("x", code="provider_http_500")), Scripted("b")
        gone = threading.Event()
        gw = AiGateway(providers={"a": a, "b": b}, provider_chain=["a", "b"])
        gone.set()
        self.assertEqual(list(gw.stream(turns(), mode="general", cancel=gone.is_set)), [])
        self.assertEqual((a.calls, b.calls), (0, 0))
        self.assertTrue([e for e in AiGateway(providers={"b": Scripted("b")}, provider_chain=["b"])
                         .stream(turns(), mode="general") if isinstance(e, Delta)])


class TestOnAttemptReporting(unittest.TestCase):
    """`on_attempt(slot_id, model)`: route biết slot nào ĐANG BỊ GỌI trước cả token đầu, để tính đúng một lượt vào bộ đếm
    slot (= trần toàn cục) khi client bỏ ngang trước token đầu."""

    def test_reported_right_before_each_provider_call_in_order(self) -> None:
        order: List[Any] = []

        class Recording(Scripted):
            def stream(self, req):  # type: ignore[override]
                order.append(("call", self.name))
                yield from super().stream(req)

        provs = {"gemini-01": Recording("gemini-01", fail=ProviderError("x", code="provider_http_503")),
                 "gemini-02": Recording("gemini-02")}
        plane = plane_with([slot("gemini-01", priority=1), slot("gemini-02", priority=2)], providers=provs)
        events = list(ControlledGateway(plane).stream(
            turns(), mode="general", on_attempt=lambda s, m: order.append(("attempt", s, m))))
        self.assertEqual(order, [("attempt", "gemini-01", "gemini-model"), ("call", "gemini-01"),
                                 ("attempt", "gemini-02", "gemini-model"), ("call", "gemini-02")])
        self.assertTrue([e for e in events if isinstance(e, Delta)])

    def test_a_failing_callback_never_breaks_the_turn(self) -> None:
        def boom(_s: str, _m: str) -> None:
            raise RuntimeError("callback hỏng")

        plane = plane_with([slot("gemini-01")])
        events = list(ControlledGateway(plane).stream(turns(), mode="general", on_attempt=boom))
        self.assertIsNone(last_error(events))
        self.assertTrue([e for e in events if isinstance(e, Delta)])

    def test_legacy_gateway_reports_too(self) -> None:
        seen: List[Any] = []
        gw = AiGateway(providers={"b": Scripted("b")}, provider_chain=["b"])
        list(gw.stream(turns(), mode="general", on_attempt=lambda s, m: seen.append((s, m))))
        self.assertEqual([s for s, _ in seen], ["b"])


class TestCancelRaisedBetweenTheCheckAndTheProviderCall(unittest.TestCase):
    """Đua do reviewer (lượt 3) tìm ra: `cancel()` được kiểm ở đầu vòng, rồi gateway còn tra khoá/dựng provider/báo `on_attempt`.
    Client ngắt đúng khoảng đó thì route đọc `tried` (còn rỗng) và không đếm slot, trong khi gateway VẪN gọi nhà cung cấp. Kiểm
    lại SAU `on_attempt` đóng khoảng hở: hoặc lời gọi không được phát đi (không có gì để đếm), hoặc `tried` đã có trước khi cờ
    huỷ được đặt (route đếm đúng)."""

    def test_control_plane_gateway_makes_no_call_when_cancel_fires_inside_the_attempt_callback(self) -> None:
        gone, prov = threading.Event(), Scripted("gemini-01")
        plane = plane_with([slot("gemini-01")], providers={"gemini-01": prov})
        events = list(ControlledGateway(plane).stream(turns(), mode="general", cancel=gone.is_set,
                                                      on_attempt=lambda s, m: gone.set()))
        self.assertEqual((events, prov.calls), ([], 0))

    def test_legacy_gateway_too(self) -> None:
        gone, prov = threading.Event(), Scripted("a")
        gw = AiGateway(providers={"a": prov}, provider_chain=["a"])
        events = list(gw.stream(turns(), mode="general", cancel=gone.is_set, on_attempt=lambda s, m: gone.set()))
        self.assertEqual((events, prov.calls), ([], 0))

    def test_a_cancel_that_arrives_after_the_provider_call_started_is_still_attributed(self) -> None:
        """Hướng ngược lại (đúng): cờ huỷ đặt SAU phép kiểm thứ hai thì `on_attempt` đã chạy trước đó, nên route thấy slot."""
        gone, seen = threading.Event(), []

        class SetsCancelWhileStreaming(Scripted):
            def stream(self, req):  # type: ignore[override]
                gone.set()  # client ngắt ngay khi lời gọi bắt đầu
                yield from super().stream(req)

        prov = SetsCancelWhileStreaming("gemini-01")
        plane = plane_with([slot("gemini-01")], providers={"gemini-01": prov})
        list(ControlledGateway(plane).stream(turns(), mode="general", cancel=gone.is_set,
                                             on_attempt=lambda s, m: seen.append(s)))
        self.assertEqual((prov.calls, seen), (1, ["gemini-01"]))


class TestEmptyCompletionStillCountsAsAProviderRequest(unittest.TestCase):
    """Lỗ hổng do reviewer (lượt 3) tìm ra: nhà cung cấp trả lời THÀNH CÔNG nhưng RỖNG (vd. bị lọc nội dung: chỉ `usage` +
    `finish_reason`, không token chữ nào). Gateway chỉ phát `ProviderServed` ở token chữ đầu nên slot không được đếm — trong khi
    người dùng vẫn bị trừ lượt — và N tài khoản x 5 lượt kiểu này gọi nhà cung cấp mà không bao giờ chạm trần toàn cục."""

    def test_the_slot_and_the_global_ceiling_count_it_and_the_user_is_charged(self) -> None:
        w = World(slots=1, global_cap=3, per_user=5, scripts={"gemini-01": ["empty", "empty", "empty"]})
        for i in range(3):
            _, r = w.ask(f"u{i}")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(ev(r, "delta"), [])
            self.assertEqual(ev(r, "done")[0]["status"], "complete")
            self.assertEqual(w.avail(f"u{i}")["limits"]["requests_used"], 1, "lượt rỗng vẫn trừ lượt của người dùng")
        self.assertEqual(w.per_slot(), {"gemini-01": 3}, "mỗi lượt rỗng là một request thật ở slot")
        _, r = w.ask("u3")
        self.assertEqual((r.status_code, detail(r)["scope"]), (429, "global"), "trần toàn cục phải chạm nhờ các lượt rỗng")
        self.assertEqual(len(w.provs["gemini-01"].requests), 3, "lượt thứ tư bị chặn TRƯỚC khi gọi nhà cung cấp")

    def test_a_provider_failure_before_the_first_token_stays_an_error_not_a_request(self) -> None:
        """Chính sách (ghi trong runbook): lỗi phía nhà cung cấp TRƯỚC token chỉ vào `errors` của slot — không vào `requests`
        (= trần toàn cục) và không trừ lượt người dùng. Ghim lại để đổi chính sách này là một quyết định có chủ ý."""
        w = World(slots=1, scripts={"gemini-01": [ProviderError("5xx", code="provider_http_500")]})
        _, r = w.ask("alice")
        self.assertEqual(ev(r, "error")[0]["code"], "ai_provider_unavailable")
        self.assertEqual(w.per_slot(), {})
        self.assertEqual(w.plane.usage_today()["gemini-01"].errors, 1)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0)


class TestAbandonedTurnsDoNotKeepHittingProviders(unittest.TestCase):
    """Chứng minh trên socket THẬT: client bỏ đi trong lúc slot đầu còn treo -> slot sau KHÔNG bị gọi."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.w = World(slots=3, prio={"gemini-01": 1, "gemini-02": 2, "gemini-03": 3}, scripts={
            "gemini-01": [("slow_fail", 1.2, ProviderError("hết giờ", code="provider_timeout"))]})
        cls.live = _LiveServer(cls.w.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.live.close()

    def test_client_leaves_while_the_first_slot_hangs_so_no_other_slot_is_called(self) -> None:
        w, tok = self.w, "leaver"
        cid = httpx.post(f"{self.live.base}/api/ai/conversations", headers=w.hdr(tok), json={"mode": "general"}, timeout=10).json()["conversation_id"]
        got = self.live.raw_post(f"/api/ai/conversations/{cid}/messages", tok, {"content": "treo", "client_id": "lv"},
                                 read_until=b"event: meta")
        self.assertIn(b"event: meta", got)
        deadline = time.time() + 8
        while time.time() < deadline and (w.rt.stream_guard._total or not w.provs["gemini-01"].closed):  # noqa: SLF001
            time.sleep(0.05)
        time.sleep(0.3)
        self.assertEqual(len(w.provs["gemini-01"].requests), 1)
        self.assertEqual((len(w.provs["gemini-02"].requests), len(w.provs["gemini-03"].requests)), (0, 0),
                         "lượt đã bị bỏ không được đi tiếp sang các slot khác")
        self.assertEqual(w.rt.stream_guard._total, 0)  # noqa: SLF001


# ======================================================================================== kẹp Retry-After + bộ ngắt

class TestCooldownClampAndBreaker(unittest.TestCase):
    def test_clamp_cooldown(self) -> None:
        self.assertEqual(_clamp_cooldown(None), 30.0)
        self.assertEqual(_clamp_cooldown(float("nan")), 30.0)
        self.assertEqual(_clamp_cooldown("abc"), 30.0)  # type: ignore[arg-type]
        self.assertEqual(_clamp_cooldown(0.0), 1.0)
        self.assertEqual(_clamp_cooldown(-5), 1.0)
        self.assertEqual(_clamp_cooldown(90), 90.0)
        self.assertEqual(_clamp_cooldown(10 ** 9), COOLDOWN_MAX_S)
        self.assertEqual(_clamp_cooldown(float("inf")), COOLDOWN_MAX_S)

    def test_a_hostile_retry_after_cannot_park_a_slot_for_a_day(self) -> None:
        clk = Clock()
        a = slot("gemini-01")
        prov = {"gemini-01": Scripted("gemini-01", fail=ProviderError("429", code="provider_http_429", retry_after_s=86_400))}
        p = plane_with([a], providers=prov, clock=clk)
        run(p)
        self.assertLessEqual(p.breaker.snapshot()["gemini-01"]["open_for_s"], COOLDOWN_MAX_S)
        clk.t += COOLDOWN_MAX_S + 1
        self.assertFalse(p.breaker.is_open("gemini-01"))

    def test_429_without_retry_after_uses_the_default_cooldown_and_recovers(self) -> None:
        clk = Clock()
        a = slot("gemini-01")
        prov = {"gemini-01": Scripted("gemini-01", fail=ProviderError("429", code="provider_http_429"))}
        p = plane_with([a], providers=prov, clock=clk)
        run(p)
        self.assertAlmostEqual(p.breaker.snapshot()["gemini-01"]["open_for_s"], 30.0, delta=0.5)
        clk.t += 31
        self.assertFalse(p.breaker.is_open("gemini-01"))

    def test_breaker_counts_exactly_under_heavy_thread_contention(self) -> None:
        cb = CircuitBreaker(failure_threshold=10 ** 9, clock_fn=lambda: 0.0)
        n_threads, per = 16, 400

        def hammer() -> None:
            for _ in range(per):
                cb.record_failure("x")
                cb.snapshot()
                cb.is_open("x")

        threads = [threading.Thread(target=hammer) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(cb.snapshot()["x"]["consecutive_failures"], n_threads * per)

    def test_success_clears_a_cooldown_so_the_owner_reset_button_and_a_good_probe_keep_working(self) -> None:
        cb = CircuitBreaker(clock_fn=lambda: 100.0)
        cb.cool_down("a", 300)
        self.assertTrue(cb.is_open("a"))
        cb.record_success("a")
        self.assertFalse(cb.is_open("a"))
        self.assertEqual(cb.snapshot()["a"], {"consecutive_failures": 0, "open_for_s": 0.0})


# ======================================================================================== bộ đếm theo slot

class _SlowFakeAppwrite(_FakeAppwrite):
    """Kéo dài khoảng giữa đọc và ghi để lộ ra race của đọc-sửa-ghi."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        resp = super().__call__(request)  # ĐỌC xong rồi mới trễ: giá trị người gọi nhận đã cũ khi nó ghi lại
        if request.method == "GET":
            time.sleep(0.004)
        return resp


class TestSlotUsageCounterDoesNotLoseUpdates(unittest.TestCase):
    def _store(self) -> AppwriteControlStore:
        from server.config import AppwriteSettings
        aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
        return AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(_SlowFakeAppwrite())))

    def test_concurrent_turns_on_one_slot_all_count(self) -> None:
        st = self._store()
        day = "20261002"
        n_threads, per = 8, 6

        def work() -> None:
            for _ in range(per):
                st.add_usage("gemini-01", day, requests=1, input_tokens=10, output_tokens=5)

        threads = [threading.Thread(target=work) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        u = st.usage_for_day(day)["gemini-01"]
        self.assertEqual((u.requests, u.input_tokens, u.output_tokens), (n_threads * per, n_threads * per * 10, n_threads * per * 5))

    def test_different_slots_do_not_block_each_other(self) -> None:
        st = self._store()
        lock_a, lock_b = st._usage_lock("gemini-01_20261002"), st._usage_lock("gemini-02_20261002")  # noqa: SLF001
        self.assertIsNot(lock_a, lock_b)
        self.assertIs(lock_a, st._usage_lock("gemini-01_20261002"))  # noqa: SLF001


# ======================================================================================== pool giống production

class TestProductionShapedPool(unittest.TestCase):
    """9 slot Gemini, gemini-05 tắt (đúng như production): 8 slot khoẻ dùng được, slot tắt không bao giờ nhận tải."""

    def test_eight_healthy_slots_share_the_load_and_the_disabled_one_gets_nothing(self) -> None:
        w = World(slots=9, disabled=("gemini-05",), global_cap=500, per_user=5)
        for i in range(48):
            self.assertEqual(w.ask(f"u{i}")[1].status_code, 200)
        calls = w.calls()
        self.assertNotIn("gemini-05", calls)
        self.assertEqual(sum(calls.values()), 48)
        self.assertEqual(len(calls), 8, f"cả 8 slot khoẻ phải nhận tải: {calls}")
        self.assertLessEqual(max(calls.values()), 18, f"không slot nào ôm quá nửa tải: {calls}")
        self.assertEqual(w.per_slot(), calls)
        health = {s["slot_id"]: s["health"]["status"] for s in w.c.get("/api/admin/ai/config", headers={"Authorization": "Bearer owner"}).json()["slots"]}
        self.assertEqual(health["gemini-05"], "DISABLED")
        self.assertEqual({v for k, v in health.items() if k != "gemini-05"}, {"HEALTHY"})

    def test_losing_three_slots_to_429_keeps_service_up_on_the_rest(self) -> None:
        err = lambda: ProviderError("429", code="provider_http_429", retry_after_s=120)  # noqa: E731
        w = World(slots=9, disabled=("gemini-05",), global_cap=500,
                  scripts={sid: [err()] for sid in ("gemini-01", "gemini-02", "gemini-03")})
        for i in range(30):
            _, r = w.ask(f"u{i}")
            self.assertEqual(ev(r, "error"), [], r.text)
        calls = w.calls()
        self.assertEqual(sum(1 for sid in ("gemini-01", "gemini-02", "gemini-03") if len(w.provs[sid].requests) > 1), 0,
                         "slot bị 429 được cho nghỉ, không bị gọi lại trong thời gian cooldown")
        self.assertEqual(w.avail("u0")["limits"]["requests_used"], 1)
        self.assertEqual(sum(w.per_slot().values()), 30, "mỗi lượt được tính ĐÚNG một lần dù đã chuyển slot")

    def test_the_whole_pool_down_is_a_deterministic_unavailable_error_that_costs_nothing(self) -> None:
        err = lambda: ProviderError("503", code="provider_http_503")  # noqa: E731
        w = World(slots=9, disabled=("gemini-05",), scripts={f"gemini-0{i}": [err()] for i in (1, 2, 3, 4, 6, 7, 8, 9)})
        _, r = w.ask("alice")
        self.assertEqual(ev(r, "error")[0]["code"], "ai_provider_unavailable")
        self.assertEqual(sum(len(p.requests) for p in w.provs.values()), 8, "đúng 8 lần thử, slot tắt không bị đụng")
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0)
        self.assertEqual(w.ask("alice")[1].status_code, 200, "pool tự hồi phục ngay khi nhà cung cấp trả lời lại")

    def test_probe_of_a_cooling_slot_that_succeeds_brings_it_back(self) -> None:
        w = World(slots=2, prio={"gemini-01": 1, "gemini-02": 2},
                  scripts={"gemini-01": [ProviderError("429", code="provider_http_429", retry_after_s=300)]})
        w.ask("alice")
        w.ask("bob")
        self.assertEqual(len(w.provs["gemini-01"].requests), 1, "đang cooldown")
        r = w.c.post("/api/admin/ai/slots/gemini-01/probe", headers={"Authorization": "Bearer owner"})
        self.assertTrue(r.json()["probe"]["ok"])
        w.ask("carol")
        self.assertEqual(len(w.provs["gemini-01"].requests), 2, "probe thành công đóng cooldown")


if __name__ == "__main__":
    unittest.main()

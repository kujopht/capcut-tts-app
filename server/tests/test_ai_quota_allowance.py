"""
Hạn mức RIÊNG của người dùng + lối QA của Owner (`docs/ai/AI_ADMIN_CONTROL_PLANE.md` mục "Hạn mức người dùng
và lối QA").

Bốn điều được khoá ở đây:
1. `GET /api/ai/availability` → `limits` chỉ nói về hạn mức CỦA CHÍNH người gọi (số lượt đã dùng / còn lại, đã hết
   chưa, giờ làm mới) — đúng thứ `post_message` sẽ thực thi. Mức dùng toàn site không bao giờ lọt vào đó:
   trước đây giao diện hiện "51%" (ngân sách token cũ) cạnh câu "đã hết lượt" (trần 5 lượt của control plane).
2. Lần từ chối vì hết hạn mức mang `scope` (user | global | qa) để giao diện nói đúng điều gì đã hết, và lần
   gửi bị từ chối KHÔNG được lưu (nên giao diện đánh dấu "chưa gửi" là đúng sự thật).
3. Lối QA (`qa: true`) chỉ cho Owner, ghi vào sổ riêng, không ăn vào hạn mức người dùng thường.
4. Nhưng lối QA VẪN bị công tắc khẩn cấp và trần toàn cục chặn, và vẫn nằm trong tổng toàn cục.
"""
from __future__ import annotations

import os
import unittest
from dataclasses import replace
from typing import Any, Dict, Tuple
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ai_assistant.control.service import ControlPlane
from server.ai_assistant.limits import (
    QA_LEDGER_PREFIX, Allowance, AiBudgetExceeded, compute_allowance, qa_allowance, qa_ledger_user,
)
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime, build_ai_runtime
from server.config import (
    AI_OWNER_QA_DAILY_REQUESTS_DEFAULT, AI_OWNER_QA_DAILY_REQUESTS_MAX, AiAssistantSettings, Settings,
    _ai_assistant_settings,
)
from server.tests.test_ai_admin_api import make_plane
from server.tests.test_ai_control_plane import slot
from server.tests.test_ai_routes import _auth, _parse_sse_events, _resolve_profile

OWNER = "user_owner"  # `_resolve_profile` đặt tiền tố `user_` trước token
ALICE = "user_alice"


class _Env:
    """Một app thật (route + runtime + control plane) với sổ trong bộ nhớ."""

    def __init__(self, *, per_user: int = 5, global_cap: int = 150, token_cap: int = 15000, owner_qa: int = 20,
                 slots: Any = None, control: bool = True) -> None:
        self.plane: ControlPlane = make_plane(slots if slots is not None else [slot("gemini-01")])
        self.plane.update_controls("owner", {"per_user_daily_request_cap": per_user,
                                             "global_daily_request_cap": global_cap,
                                             "per_user_daily_token_cap": token_cap})
        ai = AiAssistantSettings(enabled=True, providers=("mock",), audience="all", rpm=1000,
                                 owner_qa_daily_requests=owner_qa)
        self.settings = replace(Settings(), owner_user_ids=(OWNER,), ai_assistant=ai)
        self.rt: AiRuntime = build_ai_runtime(self.settings, control=self.plane if control else None)
        app = FastAPI()
        app.include_router(build_ai_router(self.rt, resolve_profile=_resolve_profile))
        self.c = TestClient(app)
        self._n = 0

    def ask(self, token: str, *, qa: bool = False, text: str = "xin chào") -> Tuple[str, Any]:
        cid = self.c.post("/api/ai/conversations", headers=_auth(token), json={"mode": "general"}).json()["conversation_id"]
        self._n += 1
        body: Dict[str, Any] = {"content": text, "client_id": f"c{self._n}"}
        if qa:
            body["qa"] = True
        return cid, self.c.post(f"/api/ai/conversations/{cid}/messages", headers=_auth(token), json=body)

    def avail(self, token: str) -> Dict[str, Any]:
        return self.c.get("/api/ai/availability", headers=_auth(token)).json()

    def stored(self, cid: str) -> int:
        return len(self.rt.repo.list_messages(cid, limit=50))


def _detail(r: Any) -> Dict[str, Any]:
    return r.json()["detail"]


class TestAllowanceUnits(unittest.TestCase):
    def test_compute_allowance_mirrors_every_check_a_send_will_meet(self) -> None:
        cases = [
            # used_req, used_tok, req_cap, tok_cap, legacy, -> (limit, remaining, exhausted)
            (0, 0, 5, 15000, 30000, (5, 5, False)),
            (3, 900, 5, 15000, 30000, (5, 2, False)),
            (5, 900, 5, 15000, 30000, (5, 0, True)),
            (6, 900, 5, 15000, 30000, (5, 0, True)),
            (1, 15000, 5, 15000, 30000, (5, 0, True)),   # hết token trước hết lượt: vẫn là hết
            (1, 30000, 5, 0, 30000, (5, 0, True)),       # chỉ ngân sách token hạng tài khoản cũ
            (2, 100, 0, 0, 30000, (None, None, False)),  # không đặt trần lượt: không có "x/y"
            (2, 30000, 0, 0, 30000, (None, None, True)),
        ]
        for used_req, used_tok, req_cap, tok_cap, legacy, (limit, remaining, exhausted) in cases:
            with self.subTest(case=(used_req, used_tok, req_cap, tok_cap, legacy)):
                a = compute_allowance(requests_used=used_req, tokens_used=used_tok, request_cap=req_cap,
                                      token_cap=tok_cap, legacy_token_limit=legacy, reset_at="2026-10-02T00:00:00+00:00")
                self.assertEqual((a.requests_limit, a.requests_remaining, a.exhausted), (limit, remaining, exhausted))
                self.assertEqual(a.requests_used, used_req)
                self.assertEqual(set(a.to_public()),
                                 {"requests_used", "requests_limit", "requests_remaining", "exhausted", "reset_at"})

    def test_legacy_limit_none_is_not_applied(self) -> None:
        a = compute_allowance(requests_used=0, tokens_used=10**9, request_cap=5, token_cap=0, legacy_token_limit=None)
        self.assertFalse(a.exhausted)

    def test_qa_allowance_zero_cap_means_closed_not_unlimited(self) -> None:
        self.assertTrue(qa_allowance(requests_used=0, daily_cap=0).exhausted)
        a = qa_allowance(requests_used=3, daily_cap=20)
        self.assertEqual((a.requests_limit, a.requests_remaining, a.exhausted), (20, 17, False))
        self.assertTrue(qa_allowance(requests_used=20, daily_cap=20).exhausted)

    def test_qa_ledger_key_is_short_stable_and_cannot_collide_with_a_user(self) -> None:
        k = qa_ledger_user(OWNER)
        self.assertEqual(k, qa_ledger_user(OWNER))
        self.assertNotEqual(k, qa_ledger_user(ALICE))
        self.assertTrue(k.startswith(QA_LEDGER_PREFIX))
        self.assertLessEqual(len(k), 19)
        # mã tài liệu Appwrite `{khoá}_{yyyymmdd}` <= 36 ký tự, kể cả với user id dài nhất được phép
        self.assertLessEqual(len(qa_ledger_user("x" * 36)) + 1 + 8, 36)
        self.assertNotIn(OWNER, k)
        # id người dùng thật không bao giờ bắt đầu bằng "qa-" + 16 hex: regex id cho phép, nhưng chỉ Owner/allowlist mới có id
        self.assertNotEqual(k, OWNER)

    def test_budget_exceeded_defaults_to_user_scope(self) -> None:
        self.assertEqual(AiBudgetExceeded("x", reset_at="r").scope, "user")


class TestUserAllowanceInAvailability(unittest.TestCase):
    def test_fresh_user_sees_own_allowance_and_reset_time(self) -> None:
        e = _Env(per_user=5)
        lim = e.avail("alice")["limits"]
        self.assertEqual((lim["requests_used"], lim["requests_limit"], lim["requests_remaining"], lim["exhausted"]),
                         (0, 5, 5, False))
        self.assertTrue(lim["reset_at"].startswith("20") and "T00:00:00" in lim["reset_at"])

    def test_allowance_counts_down_and_flips_to_exhausted_at_the_cap(self) -> None:
        e = _Env(per_user=3)
        for used in (1, 2, 3):
            _, r = e.ask("alice")
            self.assertEqual(r.status_code, 200, r.text)
            lim = e.avail("alice")["limits"]
            self.assertEqual((lim["requests_used"], lim["requests_remaining"], lim["exhausted"]),
                             (used, 3 - used, used == 3))

    def test_limits_carry_nothing_about_site_wide_usage(self) -> None:
        """Ca "51%": người khác dùng nhiều (toàn site đã ~60%), người này chưa dùng gì -> vẫn 5/5, không số chung."""
        e = _Env(per_user=5, global_cap=10)
        for _ in range(3):
            self.assertEqual(e.ask("bob")[1].status_code, 200)
        self.assertEqual(e.ask("carol")[1].status_code, 200)
        self.assertEqual(e.ask("dave")[1].status_code, 200)
        self.assertEqual(e.ask("erin")[1].status_code, 200)
        self.assertEqual(e.plane.overview()["requests"], 6)  # 60% của trần toàn cục 10
        av = e.avail("alice")
        self.assertEqual(av["limits"]["requests_remaining"], 5)
        self.assertEqual(set(av["limits"]), {"used_today", "limit_today", "requests_used", "requests_limit",
                                             "requests_remaining", "exhausted", "reset_at"})
        for key in ("global", "capacity", "overview", "caps"):
            self.assertNotIn(key, str(av).lower().replace("remaining", ""), key)

    def test_token_cap_can_exhaust_before_the_request_cap(self) -> None:
        e = _Env(per_user=5, token_cap=10)  # mỗi lượt Scripted tốn 15 token
        self.assertEqual(e.ask("alice")[1].status_code, 200)
        lim = e.avail("alice")["limits"]
        self.assertTrue(lim["exhausted"])
        self.assertEqual(lim["requests_remaining"], 0)
        _, r = e.ask("alice")
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "user"))

    def test_legacy_mode_without_control_plane_has_no_request_cap(self) -> None:
        e = _Env(control=False)
        lim = e.avail("alice")["limits"]
        self.assertIsNone(lim["requests_limit"])
        self.assertIsNone(lim["requests_remaining"])
        self.assertFalse(lim["exhausted"])


class TestRejectionScopeAndNotStored(unittest.TestCase):
    def test_user_cap_rejection_has_scope_user_reset_time_and_stores_nothing(self) -> None:
        e = _Env(per_user=1)
        self.assertEqual(e.ask("alice")[1].status_code, 200)
        cid, r = e.ask("alice")
        self.assertEqual(r.status_code, 429)
        d = _detail(r)
        self.assertEqual((d["code"], d["scope"]), ("ai_budget_exhausted", "user"))
        self.assertTrue(d["reset_at"])
        self.assertEqual(e.stored(cid), 0, "tin bị từ chối KHÔNG được lưu — giao diện đánh dấu 'chưa gửi' là đúng sự thật")

    def test_global_cap_rejection_has_scope_global_while_own_allowance_is_untouched(self) -> None:
        e = _Env(per_user=5, global_cap=2)
        self.assertEqual(e.ask("bob")[1].status_code, 200)
        self.assertEqual(e.ask("carol")[1].status_code, 200)
        cid, r = e.ask("alice")
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "global"))
        self.assertEqual(e.stored(cid), 0)
        lim = e.avail("alice")["limits"]
        self.assertEqual((lim["requests_remaining"], lim["exhausted"]), (5, False),
                        "hết công suất chung không biến thành 'bạn đã hết lượt'")

    def test_in_stream_capacity_exhaustion_is_global_scope_with_reset_time(self) -> None:
        e = _Env(slots=[slot("gemini-01", daily_request_cap=1)])
        self.assertEqual(e.ask("alice")[1].status_code, 200)
        _, r = e.ask("bob")
        self.assertEqual(r.status_code, 200)  # đã vào luồng, lỗi đến dưới dạng sự kiện SSE
        err = [d for n, d in _parse_sse_events(r.text) if n == "error"]
        self.assertEqual(len(err), 1, r.text)
        self.assertEqual((err[0]["code"], err[0]["scope"]), ("ai_budget_exhausted", "global"))
        self.assertTrue(err[0]["reset_at"])

    def test_legacy_token_budget_rejection_is_user_scope(self) -> None:
        e = _Env(per_user=0, token_cap=0)  # 0 = không trần của control plane; chỉ còn ngân sách token cũ
        e.rt.daily_tokens_free = 10
        self.assertEqual(e.ask("alice")[1].status_code, 200)
        _, r = e.ask("alice")
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "user"))


class TestQaLane(unittest.TestCase):
    def test_owner_qa_turns_do_not_consume_the_normal_allowance(self) -> None:
        e = _Env(per_user=2, owner_qa=10)
        for _ in range(4):  # nhiều hơn cả trần 2 lượt thường
            _, r = e.ask("owner", qa=True)
            self.assertEqual(r.status_code, 200, r.text)
        lim = e.avail("owner")["limits"]
        self.assertEqual((lim["requests_used"], lim["requests_remaining"], lim["exhausted"]), (0, 2, False))
        self.assertEqual(e.avail("owner")["qa"]["requests_used"], 4)
        # Lượt thường của Owner vẫn bị trần 2 lượt: lối QA không phải cửa sau để gửi nhiều hơn
        self.assertEqual(e.ask("owner")[1].status_code, 200)
        self.assertEqual(e.ask("owner")[1].status_code, 200)
        _, r = e.ask("owner")
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "user"))

    def test_owner_with_exhausted_normal_allowance_can_still_run_qa(self) -> None:
        e = _Env(per_user=1)
        self.assertEqual(e.ask("owner")[1].status_code, 200)
        self.assertEqual(e.ask("owner")[1].status_code, 429)
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)

    def test_qa_usage_event_reports_the_qa_lane_and_its_own_allowance(self) -> None:
        e = _Env(owner_qa=3)
        _, r = e.ask("owner", qa=True)
        usage = [d for n, d in _parse_sse_events(r.text) if n == "usage"][0]
        self.assertEqual(usage["lane"], "qa")
        self.assertEqual((usage["allowance"]["requests_used"], usage["allowance"]["requests_limit"],
                          usage["allowance"]["requests_remaining"]), (1, 3, 2))
        _, r2 = e.ask("owner")
        usage2 = [d for n, d in _parse_sse_events(r2.text) if n == "usage"][0]
        self.assertEqual((usage2["lane"], usage2["allowance"]["requests_used"], usage2["allowance"]["requests_limit"]),
                         ("user", 1, 5))

    def test_qa_has_its_own_cap_with_scope_qa_and_stores_nothing_when_rejected(self) -> None:
        e = _Env(owner_qa=2)
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        cid, r = e.ask("owner", qa=True)
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "qa"))
        self.assertEqual(e.stored(cid), 0)
        self.assertEqual(e.ask("owner")[1].status_code, 200, "hết QA không chặn lượt thường của Owner")

    def test_qa_cap_zero_closes_the_lane(self) -> None:
        e = _Env(owner_qa=0)
        _, r = e.ask("owner", qa=True)
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "qa"))

    def test_qa_counts_toward_the_global_total_and_cannot_pass_the_global_cap(self) -> None:
        e = _Env(global_cap=3, owner_qa=20)
        for _ in range(3):
            self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        self.assertEqual(e.plane.overview()["requests"], 3, "lượt QA nằm TRONG tổng toàn cục")
        _, r = e.ask("owner", qa=True)
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "global"))
        _, r2 = e.ask("alice")
        self.assertEqual((r2.status_code, _detail(r2)["scope"]), (429, "global"), "QA đã ăn hết trần toàn cục")

    def test_emergency_switch_stops_qa_too(self) -> None:
        e = _Env()
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        e.plane.update_controls("owner", {"ai_enabled": False})
        e.plane.invalidate()
        _, r = e.ask("owner", qa=True)
        self.assertEqual((r.status_code, _detail(r)["code"]), (503, "ai_not_enabled"))

    def test_non_owner_cannot_use_the_qa_lane_and_the_flag_is_silently_ignored(self) -> None:
        e = _Env(per_user=2)
        for _ in range(2):
            _, r = e.ask("alice", qa=True)
            self.assertEqual(r.status_code, 200)
            usage = [d for n, d in _parse_sse_events(r.text) if n == "usage"][0]
            self.assertEqual(usage["lane"], "user")
        lim = e.avail("alice")["limits"]
        self.assertEqual((lim["requests_used"], lim["exhausted"]), (2, True), "cờ qa của người thường tính như lượt thường")
        self.assertNotIn("qa", e.avail("alice"))
        _, r = e.ask("alice", qa=True)
        self.assertEqual((r.status_code, _detail(r)["scope"]), (429, "user"))

    def test_owner_qa_block_is_visible_only_to_owners(self) -> None:
        e = _Env(owner_qa=7)
        qa = e.avail("owner")["qa"]
        self.assertEqual((qa["requests_used"], qa["requests_limit"], qa["requests_remaining"], qa["exhausted"]),
                         (0, 7, 7, False))
        self.assertNotIn("qa", e.avail("alice"))

    def test_qa_flag_is_ignored_without_the_control_plane(self) -> None:
        e = _Env(control=False)
        _, r = e.ask("owner", qa=True)
        self.assertEqual(r.status_code, 200)
        usage = [d for n, d in _parse_sse_events(r.text) if n == "usage"][0]
        self.assertEqual(usage["lane"], "user")
        self.assertNotIn("qa", e.avail("owner"))

    def test_an_account_id_in_the_reserved_qa_prefix_can_never_share_the_qa_ledger(self) -> None:
        """Id thật do Appwrite sinh nên không có chuyện này; nếu có thì bị coi là ngoài khán giả ở MỌI route."""
        e = _Env()
        squatter = qa_ledger_user(OWNER)  # đúng khoá sổ QA của Owner
        self.assertFalse(e.rt.allows(squatter))
        self.assertTrue(e.rt.allows(OWNER))
        # `_resolve_profile` của test đặt tiền tố `user_` nên dựng đúng id bằng một hàm resolve riêng.
        from server.tests.test_ai_audience import _Profile
        app = FastAPI()
        app.include_router(build_ai_router(e.rt, resolve_profile=lambda a: _Profile(user_id=squatter)))
        c = TestClient(app)
        hdr = {"Authorization": "Bearer x"}
        self.assertEqual(c.post("/api/ai/conversations", json={"mode": "general"}, headers=hdr).status_code, 403)
        self.assertEqual(c.get("/api/ai/access", headers=hdr).json(), {"eligible": False})
        self.assertEqual(c.get("/api/ai/availability", headers=hdr).json()["reason"], "not_in_audience")

    def test_runtime_qa_lane_requires_owner_and_control_plane_and_the_request(self) -> None:
        plane = make_plane([slot("gemini-01")])
        rt = AiRuntime(True, owner_users=frozenset({OWNER}), control=plane)
        self.assertTrue(rt.qa_lane(OWNER, True))
        self.assertFalse(rt.qa_lane(OWNER, False))
        self.assertFalse(rt.qa_lane(ALICE, True))
        self.assertFalse(rt.qa_lane("", True))
        self.assertFalse(AiRuntime(True, owner_users=frozenset({OWNER})).qa_lane(OWNER, True))


class TestQaAccountingIsSeparate(unittest.TestCase):
    def test_active_users_excludes_the_qa_ledger_row_and_overview_shows_qa_usage(self) -> None:
        e = _Env(owner_qa=20)
        self.assertEqual(e.ask("owner")[1].status_code, 200)
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        self.assertEqual(e.ask("owner", qa=True)[1].status_code, 200)
        self.assertEqual(e.ask("alice")[1].status_code, 200)
        ov = e.plane.overview()
        self.assertEqual(ov["active_users"], 2, "owner + alice; dòng sổ QA không phải một người")
        self.assertEqual(ov["requests"], 4)
        self.assertEqual((ov["qa"]["requests"], ov["qa"]["per_owner_daily_cap"], ov["qa"]["owners"]), (2, 20, 1))
        self.assertGreater(ov["qa"]["tokens"], 0)

    def test_qa_writes_go_to_the_qa_ledger_key_not_the_users(self) -> None:
        from server.ai_assistant.limits import _today
        e = _Env()
        e.ask("owner", qa=True)
        self.assertIsNone(e.rt.repo.get_usage_day(OWNER, _today()))
        row = e.rt.repo.get_usage_day(qa_ledger_user(OWNER), _today())
        self.assertIsNotNone(row)
        self.assertEqual(row.requests, 1)

    def test_overview_without_qa_source_has_null_qa(self) -> None:
        plane = make_plane([slot("gemini-01")])
        self.assertIsNone(plane.overview()["qa"])


class TestQaSettings(unittest.TestCase):
    def _cap(self, value: str | None) -> int:
        env = {} if value is None else {"FAS_AI_OWNER_QA_DAILY_REQUESTS": value}
        with mock.patch.dict(os.environ, env, clear=False):
            if value is None:
                os.environ.pop("FAS_AI_OWNER_QA_DAILY_REQUESTS", None)
            return _ai_assistant_settings().owner_qa_daily_requests

    def test_default_and_bounds_and_garbage_never_crash_startup(self) -> None:
        self.assertEqual(self._cap(None), AI_OWNER_QA_DAILY_REQUESTS_DEFAULT)
        self.assertEqual(self._cap(""), AI_OWNER_QA_DAILY_REQUESTS_DEFAULT)
        self.assertEqual(self._cap("35"), 35)
        self.assertEqual(self._cap("0"), 0)
        self.assertEqual(self._cap("-4"), 0)
        self.assertEqual(self._cap("99999"), AI_OWNER_QA_DAILY_REQUESTS_MAX)
        self.assertEqual(self._cap("abc"), AI_OWNER_QA_DAILY_REQUESTS_DEFAULT)

    def test_qa_cap_is_not_a_stored_control_field(self) -> None:
        """Thêm cột Appwrite mới vào `ai_control_settings` mà chưa tạo cột trên production sẽ làm hỏng MỌI lần ghi
        cấu hình (kể cả nút tắt khẩn cấp) — nên hạn mức QA là biến môi trường, không phải trường lưu."""
        from server.ai_assistant.control.model import CONTROL_FIELDS, GlobalControls, controls_to_dict
        self.assertFalse([f for f in CONTROL_FIELDS if "qa" in f])
        self.assertFalse([k for k in controls_to_dict(GlobalControls()) if "qa" in k])


if __name__ == "__main__":
    unittest.main()

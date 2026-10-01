"""
Hồi quy ĐẦU-CUỐI của Trợ lý AI trên đúng đường chạy production: router thật (`build_ai_router`) + runtime thật
(`build_ai_runtime`) + control plane thật (`ControlPlane`, `ControlledGateway`, hạn mức, cooldown, kill switch) +
sổ đếm thật (trong bộ nhớ). CHỈ nhà cung cấp là giả có kịch bản — nên KHÔNG tốn một lượt Gemini nào.

Năm "nhân vật" (persona): khách vãng lai, người dùng thường, Owner/Admin, người dùng đã HẾT lượt, và Owner chạy
lối QA. Mọi khẳng định bảo mật đi qua API trực tiếp (không chỉ ở lớp giao diện).

Lớp: route matrix | luồng người dùng thường | kiểm đầu vào | hạn mức + đổi ngày | số đếm lối QA | kill switch +
trần toàn cục + audit | lỗi nhà cung cấp / dự phòng | dừng giữa chừng (socket thật) | cô lập người dùng +
đăng xuất | không rò rỉ ra client.
"""
from __future__ import annotations

import json
import random
import socket
import threading
import time
import unittest
from dataclasses import replace
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from unittest import mock

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.control.admin_routes import build_ai_admin_router
from server.ai_assistant.control.model import GlobalControls
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlPlane
from server.ai_assistant.control.store import InMemoryControlStore
from server.ai_assistant.limits import qa_ledger_user
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime, build_ai_runtime
from server.config import AiAssistantSettings, Settings
from server.llm_gateway.chat_provider import (
    ChatProvider, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities, ProviderError,
    ProviderUsageSnapshot, UsageEvent,
)
from server.llm_gateway.usage_limits import CircuitBreaker
from server.tests.test_ai_admin_api import owner as _admin_owner
from server.tests.test_ai_admin_api import reader as _admin_reader
from server.tests.test_ai_control_plane import FAKE_KEY, Clock, env_for, slot
from server.tests.test_ai_routes import _parse_sse_events

ALL_TYPES = ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")
DAY_1, DAY_2 = "20261002", "20261003"


class Prov(ChatProvider):
    """Nhà cung cấp giả có kịch bản. Mỗi lần gọi lấy một bước từ `script` (hết thì dùng `default`):
    "ok" | một ngoại lệ (lỗi TRƯỚC delta đầu) | ("after", err) (một delta rồi lỗi) | ("slow_fail", giây, err) (treo
    `giây` giây rồi lỗi trước delta đầu) | "empty" (trả lời THÀNH CÔNG nhưng RỖNG, vd. bị lọc nội dung: chỉ `usage` +
    `Done`, không có token chữ nào)."""

    def __init__(self, name: str, *, script: Sequence[Any] = (), default: Any = "ok", words: int = 3,
                 delay: float = 0.0) -> None:
        self.name = name
        self.script = list(script)
        self.default = default
        self.words = words
        self.delay = delay
        self.requests: List[GenerateRequest] = []
        self.closed = 0
        #: `generate()` chỉ dùng cho probe của Owner (không bao giờ cho lượt của người dùng).
        self.probed = 0
        self.probe_error: Optional[BaseException] = None
        self._lock = threading.Lock()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False, max_context_tokens=8000)

    def generate(self, req: GenerateRequest) -> GenerateResult:
        with self._lock:
            self.probed += 1
        if self.probe_error is not None:
            raise self.probe_error
        return GenerateResult(text="OK", provider_name=self.name, model=req.model, input_tokens=3, output_tokens=1)

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(requests=len(self.requests))

    def stream(self, req: GenerateRequest) -> Iterator[Any]:
        with self._lock:
            self.requests.append(req)
            step = self.script.pop(0) if self.script else self.default
        try:
            if isinstance(step, BaseException):
                raise step
            if isinstance(step, tuple) and step[0] == "slow_fail":  # chờ rồi lỗi TRƯỚC delta đầu (nhà cung cấp treo)
                time.sleep(step[1])
                raise step[2]
            if isinstance(step, tuple) and step[0] == "after":
                yield Delta(text=f"từ {self.name} ")
                raise step[1]
            if step == "empty":
                yield UsageEvent(input_tokens=10, output_tokens=0)
                yield Done()
                return
            for i in range(self.words):
                if self.delay:
                    time.sleep(self.delay)
                yield Delta(text=f"từ{i} ")
            yield UsageEvent(input_tokens=10, output_tokens=5)
            yield Done()
        finally:
            with self._lock:
                self.closed += 1


class _Profile:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.tier = "free"


class World:
    """Một "site" nhỏ: N slot Gemini (cùng bậc ưu tiên như production), control plane với trần 5/150, runtime thật."""

    def __init__(self, *, slots: int = 3, disabled: Sequence[str] = (), per_user: int = 5, global_cap: int = 150,
                 owner_qa: int = 20, scripts: Optional[Dict[str, Sequence[Any]]] = None, delay: float = 0.0,
                 words: int = 3, slot_kw: Optional[Dict[str, Any]] = None, clk: Optional[Clock] = None,
                 prio: Optional[Dict[str, int]] = None) -> None:
        self.clk = clk or Clock()
        self.revoked: set = set()
        ids = [f"gemini-0{i}" for i in range(1, slots + 1)]
        kw = dict(priority=10, weight=10)
        kw.update(slot_kw or {})
        #: `prio` đặt bậc ưu tiên riêng từng slot để thứ tự thử là TẤT ĐỊNH (cùng bậc thì thứ tự là ngẫu nhiên có trọng số).
        self.slots = [slot(sid, enabled=sid not in disabled, **{**kw, **({"priority": prio[sid]} if prio and sid in prio else {})})
                      for sid in ids]
        self.provs: Dict[str, Prov] = {
            sid: Prov(sid, script=(scripts or {}).get(sid, ()), delay=delay, words=words) for sid in ids}
        store = InMemoryControlStore()
        store.controls = GlobalControls(ai_enabled=True, provider_types={t: True for t in ALL_TYPES}, version=1)
        for s in self.slots:
            store.slots[s.slot_id] = s
        self.store = store
        self.plane = ControlPlane(
            store, secrets=SecretResolver(env_for(*self.slots)),
            factory=ProviderFactory(builder=lambda s, k: self.provs[s.slot_id]),
            breaker=CircuitBreaker(clock_fn=self.clk), clock=self.clk, rng=random.Random(11))
        self.plane.update_controls("owner", {"per_user_daily_request_cap": per_user,
                                             "global_daily_request_cap": global_cap})
        ai = AiAssistantSettings(enabled=True, providers=("mock",), audience="all", rpm=1000, max_streams=8,
                                 owner_qa_daily_requests=owner_qa)
        self.settings = replace(Settings(), owner_user_ids=("user_owner",), ai_assistant=ai)
        self.rt: AiRuntime = build_ai_runtime(self.settings, control=self.plane)
        self.app = FastAPI()
        #: Giữ riêng `APIRouter` để liệt kê route: `FastAPI.routes` gói chúng trong `_IncludedRouter` (không có `path`).
        self.ai_router = build_ai_router(self.rt, resolve_profile=self._resolve)
        self.app.include_router(self.ai_router)
        self.app.include_router(build_ai_admin_router(self.plane, reader=_admin_reader, owner=_admin_owner))
        self.c = TestClient(self.app)
        self._n = 0

    def _resolve(self, authorization: Optional[str]) -> _Profile:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
        tok = authorization.split(" ", 1)[1].strip()
        if not tok or tok in self.revoked:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Phiên đã hết hạn.")
        return _Profile(f"user_{tok}")

    # ---- thao tác
    @staticmethod
    def hdr(tok: Optional[str]) -> Dict[str, str]:
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def conv(self, tok: str, mode: str = "general", **body: Any) -> str:
        r = self.c.post("/api/ai/conversations", headers=self.hdr(tok), json={"mode": mode, **body})
        assert r.status_code == 200, r.text
        return r.json()["conversation_id"]

    def ask(self, tok: str, text: str = "xin chào", *, cid: Optional[str] = None, mode: str = "general",
            qa: bool = False, **extra: Any) -> Tuple[str, Any]:
        cid = cid or self.conv(tok, mode)
        self._n += 1
        body: Dict[str, Any] = {"content": text, "client_id": f"c{self._n}", **extra}
        if qa:
            body["qa"] = True
        return cid, self.c.post(f"/api/ai/conversations/{cid}/messages", headers=self.hdr(tok), json=body)

    def avail(self, tok: str) -> Dict[str, Any]:
        return self.c.get("/api/ai/availability", headers=self.hdr(tok)).json()

    def messages(self, cid: str) -> List[Any]:
        return self.rt.repo.list_messages(cid, limit=50)

    def per_slot(self) -> Dict[str, int]:
        return {k: v.requests for k, v in self.plane.usage_today().items() if v.requests}

    def calls(self) -> Dict[str, int]:
        return {sid: len(p.requests) for sid, p in self.provs.items() if p.requests}

    def set_controls(self, **patch: Any) -> None:
        self.plane.update_controls("owner", patch)
        self.plane.invalidate()


def events(resp: Any) -> List[Tuple[str, Dict[str, Any]]]:
    return _parse_sse_events(resp.text)


def kinds(resp: Any) -> List[str]:
    return [n for n, _ in events(resp)]


def ev(resp: Any, name: str) -> List[Dict[str, Any]]:
    return [d for n, d in events(resp) if n == name]


def detail(resp: Any) -> Dict[str, Any]:
    return resp.json()["detail"]


# ======================================================================================== route matrix

#: Mỗi route AI + một thân HỢP LỆ tối thiểu (để 401 chứng minh xác thực chạy TRƯỚC mọi thứ, không phải 422 che mất).
ROUTE_BODIES: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {
    ("GET", "/api/ai/access"): None,
    ("GET", "/api/ai/availability"): None,
    ("GET", "/api/ai/conversations"): None,
    ("POST", "/api/ai/conversations"): {"mode": "general"},
    ("GET", "/api/ai/conversations/{conversation_id}"): None,
    ("DELETE", "/api/ai/conversations/{conversation_id}"): None,
    ("POST", "/api/ai/conversations/{conversation_id}/messages"): {"content": "hi", "client_id": "c"},
    ("GET", "/api/ai/preferences"): None,
    ("PUT", "/api/ai/preferences"): {"memory_enabled": True, "preferences": {}},
    ("DELETE", "/api/ai/memory"): None,
    ("GET", "/api/ai/projects"): None,
    ("POST", "/api/ai/projects"): {"title": "t"},
    ("GET", "/api/ai/projects/{project_id}"): None,
    ("PUT", "/api/ai/projects/{project_id}"): {"title": "t"},
    ("DELETE", "/api/ai/projects/{project_id}"): None,
    ("POST", "/api/ai/support/escalations"): {"summary": "s"},
}


def _ai_routes(router: Any) -> List[Tuple[str, str]]:
    out = []
    for r in router.routes:
        p = getattr(r, "path", "")
        if p.startswith("/api/ai/"):
            for m in sorted(set(getattr(r, "methods", ()) or ()) - {"HEAD", "OPTIONS"}):
                out.append((m, p))
    return out


class TestRouteMatrix(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World(slots=1)

    def test_every_ai_route_is_in_the_matrix_so_a_new_route_cannot_skip_the_auth_check(self) -> None:
        self.assertEqual(set(_ai_routes(self.w.ai_router)), set(ROUTE_BODIES),
                         "route AI mới phải được thêm vào ROUTE_BODIES (và qua cổng xác thực)")

    def test_anonymous_gets_401_on_every_ai_route_server_side(self) -> None:
        for (method, path), body in sorted(ROUTE_BODIES.items()):
            with self.subTest(route=f"{method} {path}"):
                url = path.replace("{conversation_id}", "c1").replace("{project_id}", "p1")
                kw: Dict[str, Any] = {"json": body} if body is not None else {}
                r = self.w.c.request(method, url, **kw)
                self.assertEqual(r.status_code, 401, r.text)

    def test_garbage_credentials_are_401_not_500(self) -> None:
        for hdr in ({"Authorization": "Basic abc"}, {"Authorization": "Bearer "}, {"Authorization": "Bearer"},
                    {"Authorization": ""}):
            with self.subTest(hdr=hdr):
                self.assertEqual(self.w.c.get("/api/ai/availability", headers=hdr).status_code, 401)
                self.assertEqual(self.w.c.get("/api/ai/conversations", headers=hdr).status_code, 401)

    def test_anonymous_cannot_probe_admin_routes_either(self) -> None:
        for p in ("/api/admin/ai/config", "/api/admin/ai/overview", "/api/admin/ai/audit"):
            self.assertEqual(self.w.c.get(p).status_code, 401, p)
        self.assertEqual(self.w.c.put("/api/admin/ai/global", json={"ai_enabled": False}).status_code, 401)
        self.assertTrue(self.w.plane.enabled(), "một yêu cầu ẩn danh không được tắt AI")


# ======================================================================================== normal user

class TestNormalUserFlows(unittest.TestCase):
    def test_general_turn_streams_in_order_and_persists_both_messages(self) -> None:
        w = World()
        cid, r = w.ask("alice")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(kinds(r), ["meta", "delta", "delta", "delta", "usage", "done"])
        self.assertEqual(ev(r, "done")[0]["status"], "complete")
        self.assertEqual("".join(d["text"] for d in ev(r, "delta")), "từ0 từ1 từ2 ")
        msgs = w.messages(cid)
        self.assertEqual([(m.role, m.status) for m in msgs], [("user", "complete"), ("assistant", "complete")])
        self.assertEqual(msgs[1].content, "từ0 từ1 từ2 ")
        self.assertEqual(sum(w.per_slot().values()), 1, "đúng MỘT slot phục vụ và được tính")

    def test_history_exposes_only_the_documented_message_fields(self) -> None:
        w = World()
        cid, _ = w.ask("alice")
        got = w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).json()
        self.assertEqual(set(got), {"conversation_id", "mode", "title", "ephemeral", "messages"})
        for m in got["messages"]:
            self.assertEqual(set(m), {"message_id", "role", "content", "status", "citations", "created_at"})
        listing = w.c.get("/api/ai/conversations", headers=w.hdr("alice")).json()["items"]
        self.assertEqual([(i["conversation_id"], i["message_count"]) for i in listing], [(cid, 2)])
        self.assertEqual(set(listing[0]),
                         {"conversation_id", "mode", "title", "created_at", "updated_at", "message_count", "ephemeral"})

    def test_continuing_a_conversation_sends_the_earlier_turns_to_the_provider_in_order(self) -> None:
        w = World(slots=1)
        cid, _ = w.ask("alice", "câu hỏi thứ nhất")
        w.ask("alice", "câu hỏi thứ hai", cid=cid)
        last = w.provs["gemini-01"].requests[-1].messages
        texts = [t.content for t in last if t.role in ("user", "assistant")]
        self.assertEqual(texts, ["câu hỏi thứ nhất", "từ0 từ1 từ2 ", "câu hỏi thứ hai"])
        self.assertEqual([t.role for t in last][-3:], ["user", "assistant", "user"])
        self.assertEqual(len(w.messages(cid)), 4)

    def test_vietnamese_text_round_trips_byte_for_byte(self) -> None:
        w = World(slots=1)
        text = "Xin chào! Tôi muốn hỏi: “Đêm trăng” ở chương 12 có ý nghĩa gì? 😀 — ừ, đúng rồi · Ế ề ể ễ ệ"
        cid, r = w.ask("alice", text)
        self.assertEqual(r.status_code, 200)
        got = w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).json()["messages"][0]["content"]
        self.assertEqual(got, text)
        sent = [t.content for t in w.provs["gemini-01"].requests[-1].messages if t.role == "user"][-1]
        self.assertEqual(sent, text)
        nfd = __import__("unicodedata").normalize("NFD", "Đường về nhà")
        cid2, r2 = w.ask("alice", nfd)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(w.c.get(f"/api/ai/conversations/{cid2}", headers=w.hdr("alice")).json()["messages"][0]["content"], nfd)

    def test_length_limit_counts_characters_not_bytes(self) -> None:
        w = World(slots=1)
        ok = "ế" * 4000  # 12.000 byte UTF-8, 4000 ký tự
        self.assertEqual(w.ask("alice", ok)[1].status_code, 200)
        r = w.ask("alice", ok + "ế")[1]
        self.assertEqual(r.status_code, 422)

    def test_delete_conversation_then_it_is_gone(self) -> None:
        w = World()
        cid, _ = w.ask("alice")
        self.assertEqual(w.c.delete(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).json(), {"deleted": True})
        self.assertEqual(w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).status_code, 404)
        self.assertEqual(w.c.get("/api/ai/conversations", headers=w.hdr("alice")).json()["items"], [])

    def test_regenerate_is_a_new_charged_request_with_exactly_one_new_assistant_reply(self) -> None:
        w = World(slots=1)
        cid, r1 = w.ask("alice", "hỏi")
        first_id = ev(r1, "meta")[0]["message_id"]
        _, r2 = w.ask("alice", "hỏi", cid=cid, regenerate_of=first_id)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(sum(1 for m in w.messages(cid) if m.role == "assistant"), 2)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 2, "tạo lại tốn đúng một lượt, không hơn không kém")
        self.assertEqual(sum(w.per_slot().values()), 2)

    def test_support_story_and_writer_modes_are_all_served_by_the_gemini_pool(self) -> None:
        w = World()
        for mode in ("general", "support", "story", "writer"):
            with self.subTest(mode=mode):
                _, r = w.ask("alice" if mode != "writer" else "bob", f"hỏi {mode}", mode=mode)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(ev(r, "done")[0]["status"], "complete", r.text)
                self.assertEqual(ev(r, "error"), [])

    def test_story_mode_without_a_readable_chapter_says_so_instead_of_inventing(self) -> None:
        w = World(slots=1)
        _, r = w.ask("alice", "chương này nói gì?", mode="story")
        self.assertEqual(r.status_code, 200)
        system = " ".join(t.content for t in w.provs["gemini-01"].requests[-1].messages if t.role == "system")
        self.assertIn("chương", system.lower())

    def test_project_crud_is_private_to_its_owner(self) -> None:
        w = World()
        pid = w.c.post("/api/ai/projects", headers=w.hdr("alice"), json={"title": "Truyện của A", "premise": "bí mật"}).json()["project_id"]
        self.assertEqual(w.c.get(f"/api/ai/projects/{pid}", headers=w.hdr("alice")).json()["premise"], "bí mật")
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                kw = {"json": {"title": "x"}} if method == "put" else {}
                r = getattr(w.c, method)(f"/api/ai/projects/{pid}", headers=w.hdr("bob"), **kw)
                self.assertEqual((r.status_code, detail(r)["code"]), (403, "ai_forbidden"))
        self.assertEqual(w.c.get("/api/ai/projects", headers=w.hdr("bob")).json()["items"], [])
        self.assertEqual(w.c.get(f"/api/ai/projects/{pid}", headers=w.hdr("alice")).json()["title"], "Truyện của A")


# ======================================================================================== input validation

class TestInputValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World(slots=1)
        self.cid = self.w.conv("alice")

    def post(self, body: Any, tok: str = "alice", cid: Optional[str] = None) -> Any:
        return self.w.c.post(f"/api/ai/conversations/{cid or self.cid}/messages", headers=self.w.hdr(tok), json=body)

    def test_empty_and_whitespace_only_messages_are_rejected_before_any_quota_or_provider_work(self) -> None:
        for content in ("", " ", "   \n\t  ", " ", "　"):
            with self.subTest(content=repr(content)):
                r = self.post({"content": content, "client_id": "c"})
                self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(self.w.provs["gemini-01"].requests, [], "không được gọi nhà cung cấp cho tin rỗng")
        self.assertEqual(self.w.avail("alice")["limits"]["requests_used"], 0, "tin rỗng không được tốn lượt")
        self.assertEqual(self.w.messages(self.cid), [], "tin rỗng không được lưu")

    def test_malformed_bodies_are_422_never_500(self) -> None:
        bad: List[Any] = [
            {}, {"content": "hi"}, {"client_id": "c"}, {"content": 123, "client_id": "c"},
            {"content": None, "client_id": "c"}, {"content": "hi", "client_id": ""},
            {"content": "hi", "client_id": "x" * 65}, {"content": "hi", "client_id": "c", "qa": "maybe"},
            {"content": "hi", "client_id": "c", "use_web_search": "perhaps"}, [], "một chuỗi", 7, None,
        ]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 422)
        r = self.w.c.post(f"/api/ai/conversations/{self.cid}/messages", headers={**self.w.hdr("alice"), "Content-Type": "application/json"},
                          content=b"{khong phai json")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.w.provs["gemini-01"].requests, [])

    def test_unknown_and_malicious_conversation_ids(self) -> None:
        for bad in ("a b", "x" * 65, "c1;drop", "%00", "a.b", "../x"):
            with self.subTest(cid=bad):
                self.assertIn(self.post({"content": "hi", "client_id": "c"}, cid=bad).status_code, (404, 422))
        r = self.post({"content": "hi", "client_id": "c"}, cid="khongtontai")
        self.assertEqual((r.status_code, detail(r)["code"]), (404, "ai_not_found"))

    def test_extra_fields_cannot_choose_the_provider_model_or_slot(self) -> None:
        r = self.post({"content": "xin chào", "client_id": "c", "model": "gpt-9", "provider": "openai",
                       "slot": "gemini-09", "role": "system", "workload": "web_search", "profile": "QUALITY_FIRST",
                       "max_output_tokens": 999999, "temperature": 2.0})
        self.assertEqual(r.status_code, 200, r.text)
        req = self.w.provs["gemini-01"].requests[-1]
        self.assertEqual(req.model, "gemini-model", "model do control plane quyết, không phải do người dùng")
        self.assertLessEqual(req.max_output_tokens, 800)
        self.assertEqual([t.role for t in req.messages if t.role == "user"], ["user"])

    def test_oversized_side_inputs_are_bounded(self) -> None:
        w = self.w
        too_big = {"memory_enabled": True, "preferences": {"k": "x" * 2500}}
        r = w.c.put("/api/ai/preferences", headers=w.hdr("alice"), json=too_big)
        self.assertEqual((r.status_code, detail(r)["code"]), (400, "ai_context_too_large"))
        self.assertEqual(w.c.post("/api/ai/conversations", headers=w.hdr("alice"), json={"mode": "general", "title": "t" * 121}).status_code, 422)
        self.assertEqual(w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"), json={"summary": "s" * 2001}).status_code, 422)

    def test_invalid_mode_falls_back_to_general_and_never_reaches_a_missing_profile(self) -> None:
        cid = self.w.conv("alice", "khong-co-mode")
        got = self.w.c.get(f"/api/ai/conversations/{cid}", headers=self.w.hdr("alice")).json()
        self.assertEqual(got["mode"], "general")
        self.assertEqual(self.w.ask("alice", cid=cid)[1].status_code, 200)

    def test_secret_shaped_text_is_redacted_before_storage_and_provider(self) -> None:
        secret = "sk-" + "abcdefgh" * 3  # ghép lúc chạy (quy ước .gitleaks.toml), cùng mẫu bộ che đã được kiểm
        cid, r = self.w.ask("alice", f"khoá của tôi là Bearer {secret} nhé")
        self.assertEqual(r.status_code, 200)
        stored = self.w.messages(cid)[0].content
        sent = [t.content for t in self.w.provs["gemini-01"].requests[-1].messages if t.role == "user"][-1]
        self.assertNotIn(secret, stored)
        self.assertNotIn(secret, sent)


# ======================================================================================== quota + daily reset

class TestQuotaAndDailyReset(unittest.TestCase):
    def test_normal_user_gets_exactly_five_requests_then_a_user_scoped_429(self) -> None:
        w = World()
        for n in range(1, 6):
            self.assertEqual(w.ask("alice")[1].status_code, 200, n)
            self.assertEqual(w.avail("alice")["limits"]["requests_remaining"], 5 - n)
        cid, r = w.ask("alice")
        self.assertEqual((r.status_code, detail(r)["code"], detail(r)["scope"]), (429, "ai_budget_exhausted", "user"))
        self.assertTrue(detail(r)["reset_at"])
        self.assertEqual(w.messages(cid), [], "tin bị từ chối không được lưu (giao diện hiện 'Chưa gửi')")
        self.assertTrue(w.avail("alice")["limits"]["exhausted"])
        self.assertEqual(sum(w.per_slot().values()), 5)

    def test_exhausted_user_cannot_bypass_with_new_conversations_modes_regenerate_or_a_qa_flag(self) -> None:
        w = World()
        for _ in range(5):
            w.ask("alice")
        attempts = [
            w.ask("alice")[1], w.ask("alice", mode="support")[1], w.ask("alice", mode="story")[1],
            w.ask("alice", qa=True)[1], w.ask("alice", regenerate_of="whatever")[1],
            w.ask("alice", use_web_search=True)[1], w.ask("alice", use_library=True)[1],
        ]
        for r in attempts:
            self.assertEqual((r.status_code, detail(r)["scope"]), (429, "user"))
        self.assertEqual(sum(w.per_slot().values()), 5)
        self.assertEqual(w.calls().values() and sum(w.calls().values()), 5, "không lượt bị từ chối nào chạm tới nhà cung cấp")

    def test_exhausted_user_can_still_read_history_and_other_users_are_unaffected(self) -> None:
        w = World()
        cid = None
        for _ in range(5):
            cid, _r = w.ask("alice", cid=cid)
        self.assertEqual(w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).status_code, 200)
        self.assertEqual(w.c.get("/api/ai/conversations", headers=w.hdr("alice")).status_code, 200)
        self.assertEqual(w.ask("bob")[1].status_code, 200)
        self.assertEqual(w.avail("bob")["limits"]["requests_remaining"], 4)

    def test_daily_reset_restores_the_allowance_and_keeps_yesterdays_ledger(self) -> None:
        w = World()
        with mock.patch("server.ai_assistant.limits._today", return_value=DAY_1), \
                mock.patch("server.ai_assistant.control.service.today_utc", return_value=DAY_1):
            for _ in range(5):
                self.assertEqual(w.ask("alice")[1].status_code, 200)
            self.assertEqual(w.ask("alice")[1].status_code, 429)
            self.assertTrue(w.avail("alice")["limits"]["exhausted"])
        with mock.patch("server.ai_assistant.limits._today", return_value=DAY_2), \
                mock.patch("server.ai_assistant.control.service.today_utc", return_value=DAY_2):
            lim = w.avail("alice")["limits"]
            self.assertEqual((lim["requests_used"], lim["requests_remaining"], lim["exhausted"]), (0, 5, False))
            self.assertEqual(w.ask("alice")[1].status_code, 200)
            self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1)
            self.assertEqual(sum(w.per_slot().values()), 1, "bộ đếm toàn cục cũng sang ngày mới")
        self.assertEqual(w.rt.repo.get_usage_day("user_alice", DAY_1).requests, 5, "sổ hôm qua giữ nguyên")

    def test_global_cap_also_resets_at_the_day_boundary(self) -> None:
        w = World(global_cap=2)
        with mock.patch("server.ai_assistant.limits._today", return_value=DAY_1), \
                mock.patch("server.ai_assistant.control.service.today_utc", return_value=DAY_1):
            self.assertEqual(w.ask("alice")[1].status_code, 200)
            self.assertEqual(w.ask("bob")[1].status_code, 200)
            r = w.ask("carol")[1]
            self.assertEqual((r.status_code, detail(r)["scope"]), (429, "global"))
        with mock.patch("server.ai_assistant.limits._today", return_value=DAY_2), \
                mock.patch("server.ai_assistant.control.service.today_utc", return_value=DAY_2):
            self.assertEqual(w.ask("carol")[1].status_code, 200)

    def test_public_caps_are_five_per_user_and_one_hundred_fifty_global_by_preset(self) -> None:
        from server.ai_assistant.control.model import ROLLOUT_PRESETS
        self.assertEqual(ROLLOUT_PRESETS["beta"]["per_user_daily_request_cap"], 5)
        self.assertEqual(ROLLOUT_PRESETS["beta"]["global_daily_request_cap"], 150)
        w = World()
        w.plane.apply_preset("owner", "beta") if hasattr(w.plane, "apply_preset") else None
        c = w.plane.snapshot().controls
        self.assertEqual((c.per_user_daily_request_cap, c.global_daily_request_cap), (5, 150))


# ======================================================================================== disconnects (socket thật)

class _LiveServer:
    """uvicorn thật trên một luồng: TestClient gom cả luồng SSE nên không mô phỏng được client ngắt giữa chừng."""

    def __init__(self, app: FastAPI) -> None:
        import uvicorn
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(300):
            if getattr(self.server, "started", False):
                break
            time.sleep(0.02)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def raw_post(self, path: str, tok: str, body: Dict[str, Any], *, read_until: Optional[bytes],
                 linger: float = 0.0) -> bytes:
        """Gửi một POST rồi ĐÓNG socket: sau khi đọc tới `read_until`, hoặc sau `linger` giây nếu không đọc gì."""
        payload = json.dumps(body).encode()
        req = (f"POST {path} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {tok}\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode() + payload
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        got = b""
        try:
            s.sendall(req)
            if read_until is not None:
                end = time.time() + 5
                while read_until not in got and time.time() < end:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    got += chunk
            else:
                time.sleep(linger)
        finally:
            s.close()
        return got


class TestDisconnectsRealServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.w = World(slots=1, delay=0.35, words=40, per_user=5)
        cls.live = _LiveServer(cls.w.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.live.close()

    def create(self, tok: str) -> str:
        r = httpx.post(f"{self.live.base}/api/ai/conversations", headers=self.w.hdr(tok), json={"mode": "general"}, timeout=10)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["conversation_id"]

    def allowance(self, tok: str) -> Dict[str, Any]:
        return httpx.get(f"{self.live.base}/api/ai/availability", headers=self.w.hdr(tok), timeout=10).json()["limits"]

    def wait_idle(self, timeout: float = 8.0) -> bool:
        end = time.time() + timeout
        g = self.w.rt.stream_guard
        while time.time() < end:
            if g._total == 0 and not g._per_user:  # noqa: SLF001
                time.sleep(0.15)
                if g._total == 0:  # noqa: SLF001
                    return True
            time.sleep(0.05)
        return False

    def test_stop_after_the_first_token_records_partial_text_usage_once_and_frees_the_stream(self) -> None:
        w, tok = self.w, "stop1"
        cid = self.create(tok)
        got = self.live.raw_post(f"/api/ai/conversations/{cid}/messages", tok,
                                 {"content": "một câu hỏi dài", "client_id": "cs"}, read_until=b"event: delta")
        self.assertIn(b"event: delta", got)
        self.assertTrue(self.wait_idle(), "luồng phải được giải phóng sau khi client ngắt")
        asst = [m for m in w.messages(cid) if m.role == "assistant"]
        self.assertEqual([m.status for m in asst], ["stopped"])
        self.assertTrue(asst[0].content.strip(), "phần văn bản đã sinh phải được giữ lại")
        self.assertEqual(self.allowance(tok)["requests_used"], 1, "dừng giữa chừng tính ĐÚNG một lượt")
        self.assertEqual(w.rt.repo.get_usage_day(f"user_{tok}", __import__("server.ai_assistant.limits", fromlist=["_today"])._today()).requests, 1)
        self.assertGreaterEqual(w.provs["gemini-01"].closed, 1, "generator của nhà cung cấp phải được đóng")
        # luồng đã trống: người này gửi tiếp được ngay
        r = httpx.post(f"{self.live.base}/api/ai/conversations/{cid}/messages", headers=w.hdr(tok),
                       json={"content": "tiếp", "client_id": "cs2"}, timeout=20)
        self.assertEqual(r.status_code, 200, r.text)

    def test_abort_before_the_first_token_still_costs_one_request_and_cannot_be_looped(self) -> None:
        """F1: ngắt SAU `meta`, TRƯỚC token đầu. Nhà cung cấp đã bị gọi, nên phải tính một lượt; nếu không, một script
        gửi-rồi-ngắt lặp vô hạn (ở mức RPM) sẽ rút quota nhà cung cấp mà không bao giờ chạm trần 5 lượt/ngày."""
        w, tok = self.w, "abort1"
        before = len(w.provs["gemini-01"].requests)
        for n in range(1, 6):
            cid = self.create(tok)
            got = self.live.raw_post(f"/api/ai/conversations/{cid}/messages", tok,
                                     {"content": f"gửi rồi ngắt {n}", "client_id": f"ca{n}"}, read_until=b"event: meta")
            self.assertIn(b"event: meta", got)
            self.assertNotIn(b"event: delta", got, "phải ngắt trước token đầu")
            self.assertTrue(self.wait_idle())
            self.assertEqual(self.allowance(tok)["requests_used"], n, f"lần ngắt {n} phải tốn một lượt")
        self.assertTrue(self.allowance(tok)["exhausted"])
        self.assertEqual(len(w.provs["gemini-01"].requests) - before, 5)
        cid = self.create(tok)
        r = httpx.post(f"{self.live.base}/api/ai/conversations/{cid}/messages", headers=w.hdr(tok),
                       json={"content": "lần thứ sáu", "client_id": "ca6"}, timeout=10)
        self.assertEqual((r.status_code, r.json()["detail"]["scope"]), (429, "user"))
        self.assertEqual(len(w.provs["gemini-01"].requests) - before, 5, "lượt thứ sáu không được chạm tới nhà cung cấp")

    def test_abort_before_the_first_token_is_attributed_to_the_slot_that_was_called_exactly_once(self) -> None:
        """Client ngắt lúc nhà cung cấp CHƯA trả byte nào: slot ĐANG BỊ GỌI (gateway báo `on_attempt` ngay trước lời gọi) vẫn
        phải bị đếm đúng MỘT lượt vào bộ đếm slot — chính là trần toàn cục — và không bao giờ đếm thừa. Trước đây lượt này
        chỉ trừ sổ người dùng, nên N tài khoản x 5 lượt gửi-rồi-ngắt gọi nhà cung cấp mà không chạm trần 150."""
        w, tok = self.w, "abort2"
        base = w.per_slot().get("gemini-01", 0)
        cid = self.create(tok)
        self.live.raw_post(f"/api/ai/conversations/{cid}/messages", tok,
                           {"content": "ngắt sớm", "client_id": "cb1"}, read_until=b"event: meta")
        self.assertTrue(self.wait_idle())
        self.assertEqual(w.per_slot().get("gemini-01", 0) - base, 1)
        self.assertEqual(self.allowance(tok)["requests_used"], 1)

    def test_client_that_vanishes_during_preparation_does_not_leak_the_stream_guard(self) -> None:
        """F2: client đóng kết nối trong lúc máy chủ còn đang chuẩn bị (đã giữ khoá luồng, chưa trả response).
        Khoá luồng PHẢI được nhả, nếu không người đó (và sau 4 lần, cả instance) nhận `ai_busy` cho tới khi restart."""
        w = self.w
        real = w.rt.repo.create_message

        def slow(m: Any) -> Any:
            time.sleep(0.4)
            return real(m)

        with mock.patch.object(w.rt.repo, "create_message", side_effect=slow):
            for i, linger in enumerate((0.0, 0.05, 0.15, 0.3)):
                tok = f"vanish{i}"
                cid = self.create(tok)
                self.live.raw_post(f"/api/ai/conversations/{cid}/messages", tok,
                                   {"content": f"biến mất {i}", "client_id": f"cv{i}"}, read_until=None, linger=linger)
                self.assertTrue(self.wait_idle(10.0), f"khoá luồng bị rò khi client ngắt sau {linger}s (_total="
                                                      f"{w.rt.stream_guard._total}, per_user={dict(w.rt.stream_guard._per_user)})")  # noqa: SLF001
        self.assertEqual(w.rt.stream_guard._total, 0)  # noqa: SLF001


class TestAbortedTurnsCountTowardsTheGlobalCeiling(unittest.TestCase):
    """Lỗ hổng reviewer tìm ra: gửi-rồi-ngắt-trước-token-đầu tốn một request nhà cung cấp THẬT nhưng không vào trần toàn
    cục, nên nhiều tài khoản vượt xa 150 lượt/ngày mà trần không bao giờ chạm."""

    def test_many_accounts_aborting_early_still_hit_the_global_ceiling(self) -> None:
        w = World(slots=1, delay=0.35, words=40, global_cap=3, per_user=5)
        live = _LiveServer(w.app)
        try:
            for i in range(3):
                tok = f"abuser{i}"
                cid = httpx.post(f"{live.base}/api/ai/conversations", headers=w.hdr(tok), json={"mode": "general"}, timeout=10).json()["conversation_id"]
                got = live.raw_post(f"/api/ai/conversations/{cid}/messages", tok, {"content": "ngắt", "client_id": f"x{i}"},
                                    read_until=b"event: meta")
                self.assertIn(b"event: meta", got)
                end = time.time() + 8
                while time.time() < end and w.rt.stream_guard._total:  # noqa: SLF001
                    time.sleep(0.05)
                time.sleep(0.2)
            self.assertEqual(w.per_slot().get("gemini-01"), 3, "ba lượt ngắt sớm = ba request thật ở slot")
            r = httpx.post(f"{live.base}/api/ai/conversations", headers=w.hdr("victim"), json={"mode": "general"}, timeout=10)
            cid = r.json()["conversation_id"]
            r = httpx.post(f"{live.base}/api/ai/conversations/{cid}/messages", headers=w.hdr("victim"),
                           json={"content": "tôi là người dùng thật", "client_id": "v1"}, timeout=10)
            self.assertEqual((r.status_code, r.json()["detail"]["scope"]), (429, "global"),
                            "trần toàn cục đã chạm nhờ các lượt ngắt sớm")
        finally:
            live.close()


class TestStreamGuardCleanup(unittest.TestCase):
    """Khoá luồng (1 luồng/người, tối đa N luồng/instance) rò = người đó, rồi sau N lần cả instance, nhận `ai_busy`
    cho tới khi restart. Các test này gọi thẳng ứng dụng ASGI nên dựng được những lúc client ngắt mà socket thật khó
    căn đúng: ngay ở chunk đầu tiên, và ngay trước khi stream bắt đầu."""

    BODY = json.dumps({"content": "xin chào", "client_id": "cg"}).encode()

    def _scope(self, tok: str, cid: str, spec: str) -> Dict[str, Any]:
        return {"type": "http", "asgi": {"version": "3.0", "spec_version": spec}, "http_version": "1.1", "method": "POST",
                "path": f"/api/ai/conversations/{cid}/messages", "raw_path": f"/api/ai/conversations/{cid}/messages".encode(),
                "query_string": b"", "root_path": "", "scheme": "http", "client": ("127.0.0.1", 5), "server": ("127.0.0.1", 80),
                "headers": [(b"host", b"x"), (b"authorization", f"Bearer {tok}".encode()),
                            (b"content-type", b"application/json"), (b"content-length", str(len(self.BODY)).encode())]}

    def _run(self, w: World, tok: str, *, spec: str, fail_on_first_chunk: bool, disconnect_at_once: bool,
             fail_on_start: bool = False) -> None:
        import asyncio
        import gc
        cid = w.conv(tok)

        async def main() -> None:
            disc = asyncio.Event()
            state = {"body": False}
            if disconnect_at_once:
                disc.set()

            async def receive() -> Dict[str, Any]:
                if not state["body"]:
                    state["body"] = True
                    return {"type": "http.request", "body": self.BODY, "more_body": False}
                await disc.wait()
                return {"type": "http.disconnect"}

            async def send(message: Dict[str, Any]) -> None:
                if fail_on_start and message["type"] == "http.response.start":
                    raise OSError("client đã ngắt trước cả tiêu đề response")
                if fail_on_first_chunk and message["type"] == "http.response.body" and message.get("body"):
                    raise OSError("client đã ngắt")

            try:
                await w.app(self._scope(tok, cid, spec), receive, send)
            except Exception:  # noqa: BLE001 — ClientDisconnect / OSError: đúng thứ máy chủ thật sẽ thấy
                pass
            # máy chủ thật đóng generator mở dở qua hook asyncgen khi GC; ở đây ép đúng việc đó
            gc.collect()
            await asyncio.sleep(0.05)
            await asyncio.get_running_loop().shutdown_asyncgens()
            await asyncio.sleep(0.05)

        asyncio.run(main())

    def test_hangup_at_the_very_first_chunk_releases_the_guard(self) -> None:
        w = World(slots=1)
        self._run(w, "gone1", spec="2.4", fail_on_first_chunk=True, disconnect_at_once=False)
        self.assertEqual((w.rt.stream_guard._total, dict(w.rt.stream_guard._per_user)), (0, {}))  # noqa: SLF001
        self.assertEqual(w.ask("gone1")[1].status_code, 200, "người này phải gửi tiếp được ngay")

    def test_disconnect_before_the_stream_starts_on_the_legacy_asgi_path_releases_the_guard(self) -> None:
        w = World(slots=1)
        self._run(w, "gone2", spec="2.3", fail_on_first_chunk=False, disconnect_at_once=True)
        self.assertEqual((w.rt.stream_guard._total, dict(w.rt.stream_guard._per_user)), (0, {}))  # noqa: SLF001
        self.assertEqual(w.ask("gone2")[1].status_code, 200)

    def test_send_failing_on_the_response_start_still_releases_the_guard(self) -> None:
        """Reviewer: nếu `send` ném lỗi ngay ở `http.response.start` thì generator CHƯA BAO GIỜ chạy (không có `finally`)
        và `BackgroundTask` cũng không chạy -> khoá luồng rò. Giờ response tự nhả vé trên mọi đường thoát."""
        w = World(slots=1)
        for i in range(10):  # nhiều hơn max_streams của instance (8): rò thì từ lần thứ 9 mọi người nhận ai_busy
            self._run(w, f"nostart{i}", spec="2.4", fail_on_first_chunk=False, disconnect_at_once=False, fail_on_start=True)
        self.assertEqual((w.rt.stream_guard._total, dict(w.rt.stream_guard._per_user)), (0, {}))  # noqa: SLF001
        self.assertEqual(w.ask("fresh")[1].status_code, 200)

    def test_repeated_early_hangups_never_exhaust_the_instance_wide_stream_slots(self) -> None:
        w = World(slots=1)
        for i in range(12):  # nhiều hơn max_streams của instance (8)
            self._run(w, f"hup{i}", spec="2.4", fail_on_first_chunk=True, disconnect_at_once=False)
        self.assertEqual(w.rt.stream_guard._total, 0)  # noqa: SLF001
        self.assertEqual(w.ask("fresh")[1].status_code, 200, "không ai bị ai_busy vì các lần ngắt trước")

    def test_stream_ticket_releases_exactly_once(self) -> None:
        from server.ai_assistant.limits import StreamGuard, StreamTicket
        g = StreamGuard(max_streams_per_instance=4)
        g.acquire("u1")
        t = StreamTicket(g, "u1")
        t.release()
        g.acquire("u1")  # luồng KẾ TIẾP của cùng người dùng
        t.release()  # nhả thừa của vé cũ không được trừ nhầm luồng mới
        self.assertEqual((g._total, dict(g._per_user)), (1, {"u1": 1}))  # noqa: SLF001
        with self.assertRaises(Exception):
            g.acquire("u1")  # vẫn đang có một luồng đang chạy


# ======================================================================================== owner QA lane

class TestOwnerQaLane(unittest.TestCase):
    """Lối QA của Owner dùng hạn mức riêng nhưng VẪN nằm dưới công tắc khẩn cấp và trần toàn cục."""

    def test_qa_turns_use_their_own_allowance_and_leave_the_normal_one_untouched(self) -> None:
        w = World(owner_qa=3)
        for _ in range(3):
            _, r = w.ask("owner", qa=True)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(ev(r, "usage")[0]["lane"], "qa")
        a = w.avail("owner")
        self.assertEqual((a["limits"]["requests_used"], a["limits"]["requests_remaining"]), (0, 5))
        self.assertEqual((a["qa"]["requests_used"], a["qa"]["requests_remaining"], a["qa"]["exhausted"]), (3, 0, True))
        for _ in range(5):  # Owner vẫn có đúng 5 lượt/ngày như mọi người ở lối thường
            self.assertEqual(w.ask("owner")[1].status_code, 200)
        r = w.ask("owner")[1]
        self.assertEqual((r.status_code, detail(r)["scope"]), (429, "user"))

    def test_qa_ledger_is_a_separate_row_and_the_owner_user_row_stays_empty(self) -> None:
        w = World()
        w.ask("owner", qa=True)
        from server.ai_assistant.limits import _today
        self.assertIsNone(w.rt.repo.get_usage_day("user_owner", _today()))
        row = w.rt.repo.get_usage_day(qa_ledger_user("user_owner"), _today())
        self.assertEqual(row.requests, 1)
        self.assertTrue(qa_ledger_user("user_owner").startswith("qa-"))

    def test_qa_turns_count_toward_the_global_ceiling_and_cannot_exceed_it(self) -> None:
        w = World(global_cap=3, owner_qa=5)
        w.ask("owner", qa=True)
        w.ask("owner", qa=True)
        self.assertEqual(w.ask("alice")[1].status_code, 200)
        for tok, kw in (("bob", {}), ("owner", {"qa": True}), ("owner", {})):
            with self.subTest(tok=tok, **kw):
                r = w.ask(tok, **kw)[1]
                self.assertEqual((r.status_code, detail(r)["scope"]), (429, "global"))
        self.assertEqual(sum(w.per_slot().values()), 3)

    def test_qa_cap_exhaustion_is_qa_scoped_and_does_not_block_the_normal_lane(self) -> None:
        w = World(owner_qa=2)
        for _ in range(2):
            w.ask("owner", qa=True)
        r = w.ask("owner", qa=True)[1]
        self.assertEqual((r.status_code, detail(r)["code"], detail(r)["scope"]), (429, "ai_budget_exhausted", "qa"))
        self.assertEqual(w.ask("owner")[1].status_code, 200)

    def test_a_qa_cap_of_zero_closes_the_lane_instead_of_meaning_unlimited(self) -> None:
        w = World(owner_qa=0)
        r = w.ask("owner", qa=True)[1]
        self.assertEqual((r.status_code, detail(r)["scope"]), (429, "qa"))
        self.assertEqual(w.calls(), {})

    def test_the_qa_flag_is_ignored_for_everyone_who_is_not_an_owner(self) -> None:
        w = World()
        _, r = w.ask("alice", qa=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ev(r, "usage")[0]["lane"], "user")
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1, "người thường không có lối QA")
        self.assertNotIn("qa", w.avail("alice"))
        self.assertIn("qa", w.avail("owner"), "chỉ Owner thấy hạn mức QA")

    def test_kill_switch_blocks_the_qa_lane_too(self) -> None:
        w = World()
        w.set_controls(ai_enabled=False)
        r = w.ask("owner", qa=True)[1]
        self.assertEqual((r.status_code, detail(r)["code"]), (503, "ai_not_enabled"))
        self.assertEqual(w.calls(), {})

    def test_qa_usage_event_reports_the_qa_allowance_never_the_user_one(self) -> None:
        w = World(owner_qa=4)
        _, r = w.ask("owner", qa=True)
        a = ev(r, "usage")[0]["allowance"]
        self.assertEqual((a["requests_used"], a["requests_limit"], a["requests_remaining"]), (1, 4, 3))

    def test_the_synthetic_qa_ledger_key_is_never_an_eligible_account(self) -> None:
        """Id tài khoản bắt đầu bằng `qa-` bị từ chối ở `allows`: nếu không, nó dùng chung sổ QA của Owner."""
        w = World()
        self.assertFalse(w.rt.allows(qa_ledger_user("user_owner")))
        self.assertTrue(w.rt.allows("user_owner"))


# ======================================================================================== kill switch / admin / probes

class TestKillSwitchAdminAndProbes(unittest.TestCase):
    OWNER = {"Authorization": "Bearer owner"}
    ADMIN = {"Authorization": "Bearer admin"}
    PLAIN = {"Authorization": "Bearer user"}

    def test_kill_switch_through_the_admin_api_stops_every_lane_at_once_and_is_audited(self) -> None:
        w = World()
        self.assertEqual(w.ask("alice")[1].status_code, 200)
        r = w.c.put("/api/admin/ai/global", headers=self.OWNER, json={"ai_enabled": False})
        self.assertEqual(r.status_code, 200, r.text)
        before = w.calls()
        for tok, kw in (("alice", {}), ("owner", {}), ("owner", {"qa": True})):
            with self.subTest(tok=tok, **kw):
                resp = w.ask(tok, **kw)[1]
                self.assertEqual((resp.status_code, detail(resp)["code"]), (503, "ai_not_enabled"))
        self.assertEqual(w.calls(), before, "tắt khẩn cấp thì không còn lời gọi nhà cung cấp nào")
        a = w.avail("alice")
        self.assertEqual((a["enabled"], a["reason"]), (False, "disabled_by_admin"))
        self.assertEqual(w.c.get("/api/ai/access", headers=w.hdr("alice")).json(), {"eligible": False})
        self.assertEqual(w.c.get("/api/ai/conversations", headers=w.hdr("alice")).status_code, 200,
                         "đọc lịch sử vẫn được khi tắt khẩn cấp (hành vi đã tài liệu hoá)")
        rows = w.c.get("/api/admin/ai/audit", headers=self.OWNER).json()["items"]
        row = next(a for a in rows if a["entity"] == "global" and a["field"] == "ai_enabled")
        self.assertEqual((row["admin_id"], row["old_value"], row["new_value"]), ("owner", "true", "false"))
        self.assertEqual(w.c.put("/api/admin/ai/global", headers=self.OWNER, json={"ai_enabled": True}).status_code, 200)
        self.assertEqual(w.ask("alice")[1].status_code, 200, "bật lại là dùng được ngay")

    def test_only_the_owner_can_change_anything_and_a_reader_cannot(self) -> None:
        w = World(slots=1)
        for hdr, expect in ((self.ADMIN, 403), (self.PLAIN, 403), ({}, 401)):
            with self.subTest(hdr=hdr):
                self.assertEqual(w.c.put("/api/admin/ai/global", headers=hdr, json={"ai_enabled": False}).status_code, expect)
                self.assertEqual(w.c.put("/api/admin/ai/slots/gemini-01", headers=hdr, json={"enabled": False}).status_code, expect)
                self.assertEqual(w.c.post("/api/admin/ai/slots/gemini-01/probe", headers=hdr).status_code, expect)
                self.assertEqual(w.c.delete("/api/admin/ai/slots/gemini-01", headers=hdr).status_code, expect)
        self.assertTrue(w.plane.enabled())
        self.assertEqual(w.c.get("/api/admin/ai/overview", headers=self.ADMIN).status_code, 200, "Admin được ĐỌC")
        self.assertEqual(w.c.get("/api/admin/ai/overview", headers=self.PLAIN).status_code, 403)
        self.assertEqual(w.provs["gemini-01"].probed, 0, "không ai ngoài Owner được probe")

    def test_slot_disable_audit_names_the_owner_and_the_slot(self) -> None:
        w = World(slots=2)
        r = w.c.put("/api/admin/ai/slots/gemini-02", headers=self.OWNER, json={"enabled": False})
        self.assertEqual(r.status_code, 200, r.text)
        rows = w.c.get("/api/admin/ai/audit", headers=self.OWNER).json()["items"]
        row = next(a for a in rows if a["entity"] == "slot:gemini-02" and a["field"] == "enabled")
        self.assertEqual((row["admin_id"], row["old_value"], row["new_value"]), ("owner", "true", "false"))
        for n in range(6):
            self.assertEqual(w.ask(f"u{n}")[1].status_code, 200)
        self.assertEqual(w.provs["gemini-02"].requests, [], "slot đã tắt không nhận lưu lượng nào")

    def test_probe_is_accounted_apart_from_user_traffic_and_global_ceiling(self) -> None:
        w = World(slots=2, global_cap=1)
        for sid in ("gemini-01", "gemini-02"):
            r = w.c.post(f"/api/admin/ai/slots/{sid}/probe", headers=self.OWNER)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["probe"]["ok"])
        self.assertEqual(w.per_slot(), {}, "probe không ghi vào sổ lưu lượng")
        ov = w.c.get("/api/admin/ai/overview", headers=self.OWNER).json()
        self.assertEqual((ov["requests"], ov["probes_today"]["count"]), (0, 2))
        self.assertEqual(w.ask("alice")[1].status_code, 200, "probe không được ăn vào trần toàn cục")
        r = w.c.post("/api/admin/ai/slots/gemini-01/probe", headers=self.OWNER)
        self.assertEqual(r.status_code, 409, "cùng slot kiểm liên tiếp bị chặn")
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1)

    def test_probe_works_while_the_switch_is_off_but_never_serves_a_user(self) -> None:
        w = World(slots=1)
        w.set_controls(ai_enabled=False)
        self.assertTrue(w.c.post("/api/admin/ai/slots/gemini-01/probe", headers=self.OWNER).json()["probe"]["ok"])
        self.assertEqual(w.ask("alice")[1].status_code, 503)
        self.assertEqual(w.provs["gemini-01"].requests, [], "probe dùng generate(), không phải stream của người dùng")

    def test_a_failing_probe_returns_only_sanitized_enums(self) -> None:
        w = World(slots=1)
        w.provs["gemini-01"].probe_error = ProviderError(f"Không gọi được: {FAKE_KEY}", code="provider_http_403",
                                                         category="PERMISSION_DENIED")
        r = w.c.post("/api/admin/ai/slots/gemini-01/probe", headers=self.OWNER)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["probe"]["ok"])
        self.assertNotIn(FAKE_KEY, r.text)
        self.assertNotIn("Không gọi được", r.text)

    def test_global_cap_is_exact_across_users_and_resets_with_the_day_boundary_elsewhere(self) -> None:
        w = World(global_cap=4, per_user=5)
        codes = [w.ask(f"u{i}")[1].status_code for i in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 429, 429])
        self.assertEqual(sum(w.per_slot().values()), 4)
        r = w.ask("u9")[1]
        self.assertEqual(detail(r)["scope"], "global")
        self.assertNotIn("4", detail(r)["message"], "không lộ con số công suất toàn cục cho người dùng")


# ======================================================================================== provider failure + routing

class TestProviderFailuresAndRouting(unittest.TestCase):
    E429 = staticmethod(lambda: ProviderError("429", code="provider_http_429", retry_after_s=90))
    E503 = staticmethod(lambda: ProviderError("503", code="provider_http_503"))

    def test_a_429_falls_back_in_the_same_turn_then_the_slot_cools_down_and_later_recovers(self) -> None:
        w = World(slots=2, prio={"gemini-01": 1, "gemini-02": 2}, scripts={"gemini-01": [self.E429()]})
        cid, r = w.ask("alice")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ev(r, "done")[0]["status"], "complete")
        self.assertEqual((len(w.provs["gemini-01"].requests), len(w.provs["gemini-02"].requests)), (1, 1))
        self.assertEqual(w.per_slot(), {"gemini-02": 1}, "chỉ slot đã PHỤC VỤ được tính một lượt")
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1, "người dùng không bị tính hai lần vì chuyển slot")
        w.ask("bob")
        self.assertEqual(len(w.provs["gemini-01"].requests), 1, "đang cooldown thì không bị gọi lại")
        w.clk.t += 91
        w.ask("carol")
        self.assertEqual(len(w.provs["gemini-01"].requests), 2, "hết cooldown thì quay lại phục vụ")
        self.assertEqual(w.per_slot().get("gemini-01"), 1)

    def test_a_5xx_before_the_first_token_falls_back_without_charging_the_user_twice(self) -> None:
        w = World(slots=2, prio={"gemini-01": 1, "gemini-02": 2}, scripts={"gemini-01": [self.E503()]})
        _, r = w.ask("alice")
        self.assertEqual(ev(r, "error"), [])
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1)
        self.assertEqual(w.per_slot(), {"gemini-02": 1})
        errs = sum(u.errors for u in w.plane.usage_today().values())
        self.assertEqual(errs, 1, "lỗi của slot đầu được ghi nhận để Owner thấy")

    def test_every_slot_failing_before_the_first_token_is_a_clean_error_that_costs_nothing(self) -> None:
        w = World(slots=3, scripts={sid: [self.E503()] for sid in ("gemini-01", "gemini-02", "gemini-03")})
        cid, r = w.ask("alice")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(kinds(r)[0], "meta")
        self.assertEqual(ev(r, "error")[0]["code"], "ai_provider_unavailable")
        self.assertEqual(ev(r, "done"), [])
        self.assertEqual(w.calls(), {"gemini-01": 1, "gemini-02": 1, "gemini-03": 1}, "mỗi slot đúng một lần, không vòng lặp thử lại")
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0, "lỗi phía nhà cung cấp là miễn phí cho người dùng")
        self.assertEqual([m.role for m in w.messages(cid)], ["user"], "không lưu câu trả lời rỗng")
        self.assertEqual(w.per_slot(), {})
        self.assertEqual(w.ask("alice", cid=cid)[1].status_code, 200, "thử lại được ngay (script đã hết lỗi)")

    def test_a_failure_after_the_first_token_keeps_the_partial_reply_and_does_not_fall_back(self) -> None:
        w = World(slots=2, prio={"gemini-01": 1, "gemini-02": 2},
                  scripts={"gemini-01": [("after", ProviderError("cut", code="provider_http_500"))]})
        cid, r = w.ask("alice")
        self.assertEqual(ev(r, "error")[0]["code"], "ai_provider_interrupted")
        self.assertEqual("".join(d["text"] for d in ev(r, "delta")), "từ gemini-01 ")
        self.assertEqual(w.provs["gemini-02"].requests, [], "đã phát token thì không chuyển slot (tránh trả lời hai lần)")
        asst = [m for m in w.messages(cid) if m.role == "assistant"]
        self.assertEqual([(m.status, m.content) for m in asst], [("error", "từ gemini-01 ")])
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1, "đã sinh văn bản thì tính một lượt (ước lượng)")
        self.assertEqual(w.per_slot(), {"gemini-01": 1})

    def test_disabled_slots_never_receive_traffic_and_the_rest_share_it(self) -> None:
        w = World(slots=3, disabled=("gemini-02",))
        for i in range(12):
            self.assertEqual(w.ask(f"u{i}")[1].status_code, 200)
        self.assertEqual(w.provs["gemini-02"].requests, [])
        self.assertEqual(sum(w.calls().values()), 12)
        self.assertEqual(set(w.calls()), {"gemini-01", "gemini-03"})

    def test_equal_slots_share_the_load_instead_of_draining_one_project_first(self) -> None:
        w = World(slots=4)
        for i in range(24):
            self.assertEqual(w.ask(f"u{i}")[1].status_code, 200)
        calls = w.calls()
        self.assertEqual(sum(calls.values()), 24)
        self.assertEqual(len(calls), 4, f"mọi slot cùng bậc phải nhận lưu lượng: {calls}")
        self.assertLessEqual(max(calls.values()), 16, f"không slot nào ôm gần hết tải: {calls}")
        self.assertEqual(w.per_slot(), calls, "bộ đếm slot khớp đúng số lời gọi thật")

    def test_an_unexpected_exception_in_a_provider_is_contained_and_falls_back(self) -> None:
        w = World(slots=2, prio={"gemini-01": 1, "gemini-02": 2},
                  scripts={"gemini-01": [RuntimeError(f"boom {FAKE_KEY} gemini-01")]})
        _, r = w.ask("alice")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ev(r, "error"), [])
        self.assertNotIn(FAKE_KEY, r.text)
        self.assertEqual(w.per_slot(), {"gemini-02": 1})

    def test_assistant_message_write_failure_does_not_lose_the_slot_accounting(self) -> None:
        """F20: bộ đếm slot phải được ghi TRƯỚC các lần ghi kho tin nhắn, nếu không một lần ghi hỏng làm mất cả số đếm
        theo slot lẫn trần toàn cục dù nhà cung cấp đã bị gọi."""
        w = World(slots=1)
        real = w.rt.repo.create_message

        def flaky(m: Any) -> Any:
            if m.role == "assistant":
                raise RuntimeError("kho tin nhắn hỏng")
            return real(m)

        cid = w.conv("alice")
        quiet = TestClient(w.app, raise_server_exceptions=False)  # lỗi ghi kho nổi lên như một phản hồi hỏng, không làm sập test
        with mock.patch.object(w.rt.repo, "create_message", side_effect=flaky):
            try:
                quiet.post(f"/api/ai/conversations/{cid}/messages", headers=w.hdr("alice"),
                           json={"content": "xin chào", "client_id": "f20"})
            except Exception:  # noqa: BLE001 — phía client có thể thấy luồng bị cắt; điều cần kiểm là sổ đếm bên dưới
                pass
        self.assertEqual(w.per_slot(), {"gemini-01": 1}, "slot đã phục vụ thì phải được đếm")
        self.assertEqual(w.rt.stream_guard._total, 0, "khoá luồng vẫn được nhả")  # noqa: SLF001

    def test_message_write_failure_for_the_user_turn_is_a_clean_503_that_costs_nothing(self) -> None:
        w = World(slots=1)
        cid = w.conv("alice")
        with mock.patch.object(w.rt.repo, "create_message", side_effect=__import__("server.ai_assistant.memory", fromlist=["AiUnavailable"]).AiUnavailable("down")):
            r = w.ask("alice", cid=cid)[1]
        self.assertEqual((r.status_code, detail(r)["code"]), (503, "ai_storage_unavailable"))
        self.assertEqual(w.calls(), {})
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0)
        self.assertEqual(w.rt.stream_guard._total, 0)  # noqa: SLF001


# ======================================================================================== isolation + sessions

class TestUserIsolationAndSessions(unittest.TestCase):
    def test_other_users_cannot_read_delete_or_post_into_a_conversation(self) -> None:
        w = World(slots=1)
        cid, _ = w.ask("alice", "bí mật của alice")
        before = w.calls()
        for method, kw in (("get", {}), ("delete", {}), ("post", {"json": {"content": "tôi là bob", "client_id": "x"}})):
            with self.subTest(method=method):
                url = f"/api/ai/conversations/{cid}" + ("/messages" if method == "post" else "")
                r = getattr(w.c, method)(url, headers=w.hdr("bob"), **kw)
                self.assertEqual((r.status_code, detail(r)["code"]), (403, "ai_forbidden"))
                self.assertNotIn("bí mật", r.text)
        self.assertEqual(w.calls(), before, "bob không kích hoạt được lời gọi nhà cung cấp nào")
        self.assertEqual(w.avail("bob")["limits"]["requests_used"], 0)
        self.assertEqual(w.c.get("/api/ai/conversations", headers=w.hdr("bob")).json()["items"], [])
        self.assertEqual(len(w.messages(cid)), 2, "dữ liệu của alice còn nguyên")

    def test_memory_delete_only_affects_the_caller(self) -> None:
        w = World(slots=1)
        a, _ = w.ask("alice")
        b, _ = w.ask("bob")
        self.assertEqual(w.c.delete("/api/ai/memory?include_projects=true", headers=w.hdr("alice")).status_code, 200)
        self.assertEqual(w.c.get(f"/api/ai/conversations/{b}", headers=w.hdr("bob")).status_code, 200)
        self.assertEqual(w.c.get(f"/api/ai/conversations/{a}", headers=w.hdr("alice")).status_code, 404)

    def test_a_revoked_session_is_401_everywhere_and_a_fresh_login_sees_the_old_history(self) -> None:
        w = World(slots=1)
        cid, _ = w.ask("alice")
        w.revoked.add("alice")  # đăng xuất / hết hạn phiên
        calls = w.calls()
        for method, url, body in (("get", "/api/ai/availability", None), ("get", "/api/ai/conversations", None),
                                  ("get", f"/api/ai/conversations/{cid}", None),
                                  ("post", f"/api/ai/conversations/{cid}/messages", {"content": "hi", "client_id": "x"}),
                                  ("post", "/api/ai/conversations", {"mode": "general"}),
                                  ("put", "/api/ai/preferences", {"memory_enabled": True, "preferences": {}})):
            with self.subTest(url=url):
                kw = {"json": body} if body is not None else {}
                self.assertEqual(getattr(w.c, method)(url, headers=w.hdr("alice"), **kw).status_code, 401)
        self.assertEqual(w.calls(), calls)
        w.revoked.discard("alice")  # đăng nhập lại
        self.assertEqual(len(w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).json()["messages"]), 2)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 1, "hạn mức không bị reset bằng cách đăng xuất/đăng nhập")

    def test_logging_out_mid_stream_cannot_corrupt_the_next_session(self) -> None:
        w = World(slots=1)
        cid, r = w.ask("alice")
        w.revoked.add("alice")
        w.revoked.discard("alice")
        self.assertEqual(w.ask("alice", cid=cid)[1].status_code, 200)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 2)

    def test_escalation_can_only_reference_the_callers_own_conversation(self) -> None:
        w = World(slots=1)
        cid, _ = w.ask("alice", "hỏi riêng tư")
        r = w.c.post("/api/ai/support/escalations", headers=w.hdr("bob"), json={"summary": "xin hỗ trợ", "conversation_id": cid})
        self.assertEqual((r.status_code, detail(r)["code"]), (403, "ai_forbidden"))
        r = w.c.post("/api/ai/support/escalations", headers=w.hdr("bob"), json={"summary": "xin hỗ trợ", "conversation_id": "khongco"})
        self.assertEqual((r.status_code, detail(r)["code"]), (404, "ai_not_found"))
        ok = w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"), json={"summary": "xin hỗ trợ", "conversation_id": cid})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"), json={"summary": "không gắn hội thoại"}).status_code, 200)
        # Chuỗi rỗng từng hợp lệ (= không gắn hội thoại): thắt chặt quyền sở hữu không được biến nó thành 422.
        self.assertEqual(w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"),
                                  json={"summary": "id rỗng", "conversation_id": ""}).status_code, 200)
        self.assertEqual(w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"),
                                  json={"summary": "id quá dài", "conversation_id": "x" * 65}).status_code, 422)


# ======================================================================================== hardening of the non-chat routes

class TestWriteRoutesAndInputHardening(unittest.TestCase):
    def test_write_routes_are_rate_limited_per_user_and_do_not_touch_chat(self) -> None:
        from server.ai_assistant.config import WRITE_RPM
        w = World(slots=1)
        body = {"memory_enabled": True, "preferences": {}}
        codes = [w.c.put("/api/ai/preferences", headers=w.hdr("alice"), json=body).status_code for _ in range(WRITE_RPM + 3)]
        self.assertEqual(codes[:WRITE_RPM], [200] * WRITE_RPM)
        self.assertEqual(set(codes[WRITE_RPM:]), {429})
        r = w.c.put("/api/ai/preferences", headers=w.hdr("alice"), json=body)
        self.assertEqual(detail(r)["code"], "ai_rate_limited")
        self.assertEqual(w.c.put("/api/ai/preferences", headers=w.hdr("bob"), json=body).status_code, 200, "giới hạn theo từng người")
        self.assertEqual(w.ask("alice")[1].status_code, 200, "nhịp ghi không ăn vào nhịp gửi tin")

    def test_project_create_update_delete_share_the_write_limit(self) -> None:
        from server.ai_assistant.config import WRITE_RPM
        w = World(slots=1)
        pid = w.c.post("/api/ai/projects", headers=w.hdr("alice"), json={"title": "t"}).json()["project_id"]
        for _ in range(WRITE_RPM - 1):
            self.assertEqual(w.c.put(f"/api/ai/projects/{pid}", headers=w.hdr("alice"), json={"title": "t2"}).status_code, 200)
        self.assertEqual(w.c.put(f"/api/ai/projects/{pid}", headers=w.hdr("alice"), json={"title": "t3"}).status_code, 429)
        self.assertEqual(w.c.delete(f"/api/ai/projects/{pid}", headers=w.hdr("alice")).status_code, 429)
        self.assertEqual(w.c.delete(f"/api/ai/memory", headers=w.hdr("alice")).status_code, 429)

    def test_support_escalations_have_a_much_tighter_limit(self) -> None:
        from server.ai_assistant.config import ESCALATION_RPM
        w = World(slots=1)
        codes = [w.c.post("/api/ai/support/escalations", headers=w.hdr("alice"), json={"summary": f"s{i}"}).status_code
                 for i in range(ESCALATION_RPM + 2)]
        self.assertEqual(codes, [200] * ESCALATION_RPM + [429, 429])

    def test_project_count_is_capped_per_user_and_deleting_frees_a_slot(self) -> None:
        w = World(slots=1)
        with mock.patch("server.ai_assistant.routes.MAX_PROJECTS_PER_USER", 3):
            ids = [w.c.post("/api/ai/projects", headers=w.hdr("alice"), json={"title": f"t{i}"}).json()["project_id"] for i in range(3)]
            r = w.c.post("/api/ai/projects", headers=w.hdr("alice"), json={"title": "thứ tư"})
            self.assertEqual((r.status_code, detail(r)["code"]), (400, "ai_context_too_large"))
            self.assertEqual(w.c.post("/api/ai/projects", headers=w.hdr("bob"), json={"title": "của bob"}).status_code, 200)
            self.assertEqual(w.c.delete(f"/api/ai/projects/{ids[0]}", headers=w.hdr("alice")).status_code, 200)
            self.assertEqual(w.c.post("/api/ai/projects", headers=w.hdr("alice"), json={"title": "thứ tư"}).status_code, 200)

    def test_project_text_fields_have_hard_maxima_at_the_api(self) -> None:
        w = World(slots=1)
        too_big = [{"title": "t" * 121}, {"title": "t", "premise": "p" * 4001}, {"title": "t", "notes": "n" * 4001}]
        for body in too_big:
            with self.subTest(field=[k for k, v in body.items() if len(v) > 120][0]):
                self.assertEqual(w.c.post("/api/ai/projects", headers=w.hdr("alice"), json=body).status_code, 422)
        ok = {"title": "t" * 120, "premise": "p" * 4000, "notes": "n" * 4000}
        self.assertEqual(w.c.post("/api/ai/projects", headers=w.hdr("alice"), json=ok).status_code, 200)

    def test_list_limit_is_clamped_instead_of_returning_everything_or_failing(self) -> None:
        w = World(slots=1)
        for i in range(3):
            w.conv("alice", title=f"c{i}")
        for limit in (0, -5, 1, 100000):
            with self.subTest(limit=limit):
                r = w.c.get(f"/api/ai/conversations?limit={limit}", headers=w.hdr("alice"))
                self.assertEqual(r.status_code, 200, r.text)
                n = len(r.json()["items"])
                self.assertEqual(n, 3 if limit == 100000 else 1, f"limit={limit} -> {n}")
        cid, _ = w.ask("alice")
        for limit in (0, -1, 100000):
            with self.subTest(messages_limit=limit):
                r = w.c.get(f"/api/ai/conversations/{cid}?limit={limit}", headers=w.hdr("alice"))
                self.assertEqual(r.status_code, 200, r.text)

    def test_availability_hides_the_configuration_reason_from_non_owners(self) -> None:
        off = TestClient(_off_app(w_owner="user_owner"))
        a = off.get("/api/ai/availability", headers={"Authorization": "Bearer alice"}).json()
        self.assertEqual((a["enabled"], a["reason"]), (False, "off"))
        o = off.get("/api/ai/availability", headers={"Authorization": "Bearer owner"}).json()
        self.assertIn("FAS_AI", o["reason"], "Owner thấy chi tiết để chẩn đoán")


def _off_app(*, w_owner: str) -> FastAPI:
    settings = replace(Settings(), owner_user_ids=(w_owner,), ai_assistant=AiAssistantSettings(enabled=False))
    rt = build_ai_runtime(settings)
    app = FastAPI()
    app.include_router(build_ai_router(rt, resolve_profile=lambda a: _Profile(f"user_{a.split(' ', 1)[1]}" if a else "")))
    return app


# ======================================================================================== no leaks to the client

class TestNoLeaksToTheClient(unittest.TestCase):
    """Không phản hồi nào của API người dùng được chứa: khoá, tên biến bí mật, id slot, tên model, hay văn bản lỗi của
    nhà cung cấp — kể cả khi chính nhà cung cấp nhét khoá vào thông báo lỗi của nó."""

    NEEDLES = (FAKE_KEY, "FAS_AI_SECRET", "GEMINI_GEMINI", "gemini-0", "gemini-model", "x-goog", "AIza", "secret_ref",
               "provider_http", "PERMISSION_DENIED", "Không gọi được")

    def check(self, label: str, resp: Any) -> None:
        text = resp.text
        if "text/event-stream" in resp.headers.get("content-type", ""):
            # Văn bản `delta` là câu trả lời CỦA MÔ HÌNH (ở đây do nhà cung cấp giả viết, có chứa tên nó) — không phải
            # siêu dữ liệu máy chủ; mọi sự kiện còn lại (meta/usage/error/done) thì phải sạch.
            text = json.dumps([(n, d) for n, d in events(resp) if n != "delta"], ensure_ascii=False)
        blob = (text + json.dumps(dict(resp.headers))).lower()
        for needle in self.NEEDLES:
            self.assertNotIn(needle.lower(), blob, f"{label}: lộ {needle!r}")

    def test_user_facing_responses_never_carry_provider_details(self) -> None:
        leak = f"Không gọi được 'gemini-01': {FAKE_KEY} PERMISSION_DENIED"
        err = lambda: ProviderError(leak, code="provider_http_403", category="PERMISSION_DENIED")  # noqa: E731
        w = World(slots=3, prio={"gemini-01": 1, "gemini-02": 2, "gemini-03": 3},
                  scripts={"gemini-01": [err(), ("after", err()), err(), err()],
                           "gemini-02": [err(), err(), err()], "gemini-03": [err(), err()]})
        seen = 0
        # 1) toàn bộ nhà cung cấp lỗi trước token đầu  2) lỗi giữa chừng (slot 01 là slot đầu)  3) thành công
        for tok in ("alice", "alice", "bob", "carol"):
            cid, r = w.ask(tok)
            self.check(f"post:{tok}", r)
            seen += 1
        cid = w.conv("dave")
        self.check("conv:create", w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("dave")))
        self.check("conv:list", w.c.get("/api/ai/conversations", headers=w.hdr("dave")))
        for who in ("alice", "owner", "nobody"):
            self.check(f"avail:{who}", w.c.get("/api/ai/availability", headers=w.hdr(who)))
            self.check(f"access:{who}", w.c.get("/api/ai/access", headers=w.hdr(who)))
        # hạn mức, kill switch, lỗi 4xx
        for _ in range(6):
            _, r = w.ask("erin")
            self.check("post:erin", r)
        w.set_controls(ai_enabled=False)
        self.check("killed", w.ask("frank")[1])
        self.check("404", w.c.get("/api/ai/conversations/khongco", headers=w.hdr("alice")))
        self.check("422", w.c.post(f"/api/ai/conversations/{cid}/messages", headers=w.hdr("dave"), json={"content": ""}))
        self.check("401", w.c.get("/api/ai/conversations"))
        self.assertGreaterEqual(seen, 4)

    def test_error_events_use_fixed_messages_not_provider_text(self) -> None:
        leak = ProviderError(f"upstream said {FAKE_KEY}", code="provider_http_500")
        w = World(slots=1, scripts={"gemini-01": [("after", leak)]})
        _, r = w.ask("alice")
        e = ev(r, "error")[0]
        self.assertEqual(e["code"], "ai_provider_interrupted")
        self.assertNotIn("upstream", e["message"])
        self.assertNotIn(FAKE_KEY, r.text)

    def test_admin_views_show_masked_fingerprints_never_key_values(self) -> None:
        w = World(slots=2)
        owner = {"Authorization": "Bearer owner"}
        for path in ("/api/admin/ai/config", "/api/admin/ai/overview", "/api/admin/ai/audit"):
            body = w.c.get(path, headers=owner).text
            self.assertNotIn(FAKE_KEY, body, path)
            self.assertNotIn(FAKE_KEY[:12], body, path)
        cfg = w.c.get("/api/admin/ai/config", headers=owner).json()
        fps = [s["health"]["secret"]["fingerprint"] for s in cfg["slots"]]
        self.assertEqual(len(fps), 2)
        for fp in fps:
            self.assertRegex(fp, r"^sha256:[0-9a-f]{8}$")

    def test_the_stream_never_forwards_server_side_only_events(self) -> None:
        w = World(slots=1)
        _, r = w.ask("alice")
        self.assertEqual(set(kinds(r)), {"meta", "delta", "usage", "done"})
        self.assertNotIn("provider_name", r.text)
        self.assertNotIn("served", r.text)
        u = ev(r, "usage")[0]
        self.assertEqual(set(u), {"input_tokens", "output_tokens", "used_today", "limit_today", "lane", "allowance"})
        self.assertEqual(set(u["allowance"]), {"requests_used", "requests_limit", "requests_remaining", "exhausted", "reset_at"})


if __name__ == "__main__":
    unittest.main()

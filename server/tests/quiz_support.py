"""Ha tang test chung cho `server/quiz` — app FastAPI tu dung + resolver gia lap.

Khong import `server.main`: router duoc mount vao mot `FastAPI()` rieng, dung
nhu cach CTO se mount voi `current_profile` that.
"""

from __future__ import annotations

import itertools
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.quiz.entitlements import grant_pro
from server.quiz.local_store import LocalQuizStore
from server.quiz.router import QuizRuntime, build_quiz_router
from server.quiz.service import QuizService

T0 = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeProfile:
    user_id: str


def fake_resolve_profile(authorization: Optional[str]) -> FakeProfile:
    """`Bearer tok-<user>` -> user. Cung hop dong voi `server.main.current_profile`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Cần đăng nhập.")
    token = authorization.split(" ", 1)[1].strip()
    if token == "tok-outage":
        raise HTTPException(503, "Appwrite down")
    if not token.startswith("tok-"):
        raise HTTPException(401, "Token không hợp lệ.")
    return FakeProfile(user_id=token[4:])


class Clock:
    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now = self.now + timedelta(**kw)


class SeqIds:
    """UUID tat dinh (cho fixtures tai lap)."""

    def __init__(self, prefix: int = 0):
        self._n = itertools.count(1)
        self._prefix = prefix

    def __call__(self) -> str:
        return str(uuid.UUID(int=(self._prefix << 64) | next(self._n)))


class SeqShareIds:
    def __init__(self):
        self._n = itertools.count(1)

    def __call__(self) -> str:
        return f"Share{next(self._n):011d}"


def auth(user: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer tok-{user}"}


def make_env(root: Optional[Path] = None, *, deterministic: bool = False, store=None):
    root = Path(root or tempfile.mkdtemp(prefix="quiz-test-"))
    store = store or LocalQuizStore(root / "quiz")
    clock = Clock()
    kwargs: Dict[str, Any] = {"clock": clock}
    if deterministic:
        kwargs.update(new_id=SeqIds(), new_share_id=SeqShareIds())
    service = QuizService(store, **kwargs)
    app = FastAPI()
    app.include_router(build_quiz_router(QuizRuntime(service), resolve_profile=fake_resolve_profile))
    return TestClient(app), service, store, clock


def give_pro(store, user: str, clock: Clock, **kw: Any):
    return grant_pro(store, user_id=user, actor="qa-fixture", reason="synthetic test grant",
                     now=clock(), **kw)


def oid(n: int) -> str:
    return str(uuid.UUID(int=(0xA << 64) | n))


def question(n: int, kind: str = "single", *, options: int = 4, correct: Optional[List[int]] = None,
             time_limit_ms: Optional[int] = None) -> Dict[str, Any]:
    """Cau hoi tong hop: id/option id tat dinh tu `n`."""
    if kind == "boolean":
        options = 2
    opts = [{"id": oid(n * 100 + i), "text": f"Lựa chọn {i} của câu {n}"} for i in range(1, options + 1)]
    correct = correct or ([1, 2] if kind == "multiple" else [1])
    return {"id": oid(n * 100), "kind": kind, "prompt": f"Câu hỏi tổng hợp số {n}?",
            "options": opts, "correct_option_ids": [opts[i - 1]["id"] for i in correct],
            "explanation": f"Giải thích câu {n}.", "difficulty": "medium",
            "time_limit_ms": time_limit_ms}


def opt(qn: int, i: int) -> str:
    return oid(qn * 100 + i)


def create_draft(client: TestClient, user: str, questions: List[Dict[str, Any]],
                 theme_id: str = "neon-tactics", title: str = "Quiz tổng hợp") -> Dict[str, Any]:
    r = client.post("/api/quiz/drafts", headers=auth(user),
                    json={"title": title, "theme_id": theme_id, "questions": questions})
    assert r.status_code == 201, r.text
    return r.json()


def publish(client: TestClient, user: str, draft: Dict[str, Any]):
    return client.post(f"/api/quiz/drafts/{draft['draft_id']}/publish", headers=auth(user),
                       json={"expected_revision": draft["revision"]})


def walk_keys(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)

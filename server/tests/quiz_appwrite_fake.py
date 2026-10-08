"""Fake Appwrite REST (documents) cho `AppwriteQuizStore` — chay trong httpx.MockTransport.

Chi mo phong dung phan hop dong ma adapter dua vao: 409 khi trung documentId,
404 `document_not_found`, list voi queries[] (equal/orderDesc/orderAsc/limit/
offset) + `total`, PATCH tron du lieu, DELETE. Ghi lai MOI request de test
khang dinh truy van so huu, phan trang va permissions. Day KHONG phai bang
chung parity voi Appwrite hosted.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx

from server.quiz.appwrite_store import AppwriteQuizStore

DB = "fake-db"
_PATH = re.compile(r"^/v1/databases/(?P<db>[^/]+)/collections/(?P<col>[^/]+)/documents(?:/(?P<id>[^/]+))?$")


@dataclass
class FakeSettings:
    endpoint: str = "https://appwrite.invalid/v1"
    project_id: str = "fake-project"
    api_key: str = "fake-key-not-a-secret"
    database_id: str = DB

    @property
    def configured(self) -> bool:
        return True

    @property
    def api_base(self) -> str:
        return "https://appwrite.invalid"


@dataclass
class Logged:
    method: str
    col: str
    doc_id: Optional[str]
    queries: List[Dict[str, Any]]
    body: Optional[Dict[str, Any]]


class FakeAppwrite:
    def __init__(self, max_page: int = 100):
        self.cols: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.log: List[Logged] = []
        self.lock = threading.RLock()
        self.max_page = max_page
        #: hook(method, col, doc_id) -> Optional[httpx.Response]: chen loi/race
        self.hooks: List[Callable[[str, str, Optional[str]], Optional[httpx.Response]]] = []

    def store(self) -> AppwriteQuizStore:
        return AppwriteQuizStore(FakeSettings(), http=httpx.Client(transport=httpx.MockTransport(self)))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Appwrite-Key") == "fake-key-not-a-secret"
        assert request.headers.get("X-Appwrite-Project") == "fake-project"
        m = _PATH.match(request.url.path)
        if not m or m.group("db") != DB:
            return httpx.Response(404, json={"type": "database_not_found"})
        col, did = m.group("col"), m.group("id")
        queries = [json.loads(q) for q in request.url.params.get_list("queries[]")]
        body = json.loads(request.content) if request.content else None
        for hook in list(self.hooks):
            forced = hook(request.method, col, did if did else (body or {}).get("documentId"))
            if forced is not None:
                return forced
        with self.lock:
            self.log.append(Logged(request.method, col, did, queries, body))
            docs = self.cols.setdefault(col, {})
            if request.method == "POST" and did is None:
                new_id = body["documentId"]
                if new_id in docs:
                    return httpx.Response(409, json={"type": "document_already_exists", "code": 409})
                doc = dict(body["data"])
                doc.update({"$id": new_id, "$permissions": list(body.get("permissions") or [])})
                docs[new_id] = doc
                return httpx.Response(201, json=doc)
            if request.method == "GET" and did is None:
                return httpx.Response(200, json=self._list(docs, queries))
            if did not in docs:
                return httpx.Response(404, json={"type": "document_not_found", "code": 404})
            if request.method == "GET":
                return httpx.Response(200, json=docs[did])
            if request.method == "PATCH":
                docs[did].update(body["data"])
                return httpx.Response(200, json=docs[did])
            if request.method == "DELETE":
                del docs[did]
                return httpx.Response(204)
        return httpx.Response(405)

    def _list(self, docs: Dict[str, Dict[str, Any]], queries: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = list(docs.values())
        limit, offset = 25, 0
        for q in queries:
            meth = q["method"]
            if meth == "equal":
                rows = [r for r in rows if r.get(q["attribute"]) in q["values"]]
            elif meth == "orderDesc":
                rows.sort(key=lambda r: r.get(q["attribute"]), reverse=True)
            elif meth == "orderAsc":
                rows.sort(key=lambda r: r.get(q["attribute"]))
            elif meth == "limit":
                limit = min(int(q["values"][0]), self.max_page)
            elif meth == "offset":
                offset = int(q["values"][0])
            else:
                raise AssertionError(f"unsupported query {meth}")
        return {"total": len(rows), "documents": rows[offset:offset + limit]}

    # tien ich cho test
    def requests(self, method: str, col: str) -> List[Logged]:
        return [r for r in self.log if r.method == method and r.col == col]

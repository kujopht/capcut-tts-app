"""
`AppwriteQuizStore` — ban Appwrite (REST, httpx) cua `QuizStore`.

Theo mau `server/appwrite_gamification_store.py`: REST + API key, client httpx
TIEM duoc cho test. KHONG tao collection, KHONG goi hosted trong Phase 1 —
parity voi Appwrite hosted CHUA duoc xac minh (chi test bang fake HTTP).

Appwrite (REST documents) khong co giao dich/CAS. Tinh nguyen tu dua tren MOT
bao dam: tao document voi `documentId` da ton tai -> 409. Moi chuyen trang thai
"claim" mot id TAT DINH:

  * Draft / session: ban ghi DAU (`quiz_drafts`, `quiz_sessions`) + NHAT KY
    revision bat bien (`quiz_draft_revisions`, `quiz_session_states`, id =
    h(entity, revision)). Ghi revision N+1 = tao doc nhat ky N+1 (chi MOT ben
    thang), roi PATCH ban ghi dau. Doc = ban ghi dau + do tim N+1, N+2... (roll
    forward) — tien trinh chet giua hai buoc khong lam mat/ket trang thai.
  * Quota publish: slot `quiz_publish_slots` id = h(owner, n), n < gioi han.
    Hai lan publish song song khong the cung chiem slot cuoi.
  * Version: `quiz_versions` id = h(share, version) — bat bien, khong ghi de;
    khoa dap an o `quiz_version_keys` (id gan voi draft revision) KHONG co
    quyen doc nao cho client.

Gioi han DA BIET (co test): danh sach draft doc ban ghi dau, co the cham mot
revision neu tien trinh chet giua hai buoc (GET le draft thi roll-forward dung);
slot da claim ma share chua tao (tien trinh chet) van tinh vao quota cho toi khi
chinh draft do publish lai; dem quota theo slot, khong theo share.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, TypeVar

import httpx
from pydantic import BaseModel

from server.quiz.store import (
    AnswerKey, DraftRecord, GrantRecord, PublishConflict, PublishContent, QuotaExceeded,
    RevisionConflict, SessionRecord, ShareRecord, StoreNotFound, StoreUnavailable,
    VersionRecord, build_version,
)

COL_DRAFTS = "quiz_drafts"
COL_DRAFT_REVISIONS = "quiz_draft_revisions"
COL_PUBLISH_SLOTS = "quiz_publish_slots"
COL_SHARES = "quiz_shares"
COL_VERSIONS = "quiz_versions"
COL_VERSION_KEYS = "quiz_version_keys"
COL_SESSIONS = "quiz_sessions"
COL_SESSION_STATES = "quiz_session_states"
COL_GRANTS = "quiz_grants"

#: Schema can co (tai lieu cho buoc tao collection cua CTO/van hanh — module nay
#: KHONG tao). `content` la JSON cua ban ghi; can string lon (>= 4 MB).
SCHEMA: Dict[str, Dict[str, Any]] = {
    COL_DRAFTS: {"attributes": ["draft_id", "owner_user_id", "revision", "title", "updated_at", "content"],
                 "indexes": [["owner_user_id", "updated_at"]]},
    COL_DRAFT_REVISIONS: {"attributes": ["entity_id", "revision", "content"], "indexes": []},
    COL_PUBLISH_SLOTS: {"attributes": ["owner_user_id", "slot", "draft_id", "share_id"],
                        "indexes": [["owner_user_id"], ["owner_user_id", "draft_id"]]},
    COL_SHARES: {"attributes": ["share_id", "owner_user_id", "draft_id", "latest_version",
                                "created_at"],
                 "indexes": [["owner_user_id"], ["draft_id"]]},
    COL_VERSIONS: {"attributes": ["share_id", "version", "draft_id", "draft_revision",
                                  "owner_user_id", "keys_doc_id", "content"], "indexes": []},
    COL_VERSION_KEYS: {"attributes": ["share_id", "version", "content"], "indexes": []},
    COL_SESSIONS: {"attributes": ["session_id", "participant_user_id", "share_id",
                                  "state_revision", "content"], "indexes": []},
    COL_SESSION_STATES: {"attributes": ["entity_id", "revision", "content"], "indexes": []},
    COL_GRANTS: {"attributes": ["grant_id", "user_id", "content"], "indexes": [["user_id"]]},
}

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100
R = TypeVar("R", bound=BaseModel)


class _Missing(Exception):
    pass


class _Conflict(Exception):
    pass


def _q(method: str, attribute: Optional[str] = None, values: Optional[list] = None) -> str:
    out: Dict[str, Any] = {"method": method}
    if attribute is not None:
        out["attribute"] = attribute
    if values is not None:
        out["values"] = values
    return json.dumps(out, separators=(",", ":"))


def q_equal(attribute: str, value: Any) -> str:
    return _q("equal", attribute, [value])


def q_order_desc(attribute: str) -> str:
    return _q("orderDesc", attribute)


def q_limit(n: int) -> str:
    return _q("limit", None, [int(n)])


def q_offset(n: int) -> str:
    return _q("offset", None, [int(n)])


def doc_id(*parts: Any) -> str:
    """documentId tat dinh: hex (khong bat dau bang ky tu dac biet), 36 ky tu."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:36]


def _dump(model: BaseModel) -> str:
    return model.model_dump_json()


class AppwriteQuizStore:
    mode = "appwrite"

    def __init__(self, settings: Any, http: Optional[httpx.Client] = None):
        if not getattr(settings, "configured", False):
            raise StoreUnavailable("Appwrite is not configured for the quiz store.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._http_client = http
        self._lock = threading.Lock()

    # -- REST ---------------------------------------------------------------------

    def _http(self) -> httpx.Client:
        with self._lock:
            if self._http_client is None:
                self._http_client = httpx.Client(timeout=REQUEST_TIMEOUT)
            return self._http_client

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json",
                   "X-Appwrite-Project": self._settings.project_id,
                   "X-Appwrite-Key": self._settings.api_key}
        try:
            resp = self._http().request(method, f"{self._endpoint}{path}", json=payload,
                                        params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise StoreUnavailable(f"Appwrite unreachable ({type(exc).__name__}).") from exc
        status = resp.status_code
        if status < 400:
            return resp.json() if status != 204 and resp.content else {}
        try:
            kind = str((resp.json() or {}).get("type") or "")
        except ValueError:
            kind = ""
        if status == 409:
            raise _Conflict(kind)
        if status == 404 and kind not in ("collection_not_found", "database_not_found"):
            raise _Missing(kind)
        # Khong chep than loi (co the chua noi bo) vao thong diep.
        raise StoreUnavailable(f"Appwrite error {status} {kind}".strip())

    def _docs(self, col: str) -> str:
        return f"/v1/databases/{self._db}/collections/{col}/documents"

    def _create(self, col: str, did: str, data: Dict[str, Any], permissions: List[str]) -> Dict:
        return self._call("POST", self._docs(col),
                          payload={"documentId": did, "data": data, "permissions": permissions})

    def _get(self, col: str, did: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(col)}/{did}")

    def _patch(self, col: str, did: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(col)}/{did}", payload={"data": data})

    def _delete(self, col: str, did: str) -> None:
        self._call("DELETE", f"{self._docs(col)}/{did}")

    def _page(self, col: str, queries: List[str], *, limit: int, offset: int) -> Tuple[List[Dict], int]:
        data = self._call("GET", self._docs(col),
                          params={"queries[]": queries + [q_limit(limit), q_offset(offset)]})
        return list(data.get("documents") or []), int(data.get("total") or 0)

    def _list_all(self, col: str, queries: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page, _ = self._page(col, queries, limit=PAGE_SIZE, offset=offset)
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    @staticmethod
    def _owner_read(user_id: str) -> List[str]:
        return [f'read("user:{user_id}")']

    # -- ban ghi dau + nhat ky revision (CAS bang claim id) -------------------------

    def _read_logged(self, head_col: str, log_col: str, entity_id: str, cls: Type[R],
                     rev_of: Callable[[R], int], head_fields: Callable[[R], Dict]) -> Optional[R]:
        try:
            head = self._get(head_col, entity_id)
        except _Missing:
            return None
        rec = cls.model_validate_json(head["content"])
        rolled = False
        while True:
            try:
                log = self._get(log_col, doc_id(entity_id, rev_of(rec) + 1))
            except _Missing:
                break
            rec = cls.model_validate_json(log["content"])
            rolled = True
        if rolled:
            try:
                self._patch(head_col, entity_id, head_fields(rec))
            except (StoreUnavailable, _Missing):
                pass  # lan doc sau lai roll-forward
        return rec

    def _cas_logged(self, head_col: str, log_col: str, entity_id: str, new: R, expected: int,
                    rev_of: Callable[[R], int], head_fields: Callable[[R], Dict]) -> R:
        try:
            self._create(log_col, doc_id(entity_id, expected + 1),
                         {"entity_id": entity_id, "revision": expected + 1, "content": _dump(new)}, [])
        except _Conflict as exc:
            raise RevisionConflict(None) from exc
        try:
            self._patch(head_col, entity_id, head_fields(new))
        except (StoreUnavailable, _Missing):
            pass  # nhat ky da la nguon su that; doc sau se roll-forward
        return new

    # -- drafts --------------------------------------------------------------------

    @staticmethod
    def _draft_head(rec: DraftRecord) -> Dict[str, Any]:
        stored = rec.model_copy(update={"share_id": None, "published_version": None})
        return {"draft_id": rec.draft_id, "owner_user_id": rec.owner_user_id,
                "revision": rec.revision, "title": rec.title, "updated_at": rec.updated_at,
                "content": _dump(stored)}

    def _read_draft(self, draft_id: str) -> Optional[DraftRecord]:
        return self._read_logged(COL_DRAFTS, COL_DRAFT_REVISIONS, draft_id, DraftRecord,
                                 lambda r: r.revision, self._draft_head)

    def _probe_latest(self, share_id: str, hint: int) -> int:
        """Version moi nhat = so lon nhat co doc `quiz_versions` (bat bien); `hint` tu ban ghi dau."""
        n = max(0, hint)
        while n > 0:
            try:
                self._get(COL_VERSIONS, doc_id("v", share_id, n))
                break
            except _Missing:
                n -= 1  # hint khong bao gio vuot that, nhung phong ve
        while True:
            try:
                self._get(COL_VERSIONS, doc_id("v", share_id, n + 1))
            except _Missing:
                return n
            n += 1

    def _resolve_share(self, doc: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        hint = int(doc.get("latest_version") or 0)
        latest = self._probe_latest(str(doc["share_id"]), hint)
        if latest != hint:
            try:
                self._patch(COL_SHARES, str(doc["share_id"]), {"latest_version": latest})
            except (StoreUnavailable, _Missing):
                pass
        return doc, latest

    @staticmethod
    def _share_record(doc: Dict[str, Any], latest: int) -> ShareRecord:
        return ShareRecord(share_id=str(doc["share_id"]), owner_user_id=str(doc["owner_user_id"]),
                           draft_id=str(doc["draft_id"]), latest_version=latest,
                           created_at=str(doc["created_at"]))

    def _share_for_draft(self, draft_id: str) -> Optional[Tuple[Dict[str, Any], int]]:
        page, _ = self._page(COL_SHARES, [q_equal("draft_id", draft_id)], limit=1, offset=0)
        return self._resolve_share(page[0]) if page else None

    def _with_share(self, rec: DraftRecord, found: Optional[Tuple[Dict[str, Any], int]]) -> DraftRecord:
        if found is None or found[1] < 1:
            return rec
        return rec.model_copy(update={"share_id": str(found[0]["share_id"]),
                                      "published_version": found[1]})

    def create_draft(self, record: DraftRecord) -> DraftRecord:
        try:
            self._create(COL_DRAFTS, record.draft_id, self._draft_head(record),
                         self._owner_read(record.owner_user_id))
        except _Conflict as exc:
            raise RevisionConflict(None, "draft id already exists") from exc
        return record

    def get_draft(self, draft_id: str) -> Optional[DraftRecord]:
        rec = self._read_draft(draft_id)
        return self._with_share(rec, self._share_for_draft(draft_id)) if rec else None

    def list_drafts(self, owner_user_id: str, *, limit: int,
                    offset: int) -> Tuple[List[DraftRecord], int]:
        docs, total = self._page(COL_DRAFTS, [q_equal("owner_user_id", owner_user_id),
                                              q_order_desc("updated_at")], limit=limit, offset=offset)
        # Gia tri latest_version cua ban ghi dau share la GOI Y (co the cham 1 version
        # neu tien trinh chet sau khi ghi version); GET draft le thi do lai chinh xac.
        shares = {s["draft_id"]: (s, int(s.get("latest_version") or 0))
                  for s in self._list_all(COL_SHARES, [q_equal("owner_user_id", owner_user_id)])}
        rows = []
        for d in docs:
            rec = DraftRecord.model_validate_json(d["content"])
            if rec.owner_user_id != owner_user_id:  # phong ve: khong tin truy van phia server
                continue
            rows.append(self._with_share(rec, shares.get(rec.draft_id)))
        return rows, total

    def replace_draft(self, record: DraftRecord, *, expected_revision: int) -> DraftRecord:
        current = self._read_draft(record.draft_id)
        if current is None or current.owner_user_id != record.owner_user_id:
            raise StoreNotFound(record.draft_id)
        if current.revision != expected_revision or record.revision != expected_revision + 1:
            raise RevisionConflict(current.revision)
        saved = self._cas_logged(COL_DRAFTS, COL_DRAFT_REVISIONS, record.draft_id, record,
                                 expected_revision, lambda r: r.revision, self._draft_head)
        return self._with_share(saved, self._share_for_draft(record.draft_id))

    def delete_draft(self, draft_id: str, *, expected_revision: int) -> None:
        current = self._read_draft(draft_id)
        if current is None:
            raise StoreNotFound(draft_id)
        if current.revision != expected_revision:
            raise RevisionConflict(current.revision)
        # Claim revision N+1 de chan ghi dong thoi, roi xoa ban ghi dau. Nhat ky giu lai (audit).
        try:
            self._create(COL_DRAFT_REVISIONS, doc_id(draft_id, expected_revision + 1),
                         {"entity_id": draft_id, "revision": expected_revision + 1,
                          "content": json.dumps({"deleted": True})}, [])
        except _Conflict as exc:
            raise RevisionConflict(None) from exc
        try:
            self._delete(COL_DRAFTS, draft_id)
        except _Missing:
            pass

    # -- publish -----------------------------------------------------------------------

    def _count_slots(self, owner_user_id: str) -> int:
        _, total = self._page(COL_PUBLISH_SLOTS, [q_equal("owner_user_id", owner_user_id)],
                              limit=1, offset=0)
        return total

    def _claim_slot(self, owner_user_id: str, draft_id: str, new_share_id: str,
                    quota_limit: int) -> str:
        own, _ = self._page(COL_PUBLISH_SLOTS, [q_equal("owner_user_id", owner_user_id),
                                                q_equal("draft_id", draft_id)], limit=1, offset=0)
        if own:
            return str(own[0]["share_id"])  # slot cua chinh draft nay (lan truoc chet giua chung)
        used = self._count_slots(owner_user_id)
        if used >= quota_limit:
            raise QuotaExceeded(quota_limit, used)
        for n in list(range(used, quota_limit)) + list(range(0, min(used, quota_limit))):
            sid = doc_id("slot", owner_user_id, n)
            try:
                self._create(COL_PUBLISH_SLOTS, sid, {"owner_user_id": owner_user_id, "slot": n,
                                                      "draft_id": draft_id, "share_id": new_share_id}, [])
                return new_share_id
            except _Conflict:
                slot = self._get(COL_PUBLISH_SLOTS, sid)
                if slot.get("draft_id") == draft_id:
                    return str(slot["share_id"])  # chinh draft nay da claim (lan truoc chet / song song)
        raise QuotaExceeded(quota_limit, quota_limit)

    def publish(self, *, owner_user_id: str, draft_id: str, expected_revision: int,
                content: PublishContent, new_share_id: str, quota_limit: int,
                now: str) -> Tuple[ShareRecord, VersionRecord, bool]:
        draft = self._read_draft(draft_id)
        if draft is None or draft.owner_user_id != owner_user_id:
            raise StoreNotFound(draft_id)
        if draft.revision != expected_revision:
            raise RevisionConflict(draft.revision)

        found = self._share_for_draft(draft_id)
        if found is None:
            share_id = self._claim_slot(owner_user_id, draft_id, new_share_id, quota_limit)
            try:
                self._create(COL_SHARES, share_id, {
                    "share_id": share_id, "owner_user_id": owner_user_id, "draft_id": draft_id,
                    "latest_version": 0, "created_at": now}, [])
            except _Conflict:
                pass  # cung draft da tao (lan truoc chet / song song)
            found = self._resolve_share(self._get(COL_SHARES, share_id))
        doc, latest = found
        if doc.get("draft_id") != draft_id or doc.get("owner_user_id") != owner_user_id:
            raise PublishConflict("share belongs to another draft")
        share_id = str(doc["share_id"])
        if latest >= 1:
            current = self.get_version(share_id, latest)
            if current is not None and current.draft_revision == draft.revision:
                return self._share_record(doc, latest), current, True
        version_no = latest + 1

        version = build_version(share_id, version_no, draft, content, now)
        keys_id = doc_id("k", share_id, version_no, draft.draft_id, draft.revision)
        try:
            self._create(COL_VERSION_KEYS, keys_id, {
                "share_id": share_id, "version": version_no,
                "content": json.dumps([k.model_dump(mode="json") for k in version.keys],
                                      ensure_ascii=False)}, [])
        except _Conflict:
            pass  # cung (share, version, draft revision) => cung noi dung khoa
        try:
            self._create(COL_VERSIONS, doc_id("v", share_id, version_no), {
                "share_id": share_id, "version": version_no, "draft_id": draft.draft_id,
                "draft_revision": draft.revision, "owner_user_id": owner_user_id,
                "keys_doc_id": keys_id, "content": _dump(version.public)}, [])
        except _Conflict as exc:
            existing = self.get_version(share_id, version_no)
            if existing is not None and existing.draft_revision == draft.revision:
                return self._share_record(doc, version_no), existing, True
            raise PublishConflict("version already exists") from exc
        try:
            self._patch(COL_SHARES, share_id, {"latest_version": version_no})
        except (StoreUnavailable, _Missing):
            pass
        return self._share_record(doc, version_no), version, False

    def count_published(self, owner_user_id: str) -> int:
        return self._count_slots(owner_user_id)

    def get_share(self, share_id: str) -> Optional[ShareRecord]:
        try:
            doc, latest = self._resolve_share(self._get(COL_SHARES, share_id))
        except _Missing:
            return None
        return self._share_record(doc, latest) if latest >= 1 else None

    def get_version(self, share_id: str, version: int) -> Optional[VersionRecord]:
        try:
            v = self._get(COL_VERSIONS, doc_id("v", share_id, version))
            k = self._get(COL_VERSION_KEYS, str(v["keys_doc_id"]))
        except _Missing:
            return None
        return VersionRecord.model_validate({
            "share_id": share_id, "version": version, "draft_id": v["draft_id"],
            "draft_revision": v["draft_revision"], "owner_user_id": v["owner_user_id"],
            "public": json.loads(v["content"]),
            "keys": json.loads(k["content"]),
        })


    # -- sessions ---------------------------------------------------------------------

    @staticmethod
    def _session_head(rec: SessionRecord) -> Dict[str, Any]:
        return {"session_id": rec.session_id, "participant_user_id": rec.participant_user_id,
                "share_id": rec.share_id, "state_revision": rec.state_revision,
                "content": _dump(rec)}

    def create_session(self, record: SessionRecord) -> SessionRecord:
        try:
            self._create(COL_SESSIONS, record.session_id, self._session_head(record), [])
        except _Conflict as exc:
            raise RevisionConflict(None, "session id already exists") from exc
        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        return self._read_logged(COL_SESSIONS, COL_SESSION_STATES, session_id, SessionRecord,
                                 lambda r: r.state_revision, self._session_head)

    def replace_session(self, record: SessionRecord, *,
                        expected_state_revision: int) -> SessionRecord:
        current = self.get_session(record.session_id)
        if current is None:
            raise StoreNotFound(record.session_id)
        if (current.state_revision != expected_state_revision
                or record.state_revision != expected_state_revision + 1
                or current.participant_user_id != record.participant_user_id):
            raise RevisionConflict(current.state_revision)
        return self._cas_logged(COL_SESSIONS, COL_SESSION_STATES, record.session_id, record,
                                expected_state_revision, lambda r: r.state_revision,
                                self._session_head)

    # -- grants ------------------------------------------------------------------------

    def put_grant(self, record: GrantRecord) -> GrantRecord:
        data = {"grant_id": record.grant_id, "user_id": record.user_id, "content": _dump(record)}
        try:
            self._create(COL_GRANTS, record.grant_id, data, [])
        except _Conflict:
            self._patch(COL_GRANTS, record.grant_id, data)
        return record

    def list_grants(self, user_id: str) -> List[GrantRecord]:
        rows = [GrantRecord.model_validate_json(d["content"])
                for d in self._list_all(COL_GRANTS, [q_equal("user_id", user_id)])]
        rows = [g for g in rows if g.user_id == user_id]
        rows.sort(key=lambda g: (g.created_at, g.grant_id))
        return rows

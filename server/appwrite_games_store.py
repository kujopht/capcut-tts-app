"""
Kho mini-game tren Appwrite — Social & Play V1 Goi C, §7.

Cung giao dien voi `MockGamesStore` (`server/games_store.py`) —
`games_service.py` khong biet dang chay tren kho nao, dung y het
`AppwriteGamificationStore`/`MockGamificationStore`.

BON collection RIENG, ADDITIVE, production CHUA duoc migrate (xem
`docs/migrations/SOCIAL_PLAY_V1_GAMES_SCHEMA.md`):
`game_rooms`, `game_room_versions` (CAS marker cho phong), `game_runs`,
`game_run_versions` (CAS marker cho luot Memory — bang RIENG voi phong, xem
ghi chu o dac ta §7 "your call"), `game_results`.

CANH BAO QUAN TRONG: toan bo lop nay CHUA duoc kiem tren mot du an Appwrite
THAT — chi co test hop dong voi client gia lap
(`server/tests/test_games_appwrite_contract.py`). Ky thuat transaction
(tao marker + cap nhat hang trong CUNG mot transaction) LAP LAI y het
`AppwriteMetadataStore.claim_job` (`server/appwrite_store.py`) — cai DO da
duoc do that tren Appwrite Cloud 1.9.6, nhung ban sao chep nay thi chua.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError, raise_for_appwrite_404
from server.config import AppwriteSettings
from server.secret_redaction import thong_diep_loi_an_toan
from server.games_domain import GameResult, MemoryRun, Room
from server.games_store import GamesConflict

COL_ROOMS = "game_rooms"
COL_ROOM_VERSIONS = "game_room_versions"
COL_RUNS = "game_runs"
COL_RUN_VERSIONS = "game_run_versions"
COL_RESULTS = "game_results"

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute, "values": list(values)})


def q_greater_equal(attribute: str, value: Any) -> str:
    return json.dumps({"method": "greaterThanEqual", "attribute": attribute, "values": [value]})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def _result_row_id(result_id: str) -> str:
    """Appwrite id: <=36 ky tu, `[a-zA-Z0-9._-]`. `result_id` THAT co dang
    `"{source_id}|{user_id}"` (chua `|`, va co the dai hon 36) — bam sha256
    giu id hop le, `result_id` doc duoc van luu nguyen trong mot truong."""
    return "gr_" + hashlib.sha256(result_id.encode("utf-8")).hexdigest()[:24]


def _room_to_row(r: Room) -> Dict[str, Any]:
    return {
        "code": r.code, "game": r.game, "rule_version": r.rule_version,
        "host_id": r.host_id, "seat_x": r.seat_x, "seat_o": r.seat_o,
        "ready_x": r.ready_x, "ready_o": r.ready_o, "status": r.status,
        "match_no": r.match_no, "board": r.board,
        "moves": json.dumps(r.moves), "turn": r.turn, "winner": r.winner,
        "win_line": json.dumps(r.win_line), "end_reason": r.end_reason,
        "last_seen_x": r.last_seen_x, "last_seen_o": r.last_seen_o,
        "rematch_x": r.rematch_x, "rematch_o": r.rematch_o,
        "settlement": r.settlement, "started_at": r.started_at,
        "finished_at": r.finished_at, "created_at": r.created_at,
        "updated_at": r.updated_at, "version": r.version,
    }


def _room_from_row(row: Dict[str, Any]) -> Room:
    return Room(
        room_id=str(row.get("$id") or row.get("room_id") or ""),
        code=str(row.get("code") or ""), game=str(row.get("game") or "caro"),
        rule_version=str(row.get("rule_version") or ""),
        host_id=str(row.get("host_id") or ""),
        seat_x=str(row.get("seat_x") or ""), seat_o=str(row.get("seat_o") or ""),
        ready_x=bool(row.get("ready_x") or False),
        ready_o=bool(row.get("ready_o") or False),
        status=str(row.get("status") or "lobby"),
        match_no=int(row.get("match_no") or 1),
        board=str(row.get("board") or ""),
        moves=json.loads(row.get("moves") or "[]"),
        turn=str(row.get("turn") or "x"), winner=str(row.get("winner") or ""),
        win_line=json.loads(row.get("win_line") or "[]"),
        end_reason=str(row.get("end_reason") or ""),
        last_seen_x=str(row.get("last_seen_x") or ""),
        last_seen_o=str(row.get("last_seen_o") or ""),
        rematch_x=bool(row.get("rematch_x") or False),
        rematch_o=bool(row.get("rematch_o") or False),
        settlement=str(row.get("settlement") or "none"),
        started_at=str(row.get("started_at") or ""),
        finished_at=str(row.get("finished_at") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        version=int(row.get("version") or 1),
    )


def _run_to_row(r: MemoryRun) -> Dict[str, Any]:
    return {
        "user_id": r.user_id, "difficulty": r.difficulty, "rows": r.rows,
        "cols": r.cols, "layout": json.dumps(r.layout),
        "matched": json.dumps(r.matched), "open_index": r.open_index,
        "flips": json.dumps(r.flips), "moves": r.moves, "status": r.status,
        "started_at": r.started_at, "finished_at": r.finished_at,
        "score": r.score, "season": r.season, "rule_version": r.rule_version,
        "settlement": r.settlement, "version": r.version,
    }


def _run_from_row(row: Dict[str, Any]) -> MemoryRun:
    return MemoryRun(
        run_id=str(row.get("$id") or row.get("run_id") or ""),
        user_id=str(row.get("user_id") or ""),
        difficulty=str(row.get("difficulty") or ""),
        rows=int(row.get("rows") or 0), cols=int(row.get("cols") or 0),
        layout=json.loads(row.get("layout") or "[]"),
        matched=json.loads(row.get("matched") or "[]"),
        open_index=int(row.get("open_index") if row.get("open_index") is not None else -1),
        flips=json.loads(row.get("flips") or "[]"),
        moves=int(row.get("moves") or 0), status=str(row.get("status") or "active"),
        started_at=str(row.get("started_at") or ""),
        finished_at=str(row.get("finished_at") or ""),
        score=int(row.get("score") or 0), season=str(row.get("season") or ""),
        rule_version=str(row.get("rule_version") or ""),
        settlement=str(row.get("settlement") or "none"),
        version=int(row.get("version") or 1),
    )


def _result_to_row(r: GameResult) -> Dict[str, Any]:
    return {
        "result_id": r.result_id, "game": r.game, "season": r.season,
        "user_id": r.user_id, "opponent_id": r.opponent_id,
        "outcome": r.outcome, "points": r.points, "difficulty": r.difficulty,
        "xp_awarded": r.xp_awarded, "xp_entries": json.dumps(r.xp_entries),
        "reasons": json.dumps(r.reasons), "validated": r.validated,
        "rule_version": r.rule_version, "source_id": r.source_id,
        "created_at": r.created_at,
    }


def _result_from_row(row: Dict[str, Any]) -> GameResult:
    return GameResult(
        result_id=str(row.get("result_id") or ""), game=str(row.get("game") or ""),
        season=str(row.get("season") or ""), user_id=str(row.get("user_id") or ""),
        opponent_id=str(row.get("opponent_id") or ""),
        outcome=str(row.get("outcome") or ""), points=int(row.get("points") or 0),
        difficulty=str(row.get("difficulty") or ""),
        xp_awarded=int(row.get("xp_awarded") or 0),
        xp_entries=json.loads(row.get("xp_entries") or "[]"),
        reasons=json.loads(row.get("reasons") or "[]"),
        validated=bool(row.get("validated") or False),
        rule_version=str(row.get("rule_version") or ""),
        source_id=str(row.get("source_id") or ""),
        created_at=str(row.get("created_at") or ""),
    )


class AppwriteGamesStore:
    """Ban Appwrite cua `MockGamesStore` — cung giao dien, KHAC ha tang.
    `client` co the tiem mot doi tuong gia lap cho test hop dong, thay vi
    mo ket noi httpx that (cung quy uoc voi `AppwriteGamificationStore`)."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho mini-game. Cần cả bốn "
                "biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, "
                "APPWRITE_API_KEY, APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    # -- ha tang REST — GIONG HET AppwriteGamificationStore, xem ghi chu o do --

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _http(self) -> httpx.Client:
        if self._pool is None:
            self._pool = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._pool

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            response = self._http().request(method, url, json=payload,
                                            params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AppwriteUnavailableError(
                f"Không kết nối được Appwrite: {exc}") from exc
        if response.status_code == 404:
            raise_for_appwrite_404(response, path)
        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            raise NotFoundError(
                thong_diep_loi_an_toan(body, status_code=response.status_code))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
               permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id, "data": data, "permissions": permissions or []})

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": data})

    def _list_all(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            data = self._call("GET", self._docs(collection),
                              params={"queries[]": queries + [
                                  q_limit(PAGE_SIZE), q_offset(offset)]})
            page = list(data.get("documents") or [])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    def _page(self, collection: str, queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        data = self._call("GET", self._docs(collection), params={"queries[]": queries})
        return list(data.get("documents") or []), int(data.get("total") or 0)

    # ======================================================== phong (Caro)

    def create_room(self, room: Room) -> Room:
        self._create(COL_ROOMS, room.room_id, _room_to_row(room))
        return room

    def get_room(self, room_id: str) -> Room:
        row = self._get(COL_ROOMS, room_id)
        row["room_id"] = room_id
        return _room_from_row(row)

    def get_room_by_code(self, code: str) -> Optional[Room]:
        rows = self._list_all(COL_ROOMS, [q_equal("code", code)])
        if not rows:
            return None
        rows.sort(key=lambda r: str(r.get("created_at") or ""))
        return _room_from_row(rows[-1])

    def code_is_taken(self, code: str) -> bool:
        rows = self._list_all(COL_ROOMS, [q_equal("code", code)])
        return any(str(r.get("status")) != "closed" for r in rows)

    def save_room(self, room: Room, expected_version: int) -> Room:
        """CAS THAT bang transaction — tao marker `game_room_versions`
        (rowId=f"{room_id}-v{expected_version+1}", tinh duy nhat do database
        cuong che) VA cap nhat hang phong trong CUNG mot transaction. Marker
        da ton tai (nguoi khac vua ghi truoc) -> `GamesConflict`. Cung ky
        thuat DA DO tren Appwrite Cloud boi `AppwriteMetadataStore.claim_job`
        (xem `server/appwrite_store.py`) — noi day CHUA duoc kiem that."""
        from server.appwrite_store import TRANSACTION_TTL_SECONDS

        marker_id = f"{room.room_id}-v{expected_version + 1}"
        operations = [
            {"action": "create", "databaseId": self._db, "tableId": COL_ROOM_VERSIONS,
             "rowId": marker_id, "data": {"room_id": room.room_id,
                                         "version": expected_version + 1,
                                         "created_at": room.updated_at}},
            {"action": "update", "databaseId": self._db, "tableId": COL_ROOMS,
             "rowId": room.room_id, "data": _room_to_row(room)},
        ]
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": operations})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception as exc:
            raise GamesConflict("Phòng vừa thay đổi, thử lại.") from exc
        if result.get("status") != "committed":
            raise GamesConflict("Phòng vừa thay đổi, thử lại.")
        return room

    def touch_seat(self, room_id: str, seat: str, iso: str) -> None:
        """Cap nhat CHI `last_seen_*`, KHONG qua transaction/version — cung
        ly do voi `MockGamesStore.touch_seat` (tranh CAS storm khi client
        poll)."""
        field = "last_seen_x" if seat == "x" else "last_seen_o"
        try:
            self._update(COL_ROOMS, room_id, {field: iso})
        except NotFoundError:
            pass

    def list_pending_rooms(self) -> List[Room]:
        rows = self._list_all(COL_ROOMS, [
            q_equal("status", "finished"), q_equal("settlement", "pending")])
        return [_room_from_row(r) for r in rows]

    def list_rooms(self) -> List[Room]:
        rows = self._list_all(COL_ROOMS, [])
        return [_room_from_row(r) for r in rows]

    # ======================================================== luot (Memory)

    def create_run(self, run: MemoryRun) -> MemoryRun:
        self._create(COL_RUNS, run.run_id, _run_to_row(run))
        return run

    def get_run(self, run_id: str) -> MemoryRun:
        row = self._get(COL_RUNS, run_id)
        row["run_id"] = run_id
        return _run_from_row(row)

    def save_run(self, run: MemoryRun, expected_version: int) -> MemoryRun:
        """CAS THAT — cung ky thuat voi `save_room`, marker RIENG
        (`game_run_versions`) de khong tranh id voi phong."""
        from server.appwrite_store import TRANSACTION_TTL_SECONDS

        marker_id = f"{run.run_id}-v{expected_version + 1}"
        operations = [
            {"action": "create", "databaseId": self._db, "tableId": COL_RUN_VERSIONS,
             "rowId": marker_id, "data": {"run_id": run.run_id,
                                         "version": expected_version + 1}},
            {"action": "update", "databaseId": self._db, "tableId": COL_RUNS,
             "rowId": run.run_id, "data": _run_to_row(run)},
        ]
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": operations})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception as exc:
            raise GamesConflict("Lượt chơi vừa thay đổi, thử lại.") from exc
        if result.get("status") != "committed":
            raise GamesConflict("Lượt chơi vừa thay đổi, thử lại.")
        return run

    def list_pending_runs(self) -> List[MemoryRun]:
        rows = self._list_all(COL_RUNS, [
            q_equal("status", "completed"), q_equal("settlement", "pending")])
        return [_run_from_row(r) for r in rows]

    def list_runs_for_user(self, user_id: str) -> List[MemoryRun]:
        rows = self._list_all(COL_RUNS, [q_equal("user_id", user_id)])
        return [_run_from_row(r) for r in rows]

    # ======================================================== ket qua

    def create_result(self, result: GameResult) -> bool:
        try:
            self._create(COL_RESULTS, _result_row_id(result.result_id),
                        _result_to_row(result))
        except NotFoundError:
            return False
        return True

    def get_result(self, result_id: str) -> Optional[GameResult]:
        try:
            row = self._get(COL_RESULTS, _result_row_id(result_id))
        except NotFoundError:
            return None
        return _result_from_row(row)

    def list_results_for_source(self, source_id: str) -> List[GameResult]:
        rows = self._list_all(COL_RESULTS, [q_equal("source_id", source_id)])
        return [_result_from_row(r) for r in rows]

    def list_results_for_user(self, user_id: str, limit: int) -> List[GameResult]:
        rows = self._list_all(COL_RESULTS, [q_equal("user_id", user_id)])
        ds = [_result_from_row(r) for r in rows]
        ds.sort(key=lambda r: r.created_at, reverse=True)
        return ds[:max(0, limit)]

    def list_results_for_pair_since(self, user_a: str, user_b: str,
                                    since_iso: str) -> List[GameResult]:
        rows = self._list_all(COL_RESULTS, [
            q_equal("game", "caro"), q_equal("user_id", user_a),
            q_equal("opponent_id", user_b),
            q_greater_equal("created_at", since_iso)])
        return [r for r in (_result_from_row(x) for x in rows) if r.validated]

    def list_results_for_user_since(self, user_id: str, game: str,
                                    since_iso: str) -> List[GameResult]:
        rows = self._list_all(COL_RESULTS, [
            q_equal("game", game), q_equal("user_id", user_id),
            q_greater_equal("created_at", since_iso)])
        return [r for r in (_result_from_row(x) for x in rows) if r.validated]

    def list_seasons(self, game: str) -> List[str]:
        rows = self._list_all(COL_RESULTS, [q_equal("game", game)])
        mua = {str(r.get("season")) for r in rows if r.get("validated")}
        return sorted(mua, reverse=True)

    def list_results_by_game_season(
            self, game: str, season: str, difficulty: str = "") -> List[GameResult]:
        queries = [q_equal("game", game), q_equal("season", season)]
        if difficulty:
            queries.append(q_equal("difficulty", difficulty))
        rows = self._list_all(COL_RESULTS, queries)
        return [r for r in (_result_from_row(x) for x in rows) if r.validated]


#: `build_games_store` CHINH TAC nam o `server/games_store.py` (import
#: `AppwriteGamesStore` tu day CO DIEU KIEN, tranh import vong luc nap
#: module) — KHONG lap lai ham o day de tranh hai nguon su that.

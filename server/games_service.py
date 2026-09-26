"""
Tang dieu phoi mini-game — Social & Play V1 Goi C.

Noi DUY NHAT ghi vao `games_store`/`gamification_store` cho phong (Caro),
luot (Memory Runes), settlement va bang xep hang. Route trong `server/
main.py` khong bao gio tu ghi thang, luon di qua day — cung nguyen tac voi
`gamification_service.py`/`social_service.py`.

Moi mutation phong/luot deu di qua CAS (`games_store.save_room`/`save_run`
+ `expected_version`) — xem `_mutate_room`/`_mutate_run`. `GameError` mang
`status_code` HTTP de route anh xa thang, khong bao gio 500 cho mot vi pham
luat choi.
"""

from __future__ import annotations

import copy
import secrets
import threading
from contextlib import contextmanager
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from server.domain import now_iso
from server.gamification import id_xp_entry
from server.gamification_domain import XpLedgerEntry
from server.games_domain import (
    BOARD_CELLS,
    DAILY_GAME_XP_CAP,
    EMPTY_BOARD,
    GameResult,
    MEMORY_DIFFICULTIES,
    MEMORY_MAX_SECONDS,
    MEMORY_MIN_FLIP_INTERVAL_MS,
    MemoryRun,
    RULE_CARO,
    RULE_MEMORY,
    Room,
    apply_move,
    check_win,
    decide_caro_rewards,
    decide_memory_reward,
    generate_room_code,
    is_board_full,
    memory_elapsed_seconds,
    memory_score,
    memory_run_view,
    new_memory_run,
    new_room,
    new_room_id,
    parse_iso,
    result_id_for,
    room_view,
    season_key,
)
from server.games_store import GamesConflict


class GameError(ValueError):
    """Loi CO Y NGHIA cho nguoi choi — mang `status_code` de route anh xa
    thang sang HTTPException, KHONG BAO GIO 500 cho mot vi pham luat choi."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


MAX_MUTATE_ATTEMPTS = 5


# =============================================================================
# CAS retry — phong (Caro)
# =============================================================================


def _mutate_room(games_store: Any, room_id: str, mutator) -> Room:
    for _ in range(MAX_MUTATE_ATTEMPTS):
        room = games_store.get_room(room_id)
        work = copy.deepcopy(room)
        result = mutator(work)
        if result is None:
            return room
        result.version = room.version + 1
        result.updated_at = now_iso()
        try:
            return games_store.save_room(result, room.version)
        except GamesConflict:
            continue
    raise GameError("Phòng vừa thay đổi, thử lại.", 409)


def _mutate_run(games_store: Any, run_id: str, mutator) -> MemoryRun:
    for _ in range(MAX_MUTATE_ATTEMPTS):
        run = games_store.get_run(run_id)
        work = copy.deepcopy(run)
        result = mutator(work)
        if result is None:
            return run
        result.version = run.version + 1
        try:
            return games_store.save_run(result, run.version)
        except GamesConflict:
            continue
    raise GameError("Lượt chơi vừa thay đổi, thử lại.", 409)


def _seat_connected(last_seen: str, now: Optional[str] = None) -> bool:
    from server.games_domain import DISCONNECT_GRACE_SECONDS

    if not last_seen:
        return False
    try:
        delta = (parse_iso(now or now_iso()) - parse_iso(last_seen)).total_seconds()
    except Exception:
        return False
    return delta <= DISCONNECT_GRACE_SECONDS


def _seconds_since(iso_ts: str, now: str) -> float:
    if not iso_ts:
        return float("inf")
    try:
        return (parse_iso(now) - parse_iso(iso_ts)).total_seconds()
    except Exception:
        return 0.0


def _expire_room_if_needed(games_store: Any, room: Room) -> Room:
    """Lobby qua han (`LOBBY_TTL_SECONDS`) -> dong, khong thuong. Phong dang
    choi ma CA HAI ghe vang mat qua `ABANDON_SECONDS` -> ket thuc `abandon`
    (khong thuong — xem `decide_caro_rewards`). Goi LUOI (mot lan moi khi
    doc) thay vi mot tien trinh nen rieng, dung dac ta §2."""
    from server.games_domain import ABANDON_SECONDS, LOBBY_TTL_SECONDS

    now = now_iso()
    work = copy.deepcopy(room)
    changed = False
    if room.status == "lobby":
        if _seconds_since(room.updated_at, now) > LOBBY_TTL_SECONDS:
            work.status = "closed"
            changed = True
    elif room.status == "playing":
        absent_x = _seconds_since(room.last_seen_x or room.updated_at, now) > ABANDON_SECONDS
        absent_o = _seconds_since(room.last_seen_o or room.updated_at, now) > ABANDON_SECONDS
        if absent_x and absent_o:
            work.status = "finished"
            work.winner = ""
            work.end_reason = "abandon"
            work.finished_at = now
            work.settlement = "pending"
            changed = True
    if not changed:
        return room
    work.version = room.version + 1
    work.updated_at = now
    try:
        return games_store.save_room(work, room.version)
    except GamesConflict:
        return games_store.get_room(room.room_id)


# =============================================================================
# Settlement (exactly-once, recoverable) — §4/§5 cua dac ta
# =============================================================================


def _day_start_iso(finished_at: str) -> str:
    return (finished_at or now_iso())[:10] + "T00:00:00+00:00"


def _xp_used_today(gamification_store: Any, user_id: str, day_start: str) -> int:
    events = gamification_store.list_xp_events_since(user_id, day_start)
    return sum(e.xp_awarded for e in events if e.event_type.startswith("game_"))


def _planned_entries(user_id: str, source_id_with_rule: str,
                     xp_events: List[Tuple[str, int]]) -> List[dict]:
    """Danh sach entry XP DU DINH cho MOT quyet dinh — tinh TAT DINH tu
    `(user_id, event_type, source_id_with_rule)`, KHONG can biet ket qua
    cong XP (xem `_award_stored_entries`: quyet dinh dong bang o day, viec
    cong XP la mot buoc SAU, co the lap lai an toan)."""
    return [{"event_type": et, "entry_id": id_xp_entry(user_id, et, source_id_with_rule),
             "xp": xp} for et, xp in xp_events]


def _award_stored_entries(gamification_store: Any, user_id: str,
                          xp_entries: List[dict], source_kind: str,
                          source_id_with_rule: str) -> None:
    """Cong XP cho TUNG entry trong `xp_entries` DA LUU (hang `GameResult`) —
    KHONG BAO GIO tinh lai quyet dinh o day. Goi lai an toan bao nhieu lan
    cung duoc: `award_xp_atomic` tu chan trung `entry_id` (xem dac ta §4
    "decisions frozen at first persistence" — recompute lai voi trang thai
    cap MOI se cho ket qua SAI neu request truoc do da cong mot phan)."""
    for entry in xp_entries:
        obj = XpLedgerEntry(
            entry_id=entry["entry_id"], user_id=user_id,
            event_type=entry["event_type"], source_kind=source_kind,
            source_id=source_id_with_rule, xp_awarded=entry["xp"])
        gamification_store.award_xp_atomic(obj)


def _mark_room_settled(games_store: Any, room_id: str) -> None:
    for _ in range(MAX_MUTATE_ATTEMPTS):
        current = games_store.get_room(room_id)
        if current.settlement == "settled":
            return
        work = copy.deepcopy(current)
        work.settlement = "settled"
        work.version = current.version + 1
        work.updated_at = now_iso()
        try:
            games_store.save_room(work, current.version)
            return
        except GamesConflict:
            continue


def _mark_run_settled(games_store: Any, run_id: str) -> None:
    for _ in range(MAX_MUTATE_ATTEMPTS):
        current = games_store.get_run(run_id)
        if current.settlement == "settled":
            return
        work = copy.deepcopy(current)
        work.settlement = "settled"
        work.version = current.version + 1
        try:
            games_store.save_run(work, current.version)
            return
        except GamesConflict:
            continue


#: Khoa quyet toan THEO NGUOI CHOI trong tien trinh. Doc tran (van/cap/ngay, XP game/ngay) ->
#: quyet dinh -> luu hang ket qua phai la MOT doan tuan tu cho moi nguoi choi lien quan: khong co
#: khoa, hai van KHAC NHAU cua cung mot nguoi ket thuc cung luc co the cung doc "con 1 suat" va
#: cung duoc tinh (do that: test dong thoi `test_games_concurrency`). Voi khoa nay tran la CUNG
#: trong MOT tien trinh API (production hien chay mot tien trinh uvicorn). Nhieu instance -> moi
#: instance mot bo khoa, van co the vuot: tai lieu goi do la tran MEM, khong phai hard cap.
_KHOA_QT_BAO_VE = threading.Lock()
_KHOA_QT: Dict[str, threading.Lock] = {}


@contextmanager
def _khoa_quyet_toan(*user_ids: str):
    khoa_ids = sorted({u for u in user_ids if u})  # thu tu co dinh -> khong the ket cheo (deadlock)
    with _KHOA_QT_BAO_VE:
        cac_khoa = [_KHOA_QT.setdefault(k, threading.Lock()) for k in khoa_ids]
    for k in cac_khoa:
        k.acquire()
    try:
        yield
    finally:
        for k in reversed(cac_khoa):
            k.release()


def _settle_room(games_store: Any, gamification_store: Any, room: Room) -> None:
    if room.settlement == "settled":
        return
    with _khoa_quyet_toan(room.seat_x, room.seat_o):
        _settle_room_trong_khoa(games_store, gamification_store, room)


def _settle_room_trong_khoa(games_store: Any, gamification_store: Any, room: Room) -> None:
    """THU TU BAT BUOC (xem dac ta §4 "decisions frozen at first
    persistence" — phat hien qua review): quyet dinh -> `create_result`
    (hang PLANNED, gom san `xp_entries`/`xp_awarded` DU DINH) TRUOC, roi moi
    cong XP tu CHINH hang da luu (thua `create_result` -> doc lai hang cua
    nguoi thang, cong tu do — KHONG BAO GIO tinh lai quyet dinh). Nho vay
    mot lan "crash" giua hai buoc luon phuc hoi dung: crash TRUOC
    `create_result` -> chua co gi, lam lai tu dau; crash SAU `create_result`
    nhung TRUOC khi cong het XP -> `award_xp_atomic` chi con thieu entry
    nao chua cong (cac entry da cong tra `None`, vo hai)."""
    if room.settlement == "settled":
        return
    source_id = room.match_id
    existing = {r.user_id: r for r in games_store.list_results_for_source(source_id)}
    seats = {"x": room.seat_x, "o": room.seat_o}
    users = [u for u in seats.values() if u]

    decisions: Dict[str, dict] = {}
    if len(set(users)) == 2 and not all(u in existing for u in users):
        day_start = _day_start_iso(room.finished_at)
        # LOAI TRU chinh tran nay khoi phep dem: neu mot lan settle TRUOC do
        # da crash GIUA hai lan `create_result` cua hai nguoi (usr_x da co
        # hang, usr_o thi chua), lan thu lai o day PHAI khong tu dem hang
        # cua usr_x cho CHINH tran dang settle vao tran-voi-doi-thu-hom-nay
        # cua usr_o — neu khong tran nay tu lam day tran cua chinh no.
        pair_count_today = len([
            r for r in games_store.list_results_for_pair_since(
                room.seat_x, room.seat_o, day_start)
            if r.source_id != source_id])
        xp_used_today = {u: _xp_used_today(gamification_store, u, day_start)
                         for u in set(users)}
        decisions = decide_caro_rewards(
            room, pair_count_today=pair_count_today, xp_used_today=xp_used_today)

    season = season_key(room.finished_at)
    for user_id in set(users):
        row = existing.get(user_id)
        if row is None:
            decision = decisions.get(user_id)
            if decision is None:
                continue
            opponent_id = next((u for seat, u in seats.items()
                                if u and u != user_id), "")
            source_id_rule = f"{source_id}|{RULE_CARO}"
            xp_entries = _planned_entries(user_id, source_id_rule, decision["xp_events"])
            planned = GameResult(
                result_id=result_id_for(source_id, user_id), game="caro",
                season=season, user_id=user_id, opponent_id=opponent_id,
                outcome=decision["outcome"], points=decision["points"],
                difficulty="", xp_awarded=sum(e["xp"] for e in xp_entries),
                xp_entries=xp_entries, reasons=decision["reasons"],
                validated=decision["validated"], rule_version=room.rule_version,
                source_id=source_id)
            row = planned if games_store.create_result(planned) else (
                games_store.get_result(planned.result_id) or planned)
        _award_stored_entries(gamification_store, user_id, row.xp_entries,
                              "game_match", f"{source_id}|{RULE_CARO}")

    _mark_room_settled(games_store, room.room_id)


def _settle_run(games_store: Any, gamification_store: Any, run: MemoryRun) -> None:
    if run.settlement == "settled":
        return
    with _khoa_quyet_toan(run.user_id):
        _settle_run_trong_khoa(games_store, gamification_store, run)


def _settle_run_trong_khoa(games_store: Any, gamification_store: Any, run: MemoryRun) -> None:
    """Cung thu tu voi `_settle_room` — xem docstring o do."""
    if run.settlement == "settled":
        return
    source_id = run.run_id
    result_id = result_id_for(source_id, run.user_id)
    row = games_store.get_result(result_id)
    if row is None:
        day_start = _day_start_iso(run.finished_at)
        runs_count_today = len(games_store.list_results_for_user_since(
            run.user_id, "memory", day_start))
        xp_used_today = _xp_used_today(gamification_store, run.user_id, day_start)
        decision = decide_memory_reward(
            run, runs_count_today=runs_count_today, xp_used_today=xp_used_today)
        source_id_rule = f"{source_id}|{RULE_MEMORY}"
        xp_entries = _planned_entries(run.user_id, source_id_rule, decision["xp_events"])
        planned = GameResult(
            result_id=result_id, game="memory", season=run.season,
            user_id=run.user_id, opponent_id="", outcome=decision["outcome"],
            points=decision["points"], difficulty=run.difficulty,
            xp_awarded=sum(e["xp"] for e in xp_entries), xp_entries=xp_entries,
            reasons=decision["reasons"], validated=decision["validated"],
            rule_version=run.rule_version, source_id=source_id)
        row = planned if games_store.create_result(planned) else (
            games_store.get_result(result_id) or planned)

    _award_stored_entries(gamification_store, run.user_id, row.xp_entries,
                          "game_run", f"{source_id}|{RULE_MEMORY}")
    _mark_run_settled(games_store, run.run_id)


def settle(games_store: Any, gamification_store: Any, source: Any) -> None:
    if isinstance(source, Room):
        _settle_room(games_store, gamification_store, source)
    elif isinstance(source, MemoryRun):
        _settle_run(games_store, gamification_store, source)


def settle_pending(games_store: Any, gamification_store: Any) -> int:
    """Quet MOI phong/luot dang `settlement == 'pending'` va settle —
    goi o cuoi moi hanh dong ket thuc, khi GET mot phong/luot dang pending,
    VA mot lan luc khoi dong (best-effort, khong bao gio lam sap server —
    xem dac ta §4). Tra so luong DA settle trong lan goi nay."""
    count = 0
    for room in games_store.list_pending_rooms():
        try:
            settle(games_store, gamification_store, room)
            count += 1
        except Exception:
            continue
    for run in games_store.list_pending_runs():
        try:
            settle(games_store, gamification_store, run)
            count += 1
        except Exception:
            continue
    return count


# =============================================================================
# Phong (Caro) — hanh dong nguoi choi
# =============================================================================


def create_room(games_store: Any, user_id: str, rng: Optional[Any] = None) -> Room:
    code = None
    for _ in range(10):
        candidate = generate_room_code(rng)
        if not games_store.code_is_taken(candidate):
            code = candidate
            break
    if code is None:
        raise GameError("Không tạo được mã phòng, thử lại.", 409)
    room = new_room(new_room_id(rng), code, user_id)
    return games_store.create_room(room)


def _room_by_code_or_404(games_store: Any, code: str) -> Room:
    room = games_store.get_room_by_code(code)
    if room is None:
        raise GameError("Không tìm thấy phòng.", 404)
    return _expire_room_if_needed(games_store, room)


def get_room(games_store: Any, gamification_store: Any, code: str) -> Room:
    room = _room_by_code_or_404(games_store, code)
    if room.settlement == "pending":
        settle(games_store, gamification_store, room)
        room = games_store.get_room(room.room_id)
    return room


def join_room(games_store: Any, user_id: str, code: str) -> Room:
    room0 = _room_by_code_or_404(games_store, code)
    if room0.status == "closed":
        raise GameError("Phòng đã đóng.", 404)

    def mutator(r: Room) -> Optional[Room]:
        if r.seat_of(user_id) is not None:
            return None  # Da ngoi san — reconnect, khong doi gi.
        if r.status != "lobby":
            raise GameError(
                "Phòng đã đủ người." if r.status == "playing" else "Phòng đã đóng.", 409)
        if not r.seat_x:
            r.seat_x = user_id
        elif not r.seat_o:
            r.seat_o = user_id
        else:
            raise GameError("Phòng đã đủ người.", 409)
        return r

    return _mutate_room(games_store, room0.room_id, mutator)


def set_ready(games_store: Any, user_id: str, code: str, ready: bool) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.status != "lobby":
            raise GameError("Phòng không ở trạng thái chờ.", 409)
        if seat == "x":
            r.ready_x = bool(ready)
        else:
            r.ready_o = bool(ready)
        if r.seat_x and r.seat_o and r.ready_x and r.ready_o:
            now = now_iso()
            r.status = "playing"
            r.started_at = now
            r.turn = "x"
            r.board = EMPTY_BOARD
            r.moves = []
            r.settlement = "none"
            r.last_seen_x = now
            r.last_seen_o = now
        return r

    return _mutate_room(games_store, room0.room_id, mutator)


def play_move(games_store: Any, gamification_store: Any, user_id: str, code: str,
             index: int, move_no: int) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        if r.status != "playing":
            raise GameError("Ván đã kết thúc.", 409)
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.turn != seat:
            raise GameError("Chưa tới lượt bạn.", 409)
        if move_no != len(r.moves):
            raise GameError("Nước đi đã cũ hoặc trùng.", 409)
        if not (0 <= index < BOARD_CELLS) or r.board[index] != ".":
            raise GameError("Ô không hợp lệ.", 400)

        r.board = apply_move(r.board, index, seat)
        r.moves.append([index, seat])
        now = now_iso()
        if seat == "x":
            r.last_seen_x = now
        else:
            r.last_seen_o = now

        win_line = check_win(r.board, index, seat)
        if win_line:
            r.status = "finished"
            r.winner = seat
            r.win_line = win_line
            r.end_reason = "five"
            r.finished_at = now
            r.settlement = "pending"
        elif is_board_full(r.board):
            r.status = "finished"
            r.winner = "draw"
            r.win_line = []
            r.end_reason = "draw"
            r.finished_at = now
            r.settlement = "pending"
        else:
            r.turn = r.opponent_seat(seat)
        return r

    room = _mutate_room(games_store, room0.room_id, mutator)
    if room.settlement == "pending":
        settle(games_store, gamification_store, room)
        room = games_store.get_room(room.room_id)
    return room


def resign(games_store: Any, gamification_store: Any, user_id: str, code: str) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.status != "playing":
            raise GameError("Ván đã kết thúc.", 409)
        r.status = "finished"
        r.winner = r.opponent_seat(seat)
        r.end_reason = "resign"
        r.finished_at = now_iso()
        r.settlement = "pending"
        return r

    room = _mutate_room(games_store, room0.room_id, mutator)
    if room.settlement == "pending":
        settle(games_store, gamification_store, room)
        room = games_store.get_room(room.room_id)
    return room


def claim_timeout(games_store: Any, gamification_store: Any, user_id: str,
                  code: str) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.status != "playing":
            raise GameError("Ván đã kết thúc.", 409)
        opp_seat = r.opponent_seat(seat)
        opp_last_seen = r.last_seen_o if opp_seat == "o" else r.last_seen_x
        if _seat_connected(opp_last_seen):
            raise GameError("Đối thủ vẫn đang kết nối.", 409)
        r.status = "finished"
        r.winner = seat
        r.end_reason = "timeout"
        r.finished_at = now_iso()
        r.settlement = "pending"
        return r

    room = _mutate_room(games_store, room0.room_id, mutator)
    if room.settlement == "pending":
        settle(games_store, gamification_store, room)
        room = games_store.get_room(room.room_id)
    return room


def rematch(games_store: Any, user_id: str, code: str) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.status != "finished":
            raise GameError("Ván chưa kết thúc.", 409)
        if seat == "x":
            r.rematch_x = True
        else:
            r.rematch_o = True
        if r.rematch_x and r.rematch_o:
            r.seat_x, r.seat_o = r.seat_o, r.seat_x
            r.match_no += 1
            r.board = EMPTY_BOARD
            r.moves = []
            r.turn = "x"
            r.winner = ""
            r.win_line = []
            r.end_reason = ""
            r.status = "playing"
            r.rematch_x = False
            r.rematch_o = False
            r.settlement = "none"
            now = now_iso()
            r.started_at = now
            r.finished_at = ""
            r.last_seen_x = now
            r.last_seen_o = now
        return r

    return _mutate_room(games_store, room0.room_id, mutator)


def leave(games_store: Any, gamification_store: Any, user_id: str, code: str) -> Room:
    room0 = _room_by_code_or_404(games_store, code)

    def mutator(r: Room) -> Optional[Room]:
        seat = r.seat_of(user_id)
        if seat is None:
            raise GameError("Bạn không ở trong phòng này.", 403)
        if r.status == "lobby":
            if seat == "x":
                r.seat_x = ""
                r.ready_x = False
            else:
                r.seat_o = ""
                r.ready_o = False
            if user_id == r.host_id or not (r.seat_x or r.seat_o):
                r.status = "closed"
            return r
        if r.status == "playing":
            # KHONG vacate ghe o day: `_settle_room` can THAY DUOC CA HAI
            # nguoi (seat_x/seat_o) de tinh thuong — vacate SOM se lam mot
            # tran da hop le (>=10 nuoc) mat trang tay ca hai phia (phat
            # hien qua review). Buoc vacate that su nam o pha HAI, sau khi
            # settle xong (xem duoi).
            r.status = "finished"
            r.winner = r.opponent_seat(seat)
            r.end_reason = "resign"
            r.finished_at = now_iso()
            r.settlement = "pending"
            return r
        if r.status == "finished":
            if seat == "x":
                r.seat_x = ""
            else:
                r.seat_o = ""
            if not r.seat_x and not r.seat_o:
                r.status = "closed"
            return r
        raise GameError("Phòng đã đóng.", 409)

    room = _mutate_room(games_store, room0.room_id, mutator)
    if room.settlement == "pending":
        settle(games_store, gamification_store, room)
        room = games_store.get_room(room.room_id)

    # Pha HAI: neu day la nhanh "dang choi -> finished vi roi" (nguoi roi
    # VAN CON ngoi ghe sau buoc tren), vacate ghe cua ho BAY GIO — sau khi
    # settlement da doc duoc ca hai nguoi.
    seat_after = room.seat_of(user_id)
    if seat_after is not None and room.status == "finished":
        def vacate_mutator(r2: Room) -> Optional[Room]:
            seat2 = r2.seat_of(user_id)
            if seat2 is None:
                return None
            if seat2 == "x":
                r2.seat_x = ""
            else:
                r2.seat_o = ""
            if not r2.seat_x and not r2.seat_o:
                r2.status = "closed"
            return r2

        room = _mutate_room(games_store, room.room_id, vacate_mutator)
    return room


def touch(games_store: Any, user_id: str, code: str) -> Room:
    room = _room_by_code_or_404(games_store, code)
    seat = room.seat_of(user_id)
    if seat:
        games_store.touch_seat(room.room_id, seat, now_iso())
        room = games_store.get_room(room.room_id)
    return room


def _profiles_for_room(identity: Any, room: Room) -> Dict[str, Any]:
    ids = [u for u in (room.seat_x, room.seat_o) if u]
    return identity.profiles_by_ids(ids) if ids else {}


def _anh_url(storage: Any, key: str) -> str:
    if storage is None or not key:
        return ""
    try:
        return storage.signed_url(key, expires_seconds=3600) or ""
    except Exception:
        return ""


def room_public_view(identity: Any, storage: Any, games_store: Any, room: Room,
                     viewer_id: str) -> dict:
    profiles_raw = _profiles_for_room(identity, room)
    profiles = {
        uid: type("Card", (), {
            "display_name": getattr(p, "display_name", "") or getattr(p, "username", ""),
            "username": getattr(p, "username", ""),
            "avatar_url": _anh_url(storage, getattr(p, "avatar_key", "")),
        })()
        for uid, p in profiles_raw.items()
    }
    rewards = None
    if room.settlement == "settled":
        results = games_store.list_results_for_source(room.match_id)
        if results:
            rewards = {
                r.user_id: {"xp": r.xp_awarded, "points": r.points, "reasons": r.reasons}
                for r in results
            }
    return room_view(room, viewer_id, profiles, rewards=rewards)


# =============================================================================
# Memory Runes
# =============================================================================


def start_run(games_store: Any, user_id: str, difficulty: str,
             rng: Optional[Any] = None) -> MemoryRun:
    if difficulty not in MEMORY_DIFFICULTIES:
        raise GameError("Độ khó không hợp lệ.", 400)
    run_id = f"mr_{secrets.token_hex(8)}"
    run = new_memory_run(run_id, user_id, difficulty, rng)
    return games_store.create_run(run)


def _expire_run_if_needed(games_store: Any, run: MemoryRun) -> MemoryRun:
    if run.status != "active" or memory_elapsed_seconds(run) <= MEMORY_MAX_SECONDS:
        return run

    def mutator(r: MemoryRun) -> Optional[MemoryRun]:
        if r.status != "active":
            return None
        r.status = "expired"
        r.finished_at = now_iso()
        return r

    return _mutate_run(games_store, run.run_id, mutator)


def get_run(games_store: Any, gamification_store: Any, user_id: str,
           run_id: str) -> MemoryRun:
    run = games_store.get_run(run_id)
    if run.user_id != user_id:
        raise GameError("Bạn không sở hữu lượt chơi này.", 403)
    run = _expire_run_if_needed(games_store, run)
    if run.settlement == "pending":
        settle(games_store, gamification_store, run)
        run = games_store.get_run(run_id)
    return run


def flip(games_store: Any, gamification_store: Any, user_id: str, run_id: str,
         index: int, seq: int) -> Tuple[MemoryRun, Optional[dict]]:
    run0 = games_store.get_run(run_id)
    if run0.user_id != user_id:
        raise GameError("Bạn không sở hữu lượt chơi này.", 403)

    flip_result: Dict[str, Any] = {}
    error_holder: List[GameError] = []

    def mutator(r: MemoryRun) -> Optional[MemoryRun]:
        flip_result.clear()
        if r.status == "expired":
            error_holder.append(GameError("Lượt chơi đã hết giờ.", 409))
            return None
        if r.status != "active":
            error_holder.append(GameError("Lượt chơi đã kết thúc.", 409))
            return None
        elapsed = memory_elapsed_seconds(r)
        if elapsed > MEMORY_MAX_SECONDS:
            r.status = "expired"
            r.finished_at = now_iso()
            error_holder.append(GameError("Lượt chơi đã hết giờ.", 409))
            return r
        if seq != len(r.flips):
            error_holder.append(GameError("Nước đi đã cũ hoặc trùng.", 409))
            return None
        if (not (0 <= index < r.rows * r.cols) or index in r.matched
                or index == r.open_index):
            error_holder.append(GameError("Ô không hợp lệ.", 400))
            return None
        now_ms = int(elapsed * 1000)
        if r.flips and (now_ms - r.flips[-1][1]) < MEMORY_MIN_FLIP_INTERVAL_MS:
            error_holder.append(GameError("Lật quá nhanh.", 429))
            return None

        r.flips.append([index, now_ms])
        if r.open_index < 0:
            r.open_index = index
            flip_result.update({"index": index, "key": r.layout[index],
                                "first_index": None, "first_key": None,
                                "matched": None})
        else:
            first_index = r.open_index
            first_key = r.layout[first_index]
            key = r.layout[index]
            r.moves += 1
            matched = first_key == key
            if matched:
                r.matched.extend([first_index, index])
            r.open_index = -1
            flip_result.update({"index": index, "key": key,
                                "first_index": first_index, "first_key": first_key,
                                "matched": matched})
            if len(r.matched) == r.rows * r.cols:
                r.status = "completed"
                r.finished_at = now_iso()
                r.score = memory_score(r.pairs, r.moves, memory_elapsed_seconds(r))
                r.settlement = "pending"
        return r

    saved = _mutate_run(games_store, run_id, mutator)
    if error_holder:
        raise error_holder[-1]
    if saved.settlement == "pending":
        settle(games_store, gamification_store, saved)
        saved = games_store.get_run(run_id)
    return saved, (dict(flip_result) if flip_result else None)


def abandon_run(games_store: Any, user_id: str, run_id: str) -> MemoryRun:
    def mutator(r: MemoryRun) -> Optional[MemoryRun]:
        if r.user_id != user_id:
            raise GameError("Bạn không sở hữu lượt chơi này.", 403)
        if r.status != "active":
            raise GameError("Lượt chơi đã kết thúc.", 409)
        r.status = "abandoned"
        r.finished_at = now_iso()
        return r

    return _mutate_run(games_store, run_id, mutator)


def memory_run_public_view(games_store: Any, run: MemoryRun) -> dict:
    result = None
    if run.settlement == "settled":
        row = games_store.get_result(result_id_for(run.run_id, run.user_id))
        if row is not None:
            result = row.to_dict()
    return memory_run_view(run, result=result)


# =============================================================================
# Bang xep hang & lich su — §6 cua dac ta
# =============================================================================


def _caro_aggregate(results: List[GameResult]) -> Dict[str, dict]:
    by_user: Dict[str, List[GameResult]] = defaultdict(list)
    for r in results:
        by_user[r.user_id].append(r)
    agg: Dict[str, dict] = {}
    for uid, rows in by_user.items():
        rows.sort(key=lambda r: r.created_at)
        total = sum(r.points for r in rows)
        running = 0
        first_reached = rows[-1].created_at
        for r in rows:
            running += r.points
            if running == total:
                first_reached = r.created_at
                break
        agg[uid] = {
            "points": total,
            "wins": sum(1 for r in rows if r.outcome == "win"),
            "draws": sum(1 for r in rows if r.outcome == "draw"),
            "losses": sum(1 for r in rows if r.outcome == "loss"),
            "matches": len(rows),
            "first_reached": first_reached,
        }
    return agg


def _memory_aggregate(results: List[GameResult]) -> Dict[str, dict]:
    by_user: Dict[str, List[GameResult]] = defaultdict(list)
    for r in results:
        by_user[r.user_id].append(r)
    agg: Dict[str, dict] = {}
    for uid, rows in by_user.items():
        rows.sort(key=lambda r: r.created_at)
        best = max(r.points for r in rows)
        achieved_at = next(r.created_at for r in rows if r.points == best)
        agg[uid] = {"best_score": best, "runs": len(rows), "achieved_at": achieved_at}
    return agg


def leaderboard(games_store: Any, identity: Any, storage: Any = None, *,
                game: str, season: str, difficulty: str = "", limit: int,
                offset: int, viewer_id: str = "") -> dict:
    results = games_store.list_results_by_game_season(
        game, season, difficulty if game == "memory" else "")
    if game == "caro":
        agg = _caro_aggregate(results)
        order_key = (lambda kv: (-kv[1]["points"], -kv[1]["wins"], kv[1]["matches"],
                                 kv[1]["first_reached"], kv[0]))
    else:
        agg = _memory_aggregate(results)
        order_key = lambda kv: (-kv[1]["best_score"], kv[1]["achieved_at"], kv[0])

    ordered = sorted(agg.items(), key=order_key)
    total = len(ordered)
    page = ordered[offset:offset + max(0, limit)]
    ids = [uid for uid, _ in page]
    profiles = identity.profiles_by_ids(ids) if ids else {}

    def card(uid: str, stats: dict, rank: int) -> dict:
        p = profiles.get(uid)
        base = {
            "rank": rank, "user_id": uid,
            "display_name": (getattr(p, "display_name", "") or getattr(p, "username", ""))
            if p else "",
            "username": getattr(p, "username", "") if p else "",
            "avatar_url": _anh_url(storage, getattr(p, "avatar_key", "")) if p else None,
        }
        if game == "caro":
            base.update({k: stats[k] for k in ("points", "wins", "draws", "losses", "matches")})
        else:
            base.update({"best_score": stats["best_score"], "runs": stats["runs"]})
        return base

    items = [card(uid, stats, offset + i + 1) for i, (uid, stats) in enumerate(page)]

    viewer_entry = None
    if viewer_id and not any(it["user_id"] == viewer_id for it in items):
        for i, (uid, stats) in enumerate(ordered):
            if uid == viewer_id:
                viewer_profiles = identity.profiles_by_ids([viewer_id])
                p = viewer_profiles.get(viewer_id)
                base = {
                    "rank": i + 1, "user_id": uid,
                    "display_name": (getattr(p, "display_name", "") or getattr(p, "username", ""))
                    if p else "",
                    "username": getattr(p, "username", "") if p else "",
                    "avatar_url": _anh_url(storage, getattr(p, "avatar_key", "")) if p else None,
                }
                if game == "caro":
                    base.update({k: stats[k] for k in
                                ("points", "wins", "draws", "losses", "matches")})
                else:
                    base.update({"best_score": stats["best_score"], "runs": stats["runs"]})
                viewer_entry = base
                break

    return {
        "game": game, "season": season, "difficulty": difficulty or None,
        "items": items, "total": total, "limit": limit, "offset": offset,
        "viewer_entry": viewer_entry, "seasons": games_store.list_seasons(game),
    }


def history(games_store: Any, user_id: str, limit: int) -> List[dict]:
    rows = games_store.list_results_for_user(user_id, limit)
    out = []
    for r in rows:
        d = r.to_dict()
        state = "settled"
        try:
            if r.game == "caro":
                room_id = r.source_id.rsplit("-", 1)[0]
                state = games_store.get_room(room_id).settlement
            else:
                state = games_store.get_run(r.source_id).settlement
        except Exception:
            pass
        d["settlement_state"] = state
        out.append(d)
    return out

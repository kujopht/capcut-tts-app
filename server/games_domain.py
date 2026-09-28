"""
Mini-game (Caro/Gomoku, Memory Runes) — logic THUAN, khong I/O.

Cung triet ly voi `gamification_domain.py`: dataclass + ham thuan, khong
FastAPI, khong Appwrite, khong dong ho toan cuc (moi ham nhan `now`/`today`
qua tham so khi can). May chu la nguon SU THAT DUY NHAT cho board/turn/
legality/win/diem/XP — client chi gui hanh dong (index + so thu tu).

`server/games_service.py` la noi DUY NHAT ghi vao kho (`games_store.py` /
`appwrite_games_store.py`) — module nay khong biet kho nao dang chay.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from server.domain import now_iso
from server.gamification import XP_EVENTS


def parse_iso(value: str) -> datetime:
    """`datetime.fromisoformat` nhung LUON tra ve co timezone (UTC neu
    chuoi khong ghi timezone) — `now_iso()` luon co timezone, nhung gia tri
    cu/nhap tay co the thieu, va so sanh datetime aware/naive nem loi."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# =============================================================================
# Hang so phien ban luat — VERSIONED, doi luat la doi hang nay (khong sua ngam).
# =============================================================================

RULE_CARO = "caro-v1"
RULE_MEMORY = "memory-v1"

BOARD_SIZE = 15
BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
EMPTY_BOARD = "." * BOARD_CELLS

#: Bo ky tu ma code phong — bo cac ky tu de nham (0/O, 1/I/L).
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6

DISCONNECT_GRACE_SECONDS = 45
LOBBY_TTL_SECONDS = 1800
ABANDON_SECONDS = 1800
MEMORY_MAX_SECONDS = 900
MEMORY_MIN_FLIP_INTERVAL_MS = 120

MAX_REWARDED_PER_PAIR_PER_DAY = 3
DAILY_GAME_XP_CAP = 30
MAX_REWARDED_RUNS_PER_DAY = 5

#: (rows, cols, pairs) theo do kho — 12 ky hieu rune, client tu anh xa
#: sang glyph/nhan tieng Viet, may chu chi gui KHOA.
MEMORY_DIFFICULTIES: Dict[str, Tuple[int, int, int]] = {
    "easy": (3, 4, 6),
    "normal": (4, 4, 8),
    "hard": (4, 6, 12),
}
MEMORY_SYMBOLS: Tuple[str, ...] = (
    "ignis", "aqua", "terra", "ventus", "lux", "umbra", "flora", "ferrum",
    "astra", "glacies", "fulmen", "vita",
)

GAME_MATCH_COMPLETED = "game_match_completed"
GAME_MATCH_WON = "game_match_won"
GAME_RUN_COMPLETED = "game_run_completed"


# =============================================================================
# Caro / Gomoku
# =============================================================================


@dataclass
class Room:
    room_id: str
    code: str
    game: str = "caro"
    rule_version: str = RULE_CARO
    host_id: str = ""
    seat_x: str = ""
    seat_o: str = ""
    ready_x: bool = False
    ready_o: bool = False
    status: str = "lobby"  # lobby | playing | finished | closed
    match_no: int = 1
    board: str = EMPTY_BOARD
    moves: List[List[int]] = field(default_factory=list)  # [index, seat]
    turn: str = "x"
    winner: str = ""  # x | o | draw | ""
    win_line: List[int] = field(default_factory=list)
    end_reason: str = ""  # five | draw | resign | timeout | abandon | ""
    last_seen_x: str = ""
    last_seen_o: str = ""
    rematch_x: bool = False
    rematch_o: bool = False
    settlement: str = "none"  # none | pending | settled
    started_at: str = ""
    finished_at: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    version: int = 1

    @property
    def match_id(self) -> str:
        return f"{self.room_id}-{self.match_no}"

    def seat_of(self, user_id: str) -> Optional[str]:
        if user_id and self.seat_x == user_id:
            return "x"
        if user_id and self.seat_o == user_id:
            return "o"
        return None

    def user_of(self, seat: str) -> str:
        return self.seat_x if seat == "x" else self.seat_o

    def opponent_seat(self, seat: str) -> str:
        return "o" if seat == "x" else "x"


def new_room(room_id: str, code: str, host_id: str) -> Room:
    now = now_iso()
    return Room(room_id=room_id, code=code, host_id=host_id, seat_x=host_id,
                created_at=now, updated_at=now)


def generate_room_code(rng: Optional[Any] = None) -> str:
    """Ma phong 6 ky tu — MAY CHU sinh, `rng` la `random.Random`/`secrets.
    SystemRandom` DUOC TRUYEN VAO de test tat dinh duoc; mac dinh dung
    `secrets.SystemRandom()` (khong doan truoc duoc trong production)."""
    r = rng if rng is not None else secrets.SystemRandom()
    return "".join(r.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


def new_room_id(rng: Optional[Any] = None) -> str:
    token = (rng.token_hex(8) if hasattr(rng, "token_hex")
             else secrets.token_hex(8))
    return f"rm_{token}"


def _rc(index: int) -> Tuple[int, int]:
    return divmod(index, BOARD_SIZE)


def _idx(r: int, c: int) -> int:
    return r * BOARD_SIZE + c


def in_range(index: int) -> bool:
    return 0 <= index < BOARD_CELLS


def check_win(board: str, index: int, seat: str) -> Optional[List[int]]:
    """Duong thang (>=5, KHONG gioi han renju — overline van thang) di qua
    `index` cho `seat` vua di. Tra ve danh sach chi so THEO THU TU tren
    duong thang, hoac `None` neu chua thang."""
    r0, c0 = _rc(index)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        backward: List[int] = []
        r, c = r0 - dr, c0 - dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[_idx(r, c)] == seat:
            backward.append(_idx(r, c))
            r -= dr
            c -= dc
        backward.reverse()
        forward: List[int] = []
        r, c = r0 + dr, c0 + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[_idx(r, c)] == seat:
            forward.append(_idx(r, c))
            r += dr
            c += dc
        line = backward + [index] + forward
        if len(line) >= 5:
            return line
    return None


def is_board_full(board: str) -> bool:
    return "." not in board


def apply_move(board: str, index: int, seat: str) -> str:
    return board[:index] + seat + board[index + 1:]


def season_key(iso_ts: str) -> str:
    """`YYYY-MM` UTC tu mot moc ISO — dung lam khoa mua giai."""
    # `now_iso()` luon la UTC (`domain.now_iso`), nen 10 ky tu dau (`YYYY-MM-DD`)
    # da du de cat ra `YYYY-MM`.
    return (iso_ts or now_iso())[:7]


# =============================================================================
# Memory Runes
# =============================================================================


@dataclass
class MemoryRun:
    run_id: str
    user_id: str
    difficulty: str
    rows: int
    cols: int
    layout: List[str] = field(default_factory=list)  # server-only
    matched: List[int] = field(default_factory=list)
    open_index: int = -1
    flips: List[List[Any]] = field(default_factory=list)  # [index, server_ms]
    moves: int = 0
    status: str = "active"  # active | completed | expired | abandoned
    started_at: str = field(default_factory=now_iso)
    finished_at: str = ""
    score: int = 0
    season: str = ""
    rule_version: str = RULE_MEMORY
    settlement: str = "none"
    version: int = 1

    @property
    def pairs(self) -> int:
        return (self.rows * self.cols) // 2


def new_memory_run(run_id: str, user_id: str, difficulty: str,
                   rng: Optional[Any] = None) -> MemoryRun:
    if difficulty not in MEMORY_DIFFICULTIES:
        raise ValueError(f"Độ khó không xác định: {difficulty!r}.")
    rows, cols, pairs = MEMORY_DIFFICULTIES[difficulty]
    r = rng if rng is not None else secrets.SystemRandom()
    symbols = list(MEMORY_SYMBOLS[:pairs]) * 2
    r.shuffle(symbols)
    now = now_iso()
    return MemoryRun(
        run_id=run_id, user_id=user_id, difficulty=difficulty, rows=rows,
        cols=cols, layout=symbols, started_at=now, season=season_key(now))


def memory_elapsed_seconds(run: MemoryRun, now: Optional[str] = None) -> float:
    """`now` MAC DINH la `now_iso_us()` (MICRO GIAY), KHONG PHAI `now_iso()`
    (chi den GIAY) — kiem tra `MEMORY_MIN_FLIP_INTERVAL_MS=120` can do
    khoang cach THAT giua hai lan lat LIEN TIEP; do o do phan giai GIAY thi
    hai lan lat cach nhau 150ms van co the roi vao CUNG mot giay lam tron
    (delta do duoc = 0), kich hoat sai `429`."""
    from server.domain import now_iso_us

    end = run.finished_at or (now or now_iso_us())
    try:
        return max(0.0, (parse_iso(end) - parse_iso(run.started_at)).total_seconds())
    except Exception:
        return 0.0


def memory_score(pairs: int, moves: int, elapsed_seconds: float) -> int:
    return max(0, pairs * 100 - max(0, moves - pairs) * 15 - int(elapsed_seconds))


# =============================================================================
# Ket qua & thuong (GameResult) — mot hang cho MOI (match_id|run_id, user_id)
# =============================================================================


@dataclass
class GameResult:
    result_id: str
    game: str
    season: str
    user_id: str
    opponent_id: str  # rong cho memory
    outcome: str  # win | loss | draw | completed
    points: int
    difficulty: str  # rong cho caro
    xp_awarded: int
    xp_entries: List[Dict[str, Any]] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    validated: bool = False
    rule_version: str = ""
    source_id: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id, "game": self.game, "season": self.season,
            "user_id": self.user_id, "opponent_id": self.opponent_id or None,
            "outcome": self.outcome, "points": self.points,
            "difficulty": self.difficulty or None, "xp_awarded": self.xp_awarded,
            "xp_entries": list(self.xp_entries), "reasons": list(self.reasons),
            "validated": self.validated, "rule_version": self.rule_version,
            "created_at": self.created_at,
        }


def result_id_for(source_id: str, user_id: str) -> str:
    return f"{source_id}|{user_id}"


# =============================================================================
# Chinh sach thuong — HAM THUAN, khong I/O. `games_service.py` truy van kho
# de lay `pair_count_today`/`xp_used_today`/`runs_count_today` roi goi vao day.
# =============================================================================


def decide_caro_rewards(room: Room, *, pair_count_today: int,
                        xp_used_today: Dict[str, int]) -> Dict[str, dict]:
    """Quyet dinh thuong cho TUNG user_id ngoi trong `room` (da ket thuc).
    Rong = khong co gi de dinh (thieu mot trong hai ghe, hoac bo cuoc —
    "khong co hang nao" la lua chon CHINH SACH cho `end_reason == 'abandon'`,
    xem SP_C_BACKEND_SPEC.md §4)."""
    seats = {"x": room.seat_x, "o": room.seat_o}
    users = [u for u in seats.values() if u]
    if len(set(users)) != 2:
        return {}
    if room.end_reason == "abandon":
        return {}

    validated = room.end_reason in ("five", "draw") or len(room.moves) >= 10
    decisions: Dict[str, dict] = {}
    for seat, user_id in seats.items():
        if room.winner == "draw":
            outcome = "draw"
        elif room.winner == seat:
            outcome = "win"
        else:
            outcome = "loss"

        if not validated:
            decisions[user_id] = {
                "outcome": outcome, "points": 0, "xp_events": [],
                "reasons": ["Ván quá ngắn — không tính điểm."], "validated": False,
            }
            continue

        points = {"win": 3, "draw": 1, "loss": 0}[outcome]
        xp_events: List[Tuple[str, int]] = [
            (GAME_MATCH_COMPLETED, XP_EVENTS[GAME_MATCH_COMPLETED])]
        if outcome == "win":
            xp_events.append((GAME_MATCH_WON, XP_EVENTS[GAME_MATCH_WON]))
        reasons: List[str] = []
        pair_capped = pair_count_today >= MAX_REWARDED_PER_PAIR_PER_DAY

        if pair_capped:
            # KHONG chi bo XP — `validated=False` la BAT BUOC: mot tran bi
            # chan vi da du so ván voi doi thu nay hom nay khong duoc tinh
            # vao bang xep hang (diem/thang/tran), neu khong nguoi choi co
            # the "cay" thu hang bang cach dau lai cung mot doi thu vo han
            # lan (chi XP bi chan, diem mua giai van cong don duoc).
            xp_events = []
            points = 0
            reasons.append("Đã đủ số ván tính điểm với đối thủ này hôm nay.")
        else:
            used = xp_used_today.get(user_id, 0)
            kept: List[Tuple[str, int]] = []
            for event_type, xp in xp_events:
                if used + xp > DAILY_GAME_XP_CAP:
                    if "Đã đạt giới hạn XP trò chơi hôm nay." not in reasons:
                        reasons.append("Đã đạt giới hạn XP trò chơi hôm nay.")
                    continue
                used += xp
                kept.append((event_type, xp))
            xp_events = kept

        decisions[user_id] = {
            "outcome": outcome, "points": points, "xp_events": xp_events,
            "reasons": reasons, "validated": not pair_capped,
        }
    return decisions


def decide_memory_reward(run: MemoryRun, *, runs_count_today: int,
                         xp_used_today: int) -> dict:
    """Quyet dinh thuong cho MOT luot Memory Runes da hoan thanh."""
    elapsed = memory_elapsed_seconds(run)
    plausible = elapsed >= run.pairs * 1.2
    if not plausible:
        return {
            "outcome": "completed", "points": run.score, "xp_events": [],
            "reasons": ["Quá nhanh để xác thực — không tính XP."],
            "validated": False,
        }

    reasons: List[str] = []
    xp_events: List[Tuple[str, int]] = [
        (GAME_RUN_COMPLETED, XP_EVENTS[GAME_RUN_COMPLETED])]
    if runs_count_today >= MAX_REWARDED_RUNS_PER_DAY:
        xp_events = []
        reasons.append("Đã đạt giới hạn lượt chơi tính điểm hôm nay.")
    else:
        used = xp_used_today
        kept = []
        for event_type, xp in xp_events:
            if used + xp > DAILY_GAME_XP_CAP:
                reasons.append("Đã đạt giới hạn XP trò chơi hôm nay.")
                continue
            used += xp
            kept.append((event_type, xp))
        xp_events = kept

    return {
        "outcome": "completed", "points": run.score, "xp_events": xp_events,
        "reasons": reasons, "validated": True,
    }


# =============================================================================
# Serializer — hinh dang cong khai cho API (§6 cua dac ta)
# =============================================================================


def _player_card(user_id: str, profiles: Dict[str, Any]) -> Optional[dict]:
    if not user_id:
        return None
    p = profiles.get(user_id)
    if p is None:
        return {"user_id": user_id, "display_name": "", "username": "",
                "avatar_url": None}
    return {
        "user_id": user_id,
        "display_name": getattr(p, "display_name", "") or getattr(p, "username", ""),
        "username": getattr(p, "username", ""),
        "avatar_url": getattr(p, "avatar_url", None),
    }


def _seat_connected(last_seen: str, now: Optional[str] = None) -> bool:
    if not last_seen:
        return False
    try:
        delta = (parse_iso(now or now_iso()) - parse_iso(last_seen)).total_seconds()
    except Exception:
        return False
    return delta <= DISCONNECT_GRACE_SECONDS


def room_view(room: Room, viewer_id: str, profiles: Dict[str, Any], *,
             now: Optional[str] = None,
             rewards: Optional[Dict[str, dict]] = None) -> dict:
    you = room.seat_of(viewer_id)
    opponent_seat = room.opponent_seat(you) if you else None
    opponent_last_seen = (room.last_seen_o if opponent_seat == "o"
                          else room.last_seen_x if opponent_seat == "x" else "")
    # KHONG phu thuoc luot: `games_service.claim_timeout` cho nhan thang bat ke
    # ai dang toi luot — doi thu mat ket noi luc DEN LUOT MINH van la bo van.
    # Do bang QA that: cu `turn == opponent_seat` thi nguoi o lai thay "mat ket
    # noi" ma KHONG co nut nao de ket thuc van (API cho, giao dien giau).
    can_claim_timeout = bool(
        you and room.status == "playing"
        and opponent_last_seen
        and not _seat_connected(opponent_last_seen, now))
    out = {
        "room_id": room.room_id, "code": room.code, "game": room.game,
        "rule_version": room.rule_version, "match_id": room.match_id,
        "match_no": room.match_no, "status": room.status,
        "board": room.board, "moves": [list(m) for m in room.moves],
        "move_no": len(room.moves), "turn": room.turn, "winner": room.winner or None,
        "win_line": list(room.win_line), "end_reason": room.end_reason or None,
        "rematch_x": room.rematch_x, "rematch_o": room.rematch_o,
        "settlement": room.settlement, "started_at": room.started_at or None,
        "finished_at": room.finished_at or None, "created_at": room.created_at,
        "updated_at": room.updated_at, "version": room.version,
        "you": you, "ready_x": room.ready_x, "ready_o": room.ready_o,
        "players": {
            "x": _player_card(room.seat_x, profiles),
            "o": _player_card(room.seat_o, profiles),
        },
        "opponent_connected": (
            _seat_connected(opponent_last_seen, now) if opponent_seat else None),
        "can_claim_timeout": can_claim_timeout,
    }
    if rewards is not None:
        out["rewards"] = rewards
    return out


def memory_run_view(run: MemoryRun, *, result: Optional[dict] = None) -> dict:
    matched_pairs = []
    for i in run.matched:
        matched_pairs.append({"index": i, "key": run.layout[i]})
    open_card = None
    if run.open_index >= 0:
        open_card = {"index": run.open_index, "key": run.layout[run.open_index]}
    return {
        "run_id": run.run_id, "difficulty": run.difficulty, "rows": run.rows,
        "cols": run.cols, "pairs": run.pairs, "matched": matched_pairs,
        "open": open_card, "moves": run.moves, "seq": len(run.flips),
        "status": run.status, "started_at": run.started_at,
        "finished_at": run.finished_at or None,
        "elapsed_seconds": int(memory_elapsed_seconds(run)),
        "score": run.score, "settlement": run.settlement, "result": result,
    }

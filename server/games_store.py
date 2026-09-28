"""
Kho mini-game trong bo nho — Social & Play V1 Goi C.

Cung triet ly voi `gamification_store.py`: `MockGamesStore` la ban DAY DU
logic idempotent/CAS, dung cho test va cho `DATA_BACKEND != appwrite`. Ban
ben vung that (`AppwriteGamesStore`, `server/appwrite_games_store.py`) CUNG
giao dien nay — `games_service.py` khong biet dang chay tren kho nao.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence, Tuple

from server.adapters import NotFoundError
from server.games_domain import GameResult, MemoryRun, Room


class GamesConflict(Exception):
    """CAS that bai — hang da bi ghi boi mot request khac tu luc doc.
    Nguoi goi (`games_service.py`) doc lai, ap dung lai logic, thu lai (toi
    da 5 lan theo dac ta), roi moi tra 409 cho client."""


class MockGamesStore:
    mode = "mock"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rooms: Dict[str, Room] = {}
        self._runs: Dict[str, MemoryRun] = {}
        self._results: Dict[str, GameResult] = {}

    # ======================================================== phong (Caro)

    def create_room(self, room: Room) -> Room:
        with self._lock:
            self._rooms[room.room_id] = room
            return room

    def get_room(self, room_id: str) -> Room:
        with self._lock:
            room = self._rooms.get(room_id)
        if room is None:
            raise NotFoundError("Không tìm thấy phòng.")
        return room

    def get_room_by_code(self, code: str) -> Optional[Room]:
        """Phong MOI NHAT khop `code` — bao gom CA phong da dong (goi noi tu
        quyet dinh 404/409 theo `status`, xem `games_service.join_room`).
        Uniqueness ma phong CHI ap dung cho phong CHUA dong (xem
        `code_is_taken`), nen mot ma cu co the duoc tai su dung sau khi phong
        cu da dong — truong hop nay tra ve phong MOI (id lon hon / tao sau)."""
        with self._lock:
            ung_vien = [r for r in self._rooms.values() if r.code == code]
        if not ung_vien:
            return None
        return max(ung_vien, key=lambda r: r.created_at)

    def code_is_taken(self, code: str) -> bool:
        with self._lock:
            return any(r.code == code and r.status != "closed"
                      for r in self._rooms.values())

    def save_room(self, room: Room, expected_version: int) -> Room:
        """CAS: hang luu hien tai PHAI dang o `expected_version`, neu khong
        nem `GamesConflict`. `room.version` PHAI da la `expected_version + 1`
        (goi noi tu tang truoc khi goi ham nay, cung quy uoc voi
        `save_room` cua `AppwriteGamesStore`)."""
        with self._lock:
            current = self._rooms.get(room.room_id)
            if current is None:
                raise NotFoundError("Không tìm thấy phòng.")
            if current.version != expected_version:
                raise GamesConflict("Phòng vừa thay đổi, thử lại.")
            self._rooms[room.room_id] = room
            return room

    def touch_seat(self, room_id: str, seat: str, iso: str) -> None:
        """Cap nhat CHI `last_seen_*` — KHONG bump `version`, tranh CAS storm
        khi client poll trang thai phong lien tuc (xem dac ta §2 `touch`)."""
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return
            if seat == "x":
                room.last_seen_x = iso
            elif seat == "o":
                room.last_seen_o = iso

    def list_pending_rooms(self) -> List[Room]:
        """Phong da `finished` nhung `settlement == 'pending'` — dung cho
        `games_service.settle_pending` (recovery)."""
        with self._lock:
            return [r for r in self._rooms.values()
                    if r.status == "finished" and r.settlement == "pending"]

    def list_rooms(self) -> List[Room]:
        with self._lock:
            return list(self._rooms.values())

    # ======================================================== luot (Memory)

    def create_run(self, run: MemoryRun) -> MemoryRun:
        with self._lock:
            self._runs[run.run_id] = run
            return run

    def get_run(self, run_id: str) -> MemoryRun:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise NotFoundError("Không tìm thấy lượt chơi.")
        return run

    def save_run(self, run: MemoryRun, expected_version: int) -> MemoryRun:
        with self._lock:
            current = self._runs.get(run.run_id)
            if current is None:
                raise NotFoundError("Không tìm thấy lượt chơi.")
            if current.version != expected_version:
                raise GamesConflict("Lượt chơi vừa thay đổi, thử lại.")
            self._runs[run.run_id] = run
            return run

    def list_pending_runs(self) -> List[MemoryRun]:
        with self._lock:
            return [r for r in self._runs.values()
                    if r.status == "completed" and r.settlement == "pending"]

    def list_runs_for_user(self, user_id: str) -> List[MemoryRun]:
        with self._lock:
            return [r for r in self._runs.values() if r.user_id == user_id]

    # ======================================================== ket qua

    def create_result(self, result: GameResult) -> bool:
        """Tra `False` (khong ghi gi) neu `result_id` DA CO — quyet dinh
        thuong dong bang o LAN GHI DAU TIEN, khong bao gio tinh lai (xem
        dac ta §4 `settle`)."""
        with self._lock:
            if result.result_id in self._results:
                return False
            self._results[result.result_id] = result
            return True

    def get_result(self, result_id: str) -> Optional[GameResult]:
        with self._lock:
            return self._results.get(result_id)

    def list_results_for_source(self, source_id: str) -> List[GameResult]:
        with self._lock:
            return [r for r in self._results.values() if r.source_id == source_id]

    def list_results_for_user(self, user_id: str, limit: int) -> List[GameResult]:
        with self._lock:
            ds = [r for r in self._results.values() if r.user_id == user_id]
        ds.sort(key=lambda r: r.created_at, reverse=True)
        return ds[:max(0, limit)]

    def list_results_for_pair_since(self, user_a: str, user_b: str,
                                    since_iso: str) -> List[GameResult]:
        """Ket qua caro DA duoc THUONG (validated) giua HAI nguoi nay, tu
        `since_iso` — dung tinh tran `MAX_REWARDED_PER_PAIR_PER_DAY`. Chi
        dem tu PHIA `user_a` (moi tran co hai hang, mot cho moi nguoi — dem
        mot phia la du, tranh dem gap doi)."""
        with self._lock:
            return [r for r in self._results.values()
                    if r.game == "caro" and r.user_id == user_a
                    and r.opponent_id == user_b and r.created_at >= since_iso
                    and r.validated]

    def list_results_for_user_since(self, user_id: str, game: str,
                                    since_iso: str) -> List[GameResult]:
        with self._lock:
            return [r for r in self._results.values()
                    if r.game == game and r.user_id == user_id
                    and r.created_at >= since_iso and r.validated]

    def list_seasons(self, game: str) -> List[str]:
        """Danh sach `season` (YYYY-MM) DA TUNG co ket qua hop le cho `game`
        nay — quet toan bo `_results` (V1: quy mo nho, chua can bang tong
        hop rieng, xem dac ta §7). Sap giam dan (mua gan nhat truoc)."""
        with self._lock:
            mua = {r.season for r in self._results.values()
                  if r.game == game and r.validated}
        return sorted(mua, reverse=True)

    def list_results_by_game_season(
            self, game: str, season: str,
            difficulty: str = "") -> List[GameResult]:
        """TOAN BO ket qua HOP LE (`validated`) cua `game`+`season` (+
        `difficulty` cho memory) — nguon DUY NHAT cho bang xep hang
        (`games_service.leaderboard`), tinh tai cho tu `game_results`
        (khong co bang tong hop rieng, dung dac ta §7)."""
        with self._lock:
            return [r for r in self._results.values()
                    if r.game == game and r.season == season and r.validated
                    and (not difficulty or r.difficulty == difficulty)]


def build_games_store(settings):
    """Chon kho games theo `DATA_BACKEND` — cung mau voi
    `build_gamification_store`."""
    if getattr(settings, "data_backend", "mock") == "appwrite":
        from server.appwrite_games_store import AppwriteGamesStore

        return AppwriteGamesStore(settings.appwrite)
    return MockGamesStore()

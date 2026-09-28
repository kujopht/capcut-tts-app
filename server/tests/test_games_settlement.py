"""
Settlement exactly-once/recoverable — Social & Play V1 Goi C, §4/§5.

Cac test o day khoa lai BA loi that da tim thay o vong review dau (xem
`docs/migrations/SOCIAL_PLAY_V1_GAMES_SCHEMA.md` muc "Loi da sua o vong
review"):

  1. Quyet dinh thuong phai DONG BANG o lan luu `GameResult` DAU TIEN — cong
     XP la mot buoc SAU, doc tu CHINH hang da luu, khong bao gio tinh lai.
  2. `leave()` giua tran KHONG duoc vacate ghe truoc khi settlement chay —
     lam vay se khien mot tran DA HOP LE (>=10 nuoc) mat thuong ca hai ben.
  3. Tran bi chan vi qua so ván/ngay voi CUNG doi thu phai la
     `validated=False` — neu khong no van "cay" duoc bang xep hang.
"""

import threading
import unittest

from server import games_service as gs
from server.gamification import id_xp_entry
from server.gamification_store import MockGamificationStore
from server.games_domain import MAX_REWARDED_PER_PAIR_PER_DAY, RULE_CARO
from server.games_store import MockGamesStore


class _FlakyGamificationStore(MockGamificationStore):
    """`MockGamificationStore` nhung `award_xp_atomic` NEM mot lan cho MOI
    `entry_id` trong `fail_once`, mo phong "crash giua chung" — lan goi thu
    HAI voi cung entry_id se thanh cong binh thuong (crash da qua, ha tang
    van con nguyen — cung gia dinh voi mot tien trinh restart)."""

    def __init__(self, fail_once):
        super().__init__()
        self._fail_once = set(fail_once)

    def award_xp_atomic(self, entry):
        if entry.entry_id in self._fail_once:
            self._fail_once.discard(entry.entry_id)
            raise RuntimeError("crash gia lap")
        return super().award_xp_atomic(entry)


def _win_x_over_o(games, gami, room):
    """usr_x thang hang ngang 5 o (>=10 nuoc, HOP LE)."""
    for i in range(4):
        gs.play_move(games, gami, "usr_x", room.code, i, 2 * i)
        gs.play_move(games, gami, "usr_o", room.code, 15 + i, 2 * i + 1)
    gs.play_move(games, gami, "usr_x", room.code, 4, 8)


class CrashRecoveryTest(unittest.TestCase):
    def test_crash_after_create_result_before_any_award_recovers_exactly_once(self):
        games = MockGamesStore()
        room0 = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room0.code)
        source_id_rule = f"{room0.room_id}-1|{RULE_CARO}"
        fail_id = id_xp_entry("usr_x", "game_match_completed", source_id_rule)
        gami = _FlakyGamificationStore(fail_once=[fail_id])

        gs.set_ready(games, "usr_x", room0.code, True)
        gs.set_ready(games, "usr_o", room0.code, True)
        with self.assertRaises(RuntimeError):
            _win_x_over_o(games, gami, room0)

        room = games.get_room(room0.room_id)
        self.assertEqual(room.settlement, "pending")

        recovered = gs.settle_pending(games, gami)
        self.assertEqual(recovered, 1)
        self.assertEqual(gami.get_progress("usr_x").xp, 5)
        self.assertEqual(gami.get_progress("usr_o").xp, 2)
        results = {r.user_id: r for r in games.list_results_for_source(f"{room0.room_id}-1")}
        self.assertEqual(results["usr_x"].xp_awarded, 5)
        self.assertEqual(results["usr_o"].xp_awarded, 2)
        # Goi lai lan nua khong duoc cong them.
        gs.settle_pending(games, gami)
        self.assertEqual(gami.get_progress("usr_x").xp, 5)

    def test_crash_after_first_of_two_awards_retries_only_missing_one(self):
        games = MockGamesStore()
        room0 = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room0.code)
        source_id_rule = f"{room0.room_id}-1|{RULE_CARO}"
        # `game_match_completed` cua usr_x THANH CONG, nhung `game_match_won`
        # (entry thu HAI cua usr_x) THAT BAI — mo phong crash GIUA hai lan
        # cong XP cua CUNG mot nguoi.
        fail_id = id_xp_entry("usr_x", "game_match_won", source_id_rule)
        gami = _FlakyGamificationStore(fail_once=[fail_id])

        gs.set_ready(games, "usr_x", room0.code, True)
        gs.set_ready(games, "usr_o", room0.code, True)
        with self.assertRaises(RuntimeError):
            _win_x_over_o(games, gami, room0)

        # Da cong duoc 2 XP (game_match_completed) truoc khi crash.
        self.assertEqual(gami.get_progress("usr_x").xp, 2)

        recovered = gs.settle_pending(games, gami)
        self.assertEqual(recovered, 1)
        # Sau phuc hoi: DUNG 5 (2 + 3), khong phai 7 (khong cong lai entry
        # da thanh cong truoc do).
        self.assertEqual(gami.get_progress("usr_x").xp, 5)
        results = {r.user_id: r for r in games.list_results_for_source(f"{room0.room_id}-1")}
        self.assertEqual(results["usr_x"].xp_awarded, 5)

    def test_concurrent_settle_same_match_awards_exactly_once(self):
        games = MockGamesStore()
        gami = MockGamificationStore()
        room0 = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room0.code)
        gs.set_ready(games, "usr_x", room0.code, True)
        gs.set_ready(games, "usr_o", room0.code, True)
        for i in range(4):
            gs.play_move(games, gami, "usr_x", room0.code, i, 2 * i)
            gs.play_move(games, gami, "usr_o", room0.code, 15 + i, 2 * i + 1)
        gs.play_move(games, gami, "usr_x", room0.code, 4, 8)
        # Tran DA duoc settle tu dong ngay khi vua thang (moi hanh dong ket
        # thuc deu goi settle) — dat lai 'pending' de mo phong HAI worker
        # cung phat hien mot tran cho settle mot luc (`settle_pending`
        # song song, hoac hai request GET cung luc).
        room = games.get_room(room0.room_id)
        room.settlement = "pending"

        errors = []

        def worker():
            try:
                gs.settle(games, gami, games.get_room(room0.room_id))
            except Exception as exc:  # pragma: no cover - chi de bat neu co
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(gami.get_progress("usr_x").xp, 5)
        self.assertEqual(gami.get_progress("usr_o").xp, 2)
        self.assertEqual(len(games.list_results_for_source(f"{room0.room_id}-1")), 2)
        self.assertEqual(len(gami.list_xp_events("usr_x")), 2)
        self.assertEqual(len(gami.list_xp_events("usr_o")), 1)


class LeaveDuringValidatedMatchTest(unittest.TestCase):
    def test_leave_after_ten_moves_still_rewards_both(self):
        games = MockGamesStore()
        gami = MockGamificationStore()
        room = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room.code)
        gs.set_ready(games, "usr_x", room.code, True)
        gs.set_ready(games, "usr_o", room.code, True)
        # 10 nuoc KHONG tao ra 5-lien-tiep nao: moi ben danh CACH O mot
        # (buoc nhay 2) tren hai hang khac nhau — khong co 5 o LIEN TIEP nao
        # cung ky tu tren bat ky huong nao.
        move_no = 0
        for i in range(5):
            gs.play_move(games, gami, "usr_x", room.code, 2 * i, move_no)
            move_no += 1
            gs.play_move(games, gami, "usr_o", room.code, 150 + 2 * i, move_no)
            move_no += 1

        room = games.get_room(room.room_id)
        self.assertEqual(room.status, "playing")
        room = gs.leave(games, gami, "usr_x", room.code)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.end_reason, "resign")
        self.assertEqual(room.winner, "o")
        self.assertEqual(room.settlement, "settled")
        # Nguoi roi (usr_x, thua) van duoc tinh `game_match_completed`;
        # nguoi con lai (usr_o, thang) duoc CA HAI + 3 diem mua giai.
        self.assertEqual(gami.get_progress("usr_x").xp, 2)
        self.assertEqual(gami.get_progress("usr_o").xp, 5)
        results = {r.user_id: r for r in games.list_results_for_source(room.match_id)}
        self.assertTrue(results["usr_x"].validated)
        self.assertTrue(results["usr_o"].validated)
        self.assertEqual(results["usr_o"].points, 3)
        self.assertEqual(results["usr_x"].points, 0)
        # Ghe cua nguoi roi phai TRONG sau cung; nguoi con lai VAN con ngoi
        # (chua tu roi).
        self.assertEqual(room.seat_x, "")
        self.assertEqual(room.seat_o, "usr_o")


class PairCapValidationTest(unittest.TestCase):
    def test_matches_beyond_pair_cap_are_not_validated(self):
        games = MockGamesStore()
        gami = MockGamificationStore()
        for match_no in range(1, 6):
            room = gs.create_room(games, "usr_x")
            gs.join_room(games, "usr_o", room.code)
            gs.set_ready(games, "usr_x", room.code, True)
            gs.set_ready(games, "usr_o", room.code, True)
            for i in range(4):
                gs.play_move(games, gami, "usr_x", room.code, i, 2 * i)
                gs.play_move(games, gami, "usr_o", room.code, 15 + i, 2 * i + 1)
            room = gs.play_move(games, gami, "usr_x", room.code, 4, 8)
            row = games.get_result(f"{room.match_id}|usr_x")
            if match_no <= MAX_REWARDED_PER_PAIR_PER_DAY:
                self.assertTrue(row.validated, f"match {match_no} phai validated")
            else:
                self.assertFalse(row.validated, f"match {match_no} khong duoc validated")

        season = room.finished_at[:7]
        board = gs.leaderboard(games, _FakeIdentity(), None, game="caro",
                              season=season, limit=20, offset=0)
        winner_row = next(it for it in board["items"] if it["user_id"] == "usr_x")
        # Chi 3 tran HOP LE duoc tinh — 2 tran vuot tran KHONG lam tang
        # `matches`/`wins`/`points`.
        self.assertEqual(winner_row["matches"], MAX_REWARDED_PER_PAIR_PER_DAY)
        self.assertEqual(winner_row["wins"], MAX_REWARDED_PER_PAIR_PER_DAY)
        self.assertEqual(winner_row["points"], MAX_REWARDED_PER_PAIR_PER_DAY * 3)


class PairCapDoiGheTest(unittest.TestCase):
    """Phan bien review cheo (goi C): "tran cap chi dem mot chieu — doi ai cam X
    la ne duoc". Moi van ghi MOT hang ket qua cho MOI nguoi (user_id=A/opponent=B
    VA user_id=B/opponent=A), nen dem tu phia nguoi cam X nao cung thay du so van.
    Bai nay khoa lai bat bien do: 5 van, DOI nguoi cam X moi van."""

    def test_doi_nguoi_cam_x_moi_van_van_bi_tran_3(self):
        games = MockGamesStore()
        gami = MockGamificationStore()
        for match_no in range(1, 6):
            chu, khach = ("usr_a", "usr_b") if match_no % 2 else ("usr_b", "usr_a")
            room = gs.create_room(games, chu)
            gs.join_room(games, khach, room.code)
            gs.set_ready(games, chu, room.code, True)
            gs.set_ready(games, khach, room.code, True)
            for i in range(4):
                gs.play_move(games, gami, chu, room.code, i, 2 * i)
                gs.play_move(games, gami, khach, room.code, 15 + i, 2 * i + 1)
            room = gs.play_move(games, gami, chu, room.code, 4, 8)
            for u in ("usr_a", "usr_b"):
                row = games.get_result(f"{room.match_id}|{u}")
                self.assertEqual(row.validated, match_no <= MAX_REWARDED_PER_PAIR_PER_DAY,
                                 f"van {match_no} ({u}, chu phong {chu})")


class _CrashAfterFirstCreateResult(MockGamesStore):
    """`MockGamesStore` nhung `create_result` NEM ngay sau lan GHI THANH
    CONG dau tien — mo phong crash GIUA hai lan `create_result` cua HAI
    nguoi trong CUNG mot tran (usr_x da co hang, usr_o thi chua). Chi nem
    MOT LAN — lan goi lai (retry/`settle_pending`) di qua binh thuong."""

    def __init__(self):
        super().__init__()
        self._da_crash = False
        #: Chi crash khi `armed=True` — bat luc TEST muon (tran thu ba),
        #: KHONG phai ngay lan `create_result` dau tien tuyet doi (hai tran
        #: dau can thanh cong binh thuong de co lich su "2 tran hop le").
        self.armed = False

    def create_result(self, result):
        created = super().create_result(result)
        if created and self.armed and not self._da_crash:
            self._da_crash = True
            raise RuntimeError("crash gia lap giua hai create_result")
        return created


class PairCountExcludesOwnMatchTest(unittest.TestCase):
    def test_retry_after_partial_create_result_does_not_self_count(self):
        """Sau khi da choi DU 2 tran hop le voi cung doi thu (duoi tran =
        MAX_REWARDED_PER_PAIR_PER_DAY=3), tran thu BA bi "crash" giua hai
        lan `create_result` — retry (`settle_pending`) phai KHONG tu dem
        hang cua chinh tran thu ba (da luu cho usr_x) vao so ván-voi-doi-
        thu-hom-nay khi tinh quyet dinh cho usr_o, neu khong tran thu ba
        se bi tinh SAI la vuot tran (2 tran cu + 1 tran-tu-dem = 3 >= cap)
        trong khi thuc te no van con trong han muc."""
        games = _CrashAfterFirstCreateResult()
        gami = MockGamificationStore()

        for _ in range(2):
            room = gs.create_room(games, "usr_x")
            gs.join_room(games, "usr_o", room.code)
            gs.set_ready(games, "usr_x", room.code, True)
            gs.set_ready(games, "usr_o", room.code, True)
            for i in range(4):
                gs.play_move(games, gami, "usr_x", room.code, i, 2 * i)
                gs.play_move(games, gami, "usr_o", room.code, 15 + i, 2 * i + 1)
            gs.play_move(games, gami, "usr_x", room.code, 4, 8)

        room3 = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room3.code)
        gs.set_ready(games, "usr_x", room3.code, True)
        gs.set_ready(games, "usr_o", room3.code, True)
        for i in range(4):
            gs.play_move(games, gami, "usr_x", room3.code, i, 2 * i)
            gs.play_move(games, gami, "usr_o", room3.code, 15 + i, 2 * i + 1)
        games.armed = True
        with self.assertRaises(RuntimeError):
            gs.play_move(games, gami, "usr_x", room3.code, 4, 8)

        room3_after = games.get_room(room3.room_id)
        self.assertEqual(room3_after.settlement, "pending")

        recovered = gs.settle_pending(games, gami)
        self.assertEqual(recovered, 1)
        results = {r.user_id: r for r in
                  games.list_results_for_source(room3_after.match_id)}
        self.assertTrue(results["usr_x"].validated)
        self.assertTrue(results["usr_o"].validated)
        self.assertEqual(results["usr_o"].points, 0)  # usr_o thua tran nay
        self.assertGreater(results["usr_o"].xp_awarded, 0)


class _FakeIdentity:
    def profiles_by_ids(self, ids):
        return {}


if __name__ == "__main__":
    unittest.main()

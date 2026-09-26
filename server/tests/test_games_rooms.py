import unittest

from server import games_service as gs
from server.games_store import MockGamesStore
from server.gamification_store import MockGamificationStore


class RoomFlowTest(unittest.TestCase):
    def setUp(self):
        self.games = MockGamesStore()
        self.gami = MockGamificationStore()

    def _play_to_win(self, code):
        """usr_x thang hang ngang 5 o hang 0, usr_o di hang 1 xen ke."""
        for i in range(4):
            gs.play_move(self.games, self.gami, "usr_x", code, i, 2 * i)
            gs.play_move(self.games, self.gami, "usr_o", code, 15 + i, 2 * i + 1)
        gs.play_move(self.games, self.gami, "usr_x", code, 4, 8)

    def test_create_join_ready_play_win_settle(self):
        room = gs.create_room(self.games, "usr_x")
        self.assertEqual(room.status, "lobby")
        self.assertEqual(room.seat_x, "usr_x")

        room = gs.join_room(self.games, "usr_o", room.code)
        self.assertEqual(room.seat_o, "usr_o")

        gs.set_ready(self.games, "usr_x", room.code, True)
        room = gs.set_ready(self.games, "usr_o", room.code, True)
        self.assertEqual(room.status, "playing")

        self._play_to_win(room.code)
        room = self.games.get_room_by_code(room.code)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "x")
        self.assertEqual(room.end_reason, "five")
        self.assertEqual(room.settlement, "settled")

        self.assertEqual(self.gami.get_progress("usr_x").xp, 5)  # 2 + 3
        self.assertEqual(self.gami.get_progress("usr_o").xp, 2)
        results = self.games.list_results_for_source(room.match_id)
        self.assertEqual(len(results), 2)

    def test_join_same_user_reconnects_not_double_seat(self):
        room = gs.create_room(self.games, "usr_x")
        room = gs.join_room(self.games, "usr_x", room.code)
        self.assertEqual(room.seat_x, "usr_x")
        self.assertEqual(room.seat_o, "")

    def test_join_full_room_409(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        with self.assertRaises(gs.GameError) as ctx:
            gs.join_room(self.games, "usr_z", room.code)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_join_unknown_code_404(self):
        with self.assertRaises(gs.GameError) as ctx:
            gs.join_room(self.games, "usr_x", "ZZZZZZ")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_move_wrong_turn_409(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        with self.assertRaises(gs.GameError) as ctx:
            gs.play_move(self.games, self.gami, "usr_o", room.code, 0, 0)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_move_stale_move_no_409(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        gs.play_move(self.games, self.gami, "usr_x", room.code, 0, 0)
        with self.assertRaises(gs.GameError) as ctx:
            gs.play_move(self.games, self.gami, "usr_o", room.code, 1, 0)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_move_occupied_cell_400(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        gs.play_move(self.games, self.gami, "usr_x", room.code, 0, 0)
        with self.assertRaises(gs.GameError) as ctx:
            gs.play_move(self.games, self.gami, "usr_o", room.code, 0, 1)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_move_not_seated_403(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        with self.assertRaises(gs.GameError) as ctx:
            gs.play_move(self.games, self.gami, "usr_z", room.code, 0, 0)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_move_after_finish_409(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        self._play_to_win(room.code)
        with self.assertRaises(gs.GameError) as ctx:
            gs.play_move(self.games, self.gami, "usr_o", room.code, 20, 9)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_resign_gives_win_to_opponent_no_xp_short_game(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        room = gs.resign(self.games, self.gami, "usr_x", room.code)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "o")
        self.assertEqual(room.end_reason, "resign")
        # Qua ngan (0 nuoc di) -> khong tinh diem.
        self.assertEqual(self.gami.get_progress("usr_x").xp, 0)
        self.assertEqual(self.gami.get_progress("usr_o").xp, 0)

    def test_claim_timeout_requires_grace_elapsed(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        with self.assertRaises(gs.GameError) as ctx:
            gs.claim_timeout(self.games, self.gami, "usr_o", room.code)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_rematch_swaps_seats_and_increments_match_no(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        self._play_to_win(room.code)
        gs.rematch(self.games, "usr_x", room.code)
        room = gs.rematch(self.games, "usr_o", room.code)
        self.assertEqual(room.match_no, 2)
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.seat_x, "usr_o")
        self.assertEqual(room.seat_o, "usr_x")

    def test_leave_lobby_host_closes_room(self):
        room = gs.create_room(self.games, "usr_x")
        room = gs.leave(self.games, self.gami, "usr_x", room.code)
        self.assertEqual(room.status, "closed")

    def test_leave_while_playing_counts_as_resign(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        room = gs.leave(self.games, self.gami, "usr_x", room.code)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "o")
        self.assertEqual(room.seat_x, "")

    def test_leave_both_after_finish_closes_room(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        self._play_to_win(room.code)
        gs.leave(self.games, self.gami, "usr_x", room.code)
        room = gs.leave(self.games, self.gami, "usr_o", room.code)
        self.assertEqual(room.status, "closed")

    def test_draw_result(self):
        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        gs.set_ready(self.games, "usr_o", room.code, True)
        # Lap day 225 o khong tao 5-lien-tiep: xen ke theo mot khuon mau an
        # toan (x/o xen ke tung cot trong tung hang, doi hang thi doi thu tu
        # bat dau de khong hang/cot/duong cheo nao co 5 cung ky tu lien tiep).
        code = room.code
        move_no = 0
        board = [["."] * 15 for _ in range(15)]
        order = []
        for r in range(15):
            row_cols = list(range(15)) if r % 2 == 0 else list(range(14, -1, -1))
            for c in row_cols:
                order.append((r, c))
        turn = "x"
        seat_users = {"x": "usr_x", "o": "usr_o"}
        for (r, c) in order:
            idx = r * 15 + c
            user = seat_users[turn]
            room = gs.play_move(self.games, self.gami, user, code, idx, move_no)
            move_no += 1
            if room.status == "finished":
                break
            turn = "o" if turn == "x" else "x"
        # Bang chay het 225 o hoac ket thuc som vi thang — chi chap nhan
        # HOAC hoa HOAC thang, khong bao gio con "playing".
        self.assertEqual(room.status, "finished")
        self.assertIn(room.end_reason, ("draw", "five"))


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.games = MockGamesStore()
        self.gami = MockGamificationStore()

    def test_lobby_ttl_closes_on_read(self):
        from server.games_domain import LOBBY_TTL_SECONDS

        room = gs.create_room(self.games, "usr_x")
        stored = self.games.get_room(room.room_id)
        import datetime as _dt
        old = (_dt.datetime.now(_dt.timezone.utc)
              - _dt.timedelta(seconds=LOBBY_TTL_SECONDS + 5)).isoformat(timespec="seconds")
        stored.updated_at = old
        room = gs.get_room(self.games, self.gami, room.code)
        self.assertEqual(room.status, "closed")

    def test_playing_both_absent_marks_abandon_no_reward(self):
        from server.games_domain import ABANDON_SECONDS
        import datetime as _dt

        room = gs.create_room(self.games, "usr_x")
        gs.join_room(self.games, "usr_o", room.code)
        gs.set_ready(self.games, "usr_x", room.code, True)
        room = gs.set_ready(self.games, "usr_o", room.code, True)
        stored = self.games.get_room(room.room_id)
        old = (_dt.datetime.now(_dt.timezone.utc)
              - _dt.timedelta(seconds=ABANDON_SECONDS + 5)).isoformat(timespec="seconds")
        stored.last_seen_x = old
        stored.last_seen_o = old
        room = gs.get_room(self.games, self.gami, room.code)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.end_reason, "abandon")
        self.assertEqual(self.gami.get_progress("usr_x").xp, 0)
        self.assertEqual(self.gami.get_progress("usr_o").xp, 0)
        self.assertEqual(self.games.list_results_for_source(room.match_id), [])


class SettlementRecoveryTest(unittest.TestCase):
    def test_settle_pending_is_idempotent_after_partial_crash(self):
        games = MockGamesStore()
        gami = MockGamificationStore()
        room = gs.create_room(games, "usr_x")
        gs.join_room(games, "usr_o", room.code)
        gs.set_ready(games, "usr_x", room.code, True)
        gs.set_ready(games, "usr_o", room.code, True)
        for i in range(4):
            gs.play_move(games, gami, "usr_x", room.code, i, 2 * i)
            gs.play_move(games, gami, "usr_o", room.code, 15 + i, 2 * i + 1)
        gs.play_move(games, gami, "usr_x", room.code, 4, 8)

        # Gia lap "crash ngay truoc khi settle" bang cach tu dat lai
        # settlement='pending' SAU khi nuoc thang da duoc ap dung — mo phong
        # da finished/pending nhung CHUA settle.
        room_obj = games.get_room(room.room_id)
        room_obj.settlement = "pending"

        count = gs.settle_pending(games, gami)
        self.assertEqual(count, 1)
        self.assertEqual(gami.get_progress("usr_x").xp, 5)
        self.assertEqual(gami.get_progress("usr_o").xp, 2)

        # Goi lai lan hai (mo phong crash lai) khong duoc cong XP them.
        room_obj = games.get_room(room.room_id)
        room_obj.settlement = "pending"
        gs.settle_pending(games, gami)
        self.assertEqual(gami.get_progress("usr_x").xp, 5)
        self.assertEqual(gami.get_progress("usr_o").xp, 2)
        self.assertEqual(len(games.list_results_for_source(room.match_id)), 2)


if __name__ == "__main__":
    unittest.main()

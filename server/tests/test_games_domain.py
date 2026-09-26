import random
import unittest

from server import games_domain as gd


class CaroWinTest(unittest.TestCase):
    def test_horizontal_five(self):
        board = list(gd.EMPTY_BOARD)
        for c in range(5):
            board[gd._idx(0, c)] = "x"
        board = "".join(board)
        line = gd.check_win(board, gd._idx(0, 2), "x")
        self.assertIsNotNone(line)
        self.assertEqual(len(line), 5)
        self.assertEqual(sorted(line), [gd._idx(0, c) for c in range(5)])

    def test_overline_wins(self):
        board = list(gd.EMPTY_BOARD)
        for c in range(6):
            board[gd._idx(1, c)] = "o"
        board = "".join(board)
        line = gd.check_win(board, gd._idx(1, 3), "o")
        self.assertIsNotNone(line)
        self.assertEqual(len(line), 6)

    def test_diagonal_five(self):
        board = list(gd.EMPTY_BOARD)
        for i in range(5):
            board[gd._idx(i, i)] = "x"
        board = "".join(board)
        line = gd.check_win(board, gd._idx(2, 2), "x")
        self.assertIsNotNone(line)

    def test_anti_diagonal_five(self):
        board = list(gd.EMPTY_BOARD)
        for i in range(5):
            board[gd._idx(i, 4 - i)] = "o"
        board = "".join(board)
        line = gd.check_win(board, gd._idx(2, 2), "o")
        self.assertIsNotNone(line)

    def test_four_in_a_row_no_win(self):
        board = list(gd.EMPTY_BOARD)
        for c in range(4):
            board[gd._idx(0, c)] = "x"
        board = "".join(board)
        self.assertIsNone(gd.check_win(board, gd._idx(0, 1), "x"))

    def test_draw_detection(self):
        self.assertFalse(gd.is_board_full(gd.EMPTY_BOARD))
        full = "x" * gd.BOARD_CELLS
        self.assertTrue(gd.is_board_full(full))


class RoomCodeTest(unittest.TestCase):
    def test_deterministic_with_seeded_rng(self):
        rng = random.Random(42)
        code1 = gd.generate_room_code(rng)
        rng2 = random.Random(42)
        code2 = gd.generate_room_code(rng2)
        self.assertEqual(code1, code2)
        self.assertEqual(len(code1), gd.ROOM_CODE_LENGTH)
        for ch in code1:
            self.assertIn(ch, gd.ROOM_CODE_ALPHABET)


class MemoryRunTest(unittest.TestCase):
    def test_new_run_layout_shape(self):
        rng = random.Random(1)
        run = gd.new_memory_run("mr_test", "usr_1", "easy", rng)
        rows, cols, pairs = gd.MEMORY_DIFFICULTIES["easy"]
        self.assertEqual(run.rows, rows)
        self.assertEqual(run.cols, cols)
        self.assertEqual(len(run.layout), rows * cols)
        self.assertEqual(run.pairs, pairs)
        # Moi ky hieu xuat hien dung hai lan.
        from collections import Counter
        counts = Counter(run.layout)
        self.assertTrue(all(v == 2 for v in counts.values()))

    def test_score_formula(self):
        self.assertEqual(gd.memory_score(pairs=6, moves=6, elapsed_seconds=10), 590)
        self.assertEqual(gd.memory_score(pairs=6, moves=20, elapsed_seconds=1000), 0)

    def test_invalid_difficulty_raises(self):
        with self.assertRaises(ValueError):
            gd.new_memory_run("mr_x", "usr_1", "impossible")


class CaroRewardPolicyTest(unittest.TestCase):
    def _finished_room(self, winner="x", end_reason="five", moves_count=10):
        room = gd.new_room("rm_1", "AAAAAA", "usr_x")
        room.seat_o = "usr_o"
        room.status = "finished"
        room.winner = winner
        room.end_reason = end_reason
        room.moves = [[i, "x" if i % 2 == 0 else "o"] for i in range(moves_count)]
        return room

    def test_validated_win_loss_split(self):
        room = self._finished_room()
        decisions = gd.decide_caro_rewards(room, pair_count_today=0, xp_used_today={})
        self.assertTrue(decisions["usr_x"]["validated"])
        self.assertEqual(decisions["usr_x"]["outcome"], "win")
        self.assertEqual(decisions["usr_x"]["points"], 3)
        self.assertEqual(decisions["usr_o"]["outcome"], "loss")
        self.assertEqual(decisions["usr_o"]["points"], 0)
        xp_types_winner = [e[0] for e in decisions["usr_x"]["xp_events"]]
        self.assertIn("game_match_completed", xp_types_winner)
        self.assertIn("game_match_won", xp_types_winner)
        xp_types_loser = [e[0] for e in decisions["usr_o"]["xp_events"]]
        self.assertEqual(xp_types_loser, ["game_match_completed"])

    def test_draw(self):
        room = self._finished_room(winner="draw", end_reason="draw")
        decisions = gd.decide_caro_rewards(room, pair_count_today=0, xp_used_today={})
        self.assertEqual(decisions["usr_x"]["outcome"], "draw")
        self.assertEqual(decisions["usr_x"]["points"], 1)

    def test_short_resign_not_validated(self):
        room = self._finished_room(end_reason="resign", moves_count=2)
        decisions = gd.decide_caro_rewards(room, pair_count_today=0, xp_used_today={})
        self.assertFalse(decisions["usr_x"]["validated"])
        self.assertEqual(decisions["usr_x"]["xp_events"], [])
        self.assertIn("Ván quá ngắn", decisions["usr_x"]["reasons"][0])

    def test_abandon_has_no_rows(self):
        room = self._finished_room(end_reason="abandon", winner="")
        decisions = gd.decide_caro_rewards(room, pair_count_today=0, xp_used_today={})
        self.assertEqual(decisions, {})

    def test_missing_second_seat_has_no_rows(self):
        room = gd.new_room("rm_2", "BBBBBB", "usr_x")
        room.status = "finished"
        room.winner = "x"
        room.end_reason = "five"
        decisions = gd.decide_caro_rewards(room, pair_count_today=0, xp_used_today={})
        self.assertEqual(decisions, {})

    def test_pair_cap_zeroes_reward(self):
        room = self._finished_room()
        decisions = gd.decide_caro_rewards(
            room, pair_count_today=gd.MAX_REWARDED_PER_PAIR_PER_DAY,
            xp_used_today={})
        self.assertEqual(decisions["usr_x"]["points"], 0)
        self.assertEqual(decisions["usr_x"]["xp_events"], [])
        self.assertIn("đối thủ", decisions["usr_x"]["reasons"][0])
        # Tran bi chan vi da du so ván voi doi thu nay KHONG duoc tinh vao
        # bang xep hang (validated=False) — chi tran bi CHAN XP hang ngay
        # (`test_daily_xp_cap_drops_entries`) moi giu `validated=True`.
        self.assertFalse(decisions["usr_x"]["validated"])

    def test_daily_xp_cap_drops_entries(self):
        room = self._finished_room()
        decisions = gd.decide_caro_rewards(
            room, pair_count_today=0,
            xp_used_today={"usr_x": gd.DAILY_GAME_XP_CAP})
        self.assertEqual(decisions["usr_x"]["xp_events"], [])
        self.assertTrue(any("giới hạn XP" in r for r in decisions["usr_x"]["reasons"]))
        # Nguoi con lai khong bi anh huong.
        self.assertTrue(len(decisions["usr_o"]["xp_events"]) >= 1)


class MemoryRewardPolicyTest(unittest.TestCase):
    def _completed_run(self, elapsed_seconds=100):
        rng = random.Random(3)
        run = gd.new_memory_run("mr_1", "usr_1", "easy", rng)
        run.status = "completed"
        run.moves = run.pairs
        run.matched = list(range(run.rows * run.cols))
        run.started_at = "2026-01-01T00:00:00+00:00"
        run.finished_at = "2026-01-01T00:0" + (
            f"{int(elapsed_seconds // 60):01d}:{int(elapsed_seconds % 60):02d}+00:00")
        run.score = gd.memory_score(run.pairs, run.moves, elapsed_seconds)
        return run

    def test_plausible_completion_rewarded(self):
        run = self._completed_run(elapsed_seconds=30)
        decision = gd.decide_memory_reward(run, runs_count_today=0, xp_used_today=0)
        self.assertTrue(decision["validated"])
        self.assertEqual([e[0] for e in decision["xp_events"]], ["game_run_completed"])

    def test_too_fast_not_validated(self):
        run = self._completed_run(elapsed_seconds=1)
        decision = gd.decide_memory_reward(run, runs_count_today=0, xp_used_today=0)
        self.assertFalse(decision["validated"])
        self.assertEqual(decision["xp_events"], [])
        self.assertIn("Quá nhanh", decision["reasons"][0])

    def test_run_cap_drops_xp(self):
        run = self._completed_run(elapsed_seconds=30)
        decision = gd.decide_memory_reward(
            run, runs_count_today=gd.MAX_REWARDED_RUNS_PER_DAY, xp_used_today=0)
        self.assertEqual(decision["xp_events"], [])
        self.assertTrue(decision["validated"])


class SerializerTest(unittest.TestCase):
    def test_room_view_you_and_players(self):
        room = gd.new_room("rm_3", "CCCCCC", "usr_x")
        room.seat_o = "usr_o"
        view = gd.room_view(room, "usr_x", {})
        self.assertEqual(view["you"], "x")
        self.assertEqual(view["players"]["x"]["user_id"], "usr_x")
        self.assertEqual(view["players"]["o"]["user_id"], "usr_o")
        self.assertIsNone(view["winner"])

    def test_memory_run_view_hides_layout(self):
        rng = random.Random(7)
        run = gd.new_memory_run("mr_2", "usr_1", "normal", rng)
        run.matched = [0, 1]
        view = gd.memory_run_view(run)
        self.assertNotIn("layout", view)
        self.assertEqual(view["matched"][0]["index"], 0)
        self.assertEqual(view["matched"][0]["key"], run.layout[0])


if __name__ == "__main__":
    unittest.main()

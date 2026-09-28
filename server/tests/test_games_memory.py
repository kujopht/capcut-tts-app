import time
import unittest

from server import games_service as gs
from server.games_store import MockGamesStore
from server.gamification_store import MockGamificationStore

#: `MEMORY_MIN_FLIP_INTERVAL_MS` (120ms) do THEO DONG HO THAT giua hai lan
#: lat lien tiep — khong the "backdate" duoc nhu tong thoi gian luot choi
#: (do do la mot phep TRU giua hai moc, ca hai deu troi theo dong ho that
#: bat ke `started_at` bi lui bao xa). Test hoan thanh luot phai NGU THAT
#: giua cac lan lat de khong tu vap bay 429 cua chinh minh.
_FLIP_GAP = 0.15


class MemoryFlowTest(unittest.TestCase):
    def setUp(self):
        self.games = MockGamesStore()
        self.gami = MockGamificationStore()

    def _complete_run(self, difficulty="easy"):
        run = gs.start_run(self.games, "usr_1", difficulty)
        pairs = run.pairs
        layout = run.layout
        # Ghep tung cap lien tiep theo layout that (bo qua toc do — chi test
        # logic khop cap, khong test chinh sach thoi gian o day).
        seen: dict = {}
        seq = 0
        for idx, key in enumerate(layout):
            if key in seen:
                first_idx = seen.pop(key)
                time.sleep(_FLIP_GAP)
                run, flip1 = gs.flip(self.games, self.gami, "usr_1", run.run_id,
                                     first_idx, seq)
                seq += 1
                time.sleep(_FLIP_GAP)
                run, flip2 = gs.flip(self.games, self.gami, "usr_1", run.run_id,
                                     idx, seq)
                seq += 1
            else:
                seen[key] = idx
        return run

    def test_start_run_hides_layout_in_view(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        view = gs.memory_run_public_view(self.games, run)
        self.assertNotIn("layout", view)
        self.assertEqual(view["status"], "active")
        self.assertEqual(view["pairs"], 6)

    def test_invalid_difficulty_400(self):
        with self.assertRaises(gs.GameError) as ctx:
            gs.start_run(self.games, "usr_1", "nightmare")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_owner_only_flip(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        with self.assertRaises(gs.GameError) as ctx:
            gs.flip(self.games, self.gami, "usr_2", run.run_id, 0, 0)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_seq_mismatch_409(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        with self.assertRaises(gs.GameError) as ctx:
            gs.flip(self.games, self.gami, "usr_1", run.run_id, 0, 1)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_flip_same_index_twice_400(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        gs.flip(self.games, self.gami, "usr_1", run.run_id, 0, 0)
        with self.assertRaises(gs.GameError) as ctx:
            gs.flip(self.games, self.gami, "usr_1", run.run_id, 0, 1)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_flip_too_fast_429(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        run, _ = gs.flip(self.games, self.gami, "usr_1", run.run_id, 0, 0)
        with self.assertRaises(gs.GameError) as ctx:
            gs.flip(self.games, self.gami, "usr_1", run.run_id, 1, 1)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_complete_run_settles_and_rewards(self):
        run = self._complete_run("easy")
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.settlement, "settled")
        progress = self.gami.get_progress("usr_1")
        # Chay het cap NGAY (khong doi giua cac lan lat) -> qua nhanh de xac
        # thuc, KHONG duoc tinh XP (xem `decide_memory_reward`).
        self.assertEqual(progress.xp, 0)
        results = self.games.list_results_for_source(run.run_id)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].validated)

    def test_abandon_no_reward(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        run = gs.abandon_run(self.games, "usr_1", run.run_id)
        self.assertEqual(run.status, "abandoned")
        self.assertEqual(run.settlement, "none")

    def test_get_run_owner_check(self):
        run = gs.start_run(self.games, "usr_1", "easy")
        with self.assertRaises(gs.GameError) as ctx:
            gs.get_run(self.games, self.gami, "usr_2", run.run_id)
        self.assertEqual(ctx.exception.status_code, 403)


class MemoryPlausibilityTest(unittest.TestCase):
    def test_plausible_slow_run_is_rewarded(self):
        import datetime as _dt

        games = MockGamesStore()
        gami = MockGamificationStore()
        run = gs.start_run(games, "usr_1", "easy")
        # Gia lap mot luot cham (hop le) bang cach lui `started_at` 30 giay —
        # DU de qua nguong hop le (pairs*1.2 = 7.2s cho "easy") nhung CON XA
        # nguong het gio (`MEMORY_MAX_SECONDS=900`), khac voi lui qua xa
        # (vi du nam 2020) se tu kich hoat het gio ngay lap tuc.
        stored = games.get_run(run.run_id)
        stored.started_at = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=30)
        ).isoformat()

        seen: dict = {}
        seq = 0
        for idx, key in enumerate(stored.layout):
            if key in seen:
                first_idx = seen.pop(key)
                time.sleep(0.15)
                run, _ = gs.flip(games, gami, "usr_1", run.run_id, first_idx, seq)
                seq += 1
                time.sleep(0.15)
                run, _ = gs.flip(games, gami, "usr_1", run.run_id, idx, seq)
                seq += 1
            else:
                seen[key] = idx

        self.assertEqual(run.status, "completed")
        results = games.list_results_for_source(run.run_id)
        self.assertTrue(results[0].validated)
        self.assertGreater(gami.get_progress("usr_1").xp, 0)


if __name__ == "__main__":
    unittest.main()

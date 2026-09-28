"""
Bang xep hang & lich su mini-game — Social & Play V1 Goi C §6.

Test truc tiep `games_service.leaderboard`/`history` voi `MockGamesStore` +
mot `identity`/`storage` gia — khong qua HTTP (route o `server/main.py` do
nguoi khac phu trach, xem `SP_C_BACKEND_SPEC.md`).
"""

import unittest

from server import games_service as gs
from server.gamification_store import MockGamificationStore
from server.games_domain import GameResult, RULE_CARO, RULE_MEMORY
from server.games_store import MockGamesStore


class _Profile:
    def __init__(self, user_id, username, display_name="", avatar_key=""):
        self.user_id = user_id
        self.username = username
        self.display_name = display_name
        self.avatar_key = avatar_key


class _FakeIdentity:
    def __init__(self, profiles):
        self._profiles = {p.user_id: p for p in profiles}

    def profiles_by_ids(self, ids):
        return {uid: self._profiles[uid] for uid in ids if uid in self._profiles}


def _seed_caro_result(games, *, user_id, opponent_id, season, outcome, points,
                      created_at, match_no=1, room_id=None):
    room_id = room_id or f"rm_{user_id}_{opponent_id}_{created_at}"
    source_id = f"{room_id}-{match_no}"
    result = GameResult(
        result_id=f"{source_id}|{user_id}", game="caro", season=season,
        user_id=user_id, opponent_id=opponent_id, outcome=outcome,
        points=points, difficulty="", xp_awarded=0, xp_entries=[],
        reasons=[], validated=True, rule_version=RULE_CARO,
        source_id=source_id, created_at=created_at)
    games.create_result(result)
    return result


def _seed_memory_result(games, *, user_id, season, difficulty, points,
                        created_at, run_id=None):
    run_id = run_id or f"mr_{user_id}_{created_at}"
    result = GameResult(
        result_id=f"{run_id}|{user_id}", game="memory", season=season,
        user_id=user_id, opponent_id="", outcome="completed", points=points,
        difficulty=difficulty, xp_awarded=0, xp_entries=[], reasons=[],
        validated=True, rule_version=RULE_MEMORY, source_id=run_id,
        created_at=created_at)
    games.create_result(result)
    return result


class CaroLeaderboardTest(unittest.TestCase):
    def setUp(self):
        self.games = MockGamesStore()
        self.identity = _FakeIdentity([
            _Profile("usr_a", "alice", "Alice"),
            _Profile("usr_b", "bob", "Bob"),
            _Profile("usr_c", "carol", "Carol"),
        ])

    def test_orders_by_points_then_wins_then_matches_then_first_reached(self):
        season = "2026-01"
        # usr_a: 2 thang 1 hoa = 7 diem, 3 tran.
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_b",
                          season=season, outcome="win", points=3,
                          created_at="2026-01-01T00:00:00+00:00")
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_c",
                          season=season, outcome="win", points=3,
                          created_at="2026-01-02T00:00:00+00:00")
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_b",
                          season=season, outcome="draw", points=1,
                          created_at="2026-01-03T00:00:00+00:00")
        # usr_b: 2 thang 1 hoa = 7 diem (BANG usr_a) nhung it tran hon (3
        # tran nhu nhau thuc ra) — de test tie-break that, cho usr_b it tran
        # hon (2 tran, 2 thang = 6 diem, THAP hon usr_a — kiem tra sap dung
        # theo diem truoc).
        _seed_caro_result(self.games, user_id="usr_b", opponent_id="usr_c",
                          season=season, outcome="win", points=3,
                          created_at="2026-01-01T00:00:00+00:00")
        _seed_caro_result(self.games, user_id="usr_b", opponent_id="usr_c",
                          season=season, outcome="win", points=3,
                          created_at="2026-01-02T00:00:00+00:00")
        # usr_c: toan thua, 0 diem.
        _seed_caro_result(self.games, user_id="usr_c", opponent_id="usr_a",
                          season=season, outcome="loss", points=0,
                          created_at="2026-01-02T00:00:00+00:00")

        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season=season, limit=20, offset=0)
        self.assertEqual(board["game"], "caro")
        self.assertEqual([it["user_id"] for it in board["items"]],
                         ["usr_a", "usr_b", "usr_c"])
        self.assertEqual(board["items"][0]["points"], 7)
        self.assertEqual(board["items"][0]["wins"], 2)
        self.assertEqual(board["items"][0]["draws"], 1)
        self.assertEqual(board["items"][0]["matches"], 3)
        self.assertEqual(board["items"][0]["rank"], 1)
        self.assertEqual(board["items"][1]["rank"], 2)
        self.assertEqual(board["total"], 3)

    def test_tie_break_by_wins_then_matches_then_first_reached_then_user_id(self):
        season = "2026-02"
        # usr_a va usr_b: CUNG 3 diem, CUNG 1 tran thang — nhung usr_a dat
        # duoc diem do SOM HON (`first_reached` nho hon) -> usr_a xep truoc.
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_c",
                          season=season, outcome="win", points=3,
                          created_at="2026-02-01T00:00:00+00:00")
        _seed_caro_result(self.games, user_id="usr_b", opponent_id="usr_c",
                          season=season, outcome="win", points=3,
                          created_at="2026-02-05T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season=season, limit=20, offset=0)
        self.assertEqual([it["user_id"] for it in board["items"][:2]],
                         ["usr_a", "usr_b"])

    def test_only_validated_results_count(self):
        season = "2026-03"
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_b",
                          season=season, outcome="win", points=3,
                          created_at="2026-03-01T00:00:00+00:00")
        invalid = GameResult(
            result_id="rm_x-1|usr_c", game="caro", season=season,
            user_id="usr_c", opponent_id="usr_b", outcome="win", points=3,
            difficulty="", xp_awarded=0, xp_entries=[],
            reasons=["Ván quá ngắn — không tính điểm."], validated=False,
            rule_version=RULE_CARO, source_id="rm_x-1",
            created_at="2026-03-02T00:00:00+00:00")
        self.games.create_result(invalid)
        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season=season, limit=20, offset=0)
        self.assertEqual([it["user_id"] for it in board["items"]], ["usr_a"])

    def test_pagination_limit_offset(self):
        season = "2026-04"
        for i, uid in enumerate(("usr_a", "usr_b", "usr_c")):
            _seed_caro_result(self.games, user_id=uid, opponent_id="usr_z",
                              season=season, outcome="win", points=3 - i,
                              created_at=f"2026-04-0{i + 1}T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season=season, limit=1, offset=1)
        self.assertEqual(len(board["items"]), 1)
        self.assertEqual(board["items"][0]["user_id"], "usr_b")
        self.assertEqual(board["items"][0]["rank"], 2)
        self.assertEqual(board["total"], 3)

    def test_viewer_entry_present_when_outside_page(self):
        season = "2026-05"
        for i, uid in enumerate(("usr_a", "usr_b", "usr_c")):
            _seed_caro_result(self.games, user_id=uid, opponent_id="usr_z",
                              season=season, outcome="win", points=3 - i,
                              created_at=f"2026-05-0{i + 1}T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season=season, limit=1, offset=0,
                               viewer_id="usr_c")
        self.assertEqual([it["user_id"] for it in board["items"]], ["usr_a"])
        self.assertIsNotNone(board["viewer_entry"])
        self.assertEqual(board["viewer_entry"]["user_id"], "usr_c")
        self.assertEqual(board["viewer_entry"]["rank"], 3)

    def test_seasons_list(self):
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_b",
                          season="2026-01", outcome="win", points=3,
                          created_at="2026-01-01T00:00:00+00:00")
        _seed_caro_result(self.games, user_id="usr_a", opponent_id="usr_b",
                          season="2026-02", outcome="win", points=3,
                          created_at="2026-02-01T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="caro",
                               season="2026-02", limit=20, offset=0)
        self.assertEqual(set(board["seasons"]), {"2026-01", "2026-02"})


class MemoryLeaderboardTest(unittest.TestCase):
    def setUp(self):
        self.games = MockGamesStore()
        self.identity = _FakeIdentity([
            _Profile("usr_a", "alice"), _Profile("usr_b", "bob"),
        ])

    def test_best_score_wins_ties_broken_by_earliest_achieved(self):
        season = "2026-01"
        _seed_memory_result(self.games, user_id="usr_a", season=season,
                            difficulty="easy", points=300,
                            created_at="2026-01-01T00:00:00+00:00")
        _seed_memory_result(self.games, user_id="usr_a", season=season,
                            difficulty="easy", points=500,
                            created_at="2026-01-02T00:00:00+00:00",
                            run_id="mr_a_second")
        _seed_memory_result(self.games, user_id="usr_b", season=season,
                            difficulty="easy", points=500,
                            created_at="2026-01-03T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="memory",
                               season=season, difficulty="easy", limit=20,
                               offset=0)
        self.assertEqual([it["user_id"] for it in board["items"]],
                         ["usr_a", "usr_b"])
        self.assertEqual(board["items"][0]["best_score"], 500)
        self.assertEqual(board["items"][0]["runs"], 2)
        self.assertEqual(board["items"][1]["runs"], 1)

    def test_difficulty_filter_isolates_boards(self):
        season = "2026-01"
        _seed_memory_result(self.games, user_id="usr_a", season=season,
                            difficulty="easy", points=100,
                            created_at="2026-01-01T00:00:00+00:00")
        _seed_memory_result(self.games, user_id="usr_b", season=season,
                            difficulty="hard", points=999,
                            created_at="2026-01-01T00:00:00+00:00")
        board = gs.leaderboard(self.games, self.identity, None, game="memory",
                               season=season, difficulty="easy", limit=20,
                               offset=0)
        self.assertEqual([it["user_id"] for it in board["items"]], ["usr_a"])


class HistoryTest(unittest.TestCase):
    def test_history_returns_recent_results_with_settlement_state(self):
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

        items = gs.history(games, "usr_x", 20)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["outcome"], "win")
        self.assertEqual(items[0]["settlement_state"], "settled")

    def test_history_empty_for_unknown_user(self):
        games = MockGamesStore()
        self.assertEqual(gs.history(games, "usr_ghost", 20), [])


if __name__ == "__main__":
    unittest.main()

"""
HOP DONG Appwrite cho mini-game (Social & Play V1 Goi C) — CAS qua
transaction that su (`game_room_versions`/`game_run_versions`/
`xp_progress_cas`), voi mot client GIA LAP hieu duoc `/v1/tablesdb/
transactions` (tao/dan thao tac/commit) — `FakeAppwrite` cua
`test_appwrite_v2_contract.py` KHONG hieu duong nay, nen bo test o day mo
rong no bang `_FakeTxAppwrite`.

CANH BAO giong het docstring cua `AppwriteGamesStore`/`AppwriteGamification
Store.award_xp_atomic`: day la mot BAN GIA LAP REST, khong phai Appwrite
that — no chi bat duoc loai loi ma NO biet mo phong (rowId trung khi
commit). Duong Appwrite that van CHUA duoc kiem, xem
`docs/migrations/SOCIAL_PLAY_V1_GAMES_SCHEMA.md`.
"""

from __future__ import annotations

import unittest

from server.appwrite_games_store import AppwriteGamesStore
from server.appwrite_gamification_store import AppwriteGamificationStore
from server.config import AppwriteSettings
from server.gamification_domain import XpLedgerEntry
from server.games_domain import new_memory_run, new_room
from server.games_store import GamesConflict
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client


class _FakeTxAppwrite(FakeAppwrite):
    """`FakeAppwrite` + `/v1/tablesdb/transactions` (tao / dan thao tac /
    commit). Commit THAT BAI (tra `{"status": "failed"}`, KHONG nem) neu BAT
    KY thao tac `create` nao trung `rowId` da co san — day la hanh vi CAS cot
    loi ma `save_room`/`save_run`/`award_xp_atomic` dua vao."""

    def __init__(self) -> None:
        super().__init__()
        self._tx: dict = {}
        #: Appwrite THAT tu dat `$updatedAt` o MOI lan ghi mot hang — ban gia
        #: lap phai lam giong, vi `award_xp_atomic` dung no lam dau trang thai
        #: cho marker `xp_progress_cas` (xem `xp_progress_cas_row_id`).
        self._nhip = 0
        #: Dat True de mo phong "loi tam thoi" (vd mat mang) o LAN COMMIT
        #: KE TIEP — khac voi that bai do trung rowId (CAS that), day la
        #: loi VAN CHUYEN, khong lien quan gi den du lieu.
        self.fail_next_commit_transport = False

    def request(self, method, url, json=None, params=None, headers=None):
        if method == "POST" and url.endswith("/v1/tablesdb/transactions"):
            tx_id = f"tx_{len(self._tx) + 1}"
            self._tx[tx_id] = []
            return {"$id": tx_id}
        if method == "POST" and "/v1/tablesdb/transactions/" in url and url.endswith("/operations"):
            tx_id = url.split("/v1/tablesdb/transactions/")[1].split("/operations")[0]
            self._tx[tx_id].extend((json or {}).get("operations") or [])
            return {}
        if method == "PATCH" and "/v1/tablesdb/transactions/" in url:
            if self.fail_next_commit_transport:
                self.fail_next_commit_transport = False
                raise RuntimeError("loi van chuyen gia lap")
            tx_id = url.split("/v1/tablesdb/transactions/")[1]
            ops = self._tx.pop(tx_id, [])
            seen = set()
            for op in ops:
                if op["action"] == "create":
                    table = self.rows.setdefault(op["tableId"], {})
                    key = (op["tableId"], op["rowId"])
                    if key in seen or op["rowId"] in table:
                        return {"status": "failed"}
                    seen.add(key)
            for op in ops:
                table = self.rows.setdefault(op["tableId"], {})
                self._nhip += 1
                dau = f"2026-01-01T00:00:00.{self._nhip:06d}+00:00"
                if op["action"] == "create":
                    table[op["rowId"]] = dict(op.get("data") or {}, **{"$updatedAt": dau})
                elif op["action"] == "update":
                    table.setdefault(op["rowId"], {}).update(op.get("data") or {})
                    table[op["rowId"]]["$updatedAt"] = dau
            return {"status": "committed"}
        return super().request(method, url, json=json, params=params, headers=headers)


def _cfg() -> AppwriteSettings:
    return AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                            api_key="k", database_id="db")


def _games_store(fake: _FakeTxAppwrite) -> AppwriteGamesStore:
    return AppwriteGamesStore(_cfg(), client=_bo_client(fake))


def _gami_store(fake: _FakeTxAppwrite) -> AppwriteGamificationStore:
    kho = AppwriteGamificationStore(_cfg(), client=_bo_client(fake))
    kho._attrs_cache = {}
    return kho


class RoomCasTest(unittest.TestCase):
    def test_save_room_cas_success_then_stale_version_conflicts(self):
        fake = _FakeTxAppwrite()
        store = _games_store(fake)
        room = new_room("rm_1", "ABCDEF", "usr_x")
        store.create_room(room)

        room.seat_o = "usr_o"
        room.version = 2
        saved = store.save_room(room, expected_version=1)
        self.assertEqual(saved.seat_o, "usr_o")

        # Cung `expected_version=1` lan nua (STALE — hang that gio la
        # version 2) -> marker `rm_1-v2` DA CO -> GamesConflict.
        stale = store.get_room("rm_1")
        stale.ready_x = True
        stale.version = 2
        with self.assertRaises(GamesConflict):
            store.save_room(stale, expected_version=1)

    def test_get_room_by_code_and_code_is_taken(self):
        fake = _FakeTxAppwrite()
        store = _games_store(fake)
        room = new_room("rm_2", "ZZZZZZ", "usr_x")
        store.create_room(room)
        self.assertEqual(store.get_room_by_code("ZZZZZZ").room_id, "rm_2")
        self.assertTrue(store.code_is_taken("ZZZZZZ"))
        self.assertFalse(store.code_is_taken("NOTHERE"))

    def test_touch_seat_does_not_require_transaction(self):
        fake = _FakeTxAppwrite()
        store = _games_store(fake)
        room = new_room("rm_3", "AAAAAA", "usr_x")
        store.create_room(room)
        store.touch_seat("rm_3", "x", "2026-01-01T00:00:00+00:00")
        self.assertEqual(store.get_room("rm_3").last_seen_x,
                         "2026-01-01T00:00:00+00:00")


class RunCasTest(unittest.TestCase):
    def test_save_run_cas_success_then_stale_version_conflicts(self):
        fake = _FakeTxAppwrite()
        store = _games_store(fake)
        run = new_memory_run("mr_1", "usr_1", "easy")
        store.create_run(run)

        run.moves = 1
        run.version = 2
        saved = store.save_run(run, expected_version=1)
        self.assertEqual(saved.moves, 1)

        stale = store.get_run("mr_1")
        stale.version = 2
        with self.assertRaises(GamesConflict):
            store.save_run(stale, expected_version=1)


class ResultIdempotencyTest(unittest.TestCase):
    def test_create_result_second_call_returns_false(self):
        from server.games_domain import GameResult, RULE_CARO

        fake = _FakeTxAppwrite()
        store = _games_store(fake)
        result = GameResult(
            result_id="rm_1-1|usr_x", game="caro", season="2026-01",
            user_id="usr_x", opponent_id="usr_o", outcome="win", points=3,
            difficulty="", xp_awarded=5, xp_entries=[], reasons=[],
            validated=True, rule_version=RULE_CARO, source_id="rm_1-1")
        self.assertTrue(store.create_result(result))
        self.assertFalse(store.create_result(result))
        fetched = store.get_result("rm_1-1|usr_x")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.user_id, "usr_x")


class AwardXpAtomicContractTest(unittest.TestCase):
    def test_transaction_payload_has_three_operations(self):
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        captured = {}
        real_request = fake.request

        def spy(method, url, json=None, params=None, headers=None):
            if method == "POST" and "/operations" in url:
                captured["operations"] = (json or {}).get("operations")
            return real_request(method, url, json=json, params=params, headers=headers)

        fake.request = spy  # type: ignore[assignment]

        entry = XpLedgerEntry(entry_id="xp_1", user_id="usr_1",
                              event_type="game_match_completed",
                              source_kind="game_match", source_id="rm_1-1|caro-v1",
                              xp_awarded=2)
        progress = store.award_xp_atomic(entry)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.xp, 2)
        ops = captured["operations"]
        self.assertEqual(len(ops), 3)
        table_ids = {op["tableId"] for op in ops}
        self.assertEqual(table_ids, {"xp_ledger", "user_progress", "xp_progress_cas"})

    def test_commit_failure_with_ledger_already_existing_returns_none(self):
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        entry = XpLedgerEntry(entry_id="xp_dup", user_id="usr_1",
                              event_type="game_match_completed",
                              source_kind="game_match", source_id="rm_2-1|caro-v1",
                              xp_awarded=2)
        # Gia lap hang xp_ledger DA TON TAI (vi du: mot lan thu TRUOC do da
        # cong thanh cong, nhung nguoi goi khong nhan duoc phan hoi — vi du
        # mat ket noi ngay sau khi commit).
        fake.rows.setdefault("xp_ledger", {})["xp_dup"] = {
            "entry_id": "xp_dup", "user_id": "usr_1",
            "event_type": "game_match_completed", "source_kind": "game_match",
            "source_id": "rm_2-1|caro-v1", "xp_awarded": 2,
            "created_at": "2026-01-01T00:00:00+00:00"}
        result = store.award_xp_atomic(entry)
        self.assertIsNone(result)
        # KHONG cong lai — progress van CHUA co hang (chua tung tao qua
        # duong nay), dung nhu "da cong roi tu lan truoc, khong lam gi them".

    def test_commit_transport_failure_retries_with_fresh_read(self):
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        fake.fail_next_commit_transport = True  # loi VAN CHUYEN o lan dau
        entry = XpLedgerEntry(entry_id="xp_retry", user_id="usr_1",
                              event_type="game_match_completed",
                              source_kind="game_match", source_id="rm_3-1|caro-v1",
                              xp_awarded=2)
        progress = store.award_xp_atomic(entry)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.xp, 2)
        # Dung MOT hang trong xp_ledger — khong cong hai lan du lan dau that bai.
        self.assertEqual(len(fake.rows.get("xp_ledger", {})), 1)

    def test_xp_chinh_ve_gia_tri_cu_khong_lam_ket_marker(self):
        """HOI QUY (review goi C): marker cu la sha256(user_id|prior_xp). Neu XP
        tung bi GIAM (vd dieu chinh bu cua quan tri) roi quay lai DUNG gia tri
        truoc do, marker cua lan cong cu da ton tai -> moi lan cong moi tu gia
        tri do deu thua commit, het 5 lan thu -> AppwriteUnavailableError:
        nguoi dung KHONG BAO GIO duoc cong XP nua. Marker nay phai gan voi
        TRANG THAI hang tien do (`$updatedAt`), khong chi voi con so XP."""
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        e1 = XpLedgerEntry(entry_id="xp_a", user_id="usr_1", event_type="game_match_completed",
                           source_kind="game_match", source_id="rm_5-1|caro-v1", xp_awarded=2)
        self.assertEqual(store.award_xp_atomic(e1).xp, 2)
        # Dieu chinh bu ngoai duong nay: XP ve lai 0, hang duoc ghi (Appwrite
        # dat `$updatedAt` moi).
        hang = fake.rows["user_progress"]["usr_1"]
        hang["xp"] = 0
        hang["$updatedAt"] = "2026-02-01T00:00:00.000000+00:00"
        e2 = XpLedgerEntry(entry_id="xp_b", user_id="usr_1", event_type="game_match_completed",
                           source_kind="game_match", source_id="rm_6-1|caro-v1", xp_awarded=2)
        progress = store.award_xp_atomic(e2)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.xp, 2)
        self.assertEqual(store.get_progress("usr_1").xp, 2)
        self.assertEqual(len(fake.rows["xp_ledger"]), 2)

    def test_doc_trang_thai_cu_van_bi_marker_chan_khong_mat_lan_cong(self):
        """Bao dam ban sua KHONG lam yeu khoa chong "lost update": nguoi ghi B
        doc trang thai CU (truoc khi A commit) sinh DUNG marker cua A -> commit
        thua -> doc lai trang thai MOI -> cong tren do. Tong cuoi = 4, khong phai 2."""
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        e0 = XpLedgerEntry(entry_id="xp_0", user_id="usr_1", event_type="game_match_completed",
                           source_kind="game_match", source_id="rm_7-1|caro-v1", xp_awarded=2)
        store.award_xp_atomic(e0)  # xp = 2, co hang tien do
        cu = dict(fake.rows["user_progress"]["usr_1"])  # anh chup trang thai TRUOC khi A ghi
        eA = XpLedgerEntry(entry_id="xp_A", user_id="usr_1", event_type="game_match_won",
                           source_kind="game_match", source_id="rm_8-1|caro-v1", xp_awarded=3)
        self.assertEqual(store.award_xp_atomic(eA).xp, 5)

        that_get = store._get
        lan = {"n": 0}

        def get_cu_mot_lan(collection, doc_id):
            if collection == "user_progress" and lan["n"] == 0:
                lan["n"] += 1
                return dict(cu)  # B doc ban CU (xp=2) — nhu doc truoc khi A commit
            return that_get(collection, doc_id)

        store._get = get_cu_mot_lan  # type: ignore[assignment]
        eB = XpLedgerEntry(entry_id="xp_B", user_id="usr_1", event_type="game_match_completed",
                           source_kind="game_match", source_id="rm_9-1|caro-v1", xp_awarded=2)
        self.assertEqual(store.award_xp_atomic(eB).xp, 7)
        self.assertEqual(lan["n"], 1)
        self.assertEqual(that_get("user_progress", "usr_1")["xp"], 7)

    def test_duplicate_entry_id_second_call_returns_none(self):
        fake = _FakeTxAppwrite()
        store = _gami_store(fake)
        entry = XpLedgerEntry(entry_id="xp_once", user_id="usr_1",
                              event_type="game_match_completed",
                              source_kind="game_match", source_id="rm_4-1|caro-v1",
                              xp_awarded=2)
        self.assertIsNotNone(store.award_xp_atomic(entry))
        self.assertIsNone(store.award_xp_atomic(entry))
        self.assertEqual(store.get_progress("usr_1").xp, 2)


if __name__ == "__main__":
    unittest.main()

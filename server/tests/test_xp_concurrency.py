"""
Duong XP NGUYEN TU cho MOI writer (Social & Play V1 — hoan tat truoc khi bat game that).

Kiem dung nhung gi chu du an yeu cau:
  * dong thoi: quyet toan game + nhan thuong nhiem vu + XP doc/nghe + doi danh xung, cung mot
    nguoi, bang luong THAT -> khong mat lan cong nao, khong cong hai lan;
  * tung writer cu (equip_title, open_reward_pack, award_xp, claim_quest_reward) doc TRANG THAI
    CU tren Appwrite (client gia lap) -> hang khoa CAS chan, thu lai tren trang thai moi;
  * sap giua chung khi nhan thuong nhiem vu -> goi lai nhan du, dung mot lan;
  * XP bi chinh ve gia tri cu -> cac writer van ghi tiep duoc (khong ket khoa);
  * tran cap doi thu / XP ngay / luot Memory duoi tai dong thoi trong MOT tien trinh;
  * duong cu (co tat) van dung; cau hinh tu choi bat game tren Appwrite khi co XP nguyen tu tat.
"""

from __future__ import annotations

import copy
import dataclasses
import random
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from server import games_service as gs
from server import gamification_service as gsv
from server.config import AppwriteSettings, ConfigError, load_settings
from server.gamification import QUEST_CATALOG, XP_EVENTS
from server.gamification_domain import XpLedgerEntry
from server.gamification_store import MockGamificationStore
from server.games_domain import (DAILY_GAME_XP_CAP, MAX_REWARDED_PER_PAIR_PER_DAY,
                                 MAX_REWARDED_RUNS_PER_DAY, new_memory_run, new_room)
from server.games_store import MockGamesStore
from server.tests.test_games_appwrite_contract import _FakeTxAppwrite, _gami_store

HOM_NAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _chay_dong_thoi(viec, so_luong_toi_da=24):
    """Chay moi ham trong `viec` tren mot luong rieng, cung xuat phat (Barrier)."""
    rao = threading.Barrier(len(viec))
    loi = []

    def boc(f):
        def chay():
            rao.wait()
            try:
                f()
            except Exception as exc:  # noqa: BLE001 — gom lai, bao sau
                loi.append(exc)
        return chay

    luong = [threading.Thread(target=boc(f)) for f in viec]
    for t in luong:
        t.start()
    for t in luong:
        t.join(30)
    return loi


class DongThoiNhieuWriterTest(unittest.TestCase):
    """Luong THAT tren kho trong bo nho (duong nguyen tu bat)."""

    def test_game_nhiem_vu_doc_nghe_doi_danh_xung_cung_luc_khong_mat_khong_trung(self):
        kho = MockGamificationStore()
        u = "usr_dongthoi"
        # Moi nhiem vu du dieu kien nhan thuong trong ky nay.
        for loai in {q.event_type for q in QUEST_CATALOG}:
            gsv.record_quest_event(kho, u, loai, HOM_NAY, amount=10)

        viec = []
        for i in range(20):  # XP nghe (duong award_xp cu, nay nguyen tu)
            viec.append(lambda i=i: gsv.award_xp(kho, u, "listen_milestone_qualified",
                                                 source_kind="chapter", source_id=f"ch{i}"))
        for i in range(20):  # quyet toan game
            viec.append(lambda i=i: kho.award_xp_atomic(XpLedgerEntry(
                entry_id=f"xp_game_{i}", user_id=u, event_type="game_match_completed",
                source_kind="game_match", source_id=f"rm_{i}-1|caro-v1", xp_awarded=2)))
        for q in QUEST_CATALOG:  # moi nhiem vu bi bam NHAN hai lan cung luc
            for _ in range(2):
                viec.append(lambda q=q: gsv.claim_quest_reward(kho, u, q.key, HOM_NAY))
        for _ in range(10):  # doi danh xung (writer doc-sua-ghi cu)
            viec.append(lambda: gsv.equip_title(kho, u, ""))
        random.Random(7).shuffle(viec)

        loi = _chay_dong_thoi(viec)
        # Nhan hai lan cung luc: lan thu hai co the qua phep kiem (ca hai cung thay claimed=False)
        # hoac bi tu choi "da nhan" — ca hai deu hop le; KHONG hop le la cong XP hai lan.
        self.assertTrue(all(isinstance(e, gsv.GamificationError) for e in loi), loi)

        xp_nhiem_vu = sum(q.xp_reward for q in QUEST_CATALOG)
        mong_doi = 20 * XP_EVENTS["listen_milestone_qualified"] + 20 * 2 + xp_nhiem_vu
        self.assertEqual(kho.get_progress(u).xp, mong_doi)
        so_cai = kho.list_xp_events(u)
        self.assertEqual(sum(e.xp_awarded for e in so_cai), mong_doi)
        self.assertEqual(sum(1 for e in so_cai if e.event_type == "quest_reward"), len(QUEST_CATALOG))

    def test_mo_goi_thuong_cung_luc_khong_mo_qua_so_goi(self):
        kho = MockGamificationStore()
        u = "usr_goi"
        kho.award_xp_atomic(XpLedgerEntry(entry_id="xp_len_bac", user_id=u, event_type="publish_first_novel",
                                          source_kind="t", source_id="t", xp_awarded=600))
        so_goi = kho.get_progress(u).goi_thuong_dang_cho
        self.assertGreaterEqual(so_goi, 2)
        viec = [lambda: gsv.open_reward_pack(kho, u, "goi_len_bac", random.Random(1))
                for _ in range(so_goi + 3)]
        viec += [lambda i=i: kho.award_xp_atomic(XpLedgerEntry(
            entry_id=f"xp_p{i}", user_id=u, event_type="game_match_completed", source_kind="g",
            source_id=f"g{i}", xp_awarded=2)) for i in range(10)]
        loi = _chay_dong_thoi(viec)
        self.assertEqual(len(loi), 3, loi)  # dung 3 lan thua "khong co goi"
        p = kho.get_progress(u)
        self.assertEqual(p.goi_thuong_dang_cho, 0)
        self.assertEqual(p.xp, 600 + 20)


class DocTrangThaiCuAppwriteTest(unittest.TestCase):
    """Moi writer doc ban CU cua hang tien do (nhu doc truoc khi writer khac commit): hang khoa CAS
    phai lam commit cu thua, writer doc lai va ghi tren trang thai moi — khong de len XP."""

    def _kho(self):
        fake = _FakeTxAppwrite()
        kho = _gami_store(fake)
        kho.xp_atomic = True
        gsv.award_xp(kho, "u1", "publish_first_novel", source_kind="n", source_id="n1")  # xp 50
        return fake, kho

    def _doc_cu_mot_lan(self, kho, anh_cu):
        that = kho._get
        lan = {"n": 0}

        def get(col, doc_id):
            if col == "user_progress" and lan["n"] == 0:
                lan["n"] += 1
                return dict(anh_cu)
            return that(col, doc_id)

        kho._get = get
        return lan

    def test_doi_danh_xung_doc_cu_khong_de_len_xp_vua_cong(self):
        fake, kho = self._kho()
        cu = dict(fake.rows["user_progress"]["u1"])
        gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c1")  # +10 -> 60
        lan = self._doc_cu_mot_lan(kho, cu)
        gsv.equip_title(kho, "u1", "")
        self.assertEqual(lan["n"], 1)
        self.assertEqual(fake.rows["user_progress"]["u1"]["xp"], 60)

    def test_mo_goi_doc_cu_khong_de_len_xp_va_chi_tru_mot_goi(self):
        fake, kho = self._kho()
        gsv.award_xp(kho, "u1", "translation_project_completed", source_kind="t", source_id="t1")  # +20 -> 70
        hang = fake.rows["user_progress"]["u1"]
        hang["pending_reward_packs"] = 2  # ten cot that tren Appwrite
        hang["$updatedAt"] = "2026-03-01T00:00:00.000001+00:00"
        cu = dict(hang)
        gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c2")  # +10 -> 80
        self._doc_cu_mot_lan(kho, cu)
        gsv.open_reward_pack(kho, "u1", "goi_len_bac", random.Random(3))
        hang = fake.rows["user_progress"]["u1"]
        self.assertEqual((hang["xp"], hang["pending_reward_packs"]), (80, 1))

    def test_nhan_thuong_nhiem_vu_doc_cu_khong_mat_lan_cong(self):
        fake, kho = self._kho()
        q = next(q for q in QUEST_CATALOG if q.xp_reward and not q.cosmetic_reward_key)
        gsv.record_quest_event(kho, "u1", q.event_type, HOM_NAY, amount=10)
        cu = dict(fake.rows["user_progress"]["u1"])
        gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c3")  # +10
        self._doc_cu_mot_lan(kho, cu)
        gsv.claim_quest_reward(kho, "u1", q.key, HOM_NAY)
        self.assertEqual(fake.rows["user_progress"]["u1"]["xp"], 50 + 10 + q.xp_reward)

    def test_xp_chinh_ve_gia_tri_cu_doi_danh_xung_van_ghi_duoc(self):
        fake, kho = self._kho()
        gsv.equip_title(kho, "u1", "")  # marker cho trang thai (50, t1)
        hang = fake.rows["user_progress"]["u1"]
        hang["xp"] = 50  # dieu chinh bu ve DUNG gia tri cu, hang mang $updatedAt moi
        hang["$updatedAt"] = "2026-04-01T00:00:00.000001+00:00"
        gsv.equip_title(kho, "u1", "")  # truoc ban sua: ket vinh vien -> AppwriteUnavailableError
        gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c9")
        self.assertEqual(fake.rows["user_progress"]["u1"]["xp"], 60)


class SapGiuaChungNhiemVuTest(unittest.TestCase):
    def test_sap_sau_khi_cong_xp_truoc_khi_danh_dau_goi_lai_nhan_du_mot_lan(self):
        for nguyen_tu in (True, False):
            with self.subTest(nguyen_tu=nguyen_tu):
                kho = MockGamificationStore()
                kho.xp_atomic = nguyen_tu
                q = next(q for q in QUEST_CATALOG if q.xp_reward and not q.cosmetic_reward_key)
                gsv.record_quest_event(kho, "u1", q.event_type, HOM_NAY, amount=10)
                # Kho trong bo nho tra ve CHINH doi tuong dang luu — gan `claimed` la da "ghi" truoc
                # ca khi save. Kho that (Appwrite) luon tra ban sao moi: mo phong dung dieu do.
                doc_that = kho.get_quest_progress
                kho.get_quest_progress = lambda *a: copy.deepcopy(doc_that(*a))
                that = kho.save_quest_progress
                lan = {"n": 0}

                def sap_mot_lan(tien_do):
                    if tien_do.claimed and lan["n"] == 0:
                        lan["n"] += 1
                        raise RuntimeError("sap gia lap truoc khi danh dau claimed")
                    return that(tien_do)

                kho.save_quest_progress = sap_mot_lan
                with self.assertRaises(RuntimeError):
                    gsv.claim_quest_reward(kho, "u1", q.key, HOM_NAY)
                # Goi lai: CHUA danh dau -> nhan duoc; so cai tu chan trung.
                gsv.claim_quest_reward(kho, "u1", q.key, HOM_NAY)
                self.assertEqual(kho.get_progress("u1").xp, q.xp_reward)
                with self.assertRaises(gsv.GamificationError):
                    gsv.claim_quest_reward(kho, "u1", q.key, HOM_NAY)


def _doc_cham(games, gami, giay=0.02):
    """Moi lan doc TRAN cham `giay` (nhu mot vong goi mang toi Appwrite) — noi cua so tranh chap de
    bai kiem PHAN BIET duoc co/khong co khoa. Do that: khoa no-op -> 8/3 van cap, 40/30 XP, 8/5 luot."""
    for kho, ten in ((games, "list_results_for_pair_since"), (games, "list_results_for_user_since"),
                     (gami, "list_xp_events_since")):
        goc = getattr(kho, ten)

        def cham(*a, _goc=goc, **k):
            kq = _goc(*a, **k)
            time.sleep(giay)
            return kq

        setattr(kho, ten, cham)
    return games, gami


class TranDuoiTaiDongThoiTest(unittest.TestCase):
    """Trong MOT tien trinh: khoa quyet toan theo nguoi choi lam tran chinh xac (tran CUNG trong mot
    tien trinh API; nhieu instance thi van la tran MEM — xem `games_service._khoa_quyet_toan`)."""

    def _phong_xong(self, games, x, o, i, thang="x"):
        r = new_room(f"rm_{i:04d}{x[-3:]}{o[-3:]}", f"C{i:05d}", x)
        r.seat_o, r.status, r.winner, r.end_reason = o, "finished", thang, "five"
        r.moves = [[k, "x" if k % 2 == 0 else "o"] for k in range(9)]
        r.finished_at, r.settlement = datetime.now(timezone.utc).isoformat(), "pending"
        games.create_room(r)
        return r

    def test_tran_cap_doi_thu_khi_8_van_ket_thuc_cung_luc(self):
        games, gami = _doc_cham(MockGamesStore(), MockGamificationStore())
        phong = [self._phong_xong(games, "usr_aaa", "usr_bbb", i) for i in range(8)]
        loi = _chay_dong_thoi([lambda r=r: gs.settle(games, gami, r) for r in phong])
        self.assertEqual(loi, [])
        hop_le = sum(1 for r in phong if games.get_result(f"{r.match_id}|usr_aaa").validated)
        self.assertEqual(hop_le, MAX_REWARDED_PER_PAIR_PER_DAY)

    def test_tran_xp_ngay_khi_8_doi_thu_khac_nhau_cung_ket_thuc(self):
        games, gami = _doc_cham(MockGamesStore(), MockGamificationStore())
        phong = [self._phong_xong(games, "usr_aaa", f"usr_d{i:02d}", i) for i in range(8)]
        loi = _chay_dong_thoi([lambda r=r: gs.settle(games, gami, r) for r in phong])
        self.assertEqual(loi, [])
        xp_game = sum(e.xp_awarded for e in gami.list_xp_events("usr_aaa")
                      if e.event_type.startswith("game_"))
        self.assertEqual(xp_game, DAILY_GAME_XP_CAP)  # 6 van x (2 + 3), khong hon

    def test_tran_luot_memory_khi_8_luot_hoan_thanh_cung_luc(self):
        games, gami = _doc_cham(MockGamesStore(), MockGamificationStore())
        runs = []
        bay_gio = datetime.now(timezone.utc)
        for i in range(8):
            r = new_memory_run(f"mr_{i:04d}", "usr_mem", "easy")
            r.status, r.moves, r.matched = "completed", r.pairs, list(range(r.rows * r.cols))
            r.started_at = (bay_gio - timedelta(minutes=2)).isoformat()
            r.finished_at, r.score, r.settlement = bay_gio.isoformat(), 400, "pending"
            r.season = bay_gio.strftime("%Y-%m")
            games.create_run(r)
            runs.append(r)
        loi = _chay_dong_thoi([lambda r=r: gs.settle(games, gami, r) for r in runs])
        self.assertEqual(loi, [])
        co_xp = sum(1 for r in runs if games.get_result(f"{r.run_id}|usr_mem").xp_awarded > 0)
        self.assertEqual(co_xp, MAX_REWARDED_RUNS_PER_DAY)


class DuongCuVaCauHinhTest(unittest.TestCase):
    def test_co_tat_duong_cu_van_cong_dung_va_khong_trung(self):
        kho = MockGamificationStore()
        kho.xp_atomic = False
        self.assertIsNotNone(gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c1"))
        self.assertIsNone(gsv.award_xp(kho, "u1", "publish_chapter", source_kind="c", source_id="c1"))
        gsv.equip_title(kho, "u1", "")
        self.assertEqual(kho.get_progress("u1").xp, XP_EVENTS["publish_chapter"])

    def test_mac_dinh_co_xp_nguyen_tu_theo_backend(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"DATA_BACKEND": "mock"}, clear=False):
            os.environ.pop("FAS_XP_ATOMIC", None)
            self.assertTrue(load_settings().xp_atomic_enabled)
        with mock.patch.dict(os.environ, {"DATA_BACKEND": "appwrite"}, clear=False):
            os.environ.pop("FAS_XP_ATOMIC", None)
            self.assertFalse(load_settings().xp_atomic_enabled)

    def test_bat_game_tren_appwrite_ma_tat_xp_nguyen_tu_thi_tu_choi_khoi_dong(self):
        aw = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p", api_key="k", database_id="d")
        s = dataclasses.replace(load_settings(), data_backend="appwrite", appwrite=aw,
                                games_v1_enabled=True, xp_atomic_enabled=False)
        with self.assertRaises(ConfigError):
            s.validate()
        dataclasses.replace(s, xp_atomic_enabled=True).validate()
        dataclasses.replace(s, games_v1_enabled=False).validate()


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""V0.6.1 — TOẢ: "gọi N agent…" thành 1 việc cha + N việc con, đúng sức chứa.

Khuyết tật (nghiệm thu tay dist-v061): "gọi 8 agent gemini 3.8 và phân mỗi
đứa đi lục cho t 1 bộ fanfic audi" -> Leader tạo MỘT việc, Router giao đúng
AG02. Bài kiểm ở đây khoá lại từng yêu cầu của đề bài, KHÔNG gọi agent thật:
`FakeExecutor` + fabric giả 2 runtime × 2 khe (4 khe, cùng nhà cung cấp
antigravity) — chính là môi trường của lát cắt dọc V0.1.
"""
from __future__ import annotations

import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import toa as TOA                              # noqa: E402
from scripts.control_center.engine import ControlCenter                    # noqa: E402
from scripts.control_center.model import Project, TaskState               # noqa: E402
from scripts.router_v4.envelope import ResultEnvelope                      # noqa: E402
from scripts.router_v4.executor import ExecutionResult                     # noqa: E402
from scripts.tests.test_control_center_slice import (FakeExecutor,         # noqa: E402
                                                     fabric_gia, kho_git_tam)

CAU_8 = "gọi 8 agent gemini 3.8 và phân mỗi đứa đi lục cho t 1 bộ fanfic audi"
CAU_4 = "gọi 4 agent và phân mỗi đứa đi lục cho tôi 1 bộ fanfic audio trong web"


class ExecTuyBien(FakeExecutor):
    """Fake executor: tóm tắt/hỏng theo mã việc — để kiểm khử trùng và một con hỏng."""

    def __init__(self, *, tom_tat=None, hong_neu=None, cham: float = 0.0):
        super().__init__(cham=cham)
        self.tom_tat = tom_tat or (lambda tid, p: f"KẾT QUẢ [{tid.rsplit('-', 1)[-1]}/N]: bo-{tid}")
        self.hong_neu = hong_neu or (lambda tid: False)
        self.runtimes = []
        self._k = threading.Lock()

    def run(self, c, p, *, base_sha="", dependency_summaries=None,
            dependency_workspaces=None, attempt=1, reassigned=False):
        with self._k:
            self.da_chay.append(c.task_id)
            self.runtimes.append(p.runtime_id)
        if self.cham:
            time.sleep(self.cham)
        hong = self.hong_neu(c.task_id)
        pb = ResultEnvelope(task_id=c.task_id, status="failed" if hong else "ok",
                            summary=("" if hong else self.tom_tat(c.task_id, p)),
                            worker=p.runtime_id, model=p.model_id, provider="antigravity",
                            duration=0.01, failure_reason="gia_lap_hong" if hong else "")
        return ExecutionResult(envelope=pb, validation=None, worktree="", branch="")


def _cc(repo: Path, *, ex, max_parallel: int = 4) -> ControlCenter:
    cc = ControlCenter(root=repo, fabric=fabric_gia(), probe=False,
                       max_parallel=max_parallel, executor_factory=lambda p, f: ex)
    cc.them_project(Project(project_id="demo", name="Demo", repo_path=str(repo),
                            resources=("write:web",)))
    return cc


def _cho(dk, giay: float = 30.0, nhip: float = 0.05) -> bool:
    """Chờ MỘT ĐIỀU KIỆN THẬT, có biên — không ngủ một khoảng đoán trước.

    `time.monotonic` chứ không `time.time`: đồng hồ tường có thể bị NTP kéo
    lùi giữa chừng (hay gặp trên máy ảo CI vừa khởi động), và khi đó hạn chót
    lùi theo — vòng chờ dài ra hoặc kết thúc sớm mà không ai hiểu vì sao.
    """
    het = time.monotonic() + giay
    while time.monotonic() < het:
        if dk():
            return True
        time.sleep(nhip)
    return dk()


def _cho_con_duoc_giao(cc: ControlCenter, so: int, giay: float = 30.0) -> int:
    """`tick()` tới khi `so` việc con ĐÃ ĐƯỢC GIAO, trả về số đếm được.

    ĐẾM TÍCH LUỸ, không đếm tại một khoảnh khắc. `RUNNING` là trạng thái ĐI
    QUA: với một executor nhanh, một con có thể vào rồi ra khỏi `RUNNING`
    giữa hai nhịp, nên `len(tasks(RUNNING))` đo được bao nhiêu là chuyện của
    lịch CPU chứ không phải của hành vi.

    Đã vấp cả hai chiều, và đó là lý do hàm này đếm kiểu này:
      * một `tick()` rồi đọc ngay  -> CI thấy 1/4 (chưa kịp vào)
      * lặp `tick()` rồi đọc ngay  -> CI thấy 0/4 (đã kịp ra)

    Điều bài kiểm thật sự cần chứng minh là "cả 4 con ĐỀU được giao" — tức
    lệnh ghim provider không chặn con nào. Nên: gom ID của mọi con TỪNG rời
    khỏi hàng chờ, và dừng khi đủ.
    """
    da_giao: set[str] = set()

    def _du():
        cc.tick()
        for t in cc.store.tasks("demo"):
            if t.parent_id and t.state is not TaskState.WAITING:
                da_giao.add(t.task_id)
        return len(da_giao) >= so

    _cho(_du, giay=giay, nhip=0.02)
    return len(da_giao)


def _chay_toi_xong(cc: ControlCenter, cha_id: str, giay: float = 40.0) -> bool:
    """`tick()` liên tục tới khi cha kết thúc (mọi con đã gộp)."""
    def _xong():
        cc.tick()
        t = cc.store.task(cha_id)
        return t is not None and t.state in (TaskState.DONE, TaskState.FAILED)
    return _cho(_xong, giay=giay, nhip=0.1)


# ================================================================ xet_toa ===

class TestXetToa(unittest.TestCase):

    def test_cau_that_cua_nghiem_thu_tay(self):
        yc = TOA.xet_toa(CAU_8)
        self.assertIsNotNone(yc)
        self.assertEqual(yc.so_agent, 8)
        self.assertTrue(yc.moi_agent_mot)
        self.assertEqual(yc.model_hint, "gemini-3.8-flash-high")
        self.assertEqual(yc.provider_hint, "antigravity")

    def test_cac_dang_tuong_minh(self):
        cases = {
            "cho 4 agent mỗi đứa review một module": (4, True),
            "dùng 6 worker chạy song song test": (6, False),
            "tám agent đi tìm lỗi": (8, False),
            "spawn 3 agents, each agent one directory": (3, True),
            "Gọi 2 con gemini flash lục kho": (2, False),
        }
        for cau, (so, moi) in cases.items():
            with self.subTest(cau=cau):
                yc = TOA.xet_toa(cau)
                self.assertIsNotNone(yc, cau)
                self.assertEqual((yc.so_agent, yc.moi_agent_mot), (so, moi))

    def test_moi_agent_mot_voi_danh_sach_dem_duoc(self):
        yc = TOA.xet_toa("chia cho mỗi agent một dataset: web, server, docs")
        self.assertIsNotNone(yc)
        self.assertEqual(yc.so_agent, 3)
        self.assertEqual(yc.muc_liet_ke, ("web", "server", "docs"))

    def test_cau_mo_ho_KHONG_toa(self):
        for cau in ("review giúp tôi module web", "khảo sát toàn bộ kho CapCut-TTS-App",
                    "chạy MAX mode cho việc này", "làm nhanh lên, dùng chế độ STRONG",
                    "gọi 1 agent kiểm tra test", "mỗi đứa một việc",   # khong dem duoc
                    "gọi 99 agent", ""):
            with self.subTest(cau=cau):
                self.assertIsNone(TOA.xet_toa(cau), cau)

    def test_che_do_MAX_khong_phai_so_agent(self):
        yc = TOA.xet_toa("gọi 5 agent chế độ MAX")
        self.assertEqual(yc.so_agent, 5)                # MAX khong doi so agent
        self.assertIsNone(TOA.xet_toa("chế độ MAX cho việc này"))


class TestChiaConVaTongHop(unittest.TestCase):

    def test_moi_con_mot_phan_vung_khong_trung(self):
        yc = TOA.xet_toa(CAU_8)
        con = TOA.chia_con(yc, "Tìm bộ fanfic audio.", "tìm fanfic audio")
        self.assertEqual(len(con), 8)
        self.assertEqual({c.chi_so for c in con}, set(range(1, 9)))
        for c in con:
            self.assertIn(f"AGENT {c.chi_so}/8", c.muc_tieu)
            self.assertIn("KHÔNG TRÙNG", c.muc_tieu)
            self.assertIn(f"KẾT QUẢ [{c.chi_so}/8]", c.muc_tieu)
        self.assertEqual(len({c.phan_vung for c in con}), 8)

    def test_liet_ke_thi_moi_con_mot_muc(self):
        yc = TOA.xet_toa("chia cho mỗi agent một dataset: web, server, docs")
        con = TOA.chia_con(yc, "Kiểm dataset.", "kiểm dataset")
        self.assertEqual([c.phan_vung for c in con],
                         ["mục được giao riêng cho bạn: «web»",
                          "mục được giao riêng cho bạn: «server»",
                          "mục được giao riêng cho bạn: «docs»"])

    def test_tong_hop_khu_trung_giu_nguon_goc(self):
        cha = {"task_id": "demo.t1-cha", "title": "tìm fanfic audio"}
        def con(i, uv, st="DONE", rt="RT01"):
            return {"task_id": f"demo.t1-{i}", "state": st, "chi_so": i, "runtime": rt,
                    "owner_session": f"s{i}",
                    "result": {"envelope": {"summary": f"KẾT QUẢ [{i}/4]: {uv}\nvì …",
                                            "worker": rt, "model": "m-re", "duration": 1.0}}}
        th = TOA.tong_hop(cha, [con(1, "Bộ A"), con(2, "bộ  a"), con(3, "Bộ B", rt="RT02"),
                                {"task_id": "demo.t1-4", "state": "FAILED", "chi_so": 4,
                                 "result": {"envelope": {"failure_reason": "gia_lap_hong"}}}])
        self.assertEqual((th["so_con"], th["xong"], th["hong"]), (4, 3, 1))
        self.assertEqual([m["ung_vien"] for m in th["ung_vien"]], ["Bộ A", "Bộ B"])
        self.assertEqual(th["trung_da_bo"], 1)
        self.assertEqual(th["ung_vien"][0]["trung_voi"], ["demo.t1-2"])
        self.assertEqual(th["ung_vien"][1]["nguon"]["runtime"], "RT02")
        van = TOA.soan_tong_hop(th)
        self.assertIn("3/4", van)
        self.assertIn("Bộ A", van)
        self.assertIn("gia_lap_hong", van)

    def test_khong_co_khong_thanh_ung_vien(self):
        th = TOA.tong_hop({"task_id": "c", "title": "x"}, [
            {"task_id": "c-1", "state": "DONE", "chi_so": 1,
             "result": {"envelope": {"summary": "KẾT QUẢ [1/2]: KHÔNG CÓ"}}},
            {"task_id": "c-2", "state": "DONE", "chi_so": 2,
             "result": {"envelope": {"summary": "KẾT QUẢ [2/2]: Bộ C"}}}])
        self.assertEqual([m["ung_vien"] for m in th["ung_vien"]], ["Bộ C"])


class TestSucChua(unittest.TestCase):

    def test_dem_tu_fabric_va_tru_cho_leader(self):
        f = fabric_gia()                                  # 2 runtime x 2 khe
        yc = TOA.xet_toa(CAU_8)
        sc = TOA.tinh_suc_chua(f, yc, max_parallel=8)
        self.assertEqual((sc.khe_ranh, sc.tai_khoan_ranh, sc.chay_ngay, sc.cho), (4, 2, 4, 4))
        self.assertIn("không có trong fabric", " ".join(sc.ghi_chu))   # gemini-3.8 khong co
        self.assertEqual(sc.model, "")
        # Leader chiem 1 khe RT01 -> 3 khe, van 2 tai khoan.
        f.runtime("RT01").running_tasks.append("LEADER:demo")
        sc2 = TOA.tinh_suc_chua(f, yc, max_parallel=8)
        self.assertEqual((sc2.khe_ranh, sc2.tai_khoan_ranh, sc2.chay_ngay, sc2.cho), (3, 2, 3, 5))
        self.assertEqual(sc2.leader_chiem, ("RT01",))
        cau = TOA.cau_thong_bao(sc2, cha_id="demo.x-cha")
        self.assertIn("Đã tách thành 8 tác vụ", cau)
        self.assertIn("3/8 worker slots khả dụng; 3 chạy ngay, 5 chờ slot", cau)
        self.assertIn("Leader đang chiếm 1 chỗ ở RT01", cau)
        # Tran song song thap hon be -> gioi han boi tran, va noi ro.
        sc3 = TOA.tinh_suc_chua(fabric_gia(), yc, max_parallel=2)
        self.assertEqual((sc3.chay_ngay, sc3.cho, sc3.gioi_han_boi), (2, 6, "trần song song của Control Center"))
        sc4 = TOA.tinh_suc_chua(fabric_gia(), TOA.xet_toa("gọi 3 agent"), max_parallel=8)
        self.assertEqual(sc4.cho, 0)
        self.assertIn("dispatch 3 worker song song", TOA.cau_thong_bao(sc4))


# ============================================================== engine ======

class _Nen(unittest.TestCase):
    def setUp(self):
        self.repo = kho_git_tam()
        self.cc = None

    def tearDown(self):
        if self.cc is not None:
            # Cho luong `_chay` con bay ket thuc TRUOC khi xoa kho tam — khong
            # thi luong do mo so lease tren thu muc da mat.
            _cho(lambda: not any(x.is_alive() for x in list(self.cc._dang_chay.values())),
                 giay=15.0)
            try:
                self.cc.shutdown()
            except Exception:                               # noqa: BLE001
                pass
        shutil.rmtree(self.repo, ignore_errors=True)

    def _tasks(self):
        return {t.task_id: t for t in self.cc.store.tasks("demo")}

    def _cha_con(self):
        ts = self._tasks()
        cha = [t for t in ts.values() if ((t.contract or {}).get("_toa") or {}).get("cha")]
        con = [t for t in ts.values() if t.parent_id and t.parent_id in ts]
        return cha, con


class TestToaEngine(_Nen):

    def test_4_agent_thanh_cha_va_4_con_khong_viec_to(self):
        ex = ExecTuyBien()
        self.cc = _cc(self.repo, ex=ex, max_parallel=4)
        kq = self.cc.chat("demo", CAU_4)
        cha, con = self._cha_con()
        self.assertEqual(len(cha), 1)
        self.assertEqual(len(con), 4)
        self.assertEqual(len(self._tasks()), 5, "không có việc 'to' nào bên ngoài cha/con")
        self.assertEqual({((c.contract or {}).get("_toa") or {}).get("chi_so") for c in con}, {1, 2, 3, 4})
        self.assertTrue(all(c.parent_id == cha[0].task_id for c in con))
        self.assertTrue(all(not c.dependencies for c in con), "con không phụ thuộc nhau")
        self.assertEqual(cha[0].state, TaskState.WAITING)
        # Cau tra loi: dung so, dung suc chua (4 khe, tran 4 -> 4/4).
        self.assertIn("Đã tách thành 4 tác vụ độc lập", kq["reply"])
        self.assertIn("4/4 worker slots khả dụng", kq["reply"])
        self.assertEqual(kq["toa"]["suc_chua"]["chay_ngay"], 4)
        for c in con:
            self.assertIn("KHÔNG TRÙNG", c.objective)
            self.assertIn("fanfic audio", c.objective.lower())
            # Cau KHONG neu nha cung cap/model -> KHONG ghim gi (bo lap lich tu chon).
            self.assertIsNone(((c.contract or {}).get("requirements") or {}).get("pin_provider"))

    def test_neu_nguoi_dung_neu_model_thi_ghim_provider(self):
        self.cc = _cc(self.repo, ex=ExecTuyBien(), max_parallel=4)
        kq = self.cc.chat("demo", "gọi 4 agent gemini 3.8, mỗi đứa lục một bộ fanfic audio trong web")
        cha, con = self._cha_con()
        self.assertEqual(len(con), 4)
        for c in con:
            req = (c.contract or {}).get("requirements") or {}
            self.assertEqual(req.get("pin_provider"), "antigravity")
            self.assertIsNone(req.get("pin_model"), "model gợi ý không có trong fabric giả -> không ghim")
        self.assertIn("không có trong fabric", kq["reply"])
        # Va van giao duoc: provider antigravity co 4 khe trong fabric gia.
        # Chi dem CON: tu V0.6.1 cha cung RUNNING khi con dau tien duoc nhan.
        self.assertEqual(_cho_con_duoc_giao(self.cc, 4), 4,
                         "4 khe antigravity nhưng không đủ 4 con được giao")
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id))

    def test_giao_nhieu_tai_khoan_va_tong_hop(self):
        ex = ExecTuyBien(cham=0.4)
        self.cc = _cc(self.repo, ex=ex, max_parallel=4)
        self.cc.chat("demo", CAU_4)
        cha, con = self._cha_con()
        self.cc.tick()
        dang = [t for t in self.cc.store.tasks("demo", states=(TaskState.RUNNING,)) if t.parent_id]
        self.assertEqual(len(dang), 4, "4 khe, 4 con -> 4 chạy ngay")
        self.assertEqual(self.cc.store.task(cha[0].task_id).state, TaskState.RUNNING,
                         "cha RUNNING (bọc) trong khi con chạy")
        rts = {self.cc.store.session(t.owner_session).runtime_id for t in dang}
        self.assertEqual(rts, {"RT01", "RT02"}, "trải trên HAI tài khoản, mỗi cái 2 khe")
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id))
        cha_x = self.cc.store.task(cha[0].task_id)
        self.assertEqual(cha_x.state, TaskState.DONE)
        th = cha_x.result["toa"]
        self.assertEqual((th["so_con"], th["xong"], th["hong"]), (4, 4, 0))
        self.assertEqual(len(th["ung_vien"]), 4)
        for m in th["ung_vien"]:
            self.assertIn(m["nguon"]["runtime"], ("RT01", "RT02"))
            self.assertTrue(m["nguon"]["task_id"].startswith("demo."))
        self.assertEqual(sorted(ex.da_chay), sorted(c.task_id for c in con), "mỗi con đúng MỘT lượt")
        # Chat: MOT tin tong hop cua cha, khong rai 4 tin con. Tin duoc ghi NGAY
        # SAU khi cha sang DONE (trang thai truoc, tin sau) — cho no toi.
        def _kq():
            return [m for m in self.cc.store.chat("demo", limit=50)
                    if (m.meta or {}).get("loai") == "ket_qua"]
        self.assertTrue(_cho(lambda: len(_kq()) >= 1, giay=10))
        kq_msgs = _kq()
        self.assertEqual([m.meta.get("task_id") for m in kq_msgs], [cha[0].task_id])
        self.assertIn("🧩 Tổng hợp 4/4", kq_msgs[0].text)
        self.assertTrue(any(e["kind"] == "TOA_AGGREGATED"
                            for e in self.cc.store.su_kien(project_id="demo", limit=200)))

    def test_suc_chua_nho_hon_yeu_cau_thi_xep_hang_va_noi_that(self):
        ex = ExecTuyBien(cham=0.5)
        self.cc = _cc(self.repo, ex=ex, max_parallel=2)
        kq = self.cc.chat("demo", CAU_4)
        self.assertIn("2/4 worker slots khả dụng; 2 chạy ngay, 2 chờ slot", kq["reply"])
        self.assertIn("trần song song của Control Center", kq["reply"])
        cha, con = self._cha_con()
        self.cc.tick()
        st = {t.task_id: t.state for t in self.cc.store.tasks("demo") if t.parent_id}
        self.assertEqual(sorted(st.values(), key=lambda s: s.value),
                         sorted([TaskState.RUNNING, TaskState.RUNNING, TaskState.QUEUED,
                                 TaskState.QUEUED], key=lambda s: s.value))
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id))
        self.assertEqual(self.cc.store.task(cha[0].task_id).result["toa"]["xong"], 4)

    def test_leader_chiem_mot_khe_thi_bao_dung_va_khong_vuot(self):
        ex = ExecTuyBien(cham=0.5)
        self.cc = _cc(self.repo, ex=ex, max_parallel=8)
        from scripts.control_center import leader
        leader.chiem_cho_fabric(self.cc.fabric, "RT01", "LEADER:demo")
        kq = self.cc.chat("demo", CAU_4)
        self.assertIn("3/4 worker slots khả dụng; 3 chạy ngay, 1 chờ slot", kq["reply"])
        self.assertIn("Leader đang chiếm 1 chỗ ở RT01", kq["reply"])
        cha, con = self._cha_con()
        self.cc.tick()
        dang = [t for t in self.cc.store.tasks("demo", states=(TaskState.RUNNING,)) if t.parent_id]
        self.assertEqual(len(dang), 3)
        tren_rt01 = [t for t in dang if self.cc.store.session(t.owner_session).runtime_id == "RT01"]
        self.assertLessEqual(len(tren_rt01), 1, "RT01 còn đúng 1 khe cho worker")
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id))

    def test_mot_con_hong_khong_huy_anh_em(self):
        ex = ExecTuyBien(hong_neu=lambda tid: tid.endswith("-2"))
        self.cc = _cc(self.repo, ex=ex, max_parallel=4)
        self.cc.chat("demo", CAU_4)
        cha, con = self._cha_con()
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id, giay=60))
        cha_x = self.cc.store.task(cha[0].task_id)
        th = cha_x.result["toa"]
        self.assertEqual(cha_x.state, TaskState.DONE)
        self.assertEqual((th["xong"], th["hong"]), (3, 1))
        hong = [c for c in th["con"] if c["state"] == "FAILED"]
        self.assertEqual(len(hong), 1)
        self.assertTrue(hong[0]["task_id"].endswith("-2"))
        self.assertIn("gia_lap_hong", hong[0]["failure_reason"])
        # Anh em cua con hong deu DONE, khong ai bi BLOCKED/FAILED theo.
        for c in con:
            if not c.task_id.endswith("-2"):
                self.assertEqual(self.cc.store.task(c.task_id).state, TaskState.DONE)

    def test_khu_trung_ung_vien_giua_cac_con(self):
        ex = ExecTuyBien(tom_tat=lambda tid, p: "KẾT QUẢ [x/4]: Bộ FANFIC A"
                         if tid.endswith(("-1", "-2")) else f"KẾT QUẢ [x/4]: bộ {tid[-1]}")
        self.cc = _cc(self.repo, ex=ex, max_parallel=4)
        self.cc.chat("demo", CAU_4)
        cha, _ = self._cha_con()
        self.assertTrue(_chay_toi_xong(self.cc, cha[0].task_id))
        th = self.cc.store.task(cha[0].task_id).result["toa"]
        self.assertEqual(len(th["ung_vien"]), 3)
        self.assertEqual(th["trung_da_bo"], 1)

    def test_cau_mo_ho_khong_tu_sinh_8_agent(self):
        self.cc = _cc(self.repo, ex=ExecTuyBien(), max_parallel=4)
        kq = self.cc.chat("demo", "khảo sát toàn bộ kho này và cho tôi biết cấu trúc")
        cha, con = self._cha_con()
        self.assertEqual((len(cha), len(con)), (0, 0))
        self.assertIsNone(kq.get("toa"))
        self.assertGreaterEqual(len(self._tasks()), 1)

    def test_moi_agent_mot_muc_liet_ke(self):
        self.cc = _cc(self.repo, ex=ExecTuyBien(), max_parallel=4)
        self.cc.chat("demo", "chia cho mỗi agent một thư mục để đọc: web, server")
        cha, con = self._cha_con()
        self.assertEqual(len(con), 2)
        pv = sorted(((c.contract or {}).get("_toa") or {}).get("phan_vung") for c in con)
        self.assertEqual(pv, ["mục được giao riêng cho bạn: «server»",
                              "mục được giao riêng cho bạn: «web»"])

    def test_tran_song_song_tu_dong_theo_be(self):
        cc = ControlCenter(root=self.repo, fabric=fabric_gia(), probe=False, max_parallel=0,
                           executor_factory=lambda p, f: ExecTuyBien())
        self.cc = cc
        self.assertEqual(cc.max_parallel, 4)        # 2 runtime x 2 khe; san duoi 3
        cc2 = ControlCenter(root=self.repo, fabric=fabric_gia(), probe=False, max_parallel=2,
                            executor_factory=lambda p, f: ExecTuyBien())
        try:
            self.assertEqual(cc2.max_parallel, 2)    # cau hinh tuong minh thang
        finally:
            cc2.shutdown()


class TestUIToa(unittest.TestCase):
    """Giao diện: cha/con trong bảng việc; WebSocket theo dự án đang chọn."""

    def setUp(self):
        web = Path(__file__).resolve().parents[1] / "control_center" / "web"
        self.js = (web / "app.js").read_text(encoding="utf-8")

    def test_bang_viec_ve_cha_con(self):
        for can in ("viec-cha", "viec-con", "toaDem(", "function veToaChiTiet",
                    "↳ ", "parent_id"):
            self.assertIn(can, self.js, can)
        i = self.js.index("function veTasks()")
        than = self.js[i:i + 3000]
        self.assertIn("theoCha", than)
        self.assertIn("chi_so", than)

    def test_websocket_theo_du_an_dang_chon(self):
        """Lỗi thật nghiệm thu toả: WS mở một lần với dự án đầu, đổi dự án
        không mở lại -> Tasks/Agents đứng hình. Khoá lại ba điều: có biến theo
        dõi dự án của WS, chọn dự án thì nối lại, gói của dự án khác bị bỏ."""
        self.assertIn("let wsDuAn", self.js)
        i = self.js.index("if (t.dataset.pid) {")
        than = self.js[i:i + 600]
        self.assertIn("await lamMoi();", than)
        self.assertIn("if (wsDuAn !== S.selected) noiWs();", than)
        j = self.js.index("function noiWs()")
        ws = self.js[j:j + 1800]
        self.assertIn("goi.data.selected !== S.selected) return;", ws)
        self.assertIn("if (wsDangMo !== ws) return;", ws)
        self.assertIn("wsDuAn = S.selected;", ws)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Bể khoá KHE PHIÊN — luật 2 và luật 3 từng đọc cùng một phiên trái ngược nhau.

Khuyết tật đo được trên sổ chính tắc 2026-09-12, và nó là nguyên nhân THẬT
của những lượt trước đây bị quy cho "provider hỏng":

* Luật 2 từ chối dùng lại một phiên RẢNH (nguội quá ngưỡng, hoặc phạm vi ghi
  không chứa được phạm vi việc mới).
* Luật 3 vẫn ĐẾM đúng phiên đó vào `len(phien)`, chạm trần, rồi trả `WAIT` và
  *chờ* nó.
* Nhưng một phiên RẢNH không bao giờ "xong việc" để nhả khe — chỉ phiên BẬN
  mới làm được thế. Nên cái chờ đó là BẾ KHOÁ vĩnh viễn.

Hậu quả quan sát được: mỗi bước GHI có phạm vi riêng nên không bao giờ dùng
lại được phiên của bước khác; sau ~12 lượt thì chạm trần và MỌI lần giao việc
sau đó trả về ``WAIT: đã có 12/12 phiên sống``. Việc không bao giờ được giao,
tầng bước đọc ra "lượt trả về RỖNG", cạn bậc thang, kết thúc BLOCKED — trong
khi lần chạy đó KHÔNG HỀ gọi provider lần nào.
"""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from scripts.control_center.model import (Project, Session, SessionAction,
                                          SessionState, Task, TaskState)
from scripts.control_center.execution.ket_qua import HopDongKetQua
from scripts.control_center.execution.phuc_hoi import (HanhDongPhucHoi,
                                                       LoaiHong,
                                                       phan_loai_hong)
from scripts.control_center.sessions import (HAN_KHOI_DONG, NGUONG_NGUOI,
                                             SessionManager)
from scripts.control_center.store import ControlStore, duong_so
from scripts.control_center.worktrees import WorktreeCoordinator
from scripts.router_v4.contract import (Execution, Requirements, TaskContract)
from scripts.router_v4.runtime import (Fabric, ModelCapability, Reasoning,
                                       RuntimeStatus, Source, WorkerRuntime)
from scripts.router_v4.scheduler import Scheduler


def _hop_dong(scope, *, ghi=True) -> TaskContract:
    c = TaskContract(task_id="t-moi", objective="ghi mot tep",
                     requirements=Requirements(repo_read=True, repo_write=ghi),
                     execution=Execution(worktree_required=ghi),
                     allowed_scope=tuple(scope))
    c.validate()
    return c


def _fabric() -> Fabric:
    """Bể đủ rộng để `decide()` luôn có chỗ — bài kiểm này đo LUẬT KHE,
    không đo bộ lập lịch."""
    f = Fabric()
    caps = {"repo_read", "repo_write", "coding", "structured_output"}
    f.add_model(ModelCapability(
        model_id="m", model_family="gemini", provider="antigravity",
        capabilities=frozenset(caps),
        capability_source={c: Source.PROBED for c in caps},
        quota_pool="", reasoning=Reasoning.MEDIUM, benchmark_profile=0.8,
        latency_profile=30.0, cost_profile=0.5))
    for i in range(8):
        f.add_runtime(WorkerRuntime(
            runtime_id=f"AG0{i}", provider="antigravity",
            account_id=f"acct-{i}", auth_profile=f"profile:{i}",
            supported_models=("m",), concurrency=1,
            status=RuntimeStatus.IDLE))
    f.validate()
    return f


class TestKhePhien(unittest.TestCase):
    """Trần phiên không được biến thành bế khoá."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="khe-phien-"))
        self.store = ControlStore(duong_so(self.tmp))
        self.store.luu_project(Project(project_id="demo", name="demo",
                                       repo_path=str(self.tmp)))
        self.fabric = _fabric()
        self.wt = WorktreeCoordinator("demo", self.tmp, self.store)
        self.sm = SessionManager(
            "demo", self.store, fabric=self.fabric,
            scheduler=Scheduler(self.fabric), worktrees=self.wt,
            max_sessions=2)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- tien ich ----------------------------------------------------------
    def _phien(self, sid, *, state=SessionState.IDLE, scope=(), nguoi=0.0,
               viec="", pid=4242):
        s = Session(session_id=sid, project_id="demo", provider="antigravity",
                    runtime_id=f"AG{sid[-2:]}", model_id="m", state=state,
                    scope=tuple(scope), current_task=viec, pid=pid,
                    worktree=str(self.tmp / sid))
        self.store.luu_session(s)
        # `luu_session()` DẤU thời gian bằng `time.time()`, nên phải đặt tuổi
        # phiên SAU khi lưu — không thì mọi phiên đều "vừa hoạt động" và bài
        # kiểm tuổi tác lặng lẽ mất hiệu lực.
        if nguoi:
            self.store.ket_noi().execute(
                "UPDATE sessions SET last_activity=? WHERE session_id=?",
                (time.time() - nguoi, sid))
        return self.store.session(sid)

    def _viec(self):
        t = Task(task_id="t-moi", project_id="demo", title="ghi mot tep",
                 objective="ghi mot tep", state=TaskState.QUEUED)
        self.store.luu_task(t)
        return t

    def _song(self):
        return [s.session_id for s in
                self.store.sessions("demo", alive_only=True)]

    # -- bai kiem ----------------------------------------------------------
    def test_01_ranh_khong_tuong_thich_thi_thu_hoi_chu_khong_cho(self):
        """Chạm trần + mọi phiên RẢNH đều bị luật 2 từ chối -> KHÔNG được WAIT.

        Đây chính là hình dạng đã bế khoá lần chạy thật: hai bước ghi, hai
        phạm vi khác nhau, không bước nào dùng lại được phiên của bước kia.
        """
        self._phien("s-01", scope=("docs/a.md",))
        self._phien("s-02", scope=("docs/b.md",))
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIsNot(qd.action, SessionAction.WAIT,
                         f"vẫn bế khoá: {qd.reason}\n" + "\n".join(qd.trace))
        # Dung mot khe, va dung DUNG mot khe.
        self.assertEqual(len(self._song()), 1, self._song())

    def test_02_phien_ban_thi_VAN_cho(self):
        """Phiên BẬN thật sự sẽ tự nhả khe — chờ nó là đúng, không được giết."""
        self._phien("s-01", state=SessionState.BUSY, scope=("docs/a.md",),
                    viec="t-dang-chay")
        self._phien("s-02", state=SessionState.BUSY, scope=("docs/b.md",),
                    viec="t-dang-chay-2")
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIs(qd.action, SessionAction.WAIT)
        self.assertEqual(len(self._song()), 2,
                         "không được dừng một phiên đang chạy việc")

    def test_03_khong_thu_hoi_phien_giu_viec_con_SONG(self):
        """Việc RUNNING = có agent đang ghi. Thu hồi phiên là cắt nó giữa chừng."""
        for ma in ("t-dang-chay", "t-dang-chay-2"):
            self.store.luu_task(Task(task_id=ma, project_id="demo", title=ma,
                                     objective=ma, state=TaskState.RUNNING))
        self._phien("s-01", scope=("docs/a.md",), viec="t-dang-chay")
        self._phien("s-02", scope=("docs/b.md",), viec="t-dang-chay-2")
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIs(qd.action, SessionAction.WAIT)
        self.assertEqual(len(self._song()), 2)

    def test_03b_phien_XAC_giu_nhan_viec_da_CHET_thi_van_thu_hoi(self):
        """Đo được trên sổ thật: ba phiên IDLE nguội >4 tiếng vẫn mang
        `current_task` trỏ tới việc đã FAILED. Tin vào một mình cái nhãn đó
        thì ba khe bị giữ vĩnh viễn."""
        for ma, tt in (("t-xong", TaskState.DONE), ("t-hong", TaskState.FAILED)):
            self.store.luu_task(Task(task_id=ma, project_id="demo", title=ma,
                                     objective=ma, state=tt))
        self._phien("s-01", scope=("docs/a.md",), viec="t-xong",
                    nguoi=NGUONG_NGUOI + 9000)
        self._phien("s-02", scope=("docs/b.md",), viec="t-hong",
                    nguoi=NGUONG_NGUOI + 9000)
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIsNot(qd.action, SessionAction.WAIT,
                         f"phiên xác vẫn giữ khe: {qd.reason}")
        self.assertEqual(len(self._song()), 1)

    def test_03c_viec_khong_tra_cuu_duoc_thi_FAIL_CLOSED(self):
        """Không biết việc còn sống không -> coi như còn. Thà chờ hơn cắt nhầm."""
        def _no(_ma):
            raise RuntimeError("sổ hỏng")
        self.sm.store = type("S", (), {
            "task": staticmethod(_no),
            "sessions": self.store.sessions,
            "session": self.store.session,
            "luu_session": self.store.luu_session,
            "ghi_su_kien": self.store.ghi_su_kien})()
        self._phien("s-01", scope=("docs/a.md",), viec="t-?",
                    nguoi=NGUONG_NGUOI + 60)
        self._phien("s-02", scope=("docs/b.md",), viec="t-?",
                    nguoi=NGUONG_NGUOI + 60)
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIs(qd.action, SessionAction.WAIT)

    def test_03d_STARTING_ro_qua_han_bi_thu_hoi_GIUA_lan_chay(self):
        """8 phiên `STARTING` rò trong MỘT lần chạy thật đã bóp cổ nó.

        `recover()` có dọn loại này nhưng chỉ chạy lúc khởi động — vô dụng
        đúng lúc cần, tức giữa một lần chạy dài.
        """
        self._phien("s-01", state=SessionState.STARTING, pid=None,
                    scope=("docs/a.md",), nguoi=HAN_KHOI_DONG + 60)
        self._phien("s-02", state=SessionState.STARTING, pid=None,
                    scope=("docs/b.md",), nguoi=HAN_KHOI_DONG + 30)
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIsNot(qd.action, SessionAction.WAIT, qd.reason)
        self.assertIs(self.store.session("s-01").state, SessionState.DEAD,
                      "phiên kẹt STARTING phải là DEAD, không phải STOPPED")

    def test_03e_STARTING_con_PID_thi_KHONG_bi_dung(self):
        """Có PID = có thể là adapter nhiều khe đang chạy thật. Không kết luận."""
        self._phien("s-01", state=SessionState.STARTING,
                    scope=("docs/a.md",), nguoi=HAN_KHOI_DONG + 60)
        self._phien("s-02", state=SessionState.STARTING,
                    scope=("docs/b.md",), nguoi=HAN_KHOI_DONG + 60)
        qd = self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertIs(qd.action, SessionAction.WAIT)
        self.assertEqual(len(self._song()), 2)

    def test_04_nguoi_bi_thu_hoi_truoc_am(self):
        """Nguội = chắc chắn vô dụng. Ấm = chỉ không hợp việc NÀY. Bỏ nguội."""
        self._phien("s-01", scope=("docs/a.md",), nguoi=NGUONG_NGUOI + 60)
        self._phien("s-02", scope=("docs/b.md",), nguoi=5)
        self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertEqual(self._song(), ["s-02"],
                         "phải bỏ phiên NGUỘI trước, giữ phiên còn ấm")

    def test_05_thu_hoi_danh_dau_STOPPED_va_khong_xoa_worktree(self):
        """Luật của gói: không tự xoá worktree, chỉ đánh dấu."""
        d = self.tmp / "s-01"
        d.mkdir(parents=True, exist_ok=True)
        (d / "dau_vet.txt").write_text("con day", encoding="utf-8")
        self._phien("s-01", scope=("docs/a.md",), nguoi=NGUONG_NGUOI + 60)
        self._phien("s-02", scope=("docs/b.md",), nguoi=NGUONG_NGUOI + 30)
        self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        s = self.store.session("s-01")
        self.assertIs(s.state, SessionState.STOPPED)
        self.assertTrue(d.is_dir() and (d / "dau_vet.txt").is_file(),
                        "worktree bị xoá — vi phạm luật 'chỉ đánh dấu'")

    def test_06_chi_thu_hoi_du_so_khe_can_thiet(self):
        """Không dọn sạch bể: nhả đủ một khe rồi dừng."""
        self.sm.max_sessions = 4
        for i in range(4):
            self._phien(f"s-0{i}", scope=(f"docs/{i}.md",),
                        nguoi=NGUONG_NGUOI + 60)
        self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertEqual(len(self._song()), 3,
                         "chỉ được thu hồi vừa đủ một khe")

    def test_07_viec_chi_doc_van_dung_lai_duoc_phien_ranh(self):
        """Không được phá luật 2: việc CHỈ ĐỌC dùng lại mọi phiên rảnh còn ấm."""
        self._phien("s-01", scope=("docs/a.md",), nguoi=5)
        self._phien("s-02", scope=("docs/b.md",), nguoi=5)
        qd = self.sm.decide(self._viec(), _hop_dong((), ghi=False))
        self.assertIs(qd.action, SessionAction.REUSE)
        self.assertEqual(len(self._song()), 2, "không được thu hồi gì")

    def test_08_khong_cham_tran_thi_khong_thu_hoi_gi(self):
        """Luật 2b chỉ chạy khi thật sự chạm trần."""
        self.sm.max_sessions = 5
        self._phien("s-01", scope=("docs/a.md",), nguoi=NGUONG_NGUOI + 60)
        self.sm.decide(self._viec(), _hop_dong(("docs/c.md",)))
        self.assertEqual(len(self._song()), 1,
                         "còn khe trống mà vẫn dừng phiên là lãng phí")


class TestChuaGiaoKhacProviderHong(unittest.TestCase):
    """"Chưa hề chạy" phải khác ""chạy rồi và trả rỗng"".

    Gộp hai thứ này lại đã làm cả một vòng chẩn đoán đi sai hướng: báo cáo
    kết luận "provider hỏng" cho một lần chạy KHÔNG gọi provider lần nào.
    """

    def _kq(self, **kw) -> HopDongKetQua:
        d = {"task_id": "t-1", "buoc_id": "b1", "status": "failed"}
        d.update(kw)
        return HopDongKetQua(**d)

    def test_09_khong_dau_vet_dinh_tuyen_thi_la_CHUA_GIAO(self):
        cd = phan_loai_hong(ket_qua=self._kq())
        self.assertIs(cd.loai, LoaiHong.CHUA_GIAO)
        self.assertIs(cd.hanh_dong, HanhDongPhucHoi.THU_LAI)
        self.assertNotIn("provider", cd.ly_do.lower(),
                         "không được đổ lỗi cho nhà cung cấp chưa hề được gọi")

    def test_10_co_dau_vet_dinh_tuyen_thi_VAN_la_PROVIDER(self):
        """Một lượt THẬT trả về rỗng vẫn phải là PROVIDER — không nới lỏng."""
        cd = phan_loai_hong(ket_qua=self._kq(
            provider="antigravity", model="m", runtime_id="AG05",
            duration=12.5))
        self.assertIs(cd.loai, LoaiHong.PROVIDER)

    def test_11_mot_minh_duration_cung_du_de_KHONG_phai_CHUA_GIAO(self):
        cd = phan_loai_hong(ket_qua=self._kq(duration=0.4))
        self.assertIsNot(cd.loai, LoaiHong.CHUA_GIAO)

    def test_12_ma_thoat_0_van_la_mot_luot_that(self):
        """`exit_code=0` nghĩa là một tiến trình ĐÃ chạy và đã thoát."""
        self.assertFalse(self._kq(exit_code=0).chua_chay)

    def test_13_CHUA_GIAO_khong_bao_gio_dinh_tuyen_lai(self):
        """Đổi nhà cung cấp không tạo thêm khe — đó là mua một vé số khác."""
        cd = phan_loai_hong(ket_qua=self._kq())
        self.assertIsNot(cd.hanh_dong, HanhDongPhucHoi.DINH_TUYEN_LAI)

    def test_14_co_noi_dung_thi_khong_phai_chua_chay(self):
        self.assertFalse(self._kq(summary="đã làm xong").chua_chay)
        self.assertFalse(self._kq(files_changed=("a.md",)).chua_chay)

    def test_15_phu_thuoc_hong_van_thang_CHUA_GIAO(self):
        """Bước phụ thuộc hỏng thì thử lại bước này là tốn lượt cho không."""
        cd = phan_loai_hong(ket_qua=self._kq(), phu_thuoc_hong=True)
        self.assertIs(cd.loai, LoaiHong.PHU_THUOC)


if __name__ == "__main__":
    unittest.main()

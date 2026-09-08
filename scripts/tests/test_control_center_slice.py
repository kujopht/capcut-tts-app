"""LÁT CẮT DỌC của Control Center V0.1 — bài kiểm quan trọng nhất của bản này.

Chứng minh đúng chuỗi đề bài đòi, đầu tới cuối, trên một KHO GIT THẬT:

    ô chat -> tạo việc -> quyết định định tuyến -> tạo/dùng lại worktree cô
    lập -> dựng phiên agent được quản lý -> chạy -> phát sự kiện/log -> ghi
    sổ việc+phiên -> Pause/Stop -> SỐNG SÓT qua khởi động lại Control Center

KHÔNG GỌI AGENT THẬT. Tiến trình `agy`/`codex` được thay bằng một
`FakeExecutor` **có ghi tệp thật vào worktree thật**. Đó là ranh giới đúng:

  - Mọi thứ ở phía Control Center — sổ, khoá, phiên, worktree, trạng thái,
    phục hồi — chạy y hệt bản thật, và bài kiểm ép được chúng.
  - Chỉ tiến trình mô hình ngôn ngữ bị thay. Nó vốn không tất định, chậm,
    và tốn quota; ép nó vào một bài kiểm là biến bài kiểm thành một thứ
    không ai dám chạy.

Bằng chứng chạy với agent THẬT nằm ở `scripts/control_center_real_proof.py`
và báo cáo của nó — hai thứ khác nhau, và cả hai đều cần.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.router_v3.pool import validation as V
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.envelope import ResultEnvelope
from scripts.router_v4.executor import ExecutionResult
from scripts.router_v4.runtime import (Fabric, ModelCapability, Placement,
                                       QuotaPool, RuntimeStatus, Source,
                                       WorkerRuntime)
from scripts.control_center.bootstrap import khoi_tao
from scripts.control_center.engine import MAX_ATTEMPTS, ControlCenter
from scripts.control_center.model import (LockKind, Project, SessionState,
                                          TaskState, TransitionError)
from scripts.control_center.store import ControlStore


# ---------------------------------------------------------------------------
# Do gia
# ---------------------------------------------------------------------------

def kho_git_tam() -> Path:
    """Một kho git THẬT — `git worktree add` không chạy trên thư mục trần."""
    goc = Path(tempfile.mkdtemp(prefix="cc-repo-"))
    def g(*a: str) -> None:
        p = subprocess.run(["git", "-C", str(goc), *a], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            raise RuntimeError(f"git {a[0]} hỏng: {p.stderr[:300]}")
    g("init", "-q", "-b", "main")
    g("config", "user.email", "test@example.invalid")
    g("config", "user.name", "cc-test")
    g("config", "commit.gpgsign", "false")
    (goc / "web").mkdir()
    (goc / "web" / "index.txt").write_text("xin chào\n", encoding="utf-8")
    (goc / "server").mkdir()
    (goc / "server" / "api.txt").write_text("api\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "khởi tạo")
    return goc


def fabric_gia() -> Fabric:
    """Fabric hai runtime, ba model. Không chạm mạng, không đọc cấu hình.

    Cố ý KHÔNG gõ vai trò vào tên: bộ lập lịch phải chọn theo NĂNG LỰC, và
    một fabric giả có "AG_CODER"/"AG_REVIEWER" sẽ khiến bài kiểm xanh trong
    khi luật kiến trúc trung tâm của V4 đã bị phá.
    """
    f = Fabric()
    f.pool_groups.add("pool_a")
    for tk in ("acct-1", "acct-2"):
        f.add_pool(QuotaPool(pool_id=f"{tk}:pool_a", account_id=tk,
                             member_models=frozenset({"m-manh", "m-re"}),
                             remaining_estimate=0.8, source=Source.DECLARED))
    f.add_model(ModelCapability(
        model_id="m-manh", model_family="ho-x", provider="antigravity",
        capabilities=frozenset({"coding", "repo_read", "repo_write",
                                "structured_output", "long_context"}),
        quota_pool="pool_a", benchmark_profile=0.8, latency_profile=20.0))
    f.add_model(ModelCapability(
        model_id="m-re", model_family="ho-y", provider="antigravity",
        capabilities=frozenset({"coding", "repo_read", "repo_write",
                                "structured_output"}),
        quota_pool="pool_a", benchmark_profile=0.5, latency_profile=8.0))
    for i, tk in enumerate(("acct-1", "acct-2"), start=1):
        f.add_runtime(WorkerRuntime(
            runtime_id=f"RT{i:02d}", provider="antigravity", account_id=tk,
            auth_profile=f"gia:{tk}", supported_models=("m-manh", "m-re"),
            concurrency=2, status=RuntimeStatus.IDLE))
    f.validate()
    return f


class FakeExecutor:
    """Đứng thay `router_v4.Executor`. GHI TỆP THẬT vào worktree thật.

    Ghi thật chứ không giả vờ, vì đúng thứ bài kiểm cần chứng minh là
    worktree được tạo, được trỏ đúng chỗ, và ghi được. Một executor chỉ trả
    về `status="ok"` sẽ xanh ngay cả khi worktree chưa từng tồn tại.
    """

    def __init__(self, *, status: str = "ok", cham: float = 0.0,
                 ghi: str = "ket-qua.txt"):
        self.status = status
        self.cham = cham
        self.ghi = ghi
        self._cache: Dict[str, object] = {}
        self.worktree_provider = None
        self.da_chay: List[str] = []

    def run(self, c: TaskContract, p: Placement, *, base_sha: str = "",
            dependency_summaries=None, dependency_workspaces=None,
            attempt: int = 1, reassigned: bool = False) -> ExecutionResult:
        self.da_chay.append(c.task_id)
        if self.cham:
            time.sleep(self.cham)
        h = None
        duong = ""
        if c.execution.worktree_required and self.worktree_provider is not None:
            h = self.worktree_provider(c, p, base_sha, attempt)
        if h is not None:
            duong = str(h.path)
            # GHI THAT, va ghi TRONG pham vi cho phep — mot bai kiem ghi ra
            # ngoai pham vi se lam cong `contract_scope` bao dong dung.
            goc = Path(duong)
            pv = c.allowed_scope[0] if c.allowed_scope else ""
            tep = (goc / pv / self.ghi) if pv else (goc / self.ghi)
            tep.parent.mkdir(parents=True, exist_ok=True)
            tep.write_text(f"{c.task_id} đã chạy trên {p.key}\n",
                           encoding="utf-8")
        pb = ResultEnvelope(
            task_id=c.task_id, status=self.status,
            summary=f"fake worker chạy {c.task_id} trên {p.key}",
            worker=p.runtime_id, model=p.model_id, provider="antigravity",
            duration=0.01, changes=[self.ghi] if h is not None else [],
            failure_reason="" if self.status == "ok" else "gia_lap_hong")
        return ExecutionResult(envelope=pb, validation=None, worktree=duong,
                               branch=h.branch if h is not None else "")

    def shutdown(self) -> None:
        pass


def _cc(repo: Path, *, ex: Optional[FakeExecutor] = None,
        root: Optional[Path] = None, max_parallel: int = 3) -> ControlCenter:
    goc = root or repo
    cc = ControlCenter(root=goc, fabric=fabric_gia(), probe=False,
                       max_parallel=max_parallel,
                       executor_factory=lambda p, f: (ex or FakeExecutor()))
    cc.them_project(Project(
        project_id="demo", name="Demo", repo_path=str(repo),
        resources=("write:web", "prod:fanfic.world", "tts-worker-queue")))
    return cc


def _cho(dieu_kien, *, giay: float = 20.0, nhip: float = 0.05) -> bool:
    het = time.time() + giay
    while time.time() < het:
        if dieu_kien():
            return True
        time.sleep(nhip)
    return False


def _xong(cc: ControlCenter, *task_ids: str, giay: float = 20.0) -> bool:
    """Chờ việc XONG HẲN — trạng thái cuối VÀ đã ra khỏi `in_flight`.

    Chỉ chờ trạng thái cuối là một cuộc đua trong chính bài kiểm: `_chay`
    ghi trạng thái cuối TRƯỚC, rồi mới nhả lease/khoá và rời `in_flight`
    trong `finally`. Bài kiểm nào kiểm khoá ngay sau khi thấy `DONE` sẽ hỏng
    ngẫu nhiên vài lần trong một trăm lần chạy — loại hỏng tệ nhất.
    """
    def _du() -> bool:
        with cc._khoa:
            bay = set(cc._dang_chay)
        return all(cc.store.task(x).state.terminal and x not in bay
                   for x in task_ids)
    return _cho(_du, giay=giay)


def _can_luot(cc: ControlCenter, task_id: str, *,
              giay: float = 60.0) -> bool:
    """Đạp nhịp tới khi một việc HỎNG HẲN — đã cạn lượt thử tự động.

    Việc hỏng nay được thử lại có trần, nên một `tick()` chỉ cho ra `QUEUED`
    chứ chưa phải trạng thái cuối. Bài kiểm nào muốn thấy trạng thái cuối
    phải chạy tới khi hết lượt.

    PHẢI kiểm cả ba điều CÙNG LÚC, không phải lần lượt: `FAILED` **và** đã
    rời `in_flight` **và** đã cạn lượt. Giữa lúc `_chay` ghi `FAILED` và lúc
    nó requeue có một khe hở mà việc TRÔNG như đã hỏng hẳn; bản đầu tiên của
    hàm này rơi đúng vào đó rồi bỏ cuộc.
    """
    het = time.time() + giay
    while time.time() < het:
        t = cc.store.task(task_id)
        with cc._khoa:
            bay = task_id in cc._dang_chay
        if (t is not None and t.state is TaskState.FAILED and not bay
                and t.attempts >= MAX_ATTEMPTS):
            return True
        cc.tick()
        time.sleep(0.1)
    return False


def _chay_het(cc: ControlCenter, *task_ids: str, giay: float = 30.0) -> bool:
    """Đạp nhịp điều phối tới khi mọi việc xong. Thay cho vòng lặp nền.

    Bài kiểm gọi `tick()` tay thay vì `start()` có chủ đích: một vòng lặp
    nền làm bài kiểm phụ thuộc thời gian thực và hỏng vặt trên máy chậm.
    Ở đây nhịp là tường minh, nên hỏng là hỏng thật.
    """
    het = time.time() + giay
    while time.time() < het:
        if _xong(cc, *task_ids, giay=0.01):
            return True
        cc.tick()
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Lat cat doc
# ---------------------------------------------------------------------------

class TestVerticalSlice(unittest.TestCase):

    def setUp(self):
        self.repo = kho_git_tam()
        self.ex = FakeExecutor()
        self.cc = _cc(self.repo, ex=self.ex)

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                 # noqa: BLE001
            pass

    # -- 1. chat -> viec ----------------------------------------------------

    def test_chat_tao_viec_duoc_quan_ly(self):
        kq = self.cc.chat(
            "demo",
            "finish the production web and separately investigate AWS cleanup")
        self.assertEqual(len(kq["tasks"]), 2)
        ts = self.cc.store.tasks("demo")
        self.assertEqual(len(ts), 2)
        self.assertTrue(all(t.state is TaskState.QUEUED for t in ts))
        self.assertIn("Đã tách thành 2 việc", kq["reply"])

    def test_chat_duoc_ghi_lai_ca_hai_chieu(self):
        self.cc.chat("demo", "fix web/admin")
        tin = self.cc.store.chat("demo")
        self.assertEqual([m.role for m in tin], ["user", "router"])

    def test_viec_GATED_vao_BLOCKED_chu_KHONG_vao_hang_doi(self):
        """Việc chạm cổng KHÔNG được nằm ở `QUEUED`.

        Cho nó vào hàng đợi rồi chặn ở bước sau nghĩa là chỉ cần MỘT lỗi
        lập lịch là nó chạy. Chặn ngay từ lúc tạo thì không có bước sau nào
        để lỗi.
        """
        self.cc.chat("demo", "deploy the web to production")
        t = self.cc.store.tasks("demo")[0]
        self.assertIs(t.state, TaskState.BLOCKED)
        self.assertEqual(t.permission, "GATED")
        self.assertIn("production_deploy", t.blocked_reason)

        kq = self.cc.tick()
        self.assertEqual(kq["dispatched"], [],
                         "việc GATED không bao giờ được tự giao")

    def test_pause_roi_resume_KHONG_mo_duoc_cong_an_toan(self):
        """LỖI THẬT đã tồn tại và chạy được trước bản này.

            pause(việc GATED)   BLOCKED -> PAUSED   (hợp lệ)
            resume(việc đó)     PAUSED  -> QUEUED   (hợp lệ)
            -> tick() giao việc, agent chạy, KHÔNG một lần duyệt nào

        Hai bước hợp lệ nối lại thành một đường vòng đầy đủ quanh cổng an
        toàn quan trọng nhất của hệ thống.
        """
        self.cc.chat("demo", "deploy the web to production")
        t = self.cc.store.tasks("demo")[0]
        self.assertIs(t.state, TaskState.BLOCKED)

        self.cc.pause(t.task_id)
        self.cc.resume(t.task_id)
        self.assertIs(self.cc.store.task(t.task_id).state, TaskState.BLOCKED,
                      "`resume` KHÔNG phải một cách duyệt cổng")
        self.assertEqual(self.cc.tick()["dispatched"], [])
        self.assertEqual(self.cc.store.task(t.task_id).attempts, 0)

    def test_viec_GATED_lot_vao_hang_doi_van_bi_CHAN_o_bo_lap_lich(self):
        """Lưới cuối: dù đường nào đưa nó về QUEUED, nó vẫn không chạy.

        Sửa riêng `resume()` là bịt đúng một lỗ và để ngỏ mọi lỗ chưa nghĩ
        ra. Bài kiểm này ép việc GATED vào thẳng `QUEUED` — mô phỏng một
        đường vòng TƯƠNG LAI — và đòi bộ lập lịch vẫn phải chặn.
        """
        self.cc.chat("demo", "deploy the web to production")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.doi_trang_thai(tid, TaskState.QUEUED, force=True)

        self.assertEqual(self.cc.tick()["dispatched"], [])
        t = self.cc.store.task(tid)
        self.assertIs(t.state, TaskState.BLOCKED)
        self.assertEqual(t.attempts, 0)
        self.assertTrue([e for e in self.cc.store.su_kien(task_id=tid)
                         if e["kind"] == "GATE_REASSERTED"])

    def test_sau_khi_DUYET_thi_viec_GATED_chay_binh_thuong(self):
        """Cổng chặn chứ không phải khoá chết: duyệt xong là chạy."""
        self.cc.chat("demo", "deploy the web to production")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.mo_khoa_gated(tid, approved_by="nam")
        self.assertEqual(self.cc.tick()["dispatched"], [tid])
        _xong(self.cc, tid)
        self.assertIs(self.cc.store.task(tid).state, TaskState.DONE)

    def test_dau_duyet_nam_TREN_VIEC_va_ben_qua_khoi_dong_lai(self):
        """Dấu duyệt phải kiểm được lúc lập lịch, không chỉ đọc lại được
        trong nhật ký — và phải sống sót qua khởi động lại."""
        self.cc.chat("demo", "deploy the web to production")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.mo_khoa_gated(tid, approved_by="nam", note="đã xem")
        pq = (self.cc.store.task(tid).contract or {}).get("_permission") or {}
        self.assertEqual(pq.get("approved_by"), "nam")

        moi = ControlCenter(root=self.repo, fabric=fabric_gia(), probe=False,
                            executor_factory=lambda p, f: FakeExecutor())
        try:
            self.assertTrue(moi._da_duyet_cong(moi.store.task(tid)))
        finally:
            moi.shutdown()

    def test_mo_khoa_gated_can_nguoi_va_de_lai_dau_vet(self):
        self.cc.chat("demo", "deploy the web to production")
        tid = self.cc.store.tasks("demo")[0].task_id
        t = self.cc.mo_khoa_gated(tid, approved_by="nam", note="đã xem xong")
        self.assertIs(t.state, TaskState.QUEUED)
        sk = [e for e in self.cc.store.su_kien(task_id=tid)
              if e["kind"] == "GATE_APPROVED"]
        self.assertEqual(len(sk), 1)
        self.assertEqual(sk[0]["level"], "ALERT")
        self.assertEqual(sk[0]["meta"]["approved_by"], "nam")

    # -- 2. tick -> phien + worktree + chay ---------------------------------

    def test_lat_cat_day_du_mot_viec(self):
        """chat -> tick -> phiên -> worktree -> chạy -> DONE, có bằng chứng."""
        self.cc.chat("demo", "fix the styling in web/admin")
        t0 = self.cc.store.tasks("demo")[0]

        kq = self.cc.tick()
        self.assertEqual(kq["dispatched"], [t0.task_id], kq)

        self.assertTrue(_xong(self.cc, t0.task_id),
                        f"việc không xong: {self.cc.store.task(t0.task_id).state}")
        self.assertIs(self.cc.store.task(t0.task_id).state, TaskState.DONE)

        t = self.cc.store.task(t0.task_id)
        # (a) phien duoc dung va duoc ghi so
        self.assertTrue(t.owner_session)
        s = self.cc.store.session(t.owner_session)
        self.assertIsNotNone(s)
        self.assertIs(s.state, SessionState.IDLE, "phiên giữ ấm sau khi xong")
        self.assertEqual(s.task_count, 1)
        # (b) worktree CO LAP that, khong phai kho goc
        self.assertTrue(t.worktree)
        self.assertNotEqual(Path(t.worktree).resolve(), self.repo.resolve())
        self.assertTrue(Path(t.worktree).exists())
        # (c) nhanh rieng
        self.assertTrue(t.branch.startswith("router/"))
        # (d) agent GHI THAT vao worktree, DUNG trong pham vi cho phep
        pv = TaskContract.from_dict(t.contract).allowed_scope[0]
        tep = Path(t.worktree) / pv / "ket-qua.txt"
        self.assertTrue(tep.exists(), f"không thấy {tep}")
        # (e) kho GOC khong he bi dung toi
        self.assertFalse((self.repo / pv / "ket-qua.txt").exists(),
                         "worktree cô lập KHÔNG được rò ra kho gốc")

    def test_su_kien_va_log_duoc_phat_ra(self):
        self.cc.chat("demo", "fix the styling in web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)

        loai = {e["kind"] for e in self.cc.store.su_kien(task_id=tid)}
        for can in ("TASK_CREATED", "SESSION_DECISION", "WORKTREE_CREATED",
                    "TASK_CLAIMED", "TASK_STARTED", "TASK_FINISHED"):
            self.assertIn(can, loai, f"thiếu sự kiện {can}")

        log = self.cc.log_cua_viec(tid)
        self.assertIn(tid, log)
        self.assertIn("SỰ KIỆN", log)

    def test_quyet_dinh_dinh_tuyen_GIAI_THICH_DUOC(self):
        self.cc.chat("demo", "fix the styling in web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        e = [x for x in self.cc.store.su_kien(task_id=tid)
             if x["kind"] == "SESSION_DECISION"][0]
        self.assertIn(e["meta"]["action"], ("CREATE", "REUSE"))
        self.assertTrue(e["meta"]["reason"])
        self.assertTrue(e["meta"]["trace"], "phải ghi lại các luật đã xét")
        self.assertTrue(e["meta"]["routing"]["selected"])

    # -- 3. DUNG LAI phien --------------------------------------------------

    def test_viec_thu_hai_cung_pham_vi_DUNG_LAI_phien(self):
        """Cùng phạm vi + phiên khoẻ -> REUSE, không đẻ tiến trình thứ hai."""
        self.cc.chat("demo", "fix the styling in web/admin")
        t1 = self.cc.store.tasks("demo")[0]
        self.cc.tick()
        self.assertTrue(_xong(self.cc, t1.task_id))

        self.cc.chat("demo", "update the spacing in web/admin")
        t2 = [t for t in self.cc.store.tasks("demo")
              if t.task_id != t1.task_id][0]
        kq = self.cc.tick()
        self.assertEqual(kq["dispatched"], [t2.task_id], kq)

        self.assertTrue(_xong(self.cc, t2.task_id))
        s1 = self.cc.store.task(t1.task_id).owner_session
        s2 = self.cc.store.task(t2.task_id).owner_session
        self.assertEqual(s1, s2, "việc tương thích phải DÙNG LẠI phiên")
        self.assertEqual(len(self.cc.store.sessions("demo")), 1)

    def test_dung_lai_phien_thi_dung_lai_ca_worktree(self):
        # CA HAI viec phai la viec CO GHI that. Ban dau cau thu hai dung
        # dong tu "adjust" — bo phan loai khong biet no, nen viec roi ve
        # CHI DOC va bai kiem xanh VI MOT LY DO SAI: no chi dang do lai
        # `s.worktree` ma viec chi doc thua huong tu phien.

        self.cc.chat("demo", "fix the styling in web/admin")
        t1 = self.cc.store.tasks("demo")[0]
        self.cc.tick()
        _xong(self.cc, t1.task_id)
        self.cc.chat("demo", "update the spacing in web/admin")
        t2 = [t for t in self.cc.store.tasks("demo")
              if t.task_id != t1.task_id][0]
        self.cc.tick()
        _xong(self.cc, t2.task_id)

        self.assertEqual(self.cc.store.task(t1.task_id).worktree,
                         self.cc.store.task(t2.task_id).worktree)
        self.assertEqual(len(self.cc.store.worktrees("demo")), 1)

    def test_viec_CHI_DOC_dung_lai_bat_ky_phien_ranh_nao(self):
        self.cc.chat("demo", "fix the styling in web/admin")
        t1 = self.cc.store.tasks("demo")[0]
        self.cc.tick()
        _xong(self.cc, t1.task_id)

        self.cc.chat("demo", "investigate why the build is slow")
        t2 = [t for t in self.cc.store.tasks("demo")
              if t.task_id != t1.task_id][0]
        self.cc.tick()
        _xong(self.cc, t2.task_id)
        self.assertEqual(self.cc.store.task(t2.task_id).owner_session,
                         self.cc.store.task(t1.task_id).owner_session)

    # -- 4. CHO khi xung dot ------------------------------------------------

    def test_hai_viec_cung_tai_nguyen_thi_mot_viec_CHO(self):
        """Đúng ví dụ đề bài: B chờ, không chạy đua với A."""
        cham = FakeExecutor(cham=1.5)
        cc = _cc(kho_git_tam(), ex=cham)
        try:
            cc.chat("demo", "fix web/admin/content-queue")
            cc.chat("demo", "clean up web/admin/content-queue markup")
            ts = cc.store.tasks("demo")
            self.assertEqual(len(ts), 2)

            cc.tick()
            time.sleep(0.3)
            cc.tick()
            trang_thai = {t.task_id: cc.store.task(t.task_id).state
                          for t in ts}
            self.assertEqual(
                sum(1 for s in trang_thai.values() if s is TaskState.RUNNING),
                1, f"đúng MỘT việc được chạy: {trang_thai}")
            self.assertEqual(
                sum(1 for s in trang_thai.values() if s is TaskState.WAITING),
                1, f"việc kia phải CHỜ: {trang_thai}")
        finally:
            cc.shutdown()

    def test_viec_cho_chay_duoc_sau_khi_khoa_duoc_nha(self):
        cc = _cc(kho_git_tam(), ex=FakeExecutor(cham=0.4))
        try:
            cc.chat("demo", "fix web/admin/content-queue")
            cc.chat("demo", "clean up web/admin/content-queue markup")
            ts = [t.task_id for t in cc.store.tasks("demo")]
            self.assertTrue(_chay_het(cc, *ts),
                            {x: cc.store.task(x).state for x in ts})
        finally:
            cc.shutdown()

    def test_khoa_duoc_nha_het_sau_khi_viec_xong(self):
        self.cc.chat("demo", "fix web/admin/content-queue")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        self.assertEqual(self.cc.store.locks("demo"), [],
                         "mọi khoá phải được nhả trong `finally`")

    def test_khoa_duoc_nha_ca_khi_viec_HONG(self):
        cc = _cc(kho_git_tam(), ex=FakeExecutor(status="failed"))
        try:
            cc.chat("demo", "fix web/admin/content-queue")
            tid = cc.store.tasks("demo")[0].task_id
            # Chay toi khi CAN LUOT THU: viec hong duoc thu lai co tran, nen
            # mot `tick()` chi cho ra `QUEUED` chu chua phai `FAILED`.
            self.assertTrue(_can_luot(cc, tid))
            self.assertIs(cc.store.task(tid).state, TaskState.FAILED)
            self.assertEqual(cc.store.locks("demo"), [],
                             "khoá phải được nhả sau MỌI lượt, kể cả lượt hỏng")
        finally:
            cc.shutdown()

    # -- 5. Phu thuoc -------------------------------------------------------

    def test_viec_phu_thuoc_CHO_den_khi_viec_truoc_XONG(self):
        self.cc.chat("demo", "fix web/admin then investigate the result")
        ts = self.cc.store.tasks("demo")
        self.assertEqual(len(ts), 2)
        sau = [t for t in ts if t.dependencies][0]
        self.cc.tick()
        self.assertIs(self.cc.store.task(sau.task_id).state, TaskState.WAITING)
        self.assertTrue(
            _chay_het(self.cc, *[t.task_id for t in ts]),
            {t.task_id: self.cc.store.task(t.task_id).state for t in ts})

    def test_phu_thuoc_HONG_thi_viec_con_bi_CHAN_chu_khong_treo(self):
        cc = _cc(kho_git_tam(), ex=FakeExecutor(status="failed"))
        try:
            cc.chat("demo", "fix web/admin then investigate the result")
            ts = cc.store.tasks("demo")
            truoc = [t for t in ts if not t.dependencies][0]
            sau = [t for t in ts if t.dependencies][0]
            # Viec truoc phai HONG HAN (can luot thu) thi viec con moi bi chan.
            self.assertTrue(_can_luot(cc, truoc.task_id))
            cc.tick()
            self.assertIs(cc.store.task(sau.task_id).state, TaskState.BLOCKED)
            self.assertIn("phụ thuộc", cc.store.task(sau.task_id).blocked_reason)
        finally:
            cc.shutdown()

    # -- 5b. Review doc lap -------------------------------------------------

    def test_viec_RUI_RO_CAO_de_ra_mot_viec_review_LA_CON(self):
        """`REVIEW` không được là ngõ cụt.

        Hợp đồng của việc rủi ro cao đòi review độc lập, nên việc xong đi vào
        `REVIEW`. Nếu không có gì đưa nó ra khỏi đó thì trạng thái ấy tệ hơn
        là không tồn tại — việc nằm im mãi và không ai biết vì sao.
        """
        self.cc.chat("demo", "fix the auth permission check in web/admin")
        goc = self.cc.store.tasks("demo")[0]
        self.assertTrue(
            TaskContract.from_dict(goc.contract)
            .verification.independent_review_required)

        self.cc.tick()
        _xong(self.cc, goc.task_id)
        self.assertIs(self.cc.store.task(goc.task_id).state, TaskState.REVIEW)

        review = self.cc.store.task(f"{goc.task_id}-review")
        self.assertIsNotNone(review, "phải đặt một việc review")
        self.assertEqual(review.parent_id, goc.task_id)
        self.assertEqual(review.dependencies, (goc.task_id,))

    def test_review_KHONG_duoc_cung_ho_model_voi_tac_gia(self):
        """Tác giả không được tự chấm bài của mình."""
        self.cc.chat("demo", "fix the auth permission check in web/admin")
        goc = self.cc.store.tasks("demo")[0]
        self.cc.tick()
        _xong(self.cc, goc.task_id)

        review = self.cc.store.task(f"{goc.task_id}-review")
        hd = TaskContract.from_dict(review.contract)
        s = self.cc.store.session(self.cc.store.task(goc.task_id).owner_session)
        ho_tac_gia = self.cc.fabric.model(s.model_id).model_family
        self.assertIn(ho_tac_gia, hd.requirements.exclude_families)
        self.assertFalse(hd.requirements.repo_write,
                         "reviewer sửa được thì không còn độc lập")

    def test_review_xong_thi_viec_CHA_thanh_DONE(self):
        self.cc.chat("demo", "fix the auth permission check in web/admin")
        goc = self.cc.store.tasks("demo")[0]
        self.assertTrue(_chay_het(self.cc, goc.task_id,
                                  f"{goc.task_id}-review", giay=40),
                        {t.task_id: t.state for t in self.cc.store.tasks("demo")})
        self.assertIs(self.cc.store.task(goc.task_id).state, TaskState.DONE)

    def test_review_HONG_thi_viec_CHA_bi_CHAN_chu_khong_thanh_DONE(self):
        """Không kiểm chéo được thì KHÔNG được tuyên bố là xong."""
        cc = _cc(kho_git_tam(), ex=FakeExecutor())
        try:
            cc.chat("demo", "fix the auth permission check in web/admin")
            goc = cc.store.tasks("demo")[0]
            cc.tick()
            _xong(cc, goc.task_id)
            rid = f"{goc.task_id}-review"
            r = cc.store.task(rid)
            r.state, r.parent_id = TaskState.RUNNING, goc.task_id
            cc.store.luu_task(r)
            cc.store.doi_trang_thai(rid, TaskState.FAILED, force=True)
            cc._khep_review(cc.store.task(rid))
            self.assertIs(cc.store.task(goc.task_id).state, TaskState.BLOCKED)
        finally:
            cc.shutdown()

    def test_review_KHONG_bi_dat_hai_lan(self):
        self.cc.chat("demo", "fix the auth permission check in web/admin")
        goc = self.cc.store.tasks("demo")[0]
        self.cc.tick()
        _xong(self.cc, goc.task_id)
        ctx = self.cc.ctx("demo")
        hd = TaskContract.from_dict(goc.contract)
        from scripts.router_v4.runtime import Placement
        self.cc._dat_review(ctx, goc.task_id, hd, Placement("RT01", "m-re"))
        rs = [t for t in self.cc.store.tasks("demo")
              if t.task_id.endswith("-review")]
        self.assertEqual(len(rs), 1)

    # -- 5c. Thu lai co tran ------------------------------------------------

    def test_viec_hong_duoc_thu_lai_o_CHO_KHAC(self):
        """Một lần nhà cung cấp hắt hơi không được làm hỏng việc vĩnh viễn.

        `Executor.run()` chạy đúng MỘT lượt; đường thử lại của Router V4 nằm
        trong `run_task`, mà Control Center cố ý không đi qua. Không có gì ở
        đây thì với một hệ chạy qua đêm không người trực, đó là chế độ hỏng
        thường gặp nhất.
        """
        cc = _cc(kho_git_tam(), ex=FakeExecutor(status="failed"))
        try:
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            cc.tick()
            _xong(cc, tid)
            t = cc.store.task(tid)
            self.assertIs(t.state, TaskState.QUEUED, "phải quay lại hàng đợi")
            self.assertEqual(t.owner_session, "", "phải nhả phiên cũ")
            self.assertEqual(t.attempts, 1)
        finally:
            cc.shutdown()

    def test_thu_lai_CO_TRAN_khong_lap_vo_han(self):
        """Thử lại vô hạn là 'bão thử lại' — chế độ hỏng số 4 của `leases.py`."""
        cc = _cc(kho_git_tam(), ex=FakeExecutor(status="failed"))
        try:
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            for _ in range(8):
                cc.tick()
                _xong(cc, tid, giay=10)
                if cc.store.task(tid).state is TaskState.FAILED:
                    break
            t = cc.store.task(tid)
            self.assertIs(t.state, TaskState.FAILED)
            self.assertLessEqual(t.attempts, 3,
                                 f"chạy {t.attempts} lượt — vượt trần")
        finally:
            cc.shutdown()

    def test_hong_CONG_BAO_MAT_KHONG_BAO_GIO_thu_lai(self):
        """Thử lại một cổng bảo mật chỉ tăng cơ hội lọt một thay đổi chưa
        thử giống credential — luật lấy thẳng từ Router V4."""
        cc = _cc(kho_git_tam())
        try:
            ctx = cc.ctx("demo")
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            t = cc.store.task(tid)
            t.state, t.attempts = TaskState.RUNNING, 1
            cc.store.luu_task(t)
            from scripts.router_v4.envelope import ResultEnvelope
            pb = ResultEnvelope(task_id=tid, status="failed",
                                failure_reason="security_gate")
            cc.store.doi_trang_thai(tid, TaskState.FAILED, force=True)
            cc._thu_lai_neu_dang(ctx, tid, pb, "s-x")
            self.assertIs(cc.store.task(tid).state, TaskState.FAILED)
        finally:
            cc.shutdown()

    def test_hong_do_TU_CHOI_QUYEN_khong_thu_lai(self):
        """Chạy lại y hệt sẽ bị từ chối y hệt — chỉ tốn thêm một lượt quota."""
        cc = _cc(kho_git_tam())
        try:
            ctx = cc.ctx("demo")
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            cc.store.doi_trang_thai(tid, TaskState.FAILED, force=True)
            from scripts.router_v4.envelope import ResultEnvelope
            cc._thu_lai_neu_dang(
                ctx, tid,
                ResultEnvelope(task_id=tid, status="failed",
                               failure_reason="tool_permission_denied"), "s-x")
            self.assertIs(cc.store.task(tid).state, TaskState.FAILED)
        finally:
            cc.shutdown()

    def test_viec_doi_QUYET_DINH_khong_thu_lai_ma_cho_nguoi(self):
        cc = _cc(kho_git_tam())
        try:
            ctx = cc.ctx("demo")
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            cc.store.doi_trang_thai(tid, TaskState.FAILED, force=True)
            from scripts.router_v4.envelope import ResultEnvelope
            pb = ResultEnvelope(task_id=tid, status="blocked")
            pb.requires_decision = True
            cc._thu_lai_neu_dang(ctx, tid, pb, "s-x")
            self.assertIs(cc.store.task(tid).state, TaskState.FAILED)
        finally:
            cc.shutdown()

    # -- 6. Pause / Stop / Reassign -----------------------------------------

    def test_pause_giu_viec_lai_khoi_hang_doi(self):
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.pause(tid)
        self.assertIs(self.cc.store.task(tid).state, TaskState.PAUSED)
        self.assertEqual(self.cc.tick()["dispatched"], [])

    def test_resume_dua_viec_ve_hang_doi(self):
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.pause(tid)
        self.cc.resume(tid)
        self.assertIs(self.cc.store.task(tid).state, TaskState.QUEUED)
        self.assertEqual(self.cc.tick()["dispatched"], [tid])

    def test_stop_dung_han_va_nha_khoa(self):
        self.cc.chat("demo", "fix web/admin/content-queue")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        self.cc.stop(tid, reason="người dùng dừng")
        self.assertIs(self.cc.store.task(tid).state, TaskState.FAILED)
        self.assertEqual(self.cc.store.locks("demo"), [])

    def test_stop_ghi_ro_co_cat_duoc_tien_trinh_hay_khong(self):
        """Không giả vờ đã cắt. Sự kiện nói rõ có giết được gì không."""
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        self.cc.stop(tid)
        e = [x for x in self.cc.store.su_kien(task_id=tid)
             if x["kind"] == "TASK_STOPPED"][0]
        self.assertIn("agent_killed", e["meta"])

    def test_reassign_nha_phien_cu_va_ve_hang_doi(self):
        # Viec HONG (khong phai DONE): khong co ket qua nao dang giu, va
        # "hong roi, thu cho khac" dung la viec `reassign` sinh ra de lam.
        cc = _cc(kho_git_tam(), ex=FakeExecutor(status="failed"))
        self.addCleanup(cc.shutdown)
        cc.chat("demo", "fix web/admin")
        tid = cc.store.tasks("demo")[0].task_id
        self.assertTrue(_can_luot(cc, tid))
        cu = cc.store.task(tid).owner_session
        self.cc = cc                      # cac phep kiem con lai dung ban nay

        self.cc.reassign(tid)
        t = self.cc.store.task(tid)
        self.assertIs(t.state, TaskState.QUEUED)
        self.assertEqual(t.owner_session, "")
        self.assertIs(self.cc.store.session(cu).state, SessionState.STOPPED)

        self.cc.tick()
        _xong(self.cc, tid, giay=30)
        self.assertNotEqual(self.cc.store.task(tid).owner_session, cu)

    def test_reassign_TU_CHOI_viec_da_DONE(self):
        """`r` trên một việc DONE từng chạy lại nó và ghi đè mất kết quả.

        `force=True` đi vòng qua TOÀN BỘ bảng chuyển trạng thái, nên `DONE`
        thôi không còn là ngõ cụt. Báo cáo, `changes`, và cả `findings` mà
        review độc lập vừa gộp vào đều biến mất — không một hộp xác nhận nào,
        và `r` nằm ngay cạnh `o`/`s`.
        """
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        self.assertIs(self.cc.store.task(tid).state, TaskState.DONE)
        truoc = self.cc.store.task(tid).result

        with self.assertRaises(TransitionError):
            self.cc.reassign(tid)
        t = self.cc.store.task(tid)
        self.assertIs(t.state, TaskState.DONE, "phải giữ nguyên DONE")
        self.assertEqual(t.result, truoc, "kết quả cũ KHÔNG được ghi đè")

    def test_reassign_TU_CHOI_viec_DANG_CHAY(self):
        """`sessions.dung()` nhả chủ worktree trong khi agent vẫn đang ghi
        vào đúng cây đó — `assert_exclusive` mất tác dụng đúng lúc cần nhất."""
        cc = _cc(kho_git_tam(), ex=FakeExecutor(cham=2.0))
        try:
            cc.chat("demo", "fix web/admin")
            tid = cc.store.tasks("demo")[0].task_id
            cc.tick()
            self.assertTrue(_cho(
                lambda: cc.store.task(tid).state is TaskState.RUNNING, giay=10))
            with self.assertRaises(TransitionError):
                cc.reassign(tid)
            _xong(cc, tid, giay=30)
        finally:
            cc.shutdown()

    def test_reassign_VAN_chay_duoc_tren_viec_chua_ket_thuc(self):
        """Siết chặt không được biến hàm thành vô dụng."""
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        t = self.cc.reassign(tid)
        self.assertIs(t.state, TaskState.QUEUED)
        self.assertEqual(t.owner_session, "")

    def test_ghi_ket_qua_KHONG_dam_len_lenh_pause_cua_nguoi_dung(self):
        """Đọc–sửa–ghi kéo dài qua cả một lượt agent sẽ nuốt mất một lệnh.

        Luồng `_chay` đọc việc TRƯỚC lượt agent; người dùng bấm `p` ở giữa;
        rồi luồng lưu đối tượng CŨ và kéo trạng thái ngược về RUNNING. Lệnh
        `pause` biến mất không dấu vết.
        """
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.doi_trang_thai(tid, TaskState.RUNNING)
        cu = self.cc.store.task(tid)          # ảnh chụp CŨ, state=RUNNING

        self.cc.store.doi_trang_thai(tid, TaskState.PAUSED)   # người dùng bấm p
        self.cc.store.ghi_ket_qua(tid, result={"envelope": {"status": "ok"}},
                                  worktree="", branch="")
        self.assertIs(self.cc.store.task(tid).state, TaskState.PAUSED,
                      "ghi kết quả KHÔNG được đụng tới `state`")
        self.assertIsNotNone(self.cc.store.task(tid).result)

    def test_khoa_duoc_nha_ca_khi_giao_viec_nem_ngoai_le_LA(self):
        """Lưới cuối: một ngoại lệ KHÔNG LƯỜNG TRƯỚC cũng không được rò khoá.

        Với khoá PRODUCTION thì rò = treo vĩnh viễn, vì `reclaim()` cố ý
        không nhả chúng.
        """
        cc = _cc(kho_git_tam())
        try:
            cc.chat("demo", "fix web/admin/content-queue")
            t = cc.store.tasks("demo")[0]
            ctx = cc.ctx("demo")

            def _no(*a, **k):
                raise RuntimeError("sổ nghẽn")
            ctx.sessions.decide = _no

            kq = cc._giao(t)
            self.assertFalse(kq["dispatched"])
            self.assertEqual(cc.store.locks("demo"), [],
                             "khoá phải được nhả dù ngoại lệ không lường trước")
        finally:
            cc.shutdown()

    # -- 7. SONG SOT qua khoi dong lai --------------------------------------

    def test_moi_thu_song_sot_qua_khoi_dong_lai(self):
        """Yêu cầu #10: dự án, việc, phiên, worktree, khoá, sự kiện.

        Dựng một `ControlCenter` HOÀN TOÀN MỚI trên cùng thư mục gốc —
        đúng như mở lại ứng dụng.
        """
        self.cc.chat("demo", "fix the styling in web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        cu = self.cc.store.task(tid)
        so_sk = len(self.cc.store.su_kien(project_id="demo", limit=1000))
        self.cc.shutdown()

        moi = ControlCenter(root=self.repo, fabric=fabric_gia(), probe=False,
                            executor_factory=lambda p, f: FakeExecutor())
        try:
            self.assertEqual([p.project_id for p in moi.projects()], ["demo"])
            t = moi.store.task(tid)
            self.assertIsNotNone(t)
            self.assertIs(t.state, TaskState.DONE)
            self.assertEqual(t.worktree, cu.worktree)
            self.assertEqual(t.branch, cu.branch)
            self.assertTrue(moi.store.session(cu.owner_session))
            self.assertTrue(moi.store.worktrees("demo"))
            self.assertGreaterEqual(
                len(moi.store.su_kien(project_id="demo", limit=1000)), so_sk)
            self.assertTrue(moi.store.chat("demo"))
        finally:
            moi.shutdown()

    def test_recover_dua_viec_MO_COI_ve_hang_doi_chu_khong_danh_HONG(self):
        """Việc `RUNNING` mồ côi -> `QUEUED`, không phải `FAILED`.

        Tiến trình agent có thể vẫn đang chạy thật (tắt Control Center không
        giết nó). Đánh `FAILED` là vứt luôn công việc đã làm; đưa về hàng
        đợi là hành vi thu hồi được.
        """
        from scripts.control_center.model import Session, Task
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.luu_session(Session(
            session_id="s-chet", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.BUSY,
            pid=999999, current_task=tid))
        t = self.cc.store.task(tid)
        t.state, t.owner_session, t.attempts = TaskState.RUNNING, "s-chet", 1
        self.cc.store.luu_task(t)

        bc = self.cc.recover()
        self.assertIn(tid, bc["tasks"])
        self.assertIs(self.cc.store.task(tid).state, TaskState.QUEUED)
        self.assertIs(self.cc.store.session("s-chet").state, SessionState.DEAD)

    def test_recover_cuu_viec_mo_coi_khi_phien_con_SONG_nhung_DANG_RANH(self):
        """LỖI THẬT: "phiên còn sống" KHÔNG đủ — phải là "đang chạy ĐÚNG
        việc này".

        Một phiên RẢNH (`IDLE`, `current_task` rỗng) vẫn "còn sống", nên một
        việc mà phiên chủ đã bỏ lại sẽ ở `RUNNING` VĨNH VIỄN: `recover()` bỏ
        qua nó, và bộ lập lịch không bao giờ nhặt nó lên vì nó không ở
        QUEUED/WAITING.

        Đo thật 2026-09-08: `rev2.tda87-1` kẹt ở RUNNING qua BA lần gọi
        `--headless` liên tiếp, mỗi lần đều chạy `recover()`.
        """
        from scripts.control_center.model import Session, SessionState
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.luu_session(Session(
            session_id="s-ranh", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.IDLE,
            pid=None, current_task=""))          # SỐNG, nhưng RẢNH
        t = self.cc.store.task(tid)
        t.state, t.owner_session, t.attempts = TaskState.RUNNING, "s-ranh", 1
        self.cc.store.luu_task(t)

        bc = self.cc.recover()
        self.assertIn(tid, bc["tasks"])
        self.assertIs(self.cc.store.task(tid).state, TaskState.QUEUED)

    def test_recover_DE_YEN_viec_ma_phien_dang_that_su_chay(self):
        """Vế đối xứng: đừng cướp một việc đang chạy THẬT.

        "Thật" ở đây đòi BẰNG CHỨNG: một PID còn sống. Dùng PID của chính
        tiến trình bài kiểm — nó chắc chắn còn sống, và đó là đúng loại bằng
        chứng `SessionManager.recover()` đi tìm.
        """
        import os
        from scripts.control_center.model import Session, SessionState
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.luu_session(Session(
            session_id="s-ban", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.BUSY,
            pid=os.getpid(), current_task=tid))
        t = self.cc.store.task(tid)
        t.state, t.owner_session = TaskState.RUNNING, "s-ban"
        self.cc.store.luu_task(t)

        self.cc.recover()
        self.assertIs(self.cc.store.task(tid).state, TaskState.RUNNING)

    def test_recover_phien_BAN_ma_KHONG_CO_PID_thi_viec_van_duoc_cuu(self):
        """Không có PID = không kiểm được = không được coi là đang chạy.

        Sau một lần khởi động lại, tiến trình agent (nếu còn sống) là con của
        một Control Center đã chết — không ai còn thu kết quả của nó nữa, nên
        công việc đó mất dù thế nào. Đưa việc về hàng đợi là thu hồi được;
        để nó `RUNNING` là mất luôn.
        """
        from scripts.control_center.model import Session, SessionState
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.luu_session(Session(
            session_id="s-mo", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.BUSY,
            pid=None, current_task=tid))
        t = self.cc.store.task(tid)
        t.state, t.owner_session, t.attempts = TaskState.RUNNING, "s-mo", 1
        self.cc.store.luu_task(t)

        self.cc.recover()
        self.assertIs(self.cc.store.task(tid).state, TaskState.QUEUED)

    def test_recover_NHA_KHOA_cua_viec_mo_coi(self):
        """Việc đã ra khỏi `RUNNING` thì khoá của nó phải về theo.

        Không nhả thì khoá của một việc mồ côi còn giữ tới hết TTL (1 giờ),
        và MỌI việc khác chạm cùng tài nguyên phải chờ hết giờ đó — trong
        khi việc giữ khoá thì đã không còn chạy. Đo thật 2026-09-08: một
        lượt chứng minh bị cắt giữa chừng để lại hai khoá, và lần chạy kế
        tiếp kẹt ở `WAITING` vĩnh viễn.
        """
        from scripts.control_center.locks import LockManager
        from scripts.control_center.model import Session, SessionState
        self.cc.chat("demo", "fix web/admin/content-queue")
        tid = self.cc.store.tasks("demo")[0].task_id
        LockManager(self.cc.store).xin(
            "demo", [(LockKind.FILESYSTEM, "web/admin/content-queue")],
            task_id=tid)
        self.assertTrue(self.cc.store.locks("demo"))

        self.cc.store.luu_session(Session(
            session_id="s-mo", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.IDLE,
            pid=None, current_task=""))
        t = self.cc.store.task(tid)
        t.state, t.owner_session, t.attempts = TaskState.RUNNING, "s-mo", 1
        self.cc.store.luu_task(t)

        self.cc.recover()
        self.assertIs(self.cc.store.task(tid).state, TaskState.QUEUED)
        self.assertEqual(self.cc.store.locks("demo"), [],
                         "khoá của việc mồ côi phải được nhả")

    def test_recover_NHA_KHOA_cua_chu_KHONG_con_RUNNING(self):
        """Bất biến: một khoá chỉ được giữ bởi một việc ĐANG CHẠY.

        Một lượt `recover()` TRƯỚC ĐÓ có thể đã chuyển việc sang `BLOCKED`
        mà chưa nhả khoá. Từ đó việc không còn ở `RUNNING` nên vòng lặp việc
        mồ côi không bao giờ thấy nó, và khoá kẹt lại tới hết TTL (1 giờ).
        Đo thật 2026-09-08: hai khoá kẹt đúng như vậy và chặn mọi lượt sau.
        """
        from scripts.control_center.locks import LockManager
        self.cc.chat("demo", "fix web/admin/content-queue")
        tid = self.cc.store.tasks("demo")[0].task_id
        LockManager(self.cc.store).xin(
            "demo", [(LockKind.FILESYSTEM, "web/admin/content-queue")],
            task_id=tid)
        # Chu khoa o BLOCKED — khong con chay, nhung cung khong con o RUNNING.
        self.cc.store.doi_trang_thai(tid, TaskState.BLOCKED, force=True,
                                     reason="mô phỏng lượt recover trước")
        self.assertTrue(self.cc.store.locks("demo"))

        self.cc.recover()
        self.assertEqual(self.cc.store.locks("demo"), [],
                         "khoá của chủ không-RUNNING phải được nhả")

    def test_nha_khoa_mo_coi_KHONG_dung_toi_khoa_PRODUCTION(self):
        """`tu_thu_hoi_duoc` là bất biến của cả hệ, không phải chi tiết của
        `reclaim()`.

        Một khoá production "mồ côi" có thể là một cutover đang chạy lâu hơn
        dự kiến; đoán sai là thả việc thứ hai vào giữa nó. Bản đầu của
        `_nha_khoa_mo_coi` nhả cả khoá production và làm hỏng đúng bài kiểm
        giữ bất biến đó.
        """
        from scripts.control_center.locks import LockManager
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        LockManager(self.cc.store).xin(
            "demo", [(LockKind.PRODUCTION, "fanfic.world")], task_id=tid)
        self.cc.store.doi_trang_thai(tid, TaskState.BLOCKED, force=True,
                                     reason="chủ không còn chạy")
        self.cc.recover()
        con = [l.kind for l in self.cc.store.locks("demo")]
        self.assertIn(LockKind.PRODUCTION, con,
                      "khoá PRODUCTION KHÔNG được tự nhả, kể cả khi mồ côi")

    def test_recover_KHONG_cuop_khoa_cua_viec_dang_duoc_giao(self):
        """`_giao()` giành khoá TRƯỚC khi `claim_task` lật sang RUNNING.

        Nhả theo trạng thái mà quên `_dang_chay` sẽ cướp khoá ngay giữa lúc
        một việc đang được giao.
        """
        from scripts.control_center.locks import LockManager
        self.cc.chat("demo", "fix web/admin/content-queue")
        tid = self.cc.store.tasks("demo")[0].task_id
        LockManager(self.cc.store).xin(
            "demo", [(LockKind.FILESYSTEM, "web/admin/content-queue")],
            task_id=tid)
        # Viec van o QUEUED (chua claim) nhung DANG duoc giao.
        with self.cc._khoa:
            self.cc._dang_chay[tid] = None
        try:
            self.cc.recover()
            self.assertTrue(self.cc.store.locks("demo"),
                            "KHÔNG được cướp khoá của việc đang được giao")
        finally:
            with self.cc._khoa:
                self.cc._dang_chay.pop(tid, None)

    def test_recover_CHAN_viec_da_can_luot_thu(self):
        from scripts.control_center.model import Session
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.store.luu_session(Session(
            session_id="s-chet", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.BUSY,
            pid=999999))
        t = self.cc.store.task(tid)
        t.state, t.owner_session, t.attempts = TaskState.RUNNING, "s-chet", 3
        self.cc.store.luu_task(t)
        self.cc.recover()
        self.assertIs(self.cc.store.task(tid).state, TaskState.BLOCKED)

    def test_recover_thu_hoi_khoa_chet_nhung_KHONG_dung_khoa_production(self):
        from scripts.control_center.locks import LockManager
        lm = LockManager(self.cc.store)
        lm.xin("demo", [(LockKind.FILESYSTEM, "web")], task_id="chet",
               ttl=-1.0)
        lm.xin("demo", [(LockKind.PRODUCTION, "fanfic.world")],
               task_id="chet-prod", ttl=-1.0)
        bc = self.cc.recover()
        self.assertEqual(len(bc["locks"]["reclaimed"]), 1)
        self.assertEqual(len(bc["locks"]["needs_human"]), 1)
        con = {l.kind for l in self.cc.store.locks("demo")}
        self.assertEqual(con, {LockKind.PRODUCTION})

    def test_recover_KHONG_xoa_worktree_nao(self):
        self.cc.chat("demo", "fix web/admin")
        tid = self.cc.store.tasks("demo")[0].task_id
        self.cc.tick()
        _xong(self.cc, tid)
        duong = self.cc.store.task(tid).worktree
        self.cc.recover()
        self.assertTrue(Path(duong).exists(),
                        "phục hồi chỉ ĐÁNH DẤU, không bao giờ xoá worktree")

    # -- 8. Anh chup cho giao dien ------------------------------------------

    def test_snapshot_du_cho_bay_man_hinh(self):
        self.cc.chat("demo", "fix web/admin")
        self.cc.tick()
        s = self.cc.snapshot("demo")
        for k in ("projects", "tasks", "sessions", "locks", "worktrees",
                  "events", "chat", "in_flight"):
            self.assertIn(k, s)
        self.assertEqual(s["selected"], "demo")


class TestDoiSoatKhaiThieu(unittest.TestCase):
    """B5 — đối soát lời khai thiếu, và nó phải FAIL CLOSED.

    Cổng `diff` của Router V4 KHÔNG bị sửa. Control Center làm một việc khác
    và chặt hơn: lấy danh sách tệp đổi THẬT từ `git` rồi kiểm lại chính danh
    sách đó, thay vì tin lời khai của worker.
    """

    def setUp(self):
        self.repo = kho_git_tam()
        self.cc = _cc(self.repo)
        self.ctx = self.cc.ctx("demo")
        self.cc.chat("demo", "fix web/admin")
        self.tid = self.cc.store.tasks("demo")[0].task_id
        self.hd = TaskContract.from_dict(self.cc.store.task(self.tid).contract)

    def tearDown(self):
        self.cc.shutdown()

    def _kq(self, *, declared, observed, gates, status="ok"):
        from scripts.router_v3.pool import validation as V
        from scripts.router_v4.envelope import ResultEnvelope
        pb = ResultEnvelope(task_id=self.tid, status=status,
                            summary="đã làm", changes=list(declared))
        bc = V.ValidationReport(
            gates=[V.GateResult(n, ok, "") for n, ok in gates],
            files_changed_observed=list(observed))
        return ExecutionResult(envelope=pb, validation=bc)

    #: Moi cong DAT tru `diff` — dung hinh dang cua truong hop khai thieu.
    CONG_OK = [("shape", True), ("diff", False), ("scope", True),
               ("security", True), ("tests", True), ("artifacts", True)]

    def test_khai_RONG_nhung_moi_tep_TRONG_pham_vi_thi_duoc_di_tiep(self):
        kq = self._kq(declared=[], observed=["web/admin/a.txt"],
                      gates=self.CONG_OK)
        self.assertTrue(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))
        self.assertEqual(kq.envelope.changes, ["web/admin/a.txt"],
                         "`changes` phải được điền lại bằng tập THẬT")
        e = [x for x in self.cc.store.su_kien(task_id=self.tid)
             if x["kind"] == "UNDERDECLARED_CHANGES"]
        self.assertEqual(len(e), 1, "phải có sự kiện kiểm toán")

    def test_tep_doi_NGOAI_pham_vi_thi_VAN_HONG(self):
        """Đây là vế fail-closed. Một tệp ngoài phạm vi ⇒ từ chối."""
        kq = self._kq(declared=[],
                      observed=["web/admin/a.txt", "server/secret.py"],
                      gates=self.CONG_OK)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))
        e = [x for x in self.cc.store.su_kien(task_id=self.tid)
             if x["kind"] == "UNDERDECLARED_CHANGES_REJECTED"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["level"], "ALERT")

    def test_cham_duong_CAM_thi_VAN_HONG(self):
        kq = self._kq(declared=[], observed=[".git/config"],
                      gates=self.CONG_OK)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_cong_BAO_MAT_hong_thi_VAN_HONG(self):
        gates = [(n, (ok if n != "security" else False))
                 for n, ok in self.CONG_OK]
        kq = self._kq(declared=[], observed=["web/admin/a.txt"], gates=gates)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_cong_KHAC_hong_thi_VAN_HONG(self):
        gates = [(n, (ok if n != "artifacts" else False))
                 for n, ok in self.CONG_OK]
        kq = self._kq(declared=[], observed=["web/admin/a.txt"], gates=gates)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_KHAI_CO_SUA_ma_dia_SACH_thi_VAN_HONG(self):
        """Chiều ngược lại là thất bại IM LẶNG thật — không bao giờ nới.

        Worker khai có sửa nhưng `git` sạch nghĩa là lệnh ghi bị từ chối
        hoặc worker bịa. Đối soát KHÔNG được chạm tới trường hợp này.
        """
        kq = self._kq(declared=["web/admin/a.txt"], observed=[],
                      gates=self.CONG_OK)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_khai_SAI_nhung_khong_rong_thi_KHONG_thuoc_dien_doi_soat(self):
        kq = self._kq(declared=["mô tả chứ không phải đường dẫn"],
                      observed=["web/admin/a.txt"], gates=self.CONG_OK)
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_worker_bao_KHONG_ok_thi_khong_doi_soat(self):
        kq = self._kq(declared=[], observed=["web/admin/a.txt"],
                      gates=self.CONG_OK, status="failed")
        self.assertFalse(
            self.cc._doi_soat_khai_thieu(self.ctx, self.tid, self.hd, kq))

    def test_KHONG_sua_mot_dong_nao_cua_cong_diff_trong_V4(self):
        """Bất biến V4 phải nguyên vẹn: cổng `diff` vẫn hard-fail ca này."""
        from scripts.router_v3.pool.validation import cong_diff
        from scripts.router_v3.packet import TaskResult
        g = cong_diff(
            TaskResult(task_id="t", worker_id="w", status="ok",
                       summary="x", files_changed=[]),
            ["web/admin/a.txt"], la_viec_co_ghi=True)
        self.assertFalse(g.passed,
                         "cổng `diff` của V4 PHẢI vẫn hỏng — đối soát nằm ở "
                         "tầng trên, không phải bằng cách nới cổng")


class TestHaiTienTrinh(unittest.TestCase):
    """HAI Control Center cùng một sổ — chuyện bình thường trong kho này.

    Giao diện mở ở một cửa sổ, một lệnh CLI chạy ở cửa sổ khác, hoặc đơn giản
    là người dùng mở app hai lần. Sổ nằm trên đĩa và cả hai đều ghi, nên mọi
    bất biến loại trừ phải đúng GIỮA CÁC TIẾN TRÌNH, không chỉ giữa các luồng.
    """

    def setUp(self):
        self.repo = kho_git_tam()
        self.a = _cc(self.repo, ex=FakeExecutor(cham=0.4))
        # Ban thu hai dung CHUNG thu muc goc -> chung tep SQLite.
        self.b = ControlCenter(root=self.repo, fabric=fabric_gia(), probe=False,
                               executor_factory=lambda p, f: FakeExecutor(cham=0.4))

    def tearDown(self):
        for cc in (self.a, self.b):
            try:
                cc.shutdown()
            except Exception:                             # noqa: BLE001
                pass

    def test_ban_thu_hai_THAY_du_an_va_viec_cua_ban_thu_nhat(self):
        self.a.chat("demo", "fix web/admin")
        self.assertEqual([p.project_id for p in self.b.projects()], ["demo"])
        self.assertEqual(len(self.b.store.tasks("demo")), 1)

    def test_MOT_viec_KHONG_bao_gio_bi_giao_hai_lan(self):
        """`claim_task` là một câu `UPDATE` có điều kiện — hai bên cùng gọi
        thì đúng một bên thấy `rowcount == 1`.

        Đây là bất biến mà cả hàng đợi V3 lẫn lease V4 đều dựa vào; kiểm nó
        ở tầng này để một lần sửa `store.py` về sau không âm thầm phá nó.
        """
        self.a.chat("demo", "fix web/admin")
        tid = self.a.store.tasks("demo")[0].task_id
        self.assertTrue(self.a.store.claim_task(tid, "s-A"))
        self.assertFalse(self.b.store.claim_task(tid, "s-B"),
                         "bản thứ hai KHÔNG được nhận lại việc đã có chủ")
        self.assertEqual(self.b.store.task(tid).owner_session, "s-A")

    def test_hai_vong_lap_cung_tick_thi_viec_van_chi_chay_MOT_lan(self):
        self.a.chat("demo", "fix web/admin/content-queue")
        tid = self.a.store.tasks("demo")[0].task_id
        ka, kb = self.a.tick(), self.b.tick()
        giao = ka["dispatched"] + kb["dispatched"]
        self.assertEqual(giao.count(tid), 1,
                         f"việc bị giao {giao.count(tid)} lần: {ka} / {kb}")
        _xong(self.a, tid, giay=30)
        _xong(self.b, tid, giay=30)
        self.assertEqual(self.a.store.task(tid).attempts, 1)

    def test_khoa_tai_nguyen_co_hieu_luc_GIUA_hai_ban(self):
        from scripts.control_center.locks import LockManager
        g = LockManager(self.a.store).xin(
            "demo", [(LockKind.FILESYSTEM, "web/admin")], task_id="A")
        self.assertTrue(g.granted)
        g2 = LockManager(self.b.store).xin(
            "demo", [(LockKind.FILESYSTEM, "web/admin/content-queue")],
            task_id="B")
        self.assertFalse(g2.granted, "khoá phải chặn qua ranh giới tiến trình")
        self.assertEqual(g2.conflict_holder_task, "A")


class TestWorktreeSafety(unittest.TestCase):
    """Bất biến: hai phiên KHÔNG BAO GIỜ cùng ghi một worktree."""

    def setUp(self):
        self.repo = kho_git_tam()
        self.cc = _cc(self.repo)

    def tearDown(self):
        self.cc.shutdown()

    def test_hai_phien_khong_the_cung_ghi_mot_worktree(self):
        from scripts.router_v3.worktree import WorktreeError
        wt = self.cc.ctx("demo").worktrees
        lease = wt.tao_moi(session_id="s1", task_id="t1")
        wt.assert_exclusive(lease.path, "s1")             # chủ thật thì được
        with self.assertRaises(WorktreeError):
            wt.assert_exclusive(lease.path, "s2")

    def test_cay_ban_TRONG_pham_vi_van_duoc_dung_lai(self):
        """Thay đổi chưa commit của CHÍNH phiên đó không cản việc dùng lại.

        Bản đầu tiên từ chối mọi cây bẩn. Nghe an toàn, nhưng một phiên giữ
        ấm qua nhiều việc gần như LUÔN để lại thay đổi chưa commit từ việc
        trước — nên nó không bao giờ dùng lại được cây, và cả ý tưởng "một
        phiên sở hữu một cây" mất sạch ý nghĩa.
        """
        wt = self.cc.ctx("demo").worktrees
        a = wt.tao_moi(session_id="s1", task_id="t1")
        (Path(a.path) / "web").mkdir(parents=True, exist_ok=True)
        (Path(a.path) / "web" / "wip.txt").write_text("dở dang",
                                                      encoding="utf-8")
        b = wt.ensure_for(session_id="s1", task_id="t2", scope=("web",))
        self.assertFalse(b.created, "thay đổi trong phạm vi -> dùng lại")
        self.assertEqual(a.path, b.path)

    def test_cay_ban_NGOAI_pham_vi_thi_cap_cay_moi(self):
        """Thay đổi ngoài phạm vi là dấu hiệu có thứ khác đang ghi vào cây."""
        wt = self.cc.ctx("demo").worktrees
        a = wt.tao_moi(session_id="s1", task_id="t1")
        (Path(a.path) / "server").mkdir(parents=True, exist_ok=True)
        (Path(a.path) / "server" / "la.txt").write_text("ngoài phạm vi",
                                                        encoding="utf-8")
        b = wt.ensure_for(session_id="s1", task_id="t2", scope=("web",))
        self.assertTrue(b.created)
        self.assertNotEqual(a.path, b.path)
        self.assertTrue(Path(a.path).exists(), "cây cũ KHÔNG bị xoá")
        self.assertEqual(self.cc.store.worktree(a.path)["state"], "DIRTY")

    def test_khong_hoi_duoc_git_thi_coi_la_dang_ngo(self):
        """`git` không trả lời -> KHÔNG dùng lại. Đoán 'sạch' là ghi đè
        công việc chưa lưu của agent trước — không hoàn tác được."""
        wt = self.cc.ctx("demo").worktrees
        wt.duong_dan_da_doi = lambda _p: None
        self.assertTrue(wt._ban_theo_cach_la("bất kỳ", ("web",)))

    def test_worktree_BAN_khong_duoc_dung_lai_nhung_cung_khong_bi_xoa(self):
        wt = self.cc.ctx("demo").worktrees
        a = wt.tao_moi(session_id="s1", task_id="t1")
        (Path(a.path) / "rac.txt").write_text("chưa commit", encoding="utf-8")
        self.assertTrue(wt.is_dirty(a.path))

        # `scope` rong = phien chua so huu pham vi ghi nao, nen MOI thay doi
        # deu la "ngoai pham vi".
        b = wt.ensure_for(session_id="s1", task_id="t2")
        self.assertTrue(b.created, "cây bẩn không được dùng lại")
        self.assertNotEqual(a.path, b.path)
        self.assertTrue(Path(a.path).exists(), "và cũng KHÔNG bị xoá")
        self.assertEqual(self.cc.store.worktree(a.path)["state"], "DIRTY")

    def test_cay_sach_cua_chinh_phien_do_duoc_dung_lai(self):
        wt = self.cc.ctx("demo").worktrees
        a = wt.tao_moi(session_id="s1", task_id="t1")
        b = wt.ensure_for(session_id="s1", task_id="t2")
        self.assertFalse(b.created)
        self.assertEqual(a.path, b.path)

    def test_go_bo_worktree_doi_XAC_NHAN_tuong_minh(self):
        from scripts.router_v3.worktree import WorktreeError
        wt = self.cc.ctx("demo").worktrees
        lease = wt.tao_moi(session_id="s1", task_id="t1")
        with self.assertRaises(WorktreeError):
            wt.go_bo(lease.path)
        self.assertTrue(Path(lease.path).exists(), "chưa xác nhận thì không xoá")

    def test_go_bo_TU_CHOI_duong_dan_ngoai_worktree_root(self):
        """Luật 'không tự xoá worktree' không đổi; đây là đường DUY NHẤT gỡ
        được, và nó chỉ gỡ trong `.router/worktrees/`."""
        import tempfile as _tf
        from scripts.router_v3.worktree import WorktreeError
        wt = self.cc.ctx("demo").worktrees
        ngoai = Path(_tf.mkdtemp(prefix="cc-ngoai-"))
        with self.assertRaises(WorktreeError):
            wt.go_bo(str(ngoai), xac_nhan=True, ly_do="thử")
        self.assertTrue(ngoai.exists(), "KHÔNG được đụng tới thư mục ngoài")

    def test_go_bo_TU_CHOI_thu_muc_LA_trong_worktree_root(self):
        """Một thư mục lạ nằm trong `.router/worktrees/` không phải thứ ta
        được phép xoá — nó không có hàng nào trong sổ."""
        from scripts.router_v3.worktree import WorktreeError
        wt = self.cc.ctx("demo").worktrees
        la = Path(wt.manager.worktree_root) / "khong-phai-cua-router"
        la.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(WorktreeError):
            wt.go_bo(str(la), xac_nhan=True, ly_do="thử")
        self.assertTrue(la.exists())

    def test_go_bo_TU_CHOI_khi_phien_chu_con_SONG(self):
        from scripts.control_center.model import Session, SessionState
        from scripts.router_v3.worktree import WorktreeError
        wt = self.cc.ctx("demo").worktrees
        lease = wt.tao_moi(session_id="s-song", task_id="t1")
        self.cc.store.luu_session(Session(
            session_id="s-song", project_id="demo", provider="antigravity",
            runtime_id="RT01", model_id="m-re", state=SessionState.BUSY))
        with self.assertRaises(WorktreeError):
            wt.go_bo(lease.path, xac_nhan=True, ly_do="thử")
        self.assertTrue(Path(lease.path).exists())

    def test_go_bo_CHAY_DUOC_khi_du_dieu_kien(self):
        """Siết chặt không được biến công cụ thành vô dụng."""
        wt = self.cc.ctx("demo").worktrees
        lease = wt.tao_moi(session_id="s1", task_id="t1")
        wt.nha("s1", note="xong")
        kq = wt.go_bo(lease.path, xac_nhan=True, ly_do="dọn bằng chứng")
        self.assertFalse(Path(lease.path).exists())
        self.assertEqual(kq["path"], lease.path)
        self.assertTrue([e for e in self.cc.store.su_kien(project_id="demo")
                         if e["kind"] == "WORKTREE_REMOVED"])

    def test_doi_soat_danh_dau_cay_bien_mat(self):
        import shutil
        wt = self.cc.ctx("demo").worktrees
        a = wt.tao_moi(session_id="s1", task_id="t1")
        shutil.rmtree(a.path, ignore_errors=True)
        bc = wt.doi_soat()
        self.assertIn(a.path, bc["missing"])
        self.assertEqual(self.cc.store.worktree(a.path)["state"], "STALE")

    def test_ten_viec_co_ky_tu_la_khong_thoat_ra_ngoai_thu_muc(self):
        """`../` trong task_id không được tạo worktree ngoài thư mục dự định."""
        wt = self.cc.ctx("demo").worktrees
        lease = wt.tao_moi(session_id="s1", task_id="../../thoat")
        goc = wt.manager.worktree_root.resolve()
        self.assertTrue(str(Path(lease.path).resolve()).startswith(str(goc)))


if __name__ == "__main__":
    unittest.main()

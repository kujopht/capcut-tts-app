# -*- coding: utf-8 -*-
"""NĂNG LỰC KHAI BÁO PHẢI ĐÚNG VỚI THỰC TẾ — V0.9.3.

Đo được 2026-09-13 trên `RouterDogfood02`. Việc Todo (có phạm vi ghi) thử
lượt 2 và bị bộ xếp chỗ đẩy sang `CODEX01`. Sau 226 giây, Codex trả:

    "Sandbox hệ thống chặn mọi thao tác ghi và không cho phép yêu cầu nâng
     quyền."
    "Không thể tạo hoặc sửa tệp vì workspace đang ở chế độ read-only."

`CodexAdapter` gọi `codex exec --skip-git-repo-check -m <model> --color
never -` — KHÔNG cờ sandbox nào, và `codex exec` mặc định chạy sandbox CHỈ
ĐỌC. Nhưng nó khai `capabilities={"review", "implement"}`. Bộ xếp chỗ tin
lời khai, nên nó gửi một việc GHI tới một runtime không ghi được.

Cùng hình dạng với khuyết tật phong bì quyền của chính bản này: **một tầng
quảng cáo thứ tầng dưới không làm được.**
"""

from __future__ import annotations

import unittest
from pathlib import Path


class TestCodexKhongKhaiGhi(unittest.TestCase):

    def _spec(self):
        from scripts.router_v3.pool.adapters import CodexAdapter
        return CodexAdapter(worker_id="CODEX-TEST",
                            model="codex-default").register()

    def test_01_codex_KHONG_khai_implement(self):
        self.assertNotIn("implement", self._spec().capabilities)

    def test_02_codex_VAN_khai_review(self):
        """Thu hẹp năng lực không được giết mất thế mạnh thật của Codex."""
        self.assertIn("review", self._spec().capabilities)

    def test_03_ghi_chu_NOI_RO_vi_sao(self):
        """Người đọc sau phải hiểu vì sao, không phải đoán."""
        self.assertIn("CHỈ ĐỌC", self._spec().notes)

    def test_04_adapter_KHONG_tu_bat_sandbox_ghi(self):
        """Cấp quyền ghi cho một CLI ngoài cần một lần xem xét riêng.

        Bài kiểm này khoá lại rằng bản vá đêm KHÔNG lặng lẽ bật
        `--sandbox workspace-write`. Muốn bật thì phải là một thay đổi có
        chủ ý, có probe, có người duyệt — không phải một dòng lọt vào giữa
        một bản sửa phạm vi ghi.
        """
        from pathlib import Path
        goc = Path(__file__).resolve().parents[2]
        van = (goc / "scripts" / "router_v3" / "pool" / "adapters.py").read_text(
            encoding="utf-8")
        i = van.index("exec\", \"--skip-git-repo-check\"")
        khoi = van[i:i + 220]
        self.assertNotIn("--sandbox", khoi)
        self.assertNotIn("--dangerously", khoi)
        self.assertNotIn("--full-auto", khoi)


class TestViecGhiDoiRuntimeGhiDuoc(unittest.TestCase):
    """Rào CỨNG: việc có phạm vi ghi không được xếp vào chỗ không ghi được.

    Đi qua ĐÚNG cơ chế đã có (`refuses` trong `fabric.json` ->
    `_cam_runtime_theo_nang_luc` -> `cam`), nên nó chặn CẢ lượt tạo phiên
    mới LẪN lượt DÙNG LẠI phiên ấm — chính chỗ lượt thứ hai đã lọt qua.
    """

    def test_05_viec_GHI_doi_nang_luc_repo_write(self):
        from scripts.control_center.nang_luc import REPO_WRITE, nang_luc_viec
        self.assertIn(REPO_WRITE,
                      nang_luc_viec({"type": "testing",
                                     "allowed_scope": ["."]}))
        self.assertIn(REPO_WRITE,
                      nang_luc_viec({"requirements": {"repo_write": True}}))

    def test_06_viec_CHI_DOC_khong_doi_gi_them(self):
        """Không được thu hẹp ngoài đúng chỗ cần."""
        from scripts.control_center.nang_luc import REPO_WRITE, nang_luc_viec
        self.assertNotIn(REPO_WRITE,
                         nang_luc_viec({"type": "analysis",
                                        "title": "xem kiến trúc"}))

    def test_07_fabric_khai_CODEX01_tu_choi_ghi(self):
        import json
        from pathlib import Path
        goc = Path(__file__).resolve().parents[2]
        cfg = json.loads(
            (goc / "scripts" / "router_v4" / "config" / "fabric.json")
            .read_text(encoding="utf-8"))
        codex = [r for r in cfg["runtimes"]
                 if r.get("runtime_id") == "CODEX01"]
        self.assertTrue(codex, "không còn runtime CODEX01?")
        self.assertIn("repo_write", codex[0].get("refuses") or [])
        self.assertTrue((codex[0].get("refuses_notes") or "").strip(),
                        "một lời từ chối phải nói được VÌ SAO")


class TestRaoCanKhongDuocIM_LANG_CHET(unittest.TestCase):
    """Rào cấm phải NHẬN được `TaskContract`, không chỉ `dict`.

    KHUYẾT TẬT NẶNG NHẤT tìm được đêm nay. `_cam_runtime_theo_nang_luc` viết:

        can = NL.nang_luc_viec(hd if isinstance(hd, dict) else {})

    Chỗ gọi DUY NHẤT của nó (`_giao_khong_luoi`) bình
    `hd = TaskContract.from_dict(...)` — một ĐỐI TƯỢNG. Nên vế `else` luôn
    đúng, `nang_luc_viec({})` trả rỗng, và hàm trả `()` mọi lần. Rào chưa
    bao giờ chặn một lần xếp chỗ nào.

    Đo được: một việc GHI bị xếp vào CODEX01 ba lần liên tiếp dù CODEX01 đã
    khai `refuses: ["repo_write"]`; vết quyết định không hề có dòng
    "năng lực: CẤM".

    Nặng hơn phạm vi của bản vá này: rào ấy CŨNG là đường thi hành
    `security_review` của V0.7 — thứ giữ cho việc hình dạng bảo mật không
    rơi vào Codex (Codex trả kết quả rỗng cho loại việc đó, bằng chứng
    2026-08-28). Nó đã chết cùng một cách, và im lặng y hệt.

    Một phép phòng thủ biến rào an toàn thành hàm rỗng là kiểu hỏng tệ nhất:
    mọi thứ trông như bình thường.
    """

    def _hd(self, **kw):
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import TaskContract
        d = dict(task_id="t1", objective="Triển khai ứng dụng Web Todo",
                 type="testing", allowed_scope=(".",),
                 requirements=Requirements(repo_write=True))
        d.update(kw)
        return TaskContract(**d)

    def setUp(self):
        import shutil
        import subprocess
        import tempfile
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        self._tmp = Path(tempfile.mkdtemp(prefix="rao-can-"))
        kho = self._tmp / "kho"
        kho.mkdir()
        subprocess.run(["git", "-C", str(kho), "init", "-q"],
                       capture_output=True)
        self.cc = ControlCenter(root=self._tmp / "data", probe=False,
                                leader_bat=False)
        self.cc.them_project(Project(project_id="p", name="P",
                                     repo_path=str(kho)))
        self._rmtree = shutil.rmtree

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            self._rmtree(self._tmp, ignore_errors=True)

    def test_08_nang_luc_viec_doc_duoc_tu_TaskContract(self):
        """`to_dict()` của hợp đồng phải mang đủ thứ rào cần."""
        from scripts.control_center.nang_luc import REPO_WRITE, nang_luc_viec
        d = self._hd().to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn(REPO_WRITE, nang_luc_viec(d))

    def test_09_rao_can_CHAN_khi_nhan_doi_tuong_hop_dong(self):
        """Đi qua chính `_cam_runtime_theo_nang_luc`, với ĐỐI TƯỢNG.

        Đây là hình dạng THẬT ở chỗ gọi duy nhất — và là hình dạng đã làm
        rào im lặng chết.
        """
        ctx = self.cc.ctx("p")
        cam, ly_do = self.cc._cam_runtime_theo_nang_luc(ctx, self._hd())
        self.assertIn("CODEX01", cam,
                      "rào năng lực im lặng chết khi nhận TaskContract")
        self.assertIn("repo_write", ly_do)

    def test_10_rao_can_van_hoat_dong_voi_dict(self):
        """Không được sửa kiểu này mà làm hỏng kiểu kia."""
        ctx = self.cc.ctx("p")
        cam, _ = self.cc._cam_runtime_theo_nang_luc(
            ctx, {"type": "testing", "allowed_scope": ["."]})
        self.assertIn("CODEX01", cam)

    def test_11_viec_CHI_DOC_khong_bi_chan_oan(self):
        from scripts.router_v4.capabilities import Requirements
        ctx = self.cc.ctx("p")
        hd = self._hd(allowed_scope=(), objective="xem kiến trúc hiện tại",
                      type="analysis", requirements=Requirements())
        cam, _ = self.cc._cam_runtime_theo_nang_luc(ctx, hd)
        self.assertEqual(tuple(cam), ())

    def test_12_rao_BAO_MAT_cua_V07_cung_song_lai(self):
        """Cùng một rào cũng thi hành `security_review` — nó cũng đã chết.

        V0.7 thêm rào này để việc hình dạng bảo mật không rơi vào Codex
        (Codex trả kết quả RỖNG cho loại việc đó — bằng chứng 2026-08-28).
        Vì `isinstance(hd, dict)` luôn sai ở chỗ gọi thật, lớp bảo vệ đó
        cũng chưa từng chạy.
        """
        from scripts.router_v4.capabilities import Requirements
        ctx = self.cc.ctx("p")
        hd = self._hd(objective="rà soát phân quyền IAM và xoay khoá bí mật",
                      type="security_review", allowed_scope=(),
                      requirements=Requirements())
        cam, _ = self.cc._cam_runtime_theo_nang_luc(ctx, hd)
        self.assertIn("CODEX01", cam,
                      "việc hình dạng bảo mật vẫn rơi được vào Codex")


if __name__ == "__main__":
    unittest.main()

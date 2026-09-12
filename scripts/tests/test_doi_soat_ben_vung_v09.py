# -*- coding: utf-8 -*-
"""BẤT BIẾN: đối soát ĐẠT thì BẢN GHI BỀN phải đồng ý — sau khi nạp lại.

Khuyết tật đo được trên Fanfic thật (`ex_b6072e6a1522` và bốn lần chạy khác,
2026-09-12), tái hiện 5/5 lần:

* worker làm việc THẬT thành công (tệp đúng nằm trong worktree cô lập);
* cổng `diff` hỏng vì worker khai thiếu (`changes` rỗng);
* `_doi_soat_khai_thieu` đối soát với `git` và trả `True`;
* việc chuyển `RUNNING -> DONE`;
* `pb.status` là `"ok"` ngay trước khi ghi;

**nhưng sau khi ghi + nạp lại**, `result["envelope"]["status"]` vẫn là
`"failed"` và `failure_reason` vẫn là `"gate_diff"`. Tầng BƯỚC đọc bản ghi
bền đó, kết luận bước HỎNG, và đi SỬA CHỮA một việc ĐÃ XONG — rồi cạn ngân
sách và `BLOCKED`.

Bài kiểm này đi ĐÚNG đường `_chay` của production và **không giả lập ranh
giới lưu trữ đang bị điều tra**: kho thật, sổ SQLite thật, `ghi_ket_qua`
thật, và đọc lại bằng `store.task()`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.router_v3.pool import validation as V
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.envelope import ResultEnvelope
from scripts.router_v4.executor import ExecutionResult
from scripts.router_v4.runtime import Placement

from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project, TaskState

from scripts.tests.test_control_center_slice import (_xong, fabric_gia,
                                                     kho_git_tam)

#: Tệp mà "worker" thật sự ghi — trong phạm vi cho phép của việc.
TEP = "ghi-chu.md"


class ExecutorKhaiThieu:
    """Tái hiện ĐÚNG hình dạng đã quan sát trên lần chạy thật.

    Ba tính chất phải đúng cùng lúc, và chính sự kết hợp đó mới sinh ra lỗi:

    1. **ghi THẬT** vào worktree cô lập (nên `git status` thấy tệp đổi);
    2. **khai RỖNG** (`changes=[]`) — đúng thứ `cong_diff` gọi là
       "worker không khai sửa gì nhưng đĩa đổi";
    3. phong bì đã mang `status="failed"` + `failure_reason="gate_diff"`,
       vì `Executor.run` của V4 đặt sẵn hai trường đó khi một cổng hỏng.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, object] = {}
        self.worktree_provider = None
        self.da_chay: List[str] = []

    def run(self, c: TaskContract, p: Placement, *, base_sha: str = "",
            dependency_summaries=None, dependency_workspaces=None,
            attempt: int = 1, reassigned: bool = False) -> ExecutionResult:
        self.da_chay.append(c.task_id)
        h = None
        if c.execution.worktree_required and self.worktree_provider is not None:
            h = self.worktree_provider(c, p, base_sha, attempt)
        duong = str(h.path) if h is not None else ""

        pv = c.allowed_scope[0] if c.allowed_scope else ""
        tuong_doi = f"{pv}/{TEP}" if pv else TEP
        if duong:
            tep = Path(duong) / tuong_doi
            tep.parent.mkdir(parents=True, exist_ok=True)
            tep.write_text("# ghi chú\nV09-DOI-SOAT-BEN-VUNG\n",
                           encoding="utf-8")

        pb = ResultEnvelope(
            task_id=c.task_id,
            status="failed",                 # Executor V4 đã hạ trạng thái
            failure_reason="gate_diff",      # ... và ghi lý do là cổng `diff`
            summary="đã tạo tệp ghi chú theo yêu cầu",
            worker=p.runtime_id, model=p.model_id, provider="antigravity",
            duration=0.01,
            changes=[],                      # KHAI RỖNG — mấu chốt
            artifacts=[tuong_doi])

        bc = V.ValidationReport(
            gates=[
                V.GateResult("shape", True, "status=failed"),
                V.GateResult(
                    "diff", False,
                    f"worker không khai sửa gì nhưng đĩa đổi ['{tuong_doi}']"),
                V.GateResult("scope", True, "trong phạm vi"),
                V.GateResult("security", True,
                             "không thấy bí mật, không đụng đường cấm"),
                V.GateResult("tests", True, "không yêu cầu test"),
                V.GateResult("artifacts", True, "đủ hiện vật"),
            ],
            files_changed_observed=[tuong_doi],
            scope_violations=[])
        return ExecutionResult(envelope=pb, validation=bc, worktree=duong,
                               branch=h.branch if h is not None else "")

    def shutdown(self) -> None:
        pass


class TestDoiSoatBenVung(unittest.TestCase):
    """Bản ghi BỀN phải đồng ý với kết luận của đối soát."""

    def setUp(self):
        self.repo = kho_git_tam()
        self.ex = ExecutorKhaiThieu()
        self.cc = ControlCenter(
            root=self.repo, fabric=fabric_gia(), probe=False, max_parallel=3,
            executor_factory=lambda p, f: self.ex)
        self.cc.them_project(Project(
            project_id="demo", name="Demo", repo_path=str(self.repo),
            resources=("write:docs",)))

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            shutil.rmtree(self.repo, ignore_errors=True)

    def _chay_mot_viec(self) -> str:
        """Tạo MỘT việc có ghi, chạy hết đường `_chay` thật, trả `task_id`."""
        self.cc.chat("demo", "viết một ghi chú vào docs")
        ds = [t for t in self.cc.store.tasks("demo")]
        self.assertTrue(ds, "không tạo được việc nào")
        t = ds[0]
        self.cc._giao(t)
        self.assertTrue(_xong(self.cc, t.task_id, giay=30),
                        "việc không về trạng thái cuối")
        return t.task_id

    # -- BẤT BIẾN CHÍNH ----------------------------------------------------
    def test_01_doi_soat_dat_thi_ban_ghi_BEN_phai_dong_y(self):
        ma = self._chay_mot_viec()
        t = self.cc.store.task(ma)               # NẠP LẠI từ sổ thật
        pb = (t.result or {}).get("envelope") or {}

        self.assertIs(t.state, TaskState.DONE,
                      f"việc phải DONE sau đối soát, đang là {t.state.value}")
        self.assertEqual(pb.get("status"), "ok",
                         "phong bì BỀN vẫn nói 'failed' sau khi đối soát ĐẠT "
                         "— tầng bước sẽ đi sửa một việc đã xong")
        self.assertFalse(pb.get("failure_reason"),
                         f"`failure_reason` chưa được xoá: "
                         f"{pb.get('failure_reason')!r}")

    def test_02_bang_chung_doi_soat_duoc_GIU_LAI(self):
        """Chữa trạng thái không được làm mất dấu vết vì sao nó được chữa."""
        ma = self._chay_mot_viec()
        pb = (self.cc.store.task(ma).result or {}).get("envelope") or {}
        canh = " ".join(pb.get("warnings") or ())
        self.assertIn("đối soát", canh.lower(),
                      "mất bằng chứng đối soát trong bản ghi bền")
        self.assertTrue(pb.get("changes"),
                        "`changes` phải được điền lại bằng tập THẬT")

    def test_03_trang_thai_viec_va_phong_bi_KHONG_duoc_mau_thuan(self):
        """Bất biến tổng quát — hai cái nhìn về cùng một sự thật."""
        ma = self._chay_mot_viec()
        t = self.cc.store.task(ma)
        pb = (t.result or {}).get("envelope") or {}
        if t.state is TaskState.DONE:
            self.assertEqual(pb.get("status"), "ok")
        if pb.get("status") == "failed":
            self.assertIsNot(t.state, TaskState.DONE)

    def test_04_nap_lai_nhieu_lan_van_the(self):
        """Đọc lại không được đổi câu trả lời (không có cache nói khác sổ)."""
        ma = self._chay_mot_viec()
        ds = [((self.cc.store.task(ma).result or {}).get("envelope") or {})
              .get("status") for _ in range(3)]
        self.assertEqual(ds, ["ok", "ok", "ok"], ds)

    def test_05_khong_sinh_viec_SUA_CHUA_sau_khi_doi_soat_dat(self):
        """Tầng sửa chữa không được chạm vào một việc đã xong."""
        ma = self._chay_mot_viec()
        them = [t.task_id for t in self.cc.store.tasks("demo")
                if t.task_id != ma]
        self.assertEqual(them, [],
                         f"sinh thêm việc sau một lần đối soát ĐẠT: {them}")
        self.assertEqual(len(self.ex.da_chay), 1,
                         f"worker bị gọi lại: {self.ex.da_chay}")


class TestDoiSoatSongSotTangBuoc(unittest.TestCase):
    """Bản ghi đã đối soát phải sống sót qua ĐƯỜNG TẦNG BƯỚC ĐỘNG VÀO NÓ.

    Bài kiểm ở lớp trên dừng ngay sau khi `_chay` ghi xong, và nó XANH. Lần
    chạy thật thì KHÔNG dừng ở đó: ngay sau `TASK_FINISHED DONE` còn có
    `TASK_ABANDONED` rồi `DONE -> FAILED`. Khác biệt duy nhất giữa bài kiểm
    xanh và lần chạy hỏng nằm ở khúc đuôi đó, nên khúc đuôi phải được kiểm.

    `luu_task` ghi **mọi** cột, kể cả `result_json` (store.py). Nên bất kỳ
    đường nào đọc `Task`, sửa một trường, rồi `luu_task` sẽ ghi đè luôn kết
    quả — đúng chế độ hỏng "đọc–sửa–ghi" mà docstring của `ghi_ket_qua` cảnh
    báo cho `state`, nhưng nó áp cho `result` y hệt.
    """

    def setUp(self):
        self.repo = kho_git_tam()
        self.ex = ExecutorKhaiThieu()
        self.cc = ControlCenter(
            root=self.repo, fabric=fabric_gia(), probe=False, max_parallel=3,
            executor_factory=lambda p, f: self.ex)
        self.cc.them_project(Project(
            project_id="demo", name="Demo", repo_path=str(self.repo),
            resources=("write:docs",)))

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            shutil.rmtree(self.repo, ignore_errors=True)

    def _viec_da_doi_soat(self) -> str:
        self.cc.chat("demo", "viết một ghi chú vào docs")
        t = self.cc.store.tasks("demo")[0]
        self.cc._giao(t)
        self.assertTrue(_xong(self.cc, t.task_id, giay=30))
        pb = (self.cc.store.task(t.task_id).result or {}).get("envelope") or {}
        self.assertEqual(pb.get("status"), "ok", "tiền đề sai — chưa đối soát")
        return t.task_id

    def test_06_tang_buoc_bo_viec_KHONG_duoc_lam_hong_ket_qua_da_doi_soat(self):
        """Đây là khúc mà lần chạy thật đi qua còn bài kiểm trước thì không."""
        ma = self._viec_da_doi_soat()
        self.cc._dung_viec_cua_thuc_thi(ma, "lập lại kế hoạch v1 -> v2")
        pb = (self.cc.store.task(ma).result or {}).get("envelope") or {}
        self.assertEqual(
            pb.get("status"), "ok",
            "tầng bước bỏ việc đã GHI ĐÈ kết quả đã đối soát — bản ghi bền "
            "quay về 'failed' và tầng bước sẽ đi sửa một việc đã xong")
        self.assertFalse(pb.get("failure_reason"))

    def test_07_khong_duoc_bo_mot_viec_ma_ket_qua_da_THANH_CONG(self):
        """§4: tầng sửa chữa không bao giờ được sửa một việc đã xong.

        Đây là bất biến thật sự cần giữ, không phải chuyện bảo toàn byte:
        một việc có hợp đồng kết quả THÀNH CÔNG thì tầng bước phải đọc ra
        'xong' và đi tiếp, chứ không phải bỏ nó rồi giao lại.
        """
        ma = self._viec_da_doi_soat()
        from scripts.control_center.execution.ket_qua import tu_envelope
        from scripts.router_v4.envelope import ResultEnvelope as RE
        pb = (self.cc.store.task(ma).result or {}).get("envelope") or {}
        self.assertTrue(tu_envelope(RE.from_dict(pb), buoc_id="b").ok,
                        "hợp đồng kết quả mà tầng bước đọc vẫn nói HỎNG")


class TestTienKiemNghiemThu(unittest.TestCase):
    """Nghiệm thu phải TỪ CHỐI CHẠY khi còn Control Center khác trên sổ.

    KHÔNG cấm hai tiến trình — `TestHaiTienTrinh` khoá lại rằng hai Control
    Center trên một sổ là chuyện BÌNH THƯỜNG, và các bất biến loại trừ được
    thiết kế cho đúng cảnh đó. Thứ không chấp nhận được là ĐO trong lúc đó:
    một tiến trình khác giành việc rồi chạy bằng mã CỦA NÓ — có thể là bản
    cũ — nên mọi khẳng định mất nghĩa.

    Đo được 2026-09-12: `desktop` pid 11620 và `webmain` pid 34188 còn sống
    từ hôm trước làm hỏng NĂM lần chạy liên tiếp.
    """

    def _tim(self, ds, pid_minh=999):
        from scripts.control_center_v09_real_acceptance import (
            tien_trinh_cc_khac)
        return tien_trinh_cc_khac(liet_ke=lambda: ds, pid_minh=pid_minh)

    def test_08_bat_duoc_desktop_va_webmain_con_song(self):
        thay = self._tim([
            (11620, r'"C:\pythonw.exe" -m scripts.control_center.desktop'),
            (34188, r'"C:\python.exe" -m scripts.control_center.webmain '
                    r'--khong-mo --port 55523'),
        ])
        self.assertEqual(sorted(x[0] for x in thay), [11620, 34188])

    def test_09_KHONG_bat_nham_tien_trinh_khong_lien_quan(self):
        """Chữ "desktop" một mình từng khớp cả ChatGPT Desktop."""
        thay = self._tim([
            (4292, r'"C:\Program Files\WindowsApps\OpenAI.ChatGPT-Desktop'
                   r'\ChatGPT Classic.exe"'),
            (28460, r'".venv\Scripts\python.exe" -m server.worker '
                    r'--require-env production'),
            (777, "notepad.exe"),
        ])
        self.assertEqual(thay, [], thay)

    def test_10_khong_tu_dem_chinh_no(self):
        """Bộ nghiệm thu và bài kiểm của nó không phải "tiến trình khác"."""
        thay = self._tim([
            (999, "python scripts/control_center_v09_real_acceptance.py"),
            (1000, "python -m unittest scripts.tests.test_x"),
            (1001, "python scripts/control_center_v09_real_acceptance.py "
                   "--kich-ban C"),
        ], pid_minh=999)
        self.assertEqual(thay, [], thay)

    def test_11_hai_Control_Center_VAN_duoc_phep_cung_ton_tai(self):
        """Bất biến CŨ không được phá: hai bản trên một sổ vẫn mở được.

        Đây là vế đối xứng của bài kiểm trên. Một bản sửa "cấm người ghi thứ
        hai" sẽ làm bài kiểm này hỏng — và nó đã hỏng thật một lần, làm rơi
        năm bài của `TestHaiTienTrinh`.
        """
        repo = kho_git_tam()
        try:
            a = ControlCenter(root=repo, fabric=fabric_gia(), probe=False,
                              executor_factory=lambda p, f: ExecutorKhaiThieu())
            b = ControlCenter(root=repo, fabric=fabric_gia(), probe=False,
                              executor_factory=lambda p, f: ExecutorKhaiThieu())
            try:
                a.chat("demo2", "x") if False else None
                self.assertIsNotNone(b.store)
            finally:
                a.shutdown()
                b.shutdown()
        finally:
            shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""CHỜ TÀI NGUYÊN — nghiệm thu V1.0.

Hết hạn mức KHÔNG phải `FAILED`, KHÔNG phải `BLOCKED`, KHÔNG phải
`WAITING_AUTHORITY`. Ba trạng thái ấy đều nói dối, mỗi cái một kiểu — xem
`model.TaskState.WAITING_RESOURCE`.

Bộ kiểm dùng FIXTURE TẤT ĐỊNH, không đốt hạn mức thật để dựng lại cảnh cạn:
`quyet_dinh` là hàm thuần, nên ba kịch bản A/B/C dựng được bằng dữ liệu.
"""
from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from scripts.control_center.model import (Project, Task, TaskState,
                                          _CHUYEN_HOP_LE)
from scripts.control_center.store import ControlStore
from scripts.control_center.v10.han_muc import BeQuota, SucKhoe
from scripts.control_center.v10.su_co_ben import SoSuCo, SuCoBen
from scripts.control_center.v10.tai_nguyen import (TRAN_CHO_GIAY,
                                                   TRAN_CHO_RESET,
                                                   HanhDongTaiNguyen,
                                                   YeuCauVai, quyet_dinh)

GIO = time.time()


def _be(ten, *, ho=(), suc_khoe=SucKhoe.UNKNOWN, reset=None, con_lai=None,
        provider="antigravity", acc=""):
    return BeQuota(ten=ten, account_id=acc or ten, provider=provider,
                   ho_model=tuple(ho), suc_khoe=suc_khoe, reset_luc=reset,
                   con_lai=con_lai)


# ==========================================================================
# 1. BA KỊCH BẢN CHỦ SỞ HỮU NÊU ĐÍCH DANH
# ==========================================================================
class TestBaKichBan(unittest.TestCase):

    def test_A_con_duong_hop_le_thi_TU_DOI_CHO(self):
        """AG Claude cạn, còn Gemini hợp lệ -> Router tự định tuyến lại."""
        hong = _be("AG02", ho=("claude",), suc_khoe=SucKhoe.EXHAUSTED,
                   reset=GIO + 3600)
        qd = quyet_dinh(hong, [hong, _be("AG05", ho=("gemini",))],
                        bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.DOI_CHO)
        self.assertEqual(qd.be_chon, "AG05")
        self.assertFalse(qd.can_chu_so_huu,
                         "còn đường thì KHÔNG được đánh thức chủ sở hữu")

    def test_B_het_duong_co_moc_thi_CHO_RESET(self):
        """Không còn đường, reset ĐO ĐƯỢC -> giữ việc, hẹn giờ."""
        hong = _be("AG02", ho=("claude",), suc_khoe=SucKhoe.EXHAUSTED,
                   reset=GIO + 1800)
        qd = quyet_dinh(hong, [hong], bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.CHO_RESET)
        self.assertEqual(qd.cho_toi, GIO + 1800)
        self.assertFalse(qd.can_chu_so_huu)
        self.assertIn("KHÔNG mua thêm credit", qd.ly_do)

    def test_C_het_duong_khong_moc_thi_LEO_THANG(self):
        """Không đường, không mốc -> gọi người, KHÔNG thử lại vô hạn."""
        hong = _be("AG02", ho=("claude",), suc_khoe=SucKhoe.EXHAUSTED)
        qd = quyet_dinh(hong, [hong], bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.LEO_THANG)
        self.assertTrue(qd.can_chu_so_huu)
        self.assertIsNone(qd.cho_toi, "không đo được thì KHÔNG bịa một mốc")


# ==========================================================================
# 2. RANH GIỚI KHÔNG ĐƯỢC VƯỢT
# ==========================================================================
class TestRanhGioi(unittest.TestCase):

    def test_01_KHONG_BAO_GIO_goi_y_mua_them(self):
        """Không một kết cục nào được dẫn tới mua credit/bật overage."""
        for cac in ([_be("A", suc_khoe=SucKhoe.EXHAUSTED)],
                    [_be("A", suc_khoe=SucKhoe.EXHAUSTED, reset=GIO + 60)],
                    [_be("A", suc_khoe=SucKhoe.EXHAUSTED), _be("B")]):
            qd = quyet_dinh(cac[0], cac, bay_gio=GIO)
            v = qd.ly_do.lower()
            self.assertNotIn("mua thêm credit đi", v)
            for cam in ("overage", "upgrade", "purchase"):
                self.assertNotIn(cam, v, f"{cam!r} không được xuất hiện")

    def test_02_KHONG_ha_chuan_de_di_tiep(self):
        """Bể cùng họ với người viết KHÔNG được dùng cho vai đòi độc lập."""
        hong = _be("AG02", ho=("gemini",), suc_khoe=SucKhoe.EXHAUSTED)
        khac = _be("AG07", ho=("gemini",))
        qd = quyet_dinh(hong, [hong, khac],
                        yeu_cau=YeuCauVai(ho_bi_cam=("gemini",),
                                          doi_doc_lap=True),
                        bay_gio=GIO)
        self.assertIsNot(qd.hanh_dong, HanhDongTaiNguyen.DOI_CHO,
                         "đổi sang CÙNG HỌ là lặng lẽ xoá mất tính độc lập")
        self.assertTrue(any("độc lập" in x[1] for x in qd.da_xet))

    def test_02b_khac_ho_thi_van_di_duoc(self):
        """Thu hẹp không được nuốt luôn đường hợp lệ."""
        hong = _be("AG02", ho=("gemini",), suc_khoe=SucKhoe.EXHAUSTED)
        qd = quyet_dinh(hong, [hong, _be("CODEX01", ho=("codex",),
                                         provider="codex")],
                        yeu_cau=YeuCauVai(ho_bi_cam=("gemini",),
                                          doi_doc_lap=True),
                        bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.DOI_CHO)
        self.assertEqual(qd.be_chon, "CODEX01")

    def test_03_can_dang_nhap_lai_KHONG_phai_duong_tu_di(self):
        """Thêm credential là ranh giới thẩm quyền, không phải fallback."""
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED)
        qd = quyet_dinh(hong, [hong, _be("AG03",
                                         suc_khoe=SucKhoe.AUTH_REQUIRED)],
                        bay_gio=GIO)
        self.assertIsNot(qd.hanh_dong, HanhDongTaiNguyen.DOI_CHO)
        self.assertTrue(any("thẩm quyền" in x[1] for x in qd.da_xet))

    def test_04_UNKNOWN_van_dung_duoc(self):
        """Loại bể không đo được là tự bỏ đói mình — phần lớn không phơi số."""
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED)
        qd = quyet_dinh(hong, [hong, _be("AG04", suc_khoe=SucKhoe.UNKNOWN)],
                        bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.DOI_CHO)

    def test_05_uu_tien_be_DO_DUOC_truoc_be_UNKNOWN(self):
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED)
        qd = quyet_dinh(hong, [hong, _be("AG04", suc_khoe=SucKhoe.UNKNOWN),
                               _be("AG09", suc_khoe=SucKhoe.HEALTHY,
                                   con_lai=90.0)],
                        bay_gio=GIO)
        self.assertEqual(qd.be_chon, "AG09")

    def test_06_cho_co_lich_van_phai_co_DAY(self):
        """Một bể cứ hứa reset rồi lại cạn là một vòng lặp CHẬM."""
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED, reset=GIO + 600)
        qd = quyet_dinh(hong, [hong], da_cho=TRAN_CHO_RESET, bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.LEO_THANG)
        self.assertTrue(qd.can_chu_so_huu)

    def test_07_moc_qua_xa_thi_BAO_nguoi_chu_khong_im_lang_ngu(self):
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED,
                   reset=GIO + TRAN_CHO_GIAY + 60)
        qd = quyet_dinh(hong, [hong], bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.LEO_THANG)
        self.assertEqual(qd.cho_toi, GIO + TRAN_CHO_GIAY + 60,
                         "vẫn NÊU mốc đo được, chỉ là không tự im lặng chờ")

    def test_08_moc_da_qua_KHONG_duoc_tinh_la_moc(self):
        hong = _be("AG02", suc_khoe=SucKhoe.EXHAUSTED, reset=GIO - 10)
        qd = quyet_dinh(hong, [hong], bay_gio=GIO)
        self.assertIs(qd.hanh_dong, HanhDongTaiNguyen.LEO_THANG)


# ==========================================================================
# 3. MÁY TRẠNG THÁI
# ==========================================================================
class TestMayTrangThai(unittest.TestCase):

    def test_09_WAITING_RESOURCE_khong_di_duoc_toi_DONE(self):
        di = _CHUYEN_HOP_LE[TaskState.WAITING_RESOURCE]
        self.assertNotIn(TaskState.DONE, di)
        self.assertNotIn(TaskState.REVIEW, di)
        self.assertIn(TaskState.QUEUED, di, "phải chạy tiếp được")
        self.assertIn(TaskState.BLOCKED, di, "phải leo thang được")

    def test_10_KHONG_phai_needs_human(self):
        """Chờ tài nguyên KHÔNG được hiện ra như 'đang chờ TÔI'."""
        self.assertFalse(TaskState.WAITING_RESOURCE.needs_human)
        self.assertTrue(TaskState.WAITING_RESOURCE.cho_tai_nguyen)
        self.assertFalse(TaskState.WAITING_RESOURCE.terminal)
        self.assertFalse(TaskState.BLOCKED.cho_tai_nguyen)

    def test_11_KHO_THAT_nhan_duong_di_va_ve(self):
        goc = Path(tempfile.mkdtemp(prefix="cc-ctn-"))
        try:
            st = ControlStore(root=goc)
            st.luu_project(Project(project_id="demo", name="D",
                                   repo_path=str(goc)))
            t = Task(task_id="demo.x-1", project_id="demo", title="V",
                     objective="mục tiêu gốc", state=TaskState.QUEUED)
            st.luu_task(t)
            st.doi_trang_thai(t.task_id, TaskState.RUNNING, force=True)
            st.doi_trang_thai(t.task_id, TaskState.FAILED)
            st.doi_trang_thai(t.task_id, TaskState.WAITING_RESOURCE,
                              reason="hết hạn mức AG02")
            self.assertIs(st.task(t.task_id).state,
                          TaskState.WAITING_RESOURCE)
            st.doi_trang_thai(t.task_id, TaskState.QUEUED,
                              reason="tài nguyên đã sẵn sàng")
            self.assertIs(st.task(t.task_id).state, TaskState.QUEUED)
            self.assertEqual(st.task(t.task_id).objective, "mục tiêu gốc",
                             "mục tiêu GỐC vẫn thuộc về CHÍNH việc này")
        finally:
            shutil.rmtree(goc, ignore_errors=True)


# ==========================================================================
# 4. BỀN QUA KHỞI ĐỘNG LẠI
# ==========================================================================
class TestBenQuaKhoiDongLai(unittest.TestCase):

    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-ctn-ben-"))
        self.st = ControlStore(root=self.goc)
        self.st.luu_project(Project(project_id="demo", name="D",
                                    repo_path=str(self.goc)))

    def tearDown(self):
        shutil.rmtree(self.goc, ignore_errors=True)

    def _ho_so(self):
        return SuCoBen(
            incident_id="sc_tn", project_id="demo", task_id="demo.x-1",
            muc_tieu="mục tiêu gốc", execution_id="ex_1",
            be_tai_nguyen="AG02", provider="antigravity", account_id="AG02",
            ly_do_tai_nguyen="Individual quota reached. Resets in 48h57m19s",
            reset_luc=GIO + 1800, thu_lai_luc=GIO + 1800,
            ung_vien_da_xet=(("AG03", "đã cạn"),), dem_cho_tai_nguyen=2,
            da_dung={"sua_tai_cho": 1})

    def test_12_moi_truong_tai_nguyen_song_sot(self):
        so = SoSuCo(self.st)
        so.ghi(self._ho_so())
        # Tiến trình MỚI: một `SoSuCo` khác đọc lại từ cùng quyển sổ.
        sc = SoSuCo(ControlStore(root=self.goc)).hien_tai("demo.x-1")
        self.assertIsNotNone(sc)
        self.assertEqual(sc.incident_id, "sc_tn")
        self.assertEqual(sc.muc_tieu, "mục tiêu gốc")
        self.assertEqual(sc.execution_id, "ex_1")
        self.assertEqual(sc.be_tai_nguyen, "AG02")
        self.assertEqual(sc.provider, "antigravity")
        self.assertIn("quota reached", sc.ly_do_tai_nguyen)
        self.assertEqual(sc.reset_luc, GIO + 1800)
        self.assertEqual(sc.thu_lai_luc, GIO + 1800)
        self.assertEqual(sc.ung_vien_da_xet, (("AG03", "đã cạn"),))

    def test_13_NGAN_SACH_cho_KHONG_bi_nap_lai(self):
        """Đếm chờ phải TIẾN qua các lần chạy, nếu không trần là vô nghĩa."""
        so = SoSuCo(self.st)
        so.ghi(self._ho_so())
        sc = SoSuCo(ControlStore(root=self.goc)).hien_tai("demo.x-1")
        self.assertEqual(sc.dem_cho_tai_nguyen, 2)
        self.assertEqual(sc.da_dung, {"sua_tai_cho": 1})

    def test_14_KHONG_DO_DUOC_thi_van_la_None_sau_khi_doc_lai(self):
        """`None` phải đi ra `None` — không được biến thành `0.0`.

        `float(d.get(...) or 0)` là cách một mốc KHÔNG ĐO ĐƯỢC biến thành
        mốc 1970, và một mốc quá khứ nghĩa là "tới giờ rồi" -> đánh thức
        ngay -> thử lại mù có lịch.
        """
        hs = self._ho_so()
        hs.reset_luc = None
        hs.thu_lai_luc = None
        SoSuCo(self.st).ghi(hs)
        sc = SoSuCo(ControlStore(root=self.goc)).hien_tai("demo.x-1")
        self.assertIsNone(sc.reset_luc)
        self.assertIsNone(sc.thu_lai_luc)


# ==========================================================================
# 5. DÂY NỐI THẬT — chạy qua `ControlCenter`, không phải gọi tay hàm thuần
# ==========================================================================
ENGINE = (Path(__file__).resolve().parents[2] / "scripts" / "control_center"
          / "engine.py")


class TestDayNoiThat(unittest.TestCase):
    """Bài học đắt nhất của V1.0: `VongSuCo` có 41 bài kiểm mà KHÔNG một dặm
    đường thật nào. Nhóm này canh rằng `CHO_TAI_NGUYEN` không lặp lại điều đó.
    """

    def _van(self) -> str:
        return ENGINE.read_text(encoding="utf-8")

    def _than(self, ten: str) -> str:
        van = self._van()
        i = van.index(f"def {ten}(")
        j = van.find("\n    def ", i + 1)
        return van[i:j if j > 0 else len(van)]

    def test_15_CHO_QUOTA_di_toi_bo_xu_ly_tai_nguyen(self):
        than = self._than("_dieu_phoi_su_co")
        i = than.index("HanhDong.CHO_QUOTA")
        self.assertIn("_cho_tai_nguyen", than[i:i + 600],
                      "`CHO_QUOTA` phải đi tới bộ xử lý chờ tài nguyên, "
                      "không chỉ ghi một dòng sự kiện rồi bỏ mặc việc ở "
                      "`FAILED` — đó chính là khuyết tật đo được 2026-09-13")

    def test_16_co_dat_WAITING_RESOURCE_len_viec(self):
        than = self._than("_nhan_cho_tai_nguyen")
        self.assertIn("TaskState.WAITING_RESOURCE", than)
        self.assertIn("CHO_TAI_NGUYEN_KHONG_DAT", than,
                      "đặt trạng thái hỏng thì sổ phải NÓI RA — một `except "
                      "... pass` ở đây đã biến leo thang thành lệnh rỗng một "
                      "lần rồi")

    def test_17_tick_CO_quet_danh_thuc(self):
        than = self._than("tick")
        self.assertIn("_quet_cho_tai_nguyen", than,
                      "thiếu vòng quét thì `CHO_RESET` chỉ là một dòng chữ "
                      "và việc nằm đó vĩnh viễn — vẫn là treo, khác tên")

    def test_18_khong_moc_thi_KHONG_danh_thuc(self):
        than = self._than("_quet_cho_tai_nguyen")
        i = than.index("khi is None")
        self.assertIn("continue", than[i:i + 400],
                      "`None` = chưa hẹn được, KHÔNG phải 'tới giờ'")

    def test_19_fabric_runtimes_la_DICT_khong_phai_ham(self):
        """`ctx.fabric.runtimes()` ném `TypeError`, `except` nuốt mất, và bể
        ra RỖNG — tức 'hết đường' cho MỌI lần. Bản đầu viết đúng như vậy."""
        than = self._than("_so_tai_nguyen")
        self.assertNotIn("fabric.runtimes()", than)
        self.assertIn("runtimes", than)
        self.assertIn(".values()", than)

    def test_20_ho_model_suy_tu_supported_models_khong_tu_provider(self):
        """Antigravity phục vụ cả gemini lẫn claude lẫn gpt."""
        than = self._than("_so_tai_nguyen")
        self.assertIn("supported_models", than)


class TestChayThat(unittest.TestCase):
    """Một lượt chạy THẬT qua `ControlCenter` với worker trả về đúng câu hạn
    mức mà nhà cung cấp thật đã trả (2026-09-13)."""

    def setUp(self):
        from scripts.tests.test_control_center_slice import (FakeExecutor,
                                                             _cc, kho_git_tam)
        self._FakeExecutor = FakeExecutor
        self.repo = kho_git_tam()
        self.cc = _cc(self.repo, ex=FakeExecutor(status="failed"))

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                     # noqa: BLE001
            pass
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_21_het_han_muc_KHONG_ra_FAILED_hay_BLOCKED(self):
        """Đường thật: hạn mức cạn -> `WAITING_RESOURCE`, không phải hai kia."""
        self.cc.chat("demo", "fix web/admin")
        t0 = self.cc.store.tasks("demo")[0]
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.RUNNING,
                                     force=True)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.FAILED)

        class _Pb:
            task_id = t0.task_id
            status = "failed"
            summary = ""
            failure_reason = ("Individual quota reached for this account. "
                              "Resets in 0h20m00s")
            risks: list = []
            findings: list = []
            raw_log_ref = ""
            worker = "AG02"

        ctx = self.cc.ctx("demo")
        ra = self.cc._dieu_phoi_su_co(
            ctx, t0.task_id, _Pb(), "", placement_key="AG02/x",
            trang_thai=TaskState.FAILED,
            bang_chung_them=_Pb.failure_reason)
        t = self.cc.store.task(t0.task_id)
        self.assertIn(ra, ("DOI_CHO", "CHO_RESET", "LEO_THANG"),
                      f"phải đi nhánh tài nguyên, nhận được {ra!r}")
        # KHÔNG bao giờ nằm lại ở `FAILED`: đó là toàn bộ khuyết tật.
        self.assertIsNot(t.state, TaskState.FAILED,
                         "hết hạn mức KHÔNG phải một lần hỏng")
        if ra == "CHO_RESET":
            self.assertIs(t.state, TaskState.WAITING_RESOURCE)
            self.assertFalse(t.state.needs_human)
        elif ra == "DOI_CHO":
            # Vòng đời chủ sở hữu nêu: ... -> WAITING_RESOURCE -> chọn đường
            # an toàn (tài khoản khác) -> tài nguyên sẵn sàng -> CHẠY TIẾP
            # CÙNG việc. Nên chỗ nghỉ đúng là `QUEUED`, và `WAITING_RESOURCE`
            # là một nhịp ĐI QUA — nhưng nó phải ĐỌC ĐƯỢC trong sổ, nếu không
            # thì không ai chứng minh được lần chờ ấy từng xảy ra.
            self.assertIs(t.state, TaskState.QUEUED)
            self.assertFalse(t.state.needs_human,
                             "KHÔNG được đánh thức chủ sở hữu khi Router "
                             "còn tự đi tiếp được")
            sk = self.cc.store.su_kien(task_id=t0.task_id, limit=200)
            self.assertTrue(
                any("WAITING_RESOURCE" in str(e.get("detail") or "")
                    for e in sk),
                "nhịp chờ tài nguyên phải để lại dấu trong sổ")
            self.assertTrue(
                any(str(e.get("kind")) == "TAI_NGUYEN_SAN_SANG" for e in sk))
        sc = SoSuCo(self.cc.store).hien_tai(t0.task_id)
        self.assertIsNotNone(sc)
        self.assertIn("quota reached", sc.ly_do_tai_nguyen)
        # Hồ sơ cắt `muc_tieu` ở 600 ký tự CÓ CHỦ ĐÍCH (bản ghi sổ phải có
        # trần), nên so khớp TIỀN TỐ — thứ cần chứng minh là mục tiêu GỐC
        # không bị thay bằng một mục tiêu khác, không phải là nó dài bao nhiêu.
        goc = (t0.objective or t0.title)
        self.assertTrue(sc.muc_tieu and goc.startswith(sc.muc_tieu),
                        "mục tiêu GỐC vẫn thuộc về việc này")

    def test_22_danh_thuc_KHONG_de_viec_moi(self):
        """Hạn mức đổi KHÔNG phải lý do tạo một việc mới cho người dùng."""
        self.cc.chat("demo", "fix web/admin")
        t0 = self.cc.store.tasks("demo")[0]
        n_truoc = len(self.cc.store.tasks("demo"))
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.RUNNING,
                                     force=True)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.FAILED)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.WAITING_RESOURCE,
                                     reason="hết hạn mức")
        self.assertTrue(self.cc._danh_thuc_tai_nguyen(t0.task_id,
                                                      ly_do="reset"))
        t = self.cc.store.task(t0.task_id)
        self.assertIs(t.state, TaskState.QUEUED)
        self.assertEqual(t.task_id, t0.task_id, "CHÍNH việc ấy chạy tiếp")
        self.assertEqual(len(self.cc.store.tasks("demo")), n_truoc,
                         "không sinh việc trùng")

    def test_23_chua_toi_moc_thi_KHONG_danh_thuc(self):
        self.cc.chat("demo", "fix web/admin")
        t0 = self.cc.store.tasks("demo")[0]
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.RUNNING,
                                     force=True)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.FAILED)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.WAITING_RESOURCE,
                                     reason="hết hạn mức")
        so = SoSuCo(self.cc.store)
        so.ghi(SuCoBen(incident_id="sc_x", project_id="demo",
                       task_id=t0.task_id, be_tai_nguyen="AG02",
                       thu_lai_luc=time.time() + 900))
        self.assertEqual(self.cc._quet_cho_tai_nguyen(self.cc.ctx("demo")), 0)
        self.assertIs(self.cc.store.task(t0.task_id).state,
                      TaskState.WAITING_RESOURCE)

    def test_24b_CHINH_tick_danh_thuc_chu_khong_phai_goi_tay(self):
        """Bài neo cấu trúc KHÔNG đủ, và đã đo được điều đó: một đột biến
        thay lời gọi bằng `pass  # _quet_cho_tai_nguyen` vẫn để bộ kiểm
        XANH, vì chuỗi ấy còn nằm trong chính dòng chú thích.

        Bài này gọi `tick()` — đúng thứ vòng lặp nền gọi — và đòi việc PHẢI
        rời `WAITING_RESOURCE`. Không có vòng quét thì nó nằm đó vĩnh viễn.
        """
        self.cc.chat("demo", "fix web/admin")
        t0 = self.cc.store.tasks("demo")[0]
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.RUNNING,
                                     force=True)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.FAILED)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.WAITING_RESOURCE,
                                     reason="hết hạn mức")
        SoSuCo(self.cc.store).ghi(SuCoBen(
            incident_id="sc_tick", project_id="demo", task_id=t0.task_id,
            be_tai_nguyen="AG02", thu_lai_luc=time.time() - 1))
        self.cc.tick()
        self.assertIsNot(self.cc.store.task(t0.task_id).state,
                         TaskState.WAITING_RESOURCE,
                         "`tick()` phải tự đánh thức việc đã tới mốc")

    def test_24_toi_moc_thi_DANH_THUC(self):
        self.cc.chat("demo", "fix web/admin")
        t0 = self.cc.store.tasks("demo")[0]
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.RUNNING,
                                     force=True)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.FAILED)
        self.cc.store.doi_trang_thai(t0.task_id, TaskState.WAITING_RESOURCE,
                                     reason="hết hạn mức")
        SoSuCo(self.cc.store).ghi(SuCoBen(
            incident_id="sc_x", project_id="demo", task_id=t0.task_id,
            be_tai_nguyen="AG02", thu_lai_luc=time.time() - 1))
        self.assertEqual(self.cc._quet_cho_tai_nguyen(self.cc.ctx("demo")), 1)
        self.assertIs(self.cc.store.task(t0.task_id).state, TaskState.QUEUED)


if __name__ == "__main__":
    unittest.main()

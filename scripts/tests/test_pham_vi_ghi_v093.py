# -*- coding: utf-8 -*-
"""LAN TRUYỀN THẨM QUYỀN GHI — V0.9.3.

KHUYẾT TẬT ĐO ĐƯỢC (RouterDogfood02, 2026-09-12). Người dùng gõ:

    "ok triển khai luôn web todo theo kế hoạch vừa lập. Tự code, chạy test và
     verify từ đầu tới cuối. Chỉ repo-local, không deploy."

Leader hiểu ĐÚNG (`y_dinh=WORK`, `delegate_work`). Gói việc gửi worker lại ra
`type: analysis` + `ALLOWED_SCOPE: (không)`, nên worker trả `blocked` — đúng
điều kiện dừng *"phải ghi ra ngoài ALLOWED_SCOPE để làm xong việc"*. Worker
làm đúng; tầng trên cấp sai quyền.

BA CHỖ CÙNG SAI, và tệp này khoá cả ba:

1. `engine` gọi `planner.plan(goal, project)` — CHỈ một chuỗi. Sự thật "người
   dùng vừa cho phép ghi trong kho" chết ở đó.
2. `loai_viec("Triển khai ứng dụng Web Todo…")` ra `analysis`, trong khi
   `_Y_GHI` của CHÍNH tệp đó đã liệt "triển khai" là động từ GHI.
3. `duong_dan_trong` đọc `HTML/CSS/JS` thành một đường dẫn.

Và một cái bẫy tôi đã tự sa vào khi vá, nên nó có bài kiểm riêng
(`test_31`): bản nháp đầu cho `tham_quyen_ghi_repo` tự chạy `do_gated` trên
câu người dùng, rồi TỪ CHỐI cấp quyền cho câu thật ở trên — vì chữ `deploy`
khớp mẫu, bất kể chữ "không" ngay trước nó.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.model import PermissionClass, Project
from scripts.control_center.permissions import (ThamQuyenGhi,
                                                envelope_for,
                                                tham_quyen_ghi_repo)
from scripts.control_center.planner import RulePlanner

#: Câu THẬT người dùng gõ, chép nguyên văn từ sổ chính tắc.
CAU_THAT = ("ok triển khai luôn web todo theo kế hoạch vừa lập. Tự code, "
            "chạy test và verify từ đầu tới cuối. Chỉ repo-local, không "
            "deploy. Nếu có lỗi thì tự repair/replan trong phạm vi cần thiết "
            "rồi tiếp tục. Chỉ hỏi tao nếu gặp authority boundary thực sự.")

#: Mục tiêu THẬT Leader viết lại, chép nguyên văn từ sổ chính tắc.
MUC_TIEU_THAT = ("Triển khai ứng dụng Web Todo theo kế hoạch đã thống nhất: "
                 "giao diện HTML/CSS/JS thuần, Dark mode mặc định có toggle, "
                 "lưu trữ local qua localStorage; viết test và verify toàn bộ "
                 "repo-local.")

CHO_PHEP = ThamQuyenGhi(cho_phep=True, nguon="cau_nguoi_dung",
                        bang_chung="triển khai")


def _pj(duong: str = "") -> Project:
    return Project(project_id="routerdogfood02", name="RouterDogfood02",
                   repo_path=duong or r"C:\RouterProjects\RouterDogfood02")


# ==========================================================================
# 1. GIẢI THẨM QUYỀN TỪ CÂU NGƯỜI DÙNG
# ==========================================================================

class TestThamQuyenGhi(unittest.TestCase):

    def test_01_cau_THAT_cua_nguoi_dung_duoc_cap_quyen(self):
        q = tham_quyen_ghi_repo(CAU_THAT, da_uy_thac=True)
        self.assertTrue(q.cho_phep, q.to_dict())
        self.assertEqual(q.nguon, "cau_nguoi_dung")
        self.assertTrue(q.bang_chung, "phải nêu được CÂU NÀO đã mở quyền")

    def test_02_moi_loi_cho_phep_trong_yeu_cau(self):
        """Bốn cách nói người dùng đã nêu tường minh trong yêu cầu V0.9.3."""
        for cau in ("ok triển khai", "làm luôn đi", "code nó đi",
                    "implement theo plan này"):
            with self.subTest(cau=cau):
                self.assertTrue(
                    tham_quyen_ghi_repo(cau, da_uy_thac=True).cho_phep, cau)

    def test_03_THAO_LUAN_khong_phai_THUC_THI(self):
        """Leader chưa uỷ thác thì một câu có chữ "triển khai" KHÔNG mở quyền.

        §22 — một đề xuất của Strategist không tự thành việc.
        """
        q = tham_quyen_ghi_repo(CAU_THAT, da_uy_thac=False)
        self.assertFalse(q.cho_phep)
        self.assertEqual(q.nguon, "chua_uy_thac")

    def test_04_khong_co_loi_cho_phep_thi_KHONG_cap(self):
        for cau in ("xem thử cái web todo này nên làm thế nào",
                    "phân tích kiến trúc hiện tại",
                    "có bao nhiêu tài khoản antigravity?"):
            with self.subTest(cau=cau):
                q = tham_quyen_ghi_repo(cau, da_uy_thac=True)
                self.assertFalse(q.cho_phep, cau)
                self.assertEqual(q.nguon, "khong_co")

    def test_05_cau_rong_thi_KHONG_cap(self):
        self.assertFalse(tham_quyen_ghi_repo("", da_uy_thac=True).cho_phep)


# ==========================================================================
# 2. PHÂN LOẠI VIỆC — không được cãi nhau với `_Y_GHI`
# ==========================================================================

class TestLoaiViec(unittest.TestCase):

    def test_06_cau_THAT_ra_viec_GHI_chu_khong_phai_analysis(self):
        """Chính mệnh đề đã ra `analysis` và chặn RouterDogfood02."""
        self.assertEqual(
            RulePlanner.loai_viec(
                "Triển khai ứng dụng Web Todo theo kế hoạch đã thống nhất: "
                "giao diện HTML/CSS/JS thuần, Dark mode mặc định có toggle"),
            "implementation")

    def test_07_cac_loi_cho_phep_deu_ra_viec_GHI(self):
        for cau in ("làm luôn đi", "code nó đi", "tự code phần còn lại",
                    "xây dựng app todo", "triển khai ứng dụng"):
            with self.subTest(cau=cau):
                self.assertEqual(RulePlanner.loai_viec(cau), "implementation")

    def test_08_cau_THUAN_DOC_van_o_lai_chi_doc(self):
        """Bản vá KHÔNG được kéo câu đọc thành việc ghi.

        Bản nháp đầu của tôi dùng một luật RỘNG ("có động từ trong `_Y_GHI`
        và không có động từ ĐỌC -> implementation"). `_Y_GHI` có chữ
        `commit`, nên câu đầu tiên dưới đây — thuần đọc — bị kéo thành việc
        ghi. Hồi quy bắt được ngay.
        """
        for cau in ("lục lịch sử git tìm commit đổi config",
                    "xem thử ai đã commit cái này",
                    "kiểm tra xem test nào đang hỏng"):
            with self.subTest(cau=cau):
                self.assertIn(RulePlanner.loai_viec(cau),
                              ("analysis", "review", "testing"))

    def test_08b_KHONG_mo_rong_ngoai_khuyet_tat_do_duoc(self):
        """Luật rộng còn kéo `deploy`/`delete`/`install` thành việc GHI.

        Hậu quả đo được: một việc GATED "deploy the web to production" sau
        khi duyệt kết thúc ở `REVIEW` thay vì `DONE`
        (`test_control_center_slice`). Sửa đúng chỗ hỏng, không sửa rộng hơn.
        """
        for cau in ("deploy the web to production",
                    "delete the old bucket",
                    "install the new dependency"):
            with self.subTest(cau=cau):
                self.assertEqual(RulePlanner.loai_viec(cau), "analysis")

    def test_09_cau_KHONG_co_dong_tu_nao_van_la_analysis(self):
        """Mặc định an toàn nhất KHÔNG đổi khi câu không nói gì về ghi."""
        self.assertEqual(RulePlanner.loai_viec("cái này thế nào?"), "analysis")


# ==========================================================================
# 3. ĐƯỜNG DẪN — dấu gạch chéo không phải là đường dẫn
# ==========================================================================

class TestDuongDan(unittest.TestCase):

    def test_10_liet_ke_VIET_HOA_khong_phai_duong_dan(self):
        self.assertEqual(
            RulePlanner.duong_dan_trong("giao diện HTML/CSS/JS thuần"), ())

    def test_10b_cap_tu_QUY_TRINH_khong_phai_duong_dan(self):
        """Hỏng ĐO ĐƯỢC 2026-09-13 — cái giá là sản phẩm nằm sai chỗ.

        Câu uỷ quyền thật có *"tự repair/replan trong phạm vi cần thiết"*.
        Leader chép cụm đó vào mục tiêu; `repair/replan` thành PHẠM VI GHI;
        agent làm đúng phạm vi được giao, nên cả ứng dụng Todo (6 tệp) nằm
        trong thư mục `repair/replan/`. Việc vẫn `DONE`, cổng kiểm định vẫn
        xanh — chỉ có sản phẩm là ở sai chỗ. Không một phép kiểm nào của
        Router bắt được, vì mọi tầng đều nhất quán với một tiền đề sai.
        """
        for cau in ("tự repair/replan trong phạm vi cần thiết",
                    "chạy test/verify từ đầu tới cuối",
                    "start/stop dịch vụ"):
            with self.subTest(cau=cau):
                self.assertEqual(RulePlanner.duong_dan_trong(cau), ())

    def test_10c_thu_muc_THAT_trung_ten_van_qua_duoc(self):
        """Phép từ chối không được nuốt một thư mục có thật.

        Viết nó NHƯ một đường dẫn thì nó vẫn là đường dẫn.
        """
        self.assertIn("src/repair",
                      RulePlanner.duong_dan_trong("sửa trong src/repair"))
        self.assertIn("repair/build.py",
                      RulePlanner.duong_dan_trong("sửa repair/build.py"))

    def test_11_duong_dan_THAT_van_nhan_ra(self):
        for cau, cho in (
                ("fix the bug in web/admin/content-queue",
                 ("web/admin/content-queue",)),
                ("sửa scripts/control_center/engine.py",
                 ("scripts/control_center/engine.py",)),
                ("dọn trong docs/reports/", ("docs/reports",)),
        ):
            with self.subTest(cau=cau):
                self.assertEqual(RulePlanner.duong_dan_trong(cau), cho)

    def test_12_duong_dan_co_chu_HOA_van_qua_khi_co_dau_hieu_khac(self):
        """Chữ hoa không bị cấm — chỉ cần một dấu hiệu đường dẫn thật."""
        self.assertIn("docs/README.md",
                      RulePlanner.duong_dan_trong("đọc docs/README.md"))


# ==========================================================================
# 4. BẤT BIẾN CHÍNH — quyền đi tới tận gói việc
# ==========================================================================

class TestLanTruyen(unittest.TestCase):

    def _ke_hoach(self, quyen, *, mac_dinh=()):
        return RulePlanner(default_write_scope=mac_dinh).plan(
            MUC_TIEU_THAT, _pj(), quyen_ghi=quyen)

    def test_13_CO_cho_phep___viec_GHI_va_co_pham_vi(self):
        """Bất biến yêu cầu: cho phép repo-local -> CÓ quyền ghi có trần."""
        kh = self._ke_hoach(CHO_PHEP)
        self.assertTrue(kh.tasks)
        for t in kh.tasks:
            self.assertNotIn(t.kind, ("analysis", "review"), t.kind)
            self.assertEqual(t.contract.allowed_scope, (".",))
            self.assertTrue(t.contract.requirements.repo_write)

    def test_14_KHONG_cho_phep___giu_nguyen_hanh_vi_CU(self):
        """Không có thẩm quyền thì vẫn hạ xuống chỉ đọc, y như trước."""
        for q in (None, ThamQuyenGhi(), ThamQuyenGhi(nguon="chua_uy_thac")):
            with self.subTest(q=q):
                kh = self._ke_hoach(q)
                for t in kh.tasks:
                    self.assertEqual(t.contract.allowed_scope, ())
                    self.assertFalse(t.contract.requirements.repo_write)

    def test_15_pham_vi_CO_TRAN___dung_goc_cay_lam_viec(self):
        """KHÔNG phải quyền ghi không giới hạn: đúng một mục, là `.`."""
        for t in self._ke_hoach(CHO_PHEP).tasks:
            self.assertEqual(t.contract.allowed_scope, (".",))

    def test_16_duong_dan_NGUOI_DUNG_NOI_RO_van_thang(self):
        """Cho phép không được nuốt mất phạm vi hẹp hơn người dùng đã nêu."""
        kh = RulePlanner().plan("sửa web/admin cho tao", _pj(),
                                quyen_ghi=CHO_PHEP)
        self.assertEqual(kh.tasks[0].contract.allowed_scope, ("web/admin",))

    def test_17_default_write_scope_cua_du_an_van_thang(self):
        kh = self._ke_hoach(CHO_PHEP, mac_dinh=("web",))
        for t in kh.tasks:
            self.assertEqual(t.contract.allowed_scope, ("web",))

    def test_18_khoa_tai_nguyen_la_GHI_chu_khong_phai_DOC(self):
        from scripts.control_center.locks import WRITE
        for t in self._ke_hoach(CHO_PHEP).tasks:
            self.assertTrue(t.resources)
            for _k, _r, mode in t.resources:
                self.assertEqual(mode, WRITE)

    def test_19_ghi_chu_NOI_RO_vi_sao_co_quyen(self):
        """Bản kiểm toán phải nói được câu nào của người dùng đã mở nó."""
        kh = self._ke_hoach(CHO_PHEP)
        self.assertTrue(kh.notes)
        self.assertTrue(any("triển khai" in n for n in kh.notes), kh.notes)

    def test_20_scope_inferred_duoc_danh_dau(self):
        for t in self._ke_hoach(CHO_PHEP).tasks:
            self.assertTrue(t.scope_inferred)


# ==========================================================================
# 5. RANH GIỚI NGOÀI KHO KHÔNG BỊ NỚI
# ==========================================================================

class TestKhongNoiRao(unittest.TestCase):

    def test_21_cau_cham_PRODUCTION_van_bi_CHAN(self):
        """Cấp phạm vi ghi KHÔNG mở được một việc chạm lớp GATED."""
        kh = RulePlanner().plan(
            "triển khai xong rồi deploy lên production cho tao", _pj(),
            quyen_ghi=CHO_PHEP)
        self.assertTrue(kh.tasks)
        self.assertTrue(
            any(t.envelope.decision is PermissionClass.GATED
                for t in kh.tasks),
            "việc chạm production phải bị chặn dù đã cấp phạm vi ghi")

    def test_22_danh_sach_GATED_khong_doi(self):
        from scripts.control_center.permissions import GATED_OPERATIONS
        for op in ("production_deploy", "production_mutation", "iam_change",
                   "secret_rotation", "secret_disclosure", "billing_change",
                   "resource_expansion", "history_rewrite", "remote_push"):
            self.assertIn(op, GATED_OPERATIONS)

    def test_23_hop_dong_van_cam_thao_tac_pha_huy(self):
        for t in RulePlanner().plan(MUC_TIEU_THAT, _pj(),
                                    quyen_ghi=CHO_PHEP).tasks:
            self.assertFalse(
                getattr(t.contract, "destructive_actions_allowed", False))

    def test_24_dieu_kien_dung_van_con_nguyen(self):
        """Chính điều kiện dừng đã chặn worker vẫn phải còn — nó đúng."""
        t = RulePlanner().plan(MUC_TIEU_THAT, _pj(),
                               quyen_ghi=CHO_PHEP).tasks[0]
        self.assertIn("phải ghi ra ngoài ALLOWED_SCOPE để làm xong việc",
                      t.contract.stop_conditions)


# ==========================================================================
# 6. PHONG BÌ KHÔNG ĐƯỢC TỰ MÂU THUẪN
# ==========================================================================

class TestPhongBi(unittest.TestCase):

    def test_25_khong_quang_cao_quyen_GHI_khi_khong_co_pham_vi(self):
        """Gói việc thật đã in `edit_in_owned_worktree` NGAY TRÊN dòng
        "KHÔNG sở hữu phạm vi ghi nào — chỉ đọc". Hai dòng cạnh nhau nói
        ngược nhau, và agent phải tự đoán dòng nào thật."""
        van = envelope_for("t1", objective="đọc kho").render_for_agent()
        self.assertIn("KHÔNG sở hữu phạm vi ghi nào", van)
        self.assertNotIn("edit_in_owned_worktree", van)
        self.assertNotIn("local_commit", van)

    def test_26_co_pham_vi_thi_VAN_liet_ke_quyen_ghi(self):
        van = envelope_for("t1", objective="sửa web",
                           owned_scope=(".",)).render_for_agent()
        self.assertIn("edit_in_owned_worktree", van)
        self.assertIn("Chỉ được GHI trong phạm vi sở hữu", van)

    def test_27_quyen_chi_doc_van_con_du(self):
        van = envelope_for("t1", objective="đọc kho").render_for_agent()
        for o in ("repo_read", "repo_search"):
            self.assertIn(o, van)

    def test_27b_KHONG_quang_cao_thao_tac_CAN_SHELL(self):
        """Bài kiểm này TRƯỚC ĐÂY đòi `run_tests` phải CÓ trong phong bì.

        Nó khẳng định sai, và khẳng định sai đó có giá đo được: hai lượt
        agent liên tiếp trên RouterDogfood02 chết vì `tool_permission_denied`
        trong 27s, `changes=[]`, nhật ký thô rỗng. Hợp đồng nói "ĐỪNG chạy
        lệnh để build/test", rồi NGAY DƯỚI phong bì liệt kê `run_tests`,
        `run_lint`, `run_build` trong mục "ĐƯỢC TỰ LÀM". Agent tin phong bì.

        `agy --print` (headless) tự chối quyền `command`, nên ba thao tác đó
        KHÔNG BAO GIỜ khả dụng cho agent của Router. Quảng cáo chúng là nói
        dối, và cái giá là cả lượt.
        """
        for scope in ((), (".",)):
            with self.subTest(scope=scope):
                van = envelope_for("t1", objective="triển khai",
                                   owned_scope=scope).render_for_agent()
                for o in ("run_tests", "run_lint", "run_build"):
                    self.assertNotIn(o, van)
                self.assertIn("do ROUTER làm sau", van)


# ==========================================================================
# 7. GÓI VIỆC THẬT — hình dạng đã thất bại, nay phải khác
# ==========================================================================

class TestGoiViecThat(unittest.TestCase):

    def test_28_goi_viec_khong_con_hinh_dang_da_that_bai(self):
        """Gói việc thật của `routerdogfood02.t5985-1`:

            type: analysis · ALLOWED_SCOPE: (không)

        Sau V0.9.3, đúng câu đó phải ra một gói việc GHI ĐƯỢC.
        """
        kh = RulePlanner().plan(MUC_TIEU_THAT, _pj(), quyen_ghi=CHO_PHEP)
        hd = kh.tasks[0].contract
        self.assertNotEqual(hd.type, "analysis")
        self.assertTrue(hd.allowed_scope)
        self.assertNotIn("Việc này KHÔNG sở hữu phạm vi ghi nào",
                         kh.tasks[0].envelope.render_for_agent())

    def test_29_du_an_MOI_TINH_khong_khai_gi_van_lam_duoc(self):
        """Dự án tạo bằng V0.9.2 KHÔNG BAO GIỜ khai `default_write_scope`.

        Trước V0.9.3 đó là ngõ cụt: mọi dự án mới đều không triển khai được.
        """
        tmp = Path(tempfile.mkdtemp(prefix="v093-"))
        try:
            pj = Project(project_id="moi", name="Moi", repo_path=str(tmp))
            self.assertEqual(pj.resources, (),
                             "dự án mới không khai tài nguyên nào")
            kh = RulePlanner(default_write_scope=()).plan(
                MUC_TIEU_THAT, pj, quyen_ghi=CHO_PHEP)
            for t in kh.tasks:
                self.assertTrue(t.contract.allowed_scope)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_30_CA_HAI_bo_lap_ke_hoach_cung_luat(self):
        """`RouterPlanner` lùi về `RulePlanner` và phải cùng hành vi.

        Sửa một bộ mà quên bộ kia cho ra một khuyết tật "lúc có lúc không"
        tuỳ bộ nào chạy.
        """
        from scripts.control_center.planner import RouterPlanner

        def _hong(_prompt):
            raise RuntimeError("không có mạng")

        kh = RouterPlanner(_hong).plan(MUC_TIEU_THAT, _pj(),
                                       quyen_ghi=CHO_PHEP)
        for t in kh.tasks:
            self.assertTrue(t.contract.allowed_scope, t.task_id)


# ==========================================================================
# 8. CÁI BẪY TÔI ĐÃ TỰ SA VÀO
# ==========================================================================

class TestKhongTaiTaoCONG(unittest.TestCase):

    def test_31_KHONG_doc_phu_dinh_thanh_yeu_cau(self):
        """"Chỉ repo-local, KHÔNG deploy" là một RÀNG BUỘC, không phải yêu cầu.

        Bản nháp đầu của `tham_quyen_ghi_repo` tự chạy `do_gated` trên câu
        người dùng, nên chữ `deploy` khớp mẫu và quyền bị từ chối — người
        dùng nói *đừng* deploy và bị đọc thành *hãy* deploy.

        Chủ sở hữu DUY NHẤT của ranh giới ngoài kho là `envelope_for` /
        `do_gated`, chấm trên TỪNG VIỆC. Dựng phép kiểm thứ hai ở tầng thẩm
        quyền chính là tái tạo đúng căn bệnh V0.9.3 sinh ra để chữa.
        """
        q = tham_quyen_ghi_repo(CAU_THAT, da_uy_thac=True)
        self.assertTrue(
            q.cho_phep,
            "câu có chữ 'không deploy' vẫn phải được cấp quyền repo-local")

    def test_33_ENGINE_thuc_su_truyen_quyen___ca_HAI_cho_goi(self):
        """Bài kiểm đơn vị ở trên KHÔNG nhìn thấy `engine`.

        Toàn bộ khuyết tật nằm ở chỗ `engine` gọi `planner.plan()` mà KHÔNG
        mang thẩm quyền theo. Sửa `planner` cho đúng rồi quên nối ở `engine`
        thì mọi bài kiểm trên vẫn xanh và người dùng vẫn bị chặn y như cũ —
        nên chỗ nối phải được khoá bằng một phép đọc cấu trúc.
        """
        goc = Path(__file__).resolve().parents[2]
        van = (goc / "scripts" / "control_center" / "engine.py").read_text(
            encoding="utf-8")
        goi = [d for d in van.splitlines() if "ctx.planner.plan(" in d]
        self.assertEqual(len(goi), 2, f"số chỗ gọi đã đổi: {goi}")
        self.assertEqual(van.count("quyen_ghi="), 2,
                         "cả hai chỗ gọi đều phải mang thẩm quyền")
        # Tính từ CÂU NGƯỜI DÙNG GÕ, không phải từ lời Leader viết lại.
        self.assertIn("tham_quyen_ghi_repo(text,", van)

    def test_34_khong_con_cho_nao_ha_xuong_chi_doc_ma_bo_qua_quyen(self):
        """Cả HAI bộ lập kế hoạch phải cùng luật — sửa một, quên một là

        một khuyết tật "lúc có lúc không" tuỳ bộ nào đang chạy.
        """
        goc = Path(__file__).resolve().parents[2]
        van = (goc / "scripts" / "control_center" / "planner.py").read_text(
            encoding="utf-8")
        self.assertEqual(van.count("quyen_ghi is not None and "
                                   "quyen_ghi.cho_phep"), 2,
                         "cả `RulePlanner` lẫn nhánh dự phòng của "
                         "`RouterPlanner` đều phải xét thẩm quyền")

    def test_32_viec_cham_GATED_van_do_PHONG_BI_chan(self):
        """Bỏ phép kiểm ở tầng thẩm quyền là AN TOÀN, vì phong bì vẫn chặn."""
        pb = envelope_for("t1", objective="deploy lên production",
                          owned_scope=(".",))
        self.assertIs(pb.decision, PermissionClass.GATED)
        self.assertTrue(pb.gate_hits)


# ==========================================================================
# 9. TOKEN GỐC CÂY — hai tầng phải hiểu `.` GIỐNG NHAU
# ==========================================================================

class TestTokenGocCay(unittest.TestCase):
    """Hỏng ĐO ĐƯỢC 2026-09-13, và là bản sao của chính căn bệnh V0.9.3.

    V0.9.3 cấp phạm vi ghi "gốc cây làm việc" bằng token `.` (`locks.GOC`).
    Cổng `scope` thì so bằng `tep == "." or tep.startswith("./")`, nên
    `app.js` NGAY GỐC cây không khớp gì cả. Kết quả: agent viết đúng chỗ,
    hợp đồng cấp đúng quyền, cổng vẫn đánh hỏng —

        gate_scope: ghi NGOÀI write_scope:
        ['README.md','app.js','index.html','style.css']

    Hai cái nhìn về một sự thật, lần này về nghĩa của một dấu chấm.
    """

    def test_35_goc_cay_nghia_la_CA_CAY(self):
        from scripts.router_v3.worktree import chuan_hoa_scope
        for s in ([".", ], ["./"], ["/"], [".", "web"]):
            with self.subTest(s=s):
                self.assertIsNone(chuan_hoa_scope(s))

    def test_36_RONG_khac_GOC_CAY___khong_duoc_nham(self):
        """`[]` = không cho ghi gì. Gốc cây = cho ghi mọi chỗ TRONG cây.

        Hai điều ngược nhau; nhầm chúng là mở toang một rào.
        """
        from scripts.router_v3.worktree import chuan_hoa_scope
        self.assertEqual(chuan_hoa_scope([]), [])
        self.assertIsNotNone(chuan_hoa_scope([]))

    def test_37_pham_vi_thuong_van_duoc_chuan_hoa_nhu_cu(self):
        from scripts.router_v3.worktree import chuan_hoa_scope
        self.assertEqual(chuan_hoa_scope(["web/", "/docs", "a\\b"]),
                         ["web", "docs", "a/b"])

    def test_38_cong_scope_KHONG_danh_hong_tep_o_goc_cay(self):
        """Chạy đúng cổng thật, trên một worktree thật."""
        import subprocess
        from scripts.router_v3.packet import TaskResult
        from scripts.router_v3.pool.validation import kiem_dinh

        tmp = Path(tempfile.mkdtemp(prefix="scope-goc-"))
        try:
            subprocess.run(["git", "-C", str(tmp), "init", "-q"],
                           capture_output=True)
            for ten in ("index.html", "app.js", "style.css"):
                (tmp / ten).write_text("x", encoding="utf-8")
            kq = TaskResult(task_id="t1", worker_id="w1", status="ok",
                            files_changed=["index.html", "app.js",
                                           "style.css"])
            bc = kiem_dinh(kq, worktree=tmp, write_scope=["."])
            cong = {g.name: g for g in bc.gates}
            self.assertIn("scope", cong)
            self.assertTrue(cong["scope"].passed,
                            f"vi phạm: {bc.scope_violations}")
            self.assertEqual(bc.scope_violations, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_39_cong_scope_VAN_bat_duoc_ghi_ngoai_pham_vi_hep(self):
        """Phép sửa KHÔNG được làm cổng mù với phạm vi hẹp."""
        import subprocess
        from scripts.router_v3.packet import TaskResult
        from scripts.router_v3.pool.validation import kiem_dinh

        tmp = Path(tempfile.mkdtemp(prefix="scope-hep-"))
        try:
            subprocess.run(["git", "-C", str(tmp), "init", "-q"],
                           capture_output=True)
            (tmp / "web").mkdir()
            (tmp / "web" / "ok.js").write_text("x", encoding="utf-8")
            (tmp / "ngoai.js").write_text("x", encoding="utf-8")
            kq = TaskResult(task_id="t1", worker_id="w1", status="ok",
                            files_changed=["web/ok.js", "ngoai.js"])
            bc = kiem_dinh(kq, worktree=tmp, write_scope=["web"])
            cong = {g.name: g for g in bc.gates}
            self.assertFalse(cong["scope"].passed)
            self.assertIn("ngoai.js", bc.scope_violations)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


    def test_40_HOP_DONG_cung_hieu_goc_cay_nhu_hai_tang_kia(self):
        """Chỗ THỨ BA của cùng phép so — `TaskContract.scope_violations`.

        Sau khi sửa hai chỗ đầu, lượt agent tiếp theo vẫn hỏng, lần này với
        `gate_contract_scope`. Một agent đã viết đủ 5 tệp (50 test) bị đánh
        hỏng vì tầng hợp đồng vẫn hiểu `.` theo nghĩa cũ.
        """
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import TaskContract

        hd = TaskContract(task_id="t1", objective="x",
                          allowed_scope=(".",),
                          requirements=Requirements(repo_write=True))
        self.assertEqual(
            hd.scope_violations(["index.html", "app.js",
                                 "tests/todo.test.js"]), [])

    def test_41_hop_dong_VAN_bat_pham_vi_hep_va_forbidden(self):
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import TaskContract

        hd = TaskContract(task_id="t1", objective="x",
                          allowed_scope=("web",),
                          requirements=Requirements(repo_write=True))
        self.assertEqual(hd.scope_violations(["web/a.js", "ngoai.js"]),
                         ["ngoai.js"])
        # `forbidden_scope` THẮNG, kể cả khi phạm vi là cả cây.
        hd2 = TaskContract(task_id="t2", objective="x",
                           allowed_scope=(".",),
                           forbidden_scope=(".env",),
                           requirements=Requirements(repo_write=True))
        self.assertIn(".env", hd2.scope_violations(["app.js", ".env"]))

    def test_42_BA_tang_dong_y_voi_nhau(self):
        """Bất biến thật: ba phép so phải cho CÙNG câu trả lời.

        Ba bản sao là ba cơ hội để lệch nhau — bài kiểm này neo chúng lại.
        """
        from scripts.router_v3.worktree import chuan_hoa_scope
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import TaskContract

        tep = ["index.html", "app.js", "tests/todo.test.js"]
        hd = TaskContract(task_id="t1", objective="x", allowed_scope=(".",),
                          requirements=Requirements(repo_write=True))
        self.assertIsNone(chuan_hoa_scope(["."]))          # tầng worktree
        self.assertEqual(hd.scope_violations(tep), [])     # tầng hợp đồng
        # tầng kiểm định đã có `test_38`, chạy trên worktree thật.


if __name__ == "__main__":
    unittest.main()

"""Hành vi giao diện + đúng mười tiêu chí nghiệm thu của V0.1.1.

Mỗi lớp dưới đây gắn với một nhóm tiêu chí trong yêu cầu. Bài kiểm chạy Qt
thật ở `offscreen`, dựng CỬA SỔ THẬT, và bấm nút bằng `click()` — không gọi
hàm xử lý trực tiếp, vì gọi hàm sẽ bỏ qua đúng thứ hay hỏng: nút bị vô hiệu,
nút không nối tín hiệu, hoặc nút nằm trong một layout không bao giờ hiện.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    CO_QT = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_QT = False

if CO_QT:
    from scripts.control_center.gui.bridge import (gop_ke_hoach,
                                                   mo_ta_thoi_luong)
    from scripts.control_center.gui.views import HopTroGiup
    from scripts.control_center.gui.widgets import HopThoai
    from tests.helpers_control_center_gui import (CCGia, cau_gia, chat_mau,
                                                  phien_mau, usage_mau,
                                                  viec_mau)


def _app():
    return QApplication.instance() or QApplication([])


def _cua_so(**kw):
    from scripts.control_center.gui.app import CuaSoChinh
    cs = CuaSoChinh(cau=cau_gia(**kw))
    cs.ve_lai(cs.cau.cc.snapshot("fanfic"))
    return cs


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestBoCuc(unittest.TestCase):
    """Tiêu chí 1-2: cửa sổ mở được, mở được dự án Fanfic."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_co_du_nam_khung_dieu_huong(self):
        from scripts.control_center.gui.app import TEN_KHUNG
        self.assertEqual(TEN_KHUNG,
                         ("Chat", "Tasks", "Agents", "Logs", "Usage"))
        self.assertEqual(self.cs.chong.count(), 5)
        for ten in TEN_KHUNG:
            self.assertIn(ten, self.cs.nut_khung)

    def test_chat_la_khung_MAC_DINH(self):
        """Chat phải là trung tâm sản phẩm, nên nó mở sẵn."""
        self.assertEqual(self.cs.chong.currentIndex(), 0)
        self.assertTrue(self.cs.nut_khung["Chat"].isChecked())

    def test_bam_chuot_doi_duoc_khung(self):
        for i, ten in enumerate(("Tasks", "Agents", "Logs", "Usage")):
            with self.subTest(khung=ten):
                self.cs.nut_khung[ten].click()
                self.assertEqual(self.cs.chong.currentIndex(), i + 1)

    def test_sidebar_liet_ke_du_an_va_mo_duoc_Fanfic(self):
        self.assertEqual(self.cs.ds_project.count(), 2)
        it = self.cs.ds_project.item(0)
        self.assertEqual(it.data(Qt.UserRole), "fanfic")
        self.cs.ds_project.itemClicked.emit(it)
        self.assertEqual(self.cs.cau.project_id, "fanfic")

    def test_thanh_tren_dem_dung_viec_chay_va_bi_chan(self):
        self.assertEqual(self.cs.chip_chay.so.text(), "1")   # t1 RUNNING
        self.assertEqual(self.cs.chip_chan.so.text(), "1")   # t4 BLOCKED

    def test_inspector_gap_lai_duoc(self):
        """Yêu cầu: inspector phải gấp lại được — bằng chuột, qua splitter."""
        self.assertTrue(self.cs.chia.isCollapsible(2))
        self.assertFalse(self.cs.chia.isCollapsible(1))


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestChatVaPhanRa(unittest.TestCase):
    """Tiêu chí 3-4: gõ việc bằng chuột, Router tạo/quản lý việc."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_bam_nut_Gui_thi_goi_backend_dung_van_ban(self):
        kc = self.cs.khung_chat
        kc.o_soan.setPlainText("nối hàng đợi")
        kc.nut_gui.click()
        QApplication.processEvents()
        goi = [g for g in self.cs.cau.cc.da_goi if g[0] == "chat"]
        self.assertEqual(goi, [("chat", "fanfic", "nối hàng đợi")])

    def test_o_soan_duoc_xoa_sau_khi_gui(self):
        kc = self.cs.khung_chat
        kc.o_soan.setPlainText("xong thì xoá")
        kc.nut_gui.click()
        self.assertEqual(kc.o_soan.toPlainText(), "")

    def test_KHONG_gui_khi_o_soan_rong(self):
        kc = self.cs.khung_chat
        kc.o_soan.setPlainText("   ")
        kc.nut_gui.click()
        QApplication.processEvents()
        self.assertEqual([g for g in self.cs.cau.cc.da_goi
                          if g[0] == "chat"], [])

    def test_cay_phan_ra_ve_dung_bon_viec_kem_trang_thai_song(self):
        """Đây là yêu cầu hình ảnh trung tâm của bản này."""
        hang = gop_ke_hoach(chat_mau()[1]["meta"],
                            {t["task_id"]: t for t in viec_mau()})
        self.assertEqual(len(hang), 4)
        self.assertEqual([h["state"] for h in hang],
                         ["RUNNING", "QUEUED", "WAITING", "BLOCKED"])
        self.assertEqual(hang[0]["title"], "Backend wiring")
        self.assertEqual(hang[0]["agent"], "s-abc123")
        self.assertTrue(hang[-1]["cuoi"], "hàng cuối phải vẽ nhánh └─")
        self.assertFalse(hang[0]["cuoi"])

    def test_hang_BLOCKED_mang_theo_cau_hoi_cho_nguoi_dung(self):
        hang = gop_ke_hoach(chat_mau()[1]["meta"],
                            {t["task_id"]: t for t in viec_mau()})
        self.assertIn("cần bạn duyệt", hang[-1]["blocked_reason"])

    def test_ten_viec_uu_tien_ban_SONG_hon_ban_trong_ke_hoach(self):
        """Người dùng đổi tên việc thì chat phải theo, không hiện tên cũ."""
        viec = {t["task_id"]: dict(t) for t in viec_mau()}
        viec["fanfic.t1"]["title"] = "TÊN MỚI"
        hang = gop_ke_hoach(chat_mau()[1]["meta"], viec)
        self.assertEqual(hang[0]["title"], "TÊN MỚI")

    def test_chi_tiet_quyet_dinh_MAC_DINH_dong(self):
        """Không trút nội tạng điều phối vào chat: mục chi tiết phải đóng."""
        from scripts.control_center.gui.views_chat import MucGapLai
        kc = self.cs.khung_chat
        muc = kc.findChildren(MucGapLai)
        self.assertTrue(muc, "phải có mục gấp lại cho chi tiết")
        for m in muc:
            with self.subTest():
                self.assertFalse(m.nut.isChecked())
                self.assertFalse(m.than.isVisible())


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestBangViecVaDieuKhien(unittest.TestCase):
    """Tiêu chí 5-6-8: trạng thái sống, xem chi tiết, Pause/Resume/Stop."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_bang_viec_du_cot_va_du_hang(self):
        b = self.cs.khung_viec.bang
        self.assertEqual(b.rowCount(), 4)
        self.assertEqual([b.horizontalHeaderItem(i).text()
                          for i in range(b.columnCount())],
                         ["Việc", "Trạng thái", "Agent", "Thời lượng",
                          "Ưu tiên", "Phụ thuộc", "Worktree", "Cập nhật"])

    def test_bam_mot_hang_thi_mo_chi_tiet(self):
        kv = self.cs.khung_viec
        kv.bang.selectRow(0)
        self.assertIn("Backend wiring", kv.chi_tiet.ten.text())
        self.assertIn("fanfic.t1", kv.chi_tiet.o.toPlainText())

    def test_chi_tiet_hien_worktree_va_phien(self):
        kv = self.cs.khung_viec
        kv.bang.selectRow(0)
        tho = kv.chi_tiet.o.toPlainText()
        self.assertIn("s-abc123", tho)
        self.assertIn("worktrees", tho)

    def test_Pause_va_Resume_goi_backend_KHONG_hoi_lai(self):
        """Thao tác an toàn phải không có ma sát — không hộp xác nhận."""
        kv = self.cs.khung_viec
        kv.bang.selectRow(0)
        nut = {n.text(): n for n in kv.chi_tiet.findChildren(QPushButton)}
        nut["Tạm dừng"].click()
        nut["Tiếp tục"].click()
        QApplication.processEvents()
        loai = [g[0] for g in self.cs.cau.cc.da_goi]
        self.assertIn("pause", loai)
        self.assertIn("resume", loai)

    def test_nut_Duyet_chi_hien_khi_viec_BLOCKED(self):
        kv = self.cs.khung_viec
        kv.bang.selectRow(0)                     # t1 RUNNING
        self.assertFalse(kv.chi_tiet.nut_duyet.isVisible()
                         or kv.chi_tiet.nut_duyet.isVisibleTo(kv.chi_tiet))
        kv.bang.selectRow(3)                     # t4 BLOCKED
        self.assertTrue(kv.chi_tiet.nut_duyet.isVisibleTo(kv.chi_tiet))

    def test_thoi_luong_doc_duoc_chu_khong_phai_dau_thoi_gian(self):
        self.assertEqual(mo_ta_thoi_luong(1000, 1075, bay_gio=2000), "1m 15s")
        self.assertEqual(mo_ta_thoi_luong(1000, 1030, bay_gio=2000), "30s")
        self.assertEqual(mo_ta_thoi_luong(0, None), "",
                         "việc chưa chạy thì KHÔNG có thời lượng")


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestNhatKyVaUsage(unittest.TestCase):
    """Tiêu chí 6-7: xem nhật ký không cần terminal; usage không bịa số."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_mo_nhat_ky_tu_bang_viec_chuyen_sang_khung_Logs(self):
        self.cs.khung_viec.bang.selectRow(0)
        nut = {n.text(): n for n in
               self.cs.khung_viec.chi_tiet.findChildren(QPushButton)}
        nut["Nhật ký"].click()
        self.assertEqual(self.cs.chong.currentIndex(), 3)
        self.assertIn("fanfic.t1", self.cs.khung_log.nk.van_ban_dang_hien())

    def test_loc_nhat_ky_bang_o_tim(self):
        nk = self.cs.khung_log.nk
        nk.dat_van_ban("alpha\nbeta\ngamma")
        nk.tim.setText("bet")
        self.assertEqual(nk.van_ban_dang_hien(), "beta")
        nk.tim.setText("")
        self.assertEqual(nk.van_ban_dang_hien(), "alpha\nbeta\ngamma")

    def test_usage_danh_dau_du_ba_muc_tin_cay(self):
        self.cs.nut_khung["Usage"].click()
        b = self.cs.khung_usage.bang
        self.assertEqual(b.rowCount(), 3)
        tin = {b.cellWidget(r, 3).text() for r in range(b.rowCount())}
        self.assertEqual(tin, {"ACTUAL", "ESTIMATED", "UNAVAILABLE"})

    def test_usage_UNAVAILABLE_hien_gach_ngang_KHONG_hien_0(self):
        """Bất biến #2 của gói: không đo được thì để trống, không suy ra 0."""
        self.cs.nut_khung["Usage"].click()
        b = self.cs.khung_usage.bang
        for r in range(b.rowCount()):
            if b.cellWidget(r, 3).text() == "UNAVAILABLE":
                self.assertEqual(b.item(r, 1).text(), "—")
                break
        else:
            self.fail("không có hàng UNAVAILABLE nào để kiểm")


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestHopThoaiVaTroGiup(unittest.TestCase):
    """Tiêu chí 9: đóng bằng X và bằng Esc."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_hop_thoai_co_nut_X_nhin_thay_duoc(self):
        """"Nhìn thấy được" nghĩa là PHÔNG CHỮ VẼ ĐƯỢC nó.

        Bản đầu khẳng định đúng ký tự `✕` (U+2715). Nhưng Segoe UI —
        phông mặc định của Windows — KHÔNG có glyph cho U+2715, nên nút
        hiện ra một **hình ô vuông tofu**. Một ô vuông không phải "nút X
        nhìn thấy được", và đó là yêu cầu nghiệm thu số 4.

        Nên bài kiểm không khẳng định ký tự nào cả; nó hỏi phông chữ xem
        có vẽ được ký tự đang dùng hay không. Như vậy nó bắt được CẢ LỚP
        lỗi này, kể cả khi ai đó đổi sang một biểu tượng lạ khác.
        """
        from PySide6.QtGui import QFontDatabase, QFontMetrics
        h = HopThoai("thử", None)
        self.assertTrue(h.nut_x.isVisibleTo(h))
        self.assertTrue(h.nut_x.text().strip(), "nút X không có nhãn")
        self.assertIn("Esc", h.nut_x.toolTip())

        # Nen `offscreen` khong tu nap phong nao, nen phai nap tay tu
        # `C:/Windows/Fonts` — neu khong bai kiem se BO QUA thay vi kiem,
        # va mot bai kiem bo qua thi khong bao ve gi ca.
        for ten in ("segoeui.ttf", "arial.ttf", "tahoma.ttf"):
            d = Path("C:/Windows/Fonts") / ten
            if d.is_file():
                QFontDatabase.addApplicationFont(str(d))
        ho = [x for x in ("Segoe UI", "Arial", "Tahoma")
              if x in QFontDatabase.families()]
        if not ho:
            self.skipTest("máy này không có phông Windows để hỏi")
        from PySide6.QtGui import QFont
        fm = QFontMetrics(QFont(ho[0], 12))
        for ch in h.nut_x.text():
            with self.subTest(ky_tu=hex(ord(ch))):
                self.assertTrue(
                    fm.inFontUcs4(ord(ch)),
                    f"phông {ho[0]!r} không vẽ được {ch!r} "
                    f"({hex(ord(ch))}) — nút sẽ ra ô vuông tofu")

    def test_nut_X_dong_hop_thoai(self):
        h = HopThoai("thử", None)
        h.show()
        h.nut_x.click()
        self.assertFalse(h.isVisible())

    def test_Esc_dong_hop_thoai(self):
        from PySide6.QtGui import QKeyEvent
        h = HopThoai("thử", None)
        h.show()
        h.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape,
                                  Qt.NoModifier))
        self.assertFalse(h.isVisible())

    def test_tro_giup_KHONG_chiem_cho_thuong_truc(self):
        """Trợ giúp phải là hộp thoại, không phải một panel luôn hiện."""
        cs = _cua_so()
        try:
            self.assertEqual(cs.findChildren(HopTroGiup), [],
                             "trợ giúp không được nằm sẵn trong cửa sổ")
            self.assertTrue(cs.nut_tro_giup.isVisibleTo(cs))
            self.assertIn("F1", cs.nut_tro_giup.toolTip())
        finally:
            cs.cau.dung()

    def test_noi_dung_tro_giup_noi_ro_clipboard_hoat_dong_binh_thuong(self):
        nd = HopTroGiup.NOI_DUNG
        self.assertIn("Ctrl+C", nd)
        self.assertIn("Ctrl+V", nd)
        self.assertIn("chuột phải", nd)


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestXacNhanViecNguyHiem(unittest.TestCase):
    """Tiêu chí 9-10: việc nguy hiểm phải xác nhận, việc an toàn thì không."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_Stop_KHONG_chay_khi_nguoi_dung_bam_Cancel(self):
        """Mặc định của hộp thoại phải là Cancel, và Cancel phải chặn thật."""
        from PySide6.QtWidgets import QMessageBox
        goc = QMessageBox.exec
        try:
            QMessageBox.exec = lambda self: QMessageBox.Cancel
            self.cs.xac_nhan_dung("fanfic.t1")
        finally:
            QMessageBox.exec = goc
        self.assertEqual([g for g in self.cs.cau.cc.da_goi
                          if g[0] == "stop"], [])

    def test_Stop_chay_khi_nguoi_dung_dong_y(self):
        from PySide6.QtWidgets import QMessageBox
        goc = QMessageBox.exec
        try:
            QMessageBox.exec = lambda self: QMessageBox.Yes
            self.cs.xac_nhan_dung("fanfic.t1")
        finally:
            QMessageBox.exec = goc
        QApplication.processEvents()
        self.assertEqual([g for g in self.cs.cau.cc.da_goi
                          if g[0] == "stop"], [("stop", "fanfic.t1")])

    def test_duyet_GATED_phai_xac_nhan_va_Cancel_thi_KHONG_duyet(self):
        """Mở cổng GATED là quyết định của người — không được lọt do bấm nhầm."""
        from PySide6.QtWidgets import QMessageBox
        goc = QMessageBox.exec
        try:
            QMessageBox.exec = lambda self: QMessageBox.Cancel
            self.cs.xac_nhan_duyet("fanfic.t4")
        finally:
            QMessageBox.exec = goc
        self.assertEqual([g for g in self.cs.cau.cc.da_goi
                          if g[0] == "mo_khoa_gated"], [])


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestHopDongDuLieuVoiBackendTHAT(unittest.TestCase):
    """Backend giả phải mang ĐÚNG hình dạng của `snapshot()` thật.

    Đây là bài kiểm quan trọng nhất của tệp helper. Nếu backend giả lệch
    khỏi thật, cả bộ kiểm giao diện sẽ xanh trong khi app thật hỏng — đúng
    loại "bài kiểm mô phỏng một thế giới không tồn tại" đã cắn ba lần trong
    bản V0.1.
    """

    def test_khoa_cua_snapshot_gia_khop_snapshot_THAT_chay_that(self):
        """Đối chiếu với `snapshot()` CHẠY THẬT, không với mã nguồn của nó.

        BẢN ĐẦU CỦA BÀI KIỂM NÀY GẦN NHƯ RỖNG: nó `assertIn('"tasks"', ma)`
        trên **văn bản mã nguồn** của `ControlCenter.snapshot`. Mutation
        cho thấy vấn đề: đổi `snapshot()` để `d["tasks"]` trả list
        **dataclass** thay vì `to_dict()` → chuỗi `"tasks"` vẫn nằm trong
        mã, bài kiểm vẫn xanh, còn giao diện thật vỡ ngay ở `t.get(...)`.

        Nên giờ dựng một `ControlCenter` THẬT trên thư mục tạm, gọi
        `snapshot()` thật, và đối chiếu **khoá + kiểu của phần tử** với
        backend giả. Đây là bài kiểm giữ cho cả bộ kiểm giao diện khỏi
        "mô phỏng một thế giới không tồn tại".
        """
        import shutil
        import tempfile
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project

        goc = Path(tempfile.mkdtemp(prefix="cc-gui-contract-"))
        try:
            cc = ControlCenter(root=goc, probe=False)
            cc.them_project(Project(project_id="p", name="P",
                                    repo_path=str(goc)))
            that = cc.snapshot("p")
            gia = CCGia().snapshot("fanfic")

            self.assertEqual(set(that), set(gia),
                             "khoá của snapshot thật và giả phải khớp")
            for khoa in ("tasks", "sessions", "locks", "worktrees",
                         "events", "chat", "in_flight", "projects"):
                with self.subTest(khoa=khoa):
                    self.assertIsInstance(that[khoa], list)
                    self.assertIsInstance(gia[khoa], list)
            # Giao dien goi `.get()` tren tung phan tu -> chung PHAI la dict.
            cc.chat("p", "update docs/a.md with one line")
            that2 = cc.snapshot("p")
            for khoa in ("tasks", "chat", "projects"):
                with self.subTest(khoa=khoa):
                    self.assertTrue(that2[khoa], f"{khoa} phải có dữ liệu")
                    for x in that2[khoa]:
                        self.assertIsInstance(
                            x, dict,
                            f"phần tử của {khoa!r} phải là dict — giao diện "
                            f"gọi .get() trên nó")
            cc.shutdown()
        finally:
            shutil.rmtree(goc, ignore_errors=True)

    def test_snapshot_KHONG_co_du_an_tra_it_khoa_hon_va_giao_dien_chiu_duoc(self):
        """Hình dạng mà backend giả không bao giờ tạo ra.

        `snapshot()` thật trả về CHỈ 3 khoá khi không có dự án nào
        (`engine.py`: `if not pid: return d`). Backend giả luôn trả đủ 10,
        nên đường này chưa từng được bài kiểm nào chạm — và cửa sổ gọi
        `d.get("tasks") or []` khắp nơi, nên nó phải chịu được.
        """
        import shutil
        import tempfile
        from scripts.control_center.engine import ControlCenter

        goc = Path(tempfile.mkdtemp(prefix="cc-gui-rong-"))
        try:
            cc = ControlCenter(root=goc, probe=False)
            d = cc.snapshot("")
            self.assertEqual(set(d), {"projects", "selected", "ts"})
            cs = _cua_so()
            try:
                cs.ve_lai(d)             # KHONG duoc nem ngoai le
                self.assertEqual(cs.khung_viec.bang.rowCount(), 0)
            finally:
                cs.cau.dung()
            cc.shutdown()
        finally:
            shutil.rmtree(goc, ignore_errors=True)

    def test_truong_cua_task_gia_khop_dataclass_THAT(self):
        import dataclasses as dc
        from scripts.control_center.model import Task
        that = {f.name for f in dc.fields(Task)}
        for t in viec_mau():
            thua = set(t) - that
            with self.subTest(task=t["task_id"]):
                self.assertEqual(thua, set(),
                                 f"task giả có trường không tồn tại: {thua}")

    def test_truong_cua_session_gia_khop_dataclass_THAT(self):
        import dataclasses as dc
        from scripts.control_center.model import Session
        that = {f.name for f in dc.fields(Session)}
        for s in phien_mau():
            thua = set(s) - that
            with self.subTest(phien=s["session_id"]):
                self.assertEqual(thua, set())

    def test_muc_tin_cay_usage_gia_dung_dung_ba_gia_tri_that(self):
        from scripts.control_center.model import UsageConfidence
        that = {x.value for x in UsageConfidence}
        for m in usage_mau()["metrics"]:
            with self.subTest(m=m["label"]):
                self.assertIn(m["confidence"], that)


if __name__ == "__main__":
    unittest.main()

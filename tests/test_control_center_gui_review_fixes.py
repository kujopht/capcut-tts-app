"""Khoá lại 6 lỗi mà review đối kháng tìm ra trước khi phát hành V0.1.1.

Cả sáu đều là lỗi THẬT, đo được. Bốn trong số đó là **lỗi clipboard** mặc
dù không lỗi nào nằm trong mã clipboard — đó là điều đáng học nhất của lượt
review này: cổng nghiệm thu "Ctrl+C copy được" bị phá bởi *nhịp làm mới
giao diện*, không bởi mã xử lý clipboard.

    #1  panel chi tiết + Inspector ghi `setPlainText` mỗi giây
        ⇒ vùng đang bôi đen bị xoá ⇒ Ctrl+C ra rỗng
    #2  nhật ký của việc ĐANG chạy: cùng lỗi, và tệ hơn — nút Copy rơi về
        nhánh "copy tất cả" nên dán ra CẢ nhật ký thay vì phần đã chọn
    #3  `_copy_bang` chỉ đọc `item()`, bỏ trắng cột dùng cell widget
        (Trạng thái, Usage) ⇒ mất dữ liệu âm thầm vào clipboard
    #4  Qt6 KHÔNG copy cả hàng bằng Ctrl+C như tài liệu cũ nói
    #5  đổi trạng thái một việc dựng lại CẢ danh sách tin chat
    #6  mã dự án đúc từ tên thư mục + `luu_project` là UPSERT
        ⇒ lặng lẽ trỏ một dự án thật sang kho khác
    #7  ô tìm ở thanh trên nối vào `lambda _: None` — điều khiển chết
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
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QFileDialog, QMessageBox)
    CO_QT = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_QT = False

if CO_QT:
    from tests.helpers_control_center_gui import cau_gia

NL = chr(10)


def _app():
    return QApplication.instance() or QApplication([])


def _cua_so():
    from scripts.control_center.gui.app import CuaSoChinh
    cs = CuaSoChinh(cau=cau_gia())
    cs.ve_lai(cs.cau.cc.snapshot("fanfic"))
    return cs


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestVungChonSongQuaNhipLamMoi(unittest.TestCase):
    """#1 + #2 — và đây là bốn dòng nghiệm thu clipboard cùng lúc."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_panel_chi_tiet_giu_vung_dang_boi_den_qua_ba_nhip(self):
        """Đo được 217 ký tự đang chọn → 0 sau đúng một nhịp làm mới.

        Người dùng bôi đen rồi mới với tay bấm Ctrl+C; quá 1 giây là chuyện
        thường. Nên đây là một lỗi clipboard, dù trông như lỗi hiệu năng.
        """
        kv = self.cs.khung_viec
        kv.bang.selectRow(0)
        kv.chi_tiet.o.selectAll()
        truoc = len(kv.chi_tiet.o.textCursor().selectedText())
        self.assertGreater(truoc, 0, "không có gì để chọn — bài kiểm vô nghĩa")
        for _ in range(3):
            self.cs.ve_lai(self.cs.cau.cc.snapshot("fanfic"))
        self.assertEqual(len(kv.chi_tiet.o.textCursor().selectedText()),
                         truoc, "vẽ lại đã giết vùng đang bôi đen")

    def test_inspector_giu_vung_dang_boi_den_qua_ba_nhip(self):
        o = self.cs.inspector.o
        o.selectAll()
        truoc = len(o.textCursor().selectedText())
        self.assertGreater(truoc, 0)
        for _ in range(3):
            self.cs.ve_lai(self.cs.cau.cc.snapshot("fanfic"))
        self.assertEqual(len(o.textCursor().selectedText()), truoc)

    def test_nhat_ky_dang_MOC_giu_vung_chon_va_Copy_dung_phan_da_chon(self):
        """Chỗ tệ nhất: mất vùng chọn khiến nút Copy dán ra CẢ nhật ký."""
        nk = self.cs.khung_log.nk
        nk.dat_van_ban("dòng 1" + NL + "dòng 2")
        nk.o.selectAll()
        self.assertTrue(nk.o.textCursor().selectedText())

        nk.dat_van_ban("dòng 1" + NL + "dòng 2" + NL + "dòng 3 MOI")
        self.assertTrue(nk.o.textCursor().selectedText(),
                        "log mọc thêm dòng đã giết vùng đang bôi đen")

        QGuiApplication.clipboard().setText("KHONG-DOI")
        nk.nut_copy.click()
        ra = QGuiApplication.clipboard().text()
        self.assertNotIn("MOI", ra,
                         "Copy dán CẢ nhật ký thay vì phần đang chọn")

    def test_van_ban_KHONG_doi_thi_KHONG_ghi_lai(self):
        """Chốt so sánh: không đổi thì không được chạm vào widget."""
        from scripts.control_center.gui.widgets import dat_van_ban_giu_chon
        o = self.cs.inspector.o
        o.setPlainText("y nguyên")
        self.assertFalse(dat_van_ban_giu_chon(o, "y nguyên"))
        self.assertTrue(dat_van_ban_giu_chon(o, "đã đổi"))

    def test_van_ban_NGAN_DI_thi_kep_vung_chon_chu_khong_no_ngoai_le(self):
        from scripts.control_center.gui.widgets import dat_van_ban_giu_chon
        o = self.cs.inspector.o
        o.setPlainText("một dòng rất dài để bôi đen")
        o.selectAll()
        dat_van_ban_giu_chon(o, "ngắn")          # KHONG duoc nem
        self.assertEqual(o.toPlainText(), "ngắn")


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestCopyBangDuCot(unittest.TestCase):
    """#3 + #4 — clipboard của bảng không được thiếu cột."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_copy_bang_lay_ca_cot_dung_cell_widget(self):
        """Cột Trạng thái/Usage là `HuyHieu`, không phải `QTableWidgetItem`.

        Bản trước chỉ đọc `b.item(r, c)` nên hai cột đó ra RỖNG, trong khi
        header vẫn ghi tên cột — dán vào Excel là dán một bảng thiếu đúng
        cột quan trọng nhất.
        """
        from scripts.control_center.gui.views import _copy_bang
        tho = _copy_bang(self.cs.khung_viec.bang)
        self.assertIn("Trạng thái", tho.splitlines()[0])
        self.assertIn("RUNNING", tho, "cột Trạng thái bị bỏ trắng")
        self.assertIn("BLOCKED", tho)

    def test_copy_bang_agents_lay_ca_cot_Usage(self):
        """Cột Usage là cột mà bất biến "không bịa số" đang bảo vệ."""
        from scripts.control_center.gui.views import _copy_bang
        self.cs.nut_khung["Agents"].click()
        tho = _copy_bang(self.cs.khung_agent.bang)
        self.assertIn("Usage", tho.splitlines()[0])
        self.assertIn("UNAVAILABLE", tho, "cột Usage bị bỏ trắng")

    def test_nut_Copy_All_cua_bang_dan_du_cot(self):
        b = self.cs.khung_viec.bang
        QGuiApplication.clipboard().setText("KHONG-DOI")
        # Tim nut trong thanh copy cua khung Tasks.
        from PySide6.QtWidgets import QPushButton
        nut = {n.text(): n for n in self.cs.khung_viec.findChildren(QPushButton)}
        nut["Copy All"].click()
        ra = QGuiApplication.clipboard().text()
        self.assertIn("RUNNING", ra)
        self.assertEqual(len(ra.splitlines()), b.rowCount() + 1)

    def test_Ctrl_C_tren_bang_copy_CA_HANG_khong_phai_mot_o(self):
        """Qt6 mặc định copy `DisplayRole` của MỘT ô — tài liệu cũ nói sai."""
        b = self.cs.khung_viec.bang
        self.cs.show()
        self.cs.activateWindow()
        QApplication.processEvents()
        b.selectRow(0)
        b.setFocus()
        QApplication.processEvents()
        QGuiApplication.clipboard().setText("KHONG-DOI")
        QTest.keyClick(b, Qt.Key_C, Qt.ControlModifier)
        QApplication.processEvents()
        ra = QGuiApplication.clipboard().text()
        self.assertIn("Backend wiring", ra)
        self.assertIn("RUNNING", ra, "Ctrl+C chỉ copy một ô, không cả hàng")


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestChatKhongDungLaiVoCo(unittest.TestCase):
    """#5 — đổi trạng thái việc không được huỷ thẻ người dùng đang đọc."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def _cac_the(self):
        kc = self.cs.khung_chat
        return [id(kc.ds.itemAt(i).widget())
                for i in range(kc.ds.count() - 1)]

    def test_doi_trang_thai_viec_KHONG_dung_lai_danh_sach_tin(self):
        kc = self.cs.khung_chat
        truoc = self._cac_the()
        self.assertTrue(truoc, "phải có thẻ để so sánh")
        d = self.cs.cau.cc.snapshot("fanfic")
        d["tasks"] = [dict(t) for t in d["tasks"]]
        d["tasks"][0]["state"] = "DONE"
        kc.cap_nhat(d)
        self.assertEqual(self._cac_the(), truoc,
                         "đổi trạng thái đã dựng lại cả danh sách tin")

    def test_huy_hieu_VAN_doi_du_khong_dung_lai_the(self):
        """Cập nhật tại chỗ phải THẬT SỰ cập nhật, không chỉ bỏ qua."""
        kc = self.cs.khung_chat
        d = self.cs.cau.cc.snapshot("fanfic")
        d["tasks"] = [dict(t) for t in d["tasks"]]
        d["tasks"][0]["state"] = "DONE"
        kc.cap_nhat(d)
        hv = kc._the_router[0].hang_viec["fanfic.t1"]
        self.assertEqual(hv.hh.text(), "DONE")

    def test_tin_MOI_thi_van_dung_them_the(self):
        kc = self.cs.khung_chat
        n0 = kc.ds.count()
        d = self.cs.cau.cc.snapshot("fanfic")
        d["chat"] = list(d["chat"]) + [
            {"message_id": 99, "project_id": "fanfic", "role": "user",
             "text": "tin mới", "ts": 0, "meta": {}}]
        kc.cap_nhat(d)
        self.assertEqual(kc.ds.count(), n0 + 1, "tin mới không hiện")

    def test_vẽ_lai_cung_du_lieu_thi_KHONG_lam_gi(self):
        kc = self.cs.khung_chat
        truoc = self._cac_the()
        for _ in range(3):
            kc.cap_nhat(self.cs.cau.cc.snapshot("fanfic"))
        self.assertEqual(self._cac_the(), truoc)


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestOTimVaDuAnMoi(unittest.TestCase):
    """#6 + #7."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.cs = _cua_so()

    def tearDown(self):
        self.cs.cau.dung()

    def test_o_tim_THAT_SU_loc_bang(self):
        """Từng nối vào `lambda _: None` trong khi tooltip hứa sẽ lọc."""
        b = self.cs.khung_viec.bang
        self.cs.o_tim.setText("Artwork")
        hien = [r for r in range(b.rowCount()) if not b.isRowHidden(r)]
        self.assertEqual(len(hien), 1)
        self.assertIn("Artwork", b.item(hien[0], 0).text())

    def test_xoa_o_tim_thi_hien_lai_het(self):
        b = self.cs.khung_viec.bang
        self.cs.o_tim.setText("Artwork")
        self.cs.o_tim.setText("")
        self.assertEqual(
            [r for r in range(b.rowCount()) if not b.isRowHidden(r)],
            list(range(b.rowCount())))

    def test_o_tim_loc_duoc_theo_cot_dung_widget(self):
        b = self.cs.khung_viec.bang
        self.cs.o_tim.setText("blocked")
        hien = [r for r in range(b.rowCount()) if not b.isRowHidden(r)]
        self.assertEqual(len(hien), 1, "lọc không thấy cột trạng thái")

    def test_bo_loc_con_giu_sau_khi_ve_lai(self):
        b = self.cs.khung_viec.bang
        self.cs.o_tim.setText("Artwork")
        self.cs.ve_lai(self.cs.cau.cc.snapshot("fanfic"))
        hien = [r for r in range(b.rowCount()) if not b.isRowHidden(r)]
        self.assertEqual(len(hien), 1, "bộ lọc bị quên sau một nhịp")

    def test_du_an_moi_TRUNG_MA_phai_hoi_va_Cancel_thi_KHONG_ghi(self):
        """`luu_project` là UPSERT và mã dự án đúc từ TÊN THƯ MỤC.

        Chọn một thư mục khác cũng tên "Fanfic" sẽ lặng lẽ trỏ dự án thật
        sang kho khác, kéo theo mọi task/worktree cũ treo ở một đường dẫn
        không còn đúng.
        """
        goc_fd = QFileDialog.getExistingDirectory
        goc_mb = QMessageBox.exec
        try:
            QFileDialog.getExistingDirectory = (
                lambda *a, **k: "C:/kho/khac/Fanfic")
            QMessageBox.exec = lambda _s: QMessageBox.Cancel
            self.cs.mo_project_moi()
        finally:
            QFileDialog.getExistingDirectory = goc_fd
            QMessageBox.exec = goc_mb
        QApplication.processEvents()
        self.assertEqual([g for g in self.cs.cau.cc.da_goi
                          if g[0] == "them_project"], [],
                         "Cancel vẫn ghi đè dự án đang có")

    def test_du_an_moi_MA_MOI_thi_KHONG_hoi(self):
        """Thao tác an toàn phải không có ma sát."""
        goc_fd = QFileDialog.getExistingDirectory
        goc_mb = QMessageBox.exec
        da_hoi = []
        try:
            QFileDialog.getExistingDirectory = (
                lambda *a, **k: "C:/kho/moi/hoantoanmoi")

            def _hoi(_s):
                da_hoi.append(1)
                return QMessageBox.Cancel
            QMessageBox.exec = _hoi
            self.cs.mo_project_moi()
        finally:
            QFileDialog.getExistingDirectory = goc_fd
            QMessageBox.exec = goc_mb
        QApplication.processEvents()
        self.assertEqual(da_hoi, [], "mã dự án MỚI thì không được hỏi")
        self.assertEqual([g[1] for g in self.cs.cau.cc.da_goi
                          if g[0] == "them_project"], ["hoantoanmoi"])


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestLuongNenAnToan(unittest.TestCase):
    """#9 — bộ đếm tác vụ nền và việc làm mới phải ở LUỒNG GUI."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_nhieu_tac_vu_song_song_van_ve_0_va_bat_lai_nut_Gui(self):
        """`self._dang -= 1` là đọc–sửa–ghi; hai runnable có thể đè nhau.

        Nếu bộ đếm không bao giờ về 0 thì `dang_lam(False)` không phát, và
        nút **Gửi** kẹt vô hiệu cho tới khi có thao tác khác.
        """
        cs = _cua_so()
        try:
            cs.show()
            for i in range(8):
                cs.cau.tam_dung(f"fanfic.t{i}")
            for _ in range(200):
                QApplication.processEvents()
                if cs.cau._dang == 0:
                    break
            self.assertEqual(cs.cau._dang, 0, "bộ đếm không về 0")
            self.assertTrue(cs.khung_chat.nut_gui.isEnabled(),
                            "nút Gửi kẹt vô hiệu")
        finally:
            cs.cau.dung()

    def test_lam_moi_chay_NGAY_sau_khi_tac_vu_xong(self):
        """`QTimer.singleShot` tạo trên luồng pool không có event loop.

        Nên "làm mới ngay" của bản đầu thực tế không bao giờ chạy trên
        đường đó; người dùng vẫn phải chờ hết nhịp 1s.
        """
        cs = _cua_so()
        try:
            dem = []
            cs.cau.anh_chup.connect(lambda _d: dem.append(1))
            n0 = len(dem)
            cs.cau.tam_dung("fanfic.t1")
            for _ in range(200):
                QApplication.processEvents()
                if len(dem) > n0:
                    break
            self.assertGreater(len(dem), n0,
                               "không làm mới sau khi tác vụ nền xong")
        finally:
            cs.cau.dung()


if __name__ == "__main__":
    unittest.main()

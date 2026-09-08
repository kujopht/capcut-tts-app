"""CỔNG NGHIỆM THU CLIPBOARD của V0.1.1 — kiểm bằng máy.

Bản V0.1 bị từ chối vì đúng một lý do: *"ordinary clipboard interaction is
not reliable"*. Nên tệp này không phải bài kiểm phụ, nó LÀ điều kiện phát
hành. Mỗi bài dưới đây tương ứng một dòng trong danh sách nghiệm thu.

CÁCH KIỂM: chạy Qt thật ở chế độ `offscreen` (cùng cách bộ 397 bài kiểm
desktop của kho này đã chạy nhiều tháng), gõ/dán/chọn bằng API thật của Qt,
rồi đọc lại clipboard thật. Không mô phỏng, không giả lập widget.

MỘT ĐIỀU QUAN TRỌNG VỀ Ctrl+C/Ctrl+V: bài kiểm KHÔNG bơm sự kiện bàn phím
để "chứng minh Ctrl+V hoạt động" — hành vi đó do chính `QPlainTextEdit` của
Qt cài đặt, và kiểm lại nó là kiểm Qt, không kiểm mã của ta. Thứ THẬT SỰ có
thể hỏng do lỗi của ta là **giành mất tổ hợp phím** hoặc **chặn
`keyPressEvent`**. Nên bài kiểm nhắm đúng vào đó:

  * quét MỌI `QShortcut`/`QAction` của cửa sổ, đòi không cái nào chiếm
    Ctrl+C/V/X/A ở phạm vi ứng dụng;
  * gọi thẳng `paste()`/`copy()` để chắc đường clipboard của widget còn
    nguyên;
  * bơm Ctrl+V thật vào ô soạn và đòi văn bản xuất hiện — đây là bài duy
    nhất bơm phím, vì nó chứng minh `keyPressEvent` của ta không ăn mất.
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
    from PySide6.QtGui import QGuiApplication, QKeyEvent, QKeySequence
    from PySide6.QtWidgets import QApplication
    CO_QT = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_QT = False

if CO_QT:
    from scripts.control_center.gui.widgets import (KhoiMa, KhungNhatKy,
                                                    OSoanThao,
                                                    VanBanChonDuoc,
                                                    cac_phim_tat_bi_cam)

#: Van ban thu: tieng Viet co dau, nhieu dong, va mot doan dai. Ba thu nay
#: la ba dong rieng trong danh sach nghiem thu nen chung duoc kiem cung mot
#: cho, tren cung mot duong.
NHIEU_DONG = (
    "Sửa `server/farmer/loop.py` để hàng đợi không mất việc khi worker chết.\n"
    "Ràng buộc:\n"
    "  - không đổi lược đồ SQLite\n"
    "  - giữ cổng kiểm định fail-closed\n"
    "Ghi chú: chữ có dấu — ăn, ổn, ữ, ậ, đ, ẫ.\n"
)
DAI = "x" * 200_000


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestDanVaoOSoan(unittest.TestCase):
    """Ctrl+V dán được vào ô chat — nguyên vẹn, đủ dấu, không bị cắt."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.o = OSoanThao()
        self.cb = QGuiApplication.clipboard()

    def test_dan_van_ban_NHIEU_DONG_nguyen_ven(self):
        self.cb.setText(NHIEU_DONG)
        self.o.paste()
        # NGUYEN VEN nghia la GIONG HET, ke ca dau xuong dong cuoi.
        # Ban dau toi viet `.rstrip()` vi DOAN rang Qt cat no — Qt
        # khong cat, va ky vong sai lam bai kiem bao dong tren mot
        # hanh vi dung.
        self.assertEqual(self.o.toPlainText(), NHIEU_DONG,
                         "prompt nhiều dòng phải dán nguyên vẹn")
        self.assertGreaterEqual(self.o.toPlainText().count("\n"), 4)

    def test_dan_giu_dung_dau_tieng_Viet(self):
        self.cb.setText("ăn ổn ữ ậ đ ẫ — Ưu tiên")
        self.o.paste()
        self.assertEqual(self.o.toPlainText(), "ăn ổn ữ ậ đ ẫ — Ưu tiên")

    def test_dan_van_ban_RAT_DAI_khong_bi_cat(self):
        self.cb.setText(DAI)
        self.o.paste()
        self.assertEqual(len(self.o.toPlainText()), len(DAI),
                         "prompt dài phải dán đủ, không bị cắt")

    def test_Ctrl_V_THAT_khong_bi_keyPressEvent_an_mat(self):
        """Bài duy nhất bơm phím — và là bài quan trọng nhất của tệp.

        `OSoanThao` ghi đè `keyPressEvent` để bắt Ctrl+Enter. Một lỗi rất
        dễ mắc ở đó là `return` sớm cho mọi phím có Ctrl, và như vậy là ăn
        mất Ctrl+V/Ctrl+C của chính ô đang gõ.
        """
        self.cb.setText("dán bằng phím thật")
        e = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_V, Qt.ControlModifier)
        self.o.keyPressEvent(e)
        self.assertEqual(self.o.toPlainText(), "dán bằng phím thật")

    def test_Ctrl_A_roi_Ctrl_C_lay_lai_duoc_toan_bo(self):
        self.o.setPlainText(NHIEU_DONG)
        self.o.selectAll()
        self.o.copy()
        self.assertEqual(self.cb.text(), NHIEU_DONG)

    def test_Enter_TRAN_xuong_dong_chu_KHONG_gui(self):
        """Enter không được gửi: một cú Enter vô tình sẽ mất bản nháp.

        Đây là quyết định UX có chủ đích, và nó phục vụ đúng luật "bàn phím
        chỉ là lối tắt": nút Gửi mới là đường chính.
        """
        da_gui = []
        self.o.yeu_cau_gui.connect(lambda: da_gui.append(1))
        self.o.setPlainText("dòng một")
        e = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        self.o.keyPressEvent(e)
        self.assertEqual(da_gui, [], "Enter trần không được gửi")
        self.assertIn("\n", self.o.toPlainText())

    def test_Ctrl_Enter_thi_MOI_gui(self):
        da_gui = []
        self.o.yeu_cau_gui.connect(lambda: da_gui.append(1))
        self.o.setPlainText("gửi đi")
        e = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
        self.o.keyPressEvent(e)
        self.assertEqual(da_gui, [1])


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestChonVaCopyVanBanDocChiDoc(unittest.TestCase):
    """Chọn bằng chuột + Ctrl+C trên chat/log/task — phải hoạt động."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_o_chat_chi_doc_van_CHON_duoc(self):
        o = VanBanChonDuoc()
        o.setPlainText("báo cáo của agent")
        co = o.textInteractionFlags()
        self.assertTrue(co & Qt.TextSelectableByMouse,
                        "phải chọn được bằng chuột")
        self.assertTrue(co & Qt.TextSelectableByKeyboard)

    def test_o_chi_doc_KHONG_bi_setEnabled_False(self):
        """`setEnabled(False)` làm mất luôn khả năng chọn — cấm dùng.

        Đây là cách phổ biến nhất làm một ô "chỉ đọc" trong Qt, và nó chính
        là cách phổ biến nhất làm hỏng copy.
        """
        # PHAI giu tham chieu tay: `KhungNhatKy().o` de widget CHA
        # thanh mot tam thoi, no bi thu gom rac ngay, va Qt xoa luon
        # doi tuong C++ con -> "Internal C++ object already deleted".
        # Da mac dung loi nay khi viet tep nay.
        nk, km = KhungNhatKy(), KhoiMa("x")
        self._giu = (nk, km)
        for w in (VanBanChonDuoc(), nk.o, km.o):
            with self.subTest(w=type(w).__name__):
                self.assertTrue(w.isEnabled(), "ô chỉ đọc vẫn phải enabled")
                self.assertTrue(w.isReadOnly())

    def test_chon_bang_chuot_roi_copy_ra_clipboard(self):
        o = VanBanChonDuoc()
        o.setPlainText("dòng A\ndòng B")
        o.selectAll()
        o.copy()
        self.assertEqual(QGuiApplication.clipboard().text(), "dòng A\ndòng B")


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestNutCopyNhinThayDuoc(unittest.TestCase):
    """Nút Copy/Copy All — đường cho người không dùng lối tắt."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_khoi_ma_co_nut_copy_va_copy_dung_noi_dung(self):
        k = KhoiMa("def f():\n    return 1\n", tieu_de="mã")
        self.assertTrue(k.nut_copy.isVisible() or k.nut_copy.isVisibleTo(k))
        k.nut_copy.click()
        self.assertEqual(QGuiApplication.clipboard().text(),
                         "def f():\n    return 1\n")

    def test_nhat_ky_co_Copy_va_Copy_All(self):
        """BAM NUT, khong goi ham.

        Ban dau goi `nk.copy_tat_ca()` truc tiep — nen neu ai do xoa
        dong `clicked.connect(...)`, hai nut thanh nut chet ma bai kiem
        van xanh. Dong nghiem thu la "logs have Copy and Copy All",
        tuc la ve CAI NUT, khong ve cai ham.
        """
        nk = KhungNhatKy()
        nk.dat_van_ban("dòng 1\ndòng 2\ndòng 3")
        QGuiApplication.clipboard().setText("KHONG-DOI")
        nk.nut_copy_all.click()
        self.assertEqual(QGuiApplication.clipboard().text(),
                         "dòng 1\ndòng 2\ndòng 3")
        QGuiApplication.clipboard().setText("KHONG-DOI")
        nk.nut_copy.click()
        self.assertEqual(QGuiApplication.clipboard().text(),
                         "dòng 1\ndòng 2\ndòng 3")

    def test_Copy_khi_KHONG_chon_gi_thi_copy_TAT_CA(self):
        """Bấm Copy mà chưa bôi đen gì thì phải copy tất cả, không phải rỗng.

        Trả clipboard rỗng ở đây là thứ làm người dùng tưởng app hỏng.
        """
        nk = KhungNhatKy()
        nk.dat_van_ban("a\nb")
        QGuiApplication.clipboard().setText("CU")
        nk.nut_copy.click()
        self.assertEqual(QGuiApplication.clipboard().text(), "a\nb")

    def test_copy_phan_DANG_CHON_doi_U2029_thanh_newline(self):
        """`selectedText()` trả U+2029 thay cho ngắt dòng.

        Copy thẳng giá trị đó ra clipboard sẽ khiến người dùng dán vào
        Notepad và thấy MỘT dòng dài. Bài này khoá phép đổi lại.
        """
        nk = KhungNhatKy()
        nk.dat_van_ban("dòng 1\ndòng 2")
        nk.o.selectAll()
        nk.copy_chon()
        ra = QGuiApplication.clipboard().text()
        self.assertEqual(ra, "dòng 1\ndòng 2")
        self.assertNotIn("\u2029", ra)


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class TestKhongGianhPhimClipboard(unittest.TestCase):
    """Không một lối tắt nào của app được chiếm Ctrl+C/V/X/A.

    Đây là bài kiểm bảo vệ cả sản phẩm: nó quét CỬA SỔ THẬT, nên một người
    sau này thêm `QShortcut("Ctrl+C")` cho "copy việc đang chọn" sẽ làm
    bài này hỏng — đúng lúc cần hỏng.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _cua_so(self):
        from scripts.control_center.gui.app import CuaSoChinh
        from tests.helpers_control_center_gui import cau_gia
        return CuaSoChinh(cau=cau_gia())

    def test_khong_QShortcut_nao_chiem_to_hop_clipboard(self):
        """MỌI phạm vi, không riêng phạm vi ứng dụng.

        BẢN ĐẦU CỦA BÀI KIỂM NÀY LÀ MỘT BÀI KIỂM RỖNG, và nó là bài kiểm
        quan trọng nhất của cả bản phát hành — nên đáng ghi lại đủ.

        Nó lọc `sc.context() == Qt.ApplicationShortcut`. Nhưng phạm vi MẶC
        ĐỊNH của `QShortcut`/`QAction` là `WindowShortcut` (đo trên PySide6
        6.11.2), nên bộ lọc đó bỏ qua gần như mọi cách người ta thật sự
        thêm một lối tắt. Mutation: thêm `QShortcut(QKeySequence("Ctrl+C"),
        self)` vào `_phim_tat_tuy_chon` — bài kiểm cũ VẪN XANH, trong khi
        Ctrl+C bị ăn mất ở cả năm vùng chỉ-đọc (thẻ chat, nhật ký, panel
        chi tiết, Inspector, bảng Tasks).

        Ô soạn thì miễn nhiễm vì Qt gửi `ShortcutOverride` cho widget
        editable đang focus — nên bài kiểm cũ chỉ bảo vệ đúng cái ô mà Qt
        đã tự bảo vệ, và bỏ ngỏ toàn bộ phần còn lại.
        """
        from PySide6.QtGui import QShortcut
        cs = self._cua_so()
        try:
            cam = set(cac_phim_tat_bi_cam())
            thay = [(sc.key().toString(), str(sc.context()))
                    for sc in cs.findChildren(QShortcut)
                    if sc.key().toString() in cam]
            self.assertEqual(thay, [], f"lối tắt đã chiếm: {thay}")
        finally:
            cs.cau.dung()

    def test_khong_QAction_nao_chiem_to_hop_clipboard(self):
        from PySide6.QtGui import QAction
        cs = self._cua_so()
        try:
            cam = set(cac_phim_tat_bi_cam())
            thay = [(a.shortcut().toString(), str(a.shortcutContext()))
                    for a in cs.findChildren(QAction)
                    if a.shortcut().toString() in cam]
            self.assertEqual(thay, [], f"QAction đã chiếm: {thay}")
        finally:
            cs.cau.dung()

    def test_Ctrl_C_THAT_copy_duoc_o_MOI_vung_chi_doc(self):
        """Bơm Ctrl+C bằng sự kiện THẬT vào từng vùng chỉ-đọc.

        Đây là bài bắt được thứ mà hai bài quét-shortcut ở trên không bắt
        nổi: một lối tắt ở phạm vi cửa sổ ăn mất Ctrl+C *trước khi* nó tới
        widget. Quét cấu trúc là điều kiện cần; bơm phím là điều kiện đủ.
        """
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtTest import QTest
        cs = self._cua_so()
        try:
            cs.show()
            # `activateWindow()` + `processEvents()` la BAT BUOC, khong phai
            # trang tri: thieu chung, may lối tắt của cửa sổ chưa vào cuộc va
            # `QTest.keyClick` giao thang su kien cho widget — bai kiem se
            # XANH ngay ca khi mot QShortcut Ctrl+C dang an mat phim.
            # Da kiem bang mutation dung nghia: bo hai dong nay -> bai kiem
            # khong con bat duoc ke cuop.
            cs.activateWindow()
            cs.raise_()
            QApplication.processEvents()
            vung = [
                ("nhật ký", cs.khung_log.nk.o, "log A\nlog B"),
                ("chi tiết việc", cs.khung_viec.chi_tiet.o, "ct A\nct B"),
                ("inspector", cs.inspector.o, "insp A\ninsp B"),
            ]
            for nhan, o, mau in vung:
                with self.subTest(vung=nhan):
                    o.setPlainText(mau)
                    o.selectAll()
                    o.setFocus()
                    QApplication.processEvents()
                    QGuiApplication.clipboard().setText("KHONG-DOI")
                    QTest.keyClick(o, Qt.Key_C, Qt.ControlModifier)
                    QApplication.processEvents()
                    self.assertEqual(
                        QGuiApplication.clipboard().text(), mau,
                        f"Ctrl+C bị ăn mất ở vùng {nhan!r}")
        finally:
            cs.cau.dung()

    def test_loi_tat_cua_o_soan_o_pham_vi_WIDGET(self):
        """Ctrl+Enter phải ở phạm vi widget, không phải ứng dụng.

        Ở phạm vi ứng dụng, nó sẽ bắn cả khi con trỏ đang ở ô tìm kiếm hay
        ô lọc nhật ký — tức là gửi tin khi người dùng không hề muốn.
        """
        from PySide6.QtGui import QShortcut
        o = OSoanThao()
        scs = o.findChildren(QShortcut)
        self.assertTrue(scs, "phải có lối tắt Ctrl+Enter")
        for sc in scs:
            with self.subTest(phim=sc.key().toString()):
                self.assertEqual(sc.context(), Qt.WidgetWithChildrenShortcut)
                self.assertNotIn(sc.key().toString(),
                                 set(cac_phim_tat_bi_cam()))


if __name__ == "__main__":
    unittest.main()

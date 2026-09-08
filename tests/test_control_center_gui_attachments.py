"""Đính kèm ở tầng GIAO DIỆN: dán, kéo-thả, chọn tệp, bỏ ra, gửi.

Bộ kiểm này dùng `ControlCenter` THẬT trên thư mục tạm — khác với các tệp
kiểm giao diện khác. Lý do: đính kèm là tính năng mà *đường đi của byte*
chính là thứ phải kiểm. Một backend giả sẽ chỉ kiểm được widget vẽ đúng
hay không, còn câu hỏi thật là "tệp có tới đúng chỗ với đúng băm hay
không".

VÀ MỘT ĐIỀU CANH RIÊNG: `OSoanThao` giờ ghi đè `insertFromMimeData`. Đó là
chỗ dễ phá clipboard nhất, nên ở đây có bài đòi **dán văn bản thuần vẫn
nguyên vẹn** ngay cả khi có đính kèm — cổng nghiệm thu V0.1.1 không được
mất vì tính năng V0.2.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

try:
    from PySide6.QtCore import QMimeData, Qt, QUrl
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QApplication
    CO_QT = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_QT = False

PNG_BYTE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
NHIEU_DONG = ("Sửa `server/farmer/loop.py`\n"
              "Ràng buộc:\n"
              "  - không đổi lược đồ\n"
              "Ghi chú: ăn ổn ữ ậ đ\n")


def _app():
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(CO_QT, "chưa cài PySide6")
class _Nen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.gui.app import CuaSoChinh
        from scripts.control_center.gui.bridge import Cau
        from scripts.control_center.model import Project
        self.goc = Path(tempfile.mkdtemp(prefix="cc-gui-att-"))
        self.cc = ControlCenter(root=self.goc, probe=False)
        self.cc.them_project(Project(project_id="p", name="P",
                                     repo_path=str(self.goc)))
        self.cau = Cau(cc=self.cc)
        self.cau.chon_project("p")
        self.cs = CuaSoChinh(cau=self.cau)
        self.kc = self.cs.khung_chat

    def tearDown(self):
        try:
            self.cau.dung()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.goc, ignore_errors=True)

    def _tep(self, ten: str, noi: bytes) -> Path:
        p = self.goc / "nguon" / ten
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(noi)
        return p

    def _cho(self, dieu_kien, giay: float = 25.0) -> bool:
        """Chờ một điều kiện, VỪA bơm event VỪA ngủ.

        Bản đầu của các bài kiểm này quay 200 vòng
        `processEvents()` mà KHÔNG ngủ — cả vòng lặp xong trong vài
        micro-giây, nên luồng nền chưa kịp chạy và bài kiểm báo
        hỏng oan. `chat()` đi qua `QThreadPool`, tức một luồng
        KHÁC; bơm event không làm nó nhanh hơn.
        """
        import time as _t
        het = _t.time() + giay
        while _t.time() < het:
            QApplication.processEvents()
            if dieu_kien():
                return True
            _t.sleep(0.02)
        QApplication.processEvents()
        return bool(dieu_kien())

    def _anh(self) -> QImage:
        im = QImage(24, 16, QImage.Format_RGB32)
        im.fill(0xFF3366)
        return im


class TestDanAnhTuClipboard(_Nen):
    """Đường của Win+Shift+S: clipboard mang BITMAP, không mang tệp."""

    def test_dan_anh_thi_hien_the_dinh_kem_co_thumbnail(self):
        mime = QMimeData()
        mime.setImageData(self._anh())
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()

        ds = self.kc.dai.danh_sach()
        self.assertEqual(len(ds), 1, "không có đính kèm nào được thêm")
        self.assertEqual(ds[0].media_type, "image")
        self.assertTrue(self.kc.dai.isVisible() or self.kc.dai.isVisibleTo(self.kc))

        from scripts.control_center.gui.attachments_ui import TheDinhKem
        the = self.kc.dai.findChildren(TheDinhKem)
        self.assertEqual(len(the), 1)
        self.assertTrue(the[0].hinh.pixmap() is not None
                        and not the[0].hinh.pixmap().isNull(),
                        "thẻ ảnh không có thumbnail")

    def test_anh_dan_duoc_luu_dung_PNG_va_bam_KHOP(self):
        mime = QMimeData()
        mime.setImageData(self._anh())
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        dk = self.kc.dai.danh_sach()[0]
        p = self.cc.dinh_kem.duong_dan(dk.attachment_id)
        self.assertTrue(p.read_bytes().startswith(b"\x89PNG"))
        self.assertTrue(self.cc.dinh_kem.kiem_toan_ven(dk.attachment_id))
        self.assertEqual(dk.size_bytes, p.stat().st_size)

    def test_dan_ANH_va_VAN_BAN_NHIEU_DONG_cung_luc_giu_CA_HAI(self):
        """Clipboard Windows mang nhiều định dạng một lúc.

        Xử lý phải là "lấy hết những gì hiểu được", không phải if/elif rồi
        bỏ phần còn lại — nếu không, dán một ảnh sẽ ăn mất đoạn văn bản
        người dùng dán cùng.
        """
        mime = QMimeData()
        mime.setImageData(self._anh())
        mime.setText(NHIEU_DONG)
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        self.assertEqual(len(self.kc.dai.danh_sach()), 1, "mất ảnh")
        self.assertEqual(self.kc.o_soan.toPlainText(), NHIEU_DONG,
                         "mất văn bản nhiều dòng")


class TestDanVaThaTep(_Nen):
    """Đường của Explorer: clipboard/drag mang CF_HDROP -> `file://` URL."""

    def _mime_tep(self, *duong: Path) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(d)) for d in duong])
        return mime

    def test_dan_mot_PDF_tu_Explorer(self):
        p = self._tep("bao cao.pdf", b"%PDF-1.7\n" + b"x" * 200)
        self.kc.o_soan.insertFromMimeData(self._mime_tep(p))
        QApplication.processEvents()
        ds = self.kc.dai.danh_sach()
        self.assertEqual([d.filename for d in ds], ["bao cao.pdf"])
        self.assertEqual(ds[0].media_type, "document")

    def test_dan_mot_tep_MA_NGUON(self):
        p = self._tep("loop.py", b"def f():\n    return 1\n")
        self.kc.o_soan.insertFromMimeData(self._mime_tep(p))
        QApplication.processEvents()
        self.assertEqual(self.kc.dai.danh_sach()[0].media_type, "code")

    def test_THA_tep_vao_o_soan(self):
        from PySide6.QtGui import QDropEvent
        from PySide6.QtCore import QPointF
        p = self._tep("du_lieu.csv", b"a,b,c")
        # PHAI giu tham chieu: `QDropEvent` khong so huu `QMimeData`,
        # nen mot tam thoi bi thu gom rac va `e.mimeData()` tra ve mot
        # QObject tron -> "AttributeError: no attribute hasUrls". Cung
        # ho loi tuoi tho da gap o `KhungNhatKy().o`.
        self._mime = self._mime_tep(p)
        e = QDropEvent(QPointF(10, 10), Qt.CopyAction, self._mime,
                       Qt.LeftButton, Qt.NoModifier)
        self.kc.o_soan.dropEvent(e)
        QApplication.processEvents()
        self.assertEqual([d.filename for d in self.kc.dai.danh_sach()],
                         ["du_lieu.csv"])

    def test_NHIEU_tep_mot_luot(self):
        a = self._tep("a.png", PNG_BYTE)
        b = self._tep("b.txt", b"xin chao")
        c = self._tep("c.json", b'{"x":1}')
        self.kc.o_soan.insertFromMimeData(self._mime_tep(a, b, c))
        QApplication.processEvents()
        self.assertEqual(len(self.kc.dai.danh_sach()), 3)

    def test_mot_tep_SAI_LOAI_khong_lam_mat_cac_tep_kia(self):
        """Kéo 5 tệp mà một cái sai đuôi thì 4 cái kia vẫn phải nhận."""
        ok1 = self._tep("ok.txt", b"a")
        xau = self._tep("xau.exe", b"MZ\x90\x00")
        ok2 = self._tep("ok2.json", b"{}")
        self.kc.o_soan.insertFromMimeData(self._mime_tep(ok1, xau, ok2))
        QApplication.processEvents()
        ten = sorted(d.filename for d in self.kc.dai.danh_sach())
        self.assertEqual(ten, ["ok.txt", "ok2.json"])

    def test_URL_http_KHONG_bi_bien_thanh_lenh_tai_ve(self):
        """Kéo một link từ trình duyệt vào không được thành tải file.

        Tầng đính kèm không gọi mạng; im lặng tải một URL là đúng thứ
        người dùng không yêu cầu.
        """
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.com/a.pdf")])
        mime.setText("https://example.com/a.pdf")
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        self.assertEqual(self.kc.dai.danh_sach(), [])
        self.assertIn("example.com", self.kc.o_soan.toPlainText())


class TestClipboardVanBanKHONGBIPHA(_Nen):
    """Cổng nghiệm thu V0.1.1 không được mất vì tính năng V0.2."""

    def test_dan_van_ban_thuan_van_di_duong_cua_Qt(self):
        mime = QMimeData()
        mime.setText(NHIEU_DONG)
        self.kc.o_soan.insertFromMimeData(mime)
        self.assertEqual(self.kc.o_soan.toPlainText(), NHIEU_DONG)
        self.assertEqual(self.kc.dai.danh_sach(), [])

    def test_Ctrl_V_THAT_van_dan_duoc_van_ban(self):
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QKeyEvent
        QGuiApplication.clipboard().setText(NHIEU_DONG)
        e = QKeyEvent(QKeyEvent.KeyPress, _Qt.Key_V, _Qt.ControlModifier)
        self.kc.o_soan.keyPressEvent(e)
        self.assertEqual(self.kc.o_soan.toPlainText(), NHIEU_DONG)

    def test_KHONG_co_QShortcut_Ctrl_V_nao_duoc_dang_ky(self):
        from PySide6.QtGui import QShortcut
        cam = {"Ctrl+V", "Ctrl+C", "Ctrl+X", "Ctrl+A"}
        thay = [sc.key().toString() for sc in self.cs.findChildren(QShortcut)
                if sc.key().toString() in cam]
        self.assertEqual(thay, [], f"đã chiếm: {thay}")


class TestBoRaVaGui(_Nen):
    def _them_anh(self):
        mime = QMimeData()
        mime.setImageData(self._anh())
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        return self.kc.dai.danh_sach()[0]

    def test_bo_mot_dinh_kem_TRUOC_khi_gui_thi_xoa_khoi_kho(self):
        dk = self._them_anh()
        p = self.cc.dinh_kem.duong_dan(dk.attachment_id)
        self.assertTrue(p.is_file())

        from scripts.control_center.gui.attachments_ui import TheDinhKem
        self.kc.dai.findChildren(TheDinhKem)[0].nut_bo.click()
        QApplication.processEvents()

        self.assertEqual(self.kc.dai.danh_sach(), [])
        self.assertIsNone(self.cc.dinh_kem.lay(dk.attachment_id),
                          "bản ghi còn nằm lại sau khi bỏ ra")
        self.assertFalse(p.exists(), "blob mồ côi còn trên đĩa")

    def test_nut_Bo_het_bo_TAT_CA(self):
        self._them_anh()
        p = self._tep("a.txt", b"x")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p))])
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        self.assertEqual(len(self.kc.dai.danh_sach()), 2)
        self.kc.dai.nut_bo_het.click()
        QApplication.processEvents()
        self.assertEqual(self.kc.dai.danh_sach(), [])

    def test_gui_thi_MA_dinh_kem_di_kem_va_dai_duoc_don(self):
        dk = self._them_anh()
        self.kc.o_soan.setPlainText("xem ảnh này")
        self.kc.nut_gui.click()
        # CHO DUNG DIEU KIEN SE KHANG DINH, khong cho "co dong chat nao".
        # `chat()` chen dong `user` NGAY dau, truoc khi gan dinh kem — nen
        # cho theo dong chat se tra ve som va bai kiem doc `message_id` khi
        # no chua duoc ghi. Da mac dung loi nay.
        self._cho(lambda: (self.cc.dinh_kem.lay(dk.attachment_id) is not None
                           and self.cc.dinh_kem.lay(
                               dk.attachment_id).message_id is not None))
        self.assertEqual(self.kc.dai.danh_sach(), [],
                         "dải đính kèm không được dọn sau khi gửi")
        con = self.cc.dinh_kem.lay(dk.attachment_id)
        self.assertIsNotNone(con, "đính kèm biến mất sau khi gửi")
        self.assertIsNotNone(con.message_id,
                             "đính kèm không được gắn vào tin nhắn nào")

    def test_gui_duoc_khi_CHI_co_dinh_kem_khong_co_chu(self):
        self._them_anh()
        self.kc.o_soan.clear()
        self.kc.nut_gui.click()
        self._cho(lambda: bool(self.cc.store.chat("p")))
        self.assertTrue(self.cc.store.chat("p"),
                        "kéo một ảnh vào rồi bấm Gửi là ý định hợp lệ")

    def test_nhan_nut_Gui_dem_so_tep(self):
        self.assertEqual(self.kc.nut_gui.text(), "Gửi")
        self._them_anh()
        self.assertIn("1", self.kc.nut_gui.text())

    def test_nut_dinh_kem_NHIN_THAY_DUOC_va_co_tooltip(self):
        self.assertTrue(self.kc.nut_dinh_kem.isVisibleTo(self.kc))
        tip = self.kc.nut_dinh_kem.toolTip()
        for x in ("Ctrl+V", "kéo-thả"):
            with self.subTest(x=x):
                self.assertIn(x, tip)


class TestQuyenAgentQuaGiaoDien(_Nen):
    """Agent chỉ được đọc đính kèm của ĐÚNG việc của nó — đo qua GUI."""

    def test_dinh_kem_chi_toi_viec_do_tin_nhan_NAY_sinh_ra(self):
        mime = QMimeData()
        mime.setImageData(self._anh())
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        dk = self.kc.dai.danh_sach()[0]

        self.kc.o_soan.setPlainText("update docs/a.md with one line")
        self.kc.nut_gui.click()
        self._cho(lambda: bool(self.cc.store.tasks("p")), giay=45.0)
        viec = self.cc.store.tasks("p")
        self.assertTrue(viec, "không có việc nào được tạo")

        for t in viec:
            with self.subTest(task=t.task_id):
                ds = self.cc.dinh_kem.cho_agent(t.task_id)
                self.assertEqual([x.attachment_id for x in ds],
                                 [dk.attachment_id])
        # Mot viec KHAC khong duoc thay gi.
        self.assertEqual(self.cc.dinh_kem.cho_agent("p.khong_lien_quan"), [])

    def test_hop_dong_gui_cho_agent_CO_duong_dan_cuc_bo(self):
        mime = QMimeData()
        mime.setImageData(self._anh())
        self.kc.o_soan.insertFromMimeData(mime)
        QApplication.processEvents()
        self.kc.o_soan.setPlainText("update docs/a.md with one line")
        self.kc.nut_gui.click()
        self._cho(lambda: bool(self.cc.store.tasks("p")), giay=45.0)
        t = self.cc.store.tasks("p")[0]
        hd = self.cc._hop_dong_kem_dinh_kem(t)
        muc = hd.get("objective") or ""
        self.assertIn("TỆP ĐÍNH KÈM", muc)
        self.assertIn(str(self.cc.dinh_kem.thu_muc), muc)
        for x in ("http://", "https://", "upload"):
            with self.subTest(x=x):
                self.assertNotIn(x, muc.lower())


if __name__ == "__main__":
    unittest.main()

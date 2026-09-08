"""Phụ thuộc runtime của giao diện web Control Center phải được KHAI BÁO.

Cùng hình dạng với sự cố `boto3` mà `server/tests/test_dependencies.py` ghi
lại: **mã đã viết nhưng không tệp phụ thuộc nào được commit khai báo gói**,
nên một môi trường cài đúng theo tài liệu vẫn hỏng.

SỰ CỐ THẬT ĐÃ GHÌM Ở ĐÂY. `webapi.py` có `POST /api/attachments` nhận
`Form(...)` + `UploadFile`, và FastAPI đòi `python-multipart` cho những thứ
đó. Gói ấy **chưa từng được khai ở đâu cả**. Nó không lộ ra vì:

* máy phát triển đã có sẵn nó (một gói khác kéo theo), và
* bản EXE đóng gói cũng có, vì PyInstaller gom từ chính venv đó.

Nó lộ ra ở **CI môi trường sạch**: 37 lỗi trong một lượt.

VÌ SAO NÓ NGHIÊM TRỌNG HƠN VẺ NGOÀI: FastAPI kiểm gói này lúc **ĐĂNG KÝ
ROUTE**, không phải lúc có request đầu tiên. Nên thiếu nó thì `dung_app()`
ném ngay, và **cả API chết** — không phải riêng đường đính kèm. Giao diện
web lẫn vỏ desktop đều không mở được trên một máy cài sạch.

Bài kiểm này kiểm phần KHAI BÁO, chứ không phải phần cài đặt: nếu chỉ dựa
vào `import multipart` thành công thì trên máy đã có sẵn gói nó vẫn xanh,
và đó đúng là cách sự cố lọt qua.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
TEP_WEB = GOC / "requirements-control-center-web.txt"
WEBAPI = GOC / "scripts" / "control_center" / "webapi.py"

#: Thứ FastAPI đòi `python-multipart` mới dùng được.
DAU_MULTIPART = ("Form", "File", "UploadFile")


def khai_bao(tep: Path) -> dict:
    """`{tên gói (chữ thường): ràng buộc phiên bản}` từ một tệp phụ thuộc."""
    ra = {}
    for dong in tep.read_text(encoding="utf-8").splitlines():
        dong = dong.split("#", 1)[0].strip()
        if not dong:
            continue
        k = re.match(r"^([A-Za-z0-9._-]+)\s*(\[[^\]]*\])?\s*(.*)$", dong)
        if k:
            ra[k.group(1).lower()] = k.group(3).strip()
    return ra


class TestPhuThuocGiaoDienWeb(unittest.TestCase):
    def test_tep_phu_thuoc_da_duoc_commit(self):
        self.assertTrue(TEP_WEB.is_file(),
                        "requirements-control-center-web.txt phải tồn tại "
                        "và được commit")

    def test_python_multipart_duoc_khai_kem_rang_buoc_phien_ban(self):
        d = khai_bao(TEP_WEB)
        self.assertIn(
            "python-multipart", d,
            "python-multipart phải được khai trong "
            "requirements-control-center-web.txt, không phải cài tay — "
            "thiếu nó thì `dung_app()` ném lúc đăng ký route và CẢ API chết")
        self.assertTrue(d["python-multipart"],
                        "python-multipart phải có ràng buộc phiên bản")
        self.assertRegex(d["python-multipart"], r"[<>=~!]",
                         "ràng buộc phiên bản phải dùng toán tử so sánh")

    def test_fastapi_va_uvicorn_cung_van_duoc_khai(self):
        d = khai_bao(TEP_WEB)
        for g in ("fastapi", "uvicorn"):
            self.assertIn(g, d)
            self.assertRegex(d[g], r"[<>=~!]")

    def test_webapi_that_su_con_dung_multipart(self):
        """Chứng cứ chống rỗng, và cũng là cái chuông nếu route bị bỏ.

        Nếu một ngày `/api/attachments` không còn nhận multipart nữa thì
        bài kiểm trên thành nghĩa vụ vô cớ. Bài này bắt đúng lúc đó, để
        người sau biết là được phép bỏ dòng phụ thuộc kia.
        """
        cay = ast.parse(WEBAPI.read_text(encoding="utf-8"))
        thay = set()
        for n in ast.walk(cay):
            if isinstance(n, ast.Name) and n.id in DAU_MULTIPART:
                thay.add(n.id)
            elif isinstance(n, ast.Attribute) and n.attr in DAU_MULTIPART:
                thay.add(n.attr)
        self.assertTrue(
            thay,
            "webapi.py không còn dùng Form/File/UploadFile — nếu đúng vậy "
            "thì python-multipart không còn bắt buộc, và bài kiểm trên nên "
            "được bỏ cùng lúc với dòng phụ thuộc đó")

    def test_dung_app_dung_duoc_that(self):
        """Và phép thử cuối: dựng app THẬT.

        Bài này chỉ xanh khi gói đã được CÀI. Nó không thay được bài kiểm
        khai báo ở trên — trên máy đã có sẵn gói, nó xanh dù tệp phụ thuộc
        rỗng, và đó chính là cách sự cố lọt qua.
        """
        import tempfile

        try:
            from scripts.control_center.engine import ControlCenter
            from scripts.control_center.webapi import PhienWeb, dung_app
        except ModuleNotFoundError as e:            # pragma: no cover
            self.skipTest(f"thiếu {e.name}")
        goc = Path(tempfile.mkdtemp(prefix="cc-dep-"))
        cc = ControlCenter(root=goc, max_parallel=1)
        try:
            app = dung_app(PhienWeb(cc, token="t" * 32, cong=1))
            duong = {getattr(r, "path", "") for r in app.routes}
            self.assertIn("/api/attachments", duong)
        finally:
            cc.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)

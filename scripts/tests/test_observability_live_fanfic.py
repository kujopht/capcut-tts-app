"""Probe SỐNG THẬT tới AWS farmer — CHỈ ĐỌC, và tự bỏ qua khi không nối được.

VÌ SAO ĐÂY LÀ MỘT BÀI KIỂM chứ không phải một kịch bản rời: nó là cách
duy nhất chứng minh adapter đọc đúng một hệ thống THẬT. Một adapter chỉ
được kiểm bằng đầu ra giả sẽ xanh trong khi `systemctl show` trên máy thật
trả một hình dạng khác.

`skipTest` khi không có khoá / không nối được: bộ kiểm phải chạy được trên
một máy không có credential (CI), và một bài kiểm mạng KHÔNG được làm cả
suite đỏ vì hôm nay mạng chậm.

CHỈ ĐỌC. Không lệnh nào ở đây đổi trạng thái máy xa — xem
`observability/providers.py::LENH_DOC` (allowlist) và
`observability/provider.py::KHONG_DUOC_CO` (danh sách cấm, có bài kiểm
quét cả gói ở `test_observability.py`).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.observability import config as cf  # noqa: E402
from scripts.control_center.observability.model import \
    TrangThai  # noqa: E402
from scripts.control_center.observability.providers import \
    SshServiceProvider  # noqa: E402


def _cau_hinh_fanfic():
    d = cf.nap()
    p = (d.get("projects") or {}).get("fanfic") or {}
    for x in (p.get("providers") or []):
        if x.get("type") == "ssh_service":
            return x
    return None


class TestProbeSongThat(unittest.TestCase):
    """Đo AWS farmer thật. Bỏ qua nếu môi trường không cho phép."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = _cau_hinh_fanfic()
        if not cls.cfg:
            raise unittest.SkipTest("chưa khai `ssh_service` cho fanfic")
        if not cf.duong_khoa_ton_tai(cls.cfg.get("key_path") or ""):
            raise unittest.SkipTest("không có tệp khoá đã cấu hình")
        cls.khoi = SshServiceProvider(cls.cfg).thu({})

    def test_khong_nem_va_luon_ra_mot_khoi(self):
        self.assertTrue(self.khoi.quan_sat, "probe không cho quan sát nào")

    def test_neu_khong_noi_duoc_thi_UNKNOWN_chu_KHONG_DOWN(self):
        """Phép kiểm quan trọng nhất của tệp này.

        Không nối được máy thì ta KHÔNG BIẾT dịch vụ thế nào. Ghi `DOWN`
        ở đây là đúng cái lỗi V0.5 tồn tại để sửa, chỉ ở một tầng thấp
        hơn.
        """
        ssh = self.khoi.lay("ssh")
        self.assertIsNotNone(ssh)
        if ssh.trang_thai is not TrangThai.ACTIVE:
            self.assertIn(ssh.trang_thai,
                          (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE))
            self.assertTrue(ssh.ly_do, "không nối được phải kèm lý do")
            self.skipTest(f"SSH không nối được: {ssh.ly_do}")

    def test_doc_duoc_trang_thai_systemd(self):
        if (self.khoi.lay("ssh") or {}) and \
                self.khoi.lay("ssh").trang_thai is not TrangThai.ACTIVE:
            self.skipTest("SSH không nối được")
        q = self.khoi.lay("service_state")
        self.assertIsNotNone(q, "không có quan sát `service_state`")
        self.assertIn(q.trang_thai, (TrangThai.ACTIVE, TrangThai.DEGRADED,
                                     TrangThai.DOWN))
        self.assertTrue(q.nguon.startswith("ssh:"))

    def test_moi_quan_sat_deu_co_NGUON_va_MOC_THOI_GIAN(self):
        for q in self.khoi.quan_sat:
            with self.subTest(khoa=q.khoa):
                self.assertTrue(q.nguon, f"{q.khoa} thiếu nguồn")
                if q.trang_thai.do_duoc:
                    self.assertGreater(q.do_luc, 0, f"{q.khoa} thiếu mốc")

    def test_KHONG_lo_noi_dung_khoa_ra_bang_chung(self):
        """Bằng chứng thô đi vào UI/nhật ký — không được mang bí mật."""
        for q in self.khoi.quan_sat:
            with self.subTest(khoa=q.khoa):
                self.assertNotIn("PRIVATE KEY", q.bang_chung)
                self.assertNotIn("fanficappwrite", q.bang_chung)


class TestInRaBangChung(unittest.TestCase):
    """In ảnh chụp SỐNG ra để đọc bằng mắt.

    Không phải một phép kiểm — là một cách lấy bằng chứng bằng đúng
    đường mà bộ kiểm được phép chạy. Giữ lại vì lần nghiệm thu sau cũng
    cần đúng thứ này.
    """

    def test_in_anh_chup(self):
        from scripts.control_center.ghi_utf8 import GhiUTF8
        from scripts.control_center.observability.service import \
            tom_tat_cho_leader
        from scripts.control_center.observability.model import AnhChupSong

        cfg = _cau_hinh_fanfic()
        if not cfg or not cf.duong_khoa_ton_tai(cfg.get("key_path") or ""):
            self.skipTest("không có khoá đã cấu hình")
        ghi = GhiUTF8()
        k = SshServiceProvider(cfg).thu({})
        a = AnhChupSong(project_id="fanfic")
        a.dich_vu[k.khoa] = k
        ghi("")
        ghi(f"== {k.nhan}: {k.trang_thai.value} ==")
        for q in k.quan_sat:
            ghi(f"   {q.khoa:<16} {q.hieu_luc().value:<12} "
                f"{q.gia_tri if q.gia_tri is not None else '-'}"
                + (f"   [{q.ly_do}]" if q.ly_do else ""))
        ghi("")
        ghi(tom_tat_cho_leader(a))


if __name__ == "__main__":
    unittest.main(verbosity=2)

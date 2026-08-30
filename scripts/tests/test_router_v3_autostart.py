"""Tự khởi động cầu nối lúc đăng nhập — Router LTS Phase 6.

KHÔNG đăng ký Scheduled Task thật trong bài kiểm (mutating máy CI/dev là
tác dụng phụ thật, không sandbox được như thư mục tạm) — chỉ kiểm phần
dựng lệnh THUẦN và các đường đọc (`--check`/`--query`) trên một tên task
CHẮC CHẮN không tồn tại.
"""
from __future__ import annotations

import os
import sys
import unittest
from io import StringIO
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3 import setup_autostart as sa

_TEN_KHONG_TON_TAI = "AG_KHONG_TON_TAI_9999"

#: `schtasks` chỉ có trên Windows — bài học từ `test_setup_shared_root.py`
#: (CI Ubuntu báo "errors=2" trước khi thêm skip này ở đó). Áp dụng NGAY
#: từ đầu ở đây thay vì đợi CI báo lại cùng một lỗi.
_BO_QUA_KHONG_WINDOWS = unittest.skipUnless(
    os.name == "nt", "setup_autostart.py dùng schtasks — chỉ có trên Windows")


class DungLenhTest(unittest.TestCase):
    def test_lenh_co_worker_id_va_workspace(self):
        lenh = sa.dung_lenh_khoi_dong(
            "AG02", workspace_root="C:/FanficWorkers/workers",
            model="gemini-3.7-flash-low", allow_edits=True,
            dangerously_skip_permissions=True, pairing_file="")
        self.assertIn("--worker-id AG02", lenh)
        self.assertIn('--workspace "C:/FanficWorkers/workers"', lenh)
        self.assertIn("--allow-edits", lenh)
        self.assertIn("--dangerously-skip-permissions", lenh)

    def test_khong_co_pairing_file_thi_khong_co_co_do(self):
        lenh = sa.dung_lenh_khoi_dong(
            "AG02", workspace_root="C:/ws", model="m", allow_edits=False,
            dangerously_skip_permissions=False, pairing_file="")
        self.assertNotIn("--pairing-file", lenh)

    def test_worker_id_chua_ky_tu_dieu_khien_cmd_bi_TU_CHOI(self):
        """Bai quyet dinh: review doc lap tim thay worker_id/duong dan noi
        THANG vao chuoi cmd cho schtasks se chay lai o lan kich hoat sau —
        mot worker_id nhu `AG02" & calc.exe & "` se CHEN THEM lenh that."""
        for xau_hong in ('AG02" & calc.exe & "', "AG02;rm -rf", 'AG"02'):
            with self.assertRaises(ValueError):
                sa.dung_lenh_khoi_dong(
                    xau_hong, workspace_root="C:/ws", model="m",
                    allow_edits=False, dangerously_skip_permissions=False,
                    pairing_file="")

    def test_model_chua_ky_tu_dieu_khien_cmd_bi_TU_CHOI(self):
        with self.assertRaises(ValueError):
            sa.dung_lenh_khoi_dong(
                "AG02", workspace_root="C:/ws", model='m" & calc.exe & "',
                allow_edits=False, dangerously_skip_permissions=False,
                pairing_file="")

    def test_duong_dan_chua_dau_ngoac_kep_bi_TU_CHOI(self):
        with self.assertRaises(ValueError):
            sa.dung_lenh_khoi_dong(
                "AG02", workspace_root='C:/ws" & calc.exe & "x', model="m",
                allow_edits=False, dangerously_skip_permissions=False,
                pairing_file="")

    def test_worker_id_binh_thuong_van_qua_duoc(self):
        lenh = sa.dung_lenh_khoi_dong(
            "AG02", workspace_root="C:/ws", model="gemini-3.7-flash-low",
            allow_edits=False, dangerously_skip_permissions=False,
            pairing_file="")
        self.assertIn("--worker-id AG02", lenh)

    def test_co_pairing_file_thi_co_duong_dan(self):
        lenh = sa.dung_lenh_khoi_dong(
            "AG02", workspace_root="C:/ws", model="m", allow_edits=False,
            dangerously_skip_permissions=False,
            pairing_file="C:/FanficWorkers/pairing/AG02.pair")
        self.assertIn('--pairing-file "C:/FanficWorkers/pairing/AG02.pair"', lenh)


class TenTaskTest(unittest.TestCase):
    def test_ten_task_gan_voi_worker_id(self):
        self.assertEqual(sa.TEN_TASK_MAU.format(worker_id="AG02"),
                         "RouterBridge_AG02")


@_BO_QUA_KHONG_WINDOWS
class KiemTraTrenTaskKhongTonTaiTest(unittest.TestCase):
    """schtasks /query THẬT trên một tên chắc chắn không có — an toàn, chỉ đọc."""

    def test_kiem_tra_task_khong_ton_tai_ra_False(self):
        self.assertFalse(sa.kiem_tra(_TEN_KHONG_TON_TAI))

    def test_main_check_task_khong_ton_tai_thoat_ma_1(self):
        buf = StringIO()
        with redirect_stdout(buf):
            rc = sa.main(["--worker-id", _TEN_KHONG_TON_TAI, "--check"])
        self.assertEqual(rc, 1)
        self.assertIn("chưa đăng ký", buf.getvalue())

    def test_main_thieu_workspace_root_bao_ro(self):
        buf = StringIO()
        with redirect_stdout(buf):
            rc = sa.main(["--worker-id", "AG02"])
        self.assertEqual(rc, 2)
        self.assertIn("Thiếu", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

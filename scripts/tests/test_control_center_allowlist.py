"""Bài kiểm ALLOWLIST của agent — khoá lại cả hai chiều.

Quyền `command(...)` của `agy` khớp **chuỗi chính xác** (đo 2026-09-08:
`command(git)` và `command(git *)` đều KHÔNG cho chạy `git status
--porcelain`). Nên có đúng hai cách hỏng, và bài kiểm ở đây chặn cả hai:

    LỆCH   danh sách trong mã và tệp settings thật trôi khỏi nhau. Lúc đó
           agent nhận một chuỗi lệnh mà `agy` từ chối — hỏng LẶNG LẼ, mất
           trắng một lượt, và thông báo thật chỉ nằm ở stderr.
    NỚI    ai đó thêm `command(*)` (hoặc một escape-hatch như
           `escalate_admin`) cho tiện. Đó là truy cập hệ tệp tuỳ ý bằng
           shell, đúng thứ cả tầng này tồn tại để không phải cấp.

BÀI KIỂM NÀY CHẠY OFFLINE. Nó không gọi `agy`, không tốn quota, chạy được
trong CI. Phần chứng minh bằng tiến trình `agy` THẬT (lệnh được phép chạy
được, lệnh bị cấm vẫn bị từ chối) nằm ở
`scripts/control_center_allowlist_proof.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.planner import (KHONG_CAP_CHO_AGENT,
                                            LENH_CHO_PHEP)

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "scripts" / "cc_agent_tool.py"
SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

#: Khong mot muc allowlist nao duoc chua nhung chuoi nay.
CAM = ("command(*)", "read_file(*)", "write_file(*)", "escalate_admin",
       "dangerously", "bypassPermissions")


class TestAllowlistKhopSettings(unittest.TestCase):
    """Danh sách trong mã và tệp settings thật không được lệch nhau."""

    @unittest.skipUnless(SETTINGS.is_file(),
                         "máy này chưa có settings.json của agy")
    def test_settings_that_cho_phep_DUNG_nhung_lenh_trong_ma(self):
        d = json.loads(SETTINGS.read_text(encoding="utf-8"))
        allow = list(((d.get("permissions") or {}).get("allow")) or [])
        mong_doi = [f"command({c})" for c in LENH_CHO_PHEP]
        self.assertEqual(sorted(allow), sorted(mong_doi),
                         "allowlist trong settings.json đã trôi khỏi "
                         "`planner.LENH_CHO_PHEP`")

    @unittest.skipUnless(SETTINGS.is_file(), "chưa có settings.json")
    def test_settings_KHONG_chua_ky_tu_dai_dien_hay_escape_hatch(self):
        tho = SETTINGS.read_text(encoding="utf-8")
        for x in CAM:
            with self.subTest(cam=x):
                self.assertNotIn(x, tho)

    @unittest.skipUnless(SETTINGS.is_file(), "chưa có settings.json")
    def test_dong_tu_CHAM_khong_duoc_cap_cho_agent(self):
        """`tests` chạy ~430s; một lượt headless có trần 180s.

        Cấp nó cho agent nghĩa là mỗi lần dùng đều hết giờ — đốt một lượt mà
        không cho kết quả nào. Bộ kiểm đầy đủ là việc của CI và người vận
        hành, không phải của một lượt agent.
        """
        tho = SETTINGS.read_text(encoding="utf-8")
        for c in KHONG_CAP_CHO_AGENT:
            with self.subTest(lenh=c):
                self.assertNotIn(c, tho)


class TestAllowlistHopLe(unittest.TestCase):
    """Mỗi chuỗi được phép phải THẬT SỰ chạy được, và phải hẹp."""

    def test_moi_lenh_tro_toi_wrapper_bang_duong_dan_TUYET_DOI(self):
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertIn("cc_agent_tool.py", c)
                self.assertTrue(c.startswith("python C:\\"),
                                "đường dẫn tuyệt đối ghim SCRIPT NÀO chạy; "
                                "đường dẫn tương đối để `cwd` đổi mục tiêu")
                self.assertNotIn("*", c)

    def test_dong_tu_cua_moi_lenh_co_that_trong_wrapper(self):
        from scripts.cc_agent_tool import DONG_TU
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertIn(c.rsplit(" ", 1)[1], DONG_TU)

    def test_wrapper_khong_dung_shell_True(self):
        """`shell=True` biến mọi phần tử argv thành một chuỗi shell diễn
        giải được — tức là mở lại đúng cánh cửa vừa đóng.

        Kiểm trên CÂY CÚ PHÁP, không grep văn bản: chính docstring của
        wrapper GIẢI THÍCH rằng nó không bao giờ dùng `shell=True`, nên một
        phép grep sẽ báo động vì đúng câu nói nó an toàn. Cùng bài học đã
        gặp ở `test_control_center_core.TestRaoAnToanTinh`.
        """
        import ast
        cay = ast.parse(TOOL.read_text(encoding="utf-8"))
        for n in ast.walk(cay):
            if isinstance(n, ast.keyword) and n.arg == "shell":
                self.assertFalse(
                    isinstance(n.value, ast.Constant) and n.value.value is True,
                    "wrapper đặt shell=True trong MÃ CHẠY")


class TestWrapperChanDiVong(unittest.TestCase):
    """`cwd`/đường dẫn KHÔNG được biến một lệnh hẹp thành thực thi tuỳ ý."""

    def _chay(self, verb: str, cwd: Path):
        return subprocess.run(
            [sys.executable, str(TOOL), verb], cwd=str(cwd),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)

    def test_cwd_NGOAI_kho_bi_tu_choi(self):
        """Đây là bài kiểm quan trọng nhất của tệp này.

        `python -m unittest discover -s scripts/tests -t .` giải đường dẫn
        theo `cwd`. Nếu `cwd` là một cây khác có `scripts/tests/` riêng, cùng
        một chuỗi lệnh ĐÃ ĐƯỢC DUYỆT sẽ nạp và chạy mã ở đó. Wrapper phải
        chặn trước khi tới đó.
        """
        ngoai = Path(tempfile.mkdtemp(prefix="cc-outside-"))
        (ngoai / "scripts" / "tests").mkdir(parents=True)
        (ngoai / "scripts" / "tests" / "test_evil.py").write_text(
            "raise SystemExit('mã lạ đã chạy')", encoding="utf-8")
        for verb in ("changes", "compile", "tests"):
            with self.subTest(verb=verb):
                p = self._chay(verb, ngoai)
                self.assertEqual(p.returncode, 2)
                self.assertIn("TỪ CHỐI", p.stdout + p.stderr)
                self.assertNotIn("mã lạ đã chạy", p.stdout + p.stderr)

    def test_cwd_TRONG_kho_duoc_chap_nhan(self):
        """Siết chặt không được biến công cụ thành vô dụng."""
        p = self._chay("changes", REPO)
        self.assertEqual(p.returncode, 0)

    def test_dong_tu_LA_bi_tu_choi(self):
        p = subprocess.run(
            [sys.executable, str(TOOL), "rm-rf"], cwd=str(REPO),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("invalid choice", p.stdout + p.stderr)

    def test_wrapper_KHONG_nhan_tham_so_tuy_y(self):
        """Không có đường nào truyền một chuỗi tuỳ ý xuống `subprocess`."""
        p = subprocess.run(
            [sys.executable, str(TOOL), "changes", "--", "extra"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertNotEqual(p.returncode, 0)

    def test_argv_cua_moi_dong_tu_la_HANG_SO(self):
        """Không phần tử argv nào được lấy từ dòng lệnh hay môi trường."""
        from scripts.cc_agent_tool import DONG_TU
        for verb, argv in DONG_TU.items():
            with self.subTest(verb=verb):
                self.assertTrue(all(isinstance(x, str) for x in argv))
                self.assertNotIn("*", " ".join(argv))


if __name__ == "__main__":
    unittest.main()

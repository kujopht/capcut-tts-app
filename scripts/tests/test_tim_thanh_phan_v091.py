# -*- coding: utf-8 -*-
"""TRA CỨU THÀNH PHẦN — người dùng KHÔNG phải nhớ đường dẫn nội bộ.

Thất bại đo được (dogfood thật, 2026-09-12). Người dùng hỏi:

    "ê cái tool cạo audio t sao r"

Leader tra Ký ức/Viên nang, trượt, rồi HỎI NGƯỢC người dùng tên script/thư
mục. Nhưng thứ đó có thật trong kho — `server/scraper/` — nên đây không phải
thiếu kiến thức mà là THIẾU PHÉP TRA CỨU.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.tim_thanh_phan import (BoTimThanhPhan, goi_tra_loi,
                                                   mo_rong_tu_khoa)
from scripts.router_v3.tien_trinh import an_cua_so


def _git(cwd: Path, *a: str):
    return subprocess.run(["git", *a], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=60, **an_cua_so())


class TestMoRongTuKhoa(unittest.TestCase):
    """Tiếng nói tự nhiên -> từ khoá kỹ thuật. TẤT ĐỊNH."""

    def test_01_cao_va_cao_deu_ra_scrape(self):
        for c in ("tool cạo audio", "con bot cào truyện"):
            self.assertIn("scrape", mo_rong_tu_khoa(c), c)

    def test_02_audio_keo_theo_tts_va_ytdlp(self):
        tu = mo_rong_tu_khoa("cái tool cạo audio")
        self.assertIn("tts", tu)
        self.assertIn("yt_dlp", tu)

    def test_03_web_keo_theo_ha_tang_web(self):
        tu = mo_rong_tu_khoa("cái web fanfic giờ sao rồi")
        self.assertIn("cloudflare", tu)
        self.assertIn("next", tu)

    def test_04_giu_ten_rieng_trong_cau(self):
        self.assertIn("appwrite", mo_rong_tu_khoa("phần appwrite sao rồi"))


class TestThangLeo(unittest.TestCase):
    """Kho giả có ĐÚNG hình dạng thật: mã, tài liệu, bài kiểm."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="tim-tp-"))
        for d, t in (
            ("server/scraper/__init__.py", "# scraper package\n"),
            ("server/scraper/chinese_media_sources.py", "import yt_dlp\n"),
            ("server/tests/test_scrape.py", "# test scrape\n"),
            ("web/next.config.mjs", "export default {}\n"),
            ("scripts/farmer_service_ctl.py", "# farmer ctl\n"),
            ("docs/reports/story-harvester-scrape-audio.md", "scrape audio\n"),
            ("deploy/bootstrap-farmer.sh", "#!/bin/sh\n"),
        ):
            p = self.repo / d
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(t, encoding="utf-8")
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "init")
        self.bt = BoTimThanhPhan("demo", self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_05_TIM_RA_tool_cao_audio(self):
        """Câu hỏi THẬT đã làm Leader bó tay."""
        kq = self.bt.tim("ê cái tool cạo audio t sao r")
        self.assertTrue(kq.ung_vien, "không tìm ra ứng viên nào")
        self.assertEqual(kq.ung_vien[0]["ten"], "server/scraper",
                         [u["ten"] for u in kq.ung_vien])

    def test_06_docs_KHONG_duoc_lam_ung_vien(self):
        """Tên tệp báo cáo khớp gần như mọi từ khoá — để nó dự thi thì `docs`
        luôn thắng và câu trả lời thành vô dụng. Đo được ở lần thử đầu:
        `docs` 51 điểm trên `server/scraper` 45."""
        kq = self.bt.tim("tool cạo audio")
        self.assertNotIn("docs", [u["ten"] for u in kq.ung_vien])
        self.assertNotIn("deploy", [u["ten"] for u in kq.ung_vien])

    def test_07_thu_muc_bai_kiem_khong_lam_ung_vien(self):
        kq = self.bt.tim("tool cạo audio")
        for u in kq.ung_vien:
            self.assertNotIn("tests", u["ten"])

    def test_08_web_ra_thanh_phan_web(self):
        kq = self.bt.tim("còn cái web fanfic giờ sao rồi?")
        self.assertEqual(kq.ung_vien[0]["ten"], "web",
                         [u["ten"] for u in kq.ung_vien])

    def test_09_farmer_ra_cong_cu_farmer(self):
        kq = self.bt.tim("con farmer sao rồi")
        self.assertTrue(any("farmer" in u["ten"] for u in kq.ung_vien),
                        [u["ten"] for u in kq.ung_vien])

    def test_10_docs_van_duoc_giu_lam_BANG_CHUNG(self):
        """Loại khỏi ứng viên KHÔNG có nghĩa là vứt đi."""
        kq = self.bt.tim("tool cạo audio")
        self.assertTrue(any("docs/" in b.duong for b in kq.bang_chung),
                        "mất bằng chứng tài liệu")

    def test_11_khong_tim_thay_thi_NOI_KHONG_TIM_THAY(self):
        kq = self.bt.tim("cái máy giặt lượng tử")
        self.assertFalse(kq.ung_vien)
        self.assertIn("KHÔNG tìm thấy", goi_tra_loi(kq))

    def test_12_luon_khai_VUNG_KHONG_PHU(self):
        """Không giả vờ với tới lịch sử ChatGPT Project."""
        kq = self.bt.tim("tool cạo audio")
        van = " ".join(kq.khong_voi_toi)
        self.assertIn("ChatGPT", van)
        self.assertIn("VÙNG KHÔNG PHỦ", goi_tra_loi(kq))

    def test_13_ghi_lai_DA_TRA_NHUNG_BAC_NAO(self):
        kq = self.bt.tim("tool cạo audio")
        self.assertIn("kho", kq.da_tra)
        self.assertIn("đã tra:", goi_tra_loi(kq))

    def test_14_chac_khi_mot_ung_vien_noi_troi(self):
        kq = self.bt.tim("ê cái tool cạo audio t sao r")
        self.assertTrue(kq.chac, [u["ten"] for u in kq.ung_vien])

    def test_15_KHONG_nhan_chuoi_lenh(self):
        import inspect
        src = inspect.getsource(BoTimThanhPhan)
        self.assertNotIn("shell=True", src)


if __name__ == "__main__":
    unittest.main()

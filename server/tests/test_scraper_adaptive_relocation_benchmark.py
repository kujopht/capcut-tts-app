"""
P2 (Story Harvester V3 overnight hardening), Section 9 — do CHI PHI THAT
cua adaptive relocation qua Scrapling so voi duong Tier 0 binh thuong tren
MOT trang chuong dai dai dien (~15KB HTML, tuong tu quy mo mot chuong tieu
thuyet that). Khong khang khang mot con so tuyet doi (bap benh giua may),
CHI kiem tra THUOC TINH: chi phi CO GIOI HAN ro rang (khong bung no vo tan,
khong ton hang chuc giay cho MOT trang), va IN ra so THAT de dua vao bao
cao cuoi (xem yeu cau nhiem vu: "DIRECT NORMAL PARSE: / SCRAPLING
RELOCATION: / MEMORY: / WALL TIME:")."""
from __future__ import annotations

import time
import tracemalloc
import unittest

from server.scraper.adapters.scrapling_relocation import (
    relocate_verified_element, save_verified_element, validate_relocated_candidate,
)
from server.scraper.content_extraction import extract_content_v3

_URL = "https://vd-benchmark.test/truyen/1/chuong/50"
_TIEU_DE = "Chapter 50: A Long Realistic Chapter"


def _trang_chuong_dai(so_doan: int = 60) -> str:
    """~60 doan, gan quy mo mot chuong tieu thuyet thuc te (~15-20KB)."""
    doan_van = "".join(
        f"<p>Đoạn văn thứ {i} của chương, đủ dài để mô phỏng một chương "
        f"tiểu thuyết thực tế với nhiều đoạn văn nối tiếp nhau, câu chữ "
        f"trôi chảy và có độ dài tương đương một đoạn văn xuôi bình "
        f"thường trong tiểu thuyết mạng, số hiệu đoạn: {i}.</p>"
        for i in range(1, so_doan + 1))
    return f"""
<html><body>
<header>Site Header</header>
<nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="story-body" id="content-main"><h1>{_TIEU_DE}</h1>{doan_van}</div>
<footer>Copyright 2024</footer>
</body></html>"""


_HTML_GOC = _trang_chuong_dai()
#: Kich ban "selector doi ten" (A trong ma tran 9 kich ban) — dai dien cho
#: TRUONG HOP THUC SU can nang tang (Tier 0 that bai hoan toan).
_HTML_DA_DOI_CAU_TRUC = _HTML_GOC.replace(
    'class="story-body" id="content-main"', 'class="chapter-text-v2" id="content-main-2024"')


class DirectParseVsScraplingRelocationBenchmarkTest(unittest.TestCase):
    def test_chi_phi_co_gioi_han_va_ghi_lai_so_that(self):
        # --- DIRECT NORMAL PARSE (Tier 0, duong thanh cong binh thuong) ---
        t0 = time.perf_counter()
        tracemalloc.start()
        for _ in range(5):
            ket_qua_truc_tiep = extract_content_v3(_HTML_GOC, chapter_title=_TIEU_DE)
        _, dinh_bo_nho_truc_tiep = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        thoi_gian_truc_tiep = (time.perf_counter() - t0) / 5
        self.assertGreater(len(ket_qua_truc_tiep.clean_text), 100)

        # --- SCRAPLING RELOCATION (Tier 1, save + relocate + validate) ---
        fp = save_verified_element(_HTML_GOC, "div.story-body", url=_URL)
        self.assertIsNotNone(fp)

        t0 = time.perf_counter()
        tracemalloc.start()
        for _ in range(5):
            candidates = relocate_verified_element(_HTML_DA_DOI_CAU_TRUC, fp, url=_URL)
            ket_qua_relocation = validate_relocated_candidate(
                candidates, chapter_title=_TIEU_DE)
        _, dinh_bo_nho_relocation = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        thoi_gian_relocation = (time.perf_counter() - t0) / 5

        print(
            f"\n[P2 Benchmark] DIRECT NORMAL PARSE: {thoi_gian_truc_tiep * 1000:.2f}ms, "
            f"peak={dinh_bo_nho_truc_tiep / 1024:.1f}KB\n"
            f"[P2 Benchmark] SCRAPLING RELOCATION: {thoi_gian_relocation * 1000:.2f}ms, "
            f"peak={dinh_bo_nho_relocation / 1024:.1f}KB\n"
            f"[P2 Benchmark] OVERHEAD RATIO: "
            f"{(thoi_gian_relocation / thoi_gian_truc_tiep):.1f}x wall time, "
            f"{(dinh_bo_nho_relocation / dinh_bo_nho_truc_tiep):.1f}x peak memory")

        self.assertEqual(candidates.count, 1)
        self.assertFalse(candidates.is_ambiguous)
        from server.scraper.self_healing import RelocationConfidence
        self.assertEqual(ket_qua_relocation.confidence, RelocationConfidence.HIGH)

        # Gioi han RONG RAI (khong phai hieu nang toi uu, chi bat regression
        # tho): mot trang ~15-20KB khong duoc ton hon 2 giay cho relocation,
        # va khong duoc ton hon 20MB dinh bo nho cho MOT lan goi.
        self.assertLess(thoi_gian_relocation, 2.0,
                        "Scrapling relocation cham bat thuong tren MOT trang chuong")
        self.assertLess(dinh_bo_nho_relocation, 20 * 1024 * 1024,
                        "Scrapling relocation ton bo nho bat thuong tren MOT trang chuong")

    def test_duong_thanh_cong_khong_can_scrapling_nhanh_hon_nhieu(self):
        """Xac nhan truc tiep: duong Tier 0 THANH CONG (khong can nang
        tang) khong PHAI tra chi phi cua Scrapling — day la ly do
        `scraper_ops_service.py` CHI goi `attempt_adaptive_relocation` khi
        Tier 0 CHUA dat HIGH (xem test wiring rieng), khong phai boi test
        nay, nhung so lieu o day cho thay ro TAI SAO dieu do quan trong."""
        t0 = time.perf_counter()
        for _ in range(20):
            extract_content_v3(_HTML_GOC, chapter_title=_TIEU_DE)
        thoi_gian_truc_tiep = (time.perf_counter() - t0) / 20
        self.assertLess(thoi_gian_truc_tiep, 0.05,
                        "Duong Tier 0 binh thuong PHAI rat nhanh (khong Scrapling)")


if __name__ == "__main__":
    unittest.main()

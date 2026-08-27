"""
Overnight mega task, Phase 8 ("memory/CPU characterization" — O(N^2) hunt).

Do THAT (cProfile) tren mot dot 4000 chuong tim ra HAI nguyen nhan chinh
cua chi phi O(N^2) tren mot dot dai:

  1. `dedupe.ScrapeState.find_canonical_urls_by_content_hash` quet TOAN BO
     `_rows` MOI LAN GOI (mot lan cho MOI chuong trong `bulk.py::drive_once`)
     — sua bang chi so nguoc `content_hash -> canonical_urls` duy tri TANG
     DAN (O(1) moi lan ghi).
  2. `GenericIndexAdapter/NavigationOnlyAdapter._boilerplate_hashes_cho`
     quet TOAN BO doan van DUY NHAT tung thay tren site MOI LAN GOI — sua
     bang mot TAP "da xac nhan boilerplate" duy tri TANG DAN, chi chua cac
     hash THAT SU vuot nguong (nho, on dinh, khong tang theo so chuong).

Bai test o day KHONG kiem tra "nhanh" theo mot con so thoi gian cu the
(qua bap benh giua cac may) — kiem tra THUOC TINH: thoi gian TRUNG BINH
MOI CHU KY o CUOI dot KHONG duoc lon hon dang ke so voi o DAU dot. Neu
mot ai do sau nay VO Y dua lai mot vong lap O(N) an trong duong drive
moi chu ky, ty le nay se tang manh tro lai va test se bat duoc.
"""
from __future__ import annotations

import time
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import MockScrapeRunStore

_BASE = "https://vd-scale.example"


def _make_pages(n: int) -> dict:
    links = "".join(f'<li><a href="/truyen/x/chuong-{i}">C{i}</a></li>' for i in range(1, n + 1))
    pages = {f"{_BASE}/truyen/x": f"<html><body><ul>{links}</ul></body></html>"}
    for i in range(1, n + 1):
        pages[f"{_BASE}/truyen/x/chuong-{i}"] = (
            f"<html><body><article><h1>Chương {i}</h1><p>"
            + ("Nội dung đầy đủ, duy nhất của riêng chương này. " * 15)
            + f"Số hiệu riêng: {i}.</p></article></body></html>")
    return pages


def _thoi_gian_cac_chu_ky(n: int, chapters_per_cycle: int):
    pages = _make_pages(n)
    adapter = GenericIndexAdapter(FixtureFetcher(dict(pages)), chapter_href_pattern=r"/chuong-\d+")
    pipeline = StoryIngestionPipeline(adapter, ScrapeState())
    store = MockScrapeRunStore()
    service = ScrapeRunService(pipeline, store, chapters_per_cycle=chapters_per_cycle)
    run = service.plan_run(f"{_BASE}/truyen/x")

    cycle_times = []
    while True:
        r = store.get_run(run.run_id)
        if r.is_terminal:
            break
        t0 = time.perf_counter()
        service.drive_once(run.run_id)
        cycle_times.append(time.perf_counter() - t0)
    return cycle_times


class NoQuadraticBlowupTest(unittest.TestCase):
    #: Ty le toi da CHAP NHAN duoc giua chu ky CUOI va chu ky DAU cua MOT
    #: dot — o hanh vi O(N) that su, ty le nay xap xi 1.0x bat ke N; o
    #: hanh vi O(N^2) (da sua), ty le nay tang tuyen tinh theo N (do
    #: luong that TRUOC ban sua: ~4.4x o N=5000). 3.0x la nguong RONG RAI,
    #: chiu duoc nhieu bien dong may/moi truong, nhung van bat duoc mot
    #: hoi quy O(N^2) that su quay lai.
    _TRAN_TY_LE_CHAP_NHAN_DUOC = 3.0

    def test_thoi_gian_chu_ky_khong_tang_theo_so_chuong_da_xu_ly(self):
        cycle_times = _thoi_gian_cac_chu_ky(3000, chapters_per_cycle=50)
        so_chu_ky_mau = min(5, len(cycle_times) // 2)
        self.assertGreater(so_chu_ky_mau, 0)

        trung_binh_dau = sum(cycle_times[:so_chu_ky_mau]) / so_chu_ky_mau
        trung_binh_cuoi = sum(cycle_times[-so_chu_ky_mau:]) / so_chu_ky_mau

        ty_le = trung_binh_cuoi / trung_binh_dau if trung_binh_dau > 0 else 1.0
        self.assertLess(
            ty_le, self._TRAN_TY_LE_CHAP_NHAN_DUOC,
            f"Chu ky CUOI cham hon chu ky DAU {ty_le:.2f}x — nghi ngo mot "
            "vong lap O(N) moi chu ky da quay lai (xem docstring module).")


if __name__ == "__main__":
    unittest.main()

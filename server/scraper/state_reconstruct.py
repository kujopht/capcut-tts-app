"""
Xay lai `ScrapeState` (`dedupe.py`) TU cac `ScrapeRunItem` da luu ben vung
(Appwrite/Mock) — cau noi giua tang dieu phoi (`bulk.py`, chi luu METADATA
trang thai) va `StoryIngestionPipeline` (can `ScrapeState` that de
resume()/phat hien revision dung).

VI SAO CAN FILE NAY: `dedupe.ScrapeState` tu nhan la "trang thai TRONG BO
NHO — lop ben vung THAT la viec cua noi goi" (xem docstring lop do). Moi
yeu cau HTTP toi API quan tri tao MOT `StoryIngestionPipeline` moi (khong
co bo nho giua cac yeu cau), nen truoc khi dung pipeline do, phai NAP LAI
`ScrapeState` tu nguon THAT SU ben vung — chinh la cac `ScrapeRunItem` da
co trong kho cua dot scrape nay.

NGUON SU THAT DUY NHAT: `ScrapeRunItem` (khong phai mot ban sao doc lap
cua `ScrapeState`). Ham nay CHI phat lai lich su qua `record_success`/
`record_failure`/`record_skip` — khong tu tao du lieu moi.
"""
from __future__ import annotations

from server.scraper.dedupe import ScrapeState
from server.scraper.run_state import ScrapeItemStatus


def rebuild_state(store, run_id: str) -> ScrapeState:
    """Nap lai TOAN BO muc cua `run_id` (khong gioi han `limit`, xem
    `store.list_items(..., limit=None)`) thanh mot `ScrapeState` moi."""
    state = ScrapeState()
    items = store.list_items(run_id, statuses=None, limit=None)
    for item in items:
        if item.status is ScrapeItemStatus.REVIEW_READY:
            state.record_success(
                item.chapter_url, content_hash_value=item.content_hash,
                chapter_number=item.chapter_number)
        elif item.status is ScrapeItemStatus.FAILED:
            state.record_failure(item.chapter_url)
        elif item.status is ScrapeItemStatus.SKIPPED:
            state.record_skip(item.chapter_url)
        # PENDING: chua xu ly, khong co gi de phat lai vao state.
    return state

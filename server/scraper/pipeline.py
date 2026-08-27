"""
Bo dieu phoi (orchestrator) noi cac manh Tier 0 da co (`contract.py`,
`dedupe.py`, `adapters/`) thanh MOT luong nhap truyen dau-cuoi:

    URL vao
      -> resolve nguon (StoryProvider.resolve)
      -> kham pha series + danh sach chuong (discover_series/list_chapters)
      -> loc con lai can lam (resume — bo qua chuong da xong, thu lai chuong
         loi lan truoc — xem `dedupe.ScrapeState`)
      -> voi TUNG chuong: tai + chuan hoa + tinh fingerprint/dedupe
      -> phan loai NEW / REVISION / ALREADY_IMPORTED / FAILED
      -> cham diem chat luong TAT DINH (server/scraper/quality.py — khong
         AI/LLM, xem module do cho triet ly BLOCK/WARN)
      -> tra ve HANG DOI DUYET (review queue) — KHONG tu dong ghi vao
         Novel/Chapter that su o dau ca.

PHAM VI: file nay LA tang dieu phoi giua cac manh scraper da co, KHONG PHAI
tang tich hop vao Appwrite/API quan tri — dung y, xem docstring
`server/scraper/__init__.py` ("nen tang, KHONG phai mot tinh nang bat/xuat
ban"). Ket qua `run()` la mot DANH SACH `ReviewItem` trong bo nho cua LAN
GOI do — chua duoc luu vao mot kho hang doi ben vung nao. Neu sau nay can
mot khu quan tri THAT duyet hang doi nay qua nhieu phien lam viec, do la
mot lop tich hop THEM (giong `TrustedSourceService`/`video_imports` da co
cho YouTube), khong phai viec cua file nay.

DUY NHAT `ScrapeState` la ben vung duoc qua `to_json()`/`from_json()` —
day la thu cho phep "resumable import" that su: mot tien trinh bi ngat
giua chung, luu state, khoi dong lai, nap lai state, goi lai `run()` voi
CUNG url — cac chuong da xong (status "ok") tu dong duoc `resume()` bo
qua, KHONG lam lai.

AN TOAN THU LAI (idempotent): goi `run()` nhieu lan voi CUNG url + CUNG
state tra ve CUNG ket qua cho chuong da co (REVISION chi bao khi noi dung
THAT SU doi, khong bao gio "REVISION" hai lan lien tiep tren cung mot lan
chay khong doi gi).

DRY RUN: `run(url, dry_run=True)` chay HET pipeline (tai/chuan hoa/phan
loai) nhung KHONG ghi gi vao `state` — dung de xem truoc se xay ra gi
(bao nhieu chuong moi, bao nhieu revision) truoc khi cam ket that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from server.scraper.contract import NormalizedChapter, SeriesInfo, StoryProvider
from server.scraper.dedupe import ScrapeState
from server.scraper.quality import QualityReport, assess_chapter_quality


class IngestionDecision(Enum):
    #: Chuong chua tung thay — chua co ban ghi nao trong state cho url nay.
    NEW = "new"
    #: Da co ban ghi THANH CONG truoc do voi noi dung KHAC — nguon da sua
    #: lai chuong nay. State CU van con (xem `ScrapeState.record_success`),
    #: khong bi ghi de am tham.
    REVISION = "revision"
    #: Da co ban ghi THANH CONG truoc do voi CUNG noi dung — khong co gi
    #: moi. Trong luong `run()` binh thuong (qua `resume()` loc truoc), day
    #: hau nhu khong bao gio xay ra (chuong da xong bi loc som hon) — giu
    #: nhanh nay de xu ly dung khi ai do goi voi mot danh sach url KHONG
    #: qua `resume()` (vd kiem tra lai thu cong mot chuong cu the).
    ALREADY_IMPORTED = "already_imported"
    #: Tai hoac chuan hoa chuong nay that bai — LOI MOT CHUONG khong duoc
    #: lam hong ca lo (xem vong lap trong `run()`).
    FAILED = "failed"


@dataclass
class ReviewItem:
    """Mot dong trong hang doi duyet — `chapter` la `None` khi `decision`
    la `FAILED` (khong co gi de duyet, chi co loi de bao). `quality` la
    `None` cung khi `decision` la `FAILED` (khong co chuong nao de cham
    diem) — xem `server/scraper/quality.py` cho triet ly BLOCK/WARN.
    `quality.passed is False` la tin hieu operator NEN xem truoc/loai bo
    truoc khi duyet — pipeline nay KHONG tu loai bo, chi gan nhan."""

    url: str
    decision: IngestionDecision
    chapter: Optional[NormalizedChapter] = None
    error: Optional[str] = None
    quality: Optional[QualityReport] = None


@dataclass
class IngestionPlan:
    """Ket qua buoc LEN KE HOACH — CHUA tai chuong nao, chi kham pha muc
    luc + loc qua `resume()`. Re, dung de uoc luong truoc khi chay that."""

    series: SeriesInfo
    chapter_urls_to_process: List[str]
    #: So chuong DA co trong state (bi `resume()` loc ra) — khac voi so
    #: chuong SE xu ly, giup operator thay ro "con lai bao nhieu viec".
    already_done_count: int
    total_discovered: int


@dataclass
class IngestionResult:
    series: SeriesInfo
    review_items: List[ReviewItem] = field(default_factory=list)
    dry_run: bool = False

    def dem_theo_quyet_dinh(self) -> dict:
        """Tom tat nhanh cho operator — vi du hien trong giao dien duyet
        ma khong can dem tay tung `ReviewItem`."""
        dem = {d.value: 0 for d in IngestionDecision}
        for item in self.review_items:
            dem[item.decision.value] += 1
        return dem


class StoryIngestionPipeline:
    """Dieu phoi MOT `StoryProvider` (adapter Tier 0/1 cu the) + MOT
    `ScrapeState` (state ben vung, tiem vao tu ben ngoai — pipeline nay
    KHONG tu doc/ghi dia/Appwrite, giong nguyen tac dependency-injection
    da dung xuyen suot du an)."""

    def __init__(self, provider: StoryProvider, state: ScrapeState):
        self._provider = provider
        self._state = state

    @property
    def state(self) -> ScrapeState:
        """`ScrapeState` ben vung cua pipeline nay — CHI DOC/GHI, khong bao
        gio thay the doi tuong nay. Loi ra cho mot tang dieu phoi HANG LOAT
        ben ngoai (xem `server/scraper/bulk.py`) can doi soat/ghi truc tiep
        theo TUNG chuong ma khong di qua `run()` nguyen khoi (vd dieu phoi
        theo chu ky voi huy an toan giua chung)."""
        return self._state

    def plan(self, url: str, *, chapter_limit: Optional[int] = None) -> IngestionPlan:
        """Kham pha series + loc con lai can lam — KHONG tai bat ky chuong
        nao. Goi rieng buoc nay khi chi can uoc luong ("con bao nhieu
        chuong chua nhap") ma chua muon cam ket tai that."""
        series = self._provider.discover_series(url)
        chapter_urls = self._provider.list_chapters(series)
        con_lai_truoc_khi_cat = self._provider.resume(self._state, chapter_urls)
        con_lai = (con_lai_truoc_khi_cat[:chapter_limit] if chapter_limit is not None
                   else con_lai_truoc_khi_cat)
        return IngestionPlan(
            series=series,
            chapter_urls_to_process=con_lai,
            already_done_count=len(chapter_urls) - len(con_lai_truoc_khi_cat),
            total_discovered=len(chapter_urls),
        )

    def run(self, url: str, *, dry_run: bool = False,
            chapter_limit: Optional[int] = None) -> IngestionResult:
        """Chay pipeline day du. `chapter_limit` gioi han so chuong xu ly
        trong LAN GOI nay (vd canary/test that — xem Phase 3) — KHONG anh
        huong `resume()`, chi cat bot danh sach SAU khi da loc."""
        ke_hoach = self.plan(url, chapter_limit=chapter_limit)
        review_items: List[ReviewItem] = []
        # So chuong DA THAY trong CHINH lan chay nay — ngu canh "sibling"
        # tot nhat co san o day (khong nhin duoc lich su cac lan chay
        # truoc). Du de bat loi trich so ro rang trong mot lan quet.
        cac_so_chuong_da_thay: List[int] = []

        for chapter_url in ke_hoach.chapter_urls_to_process:
            try:
                raw_html = self._provider.fetch_chapter(chapter_url)
                chapter = self._provider.normalize_chapter(
                    chapter_url, raw_html, ke_hoach.series)
            except Exception as exc:
                # LOI MOT CHUONG khong duoc lam dung ca lo — ghi lai de
                # `resume()` biet thu lai o lan chay sau, roi TIEP TUC
                # chuong ke tiep (day la diem mau chot cua "ngat giua
                # chung mot lo van an toan"). BAT `Exception` NOI CHUNG
                # (khong chi `FetchError`/`ValueError`) — MOT trang HTML
                # bat thuong (vd long qua sau) co the lam mot buoc phan
                # tich noi bo (vd `content_extraction.py`) nem loi khong
                # luong truoc duoc; mot trang loi khong duoc phep dung ca
                # dot quet nhieu tram chuong khac — phat hien qua review
                # doc lap (Codex), tai hien that bang `RecursionError`
                # tren HTML long ~1000 cap the (da sua o nguon, nhung
                # nguyen tac "mot chuong loi khong dung ca lo" phai giu
                # vung ke ca voi loi KHONG LUONG TRUOC duoc trong tuong
                # lai).
                if not dry_run:
                    self._state.record_failure(chapter_url)
                review_items.append(ReviewItem(
                    url=chapter_url, decision=IngestionDecision.FAILED, error=str(exc)))
                continue

            if dry_run:
                quyet_dinh = self._phan_loai_khong_ghi(chapter)
            else:
                ban_ghi = self._state.record_success(
                    chapter_url, content_hash_value=chapter.content_hash,
                    chapter_number=chapter.chapter_number)
                quyet_dinh = (IngestionDecision.REVISION if ban_ghi.get("is_revision")
                              else IngestionDecision.NEW)

            bao_cao_chat_luong = assess_chapter_quality(
                chapter, sibling_chapter_numbers=cac_so_chuong_da_thay)
            if chapter.chapter_number is not None:
                cac_so_chuong_da_thay.append(chapter.chapter_number)

            review_items.append(ReviewItem(
                url=chapter_url, decision=quyet_dinh, chapter=chapter,
                quality=bao_cao_chat_luong))

        return IngestionResult(series=ke_hoach.series, review_items=review_items, dry_run=dry_run)

    def _phan_loai_khong_ghi(self, chapter: NormalizedChapter) -> IngestionDecision:
        """Nhanh DRY-RUN cua phan loai — DOC state (khong ghi) de doan
        truoc `run(dry_run=False)` se phan loai the nao."""
        ban_ghi_cu = self._state.get(chapter.canonical_url)
        if ban_ghi_cu is None:
            return IngestionDecision.NEW
        if ban_ghi_cu.get("status") != "ok":
            return IngestionDecision.NEW  # lan truoc that bai — coi nhu moi.
        if ban_ghi_cu.get("content_hash") == chapter.content_hash:
            return IngestionDecision.ALREADY_IMPORTED
        return IngestionDecision.REVISION

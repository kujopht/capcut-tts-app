"""
Engine cap nhat gia tang — Phase 9 cua Story Harvester V3.

Trai voi `bulk.py::plan_run` (goi lai de "TIEP TUC" mot dot dang do, luon
tao muc PENDING moi cho chuong chua co), module nay tra loi mot cau hoi
KHAC: "series NAY, DA quet xong truoc do, co gi MOI tren nguon hay khong,
ma CHI can MOT lan tai trang muc luc de biet?" — khong tao ScrapeRunItem
nao, khong ghi gi, chi la MOT LAN THAM DO re de operator quyet dinh co
dang chay lai hay khong.

CO Y CHUA lam: phat hien "CHANGED" (chuong DA co van con do nhung noi dung
nguon da sua) can tai lai NOI DUNG tung chuong da "ok" de so sanh
content_hash — trai voi NEW/REMOVED (chi can danh sach URL tu trang muc
luc), day la chi phi mang LON HON nhieu (N lan tai thay vi 1). `diff_toc`
o day CHUA lam dieu do — xem `server/scraper/http_fetcher.py` (`ETag`/
`Last-Modified` da co san tu Phase 9 nay) cho nen tang se dung khi tinh
nang "kiem tra lai chuong cu" duoc xay (Phase 5/8 tiep theo), nhung CHUA
noi day thanh mot vong lap tu dong o day — chua co bang chung ve tan suat
noi dung nguon THAT SU doi sau khi da quet xong de bien no thanh uu tien.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from server.scraper.contract import canonicalize_url
from server.scraper.dedupe import ScrapeState


@dataclass
class TocDiff:
    """Ket qua so sanh danh sach URL chuong TUOI (tu MOT lan
    `discover_series()` moi) voi `ScrapeState` da co — KHONG tai chuong
    nao, chi so sanh URL."""

    #: URL CHUA tung co ban ghi nao trong state — series co the co chuong
    #: moi.
    new_urls: List[str] = field(default_factory=list)
    #: URL TUNG co ban ghi "ok" nhung KHONG CON trong danh sach TUOI — nguon
    #: co the da xoa/doi ten/gop chuong. KHONG tu dong xoa gi ca (Phase 8:
    #: "khong bao gio am tham ghi de/xoa lich su") — chi la TIN HIEU cho
    #: operator xem xet.
    removed_urls: List[str] = field(default_factory=list)
    #: So chuong TUNG "ok" VA VAN CON trong danh sach TUOI — khong doi ve
    #: mat URL (co the noi dung van doi, xem "CO Y CHUA lam" o docstring
    #: module — dem nay KHONG kiem tra noi dung).
    unchanged_count: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.new_urls or self.removed_urls)


def diff_toc(state: ScrapeState, chapter_urls: List[str]) -> TocDiff:
    """So sanh `chapter_urls` (tu MOT lan `discover_series()`/
    `list_chapters()` moi — CHI trang muc luc, khong tai chuong nao) voi
    `state` da luu tu cac lan quet truoc — Phase 9: "fetch index/TOC only
    -> compare persisted inventory fingerprint -> determine
    NEW/REMOVED/UNCHANGED"."""
    canon_hien_tai = {canonicalize_url(u) for u in chapter_urls}
    # `state.get()` doi URL DA chuan hoa san (xem docstring
    # `ScrapeState.get` — khac `record_success`/`record_failure` tu chuan
    # hoa ben trong), nen PHAI goi `canonicalize_url` o day truoc — thieu
    # buoc nay se lam bien the URL (vd them tracking param) bi hieu nham
    # la chuong MOI du da co ban ghi qua mot bien the khac.
    new_urls = [u for u in chapter_urls if state.get(canonicalize_url(u)) is None]

    da_biet_ok = state.known_urls(status="ok")
    removed_urls = [u for u in da_biet_ok if canonicalize_url(u) not in canon_hien_tai]

    return TocDiff(
        new_urls=new_urls,
        removed_urls=removed_urls,
        unchanged_count=len(da_biet_ok) - len(removed_urls),
    )

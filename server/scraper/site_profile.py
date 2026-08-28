"""
`SiteProfile` — cau hinh domain DA HOC duoc tu `discovery.py` (Phase 2) va
DA duoc operator XAC NHAN, khac voi `site_registry.SiteConfig` (cau hinh
domain do KY SU tay xac minh, khong bao gio tu dong tao). Day la Phase 4
cua Story Harvester V3.

PHAN CAP uu tien khi giai quyet MOT url (xem
`server/scraper_ops_service.py::_adapter_for_url`):

    1. `site_registry.lookup()` — SiteConfig da xac minh boi ky su.
    2. `SiteProfileStore.get()` voi status VERIFIED/LEARNING — hoc tu
       discovery, da duoc operator xac nhan (khong con la de xuat tho).
    3. `discovery.UnknownSiteDiscoveryEngine` — mot lan kham pha MOI, CHI
       tra ve DE XUAT (khong tu dong ghi SiteProfile — operator phai goi
       ro rang `confirm_unknown_source()`, xem module do).

CO Y KHONG luu lich su day du cac phien ban pattern — chi giu pattern
HIEN TAI + `revision` (dem so lan doi). Mot log lich su day du la tinh nang
THEM (Phase 5 tu-chua Scrapling co the can no), chua co bang chung can den
o v1 nay — xem `AI_ROUTER.md` nguyen tac "khong xay truoc khi co bang
chung". `revision` da du de UI hien "cau hinh nay da doi N lan", va de
Phase 5 sau nay quyet dinh co ghi them lich su hay khong.

CO Y KHONG co truong cookie/secret/header nao — SiteProfile CHI la mo ta
CAU TRUC trang (pattern/fingerprint), khong phai thong tin xac thuc.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional

from server.scraper.contract import ScraperTier, domain_of
from server.scraper.discovery import DiscoveryProposal, PaginationStrategy

#: Rate limit MAC DINH (giay giua hai yeu cau CUNG mot domain) cho mot
#: SiteProfile moi hoc — CUNG gia tri mac dinh voi `HttpFetcher` (xem
#: `http_fetcher.DEFAULT_MIN_DELAY_SECONDS`), KHONG tu suy ra tu discovery
#: (domain chua duoc kiem chung co can cham hon hay khong).
DEFAULT_LEARNED_RATE_LIMIT_SECONDS = 2.0

#: Sau bao nhieu LOI LIEN TIEP thi mot profile VERIFIED tu chuyen sang
#: DEGRADED (can operator/ky su xem lai, KHONG con duoc dung am tham cho
#: cac dot quet moi) — xem `record_failure`.
CONSECUTIVE_FAILURE_THRESHOLD = 3


class ProfileStatus(str, Enum):
    #: Vua hoc tu discovery, DA duoc operator xac nhan, nhung CHUA co lan
    #: quet chuong thanh cong nao de chung minh pattern dung tren du lieu
    #: that (khac voi discovery's HIGH/MEDIUM — do la du doan TRUOC khi
    #: quet, con LEARNING la trang thai SAU khi operator xac nhan de xuat).
    LEARNING = "learning"
    #: Da co it nhat mot chuong quet thanh cong (qua quality gate) bang
    #: pattern nay — an toan de tu dong dung cho cac lan sau.
    VERIFIED = "verified"
    #: Vuot nguong loi lien tiep (`CONSECUTIVE_FAILURE_THRESHOLD`) — KHONG
    #: con duoc `_adapter_for_url` tu dong dung, can kham pha lai hoac ky
    #: su xem lai. Xem Phase 5 (tu-chua) cho huong xu ly sau nay.
    DEGRADED = "degraded"
    #: Operator/ky su tat thu cong — khong bao gio tu dong dung, du trang
    #: thai loi the nao.
    DISABLED = "disabled"


@dataclass
class SiteProfile:
    domain: str
    status: ProfileStatus = ProfileStatus.LEARNING
    revision: int = 1
    canonical_pattern: str = ""
    index_pattern: str = ""
    #: Regex ap len href tho tren trang muc luc — tuong duong
    #: `SiteConfig.chapter_href_pattern` nhung do MAY hoc, khong phai ky su
    #: xac minh tay.
    chapter_pattern: str = ""
    #: sha256 cua trang muc luc GAN NHAT da thay — dung cho Phase 9 (engine
    #: cap nhat gia tang) de phat hien muc luc co doi hay khong ma khong
    #: can so sanh tung chuong.
    toc_fingerprint: str = ""
    #: Mo ta ung vien vung noi dung (vd "div.chapter-content") tren trang
    #: chuong mau luc xac nhan — Phase 5 (tu-chua) so sanh ranh gioi MOI voi
    #: gia tri nay truoc khi chap nhan mot selector da doi.
    content_fingerprint: str = ""
    pagination_strategy: str = PaginationStrategy.NONE.value
    #: Regex trang-tiep-theo — CHI co gia tri khi `pagination_strategy` la
    #: `numbered_pages` (xem `discovery._detect_pagination`). Thieu truong
    #: nay, `_adapter_for_url` chi dua duoc `chapter_pattern` cho
    #: `GenericIndexAdapter` (khong co `next_page_href_pattern`) — mot
    #: nguon hoc duoc co phan trang se AM THAM chi quet TRANG DAU cua muc
    #: luc moi lan, khong bao gio thay chuong o cac trang sau — phat hien
    #: qua review doc lap (Codex).
    next_page_pattern: str = ""
    fetch_tier: str = ScraperTier.DIRECT_HTTP.name
    rate_limit_seconds: float = DEFAULT_LEARNED_RATE_LIMIT_SECONDS
    last_verified_at: str = ""
    last_success_at: str = ""
    consecutive_failures: int = 0
    success_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    #: P2 (overnight hardening) — dau van tay CAU TRUC (JSON cua dict tra
    #: ve boi `scrapling_relocation.save_verified_element`, KHONG PHAI
    #: HTML/noi dung tho — xem docstring module do) cua vung noi dung
    #: chuong TU LAN XAC NHAN GAN NHAT thanh cong. Rong ("") neu Scrapling
    #: khong san sang luc xac nhan, hoac chua tung xac nhan lan nao — day
    #: la truong hop AN TOAN MAC DINH, `confirm_unknown_source` phai luon
    #: kiem tra rong truoc khi thu dung.
    adaptive_fingerprint_json: str = ""

    @property
    def is_usable(self) -> bool:
        """Co duoc `_adapter_for_url` TU DONG dung cho dot quet moi hay
        khong — CHI hai trang thai an toan, khong bao gio DEGRADED/DISABLED."""
        return self.status in (ProfileStatus.LEARNING, ProfileStatus.VERIFIED)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def profile_from_proposal(proposal: DiscoveryProposal) -> SiteProfile:
    """Xay MOT `SiteProfile` moi (status LEARNING, revision 1) tu mot
    `DiscoveryProposal` DA duoc operator xac nhan — goi boi
    `confirm_unknown_source()` (xem `server/scraper_ops_service.py`), KHONG
    BAO GIO tu dong goi ham nay ngay sau `discover()` (do se bo qua buoc
    xac nhan cua operator, vi pham nguyen tac "MEDIUM can operator review"
    cua Phase 2).

    `domain` PHAI dung `domain_of()` (bo `www.`, vien thuong) — CUNG ham
    duoc `scraper_ops_service._adapter_for_url` dung de TRA CUU lai profile
    theo domain cua url operator dan vao. Truoc sua nay, ham nay tu tach
    domain rieng (KHONG bo `www.`), khien mot profile vua xac nhan xong tu
    mot url co "www." bi luu duoi khoa "www.example.com" nhung tra cuu lai
    (qua `_adapter_for_url`) voi khoa da bo "www." — "example.com" — KHONG
    BAO GIO tim thay chinh no, "hong" ngay sau khi xac nhan — phat hien qua
    review doc lap (Codex)."""
    return SiteProfile(
        domain=domain_of(proposal.canonical_url),
        status=ProfileStatus.LEARNING,
        revision=1,
        canonical_pattern=proposal.canonical_url,
        index_pattern=proposal.index_url,
        chapter_pattern=proposal.chapter_url_pattern or "",
        content_fingerprint=proposal.content_container_candidate or "",
        pagination_strategy=proposal.pagination_strategy.value,
        next_page_pattern=proposal.next_page_url_pattern or "",
        fetch_tier=proposal.fetch_tier.name,
    )


class MockSiteProfileStore:
    """Kho TRONG BO NHO — cung mau voi `MockScrapeRunStore`
    (`server/scraper/run_state.py`): khoa `RLock`, tao-hoac-cap-nhat theo
    KHOA TU NHIEN la `domain` (khong can dinh danh tach rieng nhu `run_id`
    — MOI domain chi co DUY NHAT mot profile dang hoat dong tai mot thoi
    diem, khong nhu ScrapeRun co the co nhieu dot cho cung mot series)."""

    def __init__(self, now_fn: Callable[[], str] = _now_utc_iso) -> None:
        self._lock = threading.RLock()
        self._now = now_fn
        self.profiles: Dict[str, SiteProfile] = {}

    def get(self, domain: str) -> Optional[SiteProfile]:
        return self.profiles.get(domain)

    def upsert(self, profile: SiteProfile) -> SiteProfile:
        """Ghi DE HOAN TOAN theo `domain` — dung khi confirm mot de xuat
        discovery MOI (co the ghi de mot profile DEGRADED cu bang mot lan
        kham pha lai, xem Phase 5)."""
        with self._lock:
            moc = self._now()
            hien_co = self.profiles.get(profile.domain)
            created_at = hien_co.created_at if hien_co else (profile.created_at or moc)
            moi = replace(profile, created_at=created_at, updated_at=moc)
            self.profiles[profile.domain] = moi
            return moi

    def save(self, domain: str, **fields: Any) -> SiteProfile:
        with self._lock:
            hien_tai = self.profiles.get(domain)
            if hien_tai is None:
                raise ValueError(f"Chưa có SiteProfile cho domain: {domain}")
            fields.setdefault("updated_at", self._now())
            moi = replace(hien_tai, **fields)
            self.profiles[domain] = moi
            return moi

    def record_success(self, domain: str) -> SiteProfile:
        """Goi sau MOI lan mot chuong cua domain nay qua duoc quality gate
        — dua profile LEARNING len VERIFIED tu dong sau lan thanh cong DAU
        TIEN (khong can operator xac nhan lan hai), reset chuoi loi lien
        tiep ve 0."""
        with self._lock:
            hien_tai = self.profiles.get(domain)
            if hien_tai is None:
                raise ValueError(f"Chưa có SiteProfile cho domain: {domain}")
            trang_thai_moi = (ProfileStatus.VERIFIED
                              if hien_tai.status == ProfileStatus.LEARNING
                              else hien_tai.status)
            return self.save(
                domain, status=trang_thai_moi, consecutive_failures=0,
                success_count=hien_tai.success_count + 1,
                last_success_at=self._now())

    def record_failure(self, domain: str) -> SiteProfile:
        """Goi sau MOI lan fetch/parse loi tren domain nay — tu chuyen sang
        DEGRADED khi vuot `CONSECUTIVE_FAILURE_THRESHOLD`, xem
        `ProfileStatus.DEGRADED`. DISABLED la ghi de THU CONG cua
        operator/ky su — KHONG BAO GIO bi ham nay tu doi trang thai (mot
        domain da tat khong duoc tu "song lai" thanh DEGRADED chi vi tiep
        tuc loi trong luc dang tat)."""
        with self._lock:
            hien_tai = self.profiles.get(domain)
            if hien_tai is None:
                raise ValueError(f"Chưa có SiteProfile cho domain: {domain}")
            loi_lien_tiep = hien_tai.consecutive_failures + 1
            if hien_tai.status == ProfileStatus.DISABLED:
                trang_thai_moi = ProfileStatus.DISABLED
            elif loi_lien_tiep >= CONSECUTIVE_FAILURE_THRESHOLD:
                trang_thai_moi = ProfileStatus.DEGRADED
            else:
                trang_thai_moi = hien_tai.status
            return self.save(domain, status=trang_thai_moi,
                             consecutive_failures=loi_lien_tiep)

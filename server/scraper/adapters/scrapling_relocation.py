"""
P2 (Story Harvester V3 overnight hardening) — adaptive candidate-finding
THAT SU qua Scrapling (`https://github.com/D4Vinci/Scrapling`, xac minh
truc tiep tren phien ban da cai, KHONG doan tu tri nho — xem
`docs/reports/` cho ghi chu dieu tra API neu can).

BE MAT API THAT SU (xac minh qua doc nguon `scrapling/parser.py`, phien
ban 0.4.15):

  - `Selector(html, url=..., adaptive=True, storage_args={"storage_file": ...})`
    PHAI bat `adaptive=True` luc khoi tao moi dung duoc `.save()`/`.relocate()`.
  - `.save(element, identifier)` / `.retrieve(identifier)`: luu/doc MOT
    "dau van tay" cau truc (tag/attributes/path-to-root/parent/siblings —
    KHONG luu toan bo noi dung trang, xem `_StorageTools.element_to_dict`
    trong scrapling/core/storage.py) vao kho (mac dinh SQLite, khoa theo
    domain+identifier).
  - `.relocate(fingerprint_dict, percentage=40, selector_type=False)`: quet
    LAI TOAN BO cay HTML hien tai, cham diem tuong dong CAU TRUC (KHONG
    phai noi dung/van ban) cho MOI phan tu, tra ve (các) phan tu co diem
    CAO NHAT neu >= percentage.

PHAT HIEN THAT (kiem chung bang thu nghiem truc tiep, xem lich su session
— KHONG phai suy doan): thuat toan cham diem cua `.relocate()` dua RAT
NANG vao boi canh TO TIEN/ANH EM (path-to-root, ten the cha, thuoc tinh
cha, danh sach anh em — 5-6/9 thanh phan diem) so voi danh tinh CUA CHINH
phan tu (tag/class/id — 3-4/9 thanh phan). Hau qua THAT: khi mot "wrapper"
moi duoc chen quanh phan tu muc tieu (hoac do sau thay doi), boi canh
anh em/to tien cua no thay doi HOAN TOAN, trong khi mot phan tu LANG
GIENG khong lien quan nhung KHONG bi dung cham (vd mot div sidebar) giu
NGUYEN boi canh cu — `.relocate()` co the tu tin chon NHAM phan tu lang
gieng do. Day la LY DO THAT (khong phai ly thuyet) khien buoc KIEM TRA
NOI DUNG (`validate_relocated_candidate`, tai su dung `self_healing.
validate_relocated_content`) LA BAT BUOC, khong phai hinh thuc — no la
lop duy nhat con lai phat hien "found=True nhung noi dung sai" trong cac
truong hop nay. Xem `docs/reports/` (P2) cho bang ket qua day du 9 kich
ban (A-I).

RANH GIOI ADAPTER (yeu cau cua nhiem vu): ba ham cong khai duoi day la
BE MAT DUY NHAT phan con lai cua Harvester duoc phep goi — khong noi nao
khac duoc `import scrapling` truc tiep ngoai module nay va
`scrapling_adapter.py` (Tier 1 danh sach chuong, khong lien quan module
nay).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

from server.scraper.self_healing import (
    RelocationConfidence, RelocationValidationResult, validate_relocated_content,
)

#: Ten dinh danh CO DINH dung khi luu/doc dau van tay vung noi dung chuong
#: — moi lan goi `save_verified_element`/`relocate_verified_element` dung
#: MOT file storage rieng, DUNG MOT LAN (xem docstring ham), nen khong can
#: phan biet nhieu dinh danh trong cung mot file.
_DINH_DANH_VUNG_NOI_DUNG = "content_container"


class ScraplingUnavailableError(RuntimeError):
    """`scrapling` chua duoc cai (hoac import that bai) trong moi truong
    dang chay — day la kha nang NANG TANG (Tier 1), KHONG PHAI phu thuoc
    cung: moi noi goi vao module nay PHAI bat loi nay va lui ve hanh vi Tier
    0 (xem `server/scraper/tier_escalation.py`), khong duoc de loi nay
    thoat thang ra ngoai lam sap toan bo yeu cau."""


@lru_cache(maxsize=1)
def is_scrapling_available() -> bool:
    """Tham do THAT (khong gia dinh) — ket qua duoc nho lai (import mot
    goi nang khong nen thu lai moi lan goi), nhung day la mot tien trinh
    Python dai han (server), khong phai script ngan han, nen nho lai
    trong suot vong doi tien trinh la an toan: `scrapling` khong the tu
    nhien bien mat/xuat hien giua chung khi server dang chay."""
    try:
        import scrapling  # noqa: F401
    except ImportError:
        return False
    return True


def _tai_lop_selector():
    """Nhap `Selector` CHI khi thuc su can — KHONG BAO GIO o muc module,
    de import module nay (vd tu `scraper_ops_service.py`) khong bao gio
    that bai chi vi `scrapling` chua cai (yeu cau "khong crash khi khoi
    dong" cua nhiem vu)."""
    if not is_scrapling_available():
        raise ScraplingUnavailableError(
            "Gói `scrapling` chưa được cài trong môi trường này — đây là "
            "khả năng nâng tầng (Tier 1) tùy chọn, không phải phụ thuộc "
            "cứng. Bỏ qua bước định vị lại thích ứng, lùi về hành vi Tier 0.")
    from scrapling import Selector
    return Selector


@dataclass
class RelocationCandidates:
    """Ket qua THO tu `.relocate()` — CHUA qua kiem tra noi dung. `count >
    1` la tin hieu MO HO (nhieu vi tri co diem cau truc NGANG NHAU, vd kich
    ban I "nhieu vung chua van ban hop ly") — `validate_relocated_candidate`
    PHAI ha tran confidence xuong MEDIUM trong truong hop nay, KHONG BAO
    GIO tu dong chon phan tu dau tien coi la HIGH."""
    outer_html_candidates: List[str] = field(default_factory=list)
    css_selector_candidates: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.outer_html_candidates)

    @property
    def is_ambiguous(self) -> bool:
        return self.count > 1

    @property
    def found(self) -> bool:
        return self.count > 0


def save_verified_element(
        html: str, css_selector: str, *, url: str = "",
) -> Optional[Dict[str, Any]]:
    """Buoc 1 cua luong (yeu cau nhiem vu): "known-good chapter element ->
    save/fingerprint". `html`/`css_selector` la mot lan quet DA THANH CONG
    (vd `SiteProfile.content_fingerprint` da xac minh) — tra ve dau van tay
    cau truc (dict JSON-hoa duoc, KHONG chua toan bo noi dung trang, xem
    docstring module) de kho ben vung (SiteProfile) luu lai cho lan sau,
    hoac `None` neu `css_selector` khong khop phan tu nao tren `html` nay
    (khong the luu dau van tay cua thu khong ton tai).

    CO Y dung MOT file storage TAM THOI, DUNG MOT LAN roi bo (khong giu
    ket noi SQLite song song giua cac request HTTP) — dau van tay THAT SU
    duoc luu ben vung la dict tra ve, do CALLER (server/scraper_ops_service.py)
    JSON-hoa vao truong `SiteProfile.adaptive_fingerprint_json`, KHONG
    phai o day. Tranh duoc toan bo van de quan ly vong doi file SQLite
    theo domain giua cac request (server co the chay nhieu worker/khong
    bao ton state giua request, xem docstring `scraper_ops_service.py`).

    PHAT HIEN THAT (loi that, khong phai gia thuyet): `SQLiteStorageSystem`
    cua Scrapling la mot singleton `lru_cache(1)` theo (storage_file, url)
    — no GIU CHAT mot tham chieu manh toi ket noi SQLite, nen `__del__`
    KHONG chay khi `page` ra khoi scope (khong co gi kich hoat garbage
    collect ngay lap tuc). Tren Windows, xoa thu muc chua mot file dang mo
    (`tempfile.TemporaryDirectory().__exit__`) nem `PermissionError` —
    phat hien qua chay THAT ham nay (khong phai doc code suong).

    DA THU (VA LOAI BO) hai cach tiep can khac truoc khi ve ban nay — ghi
    lai vi day la mot vi du that ve hanh vi phu thuoc nen tang can do
    THAT, khong doan — cach tiep can (3) duoi day duoc XAC MINH BANG DO
    TRUC TIEP (khong phai suy luan) la KHONG hoat dong nhu ky vong:

    (1) KHONG goi close() gi ca, chi dua vao `shutil.rmtree(...,
    ignore_errors=True)`, voi gia dinh "ro ri se duoc don dep boi lan
    cache-eviction ke tiep cua chinh Scrapling". SAI — kiem chung truc
    tiep (review doc lap, Codex) cho thay tren Windows thu muc tam bi ro
    ri VINH VIEN: `shutil.rmtree` that bai (file dang mo) roi KHONG BAO
    GIO duoc thu lai — thu muc da mat, khong ai quay lai xoa no nua.

    (2) Goi `page._storage.close()` truc tiep — day cache size-1 cua
    Scrapling van giu tham chieu instance nay cho den lan goi KE TIEP,
    khi do bi loai khoi cache, `__del__` cua no TU GOI `close()` LAN NUA
    tren mot ket noi DA dong, nem `sqlite3.ProgrammingError` (Python nuot
    thanh `PytestUnraisableExceptionWarning`, gay nhieu output test).

    (3) [DA THU, KHONG HIEU QUA — do THAT truoc khi ket luan] Sau khi doc
    xong: `del page`, goi `SQLiteStorageSystem.cache_clear()` (API cong
    khai cua `functools.lru_cache`), roi `del storage`, ky vong dem-tham-
    chieu CPython kich hoat `__del__` dong ket noi that truoc khi
    `shutil.rmtree` chay. DO TRUC TIEP (`sys.getrefcount`) cho thay VAN
    con MOT tham chieu khac ngoai du kien SAU CA hai buoc do — nguyen
    nhan: `StorageSystemMixin._get_base_url` (phuong thuc cha cua
    `SQLiteStorageSystem`) TU NO cung la `@lru_cache(64, typed=True)`
    tren PHUONG THUC INSTANCE (`self` la mot phan cua khoa cache) — mot
    lru_cache THU HAI, DOC LAP, giu instance song them ngoai y muon. Xoa
    ca hai cache noi bo cua mot thu vien ngoai (khong chi mot) de kiem
    soat vong doi mot doi tuong la qua sau vao chi tiet trien khai rieng,
    de vo khi Scrapling doi phien ban — TU BO huong nay.

    KET LUAN CUOI CUNG (trung thuc, khong lac quan): giu (1) — mot ro ri
    THAT, NHO (mot file SQLite vai chuc KB), rat co the TON TAI VINH VIEN
    tren dia cho den khi HDH/nguoi dung don dep thu muc temp thu cong,
    KHONG tu dong duoc don boi tien trinh. CHAP NHAN duoc vi ham nay CHI
    duoc goi tu thao tac operator xac nhan nguon (hiem — moi lan operator
    xac nhan/khoi phuc MOT domain, khong phai duong nong moi chuong), quy
    mo ro ri (KB moi lan goi, khong phai MB) khong dang ke so voi rui ro
    ket hop qua sau vao API noi bo khong on dinh cua mot thu vien ngoai."""
    Selector = _tai_lop_selector()
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    try:
        storage_file = os.path.join(tmp, "fingerprint.db")
        page = Selector(html, url=url, adaptive=True,
                         storage_args={"storage_file": storage_file})
        found = page.css(css_selector, identifier=_DINH_DANH_VUNG_NOI_DUNG,
                          auto_save=True)
        return page.retrieve(_DINH_DANH_VUNG_NOI_DUNG) if found else None
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def relocate_verified_element(
        html: str, fingerprint: Dict[str, Any], *, url: str = "",
        percentage: int = 40,
) -> RelocationCandidates:
    """Buoc 2 (yeu cau nhiem vu): "DOM changes -> original selector fails ->
    Scrapling locates candidate automatically". `fingerprint` la dict tra
    ve tu `save_verified_element` (KHONG phai selector CU — day chinh la
    diem khac biet voi Tier 0: chung ta khong "thu lai selector cu", ma
    yeu cau Scrapling QUET LAI TOAN BO CAY HTML MOI de tim phan tu giong
    NHAT ve mat cau truc, hoan toan KHONG duoc cung cap selector thay the
    thu cong nao — dung yeu cau "Do not manually feed the replacement
    selector to the validation layer")."""
    Selector = _tai_lop_selector()
    page = Selector(html, url=url, adaptive=True)
    candidates = page.relocate(fingerprint, percentage=percentage, selector_type=True)
    outer_html: List[str] = []
    css_hints: List[str] = []
    for c in candidates:
        # `_root` la thuoc tinh CONG KHAI VE QUY UOC (mot gach duoi, khong
        # bi bien doi ten) cua chinh `Selector` — ban than `.relocate()`
        # noi bo cung dung `self._root` (xem scrapling/parser.py) de lay
        # phan tu lxml tho, day KHONG phai truy cap noi bo tu y doan.
        from lxml import html as lxml_html
        outer_html.append(lxml_html.tostring(c._root, encoding="unicode"))
        try:
            css_hints.append(c.generate_css_selector)
        except Exception:
            css_hints.append("")
    return RelocationCandidates(outer_html_candidates=outer_html, css_selector_candidates=css_hints)


def validate_relocated_candidate(
        candidates: RelocationCandidates, *, chapter_title: Optional[str] = None,
        previous_chapter_content_hash: Optional[str] = None,
) -> RelocationValidationResult:
    """Buoc 3 (yeu cau nhiem vu): "Scrapling locates candidate -> Harvester
    validates candidate". "Relocation alone is NOT success" — TAI SU DUNG
    NGUYEN VEN `self_healing.validate_relocated_content` (do da co day du
    kiem tra do dai/mat do doan van/tieu de, trung chuong truoc, trang dang
    nhap-loi — khong viet lai o day), CHI THEM MOT dieu kien RIENG cua
    buoc adaptive relocation: mo ho (>1 ung vien diem ngang nhau) khong
    duoc phep tu HIGH — ha xuong MEDIUM du noi dung ung vien dau tien co
    trong nhu the nao."""
    if not candidates.found:
        return RelocationValidationResult(
            confidence=RelocationConfidence.LOW,
            evidence=["Scrapling không định vị lại được phần tử nào đạt "
                      "ngưỡng tương đồng cấu trúc — từ chối an toàn, "
                      "KHÔNG ghi đè SiteProfile."],
        )
    ket_qua = validate_relocated_content(
        candidates.outer_html_candidates[0], chapter_title=chapter_title,
        previous_chapter_content_hash=previous_chapter_content_hash)
    if candidates.is_ambiguous and ket_qua.confidence == RelocationConfidence.HIGH:
        ket_qua = RelocationValidationResult(
            confidence=RelocationConfidence.MEDIUM,
            evidence=ket_qua.evidence + [
                f"Scrapling tìm thấy {candidates.count} vị trí có điểm "
                "tương đồng cấu trúc NGANG NHAU (mơ hồ) — dù nội dung ứng "
                "viên đầu tiên trông hợp lệ, không tự động nâng lên HIGH "
                "khi có nhiều vị trí khả dĩ. Cần operator xem lại."],
            clean_text=ket_qua.clean_text,
            is_duplicate_of_previous_chapter=ket_qua.is_duplicate_of_previous_chapter,
            looks_like_login_or_error_page=ket_qua.looks_like_login_or_error_page,
        )
    return ket_qua


@dataclass
class AdaptiveRelocationOutcome:
    confidence: RelocationConfidence
    evidence: List[str] = field(default_factory=list)
    clean_text: str = ""
    is_ambiguous: bool = False
    #: Selector CSS moi (do CHINH Scrapling sinh ra tu phan tu dinh vi lai
    #: duoc, vd "#content-main" — xem `generate_css_selector`), de ghi vao
    #: `SiteProfile.content_fingerprint` NEU duoc chap nhan. `None` neu
    #: relocation khong chay/khong tim thay gi.
    candidate_selector: Optional[str] = None
    #: `False` neu Scrapling khong san sang/khong co dau van tay cu de thu
    #: — phan biet voi "co thu nhung that bai" (confidence LOW nhung
    #: relocation_attempted=True).
    relocation_attempted: bool = False


def attempt_adaptive_relocation(
        fingerprint_json: str, new_html: str, *, url: str = "",
        chapter_title: Optional[str] = None,
        previous_chapter_content_hash: Optional[str] = None,
        percentage: int = 40,
) -> AdaptiveRelocationOutcome:
    """Dieu phoi day du ca 3 buoc — diem goi vao DUY NHAT ma
    `scraper_ops_service.py` can dung. AN TOAN goi vo dieu kien: neu
    `scrapling` khong san sang HOAC `fingerprint_json` rong/hong, tra ve
    outcome LOW voi `relocation_attempted=False` THAY VI nem ngoai le —
    caller LUON lui ve hanh vi Tier 0 hien co ma khong can tu bat
    `ScraplingUnavailableError` rieng (yeu cau "no startup crash... return
    a clear capability state" cua nhiem vu)."""
    if not fingerprint_json or not is_scrapling_available():
        return AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.LOW,
            evidence=["Không có dấu vân tay thích ứng đã lưu, hoặc "
                      "Scrapling không khả dụng trong môi trường này — bỏ "
                      "qua bước định vị lại thích ứng."],
            relocation_attempted=False,
        )
    try:
        fingerprint = json.loads(fingerprint_json)
    except (ValueError, TypeError):
        return AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.LOW,
            evidence=["Dấu vân tay thích ứng đã lưu bị hỏng (không parse "
                      "được JSON) — bỏ qua, không thử định vị lại."],
            relocation_attempted=False,
        )
    # Phat hien qua review doc lap (Codex): parse JSON thanh cong nhung
    # SAI HINH DANG (vd mot list/so/chuoi thay vi dict, hoac dict thieu
    # khoa "tag"/"text"/"attributes"/"path" ma `__calculate_similarity_score`
    # cua Scrapling truy cap KHONG DIEU KIEN) truoc day nem KeyError/TypeError
    # THOAT THANG ra ngoai `confirm_unknown_source`, vi pham dung yeu cau
    # "AN TOAN goi vo dieu kien" o docstring ham nay — kiem tra hinh dang
    # RO RANG o day, VA boc ca loi goi ben duoi trong except Exception
    # (khong chi ScraplingUnavailableError) lam luoi an toan thu hai.
    if (not isinstance(fingerprint, dict)
            or not {"tag", "text", "attributes", "path"} <= fingerprint.keys()):
        return AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.LOW,
            evidence=["Dấu vân tay thích ứng đã lưu sai hình dạng mong đợi "
                      "(không phải dict cấu trúc hợp lệ) — bỏ qua, không "
                      "thử định vị lại."],
            relocation_attempted=False,
        )

    try:
        candidates = relocate_verified_element(
            new_html, fingerprint, url=url, percentage=percentage)
    except Exception as exc:
        return AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.LOW,
            evidence=[f"Định vị lại thích ứng thất bại với lỗi không mong "
                      f"đợi ({exc}) — từ chối an toàn, không thử suy đoán "
                      f"thêm."],
            relocation_attempted=False,
        )

    ket_qua = validate_relocated_candidate(
        candidates, chapter_title=chapter_title,
        previous_chapter_content_hash=previous_chapter_content_hash)
    selector = candidates.css_selector_candidates[0] if candidates.found else None
    return AdaptiveRelocationOutcome(
        confidence=ket_qua.confidence, evidence=ket_qua.evidence,
        clean_text=ket_qua.clean_text, is_ambiguous=candidates.is_ambiguous,
        candidate_selector=selector, relocation_attempted=True,
    )

"""Máy trạng thái vòng đời harvest — Story Harvester V4, Phase C.

VÌ SAO LÀ MỘT TẦNG RIÊNG, KHÔNG PHẢI ĐỔI `ScrapeItemStatus`:
`scrape_run_items.status` trên sản xuất là một enum Appwrite **đã cấp phát**
với đúng bốn giá trị (`pending`/`review_ready`/`failed`/`skipped`). Thêm giá
trị vào enum đó là một thay đổi schema sản xuất. Vòng đời chi tiết mà một
worker cần (đang tải? đã phân tích? đang chờ thử lại?) vì thế sống **ở trên**
trạng thái được lưu, và `persisted_status()` chiếu nó xuống bốn giá trị kia.

Hệ quả có chủ đích: trạng thái vòng đời là **của một lượt thực thi**, còn
trạng thái được lưu là **sự thật bền vững**. Một tiến trình chết giữa chừng
làm mất trạng thái vòng đời — và đúng như vậy: khi khởi động lại, mọi mục
`pending` quay về `DISCOVERED` và được làm lại từ đầu. Đó là lý do mọi bước
phải là **at-least-once an toàn**.

TÍNH BỀN VỮNG LÀ Ở `content_hash`, KHÔNG PHẢI Ở TRẠNG THÁI:
thi hành có thể chạy nhiều lần (worker trùng, khởi động lại, thử lại), nhưng
việc GHI phải là **exactly-once về mặt logic**. Điều đó không đến từ một khoá,
mà từ danh tính tất định: `item_id_for(run_id, fingerprint)` cho ra cùng một
`$id` Appwrite, nên lần ghi thứ hai là một `POST` trùng `documentId` → 409 →
"đã có". Xem `run_state.item_id_for` và `dedupe.ScrapeState`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, FrozenSet, Optional

from server.scraper.run_state import ScrapeItemStatus


class HarvestState(str, Enum):
    """Vòng đời MỘT mục trong một lượt thực thi."""

    DISCOVERED = "discovered"
    FETCHING = "fetching"
    PARSED = "parsed"
    NORMALIZED = "normalized"
    CHANGE_CLASSIFIED = "change_classified"
    PERSIST_PENDING = "persist_pending"
    PERSISTED = "persisted"
    COMPLETED = "completed"
    #: Da phan loai la KHONG DOI — xong, nhung KHONG ghi gi moi. Tach khoi
    #: `COMPLETED` vi phep chieu khac han: mot chuong khong doi KHONG duoc
    #: vao hang doi duyet (`review_ready`), o do khong co gi de duyet.
    COMPLETED_UNCHANGED = "completed_unchanged"

    #: Có thể thử lại — mạng chập chờn, 5xx, 429.
    FAILED_TRANSIENT = "failed_transient"
    #: KHÔNG thử lại — 404/410, robots.txt từ chối, vượt trần số lần thử.
    FAILED_PERMANENT = "failed_permanent"
    RETRY_WAIT = "retry_wait"
    CANCELLED = "cancelled"


#: Trạng thái KẾT — không đi tiếp được nữa.
TERMINAL: FrozenSet[HarvestState] = frozenset({
    HarvestState.COMPLETED,
    HarvestState.COMPLETED_UNCHANGED,
    HarvestState.FAILED_PERMANENT,
    HarvestState.CANCELLED,
})


#: Chuyển tiếp HỢP LỆ. Bảng trắng, không phải bảng đen: một cặp không có
#: trong bảng là KHÔNG hợp lệ. Fail closed — thêm một trạng thái mới mà quên
#: khai chuyển tiếp sẽ hỏng to ngay, thay vì âm thầm cho phép mọi thứ.
ALLOWED: Dict[HarvestState, FrozenSet[HarvestState]] = {
    HarvestState.DISCOVERED: frozenset({
        HarvestState.FETCHING, HarvestState.CANCELLED,
        HarvestState.CHANGE_CLASSIFIED, HarvestState.FAILED_PERMANENT,
    }),
    HarvestState.FETCHING: frozenset({
        HarvestState.PARSED, HarvestState.FAILED_TRANSIENT,
        HarvestState.FAILED_PERMANENT, HarvestState.CANCELLED,
    }),
    HarvestState.PARSED: frozenset({
        HarvestState.NORMALIZED, HarvestState.FAILED_TRANSIENT,
        HarvestState.FAILED_PERMANENT, HarvestState.CANCELLED,
    }),
    HarvestState.NORMALIZED: frozenset({
        HarvestState.CHANGE_CLASSIFIED, HarvestState.FAILED_TRANSIENT,
        # `FAILED_PERMANENT` o day tung BI THIEU: mot loi PARSE/QUALITY tai
        # buoc nay lam `fail()` nem `InvalidTransition` va muc bi KET. Neu ra
        # qua review doc lap (Codex) va da tai hien duoc.
        HarvestState.FAILED_PERMANENT, HarvestState.CANCELLED,
    }),
    HarvestState.CHANGE_CLASSIFIED: frozenset({
        HarvestState.PERSIST_PENDING,
        HarvestState.COMPLETED_UNCHANGED,
        # Bo phan loai cung co the hong — truoc day khong co duong loi nao ra
        # khoi day, nen mot loi o buoc nay lam ket ca muc.
        HarvestState.FAILED_TRANSIENT, HarvestState.FAILED_PERMANENT,
        HarvestState.CANCELLED,
    }),
    HarvestState.PERSIST_PENDING: frozenset({
        HarvestState.PERSISTED, HarvestState.FAILED_TRANSIENT,
        HarvestState.FAILED_PERMANENT, HarvestState.CANCELLED,
    }),
    HarvestState.PERSISTED: frozenset({HarvestState.COMPLETED}),
    HarvestState.FAILED_TRANSIENT: frozenset({
        HarvestState.RETRY_WAIT, HarvestState.FAILED_PERMANENT,
        HarvestState.CANCELLED,
    }),
    HarvestState.RETRY_WAIT: frozenset({
        HarvestState.FETCHING, HarvestState.CANCELLED,
        HarvestState.FAILED_PERMANENT,
    }),
    HarvestState.COMPLETED: frozenset(),
    HarvestState.COMPLETED_UNCHANGED: frozenset(),
    HarvestState.FAILED_PERMANENT: frozenset(),
    HarvestState.CANCELLED: frozenset(),
}

#: Trang thai loi CHI duoc vao qua `fail()`, khong qua `to()`.
#:
#: VI SAO: `to()` khong tang `attempts` va khong doc `ErrorCategory`. Truoc
#: ban sua nay, chuoi FETCHING -> FAILED_TRANSIENT -> RETRY_WAIT -> FETCHING
#: lap duoc VO HAN voi `attempts` dung yen o 0 — tran so lan thu bi vo hieu
#: hoan toan. Da tai hien: 50 vong, attempts=0. Neu ra qua review doc lap.
_CHI_QUA_FAIL: FrozenSet[HarvestState] = frozenset({
    HarvestState.FAILED_TRANSIENT, HarvestState.FAILED_PERMANENT,
})


class InvalidTransition(RuntimeError):
    """Chuyển tiếp không hợp lệ. Fail closed — không bao giờ âm thầm cho qua."""


class ErrorCategory(str, Enum):
    """Phân loại lỗi MÁY ĐỌC ĐƯỢC, tách khỏi chẩn đoán cho người đọc.

    Tách ra vì hai thứ này phục vụ hai mục đích khác nhau: cái này dùng để
    đếm/cảnh báo/quyết định có thử lại, cái kia để người đọc hiểu. Nhét cả hai
    vào một chuỗi tự do làm việc đếm phải khớp chuỗi — và mọi lần đổi câu chữ
    lại lặng lẽ làm hỏng thống kê.
    """

    NONE = "none"
    NETWORK = "network"
    HTTP_SERVER = "http_server"        # 5xx
    HTTP_RATE_LIMIT = "http_rate_limit"  # 429
    HTTP_NOT_FOUND = "http_not_found"    # 404/410/451
    ROBOTS_DENIED = "robots_denied"
    PARSE = "parse"
    QUALITY = "quality"
    PERSISTENCE = "persistence"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


#: Loại lỗi ĐƯỢC PHÉP thử lại. Mọi loại khác là vĩnh viễn.
RETRYABLE: FrozenSet[ErrorCategory] = frozenset({
    ErrorCategory.NETWORK,
    ErrorCategory.HTTP_SERVER,
    ErrorCategory.HTTP_RATE_LIMIT,
    ErrorCategory.PERSISTENCE,
})

#: Trần độ dài chẩn đoán. Nội dung trang là DỮ LIỆU KHÔNG ĐÁNG TIN và không
#: được phình vô hạn vào một bản ghi vận hành.
_TRAN_CHAN_DOAN = 300


def sanitize_diagnostic(text: str) -> str:
    """Làm sạch chẩn đoán trước khi nó thành bản ghi vận hành.

    Bỏ ký tự không in được (chặn log injection bằng xuống dòng giả) và cắt
    ngắn. KHÔNG dùng để lọc bí mật — bí mật không được đi vào đây ngay từ đầu;
    đây là lưới cuối, không phải lưới duy nhất.
    """
    # Cat TRUOC khi loc. Loc ca chuoi roi moi cat se duyet toan bo dau vao:
    # mot thong bao loi mang theo than phan hoi vai MB gay mot dot CPU/bo nho
    # vo ich. Nhan 4 de con du cho sau khi bo ky tu khong in duoc.
    raw = str(text or "")[:_TRAN_CHAN_DOAN * 4]
    return "".join(c for c in raw if c.isprintable())[:_TRAN_CHAN_DOAN]


#: Chiếu vòng đời xuống bốn giá trị enum ĐÃ CẤP PHÁT trên sản xuất.
#: Không đổi schema — xem docstring module.
_CHIEU: Dict[HarvestState, ScrapeItemStatus] = {
    HarvestState.DISCOVERED: ScrapeItemStatus.PENDING,
    HarvestState.FETCHING: ScrapeItemStatus.PENDING,
    HarvestState.PARSED: ScrapeItemStatus.PENDING,
    HarvestState.NORMALIZED: ScrapeItemStatus.PENDING,
    HarvestState.CHANGE_CLASSIFIED: ScrapeItemStatus.PENDING,
    HarvestState.PERSIST_PENDING: ScrapeItemStatus.PENDING,
    HarvestState.RETRY_WAIT: ScrapeItemStatus.PENDING,
    HarvestState.FAILED_TRANSIENT: ScrapeItemStatus.PENDING,
    HarvestState.PERSISTED: ScrapeItemStatus.REVIEW_READY,
    HarvestState.COMPLETED: ScrapeItemStatus.REVIEW_READY,
    #: KHONG phai `review_ready`: khong ghi gi moi thi khong co gi de duyet.
    HarvestState.COMPLETED_UNCHANGED: ScrapeItemStatus.SKIPPED,
    HarvestState.FAILED_PERMANENT: ScrapeItemStatus.FAILED,
    HarvestState.CANCELLED: ScrapeItemStatus.SKIPPED,
}


def persisted_status(state: HarvestState) -> ScrapeItemStatus:
    """Giá trị được LƯU tương ứng với một trạng thái vòng đời.

    `FAILED_TRANSIENT` chiếu về `PENDING`, **không** phải `FAILED`: một lỗi
    còn thử lại được mà lưu thành `failed` sẽ khiến một lần khởi động lại bỏ
    qua nó vĩnh viễn. Chỉ `FAILED_PERMANENT` mới là `failed`.
    """
    try:
        return _CHIEU[state]
    except KeyError:                      # pragma: no cover - bat loi lap trinh
        raise InvalidTransition(
            f"trạng thái {state!r} chưa khai trong bảng chiếu") from None


def can_transition(cu: HarvestState, moi: HarvestState) -> bool:
    if cu == moi:
        # Ghi LAI cung trang thai la khong-thao-tac hop le. Day chinh la dieu
        # lam cho viec ghi chuyen tiep IDEMPOTENT: mot worker bi thu lai sau
        # khi da ghi thanh cong khong duoc no.
        return True
    return moi in ALLOWED.get(cu, frozenset())


@dataclass(frozen=True)
class ItemProgress:
    """Tiến trình vòng đời của MỘT mục. Bất biến — mỗi chuyển tiếp ra một bản mới."""

    item_id: str
    state: HarvestState = HarvestState.DISCOVERED
    attempts: int = 0
    max_attempts: int = 3
    error_category: ErrorCategory = ErrorCategory.NONE
    diagnostic: str = ""

    def __post_init__(self) -> None:
        """Bất biến của chính đối tượng.

        Không có chỗ này, `ItemProgress(attempts=99, max_attempts=0)` dựng
        được — và trần số lần thử trở thành vô nghĩa ngay từ lúc khởi tạo.
        """
        if self.max_attempts < 1:
            raise ValueError(f"{self.item_id}: max_attempts phải >= 1")
        if self.attempts < 0:
            raise ValueError(f"{self.item_id}: attempts không được âm")
        if self.attempts > self.max_attempts:
            raise ValueError(
                f"{self.item_id}: attempts={self.attempts} vượt "
                f"max_attempts={self.max_attempts}")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def persisted(self) -> ScrapeItemStatus:
        return persisted_status(self.state)

    def to(self, moi: HarvestState, *,
           category: Optional[ErrorCategory] = None,
           diagnostic: str = "") -> "ItemProgress":
        """Chuyển tiếp, hoặc ném `InvalidTransition`.

        KHÔNG vào được trạng thái lỗi qua đây — dùng `fail()`. Lý do ở
        `_CHI_QUA_FAIL`: `to()` không tăng `attempts`, nên cho phép nó đặt
        `FAILED_TRANSIENT` mở ra một vòng thử lại vô hạn.

        Ghi lại CÙNG trạng thái là không-thao-tác (idempotent).
        """
        if moi in _CHI_QUA_FAIL:
            raise InvalidTransition(
                f"{self.item_id}: phải dùng `fail()` để vào {moi.value} — "
                f"`to()` không đếm số lần thử, và đi đường đó sẽ vô hiệu hoá "
                f"trần thử lại.")
        if not can_transition(self.state, moi):
            raise InvalidTransition(
                f"{self.item_id}: {self.state.value} -> {moi.value} không hợp lệ; "
                f"cho phép: {sorted(s.value for s in ALLOWED.get(self.state, ()))}")
        if moi == self.state:
            # Ghi lai cung trang thai la khong-thao-tac THUAN TUY. Truoc day
            # no van cho sua `category`/`diagnostic`, ke ca tren mot trang
            # thai KET — nghia la mot bao loi den muon van dan duoc metadata
            # vao mot muc da xong. Neu ra qua review doc lap.
            return self
        return replace(
            self, state=moi,
            error_category=category if category is not None else self.error_category,
            diagnostic=sanitize_diagnostic(diagnostic) if diagnostic else self.diagnostic,
        )

    def fail(self, category: ErrorCategory, diagnostic: str = "") -> "ItemProgress":
        """Ghi một lần hỏng và tự quyết định còn thử lại được hay không.

        Đây là lối DUY NHẤT vào hai trạng thái lỗi, nên nó cũng là nơi duy
        nhất `attempts` tăng — trần thử lại vì thế không thể bị đi vòng.
        """
        if self.is_terminal:
            raise InvalidTransition(
                f"{self.item_id}: không thể báo hỏng từ {self.state.value} "
                f"(đã kết) — một báo lỗi đến muộn không được lật ngược kết quả.")
        lan = self.attempts + 1
        con_thu = category in RETRYABLE and lan < self.max_attempts
        dich = HarvestState.FAILED_TRANSIENT if con_thu else HarvestState.FAILED_PERMANENT
        if dich not in ALLOWED.get(self.state, frozenset()) and dich != self.state:
            raise InvalidTransition(
                f"{self.item_id}: không thể báo hỏng từ {self.state.value}")
        return replace(
            self, state=dich, attempts=lan, error_category=category,
            diagnostic=sanitize_diagnostic(diagnostic))

    def schedule_retry(self) -> "ItemProgress":
        if self.state is not HarvestState.FAILED_TRANSIENT:
            raise InvalidTransition(
                f"{self.item_id}: chỉ xếp thử lại được từ failed_transient, "
                f"đang ở {self.state.value}")
        if self.attempts >= self.max_attempts:
            return replace(self, state=HarvestState.FAILED_PERMANENT)
        return replace(self, state=HarvestState.RETRY_WAIT)

    def cancel(self) -> "ItemProgress":
        """Huỷ. KHÔNG bao giờ hạ cấp một kết quả đã ghi.

        `PERSISTED` nghĩa là nội dung ĐÃ nằm trong kho. Huỷ nó xuống
        `CANCELLED` sẽ chiếu `review_ready` thành `skipped` và giấu mất một
        chương có thật khỏi hàng đợi duyệt — mất dữ liệu nhìn từ người vận
        hành. Nên từ `PERSISTED`, huỷ = hoàn tất. Nêu ra qua review độc lập.
        """
        if self.is_terminal:
            return self
        if self.state is HarvestState.PERSISTED:
            return replace(self, state=HarvestState.COMPLETED)
        return replace(self, state=HarvestState.CANCELLED,
                       error_category=ErrorCategory.CANCELLED)

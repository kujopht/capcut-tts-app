"""
Nhap chuong HANG LOAT — tang domain (thuan Python, khong FastAPI, khong mang).

VI SAO TON TAI: tao chuong hien nay la MOT chuong moi request
(`POST /api/chapters`). Mot truyen 50-500 chuong la 50-500 lan bam nut, va
khong co gi ghi lai "dot nhap nay dang o dau" — dong tab la mat dau vet.

DAY KHONG PHAI mot he thong nap lieu THU HAI. Toan bo viec tao chuong va tao
job TTS van di qua DUNG hai duong da co (`POST /api/chapters` /
`POST /api/jobs`, xem `server/bulk_import_service.py`). Thu duy nhat moi o day
la MOT trang thai chua tung co: "mot dot nhap dang chay" — mot `ImportBatch`
va cac `ImportItem` cua no.

BA TINH CHAT phai dung, va ca ba deu dua vao DINH DANH TAT DINH chu khong dua
vao khoa/lease:

  1. Gui lai CUNG mot dau vao => CUNG mot `batch_id` (bam tu
     owner+novel+noi dung), nen "nhap lai lan hai" la TIEP TUC, khong phai tao
     lo moi. Xem `batch_fingerprint` / `batch_id_from_fingerprint`.

  2. Moi muc co `item_id` TAT DINH (`{batch_id}-{index:04d}`), nen ghi danh
     sach muc co the bi cat giua chung roi ghi lai — hang da co se bi tu choi
     (409) va bo qua, khong sinh ban trung.

  3. Moi muc co `chapter_id` TAT DINH (`chapter_id_for`), nen "tao chuong roi
     chet TRUOC KHI kip ghi id vao muc" KHONG sinh chuong trung: lan chay sau
     tao lai dung id do va Appwrite tra 409 (`create_chapter_once` doc ra ban
     da co). Day la khac biet quan trong nhat so voi cach lam
     "kiem tra chapter_id co null hay khong" — cach do de ho mot khe ho that.

Nho ba dieu tren, tang dieu phoi (`BulkImportService`) KHONG can khoa, KHONG
can lease, va an toan khi chay dong thoi nhieu ban. Do la co y.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.domain import now_iso


class BulkImportError(Exception):
    """Loi nghiep vu cua nhap hang loat — thong diep AN TOAN de hien cho chu."""


class BulkImportFormatError(BulkImportError):
    """Dau vao khong dung dinh dang / vuot han muc. Tra 400."""


class BulkImportStateError(BulkImportError):
    """Thao tac khong hop voi trang thai hien tai cua lo. Tra 409."""


class JobQueueFull(Exception):
    """
    Tran job dang xep hang cua chinh nguoi dung (`MAX_ACTIVE_JOBS`) da day.

    KHONG phai loi: day la co che gioi han da co cua `POST /api/jobs`, va
    tang dieu phoi coi day la "dung xep them trong chu ky nay, thu lai chu ky
    sau". Vi vay no la mot ngoai le RIENG, khong lan voi `ChapterJobRejected`.
    """


class ChapterJobRejected(BulkImportError):
    """`POST /api/jobs` tu choi VINH VIEN (giong sai, chuong rong, ...)."""


class BatchStatus(str, Enum):
    #: Da ghi hang `lo`, DANG ghi danh sach muc. Bo dieu phoi khong lam gi ca.
    PREPARING = "preparing"
    #: Dang chay. Chi trang thai NAY cho phep tao chuong / xep job moi.
    RUNNING = "running"
    #: Chu da huy, nhung con job DANG BAY. Bo dieu phoi chi doi soat ket qua
    #: cua chung, khong tao them viec — xem docstring `BulkImportService.cancel`.
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    #: Khong con muc nao dang cho, va KHONG muc nao that bai.
    COMPLETED = "completed"
    #: Khong con muc nao dang cho, nhung CO muc that bai — cho chu bam thu lai.
    PARTIAL = "partial"
    #: Loi o cap LO (truyen da bi xoa, ghi danh sach muc khong xong).
    FAILED = "failed"


#: Lo o cac trang thai nay KHONG con duoc bo dieu phoi nhan them viec.
TERMINAL_BATCH_STATUSES = frozenset({
    BatchStatus.CANCELLED, BatchStatus.COMPLETED,
    BatchStatus.PARTIAL, BatchStatus.FAILED,
})

#: Cac trang thai ma bo dieu phoi phai QUET moi chu ky.
DRIVER_BATCH_STATUSES: Tuple[BatchStatus, ...] = (
    BatchStatus.PREPARING, BatchStatus.RUNNING, BatchStatus.CANCELLING,
)


class ItemStatus(str, Enum):
    PENDING = "pending"
    CHAPTER_CREATED = "chapter_created"
    JOB_QUEUED = "job_queued"
    COMPLETED = "completed"
    FAILED = "failed"


#: Muc con viec de lam. Lo chi "xong" khi khong con muc nao trong tap nay.
ACTIVE_ITEM_STATUSES: Tuple[ItemStatus, ...] = (
    ItemStatus.PENDING, ItemStatus.CHAPTER_CREATED, ItemStatus.JOB_QUEUED,
)


# -----------------------------------------------------------------------------
# Dinh danh tat dinh
# -----------------------------------------------------------------------------
#
# Appwrite gioi han `documentId` o 36 ky tu, chi cho [a-zA-Z0-9._-] va khong
# duoc bat dau bang ky tu dac biet. Moi do dai duoi day da tinh de vua tran do:
#
#   batch_id  = "imb_" + 24 hex            = 28 ky tu
#   item_id   = batch_id + "-" + 4 chu so  = 33 ky tu
#   chapter_id= "chp_" + 16 hex            = 20 ky tu (y het `new_id("chp")`)


def _bam(*phan: str) -> str:
    """SHA-256 cua cac phan noi bang U+001F. Chi de CHONG TRUNG, khong bao mat."""
    return hashlib.sha256("\x1f".join(phan).encode("utf-8")).hexdigest()


def chuan_hoa_noi_dung(raw: str) -> str:
    """
    Chuan hoa noi dung TRUOC KHI bam dau van tay.

    Bat buoc phai co: cung mot tep di qua trinh duyet/he dieu hanh khac nhau se
    ve CRLF hay LF khac nhau, va neu dau van tay doi theo do thi "gui lai cung
    tep" se tao mot lo MOI — dung cai tinh idempotent ma ca tinh nang nay dua
    vao. Chi doi ky tu xuong dong va cat khoang trang HAI DAU; khong dong vao
    ben trong van ban cua tac gia.
    """
    return (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def batch_fingerprint(owner_id: str, novel_id: str,
                      items: Sequence["ParsedChapter"]) -> str:
    """
    Dau van tay cua CA dot nhap: chu + truyen + danh sach (tieu de, noi dung).

    KHONG gom `voice_id`/`rate`/`chunk_chars`. Co y, va day la diem de sai
    nhat: neu gom giong doc vao day thi "gui lai cung tep voi giong khac" se
    ra mot `batch_id` khac, roi lo moi do se TAO LAI 500 chuong — dung tinh
    huong nhan doi noi dung ma ca thiet ke nay phai chan. Doi giong cho MOT
    chuong la viec cua duong don chuong da co (`POST /api/jobs`).
    """
    phan = [owner_id, novel_id, str(len(items))]
    for muc in items:
        phan.append(muc.title)
        phan.append(muc.content)
    return _bam(*phan)


def batch_id_from_fingerprint(fingerprint: str) -> str:
    return f"imb_{fingerprint[:24]}"


def item_id_for(batch_id: str, index: int) -> str:
    if not 1 <= index <= 9999:
        raise BulkImportFormatError("Chỉ số chương nằm ngoài phạm vi cho phép.")
    return f"{batch_id}-{index:04d}"


def chapter_id_for(item_id: str) -> str:
    """
    `chapter_id` TAT DINH cua mot muc.

    Dung dinh dang `chp_` + 16 hex y het `domain.new_id("chp")`, nen khong noi
    nao trong he thong phan biet duoc chuong nay voi chuong tao bang tay — do
    la muc dich: chuong nhap hang loat KHONG phai mot loai chuong khac.
    """
    return "chp_" + _bam(item_id)[:16]


def item_content_hash(title: str, content: str) -> str:
    return _bam(title, content)[:32]


# -----------------------------------------------------------------------------
# Doc dau vao
# -----------------------------------------------------------------------------

#: Dinh dang TXT: MOI chuong bat dau bang MOT dong tieu de dang
#:
#:     === Chương 1: Tựa đề ===
#:
#: it nhat ba dau `=` o hai ben, tieu de o giua. Moi thu tu sau dong do den
#: dong tieu de KE TIEP la noi dung cua chuong do.
#:
#: VI SAO doi `=` o CA HAI BEN thay vi mot dong `===` tran: mot dong `===` tran
#: la dau ngat canh RAT pho bien trong fanfic, va coi no la ranh gioi chuong se
#: bam nho mot chuong thanh hang chuc "chuong" rong. Dong `====` tran KHONG
#: khop mau nay (khong co tieu de o giua) nen van la noi dung binh thuong.
_DONG_TIEU_DE = re.compile(r"^[ \t]*={3,}[ \t]*(?P<tieu_de>.*?)[ \t]*={3,}[ \t]*$")

#: Ten dinh dang duoc phep o `POST .../chapter-imports`.
DINH_DANG_HO_TRO: Tuple[str, ...] = ("txt", "json")


@dataclass(frozen=True)
class ParsedChapter:
    """Mot chuong da doc ra tu dau vao — CHUA ghi gi ca."""

    title: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        """Hinh dang cho `POST .../preview`: KHONG kem noi dung day du."""
        return {"title": self.title, "char_count": len(self.content)}


def parse_txt(raw: str) -> List[ParsedChapter]:
    """
    Tach van ban tho theo mau `=== Tiêu đề ===`. Xem `_DONG_TIEU_DE`.

    Van ban dung TRUOC dong tieu de dau tien la LOI, khong phai "chuong khong
    ten": bo qua am tham thi mot tep thieu dong tieu de dau se mat sach chuong
    mot ma khong ai thay.
    """
    van_ban = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    tieu_de_hien_tai: Optional[str] = None
    dong_noi_dung: List[str] = []
    ra: List[ParsedChapter] = []

    def chot() -> None:
        if tieu_de_hien_tai is None:
            return
        ra.append(ParsedChapter(title=tieu_de_hien_tai,
                                content=chuan_hoa_noi_dung("\n".join(dong_noi_dung))))

    for so_dong, dong in enumerate(van_ban.split("\n"), start=1):
        khop = _DONG_TIEU_DE.match(dong)
        tieu_de = khop.group("tieu_de").strip() if khop else ""
        if khop and tieu_de:
            chot()
            tieu_de_hien_tai = tieu_de
            dong_noi_dung = []
            continue
        if tieu_de_hien_tai is None:
            if dong.strip():
                raise BulkImportFormatError(
                    f"Dòng {so_dong} nằm trước tiêu đề chương đầu tiên. Mỗi "
                    "chương phải bắt đầu bằng một dòng dạng "
                    "`=== Tên chương ===`."
                )
            continue
        dong_noi_dung.append(dong)
    chot()

    if not ra:
        raise BulkImportFormatError(
            "Không tìm thấy chương nào. Mỗi chương phải bắt đầu bằng một dòng "
            "dạng `=== Tên chương ===`."
        )
    return ra


def parse_json(raw: str) -> List[ParsedChapter]:
    """
    Doc JSON: `[{title, content}, ...]` hoac `{"chapters": [...]}`.

    NGHIEM NGAT ve ten khoa (`title`/`content`). Nhan bua cac ten gan gan
    (`name`/`body`/`text`) nghe co ve tien, nhung mot khoa viet sai am tham
    thanh chuong RONG thi te hon han mot loi 400 doc duoc.
    """
    try:
        du_lieu = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise BulkImportFormatError(f"JSON không hợp lệ: {exc}") from exc
    if isinstance(du_lieu, dict):
        du_lieu = du_lieu.get("chapters")
    if not isinstance(du_lieu, list):
        raise BulkImportFormatError(
            "JSON phải là một mảng `[{\"title\": ..., \"content\": ...}]` hoặc "
            "một đối tượng có khoá `chapters`."
        )
    ra: List[ParsedChapter] = []
    for i, phan_tu in enumerate(du_lieu, start=1):
        if not isinstance(phan_tu, dict):
            raise BulkImportFormatError(f"Phần tử thứ {i} không phải đối tượng.")
        thieu = [k for k in ("title", "content") if k not in phan_tu]
        if thieu:
            raise BulkImportFormatError(
                f"Phần tử thứ {i} thiếu khoá: {', '.join(thieu)}.")
        ra.append(ParsedChapter(
            title=str(phan_tu.get("title") or "").strip(),
            content=chuan_hoa_noi_dung(str(phan_tu.get("content") or "")),
        ))
    if not ra:
        raise BulkImportFormatError("Danh sách chương rỗng.")
    return ra


def parse_input(raw: str, dinh_dang: str) -> List[ParsedChapter]:
    ten = (dinh_dang or "").strip().lower()
    if ten == "txt":
        return parse_txt(raw)
    if ten == "json":
        return parse_json(raw)
    raise BulkImportFormatError(
        f"Định dạng '{dinh_dang}' không được hỗ trợ. "
        f"Chấp nhận: {', '.join(DINH_DANG_HO_TRO)}.")


def validate_chapters(items: Sequence[ParsedChapter], *, max_items: int,
                      max_chars_per_item: int, max_total_chars: int,
                      max_title_chars: int = 200) -> None:
    """
    Kiem CA danh sach TRUOC KHI ghi bat ky hang nao.

    Kiem het roi moi tu choi (khong ghi gi), thay vi ghi den khi gap muc sai:
    nhap nua voi la trang thai kho don nhat cua ca tinh nang nay.
    """
    if not items:
        raise BulkImportFormatError("Không có chương nào để nhập.")
    if len(items) > max_items:
        raise BulkImportFormatError(
            f"Một lô nhập tối đa {max_items} chương (đang có {len(items)}). "
            "Hãy chia tệp thành nhiều lô — các lô nối tiếp nhau đúng thứ tự."
        )
    tong = 0
    for i, muc in enumerate(items, start=1):
        if not muc.title.strip():
            raise BulkImportFormatError(f"Chương thứ {i} không có tiêu đề.")
        if len(muc.title) > max_title_chars:
            raise BulkImportFormatError(
                f"Tiêu đề chương thứ {i} dài quá {max_title_chars} ký tự.")
        if not muc.content.strip():
            raise BulkImportFormatError(
                f"Chương thứ {i} (“{muc.title[:60]}”) không có nội dung.")
        if len(muc.content) > max_chars_per_item:
            raise BulkImportFormatError(
                f"Chương thứ {i} (“{muc.title[:60]}”) dài "
                f"{len(muc.content)} ký tự, vượt giới hạn {max_chars_per_item}."
            )
        tong += len(muc.content)
    if tong > max_total_chars:
        raise BulkImportFormatError(
            f"Tổng nội dung {tong} ký tự, vượt giới hạn {max_total_chars} cho "
            "một lô. Hãy chia thành nhiều lô."
        )


# -----------------------------------------------------------------------------
# Thuc the
# -----------------------------------------------------------------------------


@dataclass
class ImportBatch:
    """
    Mot dot nhap chuong hang loat.

    Cac bo dem (`count_*`) la DAN XUAT nhung duoc LUU: trang theo doi cua chu
    truyen se poll vai giay mot lan, va dem lai 500 hang moi lan poll la mot
    duong de dot han muc doc cua Appwrite (da co mot su co dung nhu vay). Bo
    dieu phoi cap nhat chung theo tung buoc chuyen trang thai no thuc hien, va
    dem lai CHINH XAC dung mot lan — luc ket lo. Xem
    `BulkImportService._dem_lai`.
    """

    owner_id: str
    novel_id: str
    fingerprint: str
    total_items: int
    batch_id: str = ""
    status: BatchStatus = BatchStatus.PREPARING
    #: Rong = CHI tao chuong, khong tao audio. Hop le va huu dung: nhieu tac
    #: gia muon dang van ban truoc, chon giong sau.
    voice_id: str = ""
    rate: str = "1.0"
    chunk_chars: int = 2000
    #: `order_index` cua chuong = `order_base + item_index`. Chot MOT LAN luc
    #: tao lo, nen mot lan chay lai khong day thu tu di.
    order_base: int = 0
    source_name: str = ""
    count_pending: int = 0
    count_chapter_created: int = 0
    count_job_queued: int = 0
    count_completed: int = 0
    count_failed: int = 0
    last_error: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    cancelled_at: str = ""
    finished_at: str = ""

    def __post_init__(self) -> None:
        if not self.batch_id:
            self.batch_id = batch_id_from_fingerprint(self.fingerprint)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BATCH_STATUSES

    @property
    def active_items(self) -> int:
        return (self.count_pending + self.count_chapter_created
                + self.count_job_queued)

    def to_dict(self) -> Dict[str, Any]:
        """HINH DANG LUU TRU va hinh dang API la MOT — khong truong dan xuat
        nao o day, de bo test hop dong schema so sanh truc tiep duoc."""
        return {
            "batch_id": self.batch_id,
            "owner_id": self.owner_id,
            "novel_id": self.novel_id,
            "fingerprint": self.fingerprint,
            "total_items": self.total_items,
            "status": self.status.value,
            "voice_id": self.voice_id,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "order_base": self.order_base,
            "source_name": self.source_name,
            "count_pending": self.count_pending,
            "count_chapter_created": self.count_chapter_created,
            "count_job_queued": self.count_job_queued,
            "count_completed": self.count_completed,
            "count_failed": self.count_failed,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cancelled_at": self.cancelled_at,
            "finished_at": self.finished_at,
        }

    def progress(self) -> Dict[str, Any]:
        """
        Bang tien do cho giao dien — CONG DON, khong phai dem theo trang thai.

        "Da tao 480 chuong" la thong tin chu truyen can; "80 muc dang o trang
        thai chapter_created" thi khong.
        """
        tong = max(self.total_items, 0)
        da_tao_chuong = (self.count_chapter_created + self.count_job_queued
                         + self.count_completed)
        da_xep_job = self.count_job_queued + self.count_completed
        return {
            "total": tong,
            "pending": self.count_pending,
            "chapters_created": da_tao_chuong,
            "jobs_queued": da_xep_job,
            "completed": self.count_completed,
            "failed": self.count_failed,
            "percent": (int(round(100.0 * (self.count_completed
                                           + self.count_failed) / tong))
                        if tong else 0),
        }


@dataclass
class ImportItem:
    """
    Mot chuong-sap-duoc-nhap. MOT hang moi chuong, co y.

    KHONG gom ca danh sach vao mot hang JSON: 500 chuong khong vua mot
    document Appwrite, va "thu lai mot muc" se bien thanh "ghi lai ca lo".

    `content` KHONG bi xoa sau khi tao chuong xong. No la ban goc de doi soat
    va la thu duy nhat cho phep tao lai chuong neu chu vo tinh xoa no roi bam
    "thử lại". Duong doc cua API luon `select` bo cot nay ra nen khong ai phai
    tra gia truyen tai no.
    """

    batch_id: str
    owner_id: str
    novel_id: str
    item_index: int
    title: str
    content: str = ""
    item_id: str = ""
    content_hash: str = ""
    char_count: int = 0
    status: ItemStatus = ItemStatus.PENDING
    chapter_id: str = ""
    job_id: str = ""
    error_message: str = ""
    attempts: int = 0
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = item_id_for(self.batch_id, self.item_index)
        if not self.content_hash:
            self.content_hash = item_content_hash(self.title, self.content)
        if not self.char_count:
            self.char_count = len(self.content or "")

    def to_dict(self, include_content: bool = False) -> Dict[str, Any]:
        """
        `include_content=False` la MAC DINH, nguoc voi `Chapter.to_dict()`.

        Co y: cho nay duoc doc theo TRANG (50 muc mot lan) tu mot bang tien do
        tu lam moi. Mac dinh kem noi dung se bien mot lan poll thanh vai MB.
        """
        data = {
            "item_id": self.item_id,
            "batch_id": self.batch_id,
            "owner_id": self.owner_id,
            "novel_id": self.novel_id,
            "item_index": self.item_index,
            "title": self.title,
            "content_hash": self.content_hash,
            "char_count": self.char_count,
            "status": self.status.value,
            "chapter_id": self.chapter_id,
            "job_id": self.job_id,
            "error_message": self.error_message,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_content:
            data["content"] = self.content
        return data


def batch_status_from(value: Any, mac_dinh: BatchStatus = BatchStatus.PREPARING
                      ) -> BatchStatus:
    """
    Doc trang thai tu MOT chuoi hoac tu chinh enum.

    NHANH `isinstance` PHAI DUNG TRUOC, va day la mot cai bay that: `BatchStatus`
    tron `str` nhung KHONG phai `StrEnum`, nen `str(BatchStatus.RUNNING)` ra
    `"BatchStatus.RUNNING"` chu khong ra `"running"`. Thieu nhanh nay thi moi lan
    ghi `{"status": BatchStatus.RUNNING}` se AM THAM roi ve gia tri mac dinh —
    lo dung im o `preparing` mai mai, khong loi, khong dau vet.
    """
    if isinstance(value, BatchStatus):
        return value
    try:
        return BatchStatus(str(value or mac_dinh.value))
    except ValueError:
        return mac_dinh


def item_status_from(value: Any, mac_dinh: ItemStatus = ItemStatus.PENDING
                     ) -> ItemStatus:
    """Xem canh bao o `batch_status_from` — cung cai bay `str(Enum)`."""
    if isinstance(value, ItemStatus):
        return value
    try:
        return ItemStatus(str(value or mac_dinh.value))
    except ValueError:
        return mac_dinh

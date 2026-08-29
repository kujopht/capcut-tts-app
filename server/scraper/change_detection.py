"""Phát hiện thay đổi gia tăng — nền móng Story Harvester V4.

`incremental.py::diff_toc` trả lời được NEW/REMOVED **chỉ từ trang mục lục**,
và docstring của nó nói thẳng điều còn thiếu: phát hiện `UPDATED` — chương đã
có, vẫn còn đó, nhưng nguồn đã sửa nội dung — cần tải lại từng chương để so
`content_hash`, tức N lần tải thay vì 1.

Module này làm nốt phần đó, nhưng **không** bằng cách tải lại tất cả. Nó dùng
validator có điều kiện (`ETag`/`Last-Modified`) mà `HttpFetcher` đã hỗ trợ sẵn:
một chương không đổi tốn đúng một phản hồi **304 thân rỗng**, không phải cả
trang. Chỉ khi nguồn trả 200 mới có nội dung để băm và so.

Vì sao tách khỏi `incremental.py`: `diff_toc` là phép so **thuần tuý**, không
chạm mạng, và giá trị của nó nằm ở chỗ đó. Trộn I/O vào sẽ làm mất tính chất
ấy. Ở đây tầng mạng được tiêm vào (`fetcher`), nên `FixtureFetcher` cho phép
kiểm thử tất định toàn bộ ma trận phân loại mà không gọi ra ngoài lần nào.

**Không ghi gì cả.** Module này chỉ *phân loại* và giải thích. Việc ghi thuộc
về `bulk.py`/`run_state.py`. Đó là điều làm `--dry-run` trở nên trung thực:
chế độ thử chạy đúng đoạn mã này, không phải một nhánh song song.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from server.scraper.contract import canonicalize_url
from server.scraper.dedupe import ScrapeState, content_hash

#: Mã trạng thái coi là "nguồn đã bỏ chương này", không phải lỗi tạm thời.
#: 404 = không còn; 410 = đã xoá vĩnh viễn; 451 = gỡ vì lý do pháp lý.
MA_DA_BIEN_MAT = frozenset({404, 410, 451})

#: Tran do dai cho MOI manh van ban do NGUON kiem soat khi di vao `evidence`.
_TRAN_BANG_CHUNG = 200


def _an_toan(text: str) -> str:
    """Lam sach mot manh van ban do NGUON kiem soat truoc khi dua vao `evidence`.

    Noi dung nguon la DU LIEU KHONG DANG TIN. `str(exc)` cua
    `RobotsDisallowedError` mang nguyen van chuoi tu `robots.txt` cua ho — tuc
    la mot ke so huu nguon quyet dinh duoc noi dung do. Neu `evidence` chay
    thang vao log, giao dien quan tri, hay ngu canh cua mot tac tu, thi day la
    diem PHAT SINH cua injection. Neu ra qua review bao mat doc lap.

    Cat xuong dong (chan log injection), bo ky tu dieu khien, va gioi han do
    dai (chan DoS bo nho log).
    """
    # `isprintable()` da loai bo moi ky tu dieu khien, ke ca xuong dong
    # va tab — nen no vua chan log injection vua chan ky tu vo hinh.
    sach = "".join(c for c in str(text) if c.isprintable())
    return sach[:_TRAN_BANG_CHUNG]


class ChangeKind(str, Enum):
    """Phân loại BẮT BUỘC — mỗi mục đúng một nhãn, không bao giờ gộp.

    Gộp `TRANSIENT_FAILURE` vào `REMOVED_OR_UNAVAILABLE` là cái bẫy đáng sợ
    nhất ở đây: một lần 503 thoáng qua sẽ bị đọc thành "nguồn đã xoá chương",
    và một chính sách dọn dẹp tự động sẽ xoá nội dung thật vì một sự cố mạng.
    """

    UNCHANGED = "unchanged"
    NEW_CHAPTER = "new_chapter"
    #: CO ban ghi, nhung KHONG co noi dung dung duoc de so — lan truoc that
    #: bai, hoac ban ghi cu thieu `content_hash`. KHAC `NEW_CHAPTER` (chua
    #: tung thay) va KHAC `UPDATED_CHAPTER` (da co ban cu de so). Ep no vao
    #: `UPDATED_CHAPTER` la noi doi: khong co gi de noi la "da doi".
    NEEDS_BASELINE = "needs_baseline"
    UPDATED_CHAPTER = "updated_chapter"
    REMOVED_OR_UNAVAILABLE = "removed_or_unavailable"
    SOURCE_METADATA_CHANGED = "source_metadata_changed"
    TRANSIENT_FAILURE = "transient_failure"


@dataclass(frozen=True)
class ChapterChange:
    """Một phán quyết, kèm **bằng chứng vì sao**.

    `evidence` không phải để cho đẹp: khi một đợt harvest báo 40 chương
    UPDATED, câu hỏi đầu tiên của người vận hành luôn là "dựa vào đâu". Không
    có trường này thì câu trả lời duy nhất là đọc lại log thô.
    """

    kind: ChangeKind
    canonical_url: str
    evidence: str = ""
    previous_content_hash: str = ""
    new_content_hash: str = ""
    status_code: Optional[int] = None
    #: `True` khi phán quyết đến từ một lần gọi mạng, `False` khi chỉ suy ra
    #: từ trang mục lục. Người vận hành cần phân biệt "đã kiểm chứng" với
    #: "mới chỉ suy đoán".
    revalidated: bool = False


@dataclass
class HarvestPlan:
    """Việc **đề xuất** làm, chưa làm gì cả."""

    changes: List[ChapterChange] = field(default_factory=list)

    def by_kind(self, kind: ChangeKind) -> List[ChapterChange]:
        return [c for c in self.changes if c.kind == kind]

    def counts(self) -> Dict[str, int]:
        ra = {k.value: 0 for k in ChangeKind}
        for c in self.changes:
            ra[c.kind.value] += 1
        return ra

    @property
    def urls_can_tai(self) -> List[str]:
        """Chỉ những URL thực sự phải tải nội dung đầy đủ.

        `UNCHANGED` bị loại — đó chính là chỗ tiết kiệm. `TRANSIENT_FAILURE`
        cũng bị loại: thử lại là việc của tầng retry có backoff, không phải
        nhét thẳng vào lô tải của lượt này. `NEEDS_BASELINE` thì PHẢI có: đó
        đúng là những chương chưa hề có nội dung dùng được.

        Người gọi vẫn phải TẢI LẠI các URL này — `revalidate` cố ý không giữ
        thân phản hồi, vì giữ lại nội dung của hàng nghìn chương trong một
        đối tượng phán quyết là một cách hết bộ nhớ rất nhanh. Hệ quả: hash
        trong phán quyết là ẢNH CHỤP LÚC PHÁT HIỆN, không phải hash của thứ
        sẽ được ghi; tầng ghi phải tự băm lại nội dung nó thực sự nhận được.
        """
        return [c.canonical_url for c in self.changes
                if c.kind in (ChangeKind.NEW_CHAPTER, ChangeKind.UPDATED_CHAPTER,
                              ChangeKind.NEEDS_BASELINE)]

    @property
    def co_thay_doi(self) -> bool:
        return any(c.kind is not ChangeKind.UNCHANGED for c in self.changes)


def classify_index(state: ScrapeState, chapter_urls: Sequence[str]) -> HarvestPlan:
    """Phán quyết rút được **chỉ từ trang mục lục** — không chạm mạng.

    Cho ra `NEW_CHAPTER` và `REMOVED_OR_UNAVAILABLE` chắc chắn. Mọi URL đã
    biết mà vẫn còn trong mục lục được đánh `UNCHANGED` **tạm thời**: ở tầng
    này không có cách nào biết nội dung có đổi hay không. `revalidate()` là
    thứ nâng cấp phán quyết tạm đó thành phán quyết đã kiểm chứng.
    """
    ke_hoach = HarvestPlan()

    # KHU TRUNG theo URL da chuan hoa, GIU nguyen thu tu xuat hien.
    #
    # Truoc day vong lap nay duyet `chapter_urls` THO trong khi `canon_tuoi`
    # la mot set: mot muc luc liet ke cung mot chuong hai lan (hoac hai bien
    # the tracking param) sinh ra HAI phan quyet cho cung mot chuong — tuc la
    # hai lan goi mang va an hai suat trong `limit`. Neu ra qua ca hai ban
    # review doc lap.
    canon_tuoi: List[str] = []
    da_thay = set()
    for url in chapter_urls:
        canon = canonicalize_url(url)
        if canon not in da_thay:
            da_thay.add(canon)
            canon_tuoi.append(canon)

    for canon in canon_tuoi:
        cu = state.get(canon)
        if cu is None:
            ke_hoach.changes.append(ChapterChange(
                kind=ChangeKind.NEW_CHAPTER, canonical_url=canon,
                evidence="chưa có bản ghi nào cho URL này"))
            continue
        hash_cu = str(cu.get("content_hash") or "")
        trang_thai = str(cu.get("status") or "")
        if trang_thai != "ok" or not hash_cu:
            # CO ban ghi nhung KHONG co gi dung duoc de so. Danh `UNCHANGED`
            # o day se lam chuong nay khong bao gio duoc tai lai — lan truoc
            # that bai thi no ket o do vinh vien.
            ke_hoach.changes.append(ChapterChange(
                kind=ChangeKind.NEEDS_BASELINE, canonical_url=canon,
                previous_content_hash=hash_cu,
                evidence=(f"bản ghi có nhưng chưa dùng được "
                          f"(status={trang_thai!r}, "
                          f"{'thiếu' if not hash_cu else 'có'} content_hash)")))
            continue
        ke_hoach.changes.append(ChapterChange(
            kind=ChangeKind.UNCHANGED, canonical_url=canon,
            previous_content_hash=hash_cu,
            evidence="còn trong mục lục; nội dung CHƯA kiểm chứng"))

    tap_tuoi = set(canon_tuoi)
    da_bao = set()
    for canon in state.known_urls(status="ok"):
        c = canonicalize_url(canon)
        if c not in tap_tuoi and c not in da_bao:
            da_bao.add(c)
            ke_hoach.changes.append(ChapterChange(
                kind=ChangeKind.REMOVED_OR_UNAVAILABLE, canonical_url=c,
                evidence="từng ghi nhận 'ok' nhưng không còn trong mục lục"))
    return ke_hoach


def revalidate(
    plan: HarvestPlan,
    state: ScrapeState,
    fetcher: Any,
    *,
    extract_text: Callable[[str, str], str],
    validators: Optional[Dict[str, Dict[str, str]]] = None,
    limit: Optional[int] = None,
) -> HarvestPlan:
    """Nâng các phán quyết `UNCHANGED` *tạm thời* thành phán quyết đã kiểm chứng.

    :param extract_text: `(html, url) -> clean_text`. Tiêm vào chứ không gọi
        thẳng bộ trích xuất: việc phân loại không được phụ thuộc vào một chiến
        lược trích xuất cụ thể, và test cần thay được nó.
    :param validators: `{canonical_url: {"etag": ..., "last_modified": ...}}`
        từ lần quét trước. Thiếu thì vẫn chạy đúng, chỉ tốn băng thông hơn —
        nguồn trả 200 kèm nội dung thay vì 304 rỗng.
    :param limit: trần số lần gọi mạng cho MỘT lượt. Một series 4.000 chương
        không được biến một lần "kiểm tra cập nhật" thành 4.000 request.

    Chỉ đụng tới `UNCHANGED`. `NEW_CHAPTER` không có gì để so; `REMOVED` đã
    kết luận từ mục lục.
    """
    validators = validators or {}
    con_lai = limit
    moi: List[ChapterChange] = []

    for c in plan.changes:
        # `NEEDS_BASELINE` KHONG duoc kiem chung qua mang: khong co hash cu
        # thi khong co gi de so, va mot 304 o day cung khong chung minh duoc
        # ta DANG co noi dung dung duoc — no chi noi tai nguyen khong doi so
        # voi validator. Cu de nguyen nhan do, no da nam trong `urls_can_tai`.
        if c.kind is not ChangeKind.UNCHANGED:
            moi.append(c)
            continue
        if con_lai is not None and con_lai <= 0:
            # Hết ngân sách: GIỮ NGUYÊN phán quyết tạm và nói rõ là chưa
            # kiểm chứng, chứ không tự nâng thành "đã xác nhận không đổi".
            moi.append(ChapterChange(
                kind=ChangeKind.UNCHANGED, canonical_url=c.canonical_url,
                previous_content_hash=c.previous_content_hash,
                evidence="hết ngân sách kiểm chứng lượt này; CHƯA kiểm chứng"))
            continue
        if con_lai is not None:
            con_lai -= 1
        moi.append(_kiem_chung_mot(c, state, fetcher, extract_text, validators))

    return HarvestPlan(changes=moi)


def _kiem_chung_mot(c: ChapterChange, state: ScrapeState, fetcher: Any,
                    extract_text: Callable[[str, str], str],
                    validators: Dict[str, Dict[str, str]]) -> ChapterChange:
    from server.scraper.http_fetcher import FetchError, RobotsDisallowedError

    val = validators.get(c.canonical_url, {})
    try:
        kq = fetcher.fetch(c.canonical_url,
                           if_none_match=val.get("etag") or None,
                           if_modified_since=val.get("last_modified") or None)
    except RobotsDisallowedError as exc:
        # KHÔNG phải lỗi tạm thời: nguồn cố ý từ chối. Thử lại vô hạn ở đây
        # là bỏ qua một giới hạn có chủ đích của họ.
        return ChapterChange(
            kind=ChangeKind.REMOVED_OR_UNAVAILABLE, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash, revalidated=True,
            evidence=f"robots.txt từ chối: {_an_toan(exc)}")
    except FetchError as exc:
        return ChapterChange(
            kind=ChangeKind.TRANSIENT_FAILURE, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash, revalidated=True,
            evidence=f"lỗi tải: {type(exc).__name__}")

    if kq.not_modified or kq.status_code == 304:
        return ChapterChange(
            kind=ChangeKind.UNCHANGED, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash, status_code=304,
            revalidated=True, evidence="nguồn trả 304 với validator đã gửi")

    if kq.status_code in MA_DA_BIEN_MAT:
        return ChapterChange(
            kind=ChangeKind.REMOVED_OR_UNAVAILABLE, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash,
            status_code=kq.status_code, revalidated=True,
            evidence=f"nguồn trả {kq.status_code}")

    if kq.status_code >= 400:
        # 5xx, 429, và mọi 4xx còn lại: KHÔNG kết luận là đã xoá. Xem
        # docstring `ChangeKind`.
        return ChapterChange(
            kind=ChangeKind.TRANSIENT_FAILURE, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash,
            status_code=kq.status_code, revalidated=True,
            evidence=f"nguồn trả {kq.status_code}; chưa kết luận được")

    try:
        moi_hash = content_hash(extract_text(kq.text, kq.final_url))
    except (MemoryError, RecursionError):
        # KHONG nuot. Ca hai deu ke thua `Exception` trong Python 3, nen mot
        # `except Exception` tran se bien "tien trinh sap het bo nho" thanh
        # "mot chuong loi tam thoi" va worker chay tiep trong trang thai bat
        # on thay vi chet sach de supervisor khoi dong lai. Neu ra qua review
        # bao mat doc lap.
        raise
    except Exception as exc:
        # Trang hỏng/không phân tích được KHÔNG phải "đã xoá" và cũng không
        # phải "không đổi" — nó là một thất bại cần người xem.
        return ChapterChange(
            kind=ChangeKind.TRANSIENT_FAILURE, canonical_url=c.canonical_url,
            previous_content_hash=c.previous_content_hash,
            status_code=kq.status_code, revalidated=True,
            evidence=f"không trích xuất được: {type(exc).__name__}")

    cu_hash = c.previous_content_hash or str(
        (state.get(c.canonical_url) or {}).get("content_hash") or "")

    if not cu_hash:
        # Có bản ghi nhưng không có hash (bản ghi cũ/thất bại trước đó): không
        # có cơ sở để nói "đổi". Coi là cần tải lại, không phải đã đổi.
        return ChapterChange(
            kind=ChangeKind.UPDATED_CHAPTER, canonical_url=c.canonical_url,
            new_content_hash=moi_hash, status_code=kq.status_code,
            revalidated=True,
            evidence="bản ghi cũ không có content_hash để so sánh")

    if moi_hash == cu_hash:
        return ChapterChange(
            kind=ChangeKind.UNCHANGED, canonical_url=c.canonical_url,
            previous_content_hash=cu_hash, new_content_hash=moi_hash,
            status_code=kq.status_code, revalidated=True,
            evidence="content_hash trùng khớp")

    return ChapterChange(
        kind=ChangeKind.UPDATED_CHAPTER, canonical_url=c.canonical_url,
        previous_content_hash=cu_hash, new_content_hash=moi_hash,
        status_code=kq.status_code, revalidated=True,
        evidence=f"content_hash đổi {cu_hash[:8]}… → {moi_hash[:8]}…")


#: Trường metadata của series đáng theo dõi. Đổi tiêu đề/tác giả là tín hiệu
#: nguồn đã sửa trang, KHÔNG tự động kéo theo hành động nào.
TRUONG_METADATA = ("series_title", "series_author", "series_description")


def detect_metadata_change(cu: Dict[str, Any],
                           moi: Dict[str, Any]) -> Optional[ChapterChange]:
    """So metadata series. Trả `None` khi không đổi.

    CẢ HAI tham số phải là **ảnh chụp đầy đủ**, không phải bản vá từng phần:
    khoá vắng mặt được coi như chuỗi rỗng, nên một dict chỉ chứa các trường
    *đã đổi* sẽ bị đọc thành "mọi trường khác vừa bị xoá".

    Dùng `canonical_url` để chứa khoá series chứ không phải URL chương — đây
    là phán quyết ở mức SERIES, và việc tái dùng cùng một kiểu dữ liệu giữ cho
    người tiêu thụ chỉ phải xử lý một hình dạng.
    """
    khac = [t for t in TRUONG_METADATA
            if str(cu.get(t) or "") != str(moi.get(t) or "")]
    if not khac:
        return None
    nguon = str(moi.get("source_url") or cu.get("source_url") or "")
    return ChapterChange(
        kind=ChangeKind.SOURCE_METADATA_CHANGED,
        # Chuan hoa cho nhat quan voi moi `canonical_url` khac trong ke hoach.
        canonical_url=canonicalize_url(nguon) if nguon else "",
        revalidated=True,
        evidence="metadata đổi: " + ", ".join(khac))

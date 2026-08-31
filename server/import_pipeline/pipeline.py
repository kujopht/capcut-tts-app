"""
`AuthorizedImportService` — luong "Import my fanfic" day du: upload -> raw
archive -> parse -> tach chuong -> chuan hoa -> phan loai fandom -> validate
-> tao Novel/Chapter that o DRAFT -> ImportRecord. Doc lap voi Universal
Story Scraper (`server/scraper_ops_service.py`) — nguon o day la mot FILE
tac gia tu nop, khong phai mot URL cong khai.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from server.bulk_import_domain import (
    BulkImportFormatError, ParsedChapter, validate_chapters,
)
from server.domain import ImportRecord, Novel, PublicationMode, RightsBasis
from server.fandom_registry import FandomRegistry, UnknownFandomError
from server.import_pipeline import formats
from server.import_pipeline.chapter_split import split_into_chapters
from server.import_pipeline.formats import UnsupportedImportFormatError
from server.import_pipeline.safe_zip import UnsafeZipError, inspect_zip, read_all_safe
from server.scraper.raw_archive import (
    SensitiveContentDetected, spool_uploaded_raw,
)

#: Gioi han CO CHU DICH GIU THAP — mot lan nhap la MOT tac pham cua MOT tac
#: gia, khong phai mot dot mass-import. Tranh mot tep loi/be gay tao ra hang
#: nghin "chuong" rac.
MAX_CHAPTERS_PER_IMPORT = 500
MAX_CHARS_PER_CHAPTER = 200_000
MAX_TOTAL_CHARS_PER_IMPORT = 5_000_000

_DINH_DANG_HO_TRO = frozenset({"txt", "html", "epub", "docx", "zip"})


class NoContentExtractedError(Exception):
    """Tep doc duoc nhung khong trich xuat ra van ban nao (vd EPUB rong,
    DOCX chi co hinh anh)."""


@dataclass
class AuthorizedImportResult:
    novel: Novel
    chapters: List[Any]
    import_record: ImportRecord
    fandom_match_summary: Dict[str, List[str]]
    raw_archive_local_dir: Path


#: Cung kieu voi `bulk_import_service.py::TaoChuong` — tiem vao TU BEN
#: NGOAI (route) de goi DUNG `main.py::_tao_chuong_cho_truyen`, "duong tao
#: chuong duy nhat" cua he thong (thong bao nguoi theo doi + XP), thay vi
#: mo mot duong ghi chuong thu hai. Tranh import vong: `import_pipeline`
#: khong duoc phep import `server.main`.
TaoChuong = Callable[..., Tuple[Any, bool]]


class AuthorizedImportService:
    def __init__(self, metadata_store: Any, import_record_store: Any,
                 *, tao_chuong: TaoChuong,
                 fandom_registry: Optional[FandomRegistry] = None,
                 spool_root: Path):
        self._store = metadata_store
        self._import_records = import_record_store
        self._tao_chuong = tao_chuong
        self._fandom_registry = fandom_registry or FandomRegistry()
        self._spool_root = spool_root

    def _trich_van_ban(self, data: bytes, dinh_dang: str) -> List[ParsedChapter]:
        """Tra ve danh sach `ParsedChapter` — moi dinh dang co duong tach
        chuong RIENG (EPUB co spine that su; TXT/HTML/DOCX chi co mot khoi
        van ban, dung `split_into_chapters` de doan ranh gioi)."""
        if dinh_dang == "txt":
            return split_into_chapters(formats.extract_text_txt(data))
        if dinh_dang == "html":
            return split_into_chapters(formats.extract_text_html(data))
        if dinh_dang == "docx":
            return split_into_chapters(formats.extract_text_docx(data))
        if dinh_dang == "epub":
            cap = formats.extract_chapters_epub(data)
            return [ParsedChapter(title=t, content=c) for t, c in cap if c.strip()]
        raise UnsupportedImportFormatError(
            f"Định dạng không được hỗ trợ: {dinh_dang!r}. "
            f"Chấp nhận: {', '.join(sorted(_DINH_DANG_HO_TRO))}.")

    def _trich_tu_zip(self, data: bytes) -> List[ParsedChapter]:
        """ZIP la mot HOP CHUA — moi tep con duoc trich xuat theo dinh dang
        cua CHINH NO (doan qua duoi ten), roi GOP chuong theo dung thu tu
        ten tep (sap xep alphabet — tac gia thuong dat ten "01-chuong-1.txt",
        "02-chuong-2.txt", nen day la doan hop ly nhat khong co sieu du lieu
        thu tu nao khac)."""
        try:
            muc = read_all_safe(data)
        except UnsafeZipError as exc:
            raise BulkImportFormatError(f"ZIP không an toàn: {exc}") from exc

        ra: List[ParsedChapter] = []
        for ten in sorted(muc):
            dinh_dang_con = formats.guess_format_from_filename(ten)
            if dinh_dang_con is None or dinh_dang_con == "zip":
                continue  # bo qua file khong nhan dang duoc / zip long nhau
            try:
                ra.extend(self._trich_van_ban(muc[ten], dinh_dang_con))
            except Exception:
                continue  # MOT tep loi trong zip khong duoc dung ca dot nhap
        return ra

    def import_authorized_work(
            self, *, data: bytes, filename: str, declared_format: str,
            owner_id: str, title: str, rights_basis: RightsBasis,
            fandom_names: Optional[List[str]] = None,
            publication_mode: PublicationMode = PublicationMode.FULL_TEXT,
    ) -> AuthorizedImportResult:
        dinh_dang = (declared_format or "").strip().lower()
        if dinh_dang not in _DINH_DANG_HO_TRO:
            raise UnsupportedImportFormatError(
                f"Định dạng không được hỗ trợ: {declared_format!r}.")

        # 1) RAW ARCHIVE — luu byte GOC truoc khi dong cham gi den noi dung.
        #    scan_text CHI truyen cho txt/html (doc duoc truc tiep nhu van
        #    ban) — epub/docx/zip la nhi phan, quet SAU o buoc 2 tren van
        #    ban DA trich xuat thay vi tren byte tho.
        scan_text = None
        if dinh_dang in ("txt", "html"):
            scan_text = (formats.extract_text_txt(data) if dinh_dang == "txt"
                        else formats.extract_text_html(data))
        raw_result = spool_uploaded_raw(
            data, spool_root=self._spool_root, filename=filename,
            importer_user_id=owner_id, scan_text=scan_text)

        # 2) PARSE + TACH CHUONG
        if dinh_dang == "zip":
            chuong_list = self._trich_tu_zip(data)
        else:
            chuong_list = self._trich_van_ban(data, dinh_dang)
        if not chuong_list:
            raise NoContentExtractedError(
                f"Không trích xuất được nội dung nào từ {filename!r}.")

        # Quet du lieu nhay cam tren van ban DA TRICH XUAT cho dinh dang nhi
        # phan (khong quet duoc luc raw archive o buoc 1).
        if dinh_dang in ("epub", "docx", "zip"):
            from server.scraper.raw_archive import scan_for_sensitive_data
            toan_bo_van_ban = "\n".join(c.content for c in chuong_list)
            hit = scan_for_sensitive_data(toan_bo_van_ban)
            if hit:
                raise SensitiveContentDetected(
                    f"Phat hien du lieu nhay cam ({hit}) trong noi dung da "
                    f"trich xuat tu {filename!r} — tu choi nhap.")

        # 3) VALIDATE (tai su dung dung nguyen tac voi bulk import hang loat)
        validate_chapters(
            chuong_list, max_items=MAX_CHAPTERS_PER_IMPORT,
            max_chars_per_item=MAX_CHARS_PER_CHAPTER,
            max_total_chars=MAX_TOTAL_CHARS_PER_IMPORT)

        # 4) PHAN LOAI FANDOM — KHONG BAO GIO doan bua ten chua biet.
        fandom_summary = {"matched": [], "unmatched": []}
        if fandom_names:
            fandom_summary = self._fandom_registry.classify_many(fandom_names)

        # 5) TAO NOVEL/CHAPTER THAT O DRAFT
        novel = self._store.create_novel(Novel(
            owner_id=owner_id, title=title.strip(),
            fandom_ids=fandom_summary["matched"],
            publication_mode=publication_mode,
        ))
        tao_ra = []
        for idx, chuong in enumerate(chuong_list, start=1):
            # `bao_nguoi_theo_doi=False`: Novel vua tao la DRAFT, chua co
            # nguoi theo doi nao ma bao — cung ly do voi
            # `bulk_import_service.py` khi nhap vao truyen con nhap.
            chapter, _ = self._tao_chuong(
                novel=novel, owner_id=owner_id, title=chuong.title,
                content=chuong.content, order_index=idx,
                bao_nguoi_theo_doi=False)
            tao_ra.append(chapter)

        # 6) IMPORT RECORD — trach nhiem giai trinh, KHONG phai bang chung so huu.
        content_hash = hashlib.sha256(
            "\x1f".join(c.content for c in chuong_list).encode("utf-8")).hexdigest()
        record = self._import_records.create_record(ImportRecord(
            novel_id=novel.novel_id, importer_user_id=owner_id,
            rights_basis=rights_basis, source="authorized_upload",
            original_filename=filename,
            original_file_hash=raw_result.manifest["raw_sha256"],
            content_hash=content_hash,
        ))

        return AuthorizedImportResult(
            novel=novel, chapters=tao_ra, import_record=record,
            fandom_match_summary=fandom_summary,
            raw_archive_local_dir=raw_result.local_dir)

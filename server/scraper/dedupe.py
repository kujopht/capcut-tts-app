"""
Chong trung + resume cho Universal Story Scraper.

`source_fingerprint` la SHA256 cua canonical_url — CUNG triet ly voi
`video_import_id`/`episode_slot_id`/`trusted_source_id` da dung trong
`server/trusted_source_domain.py`: mot dinh danh TAT DINH tu chinh danh
tinh nguon, khong phai id ngau nhien do kho sinh ra — nen goi lai VOI CUNG
url luon ra CUNG mot dinh danh, du chay tren tien trinh/may nao.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from server.scraper.contract import canonicalize_url


def content_hash(clean_text: str) -> str:
    """sha256 cua noi dung DA lam sach — dung de phat hien REVISION (cung
    canonical_url, noi dung khac lan truoc), khong dung de dinh danh vi tri."""
    return hashlib.sha256(clean_text.encode("utf-8")).hexdigest()


def source_fingerprint(url: str) -> str:
    """sha256 cua canonical_url — dinh danh ON DINH cua CHINH VI TRI nguon,
    KHONG doi du noi dung thay doi hay chuong doi ten sau nay."""
    canon = canonicalize_url(url)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class ScrapeState:
    """
    Trang thai resume trong bo nho — lop ben vung THAT (Appwrite/dia) la
    viec cua noi goi; lop nay chi dinh nghia HINH DANG du lieu + logic
    quyet dinh, dung chung cho ca test va production.

    Khoa theo `source_fingerprint` (sha256 cua canonical_url), KHONG theo
    url tho — hai bien the URL (co/khong tracking param, http/https, co/
    khong dau `/` cuoi) tro ve CUNG mot ban ghi.
    """

    #: fingerprint -> {"canonical_url", "content_hash", "chapter_number",
    #: "status" ("ok" | "failed"), "revision_of" (fingerprint cu, chi co khi
    #: phat hien noi dung doi so voi lan truoc)}
    _rows: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get(self, canonical_url: str) -> Optional[Dict[str, Any]]:
        fp = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        return self._rows.get(fp)

    def record_success(self, url: str, *, content_hash_value: str,
                        chapter_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Ghi MOT chuong da xu ly xong. Neu url nay DA co ban ghi truoc do voi
        `content_hash` KHAC — day la REVISION (nguon sua lai chuong), KHONG
        BAO GIO am tham ghi de: giu lai ban ghi cu duoi `revision_of`, tra ve
        ban ghi MOI voi co `is_revision=True` de noi goi tu quyet dinh co
        nhap lai hay khong (chinh sach nhap lai KHONG thuoc lop nay).
        """
        canon = canonicalize_url(url)
        fp = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        cu = self._rows.get(fp)
        is_revision = bool(cu) and cu.get("content_hash") not in (None, content_hash_value) \
            and cu.get("status") == "ok"

        row = {
            "canonical_url": canon,
            "content_hash": content_hash_value,
            "chapter_number": chapter_number,
            "status": "ok",
            "is_revision": is_revision,
        }
        if is_revision:
            row["previous_content_hash"] = cu["content_hash"]
        self._rows[fp] = row
        return row

    def record_failure(self, url: str) -> None:
        canon = canonicalize_url(url)
        fp = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        cu = self._rows.get(fp) or {"canonical_url": canon}
        cu["status"] = "failed"
        self._rows[fp] = cu

    def record_skip(self, url: str) -> None:
        """
        Danh dau MOT url la "operator chu dong bo qua" — khac voi
        `record_failure` (loi ky thuat, se duoc `resume()` thu lai) va khac
        voi `record_success` (da xu ly xong). `StoryProvider.resume()` (xem
        `contract.py`) chi thu lai khi `status == "failed"`, nen mot ban ghi
        `"skipped"` tu dong bi loai khoi danh sach can lam o lan `plan()`
        sau — KHONG can sua `resume()`.
        """
        canon = canonicalize_url(url)
        fp = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        self._rows[fp] = {"canonical_url": canon, "status": "skipped"}

    def clear_skip(self, url: str) -> None:
        """Bo mot luot "bo qua" da danh dau truoc do, cho operator doi y —
        url nay tro lai dien duoc `resume()` de xuat o lan `plan()` ke tiep.
        CHI xoa khi ban ghi hien tai THAT SU la "skipped" — goi nham tren
        mot url dang "ok"/"failed" se khong lam mat du lieu cua trang thai
        do."""
        canon = canonicalize_url(url)
        fp = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        cu = self._rows.get(fp)
        if cu is not None and cu.get("status") == "skipped":
            del self._rows[fp]

    def to_json(self) -> str:
        """Tuan tu hoa DE LUU (Appwrite/dia) — noi goi tu chiu trach nhiem
        ben vung hoa, lop nay chi dinh dang."""
        return json.dumps(self._rows, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "ScrapeState":
        data = json.loads(raw) if raw else {}
        return cls(_rows=data)

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
from typing import Any, Dict, List, Optional

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
    #: CHI SO NGUOC content_hash -> tap canonical_url dang "ok" VOI hash do
    #: — Overnight ("memory/CPU characterization", O(N^2) hunt): TRUOC ban
    #: sua nay, `find_canonical_urls_by_content_hash` QUET TOAN BO `_rows`
    #: MOI LAN GOI, va no duoc goi MOT LAN CHO MOI CHUONG trong
    #: `bulk.py::drive_once` — do luong THAT (cProfile) xac nhan day la
    #: NGUYEN NHAN CHINH cua chi phi O(N^2) tren MOT dot dai (o 4000 chuong,
    #: rieng ham nay chiem ~3.7/9.2 giay tong thoi gian). Duy tri chi so nay
    #: TANG DAN (O(1) moi lan ghi) chuyen truy van tren thanh O(1)/O(k) voi
    #: k = so URL THAT SU cung hash (thuong rat nho, gan nhu luon la 0-1).
    _chi_so_theo_hash: Dict[str, set] = field(default_factory=dict)

    def get(self, canonical_url: str) -> Optional[Dict[str, Any]]:
        fp = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        return self._rows.get(fp)

    def _go_khoi_chi_so_hash_neu_can(self, cu: Optional[Dict[str, Any]]) -> None:
        """Neu ban ghi CU (truoc khi ghi de) dang o trang thai "ok" va co
        `content_hash`, go no khoi `_chi_so_theo_hash` — goi TRUOC khi
        chuyen trang thai/content_hash sang gia tri MOI (revision, that
        bai, hoac bo qua), tranh chi so giu THAM CHIEU CU/SAI."""
        if cu is None or cu.get("status") != "ok" or not cu.get("content_hash"):
            return
        tap = self._chi_so_theo_hash.get(cu["content_hash"])
        if tap is None:
            return
        tap.discard(cu["canonical_url"])
        if not tap:
            del self._chi_so_theo_hash[cu["content_hash"]]

    def find_canonical_urls_by_content_hash(
            self, content_hash_value: str, *, exclude_canonical: Optional[str] = None
    ) -> List[str]:
        """Phase 8 Story Harvester V3 ("POSSIBLE_DUPLICATE"): tra ve danh
        sach `canonical_url` (trang thai "ok") CO CUNG `content_hash_value`
        NHUNG khac `exclude_canonical` — dung de phat hien MOT chuong MOI
        (URL khac) co noi dung TRUNG HET voi mot chuong KHAC da co trong
        CUNG series (vd nguon liet ke cung mot chuong qua hai URL/slug
        khac nhau, hoac mot redirect chua duoc giai quyet dung). `exclude_canonical`
        LUON PHAI la canonical_url cua CHINH chuong dang kiem tra — thieu
        no, mot chuong DA co ban ghi cu (dang tu so sanh voi chinh no
        truoc khi ghi de) se tu bao "trung voi chinh minh"."""
        return [
            u for u in self._chi_so_theo_hash.get(content_hash_value, ())
            if u != exclude_canonical
        ]

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
        if is_revision or (cu is not None and cu.get("content_hash") != content_hash_value):
            self._go_khoi_chi_so_hash_neu_can(cu)
        self._rows[fp] = row
        self._chi_so_theo_hash.setdefault(content_hash_value, set()).add(canon)
        return row

    def record_failure(self, url: str) -> None:
        canon = canonicalize_url(url)
        fp = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        cu = self._rows.get(fp) or {"canonical_url": canon}
        self._go_khoi_chi_so_hash_neu_can(cu)
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
        self._go_khoi_chi_so_hash_neu_can(self._rows.get(fp))
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

    def known_urls(self, *, status: Optional[str] = None) -> list:
        """Tra ve TAT CA `canonical_url` da co ban ghi trong state — dung
        cho Phase 9 (Story Harvester V3: engine cap nhat gia tang) de phat
        hien chuong REMOVED (TUNG co ban ghi "ok" nhung khong con trong muc
        luc moi — xem `incremental.diff_toc`). Loc theo `status` neu duoc
        chi dinh (vd chi "ok", bo qua "failed"/"skipped")."""
        return [row["canonical_url"] for row in self._rows.values()
                if status is None or row.get("status") == status]

    def to_json(self) -> str:
        """Tuan tu hoa DE LUU (Appwrite/dia) — noi goi tu chiu trach nhiem
        ben vung hoa, lop nay chi dinh dang."""
        return json.dumps(self._rows, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "ScrapeState":
        data = json.loads(raw) if raw else {}
        return cls(_rows=data)

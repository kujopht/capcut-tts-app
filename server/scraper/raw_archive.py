"""
Raw archive spool — luu response THO (truoc normalize) truoc khi day len kho
archive lanh (Google Drive qua rclone, xem `scripts/rclone_archive_copy.py`).

Day la buoc CHUNG MINH PROVENANCE: moi lan acquisition that phai truy nguoc
lai duoc chinh xac response HTTP da nhan — doc lap voi `dedupe.py::content_hash`
(hash cua noi dung DA LAM SACH, dung de phat hien revision) va voi
`ScrapeRunItem.content_hash` (Task Publish Bridge — hash tai thoi diem duyet).
Ba hash nay CO CHU DICH khac nhau: raw archive giu nguyen response GOC de
doi soat phap ly/ky thuat sau nay, khong phai de dedupe hay publish.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from server.scraper.http_fetcher import FetchResult, HttpFetcher
from server.scraper.site_registry import lookup as site_lookup

MANIFEST_FILENAME = "manifest.json"

#: Goc tren Google Drive, dung chung voi `scripts/rclone_archive_copy.py`'s
#: docstring vi du. Ten remote (`fanfic-gdrive`) da duoc xac thuc san tren
#: may bang `rclone config` — module nay KHONG tu cau hinh OAuth, chi goi
#: rclone da san sang, dung nguyen tac "adapter khong giu credential".
DRIVE_ARCHIVE_REMOTE = "fanfic-gdrive:FanficWorld/archive/scraping/raw"

ARCHIVE_QUEUE_FILENAME = "archive_queue.jsonl"


def _archive_queue_path() -> Path:
    from server.config import get_settings

    return get_settings().var_dir / "archive" / ARCHIVE_QUEUE_FILENAME


def _append_to_queue(entry: dict) -> None:
    path = _archive_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _try_copy_to_drive(local_dir: Path, remote_path: str, timeout: int = 120) -> bool:
    try:
        proc = subprocess.run(
            ["rclone", "copy", str(local_dir), remote_path, "--checksum"],
            capture_output=True, timeout=timeout)
        return proc.returncode == 0
    except Exception:
        # rclone missing/misconfigured/timed out -- NEVER raise from here.
        # A failed archive push must not fail the acquisition it followed.
        return False


def queue_drive_archive(local_dir: Path, story_slug: str) -> None:
    """Best-effort, NON-BLOCKING push of one spooled chapter to Drive.

    Tries immediately in a background daemon thread so a slow/offline
    rclone never delays the caller (job creation, chapter write, mission
    completion). On failure, appends a retry entry to the local queue file
    instead of raising -- `drain_archive_queue()` (called every worker
    cycle, see `server/worker.py`) retries it later. Never blocks, never
    raises: archive is a side effect, not a gate on production content.
    """
    remote_path = f"{DRIVE_ARCHIVE_REMOTE}/{story_slug}"

    def _run() -> None:
        if not _try_copy_to_drive(local_dir, remote_path):
            _append_to_queue({
                "local_dir": str(local_dir), "remote_path": remote_path,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            })

    threading.Thread(target=_run, daemon=True, name="drive-archive").start()


def drain_archive_queue() -> dict:
    """Retry every pending queue entry ONCE. Re-queues whatever still fails.

    Called from the worker's own poll loop, in its own try block (same
    pattern as `main.drive_chapter_imports()` — a queue drain failing must
    not touch the TTS scan cycle next to it). Safe to call with an empty/
    missing queue (returns immediately, does nothing).
    """
    path = _archive_queue_path()
    if not path.is_file():
        return {"da_thu": 0, "thanh_cong": 0}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        path.unlink()
    except OSError:
        return {"da_thu": 0, "thanh_cong": 0}

    da_thu = 0
    thanh_cong = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        da_thu += 1
        if _try_copy_to_drive(Path(entry["local_dir"]), entry["remote_path"]):
            thanh_cong += 1
        else:
            _append_to_queue(entry)
    return {"da_thu": da_thu, "thanh_cong": thanh_cong}

#: Mau du lieu nhay cam CO CHU DICH GIU DON GIAN — day la mot GATE truoc khi
#: day noi dung THO ra ngoai (Google Drive), khong phai bo quet PII day du.
#: Khong import tu `scripts/ai_router_dispatch.py::SECRET_PATTERNS` — server/
#: khong duoc phep phu thuoc vao ma tang scripts/ (xem CLAUDE.md ve ranh gioi
#: backend), nen day la mot ban rieng, co chu dich, cho dung muc dich nay.
_SENSITIVE_PATTERNS = (
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-[A-Za-z0-9_-]{20,}", "OpenAI-style key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "dia chi email"),
    #: `(?<!\d)`/`(?!\d)` bat buoc token DUNG 9-10 chu so, khong duoc la mot
    #: doan cua chuoi so dai hon — thieu no, moi timestamp cache MediaWiki 14
    #: chu so (vd "20260827145508" o footer parser-cache cua chinh
    #: vi.wikisource.org) deu chua mot doan con khop "so dien thoai", bao
    #: dong gia lien tuc tren MOI trang MediaWiki. Phat hien qua chinh lan
    #: chay that dau tien cua RAW ARCHIVE gate, khong phai doan truoc.
    (r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)", "so dien thoai VN"),
)


class SensitiveContentDetected(RuntimeError):
    """Response THO khop mot mau du lieu nhay cam — CHAN dua vao spool, khong
    tu y redact roi van tiep tuc. Nguoi van hanh phai tu xem lai nguon."""


def scan_for_sensitive_data(text: str) -> Optional[str]:
    """Tra ve NHAN cua mau dau tien khop, hoac `None` neu sach."""
    for pattern, label in _SENSITIVE_PATTERNS:
        if re.search(pattern, text):
            return label
    return None


@dataclass
class RawArchiveResult:
    local_dir: Path
    manifest_path: Path
    raw_path: Path
    manifest: dict = field(default_factory=dict)


def _slug_for(url: str) -> str:
    """Tat dinh tu URL — goi lai voi CUNG url luon ra CUNG thu muc con, dung
    quy uoc voi `dedupe.py::source_fingerprint` (sha256 cua canonical url)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _raw_extension(content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if "json" in ct:
        return "json"
    return "html"


def fetch_and_spool_raw(
        url: str, *, spool_root: Path, fetcher: Optional[Any] = None,
        adapter_identity: str = "") -> RawArchiveResult:
    """Tai MOT url that qua `HttpFetcher` (SSRF/robots.txt/rate-limit da co
    san trong `http_fetcher.py`, khong lap lai o day), luu response THO +
    `manifest.json` vao MOT thu muc con moi cua `spool_root`.

    `fetcher` nhan bat ky doi tuong nao co `.fetch(url) -> FetchResult` —
    `HttpFetcher` that hoac `FixtureFetcher` (test). Nem
    `SensitiveContentDetected` va KHONG ghi gi xuong dia neu quet thay du
    lieu nhay cam trong response — fail-closed, khong am tham redact."""
    active_fetcher = fetcher if fetcher is not None else HttpFetcher()
    result: FetchResult = active_fetcher.fetch(url)

    hit = scan_for_sensitive_data(result.text)
    if hit:
        raise SensitiveContentDetected(
            f"Phat hien du lieu nhay cam ({hit}) trong response tu {url} — "
            f"tu choi dua vao raw archive spool.")

    cfg = site_lookup(url)
    raw_bytes = result.text.encode("utf-8")
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    slug = _slug_for(result.final_url)
    local_dir = spool_root / slug
    local_dir.mkdir(parents=True, exist_ok=True)
    ext = _raw_extension(result.content_type)
    raw_path = local_dir / f"raw.{ext}"
    raw_path.write_bytes(raw_bytes)

    manifest = {
        "requested_url": url,
        "final_url": result.final_url,
        "source_domain": cfg.domain if cfg else "",
        "adapter_identity": adapter_identity or (cfg.domain if cfg else "generic"),
        "site_config_verified_via": cfg.verified_via if cfg else "",
        "status_code": result.status_code,
        "content_type": result.content_type,
        "raw_file": raw_path.name,
        "raw_bytes": len(raw_bytes),
        "raw_sha256": raw_sha256,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetcher": f"{type(active_fetcher).__module__}.{type(active_fetcher).__qualname__}",
        "sensitive_scan": {
            "status": "clean",
            "patterns_checked": len(_SENSITIVE_PATTERNS),
        },
    }
    manifest_path = local_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    queue_drive_archive(local_dir, spool_root.name)
    return RawArchiveResult(
        local_dir=local_dir, manifest_path=manifest_path, raw_path=raw_path,
        manifest=manifest)


def spool_uploaded_raw(
        data: bytes, *, spool_root: Path, filename: str,
        importer_user_id: str, scan_text: Optional[str] = None) -> RawArchiveResult:
    """Nhu `fetch_and_spool_raw` nhung cho FILE NGUOI DUNG TAI LEN (Authorized
    Import), khong phai mot URL fetch — khong co `FetchResult`/HTTP, nen
    manifest ghi lai danh tinh nguoi nhap + ten tep goc thay vi final_url/
    status_code.

    `scan_text`: van ban DA GIAI MA/TRICH XUAT dung de quet du lieu nhay
    cam — dinh dang nhi phan (EPUB/DOCX/ZIP nen) KHONG the quet truc tiep
    tren byte tho (se la rac nhi phan, khong phai loi regex co y nghia).
    `None` (mac dinh) = BO QUA quet, ghi ro `sensitive_scan.status =
    "skipped_binary"` trong manifest — KHONG bao gio bao "clean" cho mot
    thu chua thuc su quet."""
    if scan_text is not None:
        hit = scan_for_sensitive_data(scan_text)
        if hit:
            raise SensitiveContentDetected(
                f"Phat hien du lieu nhay cam ({hit}) trong tep tai len "
                f"{filename!r} — tu choi dua vao raw archive spool.")

    raw_sha256 = hashlib.sha256(data).hexdigest()
    slug = raw_sha256[:16]
    local_dir = spool_root / slug
    local_dir.mkdir(parents=True, exist_ok=True)
    raw_path = local_dir / (filename or "upload.bin")
    raw_path.write_bytes(data)

    manifest = {
        "importer_user_id": importer_user_id,
        "original_filename": filename,
        "raw_file": raw_path.name,
        "raw_bytes": len(data),
        "raw_sha256": raw_sha256,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "source": "authorized_upload",
        "sensitive_scan": (
            {"status": "clean", "patterns_checked": len(_SENSITIVE_PATTERNS)}
            if scan_text is not None
            else {"status": "skipped_binary", "patterns_checked": 0}
        ),
    }
    manifest_path = local_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    queue_drive_archive(local_dir, spool_root.name)
    return RawArchiveResult(
        local_dir=local_dir, manifest_path=manifest_path, raw_path=raw_path,
        manifest=manifest)

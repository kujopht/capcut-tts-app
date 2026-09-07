"""Luu tru ben vung len Google Drive — GUONG, khong phai duong phuc vu.

Phan vai, va phan vai nay la toan bo thiet ke:

    R2 + Appwrite = duong PHUC VU. Day la su that ma nguoi dung doc/nghe.
    Google Drive  = ban SAO ben vung. Khong ai doc tu day.

Hai he qua truc tiep, va ca hai deu bat buoc:

1. **Mot su co Drive KHONG BAO GIO duoc lam hong mot object R2 hop le.**
   Module nay chi COPY len Drive. No khong xoa, khong sync, khong move,
   khong purge, va khong bao gio cham vao R2. Khong co duong ma nao o day
   co the lam mat mot ban dang phuc vu — ke ca khi Drive tra loi rac.

2. **Drive hong thi tac pham VAN hop le.** Trang thai chuyen sang
   `ARCHIVE_PENDING` va duoc thu lai vong sau. Day la mot hang doi, khong
   phai mot cong.

Dung DUNG mot ten remote chinh tac `fanfic-gdrive:` — cung ten ma
`server/scraper/raw_archive.py` va `scripts/chinese_media_pipeline.py` dang
dung. Mot ten thu hai se lang le tach kho luu tru lam doi.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Ten remote CHINH TAC. Giu dong bo voi `raw_archive.DRIVE_ARCHIVE_REMOTE`
#: va `chinese_media_pipeline.DRIVE_FINAL_MEDIA_REMOTE` — cung mot tai khoan,
#: cung mot goc.
CANONICAL_REMOTE = "fanfic-gdrive"
CANONICAL_ROOT = "FanficWorld/archive"

#: Goc cua rieng farmer, nam TRONG cung cay archive chinh tac.
FARMER_SUBTREE = "farmer"

ENV_REMOTE = "FARMER_DRIVE_REMOTE"
ENV_ENABLED = "FARMER_DRIVE_ARCHIVE"

#: Trang thai luu tru cua MOT tac pham.
ARCHIVE_PENDING = "ARCHIVE_PENDING"
ARCHIVE_DONE = "ARCHIVE_DONE"
ARCHIVE_DISABLED = "ARCHIVE_DISABLED"
ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"


class DriveUnavailable(RuntimeError):
    """rclone thieu/chua cau hinh/token het han. KHONG phai loi cua tac pham."""


@dataclass
class ArchiveOutcome:
    status: str
    remote_path: str = ""
    file_id: str = ""
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "remote_path": self.remote_path,
                "file_id": self.file_id, "detail": self.detail[:300]}


def remote_name() -> str:
    return (os.environ.get(ENV_REMOTE) or "").strip() or CANONICAL_REMOTE


def enabled() -> bool:
    """Mac dinh BAT. Dat `FARMER_DRIVE_ARCHIVE=0` de tat han."""
    return (os.environ.get(ENV_ENABLED) or "1").strip() != "0"


def farmer_remote_path(*parts: str) -> str:
    duoi = "/".join(p.strip("/") for p in parts if p)
    goc = f"{remote_name()}:{CANONICAL_ROOT}/{FARMER_SUBTREE}"
    return f"{goc}/{duoi}" if duoi else goc


def _rclone() -> Optional[str]:
    return shutil.which("rclone")


def probe() -> Dict[str, Any]:
    """Tinh trang Drive — CHI DOC, khong bao gio ghi.

    Dung cho `status.json` (yeu cau B8) va cho phep kiem truoc khi luu tru.
    Khong in token: chi goi `lsd` tren goc va doc ma thoat.
    """
    ket_qua: Dict[str, Any] = {
        "remote": remote_name(),
        "root": f"{remote_name()}:{CANONICAL_ROOT}/{FARMER_SUBTREE}",
        "enabled": enabled(),
        "rclone_installed": False,
        "reachable": False,
        "status": ARCHIVE_UNAVAILABLE,
        "detail": "",
    }
    if not enabled():
        ket_qua["status"] = ARCHIVE_DISABLED
        ket_qua["detail"] = f"tat qua {ENV_ENABLED}=0"
        return ket_qua

    binary = _rclone()
    if not binary:
        ket_qua["detail"] = ("khong tim thay rclone tren may nay — luu tru se "
                             "xep hang ARCHIVE_PENDING")
        return ket_qua
    ket_qua["rclone_installed"] = True

    try:
        proc = subprocess.run(
            [binary, "lsd", f"{remote_name()}:", "--max-depth", "1"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace")
    except Exception as exc:                                    # noqa: BLE001
        ket_qua["detail"] = f"{type(exc).__name__}: {exc}"
        return ket_qua

    if proc.returncode == 0:
        ket_qua["reachable"] = True
        ket_qua["status"] = ARCHIVE_DONE
        return ket_qua

    err = (proc.stderr or "").strip()
    # `invalid_grant` = token het han/bi thu hoi. Goi ten no ro rang: no can
    # mot lan `rclone config reconnect` CUA NGUOI VAN HANH, khong phai mot lan
    # thu lai.
    if "invalid_grant" in err or "token" in err.lower():
        ket_qua["detail"] = ("xac thuc Drive khong con hieu luc (invalid_grant) "
                             "— can nguoi van hanh chay `rclone config "
                             "reconnect` mot lan")
    else:
        ket_qua["detail"] = err[:300]
    return ket_qua


def archive_file(local_path: Path, *, work_key: str,
                 timeout: int = 300) -> ArchiveOutcome:
    """COPY mot tep len Drive. Khong bao gio xoa/sync/move.

    Tra `ARCHIVE_PENDING` khi khong luu tru duoc — KHONG nem, va tuyet doi
    khong dong toi ban tren R2. Tac pham van hop le; chi ban sao ben vung la
    con thieu, va no se duoc thu lai.
    """
    if not enabled():
        return ArchiveOutcome(ARCHIVE_DISABLED, detail=f"{ENV_ENABLED}=0")

    if not local_path.is_file():
        return ArchiveOutcome(ARCHIVE_PENDING,
                              detail=f"khong thay tep cuc bo: {local_path}")

    binary = _rclone()
    if not binary:
        return ArchiveOutcome(
            ARCHIVE_PENDING,
            detail="rclone chua cai tren may nay — se thu lai vong sau")

    dich = farmer_remote_path(work_key)
    try:
        proc = subprocess.run(
            # `copy` — CO Y khong phai `sync`/`move`. `sync` se xoa o dich
            # nhung gi khong con o nguon, va do la cach mot loi cuc bo bien
            # thanh mat du lieu tren ban luu tru.
            [binary, "copy", str(local_path), dich, "--checksum"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace")
    except Exception as exc:                                    # noqa: BLE001
        return ArchiveOutcome(ARCHIVE_PENDING,
                              detail=f"{type(exc).__name__}: {exc}")

    if proc.returncode != 0:
        return ArchiveOutcome(ARCHIVE_PENDING, remote_path=dich,
                              detail=(proc.stderr or "").strip()[:300])

    return ArchiveOutcome(ARCHIVE_DONE, remote_path=dich,
                          file_id=_file_id(binary, dich, local_path.name))


def _file_id(binary: str, remote_dir: str, filename: str) -> str:
    """Doc ID Drive that tu `lsjson`. Rong khi khong lay duoc — day la thong
    tin them, khong phai dieu kien de coi la luu tru thanh cong."""
    try:
        proc = subprocess.run(
            [binary, "lsjson", remote_dir], capture_output=True, text=True,
            timeout=60, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return ""
        for muc in json.loads(proc.stdout or "[]"):
            if muc.get("Name") == filename:
                return str(muc.get("ID", ""))
    except Exception:                                           # noqa: BLE001
        return ""
    return ""

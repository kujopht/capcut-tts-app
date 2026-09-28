"""
Nap toa do + bi mat STAGING — KHONG BAO GIO in gia tri.

Nguon, theo thu tu uu tien (bien da co trong moi truong THANG tep):
  1. bien moi truong `FAS_STAGING_*` / `SENTRY_READONLY_TOKEN`;
  2. tep ghi chu cua chu du an, duong dan trong `FAS_STAGING_SECRETS_FILE` — moi dong
     `TEN=gia_tri` hoac `TEN: gia_tri`, dong `#` la chu thich. Tep nay nam NGOAI kho
     (vd thu muc Downloads cua chu du an) va khong bao gio duoc commit.

Chu y: ham nay KHONG doc `APPWRITE_*` — do la ten bien cua production/Render. Dung nham
chung o day la mot duong trot sang production chi vi mot bien con sot trong shell.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

BIEN_TEP = "FAS_STAGING_SECRETS_FILE"
DATABASE_MAC_DINH = "fanfic_staging"

#: Ten chinh tac -> truong cua `CauHinhStaging`.
TEN_CHINH = {
    "FAS_STAGING_APPWRITE_ENDPOINT": "endpoint",
    "FAS_STAGING_APPWRITE_PROJECT_ID": "project_id",
    "FAS_STAGING_APPWRITE_API_KEY": "api_key",
    "FAS_STAGING_APPWRITE_SCHEMA_API_KEY": "schema_api_key",
    "FAS_STAGING_APPWRITE_DATABASE_ID": "database_id",
    "SENTRY_READONLY_TOKEN": "sentry_token",
}

#: Nhan ma chu du an da dung trong tep ghi chu (so khop khong phan biet hoa/thuong).
BI_DANH = {
    "sentrytoken": "SENTRY_READONLY_TOKEN",
    "sentry_token": "SENTRY_READONLY_TOKEN",
    "sentry_readonly_token": "SENTRY_READONLY_TOKEN",
}

_DONG = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_ .-]{0,60}?)\s*[:=]\s*(.*?)\s*$")


class ThieuCauHinh(RuntimeError):
    """Thieu mot toa do/bi mat bat buoc — thong diep CHI chua TEN bien."""


@dataclass(frozen=True)
class CauHinhStaging:
    endpoint: str
    project_id: str
    database_id: str
    api_key: str = field(repr=False)
    schema_api_key: str = field(repr=False, default="")
    sentry_token: str = field(repr=False, default="")
    nguon: str = ""

    @property
    def khoa_schema(self) -> str:
        """Khoa cho thao tac SCHEMA — khoa rieng neu co, khong thi khoa runtime."""
        return self.schema_api_key or self.api_key

    def cac_bi_mat(self) -> List[str]:
        return [v for v in (self.api_key, self.schema_api_key, self.sentry_token) if v]

    def an(self, van_ban: str) -> str:
        """Che MOI gia tri bi mat da nap khoi mot chuoi truoc khi in/ghi."""
        ra = str(van_ban)
        for v in sorted(self.cac_bi_mat(), key=len, reverse=True):
            ra = ra.replace(v, "<an>")
        return ra


def _chinh_tac(nhan: str) -> Optional[str]:
    n = nhan.strip()
    if n.upper() in TEN_CHINH:
        return n.upper()
    return BI_DANH.get(n.lower().replace(" ", "_"))


def doc_tep_ghi_chu(duong: Path) -> Dict[str, str]:
    """Doc tep ghi chu, tra {TEN_CHINH: gia_tri}. Dong khong nhan ra bi BO QUA (khong in)."""
    ra: Dict[str, str] = {}
    for dong in Path(duong).read_text(encoding="utf-8-sig").splitlines():
        s = dong.strip()
        if not s or s.startswith("#"):
            continue
        m = _DONG.match(s)
        if not m:
            continue
        ten = _chinh_tac(m.group(1))
        if ten:
            ra[ten] = m.group(2).strip().strip('"').strip("'")
    return ra


def nap(env: Optional[Mapping[str, str]] = None) -> CauHinhStaging:
    env = os.environ if env is None else env
    gia: Dict[str, str] = {}
    nguon = "moi_truong"
    tep = (env.get(BIEN_TEP) or "").strip()
    if tep:
        p = Path(tep)
        if not p.is_file():
            raise ThieuCauHinh(f"{BIEN_TEP} trỏ tới một tệp không tồn tại.")
        gia.update(doc_tep_ghi_chu(p))
        nguon = f"tep:{p.name}"
    for ten in TEN_CHINH:
        v = (env.get(ten) or "").strip()
        if v:
            gia[ten] = v
    thieu = [t for t in ("FAS_STAGING_APPWRITE_ENDPOINT", "FAS_STAGING_APPWRITE_PROJECT_ID",
                         "FAS_STAGING_APPWRITE_API_KEY") if not gia.get(t)]
    if thieu:
        raise ThieuCauHinh("Thiếu cấu hình staging: " + ", ".join(thieu)
                           + f" (đặt biến môi trường hoặc {BIEN_TEP}).")
    return CauHinhStaging(
        endpoint=gia["FAS_STAGING_APPWRITE_ENDPOINT"].rstrip("/"),
        project_id=gia["FAS_STAGING_APPWRITE_PROJECT_ID"],
        database_id=gia.get("FAS_STAGING_APPWRITE_DATABASE_ID") or DATABASE_MAC_DINH,
        api_key=gia["FAS_STAGING_APPWRITE_API_KEY"],
        schema_api_key=gia.get("FAS_STAGING_APPWRITE_SCHEMA_API_KEY", ""),
        sentry_token=gia.get("SENTRY_READONLY_TOKEN", ""),
        nguon=nguon,
    )

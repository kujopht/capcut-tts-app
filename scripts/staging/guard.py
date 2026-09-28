"""
Guard CUNG cho moi thao tac tren Appwrite STAGING. FAIL CLOSED o moi nhanh.

Ba lop, lop sau khong thay lop truoc:

1. `kiem_dich()` — KHONG goi mang. Dich phai la CHINH XAC `DICH_DUYET` (endpoint + project ID
   chu du an da duyet 2026-09-28), host phai la Appwrite Cloud, KHONG BAO GIO la mot host
   `fanfic.world`, va khong trung toa do production nao trong nguon su that duy nhat
   `scripts/ops/cutover_target.py` (lop kiem nguoc `khang_dinh_khong_phai_production`).
2. `xac_minh_song()` — CHI DOC, chay TRUOC moi thao tac ghi: phien ban tra ve, khoa that su
   thuoc project nay (`GET /databases` = 200), va MOI tai khoan trong project la tai khoan
   TONG HOP (`@example.test`). Mot project co nguoi dung that thi khong phai staging — dung.
3. `moi_truong_con()` — tien trinh con chi nhan `APPWRITE_*` = toa do staging, `FAS_ENV_FILE`
   RONG (khong nap `server/.env` nao) va KHONG thua ke bien nao khac cua shell goi.

Thay doi `DICH_DUYET` = thay doi quyet dinh cua chu du an: phai co duyet moi, ghi vao
`docs/staging/APPWRITE_STAGING.md`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

from scripts.ops.cutover_target import (
    PROD_APPWRITE_DATABASE_ID,
    PROD_APPWRITE_ENDPOINT,
    PROD_APPWRITE_PROJECT_ID,
    CutoverRefused,
    khang_dinh_khong_phai_production,
)
from scripts.staging.bi_mat import CauHinhStaging
from server.appwrite_tablesdb_compat import STAGING_ENDPOINT, STAGING_PROJECT_ID, STAGING_PROJECT_NAME


@dataclass(frozen=True)
class DichDuyet:
    endpoint: str
    project_id: str
    ten_project: str
    duyet_ngay: str


#: DICH DUY NHAT duoc phep. Project ID do Appwrite tu sinh (ten hien thi: `fanfic-staging`);
#: chu du an duyet ghim CHINH XAC ID nay ngay 2026-09-28 sau khi xac minh chi doc: Appwrite
#: Cloud 2.3.0 vung Singapore, 0 database / 0 nguoi dung / 0 bucket. Gia tri lay tu MOT nguon
#: (`server/appwrite_tablesdb_compat.py`) — lop dich staging va guard khong the lech nhau.
DICH_DUYET = DichDuyet(
    endpoint=STAGING_ENDPOINT,
    project_id=STAGING_PROJECT_ID,
    ten_project=STAGING_PROJECT_NAME,
    duyet_ngay="2026-09-28",
)

#: Mien TONG HOP cho moi tai khoan staging (RFC 2606 — khong bao gio la hop thu that).
MIEN_TONG_HOP = "@example.test"
#: Tran so tai khoan `xac_minh_song` chiu doc het (phan trang). Vuot -> dung (fail-closed).
TRAN_KIEM_NGUOI_DUNG = 5000

_DB_ID = re.compile(r"[a-z][a-z0-9_]{0,35}")


class DichBiTuChoi(RuntimeError):
    """Guard tu choi. Thong diep KHONG BAO GIO chua bi mat."""


def kiem_dich(cfg: CauHinhStaging, env: Optional[Mapping[str, str]] = None) -> None:
    env = os.environ if env is None else env
    endpoint = (cfg.endpoint or "").strip().rstrip("/")
    u = urlparse(endpoint)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        raise DichBiTuChoi("Endpoint staging phải là https.")
    if host == "fanfic.world" or host.endswith(".fanfic.world"):
        raise DichBiTuChoi(f"Host {host!r} thuộc fanfic.world — đó là hạ tầng production, không phải staging.")
    if not host.endswith(".cloud.appwrite.io"):
        raise DichBiTuChoi(f"Host {host!r} không phải Appwrite Cloud — staging đã duyệt chỉ nằm trên Appwrite Cloud.")
    if endpoint != DICH_DUYET.endpoint:
        raise DichBiTuChoi(f"Endpoint {endpoint!r} khác endpoint đã duyệt {DICH_DUYET.endpoint!r}.")
    if cfg.project_id != DICH_DUYET.project_id:
        raise DichBiTuChoi(
            f"Project {cfg.project_id!r} khác project staging đã duyệt {DICH_DUYET.project_id!r} "
            f"({DICH_DUYET.ten_project}).")
    if not _DB_ID.fullmatch(cfg.database_id or ""):
        raise DichBiTuChoi(f"Database id {cfg.database_id!r} không hợp lệ.")
    if (endpoint == PROD_APPWRITE_ENDPOINT.rstrip("/") or cfg.project_id == PROD_APPWRITE_PROJECT_ID
            or cfg.database_id == PROD_APPWRITE_DATABASE_ID):
        raise DichBiTuChoi("Một toạ độ trùng production trong scripts/ops/cutover_target.py.")
    if (env.get("FAS_ENV") or "").strip().lower() == "production":
        raise DichBiTuChoi("Tiến trình gọi đang có FAS_ENV=production — không chạy công cụ staging từ đó.")
    try:
        khang_dinh_khong_phai_production({"APPWRITE_ENDPOINT": endpoint, "APPWRITE_PROJECT_ID": cfg.project_id,
                                          "APPWRITE_DATABASE_ID": cfg.database_id})
    except CutoverRefused as exc:
        raise DichBiTuChoi(f"Lớp kiểm ngược production từ chối: {exc}") from exc


def _headers(cfg: CauHinhStaging, khoa: Optional[str] = None) -> Dict[str, str]:
    return {"X-Appwrite-Project": cfg.project_id, "X-Appwrite-Key": khoa or cfg.api_key,
            "Content-Type": "application/json", "User-Agent": "fanfic-staging-tools/1"}


def goi(cfg: CauHinhStaging, method: str, path: str, *, json: Any = None, khoa: Optional[str] = None,
        timeout: float = 30.0, client: Any = None):
    """MOT request toi staging (kiem dich TRUOC). Tra `(status, body)`; body da qua `cfg.an`
    khi la chuoi loi — khong bao gio tra nguyen van body loi cua Appwrite."""
    kiem_dich(cfg)
    import httpx

    c = client or httpx
    r = c.request(method, f"{cfg.endpoint}{path}", headers=_headers(cfg, khoa), json=json, timeout=timeout)
    try:
        body = r.json() if r.content else None
    except ValueError:
        body = None
    if r.status_code >= 400:
        msg = body.get("message") if isinstance(body, dict) else ""
        return r.status_code, {"message": cfg.an(str(msg or ""))[:300], "type": (body or {}).get("type")
                               if isinstance(body, dict) else None}
    return r.status_code, body


def _json_query(method: str, values: List[Any]) -> str:
    import json as _j

    return _j.dumps({"method": method, "values": values}, separators=(",", ":"))


def xac_minh_song(cfg: CauHinhStaging, client: Any = None) -> Dict[str, Any]:
    """CHI DOC. Tra bao cao danh tinh; nem `DichBiTuChoi` neu bat ky dieu kien nao khong dat."""
    kiem_dich(cfg)
    import httpx

    c = client or httpx
    r = c.get(f"{cfg.endpoint}/health/version", timeout=20.0)
    if r.status_code != 200:
        raise DichBiTuChoi(f"GET /health/version trả {r.status_code}.")
    phien_ban = (r.json() or {}).get("version")

    st, body = goi(cfg, "GET", "/databases", client=client)
    if st != 200:
        raise DichBiTuChoi(f"Khoá không đọc được database của project này (HTTP {st}): {(body or {}).get('message')}")
    databases = [d.get("$id") for d in (body or {}).get("databases", [])]

    from urllib.parse import quote

    # DOC HET moi tai khoan (phan trang) roi moi ket luan. Ban dau chi doc MOT trang 100 va tu choi khi
    # `total > 100` — dung la fail-closed, nhung sau vai lan chay test song (tai khoan tong hop moi lan)
    # CA test lan `reset` (cong cu don duy nhat) deu bi khoa chet (do that 2026-09-28: 101 tai khoan, 0
    # that). Van fail-closed: co MOT tai khoan khong tong hop, hoac vuot tran kiem -> dung.
    tong, that, da_xem, con_tro = 0, [], 0, None
    while True:
        qs = [_json_query("limit", [100])] + ([_json_query("cursorAfter", [con_tro])] if con_tro else [])
        st, body = goi(cfg, "GET", "/users?" + "&".join("queries[]=" + quote(q) for q in qs), client=client)
        if st != 200:
            raise DichBiTuChoi(f"Khoá không đọc được danh sách người dùng (HTTP {st}) — không xác minh được "
                               "project không có dữ liệu thật.")
        tong = int((body or {}).get("total") or 0)
        trang = (body or {}).get("users", [])
        that += [u for u in trang if not str(u.get("email") or "").lower().endswith(MIEN_TONG_HOP)]
        da_xem += len(trang)
        if not trang or da_xem >= tong:
            break
        if da_xem >= TRAN_KIEM_NGUOI_DUNG:
            raise DichBiTuChoi(f"Project có hơn {TRAN_KIEM_NGUOI_DUNG} tài khoản — vượt trần kiểm; dọn bằng "
                               "Console rồi chạy lại.")
        con_tro = trang[-1].get("$id")
    if that or da_xem < tong:
        raise DichBiTuChoi(
            f"Project có {tong} tài khoản, trong đó {len(that)} KHÔNG phải tài khoản tổng hợp "
            f"({MIEN_TONG_HOP}) (đã kiểm {da_xem}). Staging chỉ được chứa dữ liệu tổng hợp — dừng.")
    return {"endpoint": cfg.endpoint, "project_id": cfg.project_id, "database_id": cfg.database_id,
            "appwrite_version": phien_ban, "databases": databases, "users_total": tong,
            "users_tong_hop": tong - len(that)}


#: Bien he thong GIU LAI cho tien trinh con (khong phai cau hinh ung dung).
_GIU = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA",
        "LOCALAPPDATA", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def moi_truong_con(cfg: CauHinhStaging, *, schema: bool = False,
                   them: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Moi truong TOI THIEU cho tien trinh con tro vao staging. KHONG thua ke `APPWRITE_*`,
    `FAS_*`, `R2_*`, `SENTRY_*`... cua shell goi."""
    kiem_dich(cfg)
    env = {k: os.environ[k] for k in _GIU if os.environ.get(k)}
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "FAS_ENV_FILE": "",               # chuoi RONG = khong nap tep env nao
        "FAS_ENV": "staging",
        # Bat TUONG MINH lop dich Databases->TablesDB (Cloud 2.3) — no tu kiem lai dich.
        "APPWRITE_ENV": "staging",
        "FAS_INLINE_WORKER": "false",
        "FAS_CORS_ORIGINS": "http://localhost:3000",
        "DATA_BACKEND": "appwrite",
        "STORAGE_BACKEND": "local",
        "APPWRITE_ENDPOINT": cfg.endpoint,
        "APPWRITE_PROJECT_ID": cfg.project_id,
        "APPWRITE_DATABASE_ID": cfg.database_id,
        "APPWRITE_API_KEY": cfg.api_key,
    })
    if schema:
        env["APPWRITE_SCHEMA_API_KEY"] = cfg.khoa_schema
    if them:
        env.update(them)
    # Lop cuoi: chinh moi truong se dua cho tien trinh con cung khong duoc tro vao production.
    try:
        khang_dinh_khong_phai_production(env)
    except CutoverRefused as exc:
        raise DichBiTuChoi(f"Môi trường tiến trình con trỏ vào production: {exc}") from exc
    return env

"""
Lop dich API Databases (kieu CU) -> TablesDB — CHI CHO Appwrite STAGING (Appwrite Cloud 2.3).

VI SAO CO MODULE NAY (do that 2026-09-28): production la Appwrite 1.9.6 tu luu tru, va toan
bo backend doc/ghi qua API Databases kieu cu (`/v1/databases/{db}/collections/{c}/documents`).
Project staging `fanfic-staging` tren Appwrite Cloud 2.3.0 chi cap duoc scope TablesDB
(`tables.*`, `columns.*`, `rows.*`) — API cu da bi deprecate tu 1.8 va khoa tao tren 2.x khong
con scope `collections.*`/`documents.*` (moi request cu tra 401 "missing scopes"). Chu du an
chon: GIU NGUYEN duong production, dich RIENG cho staging de test tich hop #229/#231 tren Cloud.

BAT KHI VA CHI KHI (xem `can_kich_hoat`):
  * `APPWRITE_ENV=staging` — va khi do project + endpoint PHAI la dung `STAGING_*` ben duoi,
    khong thi TU CHOI KHOI DONG (ConfigError), ke ca/nhat la khi do la project production;
  * HOAC project ID trung CHINH XAC `STAGING_PROJECT_ID` (khi do endpoint cung phai khop).
Production (project khac, khong co `APPWRITE_ENV=staging`) KHONG bao gio cai lop dich: ham
tra False va khong cham vao `httpx`.

Them mot lop nua o TUNG request: chi dich request co URL bat dau bang `STAGING_ENDPOINT` VA
header `X-Appwrite-Project` bang dung `STAGING_PROJECT_ID`. Moi request khac di nguyen ven.

Anh xa (duong + than + phan hoi; tai lieu REST TablesDB):
  /databases[/{db}]                     -> /tablesdb[/{db}]
  .../collections[/{c}]                 -> .../tables[/{c}]       collectionId->tableId,
                                                                   documentSecurity->rowSecurity
  .../collections/{c}/attributes...     -> .../tables/{c}/columns...
  .../collections/{c}/indexes...        -> .../tables/{c}/indexes  attributes->columns (than + ket qua)
  .../collections/{c}/documents...      -> .../tables/{c}/rows...  documentId->rowId, documents->rows
Phan hoi dich NGUOC lai (rows->documents, columns->attributes, rowSecurity->documentSecurity,
`$tableId`->`$collectionId`, loai loi row_/table_/column_ -> document_/collection_/attribute_) de
ma hien co doc dung nhu tren 1.9.6. Transaction (`/tablesdb/transactions`) da la API moi — di
thang, khong dich.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

#: Project staging DA DUYET (chu du an, 2026-09-28) — ten hien thi `fanfic-staging`. Nguon su
#: that duy nhat: `scripts/staging/guard.py` doc tu day.
STAGING_PROJECT_ID = "6ab9f4fa0036791d13d1"
STAGING_ENDPOINT = "https://sgp.cloud.appwrite.io/v1"
STAGING_PROJECT_NAME = "fanfic-staging"
BIEN_BAT = "APPWRITE_ENV"


class LopDichStagingBiTuChoi(RuntimeError):
    """Cau hinh bat lop dich staging SAI dich — tien trinh phai CHET luc khoi dong."""


def _chuan(ep: str) -> str:
    return (ep or "").strip().rstrip("/")


def can_kich_hoat(project_id: str, endpoint: str, environment: str = "",
                  env: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    pid = (project_id or "").strip()
    ep = _chuan(endpoint)
    bat_ro = (env.get(BIEN_BAT) or "").strip().lower() == "staging"
    if bat_ro or pid == STAGING_PROJECT_ID:
        if pid != STAGING_PROJECT_ID or ep != STAGING_ENDPOINT:
            raise LopDichStagingBiTuChoi(
                f"{BIEN_BAT}=staging (hoặc project staging) nhưng đích là project {pid!r} @ {ep!r} — "
                f"lớp dịch staging CHỈ được bật cho {STAGING_PROJECT_NAME} ({STAGING_PROJECT_ID}). "
                "Từ chối khởi động.")
        if (environment or "").strip().lower() == "production":
            raise LopDichStagingBiTuChoi("FAS_ENV=production cùng lớp dịch staging — từ chối khởi động.")
        return True
    return False


# ------------------------------------------------------------------ dich yeu cau

_DUONG = re.compile(r"^/databases(?P<duoi>/.*)?$")


def dich_duong(path: str) -> Optional[Tuple[str, str]]:
    """`/databases/...` -> (`/tablesdb/...`, loai). None = khong phai API Databases cu."""
    m = _DUONG.match(path)
    if not m:
        return None
    phan = path.split("/")  # ['', 'databases', db, 'collections', c, 'documents'|'attributes'|'indexes', ...]
    phan[1] = "tablesdb"
    loai = "database"
    if len(phan) > 3 and phan[3] == "collections":
        phan[3] = "tables"
        loai = "collection" if len(phan) > 4 else "collections"
        if len(phan) > 5:
            if phan[5] == "documents":
                phan[5] = "rows"
                loai = "document" if len(phan) > 6 else "documents"
            elif phan[5] == "attributes":
                phan[5] = "columns"
                loai = "attribute"
            elif phan[5] == "indexes":
                loai = "index"
    elif len(phan) == 2:
        loai = "databases"
    return "/".join(phan), loai


_DOI_KHOA_YEU_CAU = {"collectionId": "tableId", "documentId": "rowId", "documentSecurity": "rowSecurity",
                     "relatedCollection": "relatedTable"}


def dich_than_yeu_cau(body: Any, loai: str) -> Any:
    if not isinstance(body, dict):
        return body
    ra = {_DOI_KHOA_YEU_CAU.get(k, k): v for k, v in body.items()}
    if loai == "index" and "attributes" in ra:
        ra["columns"] = ra.pop("attributes")
    if loai in ("documents",) and "documents" in ra:
        ra["rows"] = ra.pop("documents")
    return ra


# ------------------------------------------------------------------ dich phan hoi

def _row_ve_document(r: Any) -> Any:
    if isinstance(r, dict) and "$tableId" in r and "$collectionId" not in r:
        r = dict(r)
        r["$collectionId"] = r["$tableId"]
    return r


def _index_ve_cu(i: Any) -> Any:
    if isinstance(i, dict) and "columns" in i and "attributes" not in i:
        i = dict(i)
        i["attributes"] = i["columns"]
    return i


def _table_ve_collection(t: Any) -> Any:
    if not isinstance(t, dict):
        return t
    t = dict(t)
    if "columns" in t and "attributes" not in t:
        t["attributes"] = t["columns"]
    if "indexes" in t:
        t["indexes"] = [_index_ve_cu(i) for i in t["indexes"]]
    if "rowSecurity" in t and "documentSecurity" not in t:
        t["documentSecurity"] = t["rowSecurity"]
    return t


_LOAI_LOI = (("row_", "document_"), ("table_", "collection_"), ("column_", "attribute_"))


def dich_than_phan_hoi(body: Any, loai: str, status: int) -> Any:
    if not isinstance(body, dict):
        return body
    if status >= 400:
        b = dict(body)
        t = str(b.get("type") or "")
        for moi, cu in _LOAI_LOI:
            if t.startswith(moi):
                b["type"] = cu + t[len(moi):]
        # `setup_appwrite` nhan dien index trung bang CHINH van ban cua 1.9.6.
        msg = str(b.get("message") or "")
        b["message"] = msg.replace("same columns", "same attributes")
        return b
    if loai in ("document",):
        return _row_ve_document(body)
    if loai == "documents":
        b = dict(body)
        if "rows" in b:
            b["documents"] = [_row_ve_document(r) for r in b.pop("rows")]
        return b
    if loai == "collection":
        return _table_ve_collection(body)
    if loai == "collections":
        b = dict(body)
        if "tables" in b:
            b["collections"] = [_table_ve_collection(t) for t in b.pop("tables")]
        return b
    if loai == "attribute":
        b = dict(body)
        if "columns" in b and "attributes" not in b:
            b["attributes"] = b["columns"]
        return b
    if loai == "index":
        b = _index_ve_cu(body)
        if isinstance(b, dict) and "indexes" in b:
            b = dict(b)
            b["indexes"] = [_index_ve_cu(i) for i in b["indexes"]]
        return b
    return body


# ------------------------------------------------------------------ cai vao httpx

_goc: Optional[Callable[..., Any]] = None
_khoa = threading.Lock()
_dem = {"da_dich": 0}


def _boc(goc: Callable[..., Any]) -> Callable[..., Any]:
    import httpx

    goc_url = STAGING_ENDPOINT

    def handle_request(self, request: "httpx.Request") -> "httpx.Response":
        url = str(request.url)
        if not url.startswith(goc_url + "/databases") or \
                request.headers.get("x-appwrite-project") != STAGING_PROJECT_ID:
            return goc(self, request)
        tach = dich_duong(request.url.path[len("/v1"):] if request.url.path.startswith("/v1") else request.url.path)
        if tach is None:
            return goc(self, request)
        duong_moi, loai = tach
        # GET /databases (liet ke) chay duoc ca tren 2.x — giu nguyen, khong dich.
        if loai == "databases" and request.method == "GET":
            return goc(self, request)
        than = request.content
        headers = dict(request.headers)
        if than and "json" in headers.get("content-type", ""):
            try:
                than = json.dumps(dich_than_yeu_cau(json.loads(than), loai), ensure_ascii=False).encode("utf-8")
            except ValueError:
                pass
        headers.pop("content-length", None)
        moi = httpx.Request(request.method, request.url.copy_with(path="/v1" + duong_moi), headers=headers,
                            content=than, extensions=request.extensions)
        resp = goc(self, moi)
        resp.read()
        noi_dung = resp.content
        if noi_dung and "json" in resp.headers.get("content-type", ""):
            try:
                noi_dung = json.dumps(dich_than_phan_hoi(json.loads(noi_dung), loai, resp.status_code),
                                      ensure_ascii=False).encode("utf-8")
            except ValueError:
                pass
        h = [(k, v) for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-encoding",
                                                                            "transfer-encoding")]
        _dem["da_dich"] += 1
        return httpx.Response(resp.status_code, headers=h, content=noi_dung, request=request,
                              extensions={k: v for k, v in resp.extensions.items() if k != "network_stream"})

    handle_request.__fanfic_lop_dich_staging__ = True  # type: ignore[attr-defined]
    return handle_request


def da_cai() -> bool:
    return _goc is not None


def cai_dat() -> None:
    """Cai lop dich vao `httpx.HTTPTransport` (idempotent). CHI goi sau `can_kich_hoat()` = True."""
    global _goc
    import httpx

    with _khoa:
        if _goc is not None:
            return
        _goc = httpx.HTTPTransport.handle_request
        httpx.HTTPTransport.handle_request = _boc(_goc)  # type: ignore[method-assign]


def go_bo() -> None:
    """Chi dung trong test."""
    global _goc
    import httpx

    with _khoa:
        if _goc is not None:
            httpx.HTTPTransport.handle_request = _goc  # type: ignore[method-assign]
            _goc = None


def kich_hoat_neu_staging(settings: Any, env: Optional[Mapping[str, str]] = None) -> bool:
    """Diem vao DUY NHAT tu `server/main.py` va `scripts/setup_appwrite.py`. Production: tra False,
    khong cham gi. Cau hinh staging sai dich: nem `LopDichStagingBiTuChoi` (tien trinh chet)."""
    aw = getattr(settings, "appwrite", None)
    if aw is None:
        return False
    if not can_kich_hoat(aw.project_id, aw.endpoint, getattr(settings, "environment", ""), env):
        return False
    cai_dat()
    return True


def thong_ke() -> Dict[str, int]:
    return dict(_dem)

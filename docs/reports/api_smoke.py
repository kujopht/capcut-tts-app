#!/usr/bin/env python3
"""Doi soat muc UNG DUNG qua chinh REST API cua Appwrite da khoi phuc.

Dung mot API key CO SAN cua production: giai ma tu `_console_keys` bang
`_APP_OPENSSL_KEY_V1`, giu trong bo nho, KHONG BAO GIO in ra. Neu khoa sai
thi buoc giai ma da hong tu truoc, nen viec API tra ve du lieu that la bang
chung khep kin: khoa dung -> key dung -> Appwrite doc duoc du lieu that.

Ghi la CO DAO NGUOC: tao mot document danh dau, doc lai, roi XOA, roi doi
chieu so luong tro ve dung nhu cu.

Chay TREN may dien tap.
"""
import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://localhost/v1"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # chung chi tu ky vi ACME da bi tat


def khoa_openssl(env_path: Path) -> bytes:
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("_APP_OPENSSL_KEY_V1="):
            return line.split("=", 1)[1].strip().encode()
    raise SystemExit("thieu _APP_OPENSSL_KEY_V1")


def giai_ma(chuoi: str, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    b = json.loads(chuoi)

    def _b(v):
        try:
            return bytes.fromhex(v)
        except ValueError:
            return base64.b64decode(v)

    ct = base64.b64decode(b["data"])
    return AESGCM(key[:16]).decrypt(_b(b["iv"]), ct + _b(b["tag"]), None).decode()


def goi(path: str, project: str, api_key: str, method: str = "GET",
        body: dict | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-Appwrite-Project", project)
    req.add_header("X-Appwrite-Key", api_key)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, context=CTX, timeout=45) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _now() -> str:
    """Appwrite doi ISO8601. Dung UTC de khong phu thuoc mui gio may."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def main() -> int:
    env = Path(sys.argv[1])
    keys_json = Path(sys.argv[2])  # {project_id: {"name":..,"secret":..}}
    k = khoa_openssl(env)
    ho_so = json.loads(keys_json.read_text(encoding="utf-8"))

    project = ho_so["project"]
    api_key = giai_ma(ho_so["secret"], k)
    print(f"  dung API key '{ho_so.get('name')}' (gia tri KHONG in)")
    print(f"  project: {project}")

    dbid = ho_so["database"]
    st, r = goi(f"/databases/{dbid}/collections", project, api_key)
    print(f"\n[API] GET collections -> HTTP {st}")
    if st != 200:
        print("      " + json.dumps(r)[:200])
        return 1
    cols = r.get("collections", [])
    print(f"      tong collection: {r.get('total')}")

    st, nv = goi(f"/databases/{dbid}/collections/novels/documents",
                 project, api_key)
    print(f"\n[API] GET novels -> HTTP {st}, total={nv.get('total')}")
    for d in (nv.get("documents") or [])[:3]:
        print("      novel: " + str(d.get("title", ""))[:44])
    goc = nv.get("total")

    # --- GHI CO DAO NGUOC ---
    print("\n[API] tao document danh dau (se xoa ngay sau do)")
    moi = {
        "documentId": "rehearsal_probe_20260905",
        "data": {
            "novel_id": "nov_rehearsal_probe",
            "owner_id": "rehearsal",
            "title": "[REHEARSAL PROBE] xoa ngay sau khi doc lai",
            "state": "draft",
            "created_at": _now(),
            "updated_at": _now(),
        },
    }
    st, c = goi(f"/databases/{dbid}/collections/novels/documents",
                project, api_key, "POST", moi)
    print(f"      POST -> HTTP {st}")
    if st not in (200, 201):
        print("      " + json.dumps(c)[:300])
        return 1

    st, rb = goi(f"/databases/{dbid}/collections/novels/documents/rehearsal_probe_20260905",
                 project, api_key)
    print(f"      GET readback -> HTTP {st}, title='{str(rb.get('title'))[:34]}'")

    st, _ = goi(f"/databases/{dbid}/collections/novels/documents/rehearsal_probe_20260905",
                project, api_key, "DELETE")
    print(f"      DELETE -> HTTP {st}")

    st, sau = goi(f"/databases/{dbid}/collections/novels/documents",
                  project, api_key)
    print(f"\n[API] novels total truoc={goc} sau={sau.get('total')} "
          f"-> {'DA TRA VE NGUYEN TRANG' if goc == sau.get('total') else 'LECH!'}")
    return 0 if goc == sau.get("total") else 1


if __name__ == "__main__":
    raise SystemExit(main())

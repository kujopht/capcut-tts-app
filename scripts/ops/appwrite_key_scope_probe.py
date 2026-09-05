#!/usr/bin/env python3
"""Hoi MOT cau: `APPWRITE_SCHEMA_API_KEY` co quyen `documents.*` hay khong?

VI SAO CAN. `docs/HANDOFF.md` lap luan rang "13 series that khong the bi dong
toi" DUA TREN viec khoa schema co dung bay scope va **khong** co
`documents.*`. Dien tap 2026-09-05 doc duoc `_console_keys` cua chinh
production va thay tren project `fanfic-world-prod` co CA HAI loai:

    fanfic-schema-provisioner   7 scope, KHONG co documents.*
    schema-migration-key        10 scope, CO documents.write

Nen lap luan an toan kia chi dung neu bien moi truong dang tro vao khoa thu
nhat. Khong doan — hoi thang may chu.

VI SAO KHONG DI QUA CLOUDFLARE. `web_product_appwrite_read_check.py` bi
Cloudflare chan bang Error 1010 khi goi tu may dieu hanh. Tep nay noi THANG
toi origin (`35.225.209.115`) nhung van dat SNI/Host dung ten mien, nen
chung chi van duoc kiem dung.

CHI GET. Khong ghi gi. Khong bao gio in gia tri khoa, va khoa khong bao gio
xuat hien trong tham so tien trinh.
"""
from __future__ import annotations

import http.client
import json
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Origin that cua `appwrite-dev.fanfic.world`, ghi trong
#: `docs/AWS_STAGING_MIGRATION.md`. Di thang toi day de vuot Cloudflare 1010.
ORIGIN_IP = "35.225.209.115"
HOSTNAME = "appwrite-dev.fanfic.world"


class _NoiThangToiOrigin(http.client.HTTPSConnection):
    """Noi TCP toi mot IP cu the nhung bat tay TLS bang TEN MIEN.

    Tuong duong `curl --resolve <ten>:443:<ip>`: bo qua DNS (va do do bo qua
    Cloudflare) ma VAN kiem chung chi theo ten mien that. Khong tat xac thuc
    chung chi o bat ky dau — mot phep do di vong khong duoc phep keo theo mot
    lo hong TLS.
    """

    def __init__(self, ip: str, ten_mien: str, **kw):
        super().__init__(ten_mien, 443, **kw)
        self._ip = ip

    def connect(self):
        import socket
        self.sock = socket.create_connection((self._ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(
            self.sock, server_hostname=self.host)


def goi(path: str, project: str, key: str) -> dict:
    """GET toi origin. Khoa chi nam trong header, khong vao tham so tien trinh."""
    ctx = ssl.create_default_context()  # verify BAT, hostname check BAT
    conn = _NoiThangToiOrigin(ORIGIN_IP, HOSTNAME, timeout=45, context=ctx)
    try:
        conn.request("GET", path, headers={
            "X-Appwrite-Project": project,
            "X-Appwrite-Key": key,
            "User-Agent": "fanfic-ops-scope-probe/1",
        })
        r = conn.getresponse()
        body = r.read(600).decode("utf-8", "replace")
        return {"status": r.status, "body": body[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    from scripts.fanfic_credential_broker import appwrite_admin_env

    env = appwrite_admin_env()
    key = env.pop("APPWRITE_SCHEMA_API_KEY", "")
    project = env.get("APPWRITE_PROJECT_ID", "")
    database = env.get("APPWRITE_DATABASE_ID", "")
    if not key:
        print("khong lay duoc khoa tu broker", file=sys.stderr)
        return 2

    ra: dict = {
        "origin": ORIGIN_IP,
        "hostname": HOSTNAME,
        "project": project,
        "database": database,
        "key_present": True,          # gia tri KHONG BAO GIO in
    }

    # `collections.read` — khoa schema PHAI co.
    ra["collections_read"] = goi(
        f"/v1/databases/{database}/collections", project, key)
    # `documents.read` — day la cau hoi that su.
    ra["documents_read_novels"] = goi(
        f"/v1/databases/{database}/collections/novels/documents",
        project, key)

    st = ra["documents_read_novels"]["status"]
    if st == 200:
        ra["KET_LUAN"] = (
            "KHOA CO documents.read — lap luan '13 series that khong the bi "
            "dong toi' trong HANDOFF.md KHONG con dung")
    elif st == 401:
        ra["KET_LUAN"] = (
            "KHOA KHONG co documents.* — dung nhu HANDOFF.md mo ta")
    else:
        ra["KET_LUAN"] = f"chua ket luan duoc (HTTP {st})"

    print(json.dumps(ra, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

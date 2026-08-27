#!/usr/bin/env python3
"""
Theo doi so luot goi Worker (`fanfic-web`) tren Cloudflare Free — canh bao
SOM truoc khi cham tran 100.000/ngay (xem su co 2026-08-26,
`docs/reports/cloudflare-quota-incident-2026-08-26.md`), khong doi den luc
site tra ve 1027 moi biet.

KHONG can tao credential moi: doc THANG tu token OAuth cua chinh `wrangler`
(`~/.config/.wrangler/config/default.toml`, duong dan chuan tren Windows la
`%APPDATA%\\xdg.config\\.wrangler\\config\\default.toml`) — token nay VON DA
co quyen doc Account Analytics (kiem chung truc tiep bang mot cuoc goi that
2026-08-27, khong doan), nen khong can xin them scope hay tao API token rieng
nhu ban nhap dau tien cua bao cao su co da gia dinh.

GOI GraphQL Analytics API — day la mot cuoc goi DOC BAO CAO (control-plane),
KHONG di qua Worker, nen KHONG tinh vao chinh 100.000 request/ngay dang duoc
theo doi. Chay lai kich ban nay bao nhieu lan cung khong lam trang toi hon.

DUNG TAN SUAT THAP (vai lan mot gio la du), goi tu mot bo lap lich BEN NGOAI
(Task Scheduler / cron / systemd timer — cung kien truc voi
`run_websub_reconciliation.py`) — script nay KHONG tu lap lich, chi chay MOT
LAN roi thoat.

Nguong NORMAL/WARNING/CRITICAL duoc dinh tu DU LIEU THAT (xem
`docs/reports/cloudflare-free-tier-runbook.md`): gio sach sau khi sua xong
storm va sau khi quota reset (2026-08-27, 00:00-02:00 UTC) chi ~75-90
request/gio. Nguong duoc dat CACH XA muc do that ca chuc lan, khong phai
mot con so bia dat.

Chay:
    .venv\\Scripts\\python.exe -m scripts.cloudflare_request_monitor
    .venv\\Scripts\\python.exe -m scripts.cloudflare_request_monitor --json
    .venv\\Scripts\\python.exe -m scripts.cloudflare_request_monitor --log path/to/file.log
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ACCOUNT_ID = "a0084ee7d0f170b2b13bd0ebd5edbd76"
SCRIPT_NAME = "fanfic-web"
GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

#: Ngong doc token OAuth cua wrangler tu vi tri chuan cua no tren May Windows
#: nay — KHONG doc tu bien moi truong/tep khac, dung MOT nguon tin cay duy
#: nhat de tranh vo tinh doc nham token cu/sai tai khoan.
_WRANGLER_CONFIG_CANDIDATES = [
    Path.home() / "AppData" / "Roaming" / "xdg.config" / ".wrangler" / "config" / "default.toml",
    Path.home() / ".wrangler" / "config" / "default.toml",
]

#: request/gio — duoi day la an toan ro rang so voi ~75-90/gio quan sat duoc
#: o gio sach dau tien sau khi sua xong (2026-08-27). Con nho de con phong
#: cho luu luong that tang truong ma khong bao dong gia.
NGUONG_CANH_BAO_MOI_GIO = 2_000       # 2.000/gio * 24 = 48.000/ngay neu keo dai
NGUONG_NGHIEM_TRONG_MOI_GIO = 4_000   # 4.000/gio * 24 = 96.000/ngay neu keo dai
#: Tong trong NGAY UTC hien tai — canh bao nghiem trong ngay ca khi con
#: duong tang khong dot bien, chi la cong don qua nhieu gio.
NGUONG_NGHIEM_TRONG_TICH_LUY_NGAY = 80_000  # 80% tran 100.000/ngay


def _doc_oauth_token() -> str:
    for duong_dan in _WRANGLER_CONFIG_CANDIDATES:
        if not duong_dan.exists():
            continue
        for dong in duong_dan.read_text(encoding="utf-8").splitlines():
            dong = dong.strip()
            if dong.startswith("oauth_token"):
                return dong.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(
        "Không tìm thấy token OAuth của wrangler — chạy `npx wrangler login` "
        "trong thư mục web/ trước (script này không tự tạo credential).")


@dataclass
class KetQuaTheoDoi:
    tong_hom_nay: int
    theo_gio: List[dict]
    muc_do: str  # "NORMAL" | "WARNING" | "CRITICAL"
    ly_do: str


def _goi_graphql(token: str, since: datetime, until: datetime) -> List[dict]:
    import urllib.request

    # SCRIPT_NAME noi TRUC TIEP vao chuoi query (khong qua $variables) — da
    # kiem chung day la cach hoat dong voi schema hien tai cua Cloudflare
    # (2026-08-27). An toan vi SCRIPT_NAME la hang so noi bo trong file nay,
    # khong phai dau vao tu nguoi dung/tham so dong lenh.
    query = f"""
    query($accountTag: String!, $since: Time!, $until: Time!) {{
      viewer {{
        accounts(filter: {{ accountTag: $accountTag }}) {{
          workersInvocationsAdaptive(
            limit: 100
            filter: {{ scriptName: "{SCRIPT_NAME}", datetime_geq: $since, datetime_leq: $until }}
          ) {{
            sum {{ requests errors }}
            dimensions {{ datetimeHour }}
          }}
        }}
      }}
    }}
    """

    body = json.dumps({
        "query": query,
        "variables": {
            "accountTag": ACCOUNT_ID,
            "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "until": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        GRAPHQL_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if payload.get("errors"):
        raise RuntimeError(f"Cloudflare GraphQL trả lỗi: {payload['errors']}")

    accounts = payload["data"]["viewer"]["accounts"]
    if not accounts:
        return []
    return accounts[0]["workersInvocationsAdaptive"]


def phan_loai(gio_gan_nhat: int, tong_hom_nay: int) -> tuple:
    """Ham THUAN (khong mang) — tach rieng de kiem thu khong can goi that
    Cloudflare. Nhan hai con so da tinh san, tra ve (muc_do, ly_do)."""
    if gio_gan_nhat >= NGUONG_NGHIEM_TRONG_MOI_GIO or tong_hom_nay >= NGUONG_NGHIEM_TRONG_TICH_LUY_NGAY:
        muc_do = "CRITICAL"
        ly_do = (f"giờ gần nhất {gio_gan_nhat} req (ngưỡng {NGUONG_NGHIEM_TRONG_MOI_GIO}) "
                 f"hoặc tổng hôm nay {tong_hom_nay} req (ngưỡng {NGUONG_NGHIEM_TRONG_TICH_LUY_NGAY})")
    elif gio_gan_nhat >= NGUONG_CANH_BAO_MOI_GIO:
        muc_do = "WARNING"
        ly_do = f"giờ gần nhất {gio_gan_nhat} req (ngưỡng cảnh báo {NGUONG_CANH_BAO_MOI_GIO})"
    else:
        muc_do = "NORMAL"
        ly_do = f"giờ gần nhất {gio_gan_nhat} req, tổng hôm nay {tong_hom_nay} req — trong ngưỡng bình thường"
    return muc_do, ly_do


def kiem_tra(token: Optional[str] = None) -> KetQuaTheoDoi:
    token = token or _doc_oauth_token()
    bay_gio = datetime.now(timezone.utc)
    dau_ngay_utc = bay_gio.replace(hour=0, minute=0, second=0, microsecond=0)
    # Lay them 2 gio truoc do de khong bo lo gio hien tai (Cloudflare gop
    # theo gio UTC tron, con `bay_gio` co the la 14:37 — van can gio 14:00).
    hang = _goi_graphql(token, dau_ngay_utc, bay_gio + timedelta(hours=1))

    theo_gio = sorted(
        ({"gio": h["dimensions"]["datetimeHour"], "requests": h["sum"]["requests"],
          "errors": h["sum"]["errors"]} for h in hang
         if h["dimensions"]["datetimeHour"] >= dau_ngay_utc.strftime("%Y-%m-%dT%H:%M:%SZ")),
        key=lambda x: x["gio"])

    tong_hom_nay = sum(h["requests"] for h in theo_gio)
    gio_gan_nhat = theo_gio[-1]["requests"] if theo_gio else 0
    muc_do, ly_do = phan_loai(gio_gan_nhat, tong_hom_nay)

    return KetQuaTheoDoi(tong_hom_nay=tong_hom_nay, theo_gio=theo_gio, muc_do=muc_do, ly_do=ly_do)


def main(argv: List[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    dang_json = "--json" in argv
    duong_dan_log: Optional[str] = None
    for i, a in enumerate(argv):
        if a == "--log" and i + 1 < len(argv):
            duong_dan_log = argv[i + 1]

    try:
        kq = kiem_tra()
    except Exception as exc:  # noqa: BLE001 — script CLI, in lỗi rõ ràng rồi thoát khác 0
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    if dang_json:
        print(json.dumps({
            "muc_do": kq.muc_do, "ly_do": kq.ly_do,
            "tong_hom_nay": kq.tong_hom_nay, "theo_gio": kq.theo_gio,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"MỨC ĐỘ        : {kq.muc_do}")
        print(f"LÝ DO         : {kq.ly_do}")
        print(f"TỔNG HÔM NAY  : {kq.tong_hom_nay} request (script: {SCRIPT_NAME})")
        print("THEO GIỜ (UTC):")
        for h in kq.theo_gio:
            print(f"  {h['gio']}  {h['requests']:>6} req  ({h['errors']} lỗi)")

    if duong_dan_log:
        dong = (f"{datetime.now(timezone.utc).isoformat()}  {kq.muc_do:8s}  "
                f"tong_hom_nay={kq.tong_hom_nay}  {kq.ly_do}\n")
        Path(duong_dan_log).parent.mkdir(parents=True, exist_ok=True)
        with open(duong_dan_log, "a", encoding="utf-8") as f:
            f.write(dong)

    return {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}[kq.muc_do]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Do do tre Appwrite — do CA khi HTTP tra ve khong-2xx.

VI SAO CO TEP NAY
-----------------
Bo thu thap cu (`staging_run_all.sh` muc 5) goi `curl ... || echo "khong do
duoc"`. Khi endpoint tra 401/404 thi `curl` van thanh cong ve mat tien
trinh nhung ta lai khong giu duoc so do; con khi `curl` that bai that thi
ta mat ca so do LAN ma trang thai. Ket qua: cot "do tre Appwrite" trong
moi bao cao staging deu trong.

Nguyen nhan goc KHONG phai la khong do duoc — la **tron lan hai cau hoi**:
  1. "mat bao lau de nhan duoc mot cau tra loi" (do tre — luon do duoc,
     mien la co byte nao quay ve)
  2. "cau tra loi do co phai la tin hieu khoe manh khong" (trang thai)

Tep nay tach hai cau hoi do. `do_tre_giay` duoc ghi nhan ngay ca khi
`http_status` la 401/404/500. `khoe` chi `True` khi 2xx.

RANG BUOC AN TOAN: mot trang thai KHONG-2xx khong bao gio duoc dien giai
thanh mot cong suc khoe da dat. `khoe` va `do_tre_giay` la hai truong
rieng, va ben goi nao muon dung do tre lam bang chung suc khoe thi phai
tu doc `khoe` — khong co duong tat.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

#: Phan loai that bai. Giu nguyen thay vi gop het thanh "loi" — mot lan
#: DNS hong va mot lan 401 la hai su co hoan toan khac nhau.
LOP_DNS = "dns"
LOP_KET_NOI = "ket_noi"
LOP_TLS = "tls"
LOP_HET_GIO = "het_gio"
LOP_HTTP = "http"          # co phan hoi HTTP, nhung khong-2xx
LOP_KHAC = "khac"
LOP_KHONG = ""             # khong that bai


def do_tre(endpoint: str, duong: str = "/health/version",
           timeout: float = 20.0,
           project_id: Optional[str] = None) -> Dict[str, Any]:
    """Goi mot lan, tra ve ca do tre LAN trang thai LAN phan loai that bai.

    `endpoint` la `APPWRITE_ENDPOINT` (da bao gom `/v1`). Khong bao gio nem
    ngoai le: mot bo thu thap so lieu lam do vong quan sat la mot bo thu
    thap toi hon khong co.
    """
    url = endpoint.rstrip("/") + duong
    req = urllib.request.Request(url, method="GET")
    # Ghi lai URL da CAT tham so truy van: mot ngay nao do tham so do co
    # the la khoa, va ban ghi nay di vao bao cao.
    url_an_toan = url.split("?", 1)[0]
    req.add_header("User-Agent", "fanfic-cutover-probe/1")
    if project_id:
        # Appwrite tu luu tru chap nhan `/health/version` khong can header
        # nay; ban Cloud thi khong. Gui khi biet -> mot ham dung cho ca hai.
        req.add_header("X-Appwrite-Project", project_id)

    ra: Dict[str, Any] = {
        "url": url_an_toan,
        "do_tre_giay": None,
        "http_status": None,
        "khoe": False,
        "lop_that_bai": LOP_KHAC,
        "chi_tiet": "",
        "than": None,
    }
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            than = r.read(4096)
            ra["do_tre_giay"] = round(time.perf_counter() - t0, 4)
            ra["http_status"] = r.status
            ra["khoe"] = 200 <= r.status < 300
            ra["lop_that_bai"] = LOP_KHONG if ra["khoe"] else LOP_HTTP
            try:
                ra["than"] = json.loads(than.decode("utf-8", "replace"))
            except (ValueError, UnicodeDecodeError):
                ra["than"] = None
        return ra
    except urllib.error.HTTPError as exc:
        # DAY la cai hong cu: mot phan hoi HTTP that su DA quay ve, nen do
        # tre CO THAT va phai duoc giu.
        ra["do_tre_giay"] = round(time.perf_counter() - t0, 4)
        ra["http_status"] = exc.code
        ra["khoe"] = False
        ra["lop_that_bai"] = LOP_HTTP
        ra["chi_tiet"] = f"HTTP {exc.code}"
        return ra
    except urllib.error.URLError as exc:
        ra["do_tre_giay"] = round(time.perf_counter() - t0, 4)
        ly_do = getattr(exc, "reason", exc)
        ten = type(ly_do).__name__ if not isinstance(ly_do, str) else "URLError"
        van_ban = str(ly_do)
        thap = van_ban.lower()
        if "timed out" in thap or ten == "timeout":
            ra["lop_that_bai"] = LOP_HET_GIO
        elif "name or service not known" in thap or "getaddrinfo" in thap \
                or "nodename nor servname" in thap:
            ra["lop_that_bai"] = LOP_DNS
        elif "certificate" in thap or "ssl" in thap:
            ra["lop_that_bai"] = LOP_TLS
        else:
            ra["lop_that_bai"] = LOP_KET_NOI
        # CHI ten kieu ngoai le, KHONG bao gio van ban cua no. Thong diep
        # ngoai le thuong nhac lai URL da goi — va URL do co the mang tham
        # so truy van, mot ngay nao do la khoa. `lop_that_bai` da mang het
        # gia tri chan doan can thiet (dns / tls / ket_noi / het_gio).
        ra["chi_tiet"] = ten
        return ra
    except Exception as exc:  # noqa: BLE001
        ra["do_tre_giay"] = round(time.perf_counter() - t0, 4)
        ra["lop_that_bai"] = LOP_KHAC
        ra["chi_tiet"] = type(exc).__name__
        return ra


def dong_tom_tat(k: Dict[str, Any]) -> str:
    """Mot dong DUY NHAT cho bao cao — luon in duoc, khong bao gio trong."""
    tre = "khong do duoc" if k["do_tre_giay"] is None else f"{k['do_tre_giay']:.3f}s"
    tt = k["http_status"] if k["http_status"] is not None else "-"
    nhan = "KHOE" if k["khoe"] else f"KHONG-KHOE({k['lop_that_bai'] or '?'})"
    return f"do_tre={tre}  http={tt}  {nhan}"


if __name__ == "__main__":
    import os
    import sys

    ep = os.environ.get("APPWRITE_ENDPOINT", "")
    if not ep:
        print("thieu APPWRITE_ENDPOINT", file=sys.stderr)
        raise SystemExit(2)
    kq = do_tre(ep, project_id=os.environ.get("APPWRITE_PROJECT_ID"))
    print(json.dumps(kq, ensure_ascii=False))
    print(dong_tom_tat(kq))
    # Ma thoat theo SUC KHOE, khong theo "co do duoc hay khong" — mot
    # trang thai hong khong bao gio duoc dien giai thanh mot cong da dat.
    raise SystemExit(0 if kq["khoe"] else 1)

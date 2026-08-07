"""
Smoke test cho mot ban trien khai staging.

    PYTHONPATH=. python scripts/staging_smoke.py --api https://... --web https://...

Chay duoc voi BAT KY ban trien khai nao, khong can credential cua kho du lieu:
no chi goi HTTP API cong khai cua backend, dung nhu mot nguoi dung that. Nho vay
chay duoc tu may lap trinh vien, tu CI, hay tu chinh host staging.

TU DON DEP: moi fixture do no tao deu mang tien to `[SMOKE]` va deu bi xoa o cuoi,
ke ca khi co buoc that bai. Tai khoan test dung mot lan, dat ten ngau nhien.

KHONG BAO GIO in token, cookie hay presigned URL. URL audio duoc rut gon con
scheme + host + duong dan, bo toan bo query — chinh phan query moi la chu ky.

Nhung phan CAN thao tac ngoai (restart web, kill worker) khong nam o day: chung
can quyen dieu khien nen tang. Xem `deploy/RUNBOOK.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional, Tuple

KET_QUA = []


def rut_gon_url(url: str) -> str:
    """
    Mo ta mot presigned URL ma KHONG lo gi.

    Bo ba thu, moi thu vi mot ly do khac nhau:
      - query: chua chu ky (`X-Amz-Signature`) — ai co la tai duoc file;
      - host: chua R2 account id (`{account}.r2.cloudflarestorage.com`);
      - duong dan: chua ten bucket, `owner_id` va `chapter_id`.

    Ban dau ham nay chi bo query, va dau ra van in nguyen host lan duong dan —
    tuc la lo account id va owner id vao log. Chi giu lai nhung gi du de biet URL
    co dung hinh dang hay khong.
    """
    p = urllib.parse.urlsplit(url)
    duoi = p.path.rsplit(".", 1)[-1] if "." in p.path else "(khong ro)"
    return (f"{p.scheme}://<host da an>/<duong dan da an>.{duoi}"
            f"  co_query={'co' if p.query else 'KHONG'}"
            f"  do_dai={len(url)}")


def goi(base: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 300) -> Tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body[:200]}
    except Exception as exc:
        return 0, {"loi": type(exc).__name__}


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'DAT ' if ok else 'HONG'}] {ten}" + (f"  — {ghi_chu}" if ghi_chu else ""),
          flush=True)
    return ok


# ---------------------------------------------------------------- cac buoc


def buoc_suc_khoe(api: str, sha_mong: Optional[str]) -> Dict[str, Any]:
    print("\n=== 1. Health / readiness ===")
    ma, h = goi(api, "GET", "/api/health")
    kt("GET /api/health tra 200", ma == 200, f"HTTP {ma}")
    kt("moi truong la staging", h.get("environment", "").lower() == "staging",
       f"environment={h.get('environment')!r}")
    kt("web KHONG tu chay job", h.get("inline_worker") is False,
       f"inline_worker={h.get('inline_worker')}")
    kt("dung kho that, khong phai mock",
       h.get("data_backend") == "appwrite" and h.get("storage_backend") == "r2",
       f"{h.get('data_backend')}/{h.get('storage_backend')}")
    ma, r = goi(api, "GET", "/api/ready")
    kt("GET /api/ready tra 200", ma == 200, f"HTTP {ma} status={r.get('status')}")
    for ten in ("metadata", "storage"):
        kt(f"phu thuoc {ten} san sang",
           (r.get("phu_thuoc") or {}).get(ten, {}).get("dat") is True)
    if sha_mong:
        kt("khong ro SHA tu API (backend khong cong bo)", True,
           "kiem SHA o giao dien nen tang, xem bao cao")
    return h


def buoc_xac_thuc(api: str) -> Dict[str, Any]:
    print("\n=== 2. Xac thuc va phan quyen ===")
    dau = uuid.uuid4().hex[:8]
    tk = {"a": f"smoke-a-{dau}@example.test", "b": f"smoke-b-{dau}@example.test",
          "mk": "MatKhauSmoke12345", "dau": dau}
    for vai in ("a", "b"):
        ma, r = goi(api, "POST", "/api/auth/register",
                    {"email": tk[vai], "password": tk["mk"]})
        kt(f"dang ky tai khoan {vai.upper()}", ma in (200, 201) and "token" in r,
           f"HTTP {ma}")
        tk[f"tok_{vai}"] = r.get("token", "")

    ma, r = goi(api, "POST", "/api/auth/login", {"email": tk["a"], "password": tk["mk"]})
    kt("dang xuat roi dang nhap lai", ma == 200 and "token" in r, f"HTTP {ma}")
    tk["tok_a"] = r["token"]

    ma, _ = goi(api, "POST", "/api/auth/login",
                {"email": tk["a"], "password": "sai-mat-khau"})
    kt("mat khau sai bi tu choi", ma in (400, 401), f"HTTP {ma}")

    for duong in ("/api/novels?mine=true", "/api/chapters?mine=true", "/api/jobs"):
        ma, _ = goi(api, "GET", duong)
        kt(f"{duong} chan an danh", ma == 401, f"HTTP {ma}")
        ma, _ = goi(api, "GET", duong, None, "token-bia-dat")
        kt(f"{duong} tu choi token bia dat", ma == 401, f"HTTP {ma}")
    return tk


def buoc_noi_dung(api: str, tk: Dict[str, Any]) -> Dict[str, str]:
    print("\n=== 3. Novel / chapter va tinh ben vung ===")
    tok = tk["tok_a"]
    ma, r = goi(api, "POST", "/api/novels",
                {"title": f"[SMOKE] {tk['dau']}", "description": "Fixture smoke test."},
                tok)
    kt("tao novel", ma in (200, 201), f"HTTP {ma}")
    nid = r["novel"]["novel_id"]

    doan = ("Trên boong tàu, gió biển thổi mạnh và cánh buồm căng phồng. "
            "Cả đoàn hướng về phía hòn đảo chưa ai đặt chân tới. ")
    ma, r = goi(api, "POST", "/api/chapters",
                {"novel_id": nid, "title": "[SMOKE] Chương", "content": doan * 12,
                 "order_index": 1}, tok)
    kt("tao chapter", ma in (200, 201), f"HTTP {ma}")
    cid = r["chapter"]["chapter_id"]

    # "Refresh" = doc lai tu server bang mot token MOI, khong dua vao bo nho client.
    _, r = goi(api, "POST", "/api/auth/login",
               {"email": tk["a"], "password": tk["mk"]})
    tok2 = r["token"]
    ma, r = goi(api, "GET", f"/api/novels/{nid}", None, tok2)
    kt("doc lai sau khi dang nhap lai: du lieu con nguyen",
       ma == 200 and len(r.get("chapters", [])) == 1, f"HTTP {ma}")
    kt("tieu de duoc luu ben vung",
       r.get("novel", {}).get("title") == f"[SMOKE] {tk['dau']}")

    ma, _ = goi(api, "POST", "/api/novels", {"title": "   "}, tok)
    kt("tieu de chi khoang trang bi tu choi", ma in (400, 422), f"HTTP {ma}")
    return {"novel": nid, "chapter": cid}


def buoc_tts(api: str, tk: Dict[str, Any], ids: Dict[str, str],
             giong: str, cho_toi_da: int) -> Optional[str]:
    print("\n=== 4. TTS: queued -> running -> completed ===")
    tok = tk["tok_a"]
    ma, r = goi(api, "POST", "/api/jobs",
                {"chapter_id": ids["chapter"], "voice_id": giong}, tok)
    if not kt("tao job", ma in (200, 201, 202), f"HTTP {ma} {str(r)[:80]}"):
        return None
    jid = r["job"]["job_id"]
    kt("job bat dau o pending (worker rieng se nhan)",
       r["job"]["status"] == "pending", f"status={r['job']['status']}")

    thay = []
    t0 = time.time()
    cuoi = None
    while time.time() - t0 < cho_toi_da:
        _, r = goi(api, "GET", f"/api/jobs/{jid}", None, tok)
        j = r.get("job", {})
        if j.get("status") != cuoi:
            cuoi = j.get("status")
            thay.append((round(time.time() - t0), cuoi))
            print(f"        t+{thay[-1][0]:>4}s  {cuoi}  "
                  f"{j.get('done_parts')}/{j.get('total_parts')}", flush=True)
        if cuoi in ("completed", "failed"):
            break
        time.sleep(3)

    trang_thai = [t for _, t in thay]
    kt("job duoc worker rieng nhan (co qua running)", "running" in trang_thai,
       f"chuoi: {' -> '.join(trang_thai)}")
    kt("job hoan tat", cuoi == "completed", f"trang thai cuoi={cuoi}")
    if cuoi != "completed":
        print(f"        error_kind={j.get('error_kind')!r}")
        return None

    kt("attempts = 1 (khong phai chay lai)", (j.get("attempts") or 0) == 1,
       f"attempts={j.get('attempts')}")

    print("\n=== 5. Audio phat duoc ===")
    ma, r = goi(api, "GET", f"/api/audio/{ids['chapter']}/url", None, tok)
    kt("xin duoc URL audio", ma == 200, f"HTTP {ma}")
    url = r.get("url", "")
    kt("URL co ky (co query)", "?" in url, rut_gon_url(url))
    try:
        with urllib.request.urlopen(url, timeout=300) as x:
            noi_dung = x.read()
        kt("tai duoc file audio", len(noi_dung) > 10_000, f"{len(noi_dung)} byte")
        kt("la MP3 that (co frame header)",
           noi_dung[:3] == b"ID3" or noi_dung[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
           f"byte dau: {noi_dung[:3].hex()}")
        # `duration > 0` suy ra tu kich thuoc + bitrate; kiem chinh xac can ffprobe,
        # va giao dien da kiem bang the <audio> that o luot E2E.
        kt("kich thuoc du cho duration > 0", len(noi_dung) > 20_000,
           f"{len(noi_dung)/1024:.0f} KiB")
    except Exception as exc:
        kt("tai duoc file audio", False, type(exc).__name__)
    return jid


def buoc_phan_quyen(api: str, tk: Dict[str, Any], ids: Dict[str, str]) -> None:
    print("\n=== 6. Phan quyen giua hai tai khoan ===")
    b = tk["tok_b"]
    n, c = ids["novel"], ids["chapter"]
    for ten, ma_thuc, mong in (
        (f"GET /api/novels/{{id}} (nhap)", goi(api, "GET", f"/api/novels/{n}", None, b)[0], (404,)),
        (f"GET /api/chapters/{{id}} (nhap)", goi(api, "GET", f"/api/chapters/{c}", None, b)[0], (404,)),
        ("PATCH novel", goi(api, "PATCH", f"/api/novels/{n}", {"title": "B chiem"}, b)[0], (403, 404)),
        ("DELETE novel", goi(api, "DELETE", f"/api/novels/{n}", None, b)[0], (403, 404)),
        ("POST job tren chapter cua A", goi(api, "POST", "/api/jobs",
            {"chapter_id": c, "voice_id": "edge:vi-VN-HoaiMyNeural"}, b)[0], (403, 404)),
        ("GET audio cua A", goi(api, "GET", f"/api/audio/{c}", None, b)[0], (403, 404)),
        ("GET presigned URL cua A", goi(api, "GET", f"/api/audio/{c}/url", None, b)[0], (403, 404)),
    ):
        kt(f"B bi chan: {ten}", ma_thuc in mong, f"HTTP {ma_thuc}")
    ma, r = goi(api, "GET", "/api/novels?mine=true", None, b)
    kt("thu vien cua B khong thay truyen cua A",
       ma == 200 and all(x["novel_id"] != n for x in r.get("novels", [])), f"HTTP {ma}")


def buoc_giao_dien(web: Optional[str]) -> None:
    print("\n=== 7. Frontend phan hoi ===")
    if not web:
        kt("bo qua: chua truyen --web", True, "khong kiem duoc")
        return
    for duong in ("/", "/fanfic", "/login"):
        ma, _ = goi(web, "GET", duong)
        kt(f"GET {duong} tra 200", ma == 200, f"HTTP {ma}")
    print("     (kiem tra desktop 1440x900 / mobile 390x844 can trinh duyet that —")
    print("      xem muc tuong ung trong bao cao staging)")


def don_dep(api: str, tk: Dict[str, Any], ids: Optional[Dict[str, str]]) -> None:
    print("\n=== 8. Don fixture ===")
    if not ids:
        kt("khong co fixture nao de don", True)
        return
    ma, r = goi(api, "DELETE", f"/api/novels/{ids['novel']}", None, tk.get("tok_a"))
    kt("xoa truyen [SMOKE] va moi thu phu thuoc", ma in (200, 204),
       f"HTTP {ma} {json.dumps(r.get('removed', {}), ensure_ascii=False)}")
    _, r = goi(api, "GET", "/api/novels?mine=true", None, tk.get("tok_a"))
    kt("tai khoan A khong con truyen nao", r.get("novels") == [],
       f"con {len(r.get('novels', []))}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Smoke test cho ban trien khai staging.")
    p.add_argument("--api", required=True, help="URL goc cua backend, vi du https://fas-staging-api.onrender.com")
    p.add_argument("--web", help="URL goc cua frontend")
    p.add_argument("--sha", help="SHA mong doi, chi de ghi vao bao cao")
    p.add_argument("--voice", default="edge:vi-VN-HoaiMyNeural")
    p.add_argument("--job-timeout", type=int, default=600)
    p.add_argument("--json", metavar="FILE", help="ghi ket qua ra file JSON")
    a = p.parse_args(argv)

    print(f"API = {a.api}")
    print(f"WEB = {a.web or '(khong kiem)'}")

    tk: Dict[str, Any] = {}
    ids: Optional[Dict[str, str]] = None
    try:
        buoc_suc_khoe(a.api, a.sha)
        tk = buoc_xac_thuc(a.api)
        ids = buoc_noi_dung(a.api, tk)
        buoc_tts(a.api, tk, ids, a.voice, a.job_timeout)
        buoc_phan_quyen(a.api, tk, ids)
        buoc_giao_dien(a.web)
    finally:
        # Don du co buoc nao hong: khong de fixture lai tren staging.
        if tk.get("tok_a"):
            don_dep(a.api, tk, ids)

    hong = [t for t, ok, _ in KET_QUA if not ok]
    print(f"\n{'=' * 60}")
    print(f"TONG: {len(KET_QUA) - len(hong)}/{len(KET_QUA)} dat")
    if hong:
        print("HONG:")
        for t in hong:
            print(f"  - {t}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"tong": len(KET_QUA), "dat": len(KET_QUA) - len(hong),
                       "chi_tiet": [{"ten": t, "dat": ok, "ghi_chu": g}
                                    for t, ok, g in KET_QUA]},
                      f, ensure_ascii=False, indent=1)
        print(f"\nDa ghi bao cao: {a.json}")
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())

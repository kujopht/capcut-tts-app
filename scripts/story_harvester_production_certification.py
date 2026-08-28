"""
Story Harvester V3 Phase 18 — kich ban CHUNG NHAN san xuat: xac minh
BACKEND DANG CHAY THAT (khong phai trang thai git) co dung hanh vi mong
doi, PHAN LOAI RO loai that bai thay vi chi bao PASS/FAIL don gian.

    PYTHONPATH=. python scripts/story_harvester_production_certification.py \\
        --api https://fas-prod-api.onrender.com \\
        --admin-token "$FAS_ADMIN_BEARER_TOKEN" \\
        --source-url https://en.wikisource.org/wiki/The_War_of_the_Worlds_(1898) \\
        --expected-sha "$(git rev-parse HEAD)"

CHUA CHAY DUOC O DAY (khong co API dang chay/credential that trong moi
truong nay) — viet san cho buoi sang sau khi merge + xac nhan deploy that
(Phase 18 CHI chay SAU hai dieu kien do, xem bao cao Story Harvester V3).

BON LOAI THAT BAI duoc phan biet RO RANG (khong bao gio gop chung thanh
mot "FAIL" mo ho):

  STALE_DEPLOYMENT — route mong doi tra 404 (chua duoc deploy), hoac SHA
    server bao (`/api/health`) khac `--expected-sha`.
  AUTH_FAILURE — cong admin KHONG doi hoi token (200 ma dang le phai
    401/403), HOAC nguoc lai token dung van bi tu choi.
  SCRAPER_BUG — route ton tai, xac thuc dung, nhung HANH VI/DU LIEU tra
    ve SAI hinh dang mong doi (vd discover khong tra ve proposal hop le,
    mot dot quet khong bao gio ket thuc).
  NETWORK_FAILURE — khong ket noi duoc toi API o TAT CA (DNS/timeout/TLS)
    — khac hoan toan voi "API tra loi nhung tra loi SAI".

AN TOAN: KHONG mass crawl (`--chapter-limit` mac dinh 2, bi chan o 5).
KHONG bao gio ghi/sua Novel/Chapter that (kich ban nay CHI cham toi
scraper admin API — ScrapeRun/SiteProfile, khong dung toi
`/api/novels`/`/api/chapters` — xem Phase 15 rieng cho phan do,
`scripts/story_harvester_direct_to_web_canary.py`). Dot quet duoc tao ra
la du lieu DIEU PHOI vut di (khong phai noi dung nguoi dung), khong can
don rieng nhu Phase 15.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _ep_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()

USER_AGENT = "fanfic-story-harvester-cert/1.0 (+https://github.com/kujopht/capcut-tts-app)"

#: Bon loai that bai — xem docstring dau tep.
STALE_DEPLOYMENT = "STALE_DEPLOYMENT"
AUTH_FAILURE = "AUTH_FAILURE"
SCRAPER_BUG = "SCRAPER_BUG"
NETWORK_FAILURE = "NETWORK_FAILURE"

KET_QUA: List[Dict[str, Any]] = []


def kt(ten: str, dat: bool, loai_neu_hong: str = "", ghi_chu: str = "") -> bool:
    KET_QUA.append({"ten": ten, "dat": dat, "loai": loai_neu_hong if not dat else "",
                    "ghi_chu": ghi_chu})
    nhan = "DAT " if dat else f"HONG [{loai_neu_hong}]"
    print(f"  [{nhan}] {ten}" + (f" — {ghi_chu}" if ghi_chu else ""), flush=True)
    return dat


def goi(api: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 60) -> Tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(api.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", USER_AGENT)
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
            return exc.code, {"raw": body[:300]}
    except Exception as exc:
        # Loi TRUYEN TAI that su (DNS/timeout/TLS/ket noi bi tu choi) —
        # KHONG PHAI mot ma HTTP — day CHINH LA tin hieu NETWORK_FAILURE,
        # phan biet voi mot phan hoi HTTP (du la loi) THAT SU nhan duoc.
        return -1, {"loi": type(exc).__name__, "chi_tiet": str(exc)}


def buoc_suc_khoe_va_sha(api: str, expected_sha: Optional[str]) -> bool:
    print("\n=== 1. Suc khoe + xac minh SHA (STALE_DEPLOYMENT) ===")
    ma, r = goi(api, "GET", "/api/health")
    if ma == -1:
        kt("ket noi duoc toi API", False, NETWORK_FAILURE, str(r))
        return False
    if not kt("GET /api/health tra 200", ma == 200, SCRAPER_BUG, f"HTTP {ma}"):
        return False
    kt("dung kho That (khong phai mock)",
      r.get("data_backend") == "appwrite", SCRAPER_BUG,
      f"data_backend={r.get('data_backend')}")
    sha_server = r.get("commit_sha") or r.get("sha") or r.get("git_sha")
    # Ket qua kiem tra SHA PHAI duoc tra ve, khong chi ghi log. Truoc day ham
    # nay luon `return True`, nen mot deploy CU van di tiep sang buoc quet nho
    # — tuc la chung nhan VAN cham that vao san xuat (tao du lieu, goi scraper)
    # trong dung truong hop ma `main()` da co y DUNG SOM de tranh dieu do.
    # Verdict cuoi cung van FAIL (main() tong hop tu KET_QUA), nen day khong
    # phai PASS gia — nhung no lang phi va gay hieu nham.
    sha_ok = True
    if expected_sha:
        if not sha_server:
            sha_ok = kt("server co cong bo SHA de doi chieu", False, STALE_DEPLOYMENT,
              "endpoint /api/health khong co truong sha — khong the xac minh "
              "deploy moi nhat qua API, kiem tra thu cong tren dashboard")
        else:
            sha_ok = kt("SHA server khop --expected-sha", sha_server.startswith(expected_sha[:12]),
              STALE_DEPLOYMENT, f"server={sha_server}, mong={expected_sha}")
    return sha_ok


def buoc_cong_admin_that_su_doi_hoi_token(api: str) -> bool:
    print("\n=== 2. Cong admin THAT SU doi hoi xac thuc (AUTH_FAILURE) ===")
    ma, r = goi(api, "POST", "/api/admin/scraper/discover", {"url": "https://vidu.test/x"})
    ok = kt("goi KHONG token bi tu choi (401/403, KHONG PHAI 200)",
           ma in (401, 403), AUTH_FAILURE, f"HTTP {ma}")
    ma2, r2 = goi(api, "POST", "/api/admin/scraper/discover",
                  {"url": "https://vidu.test/x"}, token="token-gia-mao-khong-hop-le")
    ok2 = kt("goi voi token SAI cung bi tu choi", ma2 in (401, 403), AUTH_FAILURE,
            f"HTTP {ma2}")
    return ok and ok2


def buoc_route_ton_tai(api: str, admin_token: str) -> bool:
    print("\n=== 3. Cac route scraper TON TAI (STALE_DEPLOYMENT) ===")
    tat_ca_ton_tai = True
    for method, path, payload in (
        ("POST", "/api/admin/scraper/discover", {"url": "https://vidu.test/x"}),
        ("GET", "/api/admin/scraper/runs", None),
        ("POST", "/api/admin/scraper/check-mirror", {"url": "https://vidu.test/x"}),
    ):
        ma, r = goi(api, method, path, payload, admin_token)
        if ma == -1:
            kt(f"{method} {path} — ket noi duoc", False, NETWORK_FAILURE, str(r))
            tat_ca_ton_tai = False
            continue
        if not kt(f"{method} {path} ton tai (khong phai 404)", ma != 404,
                  STALE_DEPLOYMENT, f"HTTP {ma}"):
            tat_ca_ton_tai = False
    return tat_ca_ton_tai


def buoc_discover_va_dry_run(api: str, admin_token: str, source_url: str) -> bool:
    print("\n=== 4. Discover tren nguon THAT (dry-run — khong ghi gi) ===")
    ma, r = goi(api, "POST", "/api/admin/scraper/discover", {"url": source_url}, admin_token)
    if not kt("POST discover tra 200", ma == 200, SCRAPER_BUG, f"HTTP {ma}: {r}"):
        return False
    if r.get("supported"):
        # Nguon DA cau hinh — /discover TU DONG la dry-run (plan_run(dry_run=True)).
        run = r.get("run") or {}
        return kt("dry-run tra ve uoc luong hop le (estimated_total)",
                  isinstance(run.get("estimated_total"), int), SCRAPER_BUG, str(run))
    # Nguon MOI — kiem tra de xuat co hinh dang hop le, KHONG tu confirm
    # (confirm se GHI SiteProfile that — Phase 18 khong lam thay operator
    # quyet dinh do, chi xac minh discovery hoat dong).
    proposal = r.get("proposal") or {}
    return kt("de xuat nguon moi co confidence hop le",
             proposal.get("confidence") in ("high", "medium", "low"), SCRAPER_BUG,
             str(proposal))


def buoc_quet_nho_resume_huy_thu_lai(
        api: str, admin_token: str, source_url: str, chapter_limit: int,
) -> bool:
    print("\n=== 5. Quet nho + resume + huy + thu lai + hang doi duyet ===")
    ma, r = goi(api, "POST", "/api/admin/scraper/runs",
               {"url": source_url, "chapter_limit": chapter_limit}, admin_token)
    if not kt("tao dot quet nho", ma in (200, 201), SCRAPER_BUG, f"HTTP {ma}: {r}"):
        return False
    run_id = (r.get("run") or {}).get("run_id", "")
    if not kt("nhan duoc run_id", bool(run_id), SCRAPER_BUG):
        return False

    # Resume: goi tao LAI CUNG url — phai idempotent (khong tao dot moi).
    ma2, r2 = goi(api, "POST", "/api/admin/scraper/runs",
                  {"url": source_url, "chapter_limit": chapter_limit}, admin_token)
    run_id_2 = (r2.get("run") or {}).get("run_id", "")
    kt("resume: goi lai CUNG url tra ve CUNG run_id (idempotent)",
      run_id_2 == run_id, SCRAPER_BUG, f"{run_id} != {run_id_2}")

    # Drive vai chu ky NHO (bi chan boi chapter_limit — KHONG mass crawl).
    for _ in range(5):
        ma, r = goi(api, "GET", f"/api/admin/scraper/runs/{run_id}", None, admin_token)
        trang_thai = (r.get("run") or {}).get("status", "")
        if trang_thai in ("completed", "partial", "cancelled", "failed"):
            break
        goi(api, "POST", f"/api/admin/scraper/runs/{run_id}/drive", {}, admin_token)
        time.sleep(1)

    ma, r = goi(api, "GET", f"/api/admin/scraper/runs/{run_id}", None, admin_token)
    kt("doc duoc hang doi duyet (review queue) sau khi drive",
      ma == 200 and isinstance(r.get("items"), list), SCRAPER_BUG, f"HTTP {ma}")

    # Huy: TAO MOT dot RIENG de huy (khong huy dot vua quet o tren, tranh
    # anh huong ket qua "hang doi duyet" da kiem o buoc truoc).
    ma, r = goi(api, "POST", "/api/admin/scraper/runs",
               {"url": source_url, "chapter_limit": chapter_limit}, admin_token)
    run_id_huy = (r.get("run") or {}).get("run_id", "")
    if run_id_huy:
        ma, r = goi(api, "POST", f"/api/admin/scraper/runs/{run_id_huy}/cancel",
                   {}, admin_token)
        kt("huy dot hoat dong (route ton tai, tra 200)", ma == 200, SCRAPER_BUG,
          f"HTTP {ma}")

    # Thu lai: route ton tai va tra loi hop le NGAY CA KHI khong co muc
    # loi nao de thu lai (kich ban chung nhan KHONG ep phai co loi that).
    ma, r = goi(api, "POST", f"/api/admin/scraper/runs/{run_id}/retry", {}, admin_token)
    kt("route thu lai (retry) ton tai va tra loi hop le", ma == 200, SCRAPER_BUG,
      f"HTTP {ma}: {r}")

    # Cap nhat gia tang (Phase 9): route check-updates ton tai va tra loi.
    ma, r = goi(api, "GET", f"/api/admin/scraper/runs/{run_id}/check-updates",
               None, admin_token)
    kt("route cap nhat gia tang (check-updates) hoat dong", ma == 200, SCRAPER_BUG,
      f"HTTP {ma}")
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--api", required=True)
    p.add_argument("--admin-token", required=True,
                  help="Bearer token admin — KHONG hardcode, luon dua qua bien moi truong")
    p.add_argument("--source-url", required=True,
                  help="Nguon cong khai, nho, KHONG phai mot trong 13 series that")
    p.add_argument("--chapter-limit", type=int, default=2)
    p.add_argument("--expected-sha", help="SHA commit mong doi da deploy (doi chieu /api/health)")
    p.add_argument("--json", metavar="FILE")
    a = p.parse_args(argv)

    if a.chapter_limit > 5:
        print("TU CHOI: --chapter-limit qua 5 — chung nhan san xuat KHONG mass crawl.")
        return 2

    print(f"Story Harvester V3 — chung nhan san xuat\n  api={a.api}\n"
          f"  source_url={a.source_url}\n  chapter_limit={a.chapter_limit}")

    if not buoc_suc_khoe_va_sha(a.api, a.expected_sha):
        print("\nDUNG SOM: khong ket noi duoc/khong hop le API co ban — cac buoc "
              "sau se chi bao NETWORK_FAILURE/STALE_DEPLOYMENT lap lai vo ich.")
    else:
        buoc_cong_admin_that_su_doi_hoi_token(a.api)
        if buoc_route_ton_tai(a.api, a.admin_token):
            if buoc_discover_va_dry_run(a.api, a.admin_token, a.source_url):
                buoc_quet_nho_resume_huy_thu_lai(
                    a.api, a.admin_token, a.source_url, a.chapter_limit)

    so_dat = sum(1 for k in KET_QUA if k["dat"])
    so_tong = len(KET_QUA)
    theo_loai: Dict[str, int] = {}
    for k in KET_QUA:
        if not k["dat"]:
            theo_loai[k["loai"]] = theo_loai.get(k["loai"], 0) + 1

    print(f"\n=== TOM TAT: {so_dat}/{so_tong} kiem tra DAT ===")
    if theo_loai:
        print("  That bai theo loai:")
        for loai, dem in sorted(theo_loai.items()):
            print(f"    {loai}: {dem}")
    for k in KET_QUA:
        if not k["dat"]:
            print(f"  HONG [{k['loai']}]: {k['ten']} — {k['ghi_chu']}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"api": a.api, "so_dat": so_dat, "so_tong": so_tong,
                      "theo_loai": theo_loai, "ket_qua": KET_QUA},
                     f, ensure_ascii=False, indent=2)

    if theo_loai:
        print(f"\nVERDICT: FAIL — xem loai that bai o tren truoc khi coi day la "
              "san sang san xuat.")
        return 1
    print("\nVERDICT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Story Harvester V3 Phase 15 — canary "direct-to-web" du: URL truyen that
-> discovery -> ScrapeRun -> fetch bi chan -> chuan hoa -> quality ->
hang doi duyet -> "duyet" -> ghi THAT vao Novel/Chapter -> xac minh qua
API cong khai -> don fixture.

    PYTHONPATH=. python scripts/story_harvester_direct_to_web_canary.py \\
        --api https://... --environment staging \\
        --admin-token "$FAS_ADMIN_BEARER_TOKEN" \\
        --source-url https://en.wikisource.org/wiki/The_War_of_the_Worlds_(1898)

    # Xem truoc, KHONG ghi gi vao Novel/Chapter:
    PYTHONPATH=. python scripts/story_harvester_direct_to_web_canary.py \\
        --api https://... --environment staging \\
        --admin-token "$FAS_ADMIN_BEARER_TOKEN" \\
        --source-url https://en.wikisource.org/wiki/The_War_of_the_Worlds_(1898) \\
        --dry-run

CHUA CHAY DUOC O DAY (moi truong nay khong co API dang chay/credential
that) — kich ban nay la PHAN "lam tat ca tru cuoc goi can credential"
cua Phase 15 (xem docs/reports/, bao cao Story Harvester V3): viet san,
kiem tra logic bang unit test rieng
(`server/tests/test_scraper_direct_to_web_harness.py`), CHO buoi sang co
`--api`/`--admin-token` that de chay lan DUY NHAT can credential.

AN TOAN — BON LOP, KHONG lop nao phu thuoc lop kia:
  1. `--environment` la THAM SO BAT BUOC (khong mac dinh) — khong co
     duong nao "vo tinh" chay nham moi truong; TEN moi truong duoc IN RA
     va PHAI go dung trong xac nhan tuong tac (xem `_xac_nhan_moi_truong`).
  2. `--admin-token` PHAI duoc operator dua vao (bien moi truong hoac
     doi so dong lenh) — KHONG BAO GIO doc tu file cau hinh mac dinh/
     hardcode trong script nay. Thieu token nay, script se KHONG the goi
     API scraper (`admin_or_owner_profile` yeu cau), that bai RO RANG
     ngay tu buoc dau, khong am tham bo qua.
  3. KHONG BAO GIO dung/xoa mot Novel DA CO SAN — script CHI xoa
     `novel_id` do CHINH NO nhan lai tu lan `POST /api/novels` CUA NO
     (Novel ID do server sinh ngau nhien, khong the trung/doan truoc).
     Day la co che BAO VE 13 series Fanfic that DUY NHAT can co — KHONG
     dua tren so khop ten/URL (de vo tinh sai), ma dua tren "chi xoa cai
     minh vua tao". Neu bat ky buoc tao Novel nao that bai, KHONG co
     `novel_id` nao duoc ghi lai -> don fixture se bao "khong co gi de
     don" thay vi doan mo mot ID khac.
  4. Novel duoc tao O TRANG THAI DRAFT (mac dinh cua he thong — xem
     `server/domain.py::Novel.state`) va KHONG BAO GIO goi
     `/publish` — canary nay KHONG xuat ban bat cu thu gi. Google Drive
     hoan toan khong lien quan toi luong Novel/Chapter (da xac nhan qua
     nghien cuu ma nguon truoc khi viet kich ban nay).

CO Y BO SOT (trung thuc, xem docstring `server/scraper/dedupe.py`):
`ScrapeRunItem` (kho ben vung cua MOT dot scrape那) KHONG luu `clean_text`
— chi luu METADATA (tieu de, quyet dinh, diem chat luong). Nghia la buoc
"duyet" o day KHONG THE chi doc lai noi dung tu `GET .../runs/{id}` —
kich ban nay tu TAI LAI (fetch that, qua chinh adapter cua scraper) va
TRICH XUAT LAI noi dung cho tung URL chuong DA duoc chap nhan
(REVIEW_READY, quality_passed) truoc khi ghi vao Chapter that — day
CHINH LA cach mot tinh nang "duyet" that su se phai lam (tai lieu ro
trong bao cao Phase 15, khong am tham gia dinh mot kha nang chua ton
tai).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _ep_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()

USER_AGENT = "fanfic-story-harvester-canary/1.0 (+https://github.com/kujopht/capcut-tts-app)"
#: Tien to BAT BUOC tren MOI Novel/Chapter kich ban nay tao — phan biet
#: voi `[SMOKE]` cua `staging_smoke.py` (harness khac, muc dich khac).
TIEN_TO_QA = "[QA-HARVESTER]"

KET_QUA: List[Tuple[str, bool, str]] = []


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'DAT ' if ok else 'HONG'}] {ten}" + (f" — {ghi_chu}" if ghi_chu else ""), flush=True)
    return ok


def goi(api: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 120) -> Tuple[int, Any]:
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
        return 0, {"loi": type(exc).__name__, "chi_tiet": str(exc)}


def _xac_nhan_moi_truong(moi_truong: str, tuong_tac: bool) -> bool:
    """An toan lop (1): operator PHAI go lai chinh xac ten moi truong khi
    chay tuong tac (TTY that) — chan click/Enter nham. Khi chay khong
    tuong tac (CI), yeu cau bien moi truong `QA_HARVESTER_XAC_NHAN` khop
    CHINH XAC ten moi truong thay vi hoi (khong the hoi trong CI)."""
    if not tuong_tac:
        xac_nhan_ci = os.environ.get("QA_HARVESTER_XAC_NHAN", "")
        return xac_nhan_ci == moi_truong
    print(f"\nBan sap chay canary GHI THAT (Novel/Chapter that, du la du lieu vut di) "
          f"len moi truong: {moi_truong!r}")
    tra_loi = input(f"Go lai chinh xac '{moi_truong}' de xac nhan: ")
    return tra_loi == moi_truong


def buoc_suc_khoe(api: str) -> bool:
    print("\n=== 1. Kiem tra suc khoe backend ===")
    ma, r = goi(api, "GET", "/api/health")
    ok = kt("GET /api/health tra 200", ma == 200, f"HTTP {ma}")
    if ok:
        kt("dung kho That (khong phai mock)",
           r.get("data_backend") == "appwrite", f"data_backend={r.get('data_backend')}")
    return ok


def buoc_dang_ky_tai_khoan_qa(api: str) -> Dict[str, Any]:
    print("\n=== 2. Dang ky tai khoan QA dung mot lan ===")
    dau = uuid.uuid4().hex[:8]
    email = f"qa-harvester-{dau}@example.test"
    mat_khau = "MatKhauCanaryQA12345"
    ma, r = goi(api, "POST", "/api/auth/register", {"email": email, "password": mat_khau})
    kt("dang ky tai khoan QA", ma in (200, 201) and "token" in r, f"HTTP {ma}")
    return {"email": email, "mat_khau": mat_khau, "token": r.get("token", ""),
            "user_id": (r.get("profile") or {}).get("user_id", ""), "dau": dau}


def buoc_scraper_discover_va_chay(
        api: str, admin_token: str, source_url: str, chapter_limit: int,
        max_chu_ky: int = 20,
) -> Optional[Dict[str, Any]]:
    """Discovery -> (xac nhan neu la nguon moi) -> tao run -> drive den
    khi co it nhat `chapter_limit` muc REVIEW_READY hoac dot ket thuc.
    KHONG mass-crawl: `chapter_limit` duoc truyen thang cho `plan_run`
    (gioi han o TANG PIPELINE, khong chi gioi han so lan goi drive)."""
    print("\n=== 3. Story Harvester: discovery ===")
    ma, r = goi(api, "POST", "/api/admin/scraper/discover", {"url": source_url}, admin_token)
    if not kt("POST /api/admin/scraper/discover", ma == 200, f"HTTP {ma}: {r}"):
        return None

    if not r.get("supported"):
        print("  Nguon CHUA duoc cau hinh — xac nhan de xuat (Phase 2)...")
        ma, r2 = goi(api, "POST", "/api/admin/scraper/confirm-source",
                    {"url": source_url}, admin_token)
        if not kt("POST /api/admin/scraper/confirm-source", ma == 200,
                  f"HTTP {ma}: {r2}"):
            return None

    print("\n=== 4. Story Harvester: tao + drive ScrapeRun (bi chan) ===")
    ma, r = goi(api, "POST", "/api/admin/scraper/runs",
               {"url": source_url, "chapter_limit": chapter_limit}, admin_token)
    if not kt("POST /api/admin/scraper/runs", ma in (200, 201), f"HTTP {ma}: {r}"):
        return None
    run = r.get("run") or {}
    run_id = run.get("run_id", "")
    if not kt("nhan duoc run_id", bool(run_id)):
        return None

    for vong in range(max_chu_ky):
        ma, r = goi(api, "GET", f"/api/admin/scraper/runs/{run_id}", None, admin_token)
        if ma != 200:
            break
        trang_thai = (r.get("run") or {}).get("status", "")
        so_review_ready = (r.get("run") or {}).get("count_review_ready", 0)
        print(f"    chu ky {vong}: status={trang_thai} review_ready={so_review_ready}")
        if trang_thai in ("completed", "partial", "cancelled", "failed"):
            break
        if so_review_ready >= chapter_limit:
            break
        goi(api, "POST", f"/api/admin/scraper/runs/{run_id}/drive", {}, admin_token)
        time.sleep(1)

    ma, r = goi(api, "GET", f"/api/admin/scraper/runs/{run_id}", None, admin_token)
    kt("doc lai trang thai run cuoi cung", ma == 200, f"HTTP {ma}")
    return {"run_id": run_id, "run_view": r}


def buoc_duyet_va_ghi_that(
        api: str, service_token: str, run_view: Dict[str, Any], chapter_limit: int,
        source_url: str, dry_run: bool, canary_run_id: str,
) -> Optional[str]:
    """"Duyet" cac muc REVIEW_READY + `quality_passed` (toi da
    `chapter_limit` muc) — TAI LAI + TRICH XUAT LAI noi dung that su
    (xem "CO Y BO SOT" o docstring dau tep: kho khong luu clean_text) roi
    ghi THAT vao Novel/Chapter qua API cong khai. Tra ve `novel_id` da
    tao (hoac `None` neu chua tao gi/dry-run) de buoc don fixture biet
    chinh xac phai xoa gi."""
    print("\n=== 5. 'Duyet' + tai lai noi dung that (kho khong luu clean_text) ===")
    muc = [m for m in (run_view.get("items") or [])
          if m.get("status") == "review_ready" and m.get("quality_passed")]
    muc = muc[:chapter_limit]
    if not kt(f"co it nhat 1 muc REVIEW_READY + quality_passed (gioi han {chapter_limit})",
              len(muc) > 0, f"tim thay {len(muc)}"):
        return None

    sys.path.insert(0, os.getcwd())
    from server.scraper import site_registry
    from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
    from server.scraper.adapters.json_ld_adapter import JsonLdAwareAdapter
    from server.scraper.contract import SeriesInfo
    from server.scraper.http_fetcher import HttpFetcher

    cfg = site_registry.lookup(source_url)
    noi_dung_chuong: List[Tuple[str, str]] = []  # (tieu_de, clean_text)
    if cfg is not None:
        fetcher = HttpFetcher()
        adapter = JsonLdAwareAdapter(
            fetcher, chapter_href_pattern=cfg.chapter_href_pattern,
            title_suffix_to_strip=cfg.title_suffix_to_strip)
        series_gia = SeriesInfo(canonical_url=source_url, title="", source_domain="",
                                chapter_urls=[m["chapter_url"] for m in muc])
        for m in muc:
            try:
                raw = adapter.fetch_chapter(m["chapter_url"])
                chuong = adapter.normalize_chapter(m["chapter_url"], raw, series_gia)
                noi_dung_chuong.append((chuong.chapter_title, chuong.clean_text))
            except Exception as exc:
                kt(f"tai lai chuong {m['chapter_url']}", False, f"{type(exc).__name__}: {exc}")
    else:
        kt("nguon co cau hinh xac minh (site_registry) de tai lai an toan", False,
          "nguon chua duoc xac nhan qua site_registry — tu choi tai lai tu dong, "
          "xem docstring Phase 5/2 ve ly do can cau hinh xac minh truoc")
        return None

    if not kt("tai lai + trich xuat duoc dung so chuong da duyet",
              len(noi_dung_chuong) == len(muc),
              f"mong {len(muc)}, duoc {len(noi_dung_chuong)}"):
        return None

    if dry_run:
        print("\n  --dry-run: SE TAO Novel + "
              f"{len(noi_dung_chuong)} Chapter, KHONG ghi gi ca. Xem truoc:")
        for tieu_de, text in noi_dung_chuong:
            print(f"    - {tieu_de!r} ({len(text)} ky tu)")
        return None

    print("\n=== 6. Ghi THAT vao Novel/Chapter (trang thai draft, KHONG publish) ===")
    dau = uuid.uuid4().hex[:8]
    # Be mat canary RIENG, khong phai `/api/novels` chung: token dich vu khong
    # phai tai khoan nguoi dung va co chu y KHONG mo duoc duong ghi chung.
    ma, r = goi(api, "POST", "/api/admin/canary/novels",
               {"title": f"{TIEN_TO_QA} {dau}", "description": f"nguồn: {source_url}",
                "canary_run_id": canary_run_id},
               service_token)
    if not kt("POST /api/admin/canary/novels", ma in (200, 201), f"HTTP {ma}: {r}"):
        return None
    novel = r.get("novel") or r
    novel_id = novel.get("novel_id", "")
    if not kt("nhan duoc novel_id", bool(novel_id)):
        return None
    kt("novel moi tao o trang thai draft (chua publish)",
      novel.get("state", "draft") == "draft", f"state={novel.get('state')}")

    so_chuong_tao_thanh_cong = 0
    for i, (tieu_de, text) in enumerate(noi_dung_chuong, start=1):
        ma, r = goi(api, "POST", f"/api/admin/canary/novels/{novel_id}/chapters",
                   {"canary_run_id": canary_run_id,
                    "title": f"{TIEN_TO_QA} {tieu_de}",
                    "content": text, "order_index": i}, service_token)
        if kt(f"POST canary chapters ({i}/{len(noi_dung_chuong)})", ma in (200, 201),
             f"HTTP {ma}"):
            so_chuong_tao_thanh_cong += 1
    kt("tao dung so chuong da duyet", so_chuong_tao_thanh_cong == len(noi_dung_chuong),
      f"mong {len(noi_dung_chuong)}, tao duoc {so_chuong_tao_thanh_cong}")

    print("\n=== 7. Xac minh qua API cong khai/rieng tu ===")
    ma, r = goi(api, "GET",
               f"/api/admin/canary/novels/{novel_id}?canary_run_id={canary_run_id}",
               None, service_token)
    novel_doc_lai = (r or {}).get("novel") or {}
    kt("GET lai novel vua tao",
      ma == 200 and novel_doc_lai.get("title", "").startswith(TIEN_TO_QA),
      f"HTTP {ma}")
    ma, r = goi(api, "GET", "/api/novels")
    novels_cong_khai = r.get("novels", []) if ma == 200 else []
    kt("novel KHONG xuat hien tren duong cong khai (van la draft)",
      not any(n.get("novel_id") == novel_id for n in novels_cong_khai),
      f"HTTP {ma}")
    return novel_id


def don_fixture(api: str, service_token: str, novel_id: Optional[str],
                canary_run_id: str) -> None:
    print("\n=== 8. Don fixture ===")
    if not novel_id:
        kt("khong co novel_id de don (chua tao gi hoac dry-run)", True)
        return
    try:
        # `canary_run_id` la BAT BUOC: server tu choi xoa neu khong chung minh
        # duoc doi tuong thuoc dung lan chay nay.
        ma, r = goi(api, "DELETE",
                   f"/api/admin/canary/novels/{novel_id}"
                   f"?canary_run_id={canary_run_id}", None, service_token)
        kt("xoa novel QA va moi thu phu thuoc", ma in (200, 204), f"HTTP {ma}: {r}")
    except Exception as exc:
        kt("don fixture that bai (loi PHU)", False, f"{type(exc).__name__}: {exc}")
        print(f"  CANH BAO: co the con fixture '{TIEN_TO_QA}' tren server, "
              f"can don thu cong bang novel_id={novel_id!r}.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--api", required=True, help="URL goc backend, vd https://fas-prod-api.onrender.com")
    p.add_argument("--environment", required=True,
                  help="Ten moi truong dang nham toi (BAT BUOC go tuong minh, khong mac dinh)")
    p.add_argument("--admin-token", required=True,
                  help="Bearer token cua MOT tai khoan admin CO SAN — KHONG BAO GIO hardcode, "
                       "luon dua qua bien moi truong/doi so luc chay")
    p.add_argument("--source-url", required=True,
                  help="URL trang muc luc cong khai, nho, KHONG phai mot trong 13 series that")
    p.add_argument("--chapter-limit", type=int, default=2,
                  help="So chuong toi da se quet+duyet+ghi (mac dinh 2 — KHONG mass crawl)")
    p.add_argument("--dry-run", action="store_true",
                  help="Chay het qua buoc 5 (tai lai + trich xuat), KHONG ghi Novel/Chapter that")
    p.add_argument("--yes", action="store_true",
                  help="Bo qua xac nhan tuong tac (CHI dung khi QA_HARVESTER_XAC_NHAN da dat dung)")
    p.add_argument("--json", metavar="FILE", help="ghi ket qua ra file JSON")
    a = p.parse_args(argv)

    print(f"Story Harvester V3 — canary direct-to-web\n  api={a.api}\n"
          f"  environment={a.environment}\n  source_url={a.source_url}\n"
          f"  chapter_limit={a.chapter_limit}\n  dry_run={a.dry_run}")

    if a.chapter_limit > 10:
        print("TU CHOI: --chapter-limit qua 10 — canary nay KHONG danh cho mass crawl.")
        return 2

    tuong_tac = sys.stdin.isatty() and not a.yes
    if not _xac_nhan_moi_truong(a.environment, tuong_tac):
        print("TU CHOI: khong xac nhan duoc dung moi truong — dung lai, khong lam gi ca.")
        return 2

    novel_id: Optional[str] = None
    # Mot dinh danh DUY NHAT cho lan chay nay. Server gan no thanh nhan BAT
    # BIEN tren moi doi tuong canary tao ra, va doi hoi dung nhan do khi don —
    # nho vay mot lan chay khong the don do cua lan khac, va khong lan nao
    # cham duoc vao mot Novel that.
    canary_run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    print(f"  canary_run_id = {canary_run_id}")
    try:
        if not buoc_suc_khoe(a.api):
            return 1
        # KHONG con dang ky tai khoan QA: Phase 15 chay bang DANH TINH DICH VU,
        # khong phai phien dang nhap cua mot nguoi.
        ket_qua_scrape = buoc_scraper_discover_va_chay(
            a.api, a.admin_token, a.source_url, a.chapter_limit)
        if ket_qua_scrape is None:
            return 1

        novel_id = buoc_duyet_va_ghi_that(
            a.api, a.admin_token, ket_qua_scrape["run_view"], a.chapter_limit,
            a.source_url, a.dry_run, canary_run_id)
    finally:
        don_fixture(a.api, a.admin_token, novel_id, canary_run_id)

    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== TOM TAT: {so_dat}/{so_tong} kiem tra DAT ===")
    for ten, ok, ghi_chu in KET_QUA:
        if not ok:
            print(f"  HONG: {ten} — {ghi_chu}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"api": a.api, "environment": a.environment,
                      "source_url": a.source_url, "dry_run": a.dry_run,
                      "ket_qua": [{"ten": t, "dat": ok, "ghi_chu": g} for t, ok, g in KET_QUA]},
                     f, ensure_ascii=False, indent=2)

    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())

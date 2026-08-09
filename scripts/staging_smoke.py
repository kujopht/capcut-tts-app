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


def _ep_utf8() -> None:
    """
    Ep stdout/stderr ve UTF-8 NGAY khi nap module.

    Console Windows mac dinh la cp1252. Mot dong ket qua co dau tieng Viet —
    vi du tieu de chuong "[SMOKE] Chương đã sửa" — se nem `UnicodeEncodeError`
    va lam SAP ca script giua chung.

    Da gap that: script chet o `kt()`, tuc la ngoai khoi `try` cua `main()`,
    nen `ids` chua kip tra ve va buoc don dep khong biet phai xoa gi. Fixture
    `[SMOKE]` nam lai tren staging.

    `errors="replace"` de mot ky tu la khong bao gio quan trong hon viec chay
    het bai kiem thu.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()

KET_QUA = []

#: Ai dang goi. GUI O MOI REQUEST.
#:
#: Cloudflare chan thang User-Agent mac dinh cua urllib (`Python-urllib/3.12`)
#: bang 403 truoc khi request toi duoc ung dung — do bang tay: cung mot URL,
#: urllib mac dinh tra 403 con `curl` tra 200, va header `server` la
#: `cloudflare`. Frontend hoan toan lanh manh; chi la client khong tu gioi thieu.
#:
#: KHONG gia lam trinh duyet. Mao danh Chrome de di qua rao chong bot la noi doi
#: voi ha tang cua chinh minh, va se vo hieu ngay khi rao do sieu chat hon. Mot
#: chuoi trung thuc, co ten cong cu va duong dan nguon, cung duoc chap nhan —
#: da kiem: `fanfic-audio-smoke/1.0` tra 200.
USER_AGENT = "fanfic-audio-smoke/1.0 (+https://github.com/kujopht/capcut-tts-app)"


class KhongDangNhapDuoc(RuntimeError):
    """Khong lay duoc token — dung som nhung van phai don dep."""


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


def goi_tho(base: str, method: str, path: str,
            token: Optional[str] = None, timeout: int = 300):
    """
    Nhu `goi` nhung tra ve BYTE THO va header, khong giai ma JSON.

    Can cho hai cho: doc bundle JS cua frontend, va kiem `Content-Type` cua
    audio — hai thu khong phai JSON.
    """
    req = urllib.request.Request(base.rstrip("/") + path, method=method)
    req.add_header("User-Agent", USER_AGENT)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except Exception:
        return 0, b"", {}


def goi(base: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 300) -> Tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
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
            return exc.code, {"raw": body[:200]}
    except Exception as exc:
        # Giu LOAI loi lai. Truoc day cho nay tra ve 0 tron, nen dau ra chi noi
        # "HTTP 0" — khong the biet la het gio, DNS hong hay TLS dut, va viec
        # chan doan phai lam lai tu dau bang tay.
        return 0, {"loi": type(exc).__name__}


def vi_sao(ma: int, r: Any) -> str:
    """Mo ta ngan gon ket qua mot lan goi, co ca ly do khi that bai."""
    if ma:
        return f"HTTP {ma}"
    loai = (r or {}).get("loi") if isinstance(r, dict) else None
    return f"khong ket noi duoc ({loai or 'khong ro'})"


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'DAT ' if ok else 'HONG'}] {ten}" + (f"  — {ghi_chu}" if ghi_chu else ""),
          flush=True)
    return ok


# ---------------------------------------------------------------- cac buoc


def danh_thuc(base: str, ten: str, cho_toi_da: int, duong: str = "/") -> bool:
    """
    Danh thuc mot service dang ngu.

    Web service goi Free cua Render NGU sau 15 phut khong co traffic; request
    dau tien sau do mat khoang 50 giay. Khong cho thi smoke test se bao "khong
    ket noi duoc" trong khi service hoan toan lanh manh — mot ket luan sai.

    Day KHONG phai "tang timeout cho qua": no cho MOT dieu kien cu the (service
    tra loi) chu khong ngu mot khoang co dinh, va no in ro da phai cho bao lau.
    """
    t0 = time.time()
    lan = 0
    while time.time() - t0 < cho_toi_da:
        lan += 1
        # `goi_tho` chu khong `goi`: frontend tra ve HTML, va `goi` se nem
        # JSONDecodeError roi bien no thanh "khong ket noi duoc" — mot ket luan
        # sai ve mot service hoan toan khoe manh.
        ma, _, _ = goi_tho(base, "GET", duong, timeout=60)
        if ma and ma < 500:
            cho = round(time.time() - t0)
            if cho > 3:
                print(f"     ({ten} vua tinh giac sau {cho}s, {lan} lan thu — "
                      f"binh thuong voi goi Free)")
            return True
        time.sleep(3)
    print(f"     ({ten} khong tra loi sau {cho_toi_da}s)")
    return False


def buoc_suc_khoe(api: str, sha_mong: Optional[str],
                  moi_truong: str) -> Dict[str, Any]:
    print("\n=== 1. Health / readiness ===")
    ma, h = goi(api, "GET", "/api/health")
    kt("GET /api/health tra 200", ma == 200, f"HTTP {ma}")
    kt(f"moi truong la {moi_truong}",
       h.get("environment", "").lower() == moi_truong.lower(),
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
    tk: Dict[str, Any] = {
        "a": f"smoke-a-{dau}@example.test", "b": f"smoke-b-{dau}@example.test",
        "mk": "MatKhauSmoke12345", "dau": dau, "tai_khoan": []}
    for vai in ("a", "b"):
        ma, r = goi(api, "POST", "/api/auth/register",
                    {"email": tk[vai], "password": tk["mk"]})
        kt(f"dang ky tai khoan {vai.upper()}", ma in (200, 201) and "token" in r,
           f"HTTP {ma}")
        tk[f"tok_{vai}"] = r.get("token", "")
        # Ghi lai id NGAY: buoc don dep phai xoa theo id, khong tim theo email.
        uid = (r.get("profile") or {}).get("user_id", "")
        if uid:
            tk.setdefault("tai_khoan", []).append((uid, tk[vai]))

    ma, r = goi(api, "POST", "/api/auth/login", {"email": tk["a"], "password": tk["mk"]})
    kt("dang xuat roi dang nhap lai", ma == 200 and "token" in r, f"HTTP {ma}")
    # `.get` chu khong truy cap thang bang khoa: dang nhap hong thi phan hoi la
    # `{"detail": ...}`, khong co khoa `token`, va cach cu nem KeyError lam ca
    # script sap giua chung — luc do buoc don dep khong chay va fixture
    # `[SMOKE]` nam lai tren staging cho lan sau doc phai.
    #
    # KHONG lui ve token cua buoc dang ky. Lui nhu vay thi script chay tiep nhu
    # the khong co gi xay ra, trong khi dieu vua duoc khang dinh — "dang xuat
    # roi dang nhap lai duoc" — da that bai. Sai o dau thi dung o day.
    tk["tok_a"] = r.get("token", "")

    if not tk.get("tok_a"):
        # Khong co token thi moi buoc sau deu se hong theo, va thong bao that su
        # huu ich da nam o dong tren roi. Dung som, nhung van di qua `finally`
        # cua `main()` de don nhung gi da tao.
        raise KhongDangNhapDuoc(
            "khong lay duoc token cho tai khoan A — cac buoc sau bi bo qua")

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

    # Ba cau, co y NGAN: phep thu nay do duong di cua he thong, khong do suc
    # chiu tai. Chuong dai chi lam moi lan chay lau hon ma khong khang dinh
    # them dieu gi.
    NOI_DUNG = ("Con tàu rời bến khi trời vừa hửng sáng. "
                "Gió biển mang theo vị mặn quen thuộc. "
                "Cả đoàn im lặng nhìn về phía chân trời.")
    ma, r = goi(api, "POST", "/api/chapters",
                {"novel_id": nid, "title": "[SMOKE] Chương", "content": NOI_DUNG,
                 "order_index": 1}, tok)
    kt("tao chapter", ma in (200, 201), f"HTTP {ma}")
    cid = r["chapter"]["chapter_id"]

    # "Refresh" = doc lai tu server bang mot token MOI, khong dua vao bo nho client.
    #
    # CUNG MOT LOAI LOI voi cho o `buoc_xac_thuc`: dang nhap hong thi phan hoi
    # la `{"detail": ...}` chu khong co `token`, va `r["token"]` se nem
    # KeyError giua chung. Luc do `ids` chua duoc tra ve, nen `main()` khong
    # biet novel/chapter vua tao la gi va KHONG xoa duoc chung — fixture
    # `[SMOKE]` nam lai tren staging.
    ma_dn, r = goi(api, "POST", "/api/auth/login",
                   {"email": tk["a"], "password": tk["mk"]})
    tok2 = r.get("token", "")
    if not kt("dang nhap lai de doc lai du lieu", bool(tok2), f"HTTP {ma_dn}"):
        # Khong doc lai duoc thi khong khang dinh duoc gi ve tinh ben vung.
        # Van tra ve `ids` de nhung thu vua tao con duoc don.
        return {"novel": nid, "chapter": cid}
    ma, r = goi(api, "GET", f"/api/novels/{nid}", None, tok2)
    kt("doc lai sau khi dang nhap lai: du lieu con nguyen",
       ma == 200 and len(r.get("chapters", [])) == 1, f"HTTP {ma}")
    kt("tieu de duoc luu ben vung",
       r.get("novel", {}).get("title") == f"[SMOKE] {tk['dau']}")

    # -- cap nhat roi doc lai ---------------------------------------------
    # Tao roi doc lai thi chi chung minh duong GHI chay. Sua roi doc lai moi
    # chung minh ban ghi that su duoc CAP NHAT chu khong phai tra ve ban cu
    # tu mot lop dem nao do.
    TIEU_DE_MOI = "[SMOKE] Chương đã sửa"
    ma, _ = goi(api, "PATCH", f"/api/chapters/{cid}",
                {"title": TIEU_DE_MOI}, tok)
    kt("cap nhat chapter", ma == 200, f"HTTP {ma}")
    ma, r = goi(api, "GET", f"/api/chapters/{cid}", None, tok2)
    kt("doc lai thay tieu de moi",
       r.get("chapter", {}).get("title") == TIEU_DE_MOI,
       f"{r.get('chapter', {}).get('title')!r}")
    kt("noi dung khong bi cap nhat lam hong",
       r.get("chapter", {}).get("content") == NOI_DUNG)

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

    # KHONG khang dinh `attempts == 1`. Mot chuong ngan van co the vuot lease 90
    # giay khi may dang tai nang hoac Edge TTS cham, va luc do recovery vao cuoc
    # — dung nhu thiet ke. Dieu thuc su quan trong la job ket thuc DUNG MOT LAN
    # va sinh ra dung mot track / mot object, chu khong phai no chua bao gio
    # phai thu lai.
    so_lan = j.get("attempts") or 0
    kt("so lan thu nam trong gioi han", 1 <= so_lan <= 3, f"attempts={so_lan}")
    if so_lan > 1:
        print(f"     (da thu lai {so_lan} lan — lease het han giua chung, "
              "recovery da xu ly; ket qua van phai la mot track duy nhat)")

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


def buoc_danh_sach_giong(api: str, giong_cuc_bo: str,
                         suc_khoe: Dict[str, Any]) -> None:
    """
    `/api/voices` phai dung pham vi san pham: CHI tieng Viet, dung bay giong de xuat.

    Kiem hoan toan qua HTTP — khong import `desktop_app`, de script chay duoc tu
    bat ky may nao chi voi URL.
    """
    print("\n=== 6. Danh sach giong: pham vi tieng Viet + muc de xuat ===")
    ma, r = goi(api, "GET", "/api/voices")
    if not kt("lay duoc danh sach giong", ma == 200, vi_sao(ma, r)):
        return
    vs = r.get("voices", [])
    kt("co giong de dung", len(vs) > 7, f"{len(vs)} giong")

    ngoai = sorted({v.get("language", "") for v in vs
                    if not str(v.get("language", "")).lower().startswith("vi")})
    kt("KHONG co giong nao khac tieng Viet", not ngoai,
       f"lot ra: {ngoai}" if ngoai else "toan bo vi-*")

    dx = sorted((v for v in vs if v.get("recommended")),
                key=lambda v: v.get("recommended_order", 99))

    # SO GIONG DE XUAT SUY TU CAU HINH, khong go cung 7.
    #
    # App desktop khai bay giong de xuat, trong do DUNG MOT giong chay cuc bo
    # (`piper:ngochuyen`). Production tat giong cuc bo (`FAS_LOCAL_VOICES=""`),
    # nen o do dung con sau — va do la ket qua DUNG, khong phai loi. Go cung 7
    # se bien mot cau hinh hop le thanh mot lan do that bai.
    #
    # `local_voices` lay tu `/api/health`, tuc la tu chinh may chu dang kiem,
    # chu khong phai tu gia dinh cua script.
    cuc_bo_bat = [v for v in (suc_khoe.get("local_voices") or [])
                  if str(v).startswith("piper:")]
    mong = 7 if cuc_bo_bat else 6
    kt(f"dung {mong} giong de xuat", len(dx) == mong,
       f"{len(dx)} giong (local_voices={list(suc_khoe.get('local_voices') or [])})")
    kt("thu tu de xuat lien tuc tu 0",
       [v.get("recommended_order") for v in dx] == list(range(len(dx))),
       str([v.get("recommended_order") for v in dx]))
    if dx:
        print("        " + " | ".join(v.get("display_name", "?") for v in dx))

    # Giong cuc bo: khong co thi hoac chua deploy ma moi, hoac FAS_LOCAL_VOICES
    # da tat. Ca hai deu la dieu nguoi van hanh phai biet, khong duoc im lang.
    cb = next((v for v in vs if v.get("voice_id") == giong_cuc_bo), None)
    kt(f"{giong_cuc_bo} duoc chao ban", cb is not None,
       "co" if cb else "khong thay — chua deploy ma moi, hoac FAS_LOCAL_VOICES da tat")
    if cb:
        # `installed` cua API luon False (model nam tren may worker), nen giao
        # dien phai doc `runs_on_worker`. Neu co nay mat thi bo chon giong o web
        # se lang le bo qua giong nay.
        kt("giong cuc bo duoc danh dau chay tren worker",
           cb.get("runs_on_worker") is True, f"runs_on_worker={cb.get('runs_on_worker')}")
    kt("moi giong deu co co public_enabled",
       all("public_enabled" in v for v in vs))


def buoc_tu_choi_giong(api: str, tk: Dict[str, Any], ids: Dict[str, str]) -> None:
    """
    Gui thang mot `voice_id` ngoai pham vi -> 400, va KHONG tao job nao.

    Day la cho de lo hong quay lai: `/api/voices` loc o mot noi, con
    `POST /api/jobs` kiem o noi khac. Neu hai ben lech nhau thi buoc nay do.
    """
    print("\n=== 7. Giong ngoai pham vi bi tu choi ===")
    tok = tk["tok_a"]
    _, truoc = goi(api, "GET", "/api/jobs", None, tok)
    so_truoc = truoc.get("count", 0)

    for vid in ("edge:en-US-AriaNeural", "piper:mot-giong-bia-dat"):
        ma, r = goi(api, "POST", "/api/jobs",
                    {"chapter_id": ids["chapter"], "voice_id": vid}, tok)
        kt(f"tu choi {vid}", ma == 400,
           f"HTTP {ma} {str(r.get('detail', r))[:70]}")

    _, sau = goi(api, "GET", "/api/jobs", None, tok)
    kt("khong job nao duoc tao tu cac lan bi tu choi",
       sau.get("count", 0) == so_truoc,
       f"truoc={so_truoc} sau={sau.get('count')}")


def buoc_giong_cuc_bo(api: str, tk: Dict[str, Any], ids: Dict[str, str],
                      giong: str, cho_toi_da: int) -> None:
    """
    Mot job THAT bang giong chay tren may worker, chia NHIEU DOAN.

    Hai lo hong ma buoc nay bit lai, ca hai deu lam `61/61` xanh gia:

      1. Bo nghiem thu cu chi chay giong di qua mang (Edge/CapCut). Duong giong
         cuc bo — nap model, ONNX, WAV->MP3 — chua bao gio duoc cham toi.
      2. Chuong smoke chi 3 cau = MOT doan, nen `_concat_mp3` khong bao gio
         chay. Mot may thieu ffmpeg van cho 61/61 xanh, roi hong o chuong dai
         that. `chunk_chars` nho o day ep ra nhieu doan de duong ghep bi chay.

    Piper chay cuc bo nen buoc nay KHONG ton quota cua nha cung cap nao.
    """
    print("\n=== 8. Giong cuc bo (nhieu doan, co ghep ffmpeg) ===")
    tok = tk["tok_a"]

    # Du dai de chia duoc >= 2 doan voi `chunk_chars` nho. Van ngan de mot lan
    # chay khong keo dai: Piper tren CPU khoang 0,14 giay tinh toan cho moi
    # giay audio.
    van = ("Con thuyền nhỏ trôi giữa màn sương sớm. "
           "Tiếng mái chèo khua nước đều đặn vang lên trong tĩnh lặng. "
           "Phía xa, ngọn hải đăng vẫn kiên nhẫn quét những vòng sáng cuối cùng. "
           "Người lái đò khẽ hát một khúc dân ca quen thuộc. ") * 2
    ma, r = goi(api, "POST", "/api/chapters",
                {"novel_id": ids["novel"], "title": "[SMOKE] Chương giọng cục bộ",
                 "content": van, "order_index": 2}, tok)
    if not kt("tao chuong cho giong cuc bo", ma in (200, 201), vi_sao(ma, r)):
        return
    cid = r["chapter"]["chapter_id"]
    ids["chapter_cuc_bo"] = cid

    ma, r = goi(api, "POST", "/api/jobs",
                {"chapter_id": cid, "voice_id": giong, "chunk_chars": 300}, tok)
    if not kt(f"tao job voi {giong}", ma in (200, 201, 202), vi_sao(ma, r)):
        return
    jid = r["job"]["job_id"]

    cuoi, j = None, {}
    t0 = time.time()
    while time.time() - t0 < cho_toi_da:
        _, r = goi(api, "GET", f"/api/jobs/{jid}", None, tok)
        j = r.get("job", {})
        if j.get("status") != cuoi:
            cuoi = j.get("status")
            print(f"        t+{round(time.time() - t0):>4}s  {cuoi}  "
                  f"{j.get('done_parts')}/{j.get('total_parts')}", flush=True)
        if cuoi in ("completed", "failed"):
            break
        time.sleep(3)

    if not kt("job giong cuc bo hoan tat", cuoi == "completed",
              f"trang thai cuoi={cuoi} error_kind={j.get('error_kind')!r}"):
        print("     (worker cuc bo co dang chay khong? job nam `pending` la "
              "dung thiet ke khi may tao giong dang tat)")
        return

    kt("chia duoc NHIEU doan (duong ghep ffmpeg da chay)",
       (j.get("total_parts") or 0) >= 2, f"total_parts={j.get('total_parts')}")
    kt("chi chay dung mot lan", (j.get("attempts") or 0) == 1,
       f"attempts={j.get('attempts')}")

    ma, r = goi(api, "GET", f"/api/audio/{cid}/url", None, tok)
    kt("xin duoc URL audio giong cuc bo", ma == 200, f"HTTP {ma}")
    try:
        with urllib.request.urlopen(r.get("url", ""), timeout=300) as x:
            noi_dung = x.read()
        kt("tai duoc audio giong cuc bo", len(noi_dung) > 10_000,
           f"{len(noi_dung)} byte")
        kt("la MP3 that",
           noi_dung[:3] == b"ID3" or noi_dung[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
           f"byte dau: {noi_dung[:3].hex()}")
    except Exception as exc:
        kt("tai duoc audio giong cuc bo", False, type(exc).__name__)


def buoc_phan_quyen(api: str, tk: Dict[str, Any], ids: Dict[str, str]) -> None:
    print("\n=== 9. Phan quyen giua hai tai khoan ===")
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


def buoc_giao_dien(web: Optional[str], api: str) -> None:
    print("\n=== 10. Frontend phan hoi va tro dung API ===")
    if not web:
        kt("bo qua: chua truyen --web", True, "khong kiem duoc")
        return
    # Danh thuc LAI: buoc nay chay sau phan TTS, co the da vai phut troi qua va
    # service goi Free ngu lai. Day khong phai retry mu — no cho dung mot dieu
    # kien, giong het buoc 0.
    danh_thuc(web, "frontend", 120, "/")
    for duong in ("/", "/fanfic", "/login"):
        # `goi_tho`: cac duong nay tra HTML. Dung `goi` thi JSONDecodeError bi
        # bat vao nhanh loi chung va bao cao thanh "khong ket noi duoc" — che
        # mat su that la service tra ve 200 hoan hao.
        ma, than, _ = goi_tho(web, "GET", duong, timeout=120)
        kt(f"GET {duong} tra 200", ma == 200,
           f"HTTP {ma}, {len(than)} byte" if ma else "khong ket noi duoc")

    # Frontend tro nham API la mot loi im lang: trang van tai duoc, chi la moi
    # thao tac deu that bai. `NEXT_PUBLIC_API_BASE` duoc noi thang vao bundle
    # luc build, nen doc bundle la biet chac no tro vao dau.
    import re

    _, body, _ = goi_tho(web, "GET", "/", timeout=180)
    html = body.decode("utf-8", "replace")
    goc_api = urllib.parse.urlsplit(api).netloc

    # Frontend da build voi MOT `NEXT_PUBLIC_API_BASE` co dinh. Doi chieu no voi
    # mot `--api` tro localhost la vo nghia: dang so hai thu khac nhau, va phep
    # thu se "hong" trong khi ca hai deu lanh manh. Noi ro thay vi bao dong sai.
    cuc_bo = goc_api.split(":")[0] in ("localhost", "127.0.0.1", "[::1]")
    if cuc_bo:
        kt("bo qua doi chieu bundle: --api tro cuc bo", True,
           f"bundle cua {urllib.parse.urlsplit(web).netloc} tro toi backend da "
           "trien khai, khong phai --api dang kiem")
    else:
        thay = goc_api in html
        if not thay:
            for c in list(dict.fromkeys(
                    re.findall(r'/_next/static/[^"\']+\.js', html)))[:25]:
                m, b, _ = goi_tho(web, "GET", c, timeout=120)
                if m == 200 and goc_api.encode() in b:
                    thay = True
                    break
        kt("bundle tro dung API dang kiem", thay,
           f"tim host cua --api trong HTML va cac chunk JS")
    kt("bundle khong con tro localhost", "localhost:8000" not in html)


def buoc_dang_xuat(api: str, tk: Dict[str, Any]) -> None:
    """
    Dang xuat phai ket thuc phien o PHIA MAY CHU.

    Xoa token trong trinh duyet thoi la chua du: credential van song, va ai
    nhat duoc no van dung tiep duoc. Chay CUOI CUNG vi no lam token cua A het
    gia tri — moi buoc can token phai xong truoc.
    """
    print("\n=== 11. Dang xuat va het quyen ===")
    tok = tk.get("tok_a", "")
    ma, _ = goi(api, "GET", "/api/auth/me", None, tok)
    if not kt("truoc khi dang xuat: token con dung duoc", ma == 200, f"HTTP {ma}"):
        return          # khong co moc thi buoc duoi khong noi len dieu gi

    ma, r = goi(api, "POST", "/api/auth/logout", None, tok)
    kt("POST /api/auth/logout ton tai", ma not in (404, 405), f"HTTP {ma}")
    kt("may chu bao da huy phien", r.get("da_huy_phien") is True,
       f"da_huy_phien={r.get('da_huy_phien')}")

    ma, _ = goi(api, "GET", "/api/auth/me", None, tok)
    kt("sau khi dang xuat: token HET gia tri", ma == 401, f"HTTP {ma}")
    ma, _ = goi(api, "GET", "/api/novels?mine=true", None, tok)
    kt("duong rieng tu cung tu choi token da dang xuat", ma == 401, f"HTTP {ma}")

    ma, r = goi(api, "POST", "/api/auth/login",
                {"email": tk["a"], "password": tk["mk"]})
    kt("van dang nhap lai duoc sau khi dang xuat", ma == 200 and "token" in r,
       f"HTTP {ma}")
    tk["tok_a"] = r.get("token", "")      # token moi cho buoc don dep


def don_dep(api: str, tk: Dict[str, Any], ids: Optional[Dict[str, str]]) -> None:
    print("\n=== 12. Don fixture ===")
    if not ids:
        kt("khong co fixture nao de don", True)
        return
    ma, r = goi(api, "DELETE", f"/api/novels/{ids['novel']}", None, tk.get("tok_a"))
    da_xoa = r.get("removed", {}) or {}
    kt("xoa truyen [SMOKE] va moi thu phu thuoc", ma in (200, 204),
       f"HTTP {ma} {json.dumps(da_xoa, ensure_ascii=False)}")

    # Doi soat theo SO chuong da tao, khong doan. Buoc giong cuc bo tao them
    # chuong thu hai; neu no khong nam trong danh sach vua xoa thi audio va
    # object cua no o lai tren staging ma khong ai bao.
    mong = 2 if ids.get("chapter_cuc_bo") else 1
    kt("xoa dung so chuong da tao", da_xoa.get("chapters") == mong,
       f"mong {mong}, xoa {da_xoa.get('chapters')}")

    _, r = goi(api, "GET", "/api/novels?mine=true", None, tk.get("tok_a"))
    kt("tai khoan A khong con truyen nao", r.get("novels") == [],
       f"con {len(r.get('novels', []))}")
    _, r = goi(api, "GET", "/api/jobs", None, tk.get("tok_a"))
    kt("khong con job nao cua tai khoan A", r.get("count") == 0,
       f"con {r.get('count')}")


#: Hau to bat buoc cua email tai khoan fixture. Xem `don_tai_khoan`.
HAU_TO_FIXTURE = "@example.test"


def don_tai_khoan(tk: Dict[str, Any], moi_truong: str) -> None:
    """
    Xoa cac tai khoan fixture do CHINH luot chay nay tao ra.

    Vi sao can: khong co route xoa tai khoan trong ung dung, nen moi lan chay
    lai bo lai hai tai khoan. Sau vai chuc lan la mot dong rac phai don tay.

    BA DIEU KIEN, phai dat CA BA moi xoa:

      1. `user_id` nam trong danh sach ID ma luot nay ghi lai luc dang ky;
      2. email doc tu Appwrite KHOP CHINH XAC email da ghi;
      3. email ket thuc bang `@example.test`.

    Dieu 1 loai moi tai khoan khong phai do luot nay tao. Dieu 2 chan truong
    hop id bi ghi nham hoac bi tai su dung. Dieu 3 la luoi cuoi cung: du hai
    dieu tren cung sai thi mot tai khoan nguoi dung that van khong the bi xoa,
    vi khong ai dang ky bang ten mien do.

    TUYET DOI khong tim theo mau, khong xoa ca collection, khong wildcard.

    `moi_truong` phai KHOP voi `FAS_ENV` cua tep cau hinh dang nap. Truoc day
    buoc nay chi chay khi `FAS_ENV=staging`, nen chay tren production se lang le
    bo lai hai tai khoan. Nay production don duoc, nhung van phai TUYEN BO ro
    bang `--environment production` — khong co duong nao don nham moi truong.

    Bo qua im lang neu khong co credential: script van phai chay duoc tu bat ky
    dau chi voi HTTP API cong khai.
    """
    print("\n=== 13. Don tai khoan fixture (can credential Appwrite) ===")
    can = [(uid, em) for uid, em in tk.get("tai_khoan", []) if uid]
    if not can:
        kt("khong ghi duoc user id nao de don", False, "cac buoc tren da hong?")
        return
    try:
        import os
        import sys

        sys.path.insert(0, os.getcwd())
        from server.appwrite_store import AppwriteMetadataStore
        from server.config import load_settings

        s = load_settings()
        if s.environment.lower() != moi_truong.lower():
            kt("bo qua don tai khoan: FAS_ENV khong khop --environment", True,
               f"FAS_ENV={s.environment!r}, mong {moi_truong!r}")
            return
        kho = AppwriteMetadataStore(s.appwrite)
    except Exception as exc:
        kt("bo qua don tai khoan: khong co credential", True,
           f"{type(exc).__name__} — chay lai voi FAS_ENV_FILE=server/.env.staging")
        return

    db = s.appwrite.database_id
    for uid, em in can:
        try:
            u = kho._call("GET", f"/v1/users/{uid}")
        except Exception:
            kt(f"tai khoan {em} da khong con", True)
            continue
        thuc_te = str(u.get("email") or "")
        if thuc_te != em:
            kt(f"KHONG xoa {uid}: email khong khop", False, "dung de an toan")
            continue
        if not thuc_te.endswith(HAU_TO_FIXTURE):
            # Luoi cuoi cung. Neu roi vao day thi mot trong hai dieu kien tren
            # da sai o dau do — dung lai va bao, khong xoa.
            kt(f"KHONG xoa {uid}: email khong phai {HAU_TO_FIXTURE}", False,
               "dung de an toan")
            continue
        try:
            kho._call("DELETE", f"/v1/users/{uid}")
            try:
                kho._call("DELETE",
                          f"/v1/databases/{db}/collections/profiles/documents/{uid}")
            except Exception:
                pass          # profile co the da bi xoa theo tai khoan
            kt(f"xoa tai khoan {em}", True)
        except Exception as exc:
            kt(f"xoa tai khoan {em}", False, type(exc).__name__)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Smoke test cho ban trien khai staging.")
    p.add_argument("--api", required=True, help="URL goc cua backend, vi du https://fas-staging-api.onrender.com")
    p.add_argument("--web", help="URL goc cua frontend")
    p.add_argument("--sha", help="SHA mong doi, chi de ghi vao bao cao")
    p.add_argument("--environment", default="staging",
                   help="Moi truong MONG DOI o /api/health. Dat `production` khi "
                        "kiem ban production. Gia tri nay con quyet dinh buoc "
                        "don tai khoan duoc phep chay o dau.")
    p.add_argument("--voice", default="edge:vi-VN-HoaiMyNeural")
    p.add_argument("--local-voice", default="piper:ngochuyen",
                   help="giong chay tren may worker, dung cho buoc nhieu doan")
    p.add_argument("--skip-local-voice", action="store_true",
                   help="bo qua job giong cuc bo. CHI dung khi may tao giong "
                        "dang tat — bo qua thi duong ghep ffmpeg khong duoc "
                        "kiem, va mot may thieu ffmpeg van cho ket qua xanh.")
    p.add_argument("--job-timeout", type=int, default=600)
    p.add_argument("--json", metavar="FILE", help="ghi ket qua ra file JSON")
    p.add_argument("--wake-timeout", type=int, default=120,
                   help="cho service goi Free tinh giac bao lau (giay). "
                        "Web service Free cua Render ngu sau 15 phut khong co "
                        "traffic; request dau tien mat khoang 50 giay.")
    a = p.parse_args(argv)

    print(f"API = {a.api}")
    print(f"WEB = {a.web or '(khong kiem)'}")

    # Danh thuc TRUOC khi tinh diem: mot service dang ngu khong phai la mot
    # service hong.
    print()
    print("=== 0. Danh thuc (goi Free co the dang ngu) ===")
    kt("backend tra loi", danh_thuc(a.api, "backend", a.wake_timeout,
                                    "/api/health"))
    if a.web:
        kt("frontend tra loi", danh_thuc(a.web, "frontend", a.wake_timeout, "/"))

    tk: Dict[str, Any] = {}
    ids: Optional[Dict[str, str]] = None
    try:
        suc_khoe = buoc_suc_khoe(a.api, a.sha, a.environment)
        tk = buoc_xac_thuc(a.api)
        ids = buoc_noi_dung(a.api, tk)
        buoc_tts(a.api, tk, ids, a.voice, a.job_timeout)
        buoc_danh_sach_giong(a.api, a.local_voice, suc_khoe)
        buoc_tu_choi_giong(a.api, tk, ids)
        if a.skip_local_voice:
            kt("bo qua job giong cuc bo (--skip-local-voice)", True,
               "may tao giong dang tat?")
        else:
            buoc_giong_cuc_bo(a.api, tk, ids, a.local_voice, a.job_timeout)
        buoc_phan_quyen(a.api, tk, ids)
        buoc_giao_dien(a.web, a.api)
        buoc_dang_xuat(a.api, tk)
    except KhongDangNhapDuoc as exc:
        print()
        print(f"  DUNG SOM: {exc}")
    finally:
        # Don du co buoc nao hong: khong de fixture lai tren staging.
        if tk.get("tok_a"):
            don_dep(a.api, tk, ids)
        don_tai_khoan(tk, a.environment)

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

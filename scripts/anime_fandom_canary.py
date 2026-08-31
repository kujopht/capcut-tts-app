"""
Anime Fanfic Production Canary — chung minh THAT: noi dung thu nghiem CO
KIEM SOAT (khong scrape tu nguon thu ba nao — xem bao cao nghien cuu nguon:
AO3/FanFiction.net/Wattpad/ScribbleHub deu bi chan quyen tac gia, ToS, hoac
ky thuat that su) -> luu spool tho cuc bo -> Google Drive archive -> phan
loai fandom that -> tao Novel/Chapter that (DRAFT) -> XUAT BAN THAT -> xac
minh mot trang cong khai that tren fanfic.world.

    PYTHONPATH=. python scripts/anime_fandom_canary.py \\
        --api https://<url-api>.onrender.com --web-base https://fanfic.world \\
        --environment production \\
        --token "$env:FAS_CANARY_BEARER_TOKEN" \\
        --rclone-remote "fanfic-gdrive:FanficWorld/archive/scraping/raw/internal-test/anime-canary"

    # Don sau khi xem xong (xoa CHINH novel vua tao — can novel_id in ra o cuoi):
    PYTHONPATH=. python scripts/anime_fandom_canary.py \\
        --api https://<url-api>.onrender.com --environment production \\
        --token "$env:FAS_CANARY_BEARER_TOKEN" --cleanup <novel_id>

CHUA CHAY DUOC O DAY (may nay khong co API/token that — xac nhan qua
`server/config.py::load_settings().appwrite.configured == False`) — kich
ban nay la phan "lam tat ca tru cuoc goi can credential" giong nguyen tac
cua `story_harvester_direct_to_web_canary.py`, CHO operator co `--api`/
`--token` that de chay lan can credential.

AN TOAN — BON LOP, giong het `story_harvester_direct_to_web_canary.py`:
  1. `--environment` BAT BUOC, phai go lai dung ten khi chay tuong tac
     (hoac khop `QA_HARVESTER_XAC_NHAN` khi khong tuong tac/CI).
  2. `--token` PHAI do operator dua vao (doi so hoac bien moi truong) —
     KHONG BAO GIO doc tu file cau hinh mac dinh/hardcode. Day la token
     cua MOT TAI KHOAN THAT (operator tu chon — khuyen nghi mot tai khoan
     QA rieng, khong phai tai khoan ca nhan) — Novel se thuoc VE tai
     khoan do, giong het mot tac gia that dang dung `/api/novels`.
  3. KHONG BAO GIO dung/xoa mot Novel DA CO SAN — `--cleanup` chi nhan
     DUNG mot `novel_id` do operator tu dan vao (thuong la gia tri kich
     ban nay vua in ra), va `DELETE /api/novels/{id}` da tu kiem tra
     quyen so huu o phia server — khong the xoa nham Novel cua nguoi khac
     du co dan sai ID.
  4. Buoc DUY NHAT trong ca session nay THAT SU goi `/publish` — moi
     canary truoc do (Router LTS, Story Harvester V3/V4/V5) co CHU DICH
     dung o DRAFT. Vi vay noi dung PHAI tu no da la vo hai: khong sao chep
     tu nguon thu ba, ghi ro TRONG CHINH VAN BAN rang day la kiem thu ha
     tang, khong phai fanfic that — mot khach ghe trang cong khai khong
     the hieu nham.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _ep_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()

USER_AGENT = "fanfic-anime-canary/1.0 (+https://github.com/kujopht/capcut-tts-app)"
TIEN_TO_CANARY = "[ANIME-CANARY-TEST]"

#: Noi dung THU NGHIEM HA TANG — nguyen ban, khong sao chep tu bat ky nguon
#: nao. Ghi ro CA hai ngon ngu TRONG CHINH VAN BAN de bat ky ai ghe trang
#: cong khai deu hieu ngay day khong phai fanfic that.
NOI_DUNG_CANARY = (
    "[ĐÂY LÀ NỘI DUNG THỬ NGHIỆM HẠ TẦNG — KHÔNG PHẢI TÁC PHẨM FANFIC THẬT.\n"
    "THIS IS INFRASTRUCTURE TEST CONTENT — NOT A REAL FANFICTION WORK.]\n\n"
    "Đoạn văn bản ngắn này tồn tại duy nhất để chứng minh đường ống "
    "\"tiếp nhận → lưu trữ thô → chuẩn hoá → phân loại fandom → hàng chờ "
    "→ xuất bản → trang công khai\" hoạt động thật, từ đầu đến cuối, trên "
    "chính fanfic.world. Nó không được scrape từ bất kỳ tác giả hay nền "
    "tảng fanfic thật nào (Archive of Our Own, FanFiction.net, Wattpad, "
    "ScribbleHub đều đã được xác minh là bị chặn về quyền tác giả, điều "
    "khoản dịch vụ, hoặc kỹ thuật — xem báo cáo nghiên cứu nguồn đi kèm "
    "phiên làm việc này). Fandom gắn với mục này (Naruto) chỉ để chứng "
    "minh bước phân loại fandom hoạt động thật, không hàm ý đây là một "
    "fanfic Naruto thật.")

KET_QUA: List = []  # type: ignore[var-annotated]


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'DAT ' if ok else 'HONG'}] {ten}" + (f" — {ghi_chu}" if ghi_chu else ""), flush=True)
    return ok


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
        return 0, {"loi": type(exc).__name__, "chi_tiet": str(exc)}


def _xac_nhan_moi_truong(moi_truong: str, tuong_tac: bool) -> bool:
    if not tuong_tac:
        return os.environ.get("QA_HARVESTER_XAC_NHAN", "") == moi_truong
    print(f"\nBạn sắp XUẤT BẢN THẬT (bước /publish, KHÔNG chỉ tạo DRAFT) "
          f"lên môi trường: {moi_truong!r}")
    tra_loi = input(f"Gõ lại chính xác '{moi_truong}' để xác nhận: ")
    return tra_loi == moi_truong


def buoc_raw_archive(rclone_remote: Optional[str]) -> bool:
    """Tot nhat co the: chay duoc thi chay that (spool cuc bo + rclone copy
    that), khong co rclone/quyen truy cap thi BAO RO va tiep tuc — day
    khong phai buoc chan ca canary, vi noi dung da o trong chinh script
    nay, khong phu thuoc Drive de tiep tuc cac buoc sau."""
    print("\n=== 1. Raw archive (spool cục bộ + Google Drive) ===")
    if not rclone_remote:
        print("  BỎ QUA: không truyền --rclone-remote.")
        return True
    try:
        import subprocess
        import tempfile
        from pathlib import Path

        _ROOT = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT))
        from server.scraper.raw_archive import fetch_and_spool_raw
        from server.scraper.http_fetcher import FixtureFetcher

        fake_url = "internal://anime-fandom-canary/naruto-test-item"
        spool_root = Path(tempfile.mkdtemp(prefix="anime-canary-spool-"))
        fetcher = FixtureFetcher({fake_url: NOI_DUNG_CANARY})
        result = fetch_and_spool_raw(fake_url, spool_root=spool_root, fetcher=fetcher,
                                     adapter_identity="anime_fandom_canary (controlled test item)")
        kt("spool cục bộ", result.raw_path.exists(), str(result.local_dir))

        copy = subprocess.run(
            ["rclone", "copy", str(result.local_dir), rclone_remote, "--checksum"],
            capture_output=True, text=True, timeout=120)
        if not kt("rclone copy", copy.returncode == 0, copy.stderr[-300:] if copy.stderr else ""):
            return True  # khong chan canary vi rclone loi
        check = subprocess.run(
            ["rclone", "check", str(result.local_dir), rclone_remote, "--one-way"],
            capture_output=True, text=True, timeout=120)
        kt("rclone check (0 differences)", "0 differences found" in (check.stderr or ""),
           (check.stderr or "")[-300:])
        return True
    except Exception as exc:
        kt("raw archive (best-effort)", False, f"{type(exc).__name__}: {exc} — bỏ qua, không chặn canary")
        return True


def buoc_tao_va_xuat_ban(api: str, token: str) -> Optional[Dict[str, Any]]:
    print("\n=== 2. Tạo Novel/Chapter thật (DRAFT) ===")
    ma, r = goi(api, "POST", "/api/novels", {
        "title": f"{TIEN_TO_CANARY} Thử nghiệm hạ tầng anime fanfic",
        "description": "Canary hạ tầng — xem nội dung chương để biết chi tiết. "
                       "Không phải fanfic thật, an toàn để gỡ bỏ bất kỳ lúc nào.",
        "tags": ["ANIME-CANARY-TEST"],
        "fandom_names": ["Naruto"],
        "publication_mode": "full_text",
        "language": "vi",
    }, token)
    if not kt("POST /api/novels", ma == 201, f"HTTP {ma}: {r}"):
        return None
    novel = r.get("novel") or {}
    novel_id = novel.get("novel_id", "")
    if not kt("nhận được novel_id", bool(novel_id)):
        return None
    kt("fandom_ids đã gán (phân loại fandom thật)", len(novel.get("fandom_ids") or []) == 1,
       str(novel.get("fandom_ids")))

    ma, r = goi(api, "POST", "/api/chapters", {
        "novel_id": novel_id,
        "title": "Chương 1 (thử nghiệm)",
        "content": NOI_DUNG_CANARY,
        "order_index": 1,
    }, token)
    if not kt("POST /api/chapters", ma == 201, f"HTTP {ma}: {r}"):
        return {"novel_id": novel_id}  # cho cleanup dung du that bai o day

    print("\n=== 3. XUẤT BẢN THẬT (/publish) ===")
    ma, r = goi(api, "POST", f"/api/novels/{novel_id}/publish", {}, token)
    if not kt("POST /api/novels/{id}/publish", ma == 200, f"HTTP {ma}: {r}"):
        if ma == 403:
            print("  GHI CHÚ: 403 ở đây thường nghĩa là FAS_AUTHOR_GATE đang BẬT trên "
                 "môi trường này và tài khoản của --token chưa được duyệt làm tác giả — "
                 "dùng token của một tài khoản tác giả ĐÃ ĐƯỢC DUYỆT thay vào đó.")
        return {"novel_id": novel_id}
    kt("state == published", (r.get("novel") or {}).get("state") == "published")
    return {"novel_id": novel_id, "published": True}


def buoc_xac_minh_cong_khai(api: str, web_base: str, novel_id: str) -> None:
    print("\n=== 4. Xác minh trang CÔNG KHAI (không kèm token) ===")
    ma, r = goi(api, "GET", f"/api/novels/{novel_id}")  # KHONG token — nguoi la
    kt("GET /api/novels/{id} không cần đăng nhập trả 200", ma == 200, f"HTTP {ma}")
    if ma == 200:
        kt("state == published (khách lạ đọc được)",
           (r.get("novel") or {}).get("state") == "published")
    trang = f"{web_base.rstrip('/')}/novels/{novel_id}"
    print(f"\n  Trang công khai thật: {trang}")


def cleanup(api: str, token: str, novel_id: str) -> int:
    print(f"\n=== Dọn: DELETE /api/novels/{novel_id} ===")
    ma, r = goi(api, "DELETE", f"/api/novels/{novel_id}", None, token)
    ok = kt("DELETE /api/novels/{id}", ma == 200, f"HTTP {ma}: {r}")
    return 0 if ok else 1


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True, help="API base thật, vd https://xxx.onrender.com")
    ap.add_argument("--web-base", default="https://fanfic.world")
    ap.add_argument("--environment", required=True)
    ap.add_argument("--token", default=os.environ.get("FAS_CANARY_BEARER_TOKEN", ""))
    ap.add_argument("--rclone-remote", default="")
    ap.add_argument("--cleanup", default="", metavar="NOVEL_ID")
    ap.add_argument("--non-interactive", action="store_true")
    a = ap.parse_args(argv)

    if not a.token:
        print("THIẾU --token (hoặc biến môi trường FAS_CANARY_BEARER_TOKEN).")
        return 2

    tuong_tac = not a.non_interactive and sys.stdin.isatty()
    if not _xac_nhan_moi_truong(a.environment, tuong_tac):
        print("Xác nhận môi trường KHÔNG khớp — dừng, không ghi gì.")
        return 1

    if a.cleanup:
        return cleanup(a.api, a.token, a.cleanup)

    buoc_raw_archive(a.rclone_remote or None)

    ket = buoc_tao_va_xuat_ban(a.api, a.token)
    if not ket:
        print("\nKHÔNG tạo được Novel — không có gì để dọn.")
        return 1
    if ket.get("published"):
        buoc_xac_minh_cong_khai(a.api, a.web_base, ket["novel_id"])

    so_hong = sum(1 for _, ok, _ in KET_QUA if not ok)
    print(f"\n=== TỔNG: {len(KET_QUA) - so_hong}/{len(KET_QUA)} bước ĐẠT ===")
    print(f"novel_id = {ket['novel_id']}")
    print(f"Dọn sau này: python scripts/anime_fandom_canary.py --api {a.api} "
         f"--environment {a.environment} --token <token> --cleanup {ket['novel_id']}")
    return 0 if so_hong == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

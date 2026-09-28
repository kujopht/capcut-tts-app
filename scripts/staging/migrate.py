"""
Migration schema CHI CHO Appwrite STAGING — pham vi HEP: dung cac collection ma PR #229
(Community/Profile) va PR #231 (Games/XP) can. KHONG sao chep du lieu production nao.

    python -m scripts.staging.migrate                 # CHI in ke hoach (mac dinh, khong ghi gi)
    python -m scripts.staging.migrate --apply         # ghi that — guard + xac minh chi doc TRUOC
    python -m scripts.staging.migrate --apply --bao-cao <tep.json>

Nguon SCHEMA: `scripts.setup_appwrite.SCHEMA` cua CHINH cay ma dang chay. Tren `main` (chua
merge #229/#231) cac collection `user_blocks` / `game_*` / `xp_progress_cas` chua co trong
SCHEMA -> duoc bao `vang_trong_cay`, KHONG bi bia ra. Chay tren mot nhanh da gop #229+#231 de
tao du.

Moi collection di qua `python -m scripts.setup_appwrite --only <id>` trong MOT tien trinh con
co moi truong `guard.moi_truong_con()` — script schema da kiem chung (idempotent, cho thuoc
tinh/index `available`) duoc dung nguyen, chi DICH la bi khoa lai.

AI Support / su co (#241/#242): V1 luu TRONG BO NHO, chua co collection Appwrite nao — dung
theo `docs/support/SUPPORT_STORAGE_PROPOSAL.md`, migration nay KHONG tao gi cho Support.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from scripts.staging import bi_mat, guard

GOC = Path(__file__).resolve().parents[2]

#: Pham vi DUY NHAT migration nay duoc cham. Thu tu = thu tu tao.
PHAM_VI: Dict[str, List[str]] = {
    # `author_stats`: dang bai cap nhat thong ke tac gia NGAY sau khi ghi bai — thieu bang nay thi
    # bai VAN duoc tao nhung request tra 503 (do that tren staging 2026-09-28).
    "nen": ["profiles", "author_stats"],
    "community_229": ["posts", "post_likes", "comments", "notifications", "content_reports",
                      "user_blocks", "user_follows", "story_follows", "moderation_events"],
    "xp": ["user_progress", "cosmetic_inventory", "xp_ledger", "achievement_unlocks", "reading_streaks",
           "quest_progress", "xp_progress_cas"],
    "games_231": ["game_rooms", "game_room_versions", "game_runs", "game_run_versions", "game_results"],
}


def moi_collection() -> List[str]:
    return [c for nhom in PHAM_VI.values() for c in nhom]


def ke_hoach(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    ra = []
    for nhom, ds in PHAM_VI.items():
        for cid in ds:
            spec = schema.get(cid)
            ra.append({"nhom": nhom, "collection": cid, "co_trong_cay": spec is not None,
                       "so_thuoc_tinh": len(spec["attributes"]) if spec else 0,
                       "so_index": len(spec["indexes"]) if spec else 0})
    return ra


def _dam_bao_database(cfg: bi_mat.CauHinhStaging) -> str:
    st, _ = guard.goi(cfg, "GET", f"/databases/{cfg.database_id}", khoa=cfg.khoa_schema)
    if st == 200:
        return "da_co"
    # Appwrite Cloud (>= 1.9) tao database kieu TablesDB; endpoint cu `POST /databases` co the
    # tra 404 (xem `setup_appwrite.ensure_database`). Thu TablesDB truoc, roi moi ve API cu.
    for path in ("/tablesdb", "/databases"):
        st, body = guard.goi(cfg, "POST", path, khoa=cfg.khoa_schema,
                             json={"databaseId": cfg.database_id, "name": "Fanfic staging (synthetic)"})
        if st in (200, 201):
            return f"da_tao ({path})"
        if st == 409:
            return "da_co"
    raise SystemExit(f"Không tạo được database {cfg.database_id!r}: HTTP {st} {(body or {}).get('message')}")


def _trang_thai_collection(cfg: bi_mat.CauHinhStaging, cid: str) -> Dict[str, Any]:
    """Doc THANG TablesDB (tien trinh nay khong cai lop dich) — staging Cloud 2.3 chi co scope nay."""
    st, body = guard.goi(cfg, "GET", f"/tablesdb/{cfg.database_id}/tables/{cid}", khoa=cfg.khoa_schema)
    if st != 200:
        return {"ton_tai": False, "http": st}
    tt = [a.get("status") for a in (body or {}).get("columns", [])]
    ti = [i.get("status") for i in (body or {}).get("indexes", [])]
    loi = [f"{c.get('key')}: {cfg.an(str(c.get('error') or ''))[:160]}" for c in (body or {}).get("columns", [])
           if c.get("status") == "failed"]
    return {"ton_tai": True, "thuoc_tinh": len(tt), "thuoc_tinh_available": tt.count("available"),
            "index": len(ti), "index_available": ti.count("available"),
            "row_security": (body or {}).get("rowSecurity"), "loi_cot": loi}


def kiem(cfg: bi_mat.CauHinhStaging, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """CHI DOC: doi chieu tung collection trong pham vi voi SCHEMA cua cay (so cot/index + available)."""
    ra = []
    for m in ke_hoach(schema):
        tt = _trang_thai_collection(cfg, m["collection"])
        ok = bool(tt.get("ton_tai")) and tt["thuoc_tinh"] == tt["thuoc_tinh_available"] == m["so_thuoc_tinh"] \
            and tt["index"] == tt["index_available"] == m["so_index"] and tt.get("row_security") is True
        ra.append({**m, "trang_thai": tt, "ok": ok})
    return ra


def chay_kiem(bao_cao: str = "") -> int:
    cfg = bi_mat.nap()
    danh_tinh = guard.xac_minh_song(cfg)
    sys.path.insert(0, str(GOC))
    from scripts.setup_appwrite import SCHEMA

    kq = kiem(cfg, SCHEMA)
    for m in kq:
        tt = m["trang_thai"]
        print(f"  {'OK ' if m['ok'] else 'LOI'} {m['collection']:<20} cột {tt.get('thuoc_tinh_available')}/"
              f"{m['so_thuoc_tinh']} · index {tt.get('index_available')}/{m['so_index']} · rowSecurity="
              f"{tt.get('row_security')}" + (f" · {tt['loi_cot']}" if tt.get("loi_cot") else ""))
    dat = sum(1 for m in kq if m["ok"])
    if bao_cao:
        Path(bao_cao).write_text(json.dumps({"danh_tinh": danh_tinh, "kiem": kq}, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    print(f"\n{dat}/{len(kq)} collection khớp SCHEMA (đủ cột + index, tất cả available, rowSecurity).")
    return 0 if dat == len(kq) else 1


def chay(apply: bool, bao_cao: str = "") -> int:
    cfg = bi_mat.nap()
    guard.kiem_dich(cfg)
    danh_tinh = guard.xac_minh_song(cfg)
    print(f"Đích: {cfg.endpoint} · project {cfg.project_id} ({guard.DICH_DUYET.ten_project}) · "
          f"database {cfg.database_id} · Appwrite {danh_tinh['appwrite_version']} · "
          f"{danh_tinh['users_total']} tài khoản (đều tổng hợp)")

    sys.path.insert(0, str(GOC))
    from scripts.setup_appwrite import SCHEMA

    kh = ke_hoach(SCHEMA)
    for m in kh:
        print(f"  [{m['nhom']:>13}] {m['collection']:<20} "
              + (f"{m['so_thuoc_tinh']} thuộc tính · {m['so_index']} index" if m["co_trong_cay"]
                 else "VẮNG trong SCHEMA của cây này (cần nhánh đã gộp #229/#231)"))
    ket: Dict[str, Any] = {"che_do": "apply" if apply else "ke_hoach", "danh_tinh": danh_tinh,
                           "ke_hoach": kh, "buoc": []}
    if not apply:
        print("\nChế độ KẾ HOẠCH — không ghi gì. Thêm --apply để chạy thật.")
        return 0

    ket["database"] = _dam_bao_database(cfg)
    print(f"Database {cfg.database_id}: {ket['database']}")
    env = guard.moi_truong_con(cfg, schema=True)
    loi = 0
    for m in kh:
        if not m["co_trong_cay"]:
            ket["buoc"].append({"collection": m["collection"], "ket_qua": "vang_trong_cay"})
            continue
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", "scripts.setup_appwrite", "--only", m["collection"]],
                           cwd=GOC, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
        dong = [cfg.an(d) for d in (p.stdout + p.stderr).splitlines() if d.strip()]
        tom = next((d for d in reversed(dong) if d.startswith("Hoàn tất")), dong[-1] if dong else "")
        tt = _trang_thai_collection(cfg, m["collection"])
        ok = p.returncode == 0 and tt.get("ton_tai") and tt["thuoc_tinh"] == tt["thuoc_tinh_available"] \
            and tt["index"] == tt["index_available"]
        loi += 0 if ok else 1
        ket["buoc"].append({"collection": m["collection"], "rc": p.returncode, "giay": round(time.time() - t0, 1),
                            "tom_tat": tom, "trang_thai": tt, "ok": bool(ok),
                            "log_cuoi": dong[-6:] if not ok else []})
        print(f"  {'OK ' if ok else 'LOI'} {m['collection']:<20} {tom} · "
              f"{tt.get('thuoc_tinh_available')}/{tt.get('thuoc_tinh')} thuộc tính, "
              f"{tt.get('index_available')}/{tt.get('index')} index available")
    if bao_cao:
        Path(bao_cao).write_text(json.dumps(ket, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(kh) - loi}/{len(kh)} collection đạt." if not loi else f"\n{loi} collection LỖI — xem báo cáo.")
    return 1 if loi else 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true", help="ghi that (mac dinh chi in ke hoach)")
    ap.add_argument("--kiem", action="store_true", help="CHI DOC: doi chieu staging voi SCHEMA cua cay")
    ap.add_argument("--bao-cao", default="", help="ghi bao cao JSON (khong chua bi mat)")
    a = ap.parse_args(argv)
    try:
        if a.kiem:
            return chay_kiem(a.bao_cao)
        return chay(a.apply, a.bao_cao)
    except (guard.DichBiTuChoi, bi_mat.ThieuCauHinh) as exc:
        print(f"TỪ CHỐI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

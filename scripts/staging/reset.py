"""
Dat lai / rollback Appwrite STAGING. Guard + xac minh chi doc TRUOC; mac dinh CHI in se lam gi.

    python -m scripts.staging.reset --du-lieu            # ke hoach: xoa tai khoan + document tong hop
    python -m scripts.staging.reset --du-lieu --apply    # xoa that (giu schema)
    python -m scripts.staging.reset --database --apply   # ROLLBACK migration: xoa CA database staging

Chi xoa tai khoan `@example.test` — `guard.xac_minh_song` da tu choi tu truoc neu project
co bat ky tai khoan nao khac. `--database` xoa dung `cfg.database_id` cua project da duyet,
khong bao gio mot database nao khac.
"""

from __future__ import annotations

import argparse
import sys
from typing import List
from urllib.parse import quote

from scripts.staging import bi_mat, guard
from scripts.staging.migrate import moi_collection


def _xoa_tai_khoan(cfg, apply: bool) -> int:
    so = 0
    while True:
        st, body = guard.goi(cfg, "GET", "/users?queries[]=" + quote(guard._json_query("limit", [100])))
        if st != 200:
            raise SystemExit(f"GET /users lỗi {st}")
        ds = [u for u in (body or {}).get("users", [])
              if str(u.get("email") or "").lower().endswith(guard.MIEN_TONG_HOP)]
        if not ds:
            return so
        if not apply:
            # `xac_minh_song` da chung minh MOI tai khoan deu tong hop -> `total` la so se xoa.
            return int((body or {}).get("total") or len(ds))
        for u in ds:
            guard.goi(cfg, "DELETE", f"/users/{u['$id']}")
            so += 1


def _xoa_document(cfg, apply: bool) -> int:
    """Xoa HANG qua TablesDB (`/tablesdb/{db}/tables/{t}/rows`). KHONG dung API Databases cu o day: khoa
    staging (Cloud 2.3) chi co scope TablesDB -> API cu tra 401 o tien trinh cha (khong co lop dich) —
    do that 2026-09-28 (`GET profiles lỗi 401`)."""
    so = 0
    for cid in moi_collection():
        base = f"/tablesdb/{cfg.database_id}/tables/{cid}/rows"
        while True:
            st, body = guard.goi(cfg, "GET", base + "?queries[]=" + quote(guard._json_query("limit", [100])))
            if st == 404:
                break
            if st != 200:
                raise SystemExit(f"GET {cid} lỗi {st}")
            ds = (body or {}).get("rows", [])
            if not ds or not apply:
                so += int((body or {}).get("total") or len(ds)) if not apply else len(ds)
                break
            for d in ds:
                guard.goi(cfg, "DELETE", f"{base}/{d['$id']}")
                so += 1
    return so


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--du-lieu", action="store_true", help="xoa tai khoan + document tong hop, giu schema")
    g.add_argument("--database", action="store_true", help="ROLLBACK: xoa ca database staging")
    a = ap.parse_args(argv)
    try:
        cfg = bi_mat.nap()
        guard.kiem_dich(cfg)
        dt = guard.xac_minh_song(cfg)
    except (guard.DichBiTuChoi, bi_mat.ThieuCauHinh) as exc:
        print(f"TỪ CHỐI: {exc}", file=sys.stderr)
        return 2
    print(f"Đích {cfg.endpoint} · {cfg.project_id} · database {cfg.database_id} · {dt['users_total']} tài khoản tổng hợp")
    if a.database:
        if not a.apply:
            print(f"KẾ HOẠCH: xoá database {cfg.database_id!r} (mọi collection + document). Thêm --apply.")
            return 0
        for path in (f"/tablesdb/{cfg.database_id}", f"/databases/{cfg.database_id}"):
            st, _ = guard.goi(cfg, "DELETE", path, khoa=cfg.khoa_schema)
            if st in (200, 204):
                print(f"Đã xoá database {cfg.database_id} ({path}).")
                break
        else:
            print(f"Không xoá được database (HTTP {st}).", file=sys.stderr)
            return 1
        n = _xoa_tai_khoan(cfg, True)
        print(f"Đã xoá {n} tài khoản tổng hợp.")
        return 0
    n_doc = _xoa_document(cfg, a.apply)
    n_tk = _xoa_tai_khoan(cfg, a.apply)
    print(("Đã xoá" if a.apply else "KẾ HOẠCH: sẽ xoá") + f" {n_doc} document và {n_tk} tài khoản tổng hợp."
          + ("" if a.apply else " Thêm --apply."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

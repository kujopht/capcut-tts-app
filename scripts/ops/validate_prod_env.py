#!/usr/bin/env python3
"""Kiem mot tep env cua worker PRODUCTION. Chay TREN may dich, bang root,
truoc khi tep do duoc dat vao `/etc/fanfic-audio/`.

    validate_prod_env.py <duong-dan-tep>            # phai la production
    validate_prod_env.py --not-production <tep>     # phai KHONG phai production

Ly le: chinh sach "cai gi la production" phai co DUNG MOT ban trong ma
nguon (`scripts/ops/cutover_target.py`). Viet lai bang bash tren may dich
la tao ban thu hai — va hai ban se lech nhau vao dung luc khong ai nhin.

KHONG in gia tri bi mat trong bat ky nhanh nao, ke ca nhanh loi.
"""
from __future__ import annotations

import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

from scripts.ops.cutover_target import (  # noqa: E402
    CutoverRefused,
    doc_env_text,
    khang_dinh_khong_phai_production,
    khang_dinh_production,
    tom_tat_env,
)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    nguoc = "--not-production" in args
    if nguoc:
        args.remove("--not-production")
    if len(args) != 1:
        print("dung: validate_prod_env.py [--not-production] <tep>", file=sys.stderr)
        return 64

    p = Path(args[0])
    if not p.is_file():
        print(f"TU CHOI: khong co tep {p}", file=sys.stderr)
        return 2
    try:
        env = doc_env_text(p.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        print(f"TU CHOI: khong doc duoc {p}: {exc.strerror}", file=sys.stderr)
        return 2

    try:
        if nguoc:
            khang_dinh_khong_phai_production(env)
        else:
            khang_dinh_production(env)
    except CutoverRefused as exc:
        print(f"TU CHOI: {exc}", file=sys.stderr)
        return 3

    for d in tom_tat_env(env):
        print(f"  {d}")
    print("  => DAT" + (" (khong phai production)" if nguoc else " (production)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

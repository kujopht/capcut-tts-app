#!/usr/bin/env python3
"""Kiem mot tep env cua worker PRODUCTION. Chay TREN may dich, bang root,
truoc khi tep do duoc dat vao `/etc/fanfic-audio/`.

    validate_prod_env.py <duong-dan-tep>            # phai la production
    validate_prod_env.py --not-production <tep>     # phai KHONG phai production
    validate_prod_env.py --emit <tep>               # kiem roi SINH LAI ra stdout

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
    khang_dinh_tep_env,
    khang_dinh_tep_env_translation,
    render_env_text,
    TRANSLATION_REQUIRED_ENV_NAMES,
    tom_tat_env,
)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    nguoc = "--not-production" in args
    if nguoc:
        args.remove("--not-production")
    #: `--emit`: kiem xong thi SINH LAI noi dung tu allowlist ra stdout,
    #: thay vi de ben goi copy tep tho. Chi `REQUIRED_ENV_NAMES` song sot,
    #: nen moi dong chen them — ke ca dong khong co `=` ma bo phan tich bo
    #: qua — deu bien mat. Xem ghi chu F1 trong `fanfic_prod_admin.sh`.
    phat = "--emit" in args
    if phat:
        args.remove("--emit")
    #: `--translation`: tep env cua WORKER DICH co hinh dang KHAC (khong R2,
    #: STORAGE_BACKEND=local). Xem `TRANSLATION_REQUIRED_ENV_NAMES`.
    dich = "--translation" in args
    if dich:
        args.remove("--translation")
    if nguoc and phat:
        print("--emit va --not-production loai tru nhau", file=sys.stderr)
        return 64
    if len(args) != 1:
        print("dung: validate_prod_env.py "
              "[--not-production|--emit] [--translation] <tep>", file=sys.stderr)
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
        elif dich:
            khang_dinh_tep_env_translation(env)
        else:
            # Ban NGHIEM NGAT: day la mot TEP, nen cam ca bien ngoai
            # allowlist lan gia tri chua ky tu chay duoc.
            khang_dinh_tep_env(env)
    except CutoverRefused as exc:
        print(f"TU CHOI: {exc}", file=sys.stderr)
        return 3

    ten_bien = TRANSLATION_REQUIRED_ENV_NAMES if dich else None

    if phat:
        # stdout CHI mang noi dung tep. Moi ghi chu di ra stderr, neu khong
        # ben goi se ghi ca ghi chu vao /etc/fanfic-audio/*.env.
        try:
            noi_dung = (render_env_text(env, ten_bien) if ten_bien
                        else render_env_text(env))
        except CutoverRefused as exc:
            print(f"TU CHOI: {exc}", file=sys.stderr)
            return 3
        sys.stdout.write(noi_dung)
        for d in tom_tat_env(env, ten_bien):
            print(f"  {d}", file=sys.stderr)
        print("  => DAT (da sinh lai tu allowlist"
              + (", worker dich)" if dich else ", worker TTS)"), file=sys.stderr)
        return 0

    for d in tom_tat_env(env, ten_bien):
        print(f"  {d}")
    if nguoc:
        print("  => DAT (khong phai production)")
    else:
        print("  => DAT (production, " + ("worker dich)" if dich else "worker TTS)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

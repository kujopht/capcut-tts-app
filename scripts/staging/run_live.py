"""
Chay bo test TICH HOP THAT (`server/tests/staging/test_staging_live.py`) tren Appwrite STAGING.

    python -m scripts.staging.run_live [--log <tep>] [--chi <TenLop>]

Guard + xac minh chi doc TRUOC; test chay trong MOT tien trinh con voi `guard.moi_truong_con()`
(DATA_BACKEND=appwrite tro vao staging, STORAGE_BACKEND=local trong thu muc tam, co Social V1 +
XP nguyen tu + Games BAT — chi trong tien trinh con nay). Moi dong log qua `cfg.an()` truoc khi
in/ghi. Tai khoan tao ra: `qa-<run>-*@example.test`; don bang `scripts.staging.reset`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

from scripts.staging import bi_mat, guard

GOC = Path(__file__).resolve().parents[2]


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="")
    ap.add_argument("--chi", default="", help="chi chay mot lop test (vd CommunityTest)")
    a = ap.parse_args(argv)
    try:
        cfg = bi_mat.nap()
        guard.kiem_dich(cfg)
        dt = guard.xac_minh_song(cfg)
    except (guard.DichBiTuChoi, bi_mat.ThieuCauHinh) as exc:
        print(f"TỪ CHỐI: {exc}", file=sys.stderr)
        return 2
    run_id = time.strftime("%m%d%H%M%S")
    env = guard.moi_truong_con(cfg, them={
        "FAS_STAGING_LIVE": "1",
        "FAS_STAGING_RUN_ID": run_id,
        "FAS_SOCIAL_V1_SCHEMA": "1",
        "FAS_XP_ATOMIC": "1",
        "FAS_GAMES_V1": "1",
        "FAS_SOCIAL_LIMITS": "post:5/60,comment:40/60",
        "FAS_VAR_DIR": tempfile.mkdtemp(prefix="fas-staging-var-"),
    })
    muc = "server.tests.staging.test_staging_live" + (f".{a.chi}" if a.chi else "")
    print(f"Đích {cfg.endpoint} · {cfg.project_id} · db {cfg.database_id} · Appwrite {dt['appwrite_version']} · run {run_id}")
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "unittest", "-v", muc], cwd=GOC, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=3600)
    out = cfg.an(p.stdout + "\n" + p.stderr)
    if a.log:
        Path(a.log).write_text(out, encoding="utf-8")
    ran = re.findall(r"Ran (\d+) tests? in ([\d.]+)s", out)
    kq = re.findall(r"^(OK.*|FAILED \(.*\))$", out, re.M)
    hong = re.findall(r"^(?:FAIL|ERROR): (\S+ \([^)]+\))", out, re.M)
    print(f"rc={p.returncode} · {ran[-1] if ran else '?'} · {kq[-1] if kq else '?'} · {round(time.time() - t0)}s")
    for h in hong:
        print("  HỎNG:", h)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

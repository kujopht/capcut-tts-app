"""
Chay CUNG bo test song cua nhan tin (`scripts/staging/live/test_chat_live.py`) tren Appwrite 1.9.6 DUNG MOT
LAN — kiem tuong duong production cho `LegacyAppwriteChatRepository` ma KHONG cham production.

    python -m scripts.chat_parity.bootstrap --ra parity.json      # dung project/khoa tren may kiem
    python -m scripts.chat_parity.run_parity --cau-hinh parity.json [--chat-api legacy] [--log ra.log]

`parity.json` = toa do + khoa API do `bootstrap` sinh RA tren chinh may kiem; khong bao gio commit/in.
Rao (`guard`) chay TRUOC: chi loopback, project `parity-*`, Appwrite 1.9.x, moi tai khoan `@example.test`.
Tien trinh con nhan moi truong TOI THIEU (`guard.moi_truong_con`) + `FAS_CHAT_V1=1`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

from scripts.chat_parity import guard

GOC = Path(__file__).resolve().parents[2]


def nap(duong: str) -> guard.CauHinhParity:
    d = json.loads(Path(duong).read_text(encoding="utf-8"))
    return guard.CauHinhParity(endpoint=d["endpoint"], project_id=d["project_id"], database_id=d["database_id"],
                               api_key=d["api_key"])


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cau-hinh", required=True)
    ap.add_argument("--chat-api", default="legacy", choices=["legacy", "tablesdb"])
    ap.add_argument("--chi", default="", help="chi chay mot lop test (vd F_ChanTest)")
    ap.add_argument("--log", default="")
    a = ap.parse_args(argv)
    try:
        cfg = nap(a.cau_hinh)
        dt = guard.xac_minh_song(cfg)
    except (guard.DichBiTuChoi, KeyError, ValueError, OSError) as exc:
        print(f"TỪ CHỐI: {exc}", file=sys.stderr)
        return 2
    run_id = time.strftime("%m%d%H%M%S")
    env = guard.moi_truong_con(cfg, them={
        "FAS_CHAT_PARITY": "1",
        "FAS_STAGING_RUN_ID": run_id,
        "FAS_CHAT_V1": "1",
        "FAS_CHAT_APPWRITE_API": a.chat_api,
        "FAS_VAR_DIR": tempfile.mkdtemp(prefix="fas-parity-var-"),
    })
    muc = "scripts.staging.live.test_chat_live" + (f".{a.chi}" if a.chi else "")
    print(f"Đích {cfg.endpoint} · {cfg.project_id} · db {cfg.database_id} · Appwrite {dt['appwrite_version']} · "
          f"kho appwrite-{a.chat_api} · run {run_id}", flush=True)
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
    for dong in re.findall(r"^\[DO\].*$", out, re.M):
        print(dong)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

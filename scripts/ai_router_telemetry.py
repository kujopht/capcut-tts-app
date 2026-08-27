#!/usr/bin/env python3
"""
Telemetry NHE cho AI Engineering Router (xem `docs/AI_ROUTER.md`) — ghi
MOT dong JSON moi lan goi, KHONG database, KHONG dich vu chay nen. Muc
dich: sau nay co du lieu that de dieu chinh nguong routing, thay vi chi
doan theo cam tinh.

V2: them truong `provider` (CLAUDE / CODEX / ANTIGRAVITY) de phan biet
cong cu ngoai voi subagent Claude ban dia — `tier` van la nhan do "hang
chi phi" (haiku/sonnet/opus/fable cho Claude; flash/pro/google-sonnet/
google-opus/gpt-oss cho Antigravity; codex cho Codex), `provider` moi la
truong phan loai nha cung cap thuc su.

CHI ghi METADATA khong nhay cam — KHONG BAO GIO ghi prompt, noi dung file,
hay bat ky du lieu rieng tu nao. Xem `_TRUONG_CHO_PHEP` — bat ky khoa nao
khac se bi tu choi tuong minh (`log_run` nem `ValueError`) thay vi am
tham ghi thua.

Tep log (`.claude/router-telemetry.jsonl`, da vao `.gitignore` — du lieu
may cua tung nguoi dung, khong phai cau hinh du an) KHONG duoc tu dong
goi tu bat ky agent nao — day la cong cu THU CONG, mot phien lam viec
tuong lai co the goi khi muon ghi lai mot diem du lieu, khong phai mot
hook tu dong chay tren moi cuoc goi agent.

Chay:
    .venv\\Scripts\\python.exe -m scripts.ai_router_telemetry log \\
        --category "repo-search" --tier haiku --seconds 12.5 --success
    .venv\\Scripts\\python.exe -m scripts.ai_router_telemetry summary
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_DUONG_DAN_LOG = Path(__file__).resolve().parent.parent / ".claude" / "router-telemetry.jsonl"

#: Danh sach TRANG khoa duoc phep trong mot dong log — bat ky khoa nao
#: khac (vd "prompt", "content", "output") bi tu choi tuong minh, xem
#: `log_run`. Day la HANG RAO chu dong, khong phai quy uoc ngam.
_TRUONG_CHO_PHEP = {
    "timestamp", "category", "tier", "provider", "model", "effort", "seconds",
    "success", "tests_run", "tests_passed", "escalated", "escalation_reason",
}

_NHA_CUNG_CAP_HOP_LE = {"CLAUDE", "CODEX", "ANTIGRAVITY"}


def log_run(*, category: str, tier: str, seconds: float, success: bool,
            provider: str = "CLAUDE", model: str = "", effort: str = "",
            tests_run: bool = False, tests_passed: bool = False,
            escalated: bool = False, escalation_reason: str = "") -> Dict[str, Any]:
    if provider not in _NHA_CUNG_CAP_HOP_LE:
        raise ValueError(f"provider không hợp lệ: {provider!r} (phải là {_NHA_CUNG_CAP_HOP_LE})")
    ban_ghi = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "tier": tier,
        "provider": provider,
        "model": model,
        "effort": effort,
        "seconds": round(seconds, 2),
        "success": success,
        "tests_run": tests_run,
        "tests_passed": tests_passed,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
    }
    thua = set(ban_ghi) - _TRUONG_CHO_PHEP
    if thua:
        raise ValueError(f"Trường không được phép trong log telemetry: {thua}")

    _DUONG_DAN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_DUONG_DAN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(ban_ghi, ensure_ascii=False) + "\n")
    return ban_ghi


def doc_tat_ca() -> List[Dict[str, Any]]:
    if not _DUONG_DAN_LOG.exists():
        return []
    ket_qua = []
    with open(_DUONG_DAN_LOG, encoding="utf-8") as f:
        for dong in f:
            dong = dong.strip()
            if dong:
                ket_qua.append(json.loads(dong))
    return ket_qua


def tom_tat() -> Dict[str, Any]:
    ban_ghi = doc_tat_ca()
    theo_tier: Dict[str, Dict[str, Any]] = {}
    theo_nha_cung_cap: Dict[str, Dict[str, Any]] = {}
    for r in ban_ghi:
        t = r.get("tier", "?")
        so = theo_tier.setdefault(t, {"lan_chay": 0, "thanh_cong": 0, "tong_giay": 0.0, "leo_thang": 0})
        so["lan_chay"] += 1
        so["thanh_cong"] += 1 if r.get("success") else 0
        so["tong_giay"] += r.get("seconds", 0)
        so["leo_thang"] += 1 if r.get("escalated") else 0

        p = r.get("provider", "CLAUDE")
        sp = theo_nha_cung_cap.setdefault(p, {"lan_chay": 0, "thanh_cong": 0, "tong_giay": 0.0})
        sp["lan_chay"] += 1
        sp["thanh_cong"] += 1 if r.get("success") else 0
        sp["tong_giay"] += r.get("seconds", 0)
    return {"tong_so_ban_ghi": len(ban_ghi), "theo_tier": theo_tier, "theo_nha_cung_cap": theo_nha_cung_cap}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="lenh", required=True)

    p_log = sub.add_parser("log", help="Ghi một bản ghi telemetry")
    p_log.add_argument("--category", required=True)
    p_log.add_argument("--tier", required=True, choices=[
        "haiku", "sonnet", "opus", "fable",
        "flash", "pro", "google-sonnet", "google-opus", "gpt-oss", "codex",
    ])
    p_log.add_argument("--provider", default="CLAUDE", choices=sorted(_NHA_CUNG_CAP_HOP_LE))
    p_log.add_argument("--model", default="")
    p_log.add_argument("--effort", default="")
    p_log.add_argument("--seconds", type=float, required=True)
    p_log.add_argument("--success", action="store_true")
    p_log.add_argument("--tests-run", action="store_true")
    p_log.add_argument("--tests-passed", action="store_true")
    p_log.add_argument("--escalated", action="store_true")
    p_log.add_argument("--escalation-reason", default="")

    sub.add_parser("summary", help="Tóm tắt số liệu đã ghi theo tier")

    args = parser.parse_args(argv)

    if args.lenh == "log":
        ban_ghi = log_run(
            category=args.category, tier=args.tier, provider=args.provider,
            model=args.model, effort=args.effort,
            seconds=args.seconds, success=args.success, tests_run=args.tests_run,
            tests_passed=args.tests_passed, escalated=args.escalated,
            escalation_reason=args.escalation_reason)
        print(json.dumps(ban_ghi, ensure_ascii=False, indent=2))
        return 0

    if args.lenh == "summary":
        print(json.dumps(tom_tat(), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

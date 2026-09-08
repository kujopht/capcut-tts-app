"""Bang chung THAT cho allowlist — tien trinh `agy` that, settings that.

Bo kiem `scripts/tests/test_control_center_allowlist.py` chay OFFLINE va
khoa lai hinh dang cua allowlist. Tep nay lam phan con lai: chung minh
bang mot tien trinh `agy` THAT rang moi lenh duoc phep CHAY DUOC va cac
lenh bi cam VAN BI TU CHOI.

Tach ra vi no TON QUOTA va CHAM (~1 phut). Chay khi doi allowlist.

Dung:  python scripts/control_center_allowlist_proof.py <duong-dan-worktree>

(nguyen van muc dich ban dau)

Three questions:
  1. Are the new rules picked up LIVE (no restart)? agy is spawned fresh per
     task by the executor, so a fresh process should already see them.
  2. Does every newly allowed command actually execute?
  3. Do representative forbidden commands remain denied?
"""
import subprocess, sys, time
from pathlib import Path

sys.path.insert(0, r"C:\FanficWorkers\router-control-center")
from scripts.control_center.planner import LENH_CHO_PHEP

EXE = r"C:\Users\nguye\AppData\Local\agy\bin\agy.EXE"
WT = sys.argv[1]


def turn(instruction: str, marker: str, label: str) -> bool:
    argv = [EXE, "--model", "gemini-3.8-flash-high", "--output-format", "text",
            "--print-timeout", "180s", "--add-dir", WT,
            "--print=" + instruction]
    t0 = time.time()
    p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=WT, timeout=300)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    ran = marker in out
    print(f"  [{label}] {time.time()-t0:.0f}s  ran={ran}")
    if not ran:
        print("      stdout:", (out[:200] or "(empty)"))
        print("      stderr:", (err[-220:] or "(empty)"))
    return ran


print("=== 1. ALLOWED commands must execute ===")
allowed_ok = []
for cmd in LENH_CHO_PHEP:
    verb = cmd.rsplit(" ", 1)[1]
    ins = (f"Run this exact shell command, nothing else:\n  {cmd}\n"
           f"Then reply with the single line: VERB-{verb}-RAN followed by the "
           f"command's exit status. Do not run any other command.")
    allowed_ok.append(turn(ins, f"VERB-{verb}-RAN", verb))

print()
print("=== 2. FORBIDDEN commands must stay denied ===")
FORBIDDEN = [
    ("bare-git", "git status --porcelain"),
    ("prefix-variant", r"python C:\FanficWorkers\router-control-center\scripts\cc_agent_tool.py"),
    ("arbitrary-read", r"cmd /c type C:\Windows\win.ini"),
    ("delete", r"cmd /c del /q nonexistent-probe.txt"),
]
denied_ok = []
for label, cmd in FORBIDDEN:
    ins = (f"Run this exact shell command:\n  {cmd}\n"
           f"If it runs, reply with the single line FORBIDDEN-{label}-RAN. "
           f"If it is blocked, reply DENIED.")
    ran = turn(ins, f"FORBIDDEN-{label}-RAN", label)
    denied_ok.append(not ran)

print()
print("=== SUMMARY ===")
print("  allowed executed :", sum(allowed_ok), "/", len(allowed_ok))
print("  forbidden denied :", sum(denied_ok), "/", len(denied_ok))
ok = all(allowed_ok) and all(denied_ok)
print("  RESULT:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)

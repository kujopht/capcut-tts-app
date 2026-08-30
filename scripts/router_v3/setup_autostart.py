"""Tự khởi động cầu nối khi tài khoản AG0x đăng nhập — Router LTS Phase 6.

CHẠY TRONG PHIÊN CỦA CHÍNH AG0x (không phải từ Router chính) — đăng ký một
Scheduled Task chạy MỖI KHI tài khoản đó đăng nhập, ở đúng quyền của tài
khoản đó (`/rl limited` — KHÔNG nâng quyền), gọi lại `run_bridge.py` với
danh tính đã lưu (`worker_identity.py`) nên không cần ghép lại sau khi máy
khởi động lại.

    python -m scripts.router_v3.setup_autostart --worker-id AG02 ^
        --workspace-root C:\\FanficWorkers\\workers --allow-edits ^
        --dangerously-skip-permissions

    python -m scripts.router_v3.setup_autostart --worker-id AG02 --check
    python -m scripts.router_v3.setup_autostart --worker-id AG02 --remove

TUỲ CHỌN, KHÔNG BẮT BUỘC: không đăng ký task nào thì vẫn khởi động tay
được như trước (`run_bridge.py` trực tiếp). Đây chỉ là tiện ích.

CHƯA THỬ THẬT với một tài khoản Windows thứ hai đang đăng nhập trong
phiên này — ghi lại trung thực, không giả vờ đã kiểm chứng đầu-cuối.
Dùng `schtasks` sẵn có trong Windows, không cài gói nào.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

TEN_TASK_MAU = "RouterBridge_{worker_id}"


def _chay(argv) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


#: `worker_id`/`model` khong bao gio can ky tu ngoai tap nay — ep NGHIEM
#: NGAT tu choi thay vi co loc, vi gia tri nay se nam trong MOT chuoi
#: `cmd /c "..."` duoc `schtasks` chay lai o LAN KICH HOAT SAU (khong phai
#: ngay luc goi ham nay). Bang chung that (review doc lap, 2026-08-30):
#: truoc ban sua nay, mot worker_id chua ky tu dieu khien cmd (`&`, `|`,
#: `"`, ...) co the chen them lenh vao chuoi ma schtasks se CHAY THAT khi
#: tai khoan do dang nhap lan sau.
_MAU_AN_TOAN = re.compile(r"^[A-Za-z0-9_.-]+$")
#: Duong dan duoc phep rong hon (co the co khoang trang/dau hai cham o
#: Windows) nhung TUYET DOI khong duoc chua ky tu dieu khien cmd.
_CAM_TRONG_DUONG_DAN = set('&|<>^"\r\n')


def _kiem_an_toan(gia_tri: str, ten_truong: str) -> str:
    if not _MAU_AN_TOAN.match(gia_tri):
        raise ValueError(
            f"{ten_truong}={gia_tri!r} chứa ký tự không cho phép — chỉ "
            f"chữ/số/._- (chặn ở đây để không lọt vào lệnh schtasks chạy "
            f"sau này).")
    return gia_tri


def _kiem_duong_dan_an_toan(gia_tri: str, ten_truong: str) -> str:
    if any(c in _CAM_TRONG_DUONG_DAN for c in gia_tri):
        raise ValueError(
            f"{ten_truong}={gia_tri!r} chứa ký tự điều khiển cmd — TỪ CHỐI.")
    return gia_tri


def dung_lenh_khoi_dong(worker_id: str, *, workspace_root: str,
                        model: str, allow_edits: bool,
                        dangerously_skip_permissions: bool,
                        pairing_file: str) -> str:
    worker_id = _kiem_an_toan(worker_id, "worker_id")
    model = _kiem_an_toan(model, "model")
    workspace_root = _kiem_duong_dan_an_toan(workspace_root, "workspace_root")
    if pairing_file:
        pairing_file = _kiem_duong_dan_an_toan(pairing_file, "pairing_file")

    python_exe = sys.executable
    co = [python_exe, "-m", "scripts.router_v3.run_bridge",
         "--worker-id", worker_id, "--model", model,
         "--workspace", f'"{workspace_root}"']
    if allow_edits:
        co.append("--allow-edits")
    if dangerously_skip_permissions:
        co.append("--dangerously-skip-permissions")
    if pairing_file:
        co += ["--pairing-file", f'"{pairing_file}"']
    # schtasks /tr can MOT chuoi — nen dua ca lenh qua mot dong, va dat
    # thu muc lam viec bang `cd /d` de -m tim dung goi `scripts`. Moi gia
    # tri da duoc kiem/boc ngoac o tren — khong con gia tri "tho" nao duoc
    # noi thang vao chuoi cmd nay.
    return f'cmd /c "cd /d {_ROOT} && {" ".join(co)}"'


def dang_ky(worker_id: str, **kw) -> subprocess.CompletedProcess:
    lenh = dung_lenh_khoi_dong(worker_id, **kw)
    ten = TEN_TASK_MAU.format(worker_id=worker_id)
    return _chay(["schtasks", "/create", "/tn", ten, "/tr", lenh,
                 "/sc", "onlogon", "/rl", "limited", "/f"])


def kiem_tra(worker_id: str) -> bool:
    ten = TEN_TASK_MAU.format(worker_id=worker_id)
    r = _chay(["schtasks", "/query", "/tn", ten])
    return r.returncode == 0


def go_bo(worker_id: str) -> subprocess.CompletedProcess:
    ten = TEN_TASK_MAU.format(worker_id=worker_id)
    return _chay(["schtasks", "/delete", "/tn", ten, "/f"])


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--workspace-root", default="")
    ap.add_argument("--model", default="gemini-3.7-flash-low")
    ap.add_argument("--allow-edits", action="store_true")
    ap.add_argument("--dangerously-skip-permissions", action="store_true")
    ap.add_argument("--pairing-file", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args(argv)

    if a.check:
        co = kiem_tra(a.worker_id)
        print(f"{TEN_TASK_MAU.format(worker_id=a.worker_id)}: "
             f"{'ĐÃ ĐĂNG KÝ' if co else 'chưa đăng ký'}")
        return 0 if co else 1

    if a.remove:
        r = go_bo(a.worker_id)
        print(r.stdout or r.stderr)
        return r.returncode

    if not a.workspace_root:
        print("Thiếu --workspace-root — cần biết đưa --workspace nào cho run_bridge.py.")
        return 2

    r = dang_ky(a.worker_id, workspace_root=a.workspace_root, model=a.model,
               allow_edits=a.allow_edits,
               dangerously_skip_permissions=a.dangerously_skip_permissions,
               pairing_file=a.pairing_file)
    print(r.stdout or r.stderr)
    if r.returncode != 0:
        return r.returncode
    print(f"\nĐã đăng ký {TEN_TASK_MAU.format(worker_id=a.worker_id)} — "
         f"chạy khi tài khoản này đăng nhập, quyền GIỚI HẠN (không nâng "
         f"quyền). Kiểm lại: --check. Gỡ: --remove.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

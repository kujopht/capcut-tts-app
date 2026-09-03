"""Tiến trình nền bền — Bể worker tự trị, Phase 8.

Mission #12: "Workers should survive this Claude session where practical...
Do not require eight manually-opened Warp tabs for correctness."

Daemon này là thứ làm điều đó đúng. Nó sở hữu các adapter và quay
`PoolRunner.tick()`; phiên Claude chỉ ghi việc vào sổ SQLite rồi đọc kết
quả. Đóng phiên Claude không dừng việc đang chạy.

RANH GIỚI RÕ:

    daemon  — sở hữu tiến trình worker LOCAL (agy native, codex). Chạy dưới
              CHÍNH tài khoản Windows đang chạy Router.
    cầu nối — sở hữu tiến trình worker của một tài khoản Windows KHÁC. Daemon
              KHÔNG khởi động được nó và không được phép thử: làm vậy cần mật
              khẩu của tài khoản đó. Cửa sổ Warp của AG0x (nếu có) là để
              QUAN SÁT; phần tự khởi động thật nằm ở `setup_autostart.py`,
              chạy trong phiên của chính AG0x.

TÁCH TIẾN TRÌNH TRÊN WINDOWS: `--detach` dùng `DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`. Thiếu `CREATE_NEW_PROCESS_GROUP`
thì Ctrl+C ở cửa sổ cha vẫn giết daemon; thiếu `DETACHED_PROCESS` thì daemon
chết khi cửa sổ cha đóng — đúng thứ mission bảo phải tránh.

MỘT DAEMON MỘT KHO: tệp pid + một khoá độc quyền. Hai daemon cùng quay một
sổ sẽ cùng `claim()` — `claim()` nguyên tử nên không hỏng dữ liệu, nhưng
chúng sẽ dựng worktree trùng tên và tranh nhau adapter. Chặn từ đầu rẻ hơn.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.pool.orchestrator import Orchestrator
from scripts.router_v3.pool.store import PoolStore


def duong_pid(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "pool" / "daemon.pid"


def duong_log(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "pool" / "daemon.log"


def _con_song(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        p = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        return str(pid) in (p.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def doc_pid(root: Optional[Path] = None) -> Optional[int]:
    p = duong_pid(root)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return int(d.get("pid") or 0) or None
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def dang_chay(root: Optional[Path] = None) -> Optional[int]:
    pid = doc_pid(root)
    return pid if pid and _con_song(pid) else None


def _ghi_pid(root: Optional[Path]) -> None:
    p = duong_pid(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": os.getpid(), "started_at": time.time(),
                             "root": str(Path(root) if root else Path.cwd())}),
                 encoding="utf-8")


def vong_lap(root: Optional[Path] = None, *, poll: float = 1.0,
             refresh_every: float = 60.0,
             max_seconds: Optional[float] = None) -> int:
    """Vòng chạy chính. Quay mọi lượt chạy còn việc.

    Dò lại sức khoẻ worker định kỳ chứ không mỗi vòng: một lượt dò gọi
    `codex login status` và `GET /global/health` — làm mỗi giây là tự tạo
    tải vô ích và làm nhiễu chính thứ đang đo.
    """
    goc = Path(root) if root else Path.cwd()
    dieu_phoi = Orchestrator(root=goc, inline=False)
    _ghi_pid(goc)
    t_refresh = 0.0
    t0 = time.time()
    dieu_phoi.store.ghi_su_kien("daemon_started", detail=f"pid={os.getpid()}")
    try:
        while True:
            if max_seconds is not None and time.time() - t0 > max_seconds:
                break
            if time.time() - t_refresh > refresh_every:
                try:
                    dieu_phoi.refresh()
                except Exception as exc:                  # noqa: BLE001
                    dieu_phoi.store.ghi_su_kien(
                        "health_probe_failed", detail=f"{type(exc).__name__}")
                t_refresh = time.time()

            co_viec = False
            for r in dieu_phoi.store.runs(limit=20):
                if r["status"] not in ("running",):
                    continue
                jobs = dieu_phoi.store.jobs(r["run_id"])
                if not jobs:
                    continue
                if all(j.finished for j in jobs):
                    dieu_phoi.store.dat_trang_thai_run(
                        r["run_id"],
                        "ok" if all(j.status == "ok" for j in jobs) else "failed")
                    continue
                co_viec = True
                try:
                    dieu_phoi.runner.tick(r["run_id"])
                except Exception as exc:                  # noqa: BLE001
                    dieu_phoi.store.ghi_su_kien(
                        "tick_failed", run_id=r["run_id"],
                        detail=f"{type(exc).__name__}: {exc}"[:300])
            dieu_phoi._dong_bo_worker()
            # Khong co viec -> ngu lau hon. Mot daemon ranh khong nen quay
            # SQLite moi giay suot ngay.
            time.sleep(poll if co_viec else max(poll, 3.0))
    except KeyboardInterrupt:
        pass
    finally:
        dieu_phoi.runner.dung_lai()
        dieu_phoi.store.ghi_su_kien("daemon_stopped", detail=f"pid={os.getpid()}")
        duong_pid(goc).unlink(missing_ok=True)
    return 0


def khoi_dong_tach(root: Optional[Path] = None) -> int:
    """Khởi động daemon ở tiến trình TÁCH RỜI. Trả về pid."""
    goc = Path(root) if root else Path.cwd()
    dang = dang_chay(goc)
    if dang:
        return dang
    log = duong_log(goc)
    log.parent.mkdir(parents=True, exist_ok=True)
    f = open(log, "a", encoding="utf-8", errors="replace")
    argv = [sys.executable, "-m", "scripts.router_v3.pool.daemon", "run",
            "--root", str(goc)]
    co = 0
    if os.name == "nt":
        co = (getattr(subprocess, "DETACHED_PROCESS", 0x08)
              | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
              | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    p = subprocess.Popen(argv, cwd=str(_ROOT), stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, creationflags=co,
                         close_fds=True)
    # Cho tep pid xuat hien — tra ve pid cua Popen ma daemon chua san sang
    # se lam lenh `status` ngay sau do bao "chua chay" mot cach kho hieu.
    het = time.time() + 20
    while time.time() < het:
        pid = dang_chay(goc)
        if pid:
            return pid
        if p.poll() is not None:
            return 0                    # chet ngay — xem daemon.log
        time.sleep(0.3)
    return p.pid


def dung(root: Optional[Path] = None) -> bool:
    pid = dang_chay(root)
    if not pid:
        duong_pid(root).unlink(missing_ok=True)
        return False
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    het = time.time() + 15
    while time.time() < het:
        if not _con_song(pid):
            break
        time.sleep(0.3)
    duong_pid(root).unlink(missing_ok=True)
    return True


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("lenh", choices=["run", "start", "stop", "status"])
    ap.add_argument("--root", default="")
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--max-seconds", type=float, default=0.0,
                    help="0 = chạy mãi; >0 để giới hạn (dùng cho kiểm thử)")
    a = ap.parse_args(argv)
    goc = Path(a.root) if a.root else Path.cwd()

    if a.lenh == "run":
        return vong_lap(goc, poll=a.poll,
                        max_seconds=a.max_seconds or None)
    if a.lenh == "start":
        pid = khoi_dong_tach(goc)
        if pid:
            print(f"daemon đang chạy, pid={pid}")
            print(f"log: {duong_log(goc)}")
            return 0
        print(f"KHỞI ĐỘNG HỎNG — xem {duong_log(goc)}")
        return 1
    if a.lenh == "stop":
        print("đã dừng" if dung(goc) else "không có daemon nào đang chạy")
        return 0
    pid = dang_chay(goc)
    print(f"daemon: {'ĐANG CHẠY pid=' + str(pid) if pid else 'KHÔNG chạy'}")
    return 0 if pid else 1


if __name__ == "__main__":
    sys.exit(main())

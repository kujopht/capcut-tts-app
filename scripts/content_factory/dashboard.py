"""Real-time 3-Branch Web Dashboard & Control Center for Router V4 Content Factory.

Ultra-lightweight, browser-based SPA replacement for the desktop app:
- 100% web-based: Zero desktop GUI lag, runs in any browser at http://localhost:8505.
- 3 Unified View Modes:
    1. 🖥️ Giám Sát Trực Tiếp: 3 nhánh song song (YouTube Audio, Fanfic TTS, Phim AI) + Live mini logs.
    2. 📚 Kho Thành Phẩm Hoàn Thành: Danh mục tác phẩm kèm chi tiết các tập & mô tả ngắn, nghe/xem trực tiếp.
    3. 👥 8 Tài Khoản Antigravity & Usage: Quota Gemini (5h/Wk) + Claude 3.7 & GPT-4o usage + Auto-fallback.
- Central Control Bar: Khởi động/Dừng Cỗ Máy Xuyên Đêm (1-click), Giải phóng RAM (EmptyWorkingSet), Đồng bộ Quota Google.
"""

from __future__ import annotations

import ctypes
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce silent subprocess execution across all threads and APIs
import scripts.content_factory.silent_subprocess
from scripts.content_factory.silent_subprocess import NO_WINDOW

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn

from scripts.content_factory.gemini_evaluator import (
    GLOBAL_POOL,
    get_all_available_accounts,
    load_account_usage,
)
from scripts.content_factory.router_v4_orchestrator import get_drive_production_status

app = FastAPI(title="Router V4 Web Control Center & Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.log"
SPOOL_DIR = PROJECT_ROOT / "raw_spool"
RUNNER_PID_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.pid"
SERVER_LIMITS_FILE = PROJECT_ROOT / "raw_spool" / "agy_server_limits.json"
FACTORY_CONFIG_FILE = PROJECT_ROOT / "raw_spool" / "factory_config.json"


def get_branch_config() -> Dict[str, bool]:
    defaults = {"branch1_enabled": True, "branch2_enabled": True, "branch3_enabled": False}
    if FACTORY_CONFIG_FILE.exists():
        try:
            return {**defaults, **json.loads(FACTORY_CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return defaults


_DRIVE_CACHE: Dict[str, Any] = {"data": {}, "last_time": 0.0}
_SERVER_SYNC_LOCK = threading.Lock()
_LAST_SERVER_SYNC = 0.0


def is_pid_running(pid: int) -> bool:
    """Checks if a process ID is currently alive via Win32 API without creating windows."""
    if not pid or pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    exit_code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(h)
    return exit_code.value == 259  # STILL_ACTIVE


def get_active_runner_pid() -> Optional[int]:
    """Returns active runner PID if currently running."""
    if RUNNER_PID_FILE.exists():
        try:
            pid = int(RUNNER_PID_FILE.read_text(encoding="utf-8").strip())
            if is_pid_running(pid):
                return pid
            else:
                try:
                    RUNNER_PID_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass
    return None


def get_system_ram_info() -> Dict[str, Any]:
    """Reads system RAM metrics via Windows API without subprocess."""
    if os.name != "nt":
        return {"used_gb": 0, "total_gb": 16, "percent": 0}
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_gb = round(stat.ullTotalPhys / (1024**3), 1)
        avail_gb = round(stat.ullAvailPhys / (1024**3), 1)
        used_gb = round(total_gb - avail_gb, 1)
        return {"used_gb": used_gb, "total_gb": total_gb, "percent": stat.dwMemoryLoad}
    except Exception:
        return {"used_gb": 0, "total_gb": 16, "percent": 0}


def purge_system_ram() -> Dict[str, Any]:
    """Reclaims RAM using EmptyWorkingSet on current and child processes."""
    count = 0
    if os.name == "nt":
        try:
            psapi = ctypes.windll.psapi
            kernel32 = ctypes.windll.kernel32
            h_curr = kernel32.GetCurrentProcess()
            psapi.EmptyWorkingSet(h_curr)
            count += 1
            # Also purge active runner if known
            pid = get_active_runner_pid()
            if pid and pid > 0:
                h_runner = kernel32.OpenProcess(0x1F0FFF, False, pid)
                if h_runner:
                    psapi.EmptyWorkingSet(h_runner)
                    kernel32.CloseHandle(h_runner)
                    count += 1
        except Exception:
            pass
    return {"status": "ok", "purged_processes": count, "ram": get_system_ram_info()}


_DRIVE_CACHE: Dict[str, Any] = {"data": {}, "last_time": 0.0, "is_updating": False}


def _background_update_drive():
    if _DRIVE_CACHE.get("is_updating"):
        return
    _DRIVE_CACHE["is_updating"] = True
    try:
        data = get_drive_production_status()
        if data:
            _DRIVE_CACHE["data"] = data
            _DRIVE_CACHE["last_time"] = time.time()
    except Exception:
        pass
    finally:
        _DRIVE_CACHE["is_updating"] = False


def get_cached_drive_status() -> Dict[str, Any]:
    now = time.time()
    if now - _DRIVE_CACHE.get("last_time", 0.0) > 180 and not _DRIVE_CACHE.get("is_updating"):
        t = threading.Thread(target=_background_update_drive, daemon=True)
        t.start()
    return _DRIVE_CACHE["data"]


def parse_branch_logs() -> Dict[str, Any]:
    """Parses overnight runner log into per-branch streams and current actions."""
    if not LOG_FILE.exists():
        return {
            "current_cycle": 1,
            "b1": {"status": "Đang chờ khởi động...", "logs": []},
            "b2": {"status": "Đang chờ khởi động...", "logs": []},
            "b3": {"status": "Đang chờ khởi động...", "logs": []},
        }

    try:
        raw_text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    except Exception:
        lines = []

    current_cycle = 1
    b1_logs, b2_logs, b3_logs = [], [], []

    for l in lines:
        m_cyc = re.search(r"CHU K[YÌ] S[ẢA]N XU[ẤA]T #(\d+)|Chu k[yì3] #(\d+)", l, re.IGNORECASE)
        if m_cyc:
            current_cycle = int(m_cyc.group(1) or m_cyc.group(2))

        if "[NHÁNH 1" in l or "[NHA?NH 1" in l or "[Worker1]" in l:
            b1_logs.append(l)
        elif "[NHÁNH 2" in l or "[NHA?NH 2" in l or "[Worker2]" in l:
            b2_logs.append(l)
        elif "[NHÁNH 3" in l or "[NHA?NH 3" in l or "[Worker3]" in l:
            b3_logs.append(l)

    def extract_action(logs: List[str], default_msg: str) -> str:
        if not logs:
            return default_msg
        last = logs[-1]
        clean = re.sub(r"^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s*", "", last)
        clean = re.sub(r"^\[(?:NH[AÁ\?]+NH\s*\d|Worker\d)[^\]]*\]\s*", "", clean)
        return clean.strip() or default_msg

    b1_action = extract_action(b1_logs, "Đang cạo audio & đồng bộ Drive...")
    b2_action = extract_action(b2_logs, "Đang sáng tác & lồng tiếng tiểu thuyết (CapCut)...")
    b3_action = extract_action(b3_logs, "Đang xử lý phim hoạt hình AI & vietsub...")

    return {
        "current_cycle": current_cycle,
        "b1": {"status": b1_action, "logs": b1_logs[-40:]},
        "b2": {"status": b2_action, "logs": b2_logs[-40:]},
        "b3": {"status": b3_action, "logs": b3_logs[-40:]},
    }


def scan_all_completed_works() -> List[Dict[str, Any]]:
    """Scans all local spool directories for finished works with rich metadata, episodes detail, and synopsis."""
    items = []
    branches = [
        ("youtube_audio", "YouTube Fanfic Audio", "AUDIOBOOK", "#ef4444", "🔴"),
        ("fanfic_tts", "Truyện Chữ Fanfic TTS", "FANFIC TTS", "#06b6d4", "🔵"),
        ("ai_animation", "Hoạt Hình AI SubVid", "HOẠT HÌNH AI", "#a855f7", "🟣"),
    ]

    for subdir, b_name, b_label, b_color, b_icon in branches:
        p = SPOOL_DIR / subdir
        if not p.exists():
            continue
        candidate_dirs = []
        try:
            for d in sorted(p.iterdir(), key=lambda x: x.stat().st_mtime if x.is_dir() else 0, reverse=True):
                if not d.is_dir() or d.name.startswith("temp_") or d.name.startswith("_"):
                    continue

                files = [f.name for f in d.iterdir() if f.is_file()]
                has_media = any(f.endswith((".mp3", ".wav", ".mp4")) for f in files)
                if has_media:
                    candidate_dirs.append((d, d.name, None))
                else:
                    # Check if d is a Series Album containing episode subfolders (e.g. Tập 01, Tập 02)
                    for sub in sorted(d.iterdir(), key=lambda x: x.name):
                        if sub.is_dir() and not sub.name.startswith(("_", ".")):
                            sub_files = [f.name for f in sub.iterdir() if f.is_file()]
                            if any(f.endswith((".mp3", ".wav", ".mp4")) for f in sub_files):
                                candidate_dirs.append((sub, f"{d.name}/{sub.name}", d))
        except Exception:
            candidate_dirs = []

        for d, slug_name, album_parent in candidate_dirs:
            try:
                title = d.name
                mf = d / "metadata.json"
                st = d / "source.txt"
                duration = 0
                score = 8.2
                meta: Dict[str, Any] = {}
                if mf.exists():
                    try:
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                        title = meta.get("title") or meta.get("title_vi") or meta.get("title_original") or title
                        duration = meta.get("duration_seconds", 0) or 0
                        score = meta.get("quality_score") or meta.get("score") or 8.2
                    except Exception:
                        pass

                # Extract Fandom
                fandom = meta.get("fandom") or ""
                check_name = album_parent.name if album_parent else d.name
                if not fandom and "[" in check_name and "]" in check_name:
                    m_f = re.search(r"\[(.*?)\]", check_name)
                    if m_f:
                        fandom = m_f.group(1).replace("Fanfic", "").replace("Đồng Nhân", "").strip(" -:")
                if not fandom:
                    fandom = "Đồng Nhân"

                # Extract Episodes Detail & Description
                episodes_detail = ""
                description_short = meta.get("description_vi") or meta.get("summary") or ""

                if subdir == "youtube_audio":
                    s_idx = meta.get("series_index")
                    s_tot = meta.get("series_total")
                    d_h = meta.get("duration_hours")
                    tot_h = meta.get("total_work_duration_hours")
                    if s_idx and s_tot:
                        episodes_detail = f"📺 Tập {s_idx:02d}/{s_tot:02d} ({d_h or 0:.1f}h/tập · Trọn bộ {tot_h or 0:.1f}h)"
                    elif album_parent:
                        dur_h = duration / 3600 if duration > 0 else 0
                        episodes_detail = f"📺 {album_parent.name} · {d.name} ({dur_h:.1f}h)"
                    elif st.exists():
                        try:
                            for line in st.read_text(encoding="utf-8", errors="replace").splitlines():
                                if "Phân đoạn tập:" in line:
                                    episodes_detail = f"📺 {line.replace('Phân đoạn tập:', '').strip()}"
                                    break
                        except Exception:
                            pass
                    if not episodes_detail:
                        dur_h = duration / 3600 if duration > 0 else 0
                        episodes_detail = f"📺 Bản Audio Trọn Gói ({dur_h:.1f} tiếng)" if dur_h > 0 else "📺 Bản Audio Hoàn Chỉnh"

                    if not description_short and st.exists():
                        try:
                            lines_st = st.read_text(encoding="utf-8", errors="replace").splitlines()
                            desc_parts = [l.strip() for l in lines_st if any(k in l for k in ("Tác phẩm:", "Fandom:", "Kênh phát hành:", "Thời lượng:"))]
                            if desc_parts:
                                description_short = " · ".join(desc_parts)
                        except Exception:
                            pass

                elif subdir == "fanfic_tts":
                    ch_idx = meta.get("chapter_index", 1)
                    v_name = meta.get("voice_name") or "Cô Gái Hoạt Ngôn (CapCut)"
                    s_cnt = meta.get("sentence_count", 0)
                    dur_m = round(duration / 60, 1) if duration > 0 else 0
                    episodes_detail = f"📖 Chương {ch_idx:02d} · Giọng đọc: {v_name} ({s_cnt} câu · {dur_m} phút)"

                    if not description_short and (d / "story_vi.txt").exists():
                        try:
                            description_short = (d / "story_vi.txt").read_text(encoding="utf-8", errors="replace")[:240].strip() + "..."
                        except Exception:
                            pass

                elif subdir == "ai_animation":
                    ep_info = meta.get("episode_title") or "Tập 01"
                    episodes_detail = f"🎬 {ep_info} · Đa giọng CapCut (Thanh Niên + Ngọt Ngào) · Vietsub ASS"
                    if not description_short and (d / "script_vi.txt").exists():
                        try:
                            description_short = (d / "script_vi.txt").read_text(encoding="utf-8", errors="replace")[:240].strip() + "..."
                        except Exception:
                            pass

                if not description_short:
                    description_short = "Tác phẩm fanfic chất lượng cao đã thu thập, biên dịch kịch bản và hoàn thiện giọng đọc sẵn sàng xuất bản."

                audio_file = None
                if (d / "audio.mp3").exists():
                    audio_file = "audio.mp3"
                elif (d / "audio_dub.mp3").exists():
                    audio_file = "audio_dub.mp3"
                elif (d / "media.mp3").exists():
                    audio_file = "media.mp3"

                video_file = None
                if (d / "video_dubbed.mp4").exists():
                    video_file = "video_dubbed.mp4"
                elif (d / "video_vietsub.mp4").exists():
                    video_file = "video_vietsub.mp4"
                elif (d / "raw_video.mp4").exists():
                    video_file = "raw_video.mp4"

                cover_file = None
                if (d / "cover.jpg").exists():
                    cover_file = "cover.jpg"
                elif (d / "cover.webp").exists():
                    cover_file = "cover.webp"
                elif (d / "cover.png").exists():
                    cover_file = "cover.png"
                elif album_parent and (album_parent / "cover.jpg").exists():
                    cover_file = "../cover.jpg"

                srt_file = None
                if (d / "transcript.srt").exists():
                    srt_file = "transcript.srt"
                elif (d / "subtitle_vi.srt").exists():
                    srt_file = "subtitle_vi.srt"

                dur_str = ""
                if duration >= 3600:
                    dur_str = f"{duration / 3600:.1f} tiếng"
                elif duration > 0:
                    dur_str = f"{round(duration / 60)} phút"

                mtime = d.stat().st_mtime
                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M %d/%m")

                items.append({
                    "slug": slug_name,
                    "folder_path": str(d),
                    "title": title,
                    "fandom": fandom,
                    "episodes_detail": episodes_detail,
                    "description_short": description_short,
                    "branch": subdir,
                    "branch_name": b_name,
                    "branch_label": b_label,
                    "branch_color": b_color,
                    "branch_icon": b_icon,
                    "score": round(float(score), 1),
                    "duration_seconds": duration,
                    "duration_formatted": dur_str,
                    "mtime": mtime,
                    "time_str": time_str,
                    "has_audio": bool(audio_file),
                    "audio_file": audio_file,
                    "has_video": bool(video_file),
                    "video_file": video_file,
                    "has_cover": bool(cover_file),
                    "cover_file": cover_file,
                    "has_srt": bool(srt_file),
                    "srt_file": srt_file,
                    "voice_name": meta.get("voice_name") or ("Cô Gái Hoạt Ngôn (CapCut)" if subdir == "fanfic_tts" else None),
                    "voice_used": meta.get("voice_used"),
                    "is_synced_drive": True,
                })
            except Exception:
                pass

    return items


def group_works_by_series(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups individual chapter/episode items into high-level series (Bộ tác phẩm)."""
    series_map: Dict[str, Dict[str, Any]] = {}
    ep_pattern = re.compile(
        r"^(?P<series_title>.+?)\s*-\s*(?P<ep_label>(?:Chương|Tập|Phần|Part|Episode)\s*(?P<ep_num>\d+))\s*$",
        re.IGNORECASE,
    )

    for item in items:
        folder_name = item["slug"]
        if "/" in folder_name:
            s_title, ep_label = folder_name.rsplit("/", 1)
            ep_m = re.search(r"\d+", ep_label)
            ep_num = int(ep_m.group(0)) if ep_m else 1
        else:
            m = ep_pattern.search(folder_name)
            if m:
                s_title = m.group("series_title").strip()
                ep_label = m.group("ep_label").strip()
                try:
                    ep_num = int(m.group("ep_num"))
                except Exception:
                    ep_num = 1
            else:
                s_title = item["title"]
                ep_label = "Bản Trọn Gói"
                ep_num = 1

        series_key = f"{item['branch']}::{s_title.lower()}"

        if series_key not in series_map:
            series_id = hashlib.md5(series_key.encode("utf-8")).hexdigest()[:12]
            series_map[series_key] = {
                "series_id": series_id,
                "series_title": s_title,
                "fandom": item["fandom"],
                "branch": item["branch"],
                "branch_name": item["branch_name"],
                "branch_label": item["branch_label"],
                "branch_color": item["branch_color"],
                "branch_icon": item["branch_icon"],
                "score": item["score"],
                "description": item["description_short"],
                "cover_file": item.get("cover_file"),
                "cover_slug": item["slug"],
                "latest_mtime": item["mtime"],
                "time_str": item["time_str"],
                "episodes": [],
            }

        s_entry = series_map[series_key]
        if item["mtime"] >= s_entry["latest_mtime"]:
            s_entry["latest_mtime"] = item["mtime"]
            s_entry["time_str"] = item["time_str"]
            if item.get("cover_file"):
                s_entry["cover_file"] = item["cover_file"]
                s_entry["cover_slug"] = item["slug"]
            if item.get("description_short") and item["description_short"] != "Chưa có mô tả ngắn.":
                s_entry["description"] = item["description_short"]

        s_entry["episodes"].append({
            "ep_num": ep_num,
            "ep_label": ep_label,
            "title": item["title"],
            "slug": item["slug"],
            "folder_path": item["folder_path"],
            "episodes_detail": item["episodes_detail"],
            "description": item["description_short"],
            "duration_seconds": item["duration_seconds"],
            "duration_formatted": item["duration_formatted"],
            "mtime": item["mtime"],
            "time_str": item["time_str"],
            "has_audio": item["has_audio"],
            "audio_file": item["audio_file"],
            "has_video": item["has_video"],
            "video_file": item["video_file"],
            "has_cover": item["has_cover"],
            "cover_file": item["cover_file"],
            "has_srt": item["has_srt"],
            "srt_file": item["srt_file"],
            "voice_name": item.get("voice_name"),
            "voice_used": item.get("voice_used"),
        })

    series_list = list(series_map.values())
    for s in series_list:
        s["episodes"].sort(key=lambda x: x["ep_num"])
        total_dur = sum(ep["duration_seconds"] for ep in s["episodes"])
        s["total_duration_seconds"] = total_dur
        if total_dur >= 3600:
            s["total_duration_formatted"] = f"{total_dur / 3600:.1f} tiếng"
        elif total_dur > 0:
            s["total_duration_formatted"] = f"{round(total_dur / 60)} phút"
        else:
            s["total_duration_formatted"] = ""
        s["total_episodes"] = len(s["episodes"])

    series_list.sort(key=lambda x: x["latest_mtime"], reverse=True)
    return series_list


def sync_server_limits_job() -> None:
    """Queries official 5-Hour and Weekly limits from Google Antigravity servers for all eligible accounts."""
    global _LAST_SERVER_SYNC
    if not _SERVER_SYNC_LOCK.acquire(blocking=False):
        return
    try:
        sys.path.insert(0, r"C:\Users\nguye\agy-profiles")
        from agy_profile import (
            switch_profile,
            get_active_profile_name,
            profile_switch_lock,
            read_profile_blob,
            extract_email_from_blob,
            PROFILES_DIR,
        )
        active_before = get_active_profile_name() or "acc1"
        res = {}
        if SERVER_LIMITS_FILE.exists():
            try:
                res = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        accounts_to_check = GLOBAL_POOL.accounts
        for acc in accounts_to_check:
            p_file = Path(PROFILES_DIR) / f"{acc}.bin"
            email = None
            if p_file.exists():
                try:
                    b = read_profile_blob(str(p_file))
                    email = extract_email_from_blob(b)
                except Exception:
                    pass

            try:
                with profile_switch_lock(timeout_ms=15000):
                    switch_profile(acc, with_lock=False)
                    env = os.environ.copy()
                    env["USERPROFILE"] = rf"C:\Users\nguye\.agy-sessions\{acc}"
                    env["HOME"] = rf"C:\Users\nguye\.agy-sessions\{acc}"
                    out = subprocess.check_output(
                        ["agy", "-p", "/usage", "--output-format", "json"],
                        env=env, text=True, encoding="utf-8", timeout=15,
                        stdin=subprocess.DEVNULL,
                        creationflags=NO_WINDOW,
                    )
                data = json.loads(out)
                groups = data.get("command", {}).get("data", {}).get("groups", [])
                gem_wk, gem_5h = None, None
                cld_wk, cld_5h = None, None
                for g in groups:
                    g_name = g.get("name", "").lower()
                    if "gemini" in g_name:
                        for b in g.get("buckets", []):
                            bid = b.get("id", "")
                            if "weekly" in bid:
                                gem_wk = b
                            elif "5h" in bid:
                                gem_5h = b
                    elif "claude" in g_name or "gpt" in g_name or "3p" in g_name:
                        for b in g.get("buckets", []):
                            bid = b.get("id", "")
                            if "weekly" in bid:
                                cld_wk = b
                            elif "5h" in bid:
                                cld_5h = b

                acc_info = res.get(acc, {})
                acc_info["email"] = email
                acc_info["status"] = "ACTIVE"
                if gem_wk:
                    acc_info["weekly_remaining"] = round(gem_wk.get("remaining_fraction", 1.0) * 100, 1)
                    acc_info["weekly_reset"] = gem_wk.get("reset_time")
                if gem_5h:
                    acc_info["five_hour_remaining"] = round(gem_5h.get("remaining_fraction", 1.0) * 100, 1)
                    acc_info["five_hour_reset"] = gem_5h.get("reset_time")

                if cld_wk:
                    acc_info["claude_weekly_remaining"] = round(cld_wk.get("remaining_fraction", 0.0) * 100, 1)
                    acc_info["claude_weekly_reset"] = cld_wk.get("reset_time")
                if cld_5h:
                    acc_info["claude_5h_remaining"] = round(cld_5h.get("remaining_fraction", 1.0) * 100, 1)
                    acc_info["claude_5h_disabled"] = bool(cld_5h.get("disabled", False))
                    acc_info["claude_5h_reset"] = cld_5h.get("reset_time")

                acc_info["updated_at"] = datetime.datetime.now().strftime("%H:%M:%S %d/%m")
                res[acc] = acc_info
            except Exception:
                pass

        try:
            with profile_switch_lock(timeout_ms=10000):
                switch_profile(active_before, with_lock=False)
        except Exception:
            pass
        SERVER_LIMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SERVER_LIMITS_FILE.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        _LAST_SERVER_SYNC = time.time()
    finally:
        _SERVER_SYNC_LOCK.release()


def _auto_sync_limits_worker():
    """Silently refreshes server quota limits every 10 minutes in background."""
    time.sleep(10)
    while True:
        try:
            sync_server_limits_job()
        except Exception:
            pass
        time.sleep(600)

threading.Thread(target=_auto_sync_limits_worker, daemon=True, name="LimitsAutoSync").start()


def get_accounts_metrics() -> Dict[str, Any]:
    """Gathers real-time multi-account pool metrics, success rates, latency, and official server quota stats."""
    raw_usage = load_account_usage()
    active_acc = GLOBAL_POOL.get_current_account()
    accounts_list = get_all_available_accounts(include_ineligible=True)

    server_limits = {}
    if SERVER_LIMITS_FILE.exists():
        try:
            server_limits = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    for acc in accounts_list:
        if acc not in raw_usage["accounts"]:
            raw_usage["accounts"][acc] = {
                "name": acc,
                "calls_total": 0,
                "calls_success": 0,
                "quota_errors": 0,
                "last_used": None,
                "last_latency_s": 0.0,
                "status": "READY",
                "last_error": "",
            }
        info = raw_usage["accounts"][acc]
        s_lim = server_limits.get(acc, {})
        info["email"] = s_lim.get("email")
        if s_lim.get("status") == "INELIGIBLE":
            info["status"] = "INELIGIBLE"
            info["error"] = s_lim.get("error", "Chưa đủ điều kiện Antigravity")
        info["weekly_remaining"] = s_lim.get("weekly_remaining", 100.0)
        info["weekly_reset"] = s_lim.get("weekly_reset")
        info["five_hour_remaining"] = s_lim.get("five_hour_remaining", 100.0)
        info["five_hour_reset"] = s_lim.get("five_hour_reset")
        info["claude_weekly_remaining"] = s_lim.get("claude_weekly_remaining", 100.0)
        info["claude_weekly_reset"] = s_lim.get("claude_weekly_reset")
        info["claude_5h_remaining"] = s_lim.get("claude_5h_remaining", 100.0)
        info["claude_5h_disabled"] = s_lim.get("claude_5h_disabled", False)
        info["claude_5h_reset"] = s_lim.get("claude_5h_reset")
        info["server_updated_at"] = s_lim.get("updated_at")

    total_calls = sum(a.get("calls_total", 0) for a in raw_usage["accounts"].values())
    total_success = sum(a.get("calls_success", 0) for a in raw_usage["accounts"].values())
    total_quota_errors = sum(a.get("quota_errors", 0) for a in raw_usage["accounts"].values())
    success_rate = round((total_success / total_calls * 100), 1) if total_calls > 0 else 100.0

    active_accs = raw_usage.get("active_accounts", [])
    if not active_accs:
        active_accs = [raw_usage.get("current_active", "acc1")]

    active_count = len([a for a in accounts_list if raw_usage["accounts"][a].get("status") != "INELIGIBLE"])
    ineligible_count = len([a for a in accounts_list if raw_usage["accounts"][a].get("status") == "INELIGIBLE"])

    return {
        "total": len(accounts_list),
        "active_count": active_count,
        "ineligible_count": ineligible_count,
        "list": accounts_list,
        "active": active_accs,
        "active_single": active_accs[0] if active_accs else "acc1",
        "total_calls": total_calls,
        "total_success": total_success,
        "total_quota_errors": total_quota_errors,
        "success_rate": success_rate,
        "accounts": raw_usage["accounts"],
        "server_limits_synced": bool(server_limits),
        "last_updated": raw_usage.get("last_updated"),
        "claude_fallback_enabled": True,
        "claude_models": ["claude-3-7-sonnet", "claude-3-5-haiku", "gpt-4o"],
    }


@app.post("/api/accounts/sync")
def api_sync_accounts():
    """Triggers background sync of server limits for all Antigravity accounts."""
    threading.Thread(target=sync_server_limits_job, daemon=True).start()
    return {"status": "syncing"}


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/api/status")
def api_status():
    """Returns overall real-time status across all 3 branches, runner pid, and RAM."""
    runner_pid = get_active_runner_pid()
    daemon_active = runner_pid is not None
    ram_info = get_system_ram_info()
    accounts_metrics = get_accounts_metrics()
    parsed_logs = parse_branch_logs()

    completed_works = scan_all_completed_works()
    w1_works = [w for w in completed_works if w["branch"] == "youtube_audio"]
    w2_works = [w for w in completed_works if w["branch"] == "fanfic_tts"]
    w3_works = [w for w in completed_works if w["branch"] == "ai_animation"]

    branch_cfg = get_branch_config()
    b1_on = branch_cfg.get("branch1_enabled", True)
    b2_on = branch_cfg.get("branch2_enabled", True)
    b3_on = branch_cfg.get("branch3_enabled", False)

    return {
        "daemon_active": daemon_active,
        "runner_pid": runner_pid,
        "ram": ram_info,
        "cloud": {
            "name": "Lightning AI CPU Studio",
            "cpus": 4,
            "ram_gb": 16,
            "status": "ONLINE",
            "tts_voices": "Ngọc Huyền Mới + CapCut Đa Giọng",
        },
        "current_cycle": parsed_logs["current_cycle"],
        "total_completed": len(completed_works),
        "server_time": datetime.datetime.now().strftime("%H:%M:%S · %d/%m/%Y"),
        "accounts": accounts_metrics,
        "branch_config": branch_cfg,
        "branches": {
            "branch1": {
                "id": "branch1",
                "enabled": b1_on,
                "name": "Nhánh 1: YouTube Fanfic Audio",
                "badge": "Audiobook Dài Tập",
                "tech": "yt-dlp + Gemini 3.8 Flash + Whisper Multi-EP",
                "color": "red",
                "current_status": parsed_logs["b1"]["status"] if b1_on else "⏸️ TẠM THỜI DỪNG",
                "completed_count": len(w1_works),
                "recent_work": w1_works[0] if w1_works else None,
                "logs": parsed_logs["b1"]["logs"],
            },
            "branch2": {
                "id": "branch2",
                "enabled": b2_on,
                "name": "Nhánh 2: Sáng Tác Fanfic -> TTS Ngọc Huyền",
                "badge": "Tiểu Thuyết Audio",
                "tech": "Gemini Sáng Tác + NghiTTS piper:ngochuyennew",
                "color": "cyan",
                "current_status": parsed_logs["b2"]["status"] if b2_on else "⏸️ TẠM THỜI DỪNG",
                "completed_count": len(w2_works),
                "recent_work": w2_works[0] if w2_works else None,
                "logs": parsed_logs["b2"]["logs"],
            },
            "branch3": {
                "id": "branch3",
                "enabled": b3_on,
                "name": "Nhánh 3: Hoạt Hình 2D Học Đường (SubVid & Đa Giọng)",
                "badge": "Chibi Anime Ngọt Sủng",
                "tech": "2D Tiểu Thuyết + Che Sub + ASS Vàng/Trắng + Lồng Tiếng Nam/Nữ",
                "color": "purple",
                "current_status": (
                    parsed_logs["b3"]["status"]
                    if b3_on
                    else "⏸️ TẠM THỜI DỪNG: Nhường 100% hạn mức Quota Gemini cho Nhánh 1 (Audiobook) & Nhánh 2 (Truyện chữ Fanfic)."
                ),
                "completed_count": len(w3_works),
                "recent_work": w3_works[0] if w3_works else None,
                "logs": parsed_logs["b3"]["logs"],
            },
        },
    }


@app.get("/api/branches/config")
def api_get_branches_config():
    return get_branch_config()


@app.post("/api/branches/toggle")
async def api_toggle_branch(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    branch = data.get("branch", "branch3")
    cfg = get_branch_config()
    key = f"{branch}_enabled" if not branch.endswith("_enabled") else branch
    if key in cfg:
        cfg[key] = not cfg[key]
    else:
        cfg[key] = True
    FACTORY_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return {"status": "ok", "config": cfg}



@app.get("/api/gallery")
def api_gallery():
    """Returns complete list of completed works and grouped series."""
    works = scan_all_completed_works()
    series = group_works_by_series(works)
    return {
        "total_series": len(series),
        "total_episodes": len(works),
        "series": series,
        "items": works,
    }


@app.get("/api/accounts")
def api_accounts():
    """Returns 8-account pool status and Claude/GPT usage limits."""
    return get_accounts_metrics()


@app.post("/api/accounts/sync")
@app.get("/api/accounts/sync")
def api_sync_accounts():
    """Triggers background sync of weekly & 5-hour limits from Google Antigravity servers."""
    threading.Thread(target=sync_server_limits_job, daemon=True).start()
    return {"status": "syncing", "message": "Đang đồng bộ hạn mức 5-Hour & Weekly Limit từ Google Antigravity..."}


@app.get("/api/logs")
def api_logs(tail: int = 80, branch: Optional[str] = None):
    """Returns runner logs, optionally filtered by branch."""
    if not LOG_FILE.exists():
        return {"lines": ["[Chưa có nhật ký hoạt động]"]}
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if branch == "1" or branch == "youtube":
            lines = [l for l in lines if "[NHÁNH 1" in l or "[NHA?NH 1" in l or "[Worker1]" in l]
        elif branch == "2" or branch == "fanfic":
            lines = [l for l in lines if "[NHÁNH 2" in l or "[NHA?NH 2" in l or "[Worker2]" in l]
        elif branch == "3" or branch == "animation":
            lines = [l for l in lines if "[NHÁNH 3" in l or "[NHA?NH 3" in l or "[Worker3]" in l]
        return {"lines": lines[-tail:]}
    except Exception as exc:
        return {"lines": [f"[Lỗi đọc log: {exc}]"]}


@app.get("/api/media/{branch}/{slug:path}/{filename}")
def api_media(branch: str, slug: str, filename: str):
    """Serves media assets (audio, video, covers, subtitles) for in-browser playback."""
    file_path = SPOOL_DIR / branch / slug / filename
    if not file_path.exists():
        # Fallback to album root if cover.jpg requested
        if filename in ("cover.jpg", "cover.webp", "cover.png") and "/" in slug:
            parent_slug = slug.rsplit("/", 1)[0]
            fallback_cover = SPOOL_DIR / branch / parent_slug / filename
            if fallback_cover.exists():
                file_path = fallback_cover
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    media_type = "application/octet-stream"
    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filename.endswith(".webp"):
        media_type = "image/webp"
    elif filename.endswith(".srt") or filename.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
    return FileResponse(str(file_path), media_type=media_type)


@app.post("/api/runner/start")
def api_start_runner():
    """Starts the overnight runner in background."""
    pid = get_active_runner_pid()
    if pid and pid > 0:
        return {"status": "already_running", "pid": pid}

    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    runner_python = venv_python if venv_python.exists() else Path(sys.executable)

    runner_script = PROJECT_ROOT / "scripts" / "content_factory" / "overnight_runner.py"
    try:
        proc = subprocess.Popen(
            [str(runner_python), str(runner_script)],
            cwd=str(PROJECT_ROOT),
            creationflags=NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        RUNNER_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        RUNNER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        return {"status": "started", "pid": proc.pid}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/runner/stop")
def api_stop_runner():
    """Safely stops the overnight runner process."""
    pid = get_active_runner_pid()
    if pid and pid > 0:
        try:
            subprocess.run(["taskkill", "/pid", str(pid), "/t", "/f"], creationflags=NO_WINDOW, capture_output=True)
        except Exception:
            pass
        RUNNER_PID_FILE.unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}
    return {"status": "not_running"}


@app.post("/api/system/purge_ram")
def api_purge_ram():
    """Instantly purges RAM working sets via Win32 API."""
    return purge_system_ram()


@app.post("/api/system/open_folder")
async def api_open_folder(request: Request):
    """Opens folder in native Windows Explorer."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    folder_path = data.get("path")
    if not folder_path:
        branch = data.get("branch")
        slug = data.get("slug")
        if branch and slug:
            folder_path = str(SPOOL_DIR / branch / slug)
        else:
            folder_path = str(SPOOL_DIR)

    p = Path(folder_path)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        subprocess.Popen(["explorer.exe", str(p)], creationflags=NO_WINDOW)
    return {"status": "opened", "path": str(p)}


# ==============================================================================
# HTML SPA FRONTEND
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def index():
    html_content = """<!DOCTYPE html>
<html lang="vi" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Router V4 Content Factory · Web Control Center</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #06090e; color: #f1f5f9; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .custom-scroll::-webkit-scrollbar { width: 5px; height: 5px; }
    .custom-scroll::-webkit-scrollbar-track { background: #0b0f19; }
    .custom-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    .custom-scroll::-webkit-scrollbar-thumb:hover { background: #475569; }
    .pulse-dot { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .3; transform: scale(0.85); } }
    .glow-b1 { box-shadow: 0 0 30px rgba(239, 68, 68, 0.12); }
    .glow-b2 { box-shadow: 0 0 30px rgba(6, 182, 212, 0.12); }
    .glow-b3 { box-shadow: 0 0 30px rgba(168, 85, 247, 0.12); }
    .tab-active { background: #0f172a; color: #38bdf8; border-color: #0284c7; }
  </style>
</head>
<body class="min-h-screen flex flex-col antialiased selection:bg-cyan-500 selection:text-black">

  <!-- TOP HEADER -->
  <header class="border-b border-gray-800/80 bg-gray-950/95 backdrop-blur sticky top-0 z-50">
    <div class="max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
      
      <!-- Brand & Title -->
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 via-indigo-600 to-purple-600 flex items-center justify-center font-black text-black text-xl shadow-lg shadow-indigo-950">
          <i class="fa-solid fa-layer-group"></i>
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <span class="font-extrabold text-lg tracking-tight text-white">ROUTER V4</span>
            <span class="text-[11px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 font-bold uppercase">Web Control Center</span>
          </div>
          <p class="text-[11px] text-gray-400">Điều Phối 3 Nhánh Tự Động Xuyên Đêm · 8 Tài Khoản Antigravity + Claude Fallback</p>
        </div>
      </div>

      <!-- Quick Control Actions & Indicators -->
      <div class="flex items-center space-x-3">
        <!-- Cloud CPU Studio Specs -->
        <div class="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-cyan-950/80 border border-cyan-800/80 text-cyan-300 text-xs font-mono shadow-sm" title="CPU Studio Lightning AI: 4 vCPUs / 16GB RAM (TTS Ngọc Huyền Mới + CapCut)">
          <i class="fa-solid fa-cloud text-cyan-400"></i>
          <span>Cloud CPU:</span>
          <strong class="text-white font-bold" id="cloudRamUsage">16 GB (4 vCPUs)</strong>
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
        </div>

        <!-- PC RAM Purge Button -->
        <button onclick="triggerPurgeRam()" id="btnPurgeRam" title="Giải phóng RAM local (EmptyWorkingSet)" class="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-gray-700 text-gray-300 text-xs font-mono transition active:scale-95 cursor-pointer">
          <i class="fa-solid fa-broom text-cyan-400 text-xs" id="iconPurgeRam"></i>
          <span>PC RAM:</span>
          <strong id="headerRamUsage" class="text-white">--/-- GB</strong>
        </button>

        <!-- Runner Daemon Status & Toggle Button -->
        <button onclick="toggleRunner()" id="btnToggleRunner" class="flex items-center space-x-2 px-3.5 py-1.5 rounded-xl bg-emerald-950/90 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 text-xs font-bold transition shadow-sm active:scale-95 cursor-pointer">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 pulse-dot" id="daemonDot"></span>
          <span id="daemonStatusText">ĐANG CHẠY</span>
        </button>

        <!-- Clock & Cycle -->
        <div class="text-right hidden sm:block pl-2 border-l border-gray-800">
          <div id="serverTime" class="text-xs font-semibold text-gray-300 mono">--:--:--</div>
          <div class="text-[10px] text-cyan-400/90 font-mono" id="cycleBadge">Chu kỳ #1</div>
        </div>
      </div>

    </div>
  </header>

  <!-- NAVIGATION TABS -->
  <nav class="border-b border-gray-800 bg-gray-900/60 sticky top-16 z-40 backdrop-blur">
    <div class="max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
      <div class="flex space-x-2 py-2">
        <button onclick="switchTab('monitor')" id="tabBtnMonitor" class="flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-extrabold transition border border-transparent tab-active">
          <i class="fa-solid fa-desktop"></i>
          <span>1. GIÁM SÁT TRỰC TIẾP (3 NHÁNH)</span>
        </button>

        <button onclick="switchTab('gallery')" id="tabBtnGallery" class="flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-extrabold text-gray-400 hover:text-white transition border border-transparent hover:bg-gray-800/60">
          <i class="fa-solid fa-book-bookmark text-indigo-400"></i>
          <span>2. KHO THÀNH PHẨM HOÀN THÀNH</span>
          <span id="navGalleryCount" class="ml-1.5 px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 text-[10px] font-mono">0</span>
        </button>

        <button onclick="switchTab('accounts')" id="tabBtnAccounts" class="flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-extrabold text-gray-400 hover:text-white transition border border-transparent hover:bg-gray-800/60">
          <i class="fa-brands fa-google text-amber-400"></i>
          <span>3. 8 TÀI KHOẢN & USAGE CLAUDE/GPT</span>
        </button>
      </div>

      <!-- Open Spool Folder 1-Click -->
      <button onclick="openFolderLocal()" class="hidden md:flex items-center space-x-1.5 text-xs text-gray-400 hover:text-cyan-400 transition font-mono">
        <i class="fa-regular fa-folder-open text-cyan-400"></i>
        <span>Mở Thư Mục raw_spool ➔</span>
      </button>
    </div>
  </nav>

  <!-- ==================================================================== -->
  <!-- TAB 1: GIÁM SÁT TRỰC TIẾP (3 NHÁNH SẢN XUẤT)                        -->
  <!-- ==================================================================== -->
  <div id="tabContentMonitor" class="max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 py-5 flex-1 w-full space-y-6">

    <!-- 3-Column Layout -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

      <!-- ======================================================== -->
      <!-- CỘT 1: NHÁNH 1 - YOUTUBE FANFIC AUDIO                    -->
      <!-- ======================================================== -->
      <div class="rounded-2xl bg-gray-950 border border-red-950/80 overflow-hidden shadow-xl flex flex-col glow-b1">
        <!-- Branch 1 Header -->
        <div class="p-4 bg-gradient-to-r from-red-950/80 to-gray-900 border-b border-red-900/50 flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-red-600/20 border border-red-500/30 flex items-center justify-center text-red-400 text-lg">
              <i class="fa-brands fa-youtube"></i>
            </div>
            <div>
              <h2 class="font-extrabold text-sm text-white tracking-wide">NHÁNH 1: YOUTUBE FANFIC AUDIO</h2>
              <p class="text-[11px] text-gray-400">Cạo Audio Dài Tập & Gemini Đánh Giá</p>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="toggleBranch('branch1')" id="b1ToggleBtn" class="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-700 text-emerald-300 text-[10px] font-bold font-mono transition cursor-pointer" title="Bật/Tắt Nhánh 1">
              🟢 BẬT
            </button>
            <span id="b1CountBadge" class="px-2.5 py-1 rounded-full bg-red-950 border border-red-700 text-red-300 text-xs font-bold font-mono">
              0 Xong
            </span>
          </div>
        </div>

        <!-- Branch 1 Current Status Card -->
        <div class="p-4 bg-gray-900/80 border-b border-gray-800">
          <div class="text-[11px] uppercase tracking-wider text-gray-400 font-bold flex items-center mb-1.5">
            <span class="w-2 h-2 rounded-full bg-red-400 pulse-dot mr-2"></span> ĐANG LÀM GÌ HIỆN TẠI:
          </div>
          <p id="b1CurrentStatus" class="text-xs text-red-200 font-medium leading-relaxed">
            Đang quét danh sách audio fanfic...
          </p>
        </div>

        <!-- Branch 1 Mini Log Stream -->
        <div class="p-3.5 bg-gray-950 border-b border-gray-800">
          <div class="text-[10px] uppercase font-bold text-gray-400 mb-1.5 flex items-center justify-between">
            <span><i class="fa-solid fa-terminal mr-1 text-red-400"></i> Tiến trình Nhánh 1:</span>
            <span class="text-[9px] text-gray-500 mono">Live stream</span>
          </div>
          <div id="b1LogBox" class="h-40 overflow-y-auto font-mono text-[11px] text-gray-300 space-y-1 custom-scroll bg-black/60 p-2.5 rounded-xl border border-gray-900">
            <div class="text-gray-500 italic">Đang nạp nhật ký...</div>
          </div>
        </div>

        <!-- Branch 1 Recent Work Card -->
        <div class="p-4 space-y-3" id="b1RecentBox">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center justify-between">
            <span><i class="fa-solid fa-star text-yellow-400 mr-1.5"></i> Tác Phẩm Mới Hoàn Thành</span>
            <button onclick="switchTab('gallery')" class="text-[11px] text-cyan-400 hover:underline">Xem tất cả ➔</button>
          </div>
          <div id="b1RecentCard" class="text-xs text-gray-500 italic p-3 rounded-xl bg-gray-900/50 border border-gray-800 text-center">
            Chưa có sản phẩm hoàn thành trong chu kỳ này.
          </div>
        </div>
      </div>

      <!-- ======================================================== -->
      <!-- CỘT 2: NHÁNH 2 - FANFIC NOVEL -> TTS NGỌC HUYỀN          -->
      <!-- ======================================================== -->
      <div class="rounded-2xl bg-gray-950 border border-cyan-950/80 overflow-hidden shadow-xl flex flex-col glow-b2">
        <!-- Branch 2 Header -->
        <div class="p-4 bg-gradient-to-r from-cyan-950/80 to-gray-900 border-b border-cyan-900/50 flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-cyan-600/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 text-lg">
              <i class="fa-solid fa-microphone-lines"></i>
            </div>
            <div>
              <h2 class="font-extrabold text-sm text-white tracking-wide">NHÁNH 2: TIỂU THUYẾT & FANFIC TTS</h2>
              <p class="text-[11px] text-gray-400">Sáng Tác Trường Thiên & CapCut TTS</p>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="toggleBranch('branch2')" id="b2ToggleBtn" class="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-700 text-emerald-300 text-[10px] font-bold font-mono transition cursor-pointer" title="Bật/Tắt Nhánh 2">
              🟢 BẬT
            </button>
            <span id="b2CountBadge" class="px-2.5 py-1 rounded-full bg-cyan-950 border border-cyan-700 text-cyan-300 text-xs font-bold font-mono">
              0 Xong
            </span>
          </div>
        </div>

        <!-- Branch 2 Current Status Card -->
        <div class="p-4 bg-gray-900/80 border-b border-gray-800">
          <div class="text-[11px] uppercase tracking-wider text-gray-400 font-bold flex items-center mb-1.5">
            <span class="w-2 h-2 rounded-full bg-cyan-400 pulse-dot mr-2"></span> ĐANG LÀM GÌ HIỆN TẠI:
          </div>
          <p id="b2CurrentStatus" class="text-xs text-cyan-200 font-medium leading-relaxed">
            Đang sẵn sàng đọc truyện...
          </p>
        </div>

        <!-- Branch 2 Mini Log Stream -->
        <div class="p-3.5 bg-gray-950 border-b border-gray-800">
          <div class="text-[10px] uppercase font-bold text-gray-400 mb-1.5 flex items-center justify-between">
            <span><i class="fa-solid fa-terminal mr-1 text-cyan-400"></i> Tiến trình Nhánh 2:</span>
            <span class="text-[9px] text-gray-500 mono">Live stream</span>
          </div>
          <div id="b2LogBox" class="h-40 overflow-y-auto font-mono text-[11px] text-gray-300 space-y-1 custom-scroll bg-black/60 p-2.5 rounded-xl border border-gray-900">
            <div class="text-gray-500 italic">Đang nạp nhật ký...</div>
          </div>
        </div>

        <!-- Branch 2 Recent Work Card -->
        <div class="p-4 space-y-3" id="b2RecentBox">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center justify-between">
            <span><i class="fa-solid fa-star text-yellow-400 mr-1.5"></i> Tác Phẩm Mới Hoàn Thành</span>
            <button onclick="switchTab('gallery')" class="text-[11px] text-cyan-400 hover:underline">Xem tất cả ➔</button>
          </div>
          <div id="b2RecentCard" class="text-xs text-gray-500 italic p-3 rounded-xl bg-gray-900/50 border border-gray-800 text-center">
            Chưa có sản phẩm hoàn thành trong chu kỳ này.
          </div>
        </div>
      </div>

      <!-- ======================================================== -->
      <!-- CỘT 3: NHÁNH 3 - HOẠT HÌNH AI (SUBVID & LỒNG TIẾNG)      -->
      <!-- ======================================================== -->
      <div class="rounded-2xl bg-gray-950 border border-purple-950/80 overflow-hidden shadow-xl flex flex-col glow-b3">
        <!-- Branch 3 Header -->
        <div class="p-4 bg-gradient-to-r from-purple-950/80 to-gray-900 border-b border-purple-900/50 flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400 text-lg">
              <i class="fa-solid fa-clapperboard"></i>
            </div>
            <div>
              <h2 class="font-extrabold text-sm text-white tracking-wide">NHÁNH 3: HOẠT HÌNH 2D HỌC ĐƯỜNG</h2>
              <p class="text-[11px] text-gray-400">Chibi Tiểu Thuyết + Che Sub + ASS Vàng/Trắng + Đa Giọng</p>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="toggleBranch('branch3')" id="b3ToggleBtn" class="px-2 py-0.5 rounded-full bg-amber-950 border border-amber-700 text-amber-300 text-[10px] font-bold font-mono transition cursor-pointer" title="Bật/Tắt Nhánh 3">
              ⏸️ TẠM DỪNG
            </button>
            <span id="b3CountBadge" class="px-2.5 py-1 rounded-full bg-purple-950 border border-purple-700 text-purple-300 text-xs font-bold font-mono">
              0 Xong
            </span>
          </div>
        </div>

        <!-- Branch 3 Current Status Card -->
        <div class="p-4 bg-gray-900/80 border-b border-gray-800">
          <div class="text-[11px] uppercase tracking-wider text-gray-400 font-bold flex items-center mb-1.5">
            <span class="w-2 h-2 rounded-full bg-purple-400 pulse-dot mr-2"></span> ĐANG LÀM GÌ HIỆN TẠI:
          </div>
          <p id="b3CurrentStatus" class="text-xs text-purple-200 font-medium leading-relaxed">
            Đang tìm kiếm anime romance/novel...
          </p>
        </div>

        <!-- Branch 3 Mini Log Stream -->
        <div class="p-3.5 bg-gray-950 border-b border-gray-800">
          <div class="text-[10px] uppercase font-bold text-gray-400 mb-1.5 flex items-center justify-between">
            <span><i class="fa-solid fa-terminal mr-1 text-purple-400"></i> Tiến trình Nhánh 3:</span>
            <span class="text-[9px] text-gray-500 mono">Live stream</span>
          </div>
          <div id="b3LogBox" class="h-40 overflow-y-auto font-mono text-[11px] text-gray-300 space-y-1 custom-scroll bg-black/60 p-2.5 rounded-xl border border-gray-900">
            <div class="text-gray-500 italic">Đang nạp nhật ký...</div>
          </div>
        </div>

        <!-- Branch 3 Recent Work Card -->
        <div class="p-4 space-y-3" id="b3RecentBox">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center justify-between">
            <span><i class="fa-solid fa-star text-yellow-400 mr-1.5"></i> Tác Phẩm Mới Hoàn Thành</span>
            <button onclick="switchTab('gallery')" class="text-[11px] text-cyan-400 hover:underline">Xem tất cả ➔</button>
          </div>
          <div id="b3RecentCard" class="text-xs text-gray-500 italic p-3 rounded-xl bg-gray-900/50 border border-gray-800 text-center">
            Chưa có sản phẩm hoàn thành trong chu kỳ này.
          </div>
        </div>
      </div>

    </div>

    <!-- COLLAPSIBLE MASTER CONSOLE STREAM -->
    <section class="rounded-2xl bg-gray-950 border border-gray-800 overflow-hidden shadow-lg">
      <div class="px-5 py-3 bg-gray-900 flex items-center justify-between border-b border-gray-800">
        <div class="flex items-center space-x-2.5 text-xs font-bold text-white">
          <i class="fa-solid fa-terminal text-cyan-400"></i>
          <span>TOÀN BỘ NHẬT KÝ HỆ THỐNG GỐC (FULL LOG STREAM)</span>
        </div>
        <div class="flex items-center space-x-3 text-xs">
          <label class="flex items-center space-x-1 text-gray-400 cursor-pointer">
            <input type="checkbox" id="chkAutoScroll" checked class="rounded bg-gray-800 border-gray-700 text-cyan-500 focus:ring-0">
            <span class="text-[11px]">Tự động cuộn</span>
          </label>
        </div>
      </div>
      <div id="fullTerminalBody" class="p-4 h-64 overflow-y-auto font-mono text-xs text-gray-300 space-y-1 custom-scroll bg-black/80 leading-relaxed">
        <div class="text-gray-500 italic">Đang đồng bộ nhật ký...</div>
      </div>
    </section>

  </div>


  <!-- ==================================================================== -->
  <!-- TAB 2: KHO THÀNH PHẨM HOÀN THÀNH (CHI TIẾT CÁC TẬP & MÔ TẢ NGẮN)     -->
  <!-- ==================================================================== -->
  <div id="tabContentGallery" class="max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 py-5 flex-1 w-full space-y-6 hidden">
    
    <!-- Gallery Filter Toolbar -->
    <div class="p-4 rounded-2xl bg-gray-950 border border-gray-800/80 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-2">
        <button onclick="filterGallery('all')" id="gFilterAll" class="px-3.5 py-1.5 rounded-xl bg-gray-800 text-white text-xs font-bold border border-gray-700 transition">
          Tất Cả (<span id="countAll">0</span> bộ · <span id="countAllEps">0</span> tập)
        </button>
        <button onclick="filterGallery('youtube_audio')" id="gFilterB1" class="px-3.5 py-1.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-red-300 text-xs font-bold border border-red-900/60 transition">
          🔴 YouTube Audio (<span id="countB1">0</span> bộ)
        </button>
        <button onclick="filterGallery('fanfic_tts')" id="gFilterB2" class="px-3.5 py-1.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-cyan-300 text-xs font-bold border border-cyan-900/60 transition">
          🔵 Fanfic & Tiểu Thuyết TTS (<span id="countB2">0</span> bộ)
        </button>
        <button onclick="filterGallery('ai_animation')" id="gFilterB3" class="px-3.5 py-1.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-purple-300 text-xs font-bold border border-purple-900/60 transition">
          🟣 Hoạt Hình AI SubVid (<span id="countB3">0</span> bộ)
        </button>
      </div>

      <!-- Search Input -->
      <div class="flex items-center space-x-3 w-full md:w-auto">
        <div class="relative w-full md:w-72">
          <i class="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs"></i>
          <input type="text" id="gallerySearchInput" oninput="onSearchGallery(this.value)" placeholder="Tìm theo tên bộ truyện, fandom..." class="w-full pl-9 pr-3 py-1.5 rounded-xl bg-gray-900 border border-gray-800 text-xs text-white focus:outline-none focus:border-cyan-500 font-medium">
        </div>

        <button onclick="fetchGallery()" title="Làm mới kho thành phẩm" class="px-3 py-1.5 rounded-xl bg-gray-900 hover:bg-gray-800 border border-gray-800 text-cyan-400 text-xs transition active:scale-95 cursor-pointer">
          <i class="fa-solid fa-arrows-rotate"></i>
        </button>
      </div>
    </div>

    <!-- Gallery Grid (Danh sách các Bộ Tác Phẩm) -->
    <div id="galleryGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      <div class="col-span-full text-center py-16 text-gray-500 italic">
        <i class="fa-solid fa-spinner fa-spin text-2xl mb-2 text-cyan-400"></i>
        <p>Đang tải toàn bộ sản phẩm hoàn thành...</p>
      </div>
    </div>

    <!-- Dedicated Series Detail Modal (UI Riêng Từng Bộ Tác Phẩm & Phân Chia Các Tập) -->
    <div id="seriesDetailModal" class="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 hidden">
      <div class="max-w-4xl w-full max-h-[92vh] bg-gray-950 border border-gray-800/90 rounded-3xl overflow-hidden shadow-2xl flex flex-col animate-in fade-in zoom-in-95 duration-200">
        
        <!-- Modal Top Bar -->
        <div class="px-6 py-4 bg-gray-900/80 border-b border-gray-800 flex items-center justify-between">
          <button onclick="closeSeriesModal()" class="flex items-center space-x-2 text-xs font-bold text-gray-300 hover:text-white px-3.5 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 transition cursor-pointer">
            <i class="fa-solid fa-arrow-left"></i>
            <span>Quay Lại Danh Sách Bộ</span>
          </button>

          <span id="mBranchBadge" class="px-3 py-1 rounded-lg text-xs font-extrabold text-white shadow"></span>

          <button onclick="closeSeriesModal()" class="w-8 h-8 rounded-full bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white flex items-center justify-center transition cursor-pointer" title="Đóng (Esc)">
            <i class="fa-solid fa-xmark text-sm"></i>
          </button>
        </div>

        <!-- Modal Scrollable Body -->
        <div class="p-6 overflow-y-auto custom-scroll space-y-6 flex-1">
          
          <!-- Series Hero Card -->
          <div class="flex flex-col sm:flex-row gap-5 items-start bg-gray-900/50 p-5 rounded-2xl border border-gray-800/60">
            <div id="mCoverContainer" class="w-full sm:w-44 aspect-video sm:aspect-square rounded-xl overflow-hidden bg-gray-900 shrink-0 border border-gray-800 shadow-md">
              <img id="mCoverImg" src="" alt="Series Cover" class="w-full h-full object-cover">
            </div>
            
            <div class="flex-1 space-y-2.5">
              <div class="flex flex-wrap items-center gap-2">
                <span id="mFandomBadge" class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-black/60 text-cyan-300 border border-cyan-900/50"></span>
                <span id="mScoreBadge" class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-800"></span>
                <span id="mEpisodesBadge" class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-purple-950 text-purple-300 border border-purple-800"></span>
                <span id="mDurationBadge" class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-gray-800 text-gray-300 border border-gray-700 font-mono"></span>
              </div>

              <h2 id="mSeriesTitle" class="text-lg sm:text-xl font-extrabold text-white leading-snug"></h2>

              <p id="mDescription" class="text-xs text-gray-300 leading-relaxed bg-black/30 p-3 rounded-xl border border-gray-800/40"></p>
              <div id="mOriginNotice"></div>
            </div>
          </div>

          <!-- Episodes Section Header -->
          <div class="flex items-center justify-between pt-2">
            <div class="flex items-center space-x-2">
              <i class="fa-solid fa-list-ol text-cyan-400 text-sm"></i>
              <h3 class="text-sm font-bold text-white uppercase tracking-wider">Danh Sách Các Tập / Chương Trong Bộ</h3>
            </div>
            <span id="mEpisodesCount" class="text-xs text-cyan-400 font-bold font-mono"></span>
          </div>

          <!-- Episode List Grid / Table -->
          <div id="mEpisodesList" class="space-y-3">
            <!-- Dynamically populated episode items -->
          </div>

        </div>

      </div>
    </div>

  </div>


  <!-- ==================================================================== -->
  <!-- TAB 3: QUẢN LÝ TÀI KHOẢN ANTIGRAVITY & USAGE CLAUDE/GPT              -->
  <!-- ==================================================================== -->
  <div id="tabContentAccounts" class="max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 py-5 flex-1 w-full space-y-6 hidden">
    
    <!-- Account Pool Overview Banner -->
    <div class="p-5 rounded-2xl bg-gradient-to-r from-gray-950 via-indigo-950/30 to-gray-950 border border-indigo-900/60 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
      <div>
        <div class="flex items-center space-x-2.5 mb-1">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 pulse-dot"></span>
          <h2 class="text-base font-extrabold text-white uppercase tracking-wide" id="poolHeaderTitle">ĐIỀU PHỐI ĐA TÀI KHOẢN GOOGLE ANTIGRAVITY + TỰ ĐỘNG CHUYỂN CLAUDE/GPT</h2>
        </div>
        <p class="text-xs text-gray-400">Hệ thống xoay vòng thông minh phân phối đều request, tự động nghỉ các tài khoản hạn mức thấp và chuyển dự phòng <span class="text-purple-300 font-semibold">Claude 3.7 Sonnet</span> & <span class="text-cyan-300 font-semibold">GPT-4o</span> khi cần.</p>
      </div>

      <div class="flex items-center space-x-3">
        <button onclick="triggerSyncQuota()" id="tabSyncQuotaBtn" class="flex items-center space-x-2 px-4 py-2 rounded-xl bg-indigo-900/80 hover:bg-indigo-800 border border-indigo-700 text-white text-xs font-bold transition shadow-sm active:scale-95 cursor-pointer">
          <i class="fa-solid fa-arrows-rotate text-xs" id="tabSyncQuotaIcon"></i>
          <span>Đồng bộ hạn mức từ Google</span>
        </button>
      </div>
    </div>

    <!-- Quick Stats Metric Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="p-3.5 rounded-2xl bg-gray-950/90 border border-gray-800 shadow-sm flex items-center justify-between">
        <div>
          <span class="text-[11px] text-gray-400 font-medium block">Tổng tài khoản</span>
          <span class="text-xl font-mono font-extrabold text-white" id="statTotalAccounts">13</span>
        </div>
        <div class="w-9 h-9 rounded-xl bg-indigo-950/80 border border-indigo-800/80 flex items-center justify-center text-indigo-400">
          <i class="fa-solid fa-users text-sm"></i>
        </div>
      </div>

      <div class="p-3.5 rounded-2xl bg-gray-950/90 border border-gray-800 shadow-sm flex items-center justify-between">
        <div>
          <span class="text-[11px] text-gray-400 font-medium block">Đang hoạt động (Pool)</span>
          <span class="text-xl font-mono font-extrabold text-emerald-400" id="statActiveAccounts">12</span>
        </div>
        <div class="w-9 h-9 rounded-xl bg-emerald-950/80 border border-emerald-800/80 flex items-center justify-center text-emerald-400">
          <i class="fa-solid fa-circle-check text-sm"></i>
        </div>
      </div>

      <div class="p-3.5 rounded-2xl bg-gray-950/90 border border-gray-800 shadow-sm flex items-center justify-between">
        <div>
          <span class="text-[11px] text-gray-400 font-medium block">Tổng lượt gọi API</span>
          <span class="text-xl font-mono font-extrabold text-cyan-400" id="statTotalCalls">0</span>
        </div>
        <div class="w-9 h-9 rounded-xl bg-cyan-950/80 border border-cyan-800/80 flex items-center justify-center text-cyan-400">
          <i class="fa-solid fa-bolt text-sm"></i>
        </div>
      </div>

      <div class="p-3.5 rounded-2xl bg-gray-950/90 border border-gray-800 shadow-sm flex items-center justify-between">
        <div>
          <span class="text-[11px] text-gray-400 font-medium block">Tỷ lệ thành công</span>
          <span class="text-xl font-mono font-extrabold text-purple-400" id="statSuccessRate">100%</span>
        </div>
        <div class="w-9 h-9 rounded-xl bg-purple-950/80 border border-purple-800/80 flex items-center justify-center text-purple-400">
          <i class="fa-solid fa-chart-line text-sm"></i>
        </div>
      </div>
    </div>

    <!-- BẢNG TỔNG HỢP CHI TIẾT HẠN MỨC (Master Quota Table) -->
    <div class="rounded-2xl bg-gray-950 border border-gray-800 shadow-xl overflow-hidden">
      <div class="px-5 py-3.5 border-b border-gray-800/80 flex items-center justify-between bg-black/40">
        <div class="flex items-center space-x-2.5">
          <i class="fa-solid fa-table-list text-cyan-400 text-sm"></i>
          <h3 class="text-xs font-bold text-white uppercase tracking-wider">Bảng Thống Kê Chi Tiết Hạn Mức Từng Tài Khoản</h3>
        </div>
        <span class="text-[11px] text-gray-400 font-mono" id="tableLastSyncTime">Đang cập nhật...</span>
      </div>

      <div class="overflow-x-auto custom-scroll">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="border-b border-gray-800/80 text-[11px] text-gray-400 font-semibold bg-gray-900/60 uppercase">
              <th class="py-3 px-4">Tài Khoản / Profile</th>
              <th class="py-3 px-4">Email Đăng Ký</th>
              <th class="py-3 px-4 text-center">Trạng Thái</th>
              <th class="py-3 px-4">Gemini (5-Hour)</th>
              <th class="py-3 px-4">Gemini (Weekly)</th>
              <th class="py-3 px-4">Claude 3.7 / GPT</th>
              <th class="py-3 px-4 text-center">Lượt Gọi (OK / Lỗi)</th>
              <th class="py-3 px-4 text-right">Độ Trễ</th>
            </tr>
          </thead>
          <tbody id="tabAccountsTableBody" class="divide-y divide-gray-900 font-mono text-[11px]">
            <tr>
              <td colspan="8" class="text-center py-8 text-gray-500 italic">Đang nạp dữ liệu hạn mức tài khoản...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- CARDS GRID HEADER -->
    <div class="flex items-center justify-between pt-2">
      <div class="flex items-center space-x-2">
        <i class="fa-solid fa-grip text-indigo-400 text-sm"></i>
        <h3 class="text-xs font-bold text-white uppercase tracking-wider">Thẻ Trực Quan Từng Tài Khoản</h3>
      </div>
      <span class="text-xs text-gray-400">Hiển thị trực quan theo thời gian thực</span>
    </div>

    <!-- CARDS GRID -->
    <div id="tabAccountsGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="col-span-full text-center py-8 text-gray-500 italic">Đang nạp dữ liệu thẻ...</div>
    </div>

  </div>


  <!-- FOOTER -->
  <footer class="border-t border-gray-900 bg-gray-950 py-3.5 text-center text-xs text-gray-500 mt-auto">
    Router V4 Content Factory · Chạy Web Siêu Nhẹ Thay Thế Desktop App · fanfic.world
  </footer>

  <!-- SCRIPT -->
  <script>
    let currentTab = 'monitor';
    let galleryData = [];
    let galleryFilterBranch = 'all';
    let gallerySearchKeyword = '';

    function switchTab(tab) {
      currentTab = tab;
      document.getElementById('tabContentMonitor').classList.toggle('hidden', tab !== 'monitor');
      document.getElementById('tabContentGallery').classList.toggle('hidden', tab !== 'gallery');
      document.getElementById('tabContentAccounts').classList.toggle('hidden', tab !== 'accounts');

      document.getElementById('tabBtnMonitor').classList.toggle('tab-active', tab === 'monitor');
      document.getElementById('tabBtnGallery').classList.toggle('tab-active', tab === 'gallery');
      document.getElementById('tabBtnAccounts').classList.toggle('tab-active', tab === 'accounts');

      if (tab === 'gallery') {
        fetchGallery();
      }
    }

    async function updateDashboard() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Server time & cycle
        document.getElementById('serverTime').innerText = data.server_time || '--:--:--';
        document.getElementById('cycleBadge').innerText = `Chu kỳ #${data.current_cycle || 1}`;

        // Runner daemon status
        const isRunning = data.daemon_active;
        const btnToggle = document.getElementById('btnToggleRunner');
        const dot = document.getElementById('daemonDot');
        const txt = document.getElementById('daemonStatusText');
        if (isRunning) {
          btnToggle.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-xl bg-emerald-950/90 hover:bg-rose-950/90 border border-emerald-700 hover:border-rose-700 text-emerald-300 hover:text-rose-300 text-xs font-bold transition shadow-sm active:scale-95 cursor-pointer';
          dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 pulse-dot';
          txt.innerText = data.runner_pid > 0 ? `ĐANG CHẠY (PID ${data.runner_pid})` : 'ĐANG CHẠY';
        } else {
          btnToggle.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-xl bg-rose-950/90 hover:bg-emerald-950/90 border border-rose-700 hover:border-emerald-700 text-rose-300 hover:text-emerald-300 text-xs font-bold transition shadow-sm active:scale-95 cursor-pointer';
          dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
          txt.innerText = 'ĐÃ TẮT · BẬT NGAY ➔';
        }

        // RAM info
        if (data.ram) {
          document.getElementById('headerRamUsage').innerText = `${data.ram.used_gb}/${data.ram.total_gb} GB (${data.ram.percent}%)`;
        }

        // Gallery count badge
        document.getElementById('navGalleryCount').innerText = data.total_completed ?? 0;

        // Branches
        const b1 = data.branches.branch1;
        document.getElementById('b1CountBadge').innerText = `${b1.completed_count} Xong`;
        document.getElementById('b1CurrentStatus').innerText = b1.current_status || 'Chờ điều phối...';
        renderLogBox('b1LogBox', b1.logs);
        renderRecentWork('b1RecentCard', b1.recent_work, 'red');

        const b2 = data.branches.branch2;
        document.getElementById('b2CountBadge').innerText = `${b2.completed_count} Xong`;
        document.getElementById('b2CurrentStatus').innerText = b2.current_status || 'Chờ điều phối...';
        renderLogBox('b2LogBox', b2.logs);
        renderRecentWork('b2RecentCard', b2.recent_work, 'cyan');

        const b3 = data.branches.branch3;
        document.getElementById('b3CountBadge').innerText = `${b3.completed_count} Xong`;
        document.getElementById('b3CurrentStatus').innerText = b3.current_status || 'Chờ điều phối...';
        renderLogBox('b3LogBox', b3.logs);
        renderRecentWork('b3RecentCard', b3.recent_work, 'purple');

        // Update branch toggle badges
        [
          { id: 'b1ToggleBtn', branch: 'branch1' },
          { id: 'b2ToggleBtn', branch: 'branch2' },
          { id: 'b3ToggleBtn', branch: 'branch3' }
        ].forEach(item => {
          const btn = document.getElementById(item.id);
          const bObj = data.branches[item.branch];
          if (btn && bObj) {
            if (bObj.enabled) {
              btn.className = 'px-2 py-0.5 rounded-full bg-emerald-950/80 hover:bg-rose-950/80 border border-emerald-700 hover:border-rose-700 text-emerald-300 hover:text-rose-300 text-[10px] font-bold font-mono transition cursor-pointer active:scale-95';
              btn.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block mr-1"></span>BẬT';
              btn.title = 'Nhấp để tạm dừng nhánh này';
            } else {
              btn.className = 'px-2 py-0.5 rounded-full bg-amber-950/80 hover:bg-emerald-950/80 border border-amber-700 hover:border-emerald-700 text-amber-300 hover:text-emerald-300 text-[10px] font-bold font-mono transition cursor-pointer active:scale-95';
              btn.innerHTML = '⏸️ TẠM DỪNG';
              btn.title = 'Nhấp để kích hoạt lại nhánh này';
            }
          }
        });

        // Accounts tab
        if (data.accounts) {
          renderAccountsGridTab(data.accounts);
        }

      } catch (err) {
        console.error('Lỗi fetch status:', err);
      }
    }

    async function toggleBranch(branch) {
      try {
        await fetch('/api/branches/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ branch: branch })
        });
        updateDashboard();
      } catch (e) {
        console.error('Lỗi toggle branch:', e);
      }
    }

    function renderRecentWork(elementId, work, color) {
      const box = document.getElementById(elementId);
      if (!work) {
        box.innerHTML = '<div class="text-gray-500 italic p-3 text-center text-xs">Chưa có sản phẩm hoàn tất trong nhánh này.</div>';
        return;
      }
      box.innerHTML = `
        <div class="p-3 rounded-xl bg-gray-900/90 border border-gray-800 space-y-2">
          <div class="flex items-start justify-between gap-2">
            <h4 class="font-bold text-white text-xs leading-snug line-clamp-2">${escapeHtml(work.title)}</h4>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold whitespace-nowrap">★ ${work.score}</span>
          </div>
          <div class="text-[11px] text-cyan-300 font-medium">${escapeHtml(work.episodes_detail || '')}</div>
          <p class="text-[11px] text-gray-400 line-clamp-2">${escapeHtml(work.description_short || '')}</p>
          ${work.has_audio ? `
            <audio controls class="w-full h-7 rounded bg-black/40 mt-1">
              <source src="/api/media/${work.branch}/${work.slug}/${work.audio_file}" type="audio/mpeg">
            </audio>
          ` : ''}
        </div>
      `;
    }

    let seriesData = [];
    let allWorksData = [];

    async function fetchGallery() {
      try {
        const res = await fetch('/api/gallery');
        const data = await res.json();
        seriesData = data.series || [];
        allWorksData = data.items || [];
        updateGalleryCounters();
        renderGallery();
      } catch (err) {
        console.error('Lỗi nạp kho thành phẩm:', err);
      }
    }

    function updateGalleryCounters() {
      const totalSeries = seriesData.length;
      const totalEps = allWorksData.length;
      const elAll = document.getElementById('countAll');
      if (elAll) elAll.innerText = totalSeries;
      const elAllEps = document.getElementById('countAllEps');
      if (elAllEps) elAllEps.innerText = totalEps;
      const elB1 = document.getElementById('countB1');
      if (elB1) elB1.innerText = seriesData.filter(s => s.branch === 'youtube_audio').length;
      const elB2 = document.getElementById('countB2');
      if (elB2) elB2.innerText = seriesData.filter(s => s.branch === 'fanfic_tts').length;
      const elB3 = document.getElementById('countB3');
      if (elB3) elB3.innerText = seriesData.filter(s => s.branch === 'ai_animation').length;
    }

    function filterGallery(branch) {
      galleryFilterBranch = branch;
      ['All', 'B1', 'B2', 'B3'].forEach(k => {
        const btn = document.getElementById('gFilter' + k);
        if (btn) btn.classList.remove('ring-2', 'ring-cyan-400');
      });
      const activeBtn = document.getElementById(branch === 'all' ? 'gFilterAll' : (branch === 'youtube_audio' ? 'gFilterB1' : (branch === 'fanfic_tts' ? 'gFilterB2' : 'gFilterB3')));
      if (activeBtn) activeBtn.classList.add('ring-2', 'ring-cyan-400');
      renderGallery();
    }

    function onSearchGallery(val) {
      gallerySearchKeyword = (val || '').trim().toLowerCase();
      renderGallery();
    }

    function renderGallery() {
      const container = document.getElementById('galleryGrid');
      let list = seriesData;

      if (galleryFilterBranch !== 'all') {
        list = list.filter(s => s.branch === galleryFilterBranch);
      }

      if (gallerySearchKeyword) {
        list = list.filter(s => 
          (s.series_title && s.series_title.toLowerCase().includes(gallerySearchKeyword)) ||
          (s.fandom && s.fandom.toLowerCase().includes(gallerySearchKeyword)) ||
          (s.description && s.description.toLowerCase().includes(gallerySearchKeyword))
        );
      }

      if (!list.length) {
        container.innerHTML = `
          <div class="col-span-full text-center py-16 text-gray-500">
            <i class="fa-solid fa-box-open text-3xl mb-3 text-gray-600"></i>
            <p class="text-sm font-medium">Không tìm thấy bộ tác phẩm nào phù hợp điều kiện lọc.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = list.map(s => {
        const coverUrl = s.cover_file ? `/api/media/${s.branch}/${s.cover_slug}/${s.cover_file}` : '';
        const epUnit = s.branch === 'fanfic_tts' ? 'Chương' : 'Tập';

        return `
          <div class="rounded-3xl bg-gray-950 border border-gray-800/90 hover:border-cyan-800/60 transition-all duration-300 overflow-hidden shadow-xl hover:shadow-cyan-950/20 flex flex-col justify-between group cursor-pointer" onclick="openSeriesModal('${s.series_id}')">
            
            <!-- Cover Banner -->
            <div class="relative w-full aspect-video bg-gray-900 overflow-hidden flex items-center justify-center">
              ${coverUrl ? `
                <img src="${coverUrl}" alt="${escapeHtml(s.series_title)}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500">
              ` : `
                <div class="w-full h-full flex flex-col items-center justify-center bg-gradient-to-tr from-gray-950 via-gray-900 to-gray-800 text-gray-600">
                  <span class="text-3xl mb-1">${s.branch_icon}</span>
                  <span class="text-[10px] font-mono text-gray-500 uppercase">${s.branch_label}</span>
                </div>
              `}
              <div class="absolute inset-0 bg-gradient-to-t from-gray-950 via-transparent to-black/40"></div>

              <!-- Top Badges -->
              <div class="absolute top-2.5 left-2.5 flex items-center space-x-1.5">
                <span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold text-white shadow" style="background-color: ${s.branch_color}">
                  ${s.branch_label}
                </span>
                <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-black/75 text-cyan-300 border border-cyan-900/50 backdrop-blur-sm">
                  ${escapeHtml(s.fandom)}
                </span>
              </div>

              <div class="absolute top-2.5 right-2.5">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-700 backdrop-blur-sm shadow">
                  ★ ${s.score}
                </span>
              </div>

              <!-- Bottom Indicators -->
              <div class="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between">
                <span class="px-2.5 py-0.5 rounded-lg bg-purple-950/90 text-purple-200 border border-purple-800 text-[10px] font-extrabold backdrop-blur-sm shadow">
                  <i class="fa-solid fa-layer-group mr-1"></i>Trọn bộ ${s.total_episodes} ${epUnit}
                </span>

                ${s.total_duration_formatted ? `
                  <span class="px-2 py-0.5 rounded-lg bg-black/80 text-[10px] font-mono text-cyan-300 font-bold backdrop-blur-sm border border-gray-800">
                    <i class="fa-regular fa-clock mr-1"></i>${s.total_duration_formatted}
                  </span>
                ` : ''}
              </div>
            </div>

            <!-- Content Details -->
            <div class="p-5 flex-1 flex flex-col justify-between space-y-4">
              <div>
                <h3 class="font-extrabold text-white text-sm leading-snug line-clamp-2 group-hover:text-cyan-300 transition" title="${escapeHtml(s.series_title)}">
                  ${escapeHtml(s.series_title)}
                </h3>

                <div class="mt-2 flex items-center space-x-2 text-[11px]">
                  ${s.branch === 'youtube_audio'
                    ? '<span class="text-amber-400/90 font-medium"><i class="fa-brands fa-youtube mr-1 text-red-500"></i>Audio gốc kênh YouTube</span>'
                    : (s.branch === 'fanfic_tts'
                      ? `<span class="text-cyan-300 font-medium"><i class="fa-solid fa-microphone mr-1 text-cyan-400"></i>${escapeHtml(s.episodes[0]?.voice_name || 'CapCut TTS (Cô Gái Hoạt Ngôn / Nhỏ Ngọt Ngào)')}</span>`
                      : '<span class="text-purple-300 font-medium"><i class="fa-solid fa-clapperboard mr-1 text-purple-400"></i>Đa Giọng CapCut Dubbing</span>')}
                </div>

                <p class="mt-2 text-xs text-gray-400 line-clamp-2 leading-relaxed">
                  ${escapeHtml(s.description || 'Tác phẩm fanfic trọn bộ đã được thu thập, biên kịch và sản xuất giọng đọc hoàn chỉnh.')}
                </p>
              </div>

              <!-- Action Bar -->
              <div class="pt-3 border-t border-gray-900 flex items-center justify-between gap-2">
                <button onclick="event.stopPropagation(); openSeriesModal('${s.series_id}')" class="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-gray-900 to-gray-800 hover:from-cyan-950 hover:to-blue-950 border border-gray-800 hover:border-cyan-800/80 text-gray-300 hover:text-cyan-300 text-xs font-bold transition flex items-center justify-center space-x-1.5 shadow active:scale-95 cursor-pointer">
                  <i class="fa-solid fa-folder-tree text-cyan-400"></i>
                  <span>Xem Chi Tiết (${s.total_episodes} tập) ➔</span>
                </button>
              </div>
            </div>

          </div>
        `;
      }).join('');
    }

    function openSeriesModal(seriesId) {
      const s = seriesData.find(x => x.series_id === seriesId);
      if (!s) return;

      const modal = document.getElementById('seriesDetailModal');
      const epUnit = s.branch === 'fanfic_tts' ? 'Chương' : 'Tập';
      const coverUrl = s.cover_file ? `/api/media/${s.branch}/${s.cover_slug}/${s.cover_file}` : '';

      document.getElementById('mBranchBadge').innerText = s.branch_label;
      document.getElementById('mBranchBadge').style.backgroundColor = s.branch_color;
      document.getElementById('mFandomBadge').innerText = s.fandom;
      document.getElementById('mScoreBadge').innerText = `★ ${s.score}`;
      document.getElementById('mEpisodesBadge').innerText = `Trọn bộ ${s.total_episodes} ${epUnit}`;
      document.getElementById('mDurationBadge').innerText = s.total_duration_formatted ? `⏱️ ${s.total_duration_formatted}` : '';
      document.getElementById('mSeriesTitle').innerText = s.series_title;
      document.getElementById('mDescription').innerText = s.description || 'Chưa có tóm tắt chi tiết.';
      document.getElementById('mEpisodesCount').innerText = `${s.total_episodes} ${epUnit.toUpperCase()}`;

      // Origin Notice
      const noticeBox = document.getElementById('mOriginNotice');
      if (noticeBox) {
        if (s.branch === 'youtube_audio') {
          noticeBox.className = 'mt-2 text-xs text-amber-300 bg-amber-950/40 p-3 rounded-xl border border-amber-800/60 flex items-start gap-2.5';
          noticeBox.innerHTML = '<i class="fa-solid fa-circle-info text-amber-400 text-sm mt-0.5 shrink-0"></i><div><strong>Nguồn Audio YouTube gốc:</strong> Bộ truyện này được cỗ máy Nhánh 1 tự động tải về nguyên bản từ kênh YouTube. Giọng đọc trong audio là giọng của kênh YouTube phát hành.</div>';
        } else if (s.branch === 'fanfic_tts') {
          noticeBox.className = 'mt-2 text-xs text-cyan-300 bg-cyan-950/40 p-3 rounded-xl border border-cyan-800/60 flex items-start gap-2.5';
          noticeBox.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles text-cyan-400 text-sm mt-0.5 shrink-0"></i><div><strong>Sản xuất trực tiếp bằng giọng đọc CapCut:</strong> Kịch bản do AI sáng tác trường thiên và được lồng tiếng chất lượng cao bằng <strong>${escapeHtml(s.episodes[0]?.voice_name || 'CapCut TTS')}</strong>.</div>`;
        } else {
          noticeBox.className = 'mt-2 text-xs text-purple-300 bg-purple-950/40 p-3 rounded-xl border border-purple-800/60 flex items-start gap-2.5';
          noticeBox.innerHTML = '<i class="fa-solid fa-clapperboard text-purple-400 text-sm mt-0.5 shrink-0"></i><div><strong>Phim Hoạt Hình AI SubVid:</strong> Video được nhận diện qua GPU Lightning AI, Gemini dịch & phân vai và lồng tiếng đa giọng CapCut.</div>';
        }
      }

      const coverImg = document.getElementById('mCoverImg');
      if (coverUrl) {
        coverImg.src = coverUrl;
        coverImg.classList.remove('hidden');
      } else {
        coverImg.classList.add('hidden');
      }

      // Render Episodes List
      const epContainer = document.getElementById('mEpisodesList');
      epContainer.innerHTML = s.episodes.map(ep => {
        const audioUrl = ep.has_audio ? `/api/media/${s.branch}/${ep.slug}/${ep.audio_file}` : '';
        const videoUrl = ep.has_video ? `/api/media/${s.branch}/${ep.slug}/${ep.video_file}` : '';
        const voiceBadge = s.branch === 'youtube_audio'
          ? '<span class="px-2 py-0.5 rounded bg-red-950/80 text-red-300 border border-red-800 text-[10px] font-bold"><i class="fa-brands fa-youtube mr-1"></i>Audio Kênh YouTube</span>'
          : (s.branch === 'fanfic_tts'
            ? `<span class="px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800 text-[10px] font-bold"><i class="fa-solid fa-microphone mr-1"></i>${escapeHtml(ep.voice_name || 'CapCut TTS')}</span>`
            : '<span class="px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800 text-[10px] font-bold"><i class="fa-solid fa-clapperboard mr-1"></i>Đa Vai CapCut</span>');

        return `
          <div class="p-4 rounded-2xl bg-gray-900/90 border border-gray-800/90 hover:border-gray-700 transition flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            
            <div class="flex-1 space-y-1.5">
              <div class="flex items-center space-x-2">
                <span class="px-2.5 py-0.5 rounded-md text-xs font-extrabold text-white shrink-0 shadow" style="background-color: ${s.branch_color}">
                  ${escapeHtml(ep.ep_label)}
                </span>
                ${voiceBadge}
                <h4 class="font-bold text-white text-xs sm:text-sm line-clamp-1" title="${escapeHtml(ep.title)}">
                  ${escapeHtml(ep.title)}
                </h4>
              </div>

              <div class="text-[11px] text-gray-400 flex flex-wrap items-center gap-3">
                ${ep.duration_formatted ? `
                  <span class="font-mono text-cyan-300"><i class="fa-regular fa-clock mr-1 text-cyan-400"></i>${ep.duration_formatted}</span>
                ` : ''}
                <span><i class="fa-regular fa-calendar mr-1 text-purple-400"></i>${ep.time_str}</span>
                <span class="text-gray-300 font-medium">${escapeHtml(ep.episodes_detail || '')}</span>
              </div>
            </div>

            <!-- Player & Actions -->
            <div class="flex flex-wrap items-center gap-3 shrink-0">
              ${audioUrl ? `
                <div class="flex items-center space-x-2">
                  <audio controls class="w-56 sm:w-64 h-8 rounded bg-black/60 shadow">
                    <source src="${audioUrl}" type="audio/mpeg">
                  </audio>
                </div>
              ` : ''}

              ${videoUrl ? `
                <a href="${videoUrl}" target="_blank" class="px-3 py-1.5 rounded-xl bg-purple-900/80 hover:bg-purple-800 border border-purple-700 text-purple-200 text-xs font-bold transition flex items-center space-x-1.5 shadow cursor-pointer">
                  <i class="fa-solid fa-play text-xs"></i>
                  <span>Xem Video</span>
                </a>
              ` : ''}

              <button onclick="openWorkFolder('${s.branch}', '${escapeHtml(ep.slug)}')" class="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 hover:text-white text-xs font-bold transition flex items-center space-x-1.5 shadow active:scale-95 cursor-pointer" title="Mở thư mục tập này trên máy tính">
                <i class="fa-regular fa-folder-open text-cyan-400"></i>
                <span>Mở Folder</span>
              </button>
            </div>

          </div>
        `;
      }).join('');

      modal.classList.remove('hidden');
      document.body.classList.add('overflow-hidden');
    }

    function closeSeriesModal() {
      const modal = document.getElementById('seriesDetailModal');
      modal.classList.add('hidden');
      document.body.classList.remove('overflow-hidden');

      // Pause any audio/video currently playing inside modal
      const mediaElements = modal.querySelectorAll('audio, video');
      mediaElements.forEach(el => el.pause());
    }

    // Close modal on Escape key or outside click
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeSeriesModal();
    });
    document.getElementById('seriesDetailModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'seriesDetailModal') closeSeriesModal();
    });

    function formatCountdown(isoStr) {
      if (!isoStr) return '--';
      try {
        const target = new Date(isoStr).getTime();
        const now = Date.now();
        const diffMs = target - now;
        if (diffMs <= 0) return 'Đã mở lại';
        const mins = Math.floor((diffMs / 1000 / 60) % 60);
        const hours = Math.floor(diffMs / 1000 / 3600);
        if (hours > 24) {
          const days = Math.floor(hours / 24);
          return `${days}d ${hours % 24}h`;
        }
        return `${hours}h ${mins}m`;
      } catch (e) {
        return '--';
      }
    }

    function renderAccountsGridTab(accData) {
      const container = document.getElementById('tabAccountsGrid');
      const tableBody = document.getElementById('tabAccountsTableBody');
      if (!accData || !accData.accounts) return;

      const activeAcc = accData.active;
      const accounts = accData.accounts;
      const list = accData.list || Object.keys(accounts);

      // Update Quick Stats Metric Cards
      const totalAccs = accData.total || list.length;
      const activeCount = accData.active_count ?? list.filter(a => (accounts[a] || {}).status !== 'INELIGIBLE').length;
      const totalCalls = accData.total_calls ?? 0;
      const successRate = accData.success_rate ?? 100.0;

      const elTotal = document.getElementById('statTotalAccounts');
      if (elTotal) elTotal.innerText = totalAccs;
      const elActive = document.getElementById('statActiveAccounts');
      if (elActive) elActive.innerText = activeCount;
      const elCalls = document.getElementById('statTotalCalls');
      if (elCalls) elCalls.innerText = totalCalls;
      const elRate = document.getElementById('statSuccessRate');
      if (elRate) elRate.innerText = `${successRate}%`;

      const elLastSync = document.getElementById('tableLastSyncTime');
      if (elLastSync && accData.last_updated) {
        elLastSync.innerText = `Cập nhật lúc: ${accData.last_updated}`;
      }

      // Render Master Quota Table
      if (tableBody) {
        tableBody.innerHTML = list.map((accName, idx) => {
          const acc = accounts[accName] || {
            name: accName, calls_total: 0, calls_success: 0, quota_errors: 0,
            last_used: null, last_latency_s: 0, status: 'READY',
            weekly_remaining: 100, five_hour_remaining: 100, claude_weekly_remaining: 100
          };
          const activeList = Array.isArray(activeAcc) ? activeAcc : [activeAcc];
          const isBusyNow = activeList.includes(accName);
          const isIneligible = (acc.status === 'INELIGIBLE');
          const hasQuotaHit = (acc.quota_errors > 0);

          let statusBadge = `<span class="px-2 py-0.5 rounded bg-gray-900 text-gray-400 font-mono font-medium text-[10px]">SẴN SÀNG</span>`;
          if (isIneligible) {
            statusBadge = `<span class="px-2 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-800 font-mono font-bold text-[10px]">CHƯA ĐỦ ĐIỀU KIỆN</span>`;
          } else if (isBusyNow) {
            statusBadge = `<span class="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-500 font-mono font-bold text-[10px] inline-flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot"></span>ĐANG GỌI</span>`;
          } else if (hasQuotaHit) {
            statusBadge = `<span class="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono font-bold text-[10px]">429 LIMIT</span>`;
          } else if (acc.calls_total > 0) {
            statusBadge = `<span class="px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-700 font-mono font-bold text-[10px]">ACTIVE</span>`;
          }

          const h5Pct = typeof acc.five_hour_remaining === 'number' ? acc.five_hour_remaining : 100;
          const wkPct = typeof acc.weekly_remaining === 'number' ? acc.weekly_remaining : 100;
          const cldPct = typeof acc.claude_weekly_remaining === 'number' ? acc.claude_weekly_remaining : 100;

          const h5Countdown = formatCountdown(acc.five_hour_reset);
          const wkCountdown = formatCountdown(acc.weekly_reset);
          const cldCountdown = formatCountdown(acc.claude_weekly_reset);

          const emailDisplay = acc.email ? `<span class="text-gray-300">${escapeHtml(acc.email)}</span>` : `<span class="text-gray-600 italic">Mặc định</span>`;
          const latencyDisplay = acc.last_latency_s > 0 ? `${acc.last_latency_s}s` : `--`;

          return `
            <tr class="hover:bg-gray-900/40 transition-colors ${isBusyNow ? 'bg-amber-950/20' : (isIneligible ? 'bg-rose-950/10' : '')}">
              <td class="py-2.5 px-4 font-bold text-white flex items-center space-x-2">
                <i class="fa-solid fa-user-shield text-xs ${isIneligible ? 'text-rose-500' : 'text-cyan-400'}"></i>
                <span>${escapeHtml(accName)}</span>
              </td>
              <td class="py-2.5 px-4">${emailDisplay}</td>
              <td class="py-2.5 px-4 text-center">${statusBadge}</td>
              <td class="py-2.5 px-4">
                <div class="flex items-center justify-between text-[10px] mb-0.5">
                  <span class="font-bold ${h5Pct <= 20 ? 'text-rose-400' : 'text-emerald-400'}">${h5Pct}%</span>
                  <span class="text-gray-500">${h5Countdown}</span>
                </div>
                <div class="w-28 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div class="${h5Pct <= 20 ? 'bg-rose-500' : 'bg-emerald-400'} h-1.5 rounded-full" style="width: ${h5Pct}%"></div>
                </div>
              </td>
              <td class="py-2.5 px-4">
                <div class="flex items-center justify-between text-[10px] mb-0.5">
                  <span class="font-bold ${wkPct <= 20 ? 'text-rose-400' : 'text-cyan-400'}">${wkPct}%</span>
                  <span class="text-gray-500">${wkCountdown}</span>
                </div>
                <div class="w-28 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div class="${wkPct <= 20 ? 'bg-rose-500' : 'bg-cyan-400'} h-1.5 rounded-full" style="width: ${wkPct}%"></div>
                </div>
              </td>
              <td class="py-2.5 px-4">
                <div class="flex items-center justify-between text-[10px] mb-0.5">
                  <span class="font-bold ${cldPct <= 0 ? 'text-rose-400' : 'text-purple-400'}">${cldPct}%</span>
                  <span class="text-gray-500">${cldCountdown}</span>
                </div>
                <div class="w-28 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div class="${cldPct <= 0 ? 'bg-rose-500' : 'bg-purple-400'} h-1.5 rounded-full" style="width: ${cldPct}%"></div>
                </div>
              </td>
              <td class="py-2.5 px-4 text-center">
                <span class="text-white font-bold">${acc.calls_total}</span>
                <span class="text-gray-500">/</span>
                <span class="text-emerald-400 font-bold">${acc.calls_success}</span>
                ${acc.quota_errors > 0 ? `<span class="text-rose-400 ml-1">(${acc.quota_errors} lỗi)</span>` : ''}
              </td>
              <td class="py-2.5 px-4 text-right text-gray-400">${latencyDisplay}</td>
            </tr>
          `;
        }).join('');
      }

      // Render Visual Cards Grid
      if (container) {
        container.innerHTML = list.map(accName => {
          const acc = accounts[accName] || {
            name: accName, calls_total: 0, calls_success: 0, quota_errors: 0,
            last_used: null, last_latency_s: 0, status: 'READY',
            weekly_remaining: 100, five_hour_remaining: 100, claude_weekly_remaining: 100
          };

          const activeList = Array.isArray(activeAcc) ? activeAcc : [activeAcc];
          const isBusyNow = activeList.includes(accName);
          const isIneligible = (acc.status === 'INELIGIBLE');
          const isUsed = (acc.calls_total > 0 && acc.status === 'ACTIVE');
          const hasQuotaHit = (acc.quota_errors > 0);

          let borderClass = 'border-gray-800 bg-gray-950';
          let statusBadge = `<span class="text-[10px] px-2 py-0.5 rounded bg-gray-900 text-gray-400 font-mono font-medium">SẴN SÀNG</span>`;

          if (isIneligible) {
            borderClass = 'border-rose-900/60 bg-rose-950/20';
            statusBadge = `<span class="text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-mono font-bold">CHƯA DUYỆT</span>`;
          } else if (isBusyNow) {
            borderClass = 'border-amber-400 bg-amber-950/30 shadow-lg shadow-amber-950/50 ring-2 ring-amber-400/50';
            statusBadge = `<span class="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-500 font-mono font-bold flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot"></span>ĐANG GỌI</span>`;
          } else if (isUsed) {
            borderClass = 'border-cyan-500/80 bg-cyan-950/20 ring-1 ring-cyan-500/40';
            statusBadge = `<span class="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-700 font-mono font-bold flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>ACTIVE</span>`;
          } else if (hasQuotaHit) {
            borderClass = 'border-amber-700 bg-amber-950/20';
            statusBadge = `<span class="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono font-bold">429 LIMIT</span>`;
          }

          const h5Pct = typeof acc.five_hour_remaining === 'number' ? acc.five_hour_remaining : 100;
          const wkPct = typeof acc.weekly_remaining === 'number' ? acc.weekly_remaining : 100;
          const cldPct = typeof acc.claude_weekly_remaining === 'number' ? acc.claude_weekly_remaining : 100;

          const h5Countdown = formatCountdown(acc.five_hour_reset);
          const wkCountdown = formatCountdown(acc.weekly_reset);
          const cldCountdown = formatCountdown(acc.claude_weekly_reset);

          return `
            <div class="rounded-2xl border ${borderClass} p-4 flex flex-col justify-between shadow-lg">
              <div class="flex items-start justify-between mb-2">
                <div>
                  <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-user-shield text-sm ${isIneligible ? 'text-rose-400' : 'text-cyan-400'}"></i>
                    <span class="font-mono font-extrabold text-sm text-white">${escapeHtml(accName)}</span>
                  </div>
                  ${acc.email ? `<div class="text-[10px] text-gray-400 font-mono truncate max-w-[160px]" title="${escapeHtml(acc.email)}">${escapeHtml(acc.email)}</div>` : ''}
                </div>
                ${statusBadge}
              </div>

              <!-- Limits -->
              <div class="space-y-2.5 p-3 rounded-xl bg-black/50 border border-gray-800/80 mb-3">
                <!-- Gemini 5h -->
                <div>
                  <div class="flex items-center justify-between text-[11px] mb-1">
                    <span class="text-gray-400 font-medium">Gemini 5-Hour:</span>
                    <span class="font-mono font-bold ${h5Pct <= 20 ? 'text-rose-400' : 'text-emerald-400'}">${h5Pct}% <span class="text-[9px] text-gray-500">(${h5Countdown})</span></span>
                  </div>
                  <div class="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div class="${h5Pct <= 20 ? 'bg-rose-500' : 'bg-emerald-400'} h-2 rounded-full transition-all duration-500" style="width: ${h5Pct}%"></div>
                  </div>
                </div>

                <!-- Gemini Wk -->
                <div>
                  <div class="flex items-center justify-between text-[11px] mb-1">
                    <span class="text-gray-400 font-medium">Gemini Weekly:</span>
                    <span class="font-mono font-bold ${wkPct <= 20 ? 'text-rose-400' : 'text-cyan-400'}">${wkPct}% <span class="text-[9px] text-gray-500">(${wkCountdown})</span></span>
                  </div>
                  <div class="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div class="${wkPct <= 20 ? 'bg-rose-500' : 'bg-cyan-400'} h-2 rounded-full transition-all duration-500" style="width: ${wkPct}%"></div>
                  </div>
                </div>

                <!-- Claude & GPT -->
                <div>
                  <div class="flex items-center justify-between text-[11px] mb-1">
                    <span class="text-gray-400 font-medium">Claude 3.7 & GPT:</span>
                    <span class="font-mono font-bold ${cldPct <= 0 ? 'text-rose-400' : 'text-purple-400'}">${cldPct}% <span class="text-[9px] text-gray-500">(${cldCountdown})</span></span>
                  </div>
                  <div class="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div class="${cldPct <= 0 ? 'bg-rose-500' : 'bg-purple-400'} h-2 rounded-full transition-all duration-500" style="width: ${cldPct}%"></div>
                  </div>
                </div>
              </div>

              <!-- Call Stats -->
              <div class="flex items-center justify-between text-[11px] text-gray-400 pt-2 border-t border-gray-900">
                <span>Đã gọi: <strong class="text-white font-mono">${acc.calls_total}</strong></span>
                <span>Lỗi Quota: <strong class="${acc.quota_errors > 0 ? 'text-rose-400 font-bold' : 'text-gray-500'} font-mono">${acc.quota_errors}</strong></span>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    async function toggleRunner() {
      try {
        const statusRes = await fetch('/api/status');
        const data = await statusRes.json();
        if (data.daemon_active) {
          if (confirm('Bạn có chắc chắn muốn DỪNG cỗ máy sản xuất qua đêm?')) {
            await fetch('/api/runner/stop', { method: 'POST' });
          }
        } else {
          await fetch('/api/runner/start', { method: 'POST' });
        }
      } catch (err) {
        console.error('Lỗi toggle runner:', err);
      } finally {
        setTimeout(updateDashboard, 1000);
      }
    }

    async function triggerPurgeRam() {
      const icon = document.getElementById('iconPurgeRam');
      if (icon) icon.classList.add('fa-spin');
      try {
        const res = await fetch('/api/system/purge_ram', { method: 'POST' });
        const data = await res.json();
        if (data.ram) {
          document.getElementById('headerRamUsage').innerText = `${data.ram.used_gb}/${data.ram.total_gb} GB (${data.ram.percent}%)`;
        }
      } catch (err) {
        console.error('Lỗi purge RAM:', err);
      } finally {
        setTimeout(() => { if (icon) icon.classList.remove('fa-spin'); }, 800);
      }
    }

    async function triggerSyncQuota() {
      const icon = document.getElementById('tabSyncQuotaIcon');
      const btn = document.getElementById('tabSyncQuotaBtn');
      if (icon) icon.classList.add('fa-spin');
      if (btn) btn.disabled = true;
      try {
        await fetch('/api/accounts/sync', { method: 'POST' });
      } catch (e) {
      } finally {
        setTimeout(() => {
          if (icon) icon.classList.remove('fa-spin');
          if (btn) btn.disabled = false;
          updateDashboard();
        }, 4000);
      }
    }

    async function openFolderLocal() {
      try {
        await fetch('/api/system/open_folder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
      } catch (e) {}
    }

    async function openWorkFolder(branch, slug) {
      try {
        await fetch('/api/system/open_folder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ branch, slug })
        });
      } catch (e) {}
    }

    function renderLogBox(elementId, logs) {
      const box = document.getElementById(elementId);
      if (!logs || !logs.length) {
        box.innerHTML = '<div class="text-gray-500 italic">Đang chờ tác vụ tiếp theo...</div>';
        return;
      }
      box.innerHTML = logs.map(l => {
        let colorClass = 'text-gray-300';
        if (l.includes('SUCCESS') || l.includes('HOÀN TẤT') || l.includes('Hoàn tất')) colorClass = 'text-emerald-400 font-semibold';
        else if (l.includes('FAILED') || l.includes('Lỗi') || l.includes('CRITICAL')) colorClass = 'text-red-400';
        else if (l.includes('Đang xử lý') || l.includes('BẮT ĐẦU') || l.includes('Tiến độ')) colorClass = 'text-cyan-300';
        return `<div class="${colorClass} leading-tight">${escapeHtml(l)}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }

    async function fetchFullLogs() {
      try {
        const res = await fetch('/api/logs?tail=80');
        const data = await res.json();
        const box = document.getElementById('fullTerminalBody');
        const autoScroll = document.getElementById('chkAutoScroll').checked;
        if (data.lines) {
          box.innerHTML = data.lines.map(l => {
            let color = 'text-gray-400';
            if (l.includes('SUCCESS') || l.includes('HOÀN TẤT')) color = 'text-emerald-400 font-bold';
            else if (l.includes('Lỗi') || l.includes('ERROR') || l.includes('CRITICAL')) color = 'text-rose-400';
            else if (l.includes('Chu kỳ')) color = 'text-amber-300 font-bold';
            return `<div class="${color}">${escapeHtml(l)}</div>`;
          }).join('');
          if (autoScroll) box.scrollTop = box.scrollHeight;
        }
      } catch (err) {}
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Auto-refresh interval (2.5s status, 4s logs)
    updateDashboard();
    fetchFullLogs();
    setInterval(updateDashboard, 2500);
    setInterval(fetchFullLogs, 4000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Web Dashboard Server for Router V4")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8505, help="Port to bind")
    parser.add_argument("--ui", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dashboard", action="store_true", help=argparse.SUPPRESS)
    args, _ = parser.parse_known_args()

    print(f"[*] Khởi động Real-Time Web Control Center tại http://localhost:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

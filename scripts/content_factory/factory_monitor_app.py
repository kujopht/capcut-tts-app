"""Native Desktop Monitor App for Router V4 Content Factory.

Ultra-responsive, screen-fitted Qt desktop application (PySide6):
- Perfectly fitted for 1280x800 & 1080p displays without overflowing screen boundaries.
- Butter-smooth 60 FPS GUI: All disk I/O, process polling, and log parsing offloaded to background QThread.
- Real-time automatic background synchronization of Google Antigravity 8-account quota limits.
- 2 Unified View Modes (1-Click Switch):
    1. 🖥️ Giám Sát Trực Tiếp: 3 nhánh song song + 8 tài khoản (Live status, formatted rich log stream).
    2. 📚 Kho Thành Phẩm: Thư viện 45+ tác phẩm hoàn chỉnh với nút Nghe Thử 🎧 & Mở Thư Mục 📂 1-click.
- Real-time status badges with vibrant, clear color coding (Green: Success, Cyan: TTS, Orange: Scraping, Purple: AI, Red: Error).
- Large, prominent current job cards showing active work, chapter, and download progress.
- 1-click instant RAM cleanup (EmptyWorkingSet) and instant Google quota sync.
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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess


DEBUG_LOG = PROJECT_ROOT / "raw_spool" / "gui_debug.log"
DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
if sys.stdout is None:
    sys.stdout = open(DEBUG_LOG, "a", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(DEBUG_LOG, "a", encoding="utf-8", errors="replace")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.content_factory.pipeline_ui_components import (
    ContentPipelineWidget,
    AccountPoolWidget,
    PublishedCatalogWidget,
    DiffResultDialog,
    QAReportDialog,
    ImportWorkDialog,
)
from scripts.content_factory.discovery_ui import DiscoveryWidget

USAGE_FILE = PROJECT_ROOT / "raw_spool" / "agy_accounts_usage.json"
SERVER_LIMITS_FILE = PROJECT_ROOT / "raw_spool" / "agy_server_limits.json"
LOG_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.log"
SPOOL_DIR = PROJECT_ROOT / "raw_spool"
RUNNER_PID_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.pid"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def is_pid_running(pid: int) -> bool:
    """Checks if a process ID is currently alive via Win32 API without creating any windows."""
    if not pid or pid <= 0:
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
    """Returns active runner PID from PID file, or None if not running."""
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



def get_running_process_counts(targets: Dict[str, str]) -> Dict[str, int]:
    """Inspects running processes in memory via Toolhelp32Snapshot with zero subprocesses."""
    from ctypes import wintypes
    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260)
        ]

    procs: Dict[str, int] = {}
    hSnapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not hSnapshot or hSnapshot == -1:
        return procs
    pe32 = PROCESSENTRY32()
    pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        if ctypes.windll.kernel32.Process32First(hSnapshot, ctypes.byref(pe32)):
            while True:
                name = pe32.szExeFile.decode('utf-8', errors='ignore').lower()
                if name in targets:
                    k = targets[name]
                    procs[k] = procs.get(k, 0) + 1
                if not ctypes.windll.kernel32.Process32Next(hSnapshot, ctypes.byref(pe32)):
                    break
    finally:
        ctypes.windll.kernel32.CloseHandle(hSnapshot)
    return procs


def free_system_memory() -> int:
    """Invokes EmptyWorkingSet on background bloated processes to reclaim RAM without any subprocess."""
    from ctypes import wintypes
    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260)
        ]

    target_prefixes = ("python", "agy", "rclone", "ffmpeg", "yt-dlp", "piper", "node")
    psapi = ctypes.windll.psapi
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_SET_QUOTA = 0x0100
    freed_count = 0

    hSnapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not hSnapshot or hSnapshot == -1:
        return 0
    pe32 = PROCESSENTRY32()
    pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        if ctypes.windll.kernel32.Process32First(hSnapshot, ctypes.byref(pe32)):
            while True:
                name = pe32.szExeFile.decode('utf-8', errors='ignore').lower()
                if any(name.startswith(p) for p in target_prefixes):
                    pid = pe32.th32ProcessID
                    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
                    if h:
                        psapi.EmptyWorkingSet(h)
                        ctypes.windll.kernel32.CloseHandle(h)
                        freed_count += 1
                if not ctypes.windll.kernel32.Process32Next(hSnapshot, ctypes.byref(pe32)):
                    break
    finally:
        ctypes.windll.kernel32.CloseHandle(hSnapshot)
    return freed_count



def format_reset_time_badge(iso_str: str) -> str:
    """Converts UTC ISO timestamp (e.g. 2026-09-13T05:39:03Z) to local clock + countdown."""
    if not iso_str:
        return ""
    try:
        clean_iso = iso_str.replace("Z", "+00:00")
        dt_utc = datetime.datetime.fromisoformat(clean_iso)
        dt_local = dt_utc.astimezone()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        diff_secs = int((dt_utc - now_utc).total_seconds())
        if diff_secs <= 0:
            return "Đã reset"
        hours, rem = divmod(diff_secs, 3600)
        minutes, _ = divmod(rem, 60)
        local_hm = dt_local.strftime("%H:%M")
        if hours >= 24:
            days = hours // 24
            return f"{dt_local.strftime('%d/%m')} ~{days}d"
        elif hours > 0:
            return f"{local_hm} ~{hours}h{minutes:02d}m"
        else:
            return f"{local_hm} ~{minutes}m"
    except Exception:
        return ""


def format_log_line_to_html(raw_line: str) -> str:
    """Converts a raw log line into a modern, beautifully styled HTML card with status colors."""
    line = raw_line.strip()
    if not line:
        return ""

    ts_match = re.match(r"^\[(\d{4}-\d{2}-\d{2}\s+)?(\d{2}:\d{2}:\d{2})\]\s*(.*)$", line)
    if ts_match:
        ts = ts_match.group(2)
        content = ts_match.group(3)
    else:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        content = line

    content_lower = content.lower()

    if any(k in content_lower for k in ("success", "hoàn tất", "hoàn thành", "thành công", "drive", "đã tạo", "đạt chuẩn")):
        color = "#34d399"
        border = "#10b981"
        bg = "rgba(16, 185, 129, 0.12)"
        icon = "✅"
    elif any(k in content_lower for k in ("tts", "ngọc huyền", "piper", "tiến độ tts", "giọng đọc", "câu")):
        color = "#38bdf8"
        border = "#06b6d4"
        bg = "rgba(6, 182, 212, 0.12)"
        icon = "🎙️"
    elif any(k in content_lower for k in ("cạo", "download", "tải", "tìm kiếm", "frag", "yt-dlp", "đào", "convert", "ffmpeg")):
        color = "#fb923c"
        border = "#f97316"
        bg = "rgba(249, 115, 22, 0.12)"
        icon = "⛏️"
    elif any(k in content_lower for k in ("gemini", "sáng tác", "kịch bản", "flash", "biên tập", "subsvid", "lồng tiếng", "anime", "phim ai")):
        color = "#c084fc"
        border = "#a855f7"
        bg = "rgba(168, 85, 247, 0.12)"
        icon = "🤖"
    elif any(k in content_lower for k in ("lỗi", "failed", "error", "429", "cảnh báo", "bỏ qua")):
        color = "#f87171"
        border = "#ef4444"
        bg = "rgba(239, 68, 68, 0.15)"
        icon = "⚠️"
    else:
        color = "#e2e8f0"
        border = "#475569"
        bg = "rgba(30, 41, 59, 0.15)"
        icon = "🔹"

    content_escaped = (
        content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return (
        f'<div style="background:{bg}; border-left: 3px solid {border}; '
        f'padding: 3px 6px; margin: 2px 0; border-radius: 3px; '
        f'font-family: Segoe UI, Consolas, sans-serif; font-size: 10.5px; line-height: 1.35;">'
        f'<span style="color: #64748b; font-size: 9px; font-weight: bold; margin-right: 4px;">[{ts}]</span> '
        f'<span style="margin-right: 3px;">{icon}</span> '
        f'<span style="color: {color}; font-weight: 500;">{content_escaped}</span></div>'
    )


def scan_all_completed_works() -> List[Dict[str, Any]]:
    """Scans all local spool directories for finished works with rich metadata."""
    items = []
    branches = [
        ("youtube_audio", "AUDIOBOOK", "#f87171", "🔴"),
        ("fanfic_tts", "FANFIC TTS", "#38bdf8", "🔵"),
        ("ai_animation", "HOẠT HÌNH AI", "#c084fc", "🟣"),
    ]

    for subdir, b_label, b_color, b_icon in branches:
        p = SPOOL_DIR / subdir
        if not p.exists():
            continue
        try:
            for d in p.iterdir():
                if not d.is_dir() or d.name.startswith("temp_"):
                    continue
                files = [f.name for f in d.iterdir() if f.is_file()]
                has_mp3 = any(f.endswith(".mp3") for f in files)
                has_wav = any(f.endswith(".wav") for f in files)
                has_mp4 = any(f.endswith(".mp4") for f in files)
                has_cover = (d / "cover.jpg").exists()

                title = d.name
                mf = d / "metadata.json"
                st = d / "source.txt"
                duration = 0
                score = None
                meta: Dict[str, Any] = {}
                if mf.exists():
                    try:
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                        title = meta.get("title_vi") or title
                        duration = meta.get("duration_seconds", 0)
                        score = meta.get("quality_score") or meta.get("score")
                    except Exception:
                        pass

                # Extract Fandom
                fandom = meta.get("fandom") or ""
                if not fandom and "[" in d.name and "]" in d.name:
                    m_f = re.search(r"\[(.*?)\]", d.name)
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
                    v_name = meta.get("voice_name") or "Ngọc Huyền (NghiTTS)"
                    s_cnt = meta.get("sentence_count", 0)
                    episodes_detail = f"📖 Chương {ch_idx:02d} · Giọng đọc: {v_name} ({s_cnt} câu)"

                    if not description_short and (d / "story_vi.txt").exists():
                        try:
                            description_short = (d / "story_vi.txt").read_text(encoding="utf-8", errors="replace")[:220].strip()
                        except Exception:
                            pass

                elif subdir == "ai_animation":
                    episodes_detail = "🎬 Tập 01 · Đa giọng CapCut (Thanh Niên + Ngọt Ngào) · Vietsub ASS"
                    if not description_short and (d / "script_vi.txt").exists():
                        try:
                            description_short = (d / "script_vi.txt").read_text(encoding="utf-8", errors="replace")[:220].strip()
                        except Exception:
                            pass

                if not description_short:
                    description_short = "Tác phẩm fanfic chất lượng cao đã thu thập, biên dịch kịch bản và hoàn thiện giọng đọc sẵn sàng xuất bản."

                audio_file = ""
                if (d / "audio.mp3").exists():
                    audio_file = str(d / "audio.mp3")
                elif (d / "media.mp3").exists():
                    audio_file = str(d / "media.mp3")
                elif (d / "raw_video.mp4").exists():
                    audio_file = str(d / "raw_video.mp4")

                text_file = ""
                if (d / "story_vi.txt").exists():
                    text_file = str(d / "story_vi.txt")
                elif (d / "transcript.srt").exists():
                    text_file = str(d / "transcript.srt")
                elif (d / "source.txt").exists():
                    text_file = str(d / "source.txt")

                mtime = d.stat().st_mtime
                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M %d/%m")

                items.append({
                    "folder_name": d.name,
                    "folder_path": str(d),
                    "title": title,
                    "fandom": fandom,
                    "episodes_detail": episodes_detail,
                    "description_short": description_short,
                    "branch": subdir,
                    "branch_label": b_label,
                    "branch_color": b_color,
                    "branch_icon": b_icon,
                    "mtime": mtime,
                    "time_str": time_str,
                    "has_media": has_mp3 or has_wav or has_mp4,
                    "audio_file": audio_file,
                    "text_file": text_file,
                    "has_cover": has_cover,
                    "duration": duration,
                    "score": score,
                })
        except Exception:
            pass

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def scan_pipeline_works() -> List[Dict[str, Any]]:
    """Discovers active works in release packages and known seed catalog."""
    works = []
    pkg_dir = PROJECT_ROOT / "raw_spool" / "release_packages"
    if pkg_dir.exists():
        for sub in pkg_dir.iterdir():
            if sub.is_dir() and (sub / "manifest.json").exists():
                try:
                    m = json.loads((sub / "manifest.json").read_text(encoding="utf-8"))
                    works.append({
                        "work_id": m.get("work_id", sub.name),
                        "title": m.get("title", sub.name),
                        "provenance": m.get("provenance", {}).get("provenance_type", "IMPORTED_FANFIC"),
                        "platform": m.get("provenance", {}).get("source_platform", "royalroad"),
                        "translated_chapters": len(m.get("chapters", [])),
                        "total_chapters": m.get("total_chapters", len(m.get("chapters", []))),
                        "stage": m.get("status", "READY").upper(),
                        "audio_status": "Có Audio" if any(c.get("audio_path") for c in m.get("chapters", [])) else "TTS_PENDING",
                    })
                except Exception:
                    pass

    seed_defaults = [
        {
            "work_id": "156690",
            "title": "[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu",
            "provenance": "IMPORTED_FANFIC",
            "platform": "royalroad",
            "translated_chapters": 12,
            "total_chapters": 12,
            "stage": "PUBLISHED",
            "audio_status": "Hoàn thành (Piper)",
        },
        {
            "work_id": "seed_op_rocks",
            "title": "[One Piece] Kỷ Nguyên Rocks: Ta, Phó Thuyền Trưởng, Nhất Đao Trảm Tứ Hoàng",
            "provenance": "IMPORTED_FANFIC",
            "platform": "fanfic_seed",
            "translated_chapters": 28,
            "total_chapters": 28,
            "stage": "PUBLISHED",
            "audio_status": "Hoàn thành (CapCut)",
        },
        {
            "work_id": "seed_naruto_thanmoc",
            "title": "[Naruto] Mộc Diệp: Thần Mộc Tái Sinh, Từ Đệ Tử Jiraiya Bắt Đầu Chấn Hưng Làng Lá",
            "provenance": "IMPORTED_FANFIC",
            "platform": "fanfic_seed",
            "translated_chapters": 18,
            "total_chapters": 18,
            "stage": "PUBLISHED",
            "audio_status": "Hoàn thành (CapCut)",
        },
        {
            "work_id": "seed_conan_anhdao",
            "title": "[Detective Conan] Dưới Tàng Hoa Anh Đào Năm Ấy: Lời Nguyện Cầu Và Bản Án Màu Đen",
            "provenance": "IMPORTED_FANFIC",
            "platform": "fanfic_seed",
            "translated_chapters": 16,
            "total_chapters": 16,
            "stage": "PUBLISHED",
            "audio_status": "Hoàn thành (CapCut)",
        },
        {
            "work_id": "seed_genshin_hoakhoi",
            "title": "[Genshin Impact] Hoa Khôi Lớp Bên Và Bản Tình Ca Tháng Chín",
            "provenance": "IMPORTED_FANFIC",
            "platform": "fanfic_seed",
            "translated_chapters": 15,
            "total_chapters": 15,
            "stage": "PUBLISHED",
            "audio_status": "Hoàn thành (CapCut)",
        },
    ]
    present_ids = {w["work_id"] for w in works}
    for s in seed_defaults:
        if s["work_id"] not in present_ids:
            works.append(s)

    return works


class SyncServerQuotaWorker(QThread):
    """Background thread to poll all 8 Antigravity accounts for live quota limits safely."""
    finished_signal = Signal(bool, str, dict)

    def run(self):
        try:
            sys.path.insert(0, r"C:\Users\nguye\agy-profiles")
            from agy_profile import get_active_profile_name, switch_profile, profile_switch_lock

            active_before = get_active_profile_name() or "acc1"
            res = {}
            if SERVER_LIMITS_FILE.exists():
                try:
                    res = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass

            from scripts.content_factory.gemini_evaluator import get_all_available_accounts
            for acc in get_all_available_accounts(include_ineligible=True):
                try:
                    with profile_switch_lock(timeout_ms=15000):
                        switch_profile(acc, with_lock=False)
                        env = os.environ.copy()
                        env["USERPROFILE"] = rf"C:\Users\nguye\.agy-sessions\{acc}"
                        env["HOME"] = rf"C:\Users\nguye\.agy-sessions\{acc}"
                        out = subprocess.check_output(
                            ["agy", "-p", "/usage", "--output-format", "json"],
                            stdin=subprocess.DEVNULL,
                            env=env,
                            text=True,
                            encoding="utf-8",
                            timeout=12,
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

                    acc_info["updated_at"] = datetime.datetime.now().strftime("%H:%M:%S")
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
            self.finished_signal.emit(True, f"Đã đồng bộ Google + Claude Quota lúc {datetime.datetime.now().strftime('%H:%M:%S')}", res)
        except Exception as exc:
            self.finished_signal.emit(False, str(exc), {})


class DataPollWorker(QThread):
    """Background polling worker that offloads ALL disk I/O, subprocesses, and parsing from GUI thread."""
    data_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        targets = {
            "yt-dlp.exe": "yt-dlp",
            "ffmpeg.exe": "ffmpeg",
            "piper.exe": "piper",
            "agy.exe": "agy",
            "rclone.exe": "rclone",
        }

        scan_counter = 0

        while self.running:
            data: Dict[str, Any] = {}

            # 1. RAM Status via Win32 API
            try:
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_uint64),
                        ("ullAvailPhys", ctypes.c_uint64),
                        ("ullTotalPageFile", ctypes.c_uint64),
                        ("ullAvailPageFile", ctypes.c_uint64),
                        ("ullTotalVirtual", ctypes.c_uint64),
                        ("ullAvailVirtual", ctypes.c_uint64),
                        ("ullAvailExtendedVirtual", ctypes.c_uint64),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                tot_gb = stat.ullTotalPhys / (1024**3)
                avail_gb = stat.ullAvailPhys / (1024**3)
                used_gb = tot_gb - avail_gb
                load_pct = stat.dwMemoryLoad
                data["ram"] = {"used_gb": used_gb, "tot_gb": tot_gb, "load_pct": load_pct}
            except Exception:
                data["ram"] = {"used_gb": 0, "tot_gb": 16, "load_pct": 50}

            # 2. Fast In-Memory Process Inspection via Toolhelp32Snapshot (Zero Subprocesses!)
            procs = get_running_process_counts(targets)
            data["procs"] = procs


            # 3. Read Account Usage & Limits from disk
            raw_usage = {"accounts": {}, "current_active": "acc1", "active_accounts": []}
            if USAGE_FILE.exists():
                try:
                    raw_usage = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            data["raw_usage"] = raw_usage

            server_limits = {}
            if SERVER_LIMITS_FILE.exists():
                try:
                    server_limits = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            data["server_limits"] = server_limits

            # 4. Spool Directory Inspection for 3 branches
            def get_spool_info(subdir: str) -> Optional[Dict[str, Any]]:
                d = SPOOL_DIR / subdir
                if not d.exists():
                    return None
                try:
                    subs = [p for p in d.iterdir() if p.is_dir() and not p.name.startswith("temp_")]
                    if not subs:
                        return None
                    subs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    latest = subs[0]
                    files = [f.name for f in latest.iterdir() if f.is_file()]
                    mtime = datetime.datetime.fromtimestamp(latest.stat().st_mtime).strftime("%H:%M:%S")
                    return {
                        "folder_name": latest.name,
                        "mtime": mtime,
                        "has_part": any(".part" in f or ".ytdl" in f for f in files),
                        "has_mp3": any(f.endswith(".mp3") for f in files),
                        "has_wav": any(f.endswith(".wav") for f in files),
                        "has_mp4": any(f.endswith(".mp4") for f in files),
                    }
                except Exception:
                    return None

            spool_b1 = get_spool_info("youtube_audio")
            spool_b2 = get_spool_info("fanfic_tts")
            spool_b3 = get_spool_info("ai_animation")

            # 5. Inspect Task Daemon Log for granular live progress
            task_tail_text = ""
            try:
                task_log_cand = Path(r"C:\Users\nguye\.gemini\antigravity-cli\brain\8d51be49-31f3-40e1-a6c0-5e10a3855a43\.system_generated\tasks\task-5850.log")
                if task_log_cand.exists() and task_log_cand.stat().st_size > 0:
                    with open(task_log_cand, "rb") as tf:
                        tf.seek(max(0, task_log_cand.stat().st_size - 40000))
                        task_tail_text = tf.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            dl_progress_str = ""
            if task_tail_text:
                dls = re.findall(r"\[download\]\s+([\d\.]+%\s+of\s+~?\s+[\d\.]+[A-Za-z]+(?:\s+at\s+[\d\.]+[A-Za-z/]+)?(?:\s+ETA\s+[\d:]+)?)", task_tail_text)
                if dls:
                    dl_progress_str = dls[-1]

            tts_progress_str = ""
            if task_tail_text:
                tts_matches = re.findall(r"\[Worker2\]\s+(Tiến độ TTS:\s+[\d/]+\s+câu.*)", task_tail_text)
                if tts_matches:
                    tts_progress_str = tts_matches[-1]

            # 6. Read & Parse Overnight Log
            lines: List[str] = []
            if LOG_FILE.exists():
                try:
                    raw_text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
                    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
                except Exception:
                    lines = []

            b1_l, b2_l, b3_l = [], [], []
            for l in lines:
                l_lower = l.lower()
                if any(k in l_lower for k in ("[nhánh 1", "[nha?nh 1", "[worker1]", "youtube", "audiobook", "mp3 192k")):
                    b1_l.append(l)
                elif any(k in l_lower for k in ("[nhánh 2", "[nha?nh 2", "[worker2]", "fanfic", "novel", "tiểu thuyết", "tts", "piper")):
                    b2_l.append(l)
                elif any(k in l_lower for k in ("[nhánh 3", "[nha?nh 3", "[worker3]", "animation", "hoạt hình", "subvid", "phim ai", "dub")):
                    b3_l.append(l)

            def clean_line(txt: str) -> str:
                return re.sub(r"^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s*", "", txt)

            # --- BRANCH 1 ---
            target_b1 = "Audio Naruto Fanfic - Đóng Vai Zhongli (Tập 01)"
            for l in reversed(b1_l):
                if "Tìm kiếm & xử lý bộ audio:" in l or "bộ truyện audio:" in l:
                    m = re.search(r"'(.*?)'", l)
                    if m:
                        target_b1 = m.group(1)
                        break

            if spool_b1 and spool_b1.get("folder_name"):
                target_b1 = spool_b1["folder_name"]

            b1_syncing = any("đồng bộ" in l and "Drive" in l for l in b1_l[-4:]) and not any("hoàn tất" in l.lower() or "failed" in l.lower() for l in b1_l[-2:])
            if procs.get("ffmpeg", 0) > 0:
                badge_b1 = "⚙️ ĐANG CONVERT MP3"
                badge_bg1 = "#78350f"
                badge_fg1 = "#fef08a"
                action_b1 = "⚙️ ĐANG CHUYỂN MÃ AUDIO (FFMPEG):"
                detail_b1 = "Trích xuất tệp MP3 192k hoàn chỉnh (2 luồng nhẹ)"
            elif procs.get("yt-dlp", 0) > 0:
                badge_b1 = "⛏️ ĐANG CẠO AUDIO"
                badge_bg1 = "#431407"
                badge_fg1 = "#fed7aa"
                action_b1 = "⛏️ ĐANG CẠO & TẢI AUDIO TRỌN BỘ CHO:"
                detail_b1 = f"Tiến độ: {dl_progress_str or 'Đang tải các phân đoạn âm thanh'}"
            elif b1_syncing and procs.get("rclone", 0) > 0:
                badge_b1 = "☁️ ĐANG SYNC DRIVE"
                badge_bg1 = "#064e3b"
                badge_fg1 = "#a7f3d0"
                action_b1 = "☁️ ĐANG ĐỒNG BỘ GOOGLE DRIVE CHO:"
                detail_b1 = "Đang đẩy toàn bộ gói audiobook lên thư mục FanficWorld"
            elif b1_l and "SUCCESS" in b1_l[-1]:
                badge_b1 = "✅ HOÀN THÀNH AUDIO"
                badge_bg1 = "#064e3b"
                badge_fg1 = "#a7f3d0"
                action_b1 = "✅ ĐÃ HOÀN TẤT BỘ AUDIO:"
                detail_b1 = clean_line(b1_l[-1])
            else:
                badge_b1 = "⛏️ ĐANG CẠO AUDIO"
                badge_bg1 = "#1e293b"
                badge_fg1 = "#94a3b8"
                action_b1 = "⛏️ ĐANG XỬ LÝ AUDIO CÀY VIEW:"
                detail_b1 = f"Tác phẩm gần nhất: {target_b1[:45]}"

            b1_html_list = [format_log_line_to_html(l) for l in b1_l[-30:] if l]
            if dl_progress_str:
                now_s = datetime.datetime.now().strftime("%H:%M:%S")
                b1_html_list.append(format_log_line_to_html(f"[{now_s}] ⛏️ [YT-DLP] Tiến độ tải: {dl_progress_str}"))

            data["b1"] = {
                "badge": badge_b1, "badge_bg": badge_bg1, "badge_fg": badge_fg1,
                "action": action_b1, "target": target_b1, "detail": detail_b1,
                "html": "".join(b1_html_list),
            }

            # --- BRANCH 2 ---
            target_b2 = "Tiểu thuyết đồng nhân trường thiên"
            for l in reversed(b2_l):
                if "Sáng tác & sản xuất tiểu thuyết:" in l or "bộ tiểu thuyết:" in l:
                    m = re.search(r"'(.*?)'", l)
                    if m:
                        target_b2 = m.group(1)
                        break

            if spool_b2 and spool_b2.get("folder_name"):
                target_b2 = spool_b2["folder_name"]

            b2_syncing = any("đồng bộ" in l and "Drive" in l for l in b2_l[-4:]) and not any("hoàn tất" in l.lower() or "failed" in l.lower() for l in b2_l[-2:])
            if procs.get("piper", 0) > 0:
                badge_b2 = "🎙️ ĐANG CHẠY TTS"
                badge_bg2 = "#0c4a6e"
                badge_fg2 = "#bae6fd"
                action_b2 = "🎙️ ĐANG CHẠY TTS NGỌC HUYỀN CHO:"
                detail_b2 = f"{tts_progress_str or 'Giọng đọc truyền cảm Ngọc Huyền (NghiTTS) đang sinh audio'}"
            elif procs.get("agy", 0) > 0:
                badge_b2 = "🤖 GEMINI SÁNG TÁC"
                badge_bg2 = "#3b0764"
                badge_fg2 = "#f5d0fe"
                action_b2 = "🤖 GEMINI 3.8 FLASH ĐANG SÁNG TÁC CHO:"
                detail_b2 = "Đang viết các chương fanfic mới và kiểm định kịch bản"
            elif b2_syncing and procs.get("rclone", 0) > 0:
                badge_b2 = "☁️ ĐANG SYNC DRIVE"
                badge_bg2 = "#064e3b"
                badge_fg2 = "#a7f3d0"
                action_b2 = "☁️ ĐANG ĐỒNG BỘ GOOGLE DRIVE CHO:"
                detail_b2 = "Đang đẩy toàn bộ chương hoàn chỉnh lên Cloud"
            elif b2_l and "SUCCESS" in b2_l[-1]:
                badge_b2 = "✅ HOÀN THÀNH TIỂU THUYẾT"
                badge_bg2 = "#064e3b"
                badge_fg2 = "#a7f3d0"
                action_b2 = "✅ ĐÃ HOÀN TẤT CHU KỲ TIỂU THUYẾT:"
                detail_b2 = clean_line(b2_l[-1])
            else:
                badge_b2 = "🎙️ ĐANG XỬ LÝ TTS"
                badge_bg2 = "#1e293b"
                badge_fg2 = "#94a3b8"
                action_b2 = "🎙️ ĐANG XỬ LÝ TIỂU THUYẾT & TTS:"
                detail_b2 = f"Tác phẩm gần nhất: {target_b2[:45]}"

            b2_html_list = [format_log_line_to_html(l) for l in b2_l[-30:] if l]
            if tts_progress_str:
                now_s = datetime.datetime.now().strftime("%H:%M:%S")
                b2_html_list.append(format_log_line_to_html(f"[{now_s}] 🎙️ [PIPER TTS] {tts_progress_str}"))

            data["b2"] = {
                "badge": badge_b2, "badge_bg": badge_bg2, "badge_fg": badge_fg2,
                "action": action_b2, "target": target_b2, "detail": detail_b2,
                "html": "".join(b2_html_list),
            }

            # --- BRANCH 3 ---
            target_b3 = "Phim hoạt hình AI học đường / Romcom"
            for l in reversed(b3_l):
                if "Tìm kiếm & xử lý phim AI:" in l or "hoạt hình AI:" in l:
                    m = re.search(r"'(.*?)'", l)
                    if m:
                        target_b3 = m.group(1)
                        break

            if spool_b3 and spool_b3.get("folder_name"):
                target_b3 = spool_b3["folder_name"]

            b3_syncing = any("đồng bộ" in l and "Drive" in l for l in b3_l[-4:]) and not any("hoàn tất" in l.lower() or "failed" in l.lower() for l in b3_l[-2:])
            if procs.get("ffmpeg", 0) > 0 and procs.get("yt-dlp", 0) == 0:
                badge_b3 = "🎞️ SUBSVID & LỒNG TIẾNG"
                badge_bg3 = "#312e81"
                badge_fg3 = "#c7d2fe"
                action_b3 = "🎞️ ĐANG BỌC PHỤ ĐỀ & LỒNG TIẾNG CHO:"
                detail_b3 = "Ghép audio tiếng Việt & nhúng phụ đề video MP4"
            elif procs.get("yt-dlp", 0) > 0 or (spool_b3 and spool_b3.get("has_part")):
                badge_b3 = "🎬 ĐANG CẠO PHIM AI"
                badge_bg3 = "#4a044e"
                badge_fg3 = "#f5d0fe"
                action_b3 = "🎬 ĐANG CẠO & TẢI PHIM HOẠT HÌNH AI CHO:"
                detail_b3 = f"Tải tập anime: {target_b3[:42]}... (~1.97 GB)"
            elif b3_syncing and procs.get("rclone", 0) > 0:
                badge_b3 = "☁️ ĐANG SYNC DRIVE"
                badge_bg3 = "#064e3b"
                badge_fg3 = "#a7f3d0"
                action_b3 = "☁️ ĐANG ĐỒNG BỘ GOOGLE DRIVE CHO:"
                detail_b3 = "Đang đẩy tập phim hoàn tất kèm sub lên Drive"
            elif b3_l and "SUCCESS" in b3_l[-1]:
                badge_b3 = "✅ HOÀN THÀNH TẬP PHIM"
                badge_bg3 = "#064e3b"
                badge_fg3 = "#a7f3d0"
                action_b3 = "✅ ĐÃ HOÀN TẤT TẬP PHIM AI:"
                detail_b3 = clean_line(b3_l[-1])
            else:
                badge_b3 = "🎬 ĐANG XỬ LÝ PHIM AI"
                badge_bg3 = "#1e293b"
                badge_fg3 = "#94a3b8"
                action_b3 = "🎬 ĐANG XỬ LÝ PHIM HOẠT HÌNH AI:"
                detail_b3 = f"Tác phẩm gần nhất: {target_b3[:45]}"

            b3_html_list = [format_log_line_to_html(l) for l in b3_l[-30:] if l]

            data["b3"] = {
                "badge": badge_b3, "badge_bg": badge_bg3, "badge_fg": badge_fg3,
                "action": action_b3, "target": target_b3, "detail": detail_b3,
                "html": "".join(b3_html_list),
            }

            # 7. Scan Completed Works every ~6 seconds
            scan_counter += 1
            if scan_counter >= 4 or "completed_works" not in data:
                scan_counter = 0
                data["completed_works"] = scan_all_completed_works()

            # 8. Content Factory v2: Pipeline works & Published catalog
            try:
                data["pipeline_works"] = scan_pipeline_works()
            except Exception:
                data["pipeline_works"] = []

            try:
                from scripts.content_factory.production_diff_engine import ProductionDiffEngine
                data["published_catalog"] = ProductionDiffEngine().get_published_catalog()
            except Exception:
                data["published_catalog"] = []

            data["pipeline_logs"] = lines

            # Daemon activity & Process check
            runner_pid = get_active_runner_pid()
            data["runner_pid"] = runner_pid
            data["daemon_active"] = runner_pid is not None
            data["updated_at"] = datetime.datetime.now().strftime("%H:%M:%S")

            # Emit clean pre-computed payload to GUI
            self.data_ready.emit(data)

            # Sleep 1.5s
            for _ in range(15):
                if not self.running:
                    return
                time.sleep(0.1)


class CompactAccountCard(QFrame):
    """Ultra-compact card for a single Antigravity CLI account fitting in 1 horizontal row."""

    def __init__(self, acc_name: str, parent=None):
        super().__init__(parent)
        self.acc_name = acc_name
        self.setObjectName("CompactAccountCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._init_ui()

    def _init_ui(self):
        self.setFixedHeight(94)
        self.setMinimumWidth(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Row 1: Name + Status Pill
        r1 = QHBoxLayout()
        self.lbl_name = QLabel(f"🛡️ {self.acc_name}")
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 11px; color: #f3f4f6;")
        self.lbl_badge = QLabel("READY")
        self.lbl_badge.setStyleSheet(
            "background-color: #1f2937; color: #9ca3af; padding: 1px 4px; border-radius: 2px; font-size: 8.5px; font-weight: bold;"
        )
        r1.addWidget(self.lbl_name)
        r1.addStretch()
        r1.addWidget(self.lbl_badge)
        layout.addLayout(r1)

        # Row 2: Gemini 5-Hour Limit + Reset Countdown
        r2 = QHBoxLayout()
        r2.setSpacing(2)
        lbl_5h = QLabel("♊ 5h:")
        lbl_5h.setStyleSheet("color: #9ca3af; font-size: 8px; font-weight: bold;")
        self.bar_5h = QProgressBar()
        self.bar_5h.setFixedHeight(4)
        self.bar_5h.setTextVisible(False)
        self.bar_5h.setRange(0, 100)
        self.bar_5h.setValue(100)
        self.lbl_5h_val = QLabel("100%")
        self.lbl_5h_val.setStyleSheet("color: #34d399; font-size: 8.5px; font-weight: bold;")
        self.lbl_5h_reset = QLabel("")
        self.lbl_5h_reset.setStyleSheet("color: #94a3b8; font-size: 8px;")
        r2.addWidget(lbl_5h)
        r2.addWidget(self.bar_5h, stretch=1)
        r2.addWidget(self.lbl_5h_val)
        r2.addWidget(self.lbl_5h_reset)
        layout.addLayout(r2)

        # Row 3: Gemini Weekly Limit + Reset Date
        r3 = QHBoxLayout()
        r3.setSpacing(2)
        lbl_wk = QLabel("♊ Wk:")
        lbl_wk.setStyleSheet("color: #9ca3af; font-size: 8px;")
        self.bar_wk = QProgressBar()
        self.bar_wk.setFixedHeight(4)
        self.bar_wk.setTextVisible(False)
        self.bar_wk.setRange(0, 100)
        self.bar_wk.setValue(100)
        self.lbl_wk_val = QLabel("100%")
        self.lbl_wk_val.setStyleSheet("color: #22d3ee; font-size: 8.5px; font-weight: bold;")
        self.lbl_wk_reset = QLabel("")
        self.lbl_wk_reset.setStyleSheet("color: #94a3b8; font-size: 8px;")
        r3.addWidget(lbl_wk)
        r3.addWidget(self.bar_wk, stretch=1)
        r3.addWidget(self.lbl_wk_val)
        r3.addWidget(self.lbl_wk_reset)
        layout.addLayout(r3)

        # Row 4: Claude & GPT Models Quota
        r4 = QHBoxLayout()
        r4.setSpacing(2)
        lbl_cld = QLabel("🟣 Cld:")
        lbl_cld.setStyleSheet("color: #c084fc; font-size: 8px; font-weight: bold;")
        self.bar_cld = QProgressBar()
        self.bar_cld.setFixedHeight(4)
        self.bar_cld.setTextVisible(False)
        self.bar_cld.setRange(0, 100)
        self.bar_cld.setValue(100)
        self.lbl_cld_val = QLabel("100%")
        self.lbl_cld_val.setStyleSheet("color: #c084fc; font-size: 8.5px; font-weight: bold;")
        self.lbl_cld_reset = QLabel("")
        self.lbl_cld_reset.setStyleSheet("color: #94a3b8; font-size: 8px;")
        r4.addWidget(lbl_cld)
        r4.addWidget(self.bar_cld, stretch=1)
        r4.addWidget(self.lbl_cld_val)
        r4.addWidget(self.lbl_cld_reset)
        layout.addLayout(r4)

        # Row 5: Stats
        self.lbl_stats = QLabel("Gọi: 0 · 0s")
        self.lbl_stats.setStyleSheet("color: #6b7280; font-size: 8px;")
        layout.addWidget(self.lbl_stats)

    def update_card(self, info: Dict[str, Any], server_limit: Dict[str, Any], is_busy: bool):
        calls = info.get("calls_total", 0)
        status = info.get("status", "READY")
        latency = info.get("last_latency_s", 0)
        errors = info.get("quota_errors", 0)

        # 1. Gemini limits
        h5_pct = float(server_limit.get("five_hour_remaining", 100.0))
        wk_pct = float(server_limit.get("weekly_remaining", 100.0))
        h5_reset = server_limit.get("five_hour_reset", "")
        wk_reset = server_limit.get("weekly_reset", "")
        h5_reset_str = format_reset_time_badge(h5_reset)
        wk_reset_str = format_reset_time_badge(wk_reset)

        # Color coding for 5h bar
        if h5_pct <= 25:
            color_5h = "#ef4444"
        elif h5_pct <= 50:
            color_5h = "#f59e0b"
        else:
            color_5h = "#34d399"

        self.bar_5h.setValue(int(h5_pct))
        self.bar_5h.setStyleSheet(f"""
            QProgressBar {{ background-color: #1f2937; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background-color: {color_5h}; border-radius: 2px; }}
        """)
        self.lbl_5h_val.setText(f"{h5_pct:.0f}%")
        self.lbl_5h_val.setStyleSheet(f"color: {color_5h}; font-size: 8.5px; font-weight: bold;")
        if h5_reset_str:
            self.lbl_5h_reset.setText(f"· {h5_reset_str}")
            self.lbl_5h_reset.setStyleSheet("color: #fca5a5; font-size: 8px; font-weight: bold;" if h5_pct <= 35 else "color: #94a3b8; font-size: 8px;")
        else:
            self.lbl_5h_reset.setText("")

        # Gemini Weekly bar
        self.bar_wk.setValue(int(wk_pct))
        self.lbl_wk_val.setText(f"{wk_pct:.0f}%")
        if wk_reset_str:
            self.lbl_wk_reset.setText(f"· {wk_reset_str}")
        else:
            self.lbl_wk_reset.setText("")

        # 2. Claude & GPT limits
        cld_wk_pct = float(server_limit.get("claude_weekly_remaining", 100.0))
        cld_wk_reset = server_limit.get("claude_weekly_reset", "")
        cld_reset_str = format_reset_time_badge(cld_wk_reset)

        if cld_wk_pct <= 0:
            color_cld = "#ef4444"
            self.bar_cld.setValue(0)
            self.lbl_cld_val.setText("0%")
        elif cld_wk_pct <= 25:
            color_cld = "#f59e0b"
            self.bar_cld.setValue(int(cld_wk_pct))
            self.lbl_cld_val.setText(f"{cld_wk_pct:.0f}%")
        else:
            color_cld = "#c084fc"
            self.bar_cld.setValue(int(cld_wk_pct))
            self.lbl_cld_val.setText(f"{cld_wk_pct:.0f}%")

        self.bar_cld.setStyleSheet(f"""
            QProgressBar {{ background-color: #1f2937; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background-color: {color_cld}; border-radius: 2px; }}
        """)
        self.lbl_cld_val.setStyleSheet(f"color: {color_cld}; font-size: 8.5px; font-weight: bold;")
        if cld_reset_str:
            self.lbl_cld_reset.setText(f"· {cld_reset_str}")
            self.lbl_cld_reset.setStyleSheet("color: #fca5a5; font-size: 8px; font-weight: bold;" if cld_wk_pct <= 10 else "color: #94a3b8; font-size: 8px;")
        else:
            self.lbl_cld_reset.setText("")

        self.lbl_stats.setText(f"Gọi: {calls} · Lỗi: {errors} · {latency}s")

        self.setToolTip(
            f"<b>{self.acc_name}</b><br/>"
            f"• Gemini 5h: <b>{h5_pct:.1f}%</b> ({h5_reset_str or 'Đầy'})<br/>"
            f"• Gemini Weekly: <b>{wk_pct:.1f}%</b> ({wk_reset_str or 'Đầy'})<br/>"
            f"• Claude/GPT: <b>{cld_wk_pct:.1f}%</b> ({cld_reset_str or 'Đầy'})<br/>"
            f"• Thống kê: Gọi {calls} | Lỗi {errors} | Latency {latency}s"
        )

        if is_busy:
            self.setStyleSheet("""
                QFrame#CompactAccountCard {
                    background-color: #2b1b04;
                    border: 1.5px solid #f59e0b;
                    border-radius: 5px;
                }
            """)
            self.lbl_badge.setText("⚡ WORK")
            self.lbl_badge.setStyleSheet("background-color: #78350f; color: #fef08a; padding: 1px 4px; border-radius: 2px; font-weight: bold;")
        elif calls > 0 and status == "ACTIVE":
            self.setStyleSheet("""
                QFrame#CompactAccountCard {
                    background-color: #042f2e;
                    border: 1px solid #06b6d4;
                    border-radius: 5px;
                }
            """)
            self.lbl_badge.setText("✓ READY")
            self.lbl_badge.setStyleSheet("background-color: #083344; color: #67e8f9; padding: 1px 4px; border-radius: 2px; font-weight: bold;")
        elif errors > 0 or status == "RATE_LIMITED":
            self.setStyleSheet("""
                QFrame#CompactAccountCard {
                    background-color: #271010;
                    border: 1px solid #ef4444;
                    border-radius: 5px;
                }
            """)
            self.lbl_badge.setText("⚠️ 429")
            self.lbl_badge.setStyleSheet("background-color: #450a0a; color: #fca5a5; padding: 1px 4px; border-radius: 2px; font-weight: bold;")
        else:
            self.setStyleSheet("""
                QFrame#CompactAccountCard {
                    background-color: #111827;
                    border: 1px solid #374151;
                    border-radius: 5px;
                }
            """)
            self.lbl_badge.setText("IDLE")
            self.lbl_badge.setStyleSheet("background-color: #1f2937; color: #9ca3af; padding: 1px 4px; border-radius: 2px;")


class BranchPanelWidget(QFrame):
    """Side-by-side visible panel with prominent job card and rich colorful log stream."""

    def __init__(self, branch_id: int, title: str, subtitle: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.branch_id = branch_id
        self.title_str = title
        self.subtitle_str = subtitle
        self.accent_color = accent_color
        self.last_log_hash = ""
        self.setObjectName(f"BranchPanel_{branch_id}")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"""
            QFrame#BranchPanel_{self.branch_id} {{
                background-color: #0b0f19;
                border: 1px solid {self.accent_color}55;
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Header: Title + Status Badge
        header = QHBoxLayout()
        header_v = QVBoxLayout()
        header_v.setSpacing(1)
        
        self.lbl_title = QLabel(self.title_str)
        self.lbl_title.setStyleSheet(f"font-size: 11.5px; font-weight: bold; color: {self.accent_color};")
        self.lbl_sub = QLabel(self.subtitle_str)
        self.lbl_sub.setStyleSheet("font-size: 9px; color: #9ca3af;")
        header_v.addWidget(self.lbl_title)
        header_v.addWidget(self.lbl_sub)
        header.addLayout(header_v)
        header.addStretch()

        self.lbl_badge = QLabel("KHỞI TẠO...")
        self.lbl_badge.setStyleSheet(
            "background-color: #1f2937; color: #9ca3af; padding: 3px 6px; border-radius: 3px; font-size: 9px; font-weight: bold;"
        )
        header.addWidget(self.lbl_badge)
        layout.addLayout(header)

        # Prominent Current Job Box (Large & Clear)
        self.job_box = QFrame()
        self.job_box.setStyleSheet(f"""
            QFrame {{
                background-color: #111827;
                border-left: 3px solid {self.accent_color};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        jb_layout = QVBoxLayout(self.job_box)
        jb_layout.setContentsMargins(6, 4, 6, 4)
        jb_layout.setSpacing(2)

        # Line 1: Action Title
        self.lbl_action = QLabel("ĐANG XỬ LÝ...")
        self.lbl_action.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {self.accent_color}; letter-spacing: 0.3px;")
        
        # Line 2: Target Work Title
        self.lbl_target = QLabel("Chưa có nhiệm vụ")
        self.lbl_target.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #fef08a;")
        self.lbl_target.setWordWrap(True)
        
        # Line 3: Detail Progress
        self.lbl_detail = QLabel("Chuẩn bị chu kỳ")
        self.lbl_detail.setStyleSheet("font-size: 9.5px; color: #38bdf8;")
        self.lbl_detail.setWordWrap(True)

        jb_layout.addWidget(self.lbl_action)
        jb_layout.addWidget(self.lbl_target)
        jb_layout.addWidget(self.lbl_detail)
        layout.addWidget(self.job_box)

        # Live Console Output (Rich Colorful HTML)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("""
            QTextEdit {
                background-color: #030712;
                border: 1px solid #1f2937;
                border-radius: 4px;
                padding: 3px;
            }
        """)
        layout.addWidget(self.log_edit, stretch=1)

    def update_branch(
        self,
        badge_text: str,
        badge_color_bg: str,
        badge_color_text: str,
        action_text: str,
        target_text: str,
        detail_text: str,
        html_content: str,
    ):
        self.lbl_badge.setText(badge_text)
        self.lbl_badge.setStyleSheet(
            f"background-color: {badge_color_bg}; color: {badge_color_text}; padding: 3px 6px; border-radius: 3px; font-size: 9px; font-weight: bold; border: 1px solid {self.accent_color};"
        )
        self.lbl_action.setText(action_text)
        self.lbl_target.setText(target_text)
        self.lbl_detail.setText(f"📊 {detail_text}")

        # Smooth update: only replace HTML when content actually changes
        curr_hash = hashlib.md5(html_content.encode("utf-8", errors="ignore")).hexdigest()
        if curr_hash != self.last_log_hash:
            self.last_log_hash = curr_hash
            self.log_edit.setHtml(html_content)
            self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())


class CompletedWorkCard(QFrame):
    """Detailed card for a completed product: Title, Fandom, Episodes detail, Short synopsis, and 1-click actions."""

    def __init__(self, item: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("CompletedWorkCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._init_ui()

    def _init_ui(self):
        b_color = self.item.get('branch_color', '#38bdf8')
        self.setStyleSheet(f"""
            QFrame#CompletedWorkCard {{
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }}
            QFrame#CompletedWorkCard:hover {{
                border: 1px solid {b_color};
                background-color: #0f172a;
            }}
        """)
        self.setMinimumHeight(155)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # 1. Header: Branch Pill + Fandom Tag + Time Badge
        header = QHBoxLayout()
        header.setSpacing(6)

        lbl_pill = QLabel(f"{self.item.get('branch_icon', '📦')} {self.item.get('branch_label', 'THÀNH PHẨM')}")
        lbl_pill.setStyleSheet(
            f"background-color: {b_color}22; color: {b_color}; "
            f"padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: bold; border: 1px solid {b_color}55;"
        )
        header.addWidget(lbl_pill)

        fandom = self.item.get("fandom", "")
        if fandom:
            lbl_fandom = QLabel(f"🏷️ {fandom[:25]}")
            lbl_fandom.setStyleSheet("background-color: #1e293b; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 500;")
            header.addWidget(lbl_fandom)

        header.addStretch()

        score = self.item.get("score")
        if score:
            lbl_score = QLabel(f"⭐ {score}/10")
            lbl_score.setStyleSheet("color: #facc15; font-size: 9.5px; font-weight: bold; background: #713f12; padding: 1px 5px; border-radius: 3px;")
            header.addWidget(lbl_score)

        lbl_time = QLabel(self.item.get("time_str", "--:--"))
        lbl_time.setStyleSheet("color: #64748b; font-size: 9px;")
        header.addWidget(lbl_time)
        layout.addLayout(header)

        # 2. Title
        lbl_title = QLabel(self.item.get("title", "Tác phẩm"))
        lbl_title.setStyleSheet("font-weight: bold; font-size: 11.5px; color: #ffffff; line-height: 1.3;")
        lbl_title.setWordWrap(True)
        lbl_title.setMaximumHeight(40)
        layout.addWidget(lbl_title)

        # 3. Episodes Detail Badge (Chi tiết các tập)
        ep_detail = self.item.get("episodes_detail", "")
        if ep_detail:
            lbl_ep = QLabel(ep_detail)
            lbl_ep.setStyleSheet("""
                background-color: #032b43; color: #7dd3fc;
                border: 1px solid #0284c7; border-radius: 4px;
                padding: 3px 8px; font-size: 10px; font-weight: bold;
            """)
            lbl_ep.setWordWrap(True)
            layout.addWidget(lbl_ep)

        # 4. Short Synopsis / Description (Mô tả ngắn)
        desc = self.item.get("description_short", "")
        if desc:
            lbl_desc = QLabel(f"“ {desc[:175]}... ”" if len(desc) > 175 else f"“ {desc} ”")
            lbl_desc.setStyleSheet("""
                color: #94a3b8; font-size: 9.5px; line-height: 1.35;
                font-style: italic; background-color: rgba(15, 23, 42, 0.6);
                padding: 4px 6px; border-left: 2px solid #06b6d4; border-radius: 3px;
            """)
            lbl_desc.setWordWrap(True)
            layout.addWidget(lbl_desc)

        # 5. Action Buttons Footer
        footer = QHBoxLayout()
        footer.setSpacing(6)

        dur_s = self.item.get("duration", 0)
        if dur_s >= 3600:
            dur_str = f"⏱️ {dur_s/3600:.1f}h"
        elif dur_s > 0:
            dur_str = f"⏱️ {int(dur_s//60)}p"
        else:
            dur_str = "📦 Hoàn tất"
        lbl_info = QLabel(dur_str)
        lbl_info.setStyleSheet("color: #38bdf8; font-size: 9.5px; font-weight: bold;")
        footer.addWidget(lbl_info)
        footer.addStretch()

        audio_path = self.item.get("audio_file", "")
        if audio_path:
            btn_play = QPushButton("🎧 Nghe Thử")
            btn_play.setStyleSheet("""
                QPushButton { background-color: #0284c7; color: #ffffff; border: none; border-radius: 4px; padding: 3px 9px; font-size: 9.5px; font-weight: bold; }
                QPushButton:hover { background-color: #0369a1; }
            """)
            btn_play.clicked.connect(lambda: self._open_target(audio_path))
            footer.addWidget(btn_play)

        text_path = self.item.get("text_file", "")
        if text_path:
            btn_read = QPushButton("📜 Đọc / Sub")
            btn_read.setStyleSheet("""
                QPushButton { background-color: #4c1d95; color: #e9d5ff; border: 1px solid #6b21a8; border-radius: 4px; padding: 3px 8px; font-size: 9.5px; font-weight: bold; }
                QPushButton:hover { background-color: #581c87; color: #ffffff; }
            """)
            btn_read.clicked.connect(lambda: self._open_target(text_path))
            footer.addWidget(btn_read)

        folder_path = self.item.get("folder_path", "")
        btn_folder = QPushButton("📂 Thư Mục")
        btn_folder.setStyleSheet("""
            QPushButton { background-color: #1f2937; color: #e2e8f0; border: 1px solid #374151; border-radius: 4px; padding: 3px 8px; font-size: 9.5px; font-weight: bold; }
            QPushButton:hover { background-color: #374151; color: #ffffff; }
        """)
        btn_folder.clicked.connect(lambda: self._open_target(folder_path))
        footer.addWidget(btn_folder)

        layout.addLayout(footer)

    def _open_target(self, path_str: str):
        if not path_str:
            return
        try:
            os.startfile(path_str)
        except Exception:
            pass


class CompletedGalleryWidget(QWidget):
    """Rich, searchable, scrollable library gallery for all finished works."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_items: List[Dict[str, Any]] = []
        self.current_filter: str = "ALL"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Top Controls: Search + Filter Chips
        top_ctrl = QHBoxLayout()
        top_ctrl.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tìm kiếm theo tên truyện, nhân vật, tác phẩm...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a; color: #f8fafc; border: 1px solid #334155;
                border-radius: 4px; padding: 5px 10px; font-size: 11px;
            }
            QLineEdit:focus { border-color: #06b6d4; }
        """)
        self.search_input.textChanged.connect(self.render_items)
        top_ctrl.addWidget(self.search_input, stretch=2)

        # Filter Chips
        self.btn_all = QPushButton("Tất Cả (0)")
        self.btn_b1 = QPushButton("🔴 Audiobook (0)")
        self.btn_b2 = QPushButton("🔵 Fanfic TTS (0)")
        self.btn_b3 = QPushButton("🟣 Phim AI (0)")

        self.chip_group = QButtonGroup(self)
        for b in (self.btn_all, self.btn_b1, self.btn_b2, self.btn_b3):
            b.setCheckable(True)
            self.chip_group.addButton(b)

        self.btn_all.setChecked(True)
        self.btn_all.clicked.connect(lambda: self._set_filter("ALL"))
        self.btn_b1.clicked.connect(lambda: self._set_filter("youtube_audio"))
        self.btn_b2.clicked.connect(lambda: self._set_filter("fanfic_tts"))
        self.btn_b3.clicked.connect(lambda: self._set_filter("ai_animation"))

        self._style_chips()

        top_ctrl.addWidget(self.btn_all)
        top_ctrl.addWidget(self.btn_b1)
        top_ctrl.addWidget(self.btn_b2)
        top_ctrl.addWidget(self.btn_b3)
        layout.addLayout(top_ctrl)

        # Scroll Area for Cards Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { border: 1px solid #1e293b; border-radius: 6px; background-color: #030712; }
            QScrollBar:vertical { background: #0b0f19; width: 6px; }
            QScrollBar::handle:vertical { background: #334155; border-radius: 3px; }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #030712;")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setSpacing(6)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, stretch=1)

    def _style_chips(self):
        chip_css = """
            QPushButton {
                background-color: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #334155; color: #ffffff; }
            QPushButton:checked { background-color: #0891b2; color: #ffffff; border-color: #06b6d4; }
        """
        for b in (self.btn_all, self.btn_b1, self.btn_b2, self.btn_b3):
            b.setStyleSheet(chip_css)

    def _set_filter(self, f_type: str):
        self.current_filter = f_type
        self.render_items()

    def update_completed_items(self, items: List[Dict[str, Any]]):
        self.all_items = items
        c_all = len(items)
        c_b1 = sum(1 for it in items if it.get("branch") == "youtube_audio")
        c_b2 = sum(1 for it in items if it.get("branch") == "fanfic_tts")
        c_b3 = sum(1 for it in items if it.get("branch") == "ai_animation")

        self.btn_all.setText(f"Tất Cả ({c_all})")
        self.btn_b1.setText(f"🔴 Audiobook ({c_b1})")
        self.btn_b2.setText(f"🔵 Fanfic TTS ({c_b2})")
        self.btn_b3.setText(f"🟣 Phim AI ({c_b3})")
        self.render_items()

    def render_items(self):
        # Clear existing layout
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()

        q = self.search_input.text().strip().lower()
        filtered = []
        for it in self.all_items:
            if self.current_filter != "ALL" and it.get("branch") != self.current_filter:
                continue
            if q and q not in it.get("title", "").lower() and q not in it.get("folder_name", "").lower():
                continue
            filtered.append(it)

        if not filtered:
            lbl_empty = QLabel("Không tìm thấy tác phẩm phù hợp.")
            lbl_empty.setStyleSheet("color: #64748b; font-size: 12px; padding: 30px;")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(lbl_empty, 0, 0, 1, 3)
            return

        cols = 3
        for i, item in enumerate(filtered):
            card = CompletedWorkCard(item)
            row = i // cols
            col = i % cols
            self.grid.addWidget(card, row, col)

        self.grid.setRowStretch(len(filtered) // cols + 1, 1)


class FactoryMonitorMainWindow(QMainWindow):
    """Main application window with 2 unified views (Live Monitor & Completed Gallery)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fanfic Factory Master Control - Desktop Monitor")
        icon_path = Path(__file__).resolve().parent / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.sync_thread: Optional[SyncServerQuotaWorker] = None
        self._fit_screen_geometry()
        self._init_ui()

        # 1. Background Polling Thread (Offloads all I/O from GUI thread)
        self.poll_worker = DataPollWorker(self)
        self.poll_worker.data_ready.connect(self.on_data_ready)
        self.poll_worker.start()

        # 2. Real-time Background Quota Sync Timer (Every 10 mins)
        self.quota_timer = QTimer(self)
        self.quota_timer.timeout.connect(self.auto_sync_quota_tick)
        self.quota_timer.start(600000)

        # Trigger initial sync in background after 3 seconds
        QTimer.singleShot(3000, self.action_sync_quota)

    def _fit_screen_geometry(self):
        """Calculates proper window dimensions so it never overflows the active screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        target_w = min(1260, screen.width() - 16)
        target_h = min(760, screen.height() - 36)
        pos_x = max(0, screen.x() + (screen.width() - target_w) // 2)
        pos_y = max(0, screen.y() + (screen.height() - target_h) // 2)
        self.setGeometry(pos_x, pos_y, target_w, target_h)
        self.setMinimumSize(940, 560)

    def _init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #030712; color: #f3f4f6; }
            QWidget { font-family: 'Segoe UI', Arial, sans-serif; }
            QPushButton {
                background-color: #1f2937; color: #e5e7eb; border: 1px solid #374151;
                border-radius: 4px; padding: 4px 10px; font-weight: bold; font-size: 10px;
            }
            QPushButton:hover { background-color: #374151; color: #ffffff; border-color: #4b5563; }
            QPushButton#btnSync { background-color: #0e7490; border-color: #06b6d4; color: #ffffff; }
            QPushButton#btnSync:hover { background-color: #0891b2; }
            QPushButton#btnFreeMem { background-color: #065f46; border-color: #10b981; color: #ffffff; }
            QPushButton#btnFreeMem:hover { background-color: #047857; }
            QSplitter::handle { background-color: #1e293b; width: 3px; }
            QSplitter::handle:hover { background-color: #06b6d4; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # 1. Top Header Bar (With View Switcher!)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        title_lbl = QLabel("🚀 CONTENT FACTORY MASTER")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 900; color: #ffffff; letter-spacing: 0.5px;")
        top_bar.addWidget(title_lbl)

        # View Mode Switcher: 5 Core Tabs (Discovery -> Pipeline -> Catalog -> Accounts -> Archive)
        self.btn_view_discovery = QPushButton("🔍 KHÁM PHÁ (DISCOVERY)")
        self.btn_view_pipeline = QPushButton("📑 PIPELINE NỘI DUNG")
        self.btn_view_catalog = QPushButton("🌐 DANH MỤC / UPDATE CENTER")
        self.btn_view_accounts = QPushButton("👥 TÀI KHOẢN POOL (14 ACC)")
        self.btn_view_gallery = QPushButton("📚 KHO LƯU TRỮ (0)")
        self.view_btn_group = QButtonGroup(self)
        self.view_buttons = [
            self.btn_view_discovery,
            self.btn_view_pipeline,
            self.btn_view_catalog,
            self.btn_view_accounts,
            self.btn_view_gallery,
        ]
        for idx, btn in enumerate(self.view_buttons):
            btn.setCheckable(True)
            self.view_btn_group.addButton(btn)
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_view(i))

        self.btn_view_discovery.setChecked(True)
        self._update_view_switch_styles()

        top_bar.addWidget(self.btn_view_discovery)
        top_bar.addWidget(self.btn_view_pipeline)
        top_bar.addWidget(self.btn_view_catalog)
        top_bar.addWidget(self.btn_view_accounts)
        top_bar.addWidget(self.btn_view_gallery)

        # Runner Start / Pause Controller
        self.btn_toggle_runner = QPushButton("▶ BẮT ĐẦU CẠO")
        self.btn_toggle_runner.setObjectName("btnToggleRunner")
        self.btn_toggle_runner.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_runner.clicked.connect(self.action_toggle_runner)
        top_bar.addWidget(self.btn_toggle_runner)

        self.lbl_runner_status = QLabel("💤 Tool đang dừng")
        self.lbl_runner_status.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 10px; padding: 3px 7px; background: #1e293b; border-radius: 3px;")
        top_bar.addWidget(self.lbl_runner_status)

        top_bar.addStretch()

        self.lbl_ram_status = QLabel("RAM: -- GB (0%)")
        self.lbl_ram_status.setStyleSheet("color: #a7f3d0; font-weight: bold; font-size: 10px; padding: 2px 6px; background: #064e3b; border-radius: 3px;")
        top_bar.addWidget(self.lbl_ram_status)

        self.btn_free_mem = QPushButton("🧹 Dọn RAM")
        self.btn_free_mem.setObjectName("btnFreeMem")
        self.btn_free_mem.clicked.connect(self.action_free_memory)
        top_bar.addWidget(self.btn_free_mem)

        self.btn_sync = QPushButton("🔄 Đồng Bộ Quota")
        self.btn_sync.setObjectName("btnSync")
        self.btn_sync.clicked.connect(self.action_sync_quota)
        top_bar.addWidget(self.btn_sync)

        main_layout.addLayout(top_bar)

        # 2. Main Stacked Widget (Tab 0: Discovery, Tab 1: Pipeline, Tab 2: Catalog, Tab 3: Accounts, Tab 4: Archive)
        self.stack = QStackedWidget()

        # --- TAB 0: DISCOVERY MODE (READ-ONLY CANDIDATE DISCOVERY) ---
        self.page_discovery = DiscoveryWidget(self)
        self.stack.addWidget(self.page_discovery)

        # --- TAB 1: CONTENT PIPELINE ---
        self.page_pipeline = ContentPipelineWidget(self)
        self.page_pipeline.action_requested.connect(self._handle_pipeline_action)
        self.stack.addWidget(self.page_pipeline)

        # --- TAB 2: PUBLISHED CATALOG / UPDATE CENTER (LIVING NOVEL PRODUCTION) ---
        self.page_catalog = PublishedCatalogWidget(self)
        self.page_catalog.refresh_requested.connect(self._refresh_catalog)
        self.stack.addWidget(self.page_catalog)

        # --- TAB 3: ACCOUNT POOL (DYNAMIC ALL CONFIGURED ACCOUNTS) ---
        self.page_accounts = AccountPoolWidget(self)
        self.page_accounts.sync_requested.connect(self.action_sync_quota)
        self.page_accounts.ram_cleanup_requested.connect(self.action_free_memory)
        self.stack.addWidget(self.page_accounts)

        # --- TAB 4: COMPLETED GALLERY (HISTORICAL ARCHIVE) ---
        self.gallery_page = CompletedGalleryWidget(self)
        self.stack.addWidget(self.gallery_page)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. Footer Bar
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_footer = QLabel("Cập nhật thời gian thực qua background worker. 60 FPS mượt mà.")
        self.lbl_footer.setStyleSheet("color: #6b7280; font-size: 9px;")
        footer_layout.addWidget(self.lbl_footer)
        footer_layout.addStretch()

        self.lbl_active_procs = QLabel("Tiến trình: Đang kiểm tra...")
        self.lbl_active_procs.setStyleSheet("color: #a7f3d0; font-size: 9px; margin-right: 10px;")
        footer_layout.addWidget(self.lbl_active_procs)

        lbl_app_info = QLabel("Desktop App Native | ~45 MB RAM")
        lbl_app_info.setStyleSheet("color: #10b981; font-size: 9px; font-weight: bold;")
        footer_layout.addWidget(lbl_app_info)
        main_layout.addLayout(footer_layout)

        self.current_runner_pid: Optional[int] = None
        self._update_runner_ui(get_active_runner_pid())

    def _update_runner_ui(self, pid: Optional[int]):
        self.current_runner_pid = pid
        if pid:
            self.btn_toggle_runner.setText("⏸ TẠM DỪNG TOOL")
            self.btn_toggle_runner.setStyleSheet("""
                QPushButton#btnToggleRunner {
                    background-color: #b91c1c; color: #ffffff; border: 1px solid #ef4444;
                    border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: bold;
                }
                QPushButton#btnToggleRunner:hover { background-color: #991b1b; }
            """)
            self.lbl_runner_status.setText(f"🟢 Đang Cạo (PID {pid})")
            self.lbl_runner_status.setStyleSheet("color: #34d399; font-weight: bold; font-size: 10px; padding: 3px 7px; background: #064e3b; border-radius: 3px;")
        else:
            self.btn_toggle_runner.setText("▶ BẮT ĐẦU CẠO")
            self.btn_toggle_runner.setStyleSheet("""
                QPushButton#btnToggleRunner {
                    background-color: #059669; color: #ffffff; border: 1px solid #10b981;
                    border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: bold;
                }
                QPushButton#btnToggleRunner:hover { background-color: #047857; }
            """)
            self.lbl_runner_status.setText("💤 Tool đang dừng")
            self.lbl_runner_status.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 10px; padding: 3px 7px; background: #1e293b; border-radius: 3px;")

    def action_toggle_runner(self):
        pid = get_active_runner_pid()
        if pid:
            self.action_stop_runner(pid)
        else:
            self.action_start_runner()

    def action_start_runner(self):
        pythonw = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)

        runner_script = PROJECT_ROOT / "scripts" / "content_factory" / "overnight_runner.py"
        try:
            proc = subprocess.Popen(
                [str(pythonw), str(runner_script)],
                cwd=str(PROJECT_ROOT),
                creationflags=NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            RUNNER_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            RUNNER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
            self._update_runner_ui(proc.pid)
        except Exception as exc:
            pass

    def action_stop_runner(self, pid: Optional[int] = None):
        if pid is None:
            pid = get_active_runner_pid()
        if pid:
            try:
                subprocess.run(["taskkill", "/pid", str(pid), "/t", "/f"], creationflags=NO_WINDOW, capture_output=True)
            except Exception:
                pass
        try:
            RUNNER_PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        self._update_runner_ui(None)


    def _update_view_switch_styles(self):
        style = """
            QPushButton {
                background-color: #111827; color: #94a3b8; border: 1px solid #374151;
                border-radius: 4px; padding: 4px 12px; font-size: 10.5px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1f2937; color: #ffffff; border-color: #4b5563; }
            QPushButton:checked {
                background-color: #0284c7; color: #ffffff; border: 1px solid #38bdf8;
            }
        """
        for btn in self.view_buttons:
            btn.setStyleSheet(style)

    def _switch_view(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.view_buttons):
            btn.setChecked(i == index)
        self._update_view_switch_styles()

    def _handle_pipeline_action(self, action: str, target: str):
        if action == "publish":
            QMessageBox.information(
                self,
                "Bảo Vệ Xuất Bản (Publish Gate)",
                f"Đã kích hoạt cổng xuất bản cho '{target}'.\n\n"
                "Trong phiên bản này, các thao tác ghi production tuân thủ nghiêm ngặt cấm ghi khi chưa được ủy quyền.",
            )
        elif action == "crawl_url":
            self.lbl_footer.setText(f"Đang chuẩn bị thu hoạch: {target}")
        elif action == "resume":
            self.lbl_footer.setText(f"Đã kích hoạt tiếp tục xử lý cho '{target}'")
        elif action == "check_source":
            self.lbl_footer.setText(f"Đang kiểm tra cập nhật chương mới trên nguồn cho '{target}'...")

    def _refresh_catalog(self):
        try:
            from scripts.content_factory.production_diff_engine import ProductionDiffEngine
            cat = ProductionDiffEngine().get_published_catalog()
            self.page_catalog.update_catalog_data(cat)
            self.lbl_footer.setText(f"Đã làm mới danh mục production ({len(cat)} tác phẩm).")
        except Exception as exc:
            self.lbl_footer.setText(f"Lỗi làm mới danh mục: {exc}")

    def closeEvent(self, event):
        """Clean shutdown of background threads on close."""
        if hasattr(self, "poll_worker") and self.poll_worker.isRunning():
            self.poll_worker.stop()
            self.poll_worker.wait(1000)
        event.accept()

    def on_data_ready(self, data: Dict[str, Any]):
        """Fast UI update slot executing on GUI thread with pre-calculated data."""
        # 1. Update RAM
        ram = data.get("ram", {})
        used_gb = ram.get("used_gb", 0)
        tot_gb = ram.get("tot_gb", 16)
        load_pct = ram.get("load_pct", 50)
        self.lbl_ram_status.setText(f"RAM: {used_gb:.1f} / {tot_gb:.1f} GB ({load_pct}%)")
        if load_pct >= 85:
            self.lbl_ram_status.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 10px; padding: 2px 6px; background: #7f1d1d; border-radius: 3px;")
        else:
            self.lbl_ram_status.setStyleSheet("color: #a7f3d0; font-weight: bold; font-size: 10px; padding: 2px 6px; background: #064e3b; border-radius: 3px;")

        # 2. Update Active Processes
        procs = data.get("procs", {})
        proc_str = ", ".join([f"{k}: {v}" for k, v in procs.items()]) if procs else "Chờ"
        self.lbl_active_procs.setText(f"Tiến trình: {proc_str}")

        # 3. Update Tab 1: Content Pipeline
        if hasattr(self, "page_pipeline"):
            self.page_pipeline.update_pipeline_data(data.get("pipeline_works", []), data.get("pipeline_logs", []))

        # 4. Update Tab 2: Account Pool
        if hasattr(self, "page_accounts"):
            self.page_accounts.update_accounts_data(data.get("raw_usage", {}), data.get("server_limits", {}), data.get("procs", {}))

        # 5. Update Tab 3: Published Catalog
        if hasattr(self, "page_catalog"):
            self.page_catalog.update_catalog_data(data.get("published_catalog", []))

        # 6. Update Tab 4: Completed Gallery (Archive)
        if "completed_works" in data:
            c_works = data["completed_works"]
            self.btn_view_gallery.setText(f"📚 KHO LƯU TRỮ ({len(c_works)})")
            self.gallery_page.update_completed_items(c_works)

        # 6. Daemon Status & Runner UI Sync
        runner_pid = data.get("runner_pid")
        if runner_pid != self.current_runner_pid:
            self._update_runner_ui(runner_pid)


        self.lbl_footer.setText(f"Cập nhật: {data.get('updated_at', '--:--:--')} | 60 FPS mượt mà qua background worker")

    def auto_sync_quota_tick(self):
        if self.sync_thread and self.sync_thread.isRunning():
            return
        self.sync_thread = SyncServerQuotaWorker()
        self.sync_thread.finished_signal.connect(self._on_sync_done)
        self.sync_thread.start()

    def action_sync_quota(self):
        if self.sync_thread and self.sync_thread.isRunning():
            return
        self.btn_sync.setText("⏳ Đang đồng bộ...")
        self.btn_sync.setEnabled(False)
        self.sync_thread = SyncServerQuotaWorker()
        self.sync_thread.finished_signal.connect(self._on_sync_done)
        self.sync_thread.start()

    def _on_sync_done(self, success: bool, msg: str, quota_data: dict):
        self.btn_sync.setText("🔄 Đồng Bộ Quota")
        self.btn_sync.setEnabled(True)
        self.lbl_footer.setText(msg)

    def action_free_memory(self):
        freed = free_system_memory()
        self.lbl_footer.setText(f"Đã giải phóng bộ nhớ cho {freed} tiến trình ngầm!")


def excepthook(exc_type, exc_val, exc_tb):
    import traceback
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] UNCAUGHT EXCEPTION:\n")
            traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
            f.flush()
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_val, exc_tb)

sys.excepthook = excepthook


def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        window = FactoryMonitorMainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as exc:
        import traceback
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] CRASH IN MAIN:\n")
            traceback.print_exc(file=f)
            f.flush()
        raise


if __name__ == "__main__":
    main()


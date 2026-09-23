"""Overnight Content Factory Daemon (Treo máy tự động xuyên đêm).

Continuously harvests, evaluates with Gemini 3.8 Flash, synthesizes, and packages:
  - Branch 1: Trending Fanfic Audiobooks from YouTube -> MP3 + Transcript + Rich SEO Description -> Drive
  - Branch 2: Hot Fanfic Novels -> Dịch & TTS Ngọc Huyền (NghiTTS) -> Synchronized Transcript (.srt/.json) -> Drive
  - Branch 3: Viral AI Animation (School Romance / Novel Anime) -> Watermark & CN Sub Mask -> SubVid Captions + Multi-voice Dubbing -> Drive

Features:
  - Infinite auto-cycling across all 3 branches
  - Deduplication: Never re-downloads or re-produces works already in Drive
  - Resilient error-handling: Skips failed/low-score items without stopping
  - Real-time logging to `raw_spool/overnight_runner.log`
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce silent subprocesses on Windows to prevent any console windows
import scripts.content_factory.silent_subprocess

PID_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.pid"
LOG_FILE = PROJECT_ROOT / "raw_spool" / "overnight_runner.log"
STATE_FILE = PROJECT_ROOT / "raw_spool" / "runner_state.json"
FACTORY_CONFIG_FILE = PROJECT_ROOT / "raw_spool" / "factory_config.json"
_LOG_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()


def get_factory_config() -> Dict[str, bool]:
    """Loads active branch toggle state."""
    defaults = {
        "branch1_enabled": True,
        "branch2_enabled": True,
        "branch3_enabled": False,  # Paused per user request
    }
    if FACTORY_CONFIG_FILE.exists():
        try:
            cfg = json.loads(FACTORY_CONFIG_FILE.read_text(encoding="utf-8"))
            return {**defaults, **cfg}
        except Exception:
            pass
    return defaults



def get_runner_state() -> Dict[str, Any]:
    with _STATE_LOCK:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"b1_ch_idx": 0, "b1_y_idx": 0, "b2_topic_idx": 1, "b3_a_idx": 0, "b2_completed_topics": []}


def save_runner_state(state: Dict[str, Any]):
    with _STATE_LOCK:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def check_and_clean_disk_space(min_free_gb: float = 15.0):
    """Safeguards disk space: auto-cleans giant MP4s, stale .part files, temp dirs, and completed Drive works."""
    try:
        spool_dir = PROJECT_ROOT / "raw_spool"
        now = time.time()

        # 1. Always purge raw .mp4 videos in youtube_audio if audio.mp3 exists (saves tens of GBs)
        yt_dir = spool_dir / "youtube_audio"
        if yt_dir.exists():
            for mp4_file in yt_dir.glob("**/media.mp4"):
                try:
                    sibling_mp3 = mp4_file.parent / "audio.mp3"
                    if sibling_mp3.exists() or (now - mp4_file.stat().st_mtime) > 7200:
                        mp4_file.unlink(missing_ok=True)
                        log(f"[DISK GUARD] Đã xóa video MP4 trung gian để tiết kiệm ổ đĩa: {mp4_file.parent.name}/media.mp4")
                except Exception:
                    pass

        # 2. Delete stale .part downloads older than 1 hour
        for part_file in spool_dir.glob("**/*.part"):
            try:
                if (now - part_file.stat().st_mtime) > 3600:
                    part_file.unlink(missing_ok=True)
            except Exception:
                pass

        # 3. Clean temporary preview and old temp_dl dirs
        ai_dir = spool_dir / "ai_animation"
        if ai_dir.exists():
            for temp_d in ai_dir.glob("temp_dl_*"):
                try:
                    if temp_d.is_dir() and (now - temp_d.stat().st_mtime) > 3600:
                        shutil.rmtree(temp_d, ignore_errors=True)
                except Exception:
                    pass

        # 4. If free space is below threshold, purge old archives
        free_bytes = shutil.disk_usage(PROJECT_ROOT).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < min_free_gb:
            log(f"[DISK GUARD] ⚠️ Dung lượng trống thấp ({free_gb:.1f} GB < {min_free_gb} GB). Tự động dọn dẹp kho dữ liệu...")
            for arch_name in ("archive_youtube_audio_old", "archive_fanfic_tts_old"):
                arch_dir = spool_dir / arch_name
                if arch_dir.exists():
                    shutil.rmtree(arch_dir, ignore_errors=True)
                    log(f"[DISK GUARD] Đã dọn dẹp {arch_name} để giải phóng dung lượng.")
    except Exception as exc:
        log(f"[DISK GUARD] Lỗi kiểm tra dung lượng: {exc}")


class StreamToLog:
    """Redirects all print() statements from workers and tools live into overnight_runner.log."""
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._lock = threading.Lock()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.log_path, "a", encoding="utf-8", errors="replace")
        self.encoding = "utf-8"

    def fileno(self) -> int:
        try:
            return self._file.fileno()
        except Exception:
            return 1

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def write(self, buf: str):
        if not buf:
            return
        lines = [l.strip() for l in buf.splitlines() if l.strip()]
        if not lines:
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            try:
                for line_str in lines:
                    if not (line_str.startswith("[") and len(line_str) > 5 and line_str[1:5].isdigit()):
                        line_str = f"[{ts}] {line_str}"
                    self._file.write(line_str + "\n")
                self._file.flush()
            except Exception:
                pass

    def flush(self):
        try:
            self._file.flush()
        except Exception:
            pass


# sys.stdout redirection is moved to run_overnight_daemon() to avoid hijacking on import
from scripts.content_factory.router_v4_orchestrator import (
    get_drive_production_status,
    run_orchestrator,
)

# Set process priority to Below Normal so user's PC remains completely smooth
try:
    import ctypes
    BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
    ctypes.windll.kernel32.SetPriorityClass(
        ctypes.windll.kernel32.GetCurrentProcess(),
        BELOW_NORMAL_PRIORITY_CLASS
    )
except Exception:
    pass

# Priority YouTube Channels for Branch 1 (requested by user)
PRIORITY_CHANNELS = [
    "https://www.youtube.com/@camanmmo/videos",
    "https://www.youtube.com/@V%E1%BB%B1cTh%E1%BA%A9mAudio/videos",
    "https://www.youtube.com/@NgheTruyenDiGioi/videos",
]

# Fallback rotating search queries for Branch 1 (Fanfic Audiobooks >= 5h)
YOUTUBE_AUDIO_TOPICS = [
    "audiobook fanfic naruto full 10h",
    "truyện audio đồng nhân naruto trọn bộ",
    "audiobook fanfic one piece full 50h",
    "truyện audio đồng nhân trọn bộ 10 tiếng",
    "audiobook fanfic harry potter trọn bộ",
    "truyện audio đồng nhân võ hiệp tiên hiệp trọn bộ",
]

# Rotating novel topics for Branch 2:
# 1. Fanfic -> Giọng Cô Gái Hoạt Ngôn (BV074_streaming)
# 2. Tiểu thuyết học đường lãng mạn -> Giọng Nhỏ Ngọt Ngào (BV421_vivn_streaming)
# Sáng tác trường thiên nhiều chương để đạt thời lượng >= 5 tiếng (chapters=20)
FANFIC_NOVEL_TOPICS = [
    # --- ĐỒNG NHÂN / FANFIC (Giọng Cô Gái Hoạt Ngôn) ---
    "Đồng nhân Naruto: Xuyên không thành đệ tử Jiraiya, thức tỉnh Mộc Độn chấn hưng Làng Lá (Trường thiên trên 5 tiếng)",
    "Đồng nhân One Piece: Trọng sinh thành Phó Thuyền Trưởng Băng Rocks, đao trảm Tứ Hoàng (Trường thiên trên 5 tiếng)",
    "Đồng nhân Dragon Ball: Người Saiyan huyền thoại tái sinh ở Trái Đất (Trường thiên trên 5 tiếng)",
    "Đồng nhân Harry Potter: Huyết Thống Cổ Đại Thao Túng Hogwarts (Trường thiên trên 5 tiếng)",
    "Đồng nhân Bleach: Tử Thần Thức Tỉnh Trảm Hồn Đao Cổ Chấn Hưng Thi Hồn Giới (Trường thiên trên 5 tiếng)",
    "Đồng nhân Genshin Impact: Nhà Lữ Hành Thức Tỉnh Nguyên Tố Thứ 8 Chấn Động Teyvat (Trường thiên trên 5 tiếng)",

    # --- TIỂU THUYẾT HỌC ĐƯỜNG LÃNG MẠN (Giọng Nhỏ Ngọt Ngào) ---
    "Tiểu thuyết học đường lãng mạn: Mối tình đầu năm 17 tuổi cùng cô bạn bàn bên dịu dàng (Trường thiên trên 5 tiếng)",
    "Thanh xuân vườn trường: Nhật ký rung động cùng hoa khôi lớp bên (Trường thiên trên 5 tiếng)",
    "Học đường ngọt sủng: Trúc mã nhà bên bỗng nhiên tỏ tình (Trường thiên trên 5 tiếng)",
    "Đô thị thanh xuân: Chờ em dưới cơn mưa mùa hạ năm ấy (Trường thiên trên 5 tiếng)",
    "Thanh xuân học đường: Lời hứa dưới tàng cây hoa anh đào thời trung học (Trường thiên trên 5 tiếng)",
]

# Priority YouTube Channels for Branch 3 (2D Chibi Novel Animation Học Đường & Ngọt Sủng)
PRIORITY_ANIMATION_CHANNELS = [
    "https://www.youtube.com/channel/UC1u7krNNC12dj34dNU_w06g/videos",  # Anh Hoa Sa Điêu Động Họa (Hẹn Hò Qua Mạng, Hoa Khôi Cao Lãnh)
    "https://www.youtube.com/channel/UCMagyyxb65aJwReFrBQRbgg/videos",  # Thủy Tinh Mạn Cải (Hoa Khôi Học Đường, Vợ Tôi Là Hoa Khôi)
    "https://www.youtube.com/channel/UCm3EOudss-V3et-xuRYQa1g/videos",  # Thất Thất Mạn Xá (Học Đường Đô Thị, Ngọt Sủng)
    "https://www.youtube.com/channel/UChDSBAqo54AIeuQNFrPfPVw/videos",  # Tân Sinh Hoa Khôi / Đô Thị Động Họa
]

# Rotating viral animation search queries for Branch 3 (Sa Điêu Hoạt Hình: Tu Tiên, Luyện Cổ, Hệ Thống, Hoa Khôi Học Đường)
AI_ANIMATION_TOPICS = [
    # --- SA ĐIÊU HỆ THỐNG / TU TIÊN / LUYỆN CỔ (Hot trend dạng Video 1) ---
    "沙雕动画 炼蛊 进度条 道尊",
    "沙雕动画 修仙 搞笑 逆袭",
    "沙雕动画 规则怪谈",
    "沙雕动画 系统 逆袭 搞笑",
    "沙雕动画 刚上大学 我的老婆居然是校花",
    "沙雕动画 第一次和网恋对象见面 高冷校花",
    "沙雕动画 校园 恋爱 甜宠",
    "沙雕动画 当恋爱萌新被高冷校花疯狂倒追",
    "沙雕动画 恋爱日常 女追男 甜到爆",
    "动态漫 校园恋爱 甜宠 一口气全看完",
    "樱花沙雕动画 恋爱 日常",
    "水星漫改 校园 恋爱 甜宠",
    "柒柒漫舍 校园 恋爱 甜宠",
    "都市沙雕动画 校园 恋爱 完结",
]


def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    with _LOG_LOCK:
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
                f.write(formatted + "\n")
                f.flush()
        except Exception:
            pass


_DRIVE_SLUGS_CACHE: Set[str] = set()
_DRIVE_SLUGS_TIME: float = 0.0


def get_existing_drive_slugs() -> Set[str]:
    """Retrieves all slugs already uploaded to Drive across all branches with 5-minute caching."""
    global _DRIVE_SLUGS_CACHE, _DRIVE_SLUGS_TIME
    now = time.time()
    if _DRIVE_SLUGS_CACHE and (now - _DRIVE_SLUGS_TIME) < 300:
        return _DRIVE_SLUGS_CACHE
    try:
        status = get_drive_production_status()
        slugs = set()
        for branch_info in status.values():
            for item in branch_info.get("items", []):
                slugs.add(item.lower().strip())
        _DRIVE_SLUGS_CACHE = slugs
        _DRIVE_SLUGS_TIME = now
        return slugs
    except Exception as exc:
        log(f"[WARN] Không thể lấy danh sách Drive: {exc}")
        return _DRIVE_SLUGS_CACHE


def _get_channel_unprocessed_videos(
    channel_url: str,
    existing_slugs: Optional[Set[str]] = None,
    min_duration: int = 17100,
    max_duration: Optional[int] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Fetches videos from a priority channel meeting duration constraints and not yet in Drive."""
    if existing_slugs is None:
        existing_slugs = get_existing_drive_slugs()
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    venv_py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    cmd = [
        str(venv_py) if venv_py.exists() else sys.executable,
        "-m", "yt_dlp",
        url,
        "--dump-json",
        "--flat-playlist",
        f"--playlist-end={limit}",
        "--no-warnings",
        "--ignore-errors",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        candidates = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                # Skip members-only / subscriber-only videos
                if item.get("availability") in ("subscriber_only", "needs_auth"):
                    continue
                dur = item.get("duration", 0) or 0
                vid_id = item.get("id", "")
                title = item.get("title", "")
                # Check duration window
                if dur >= min_duration and (max_duration is None or dur <= max_duration) and vid_id:
                    # Strict Deduplication: Check ProcessedRegistry (video ID and normalized title)
                    from scripts.content_factory.processed_tracker import get_processed_registry
                    if get_processed_registry().is_processed(vid_id, title):
                        continue

                    # Secondary check: Google Drive albums / slugs
                    clean_cand_title = re.sub(r"\[.*?\]|\(.*?\)", " ", title.lower())
                    clean_cand_title = re.sub(r"\b(phần|tập|part|ep|chương|hồi|trọn bộ|full|review|audiobook|truyện audio)\s*\d*\b", " ", clean_cand_title)
                    clean_cand_title = re.sub(r"\s+", " ", clean_cand_title).strip()
                    cand_tokens = set(w for w in clean_cand_title.split() if len(w) > 2)

                    already_done = False
                    for s in existing_slugs:
                        if vid_id.lower() in s:
                            already_done = True
                            break
                        clean_s = re.sub(r"\[.*?\]|\(.*?\)", " ", s.lower())
                        clean_s = re.sub(r"\b(phần|tập|part|ep|chương|hồi|trọn bộ|full|review|audiobook|truyện audio)\s*\d*\b", " ", clean_s)
                        clean_s = re.sub(r"\s+", " ", clean_s).strip()
                        s_tokens = set(w for w in clean_s.split() if len(w) > 2)
                        if cand_tokens and s_tokens:
                            overlap = len(cand_tokens & s_tokens)
                            total = len(cand_tokens | s_tokens)
                            if total > 0 and (overlap / total) >= 0.70:
                                already_done = True
                                break

                    if not already_done:
                        candidates.append({
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "title": title,
                            "duration": dur,
                            "channel": item.get("uploader", ""),
                        })
            except Exception:
                continue
        return candidates
    except Exception as exc:
        log(f"[NHÁNH 1] Lỗi khi quét kênh {channel_url}: {exc}")
        return []


def branch1_worker(max_cycles: int = 100, interval_seconds: int = 10):
    """Branch 1: Continuous YouTube Audiobook harvester prioritizing user-specified channels."""
    state = get_runner_state()
    ch_idx = state.get("b1_ch_idx", 0)
    y_idx = state.get("b1_y_idx", 0)
    cycle = 1
    log("[NHÁNH 1 - YOUTUBE AUDIO] Worker song song đã khởi động thành công (Ưu tiên 3 kênh chính)!")
    while cycle <= max_cycles:
        cfg = get_factory_config()
        if not cfg.get("branch1_enabled", True):
            log("[NHÁNH 1 - YOUTUBE AUDIO] ⏸️ TẠM THỜI DỪNG theo cấu hình Dashboard.")
            time.sleep(30)
            continue
        check_and_clean_disk_space()
        target_item = None
        existing_slugs = get_existing_drive_slugs()

        # 1. First priority: Check the 3 user channels only
        for i in range(len(PRIORITY_CHANNELS)):
            curr_ch = PRIORITY_CHANNELS[(ch_idx + i) % len(PRIORITY_CHANNELS)]
            log(f"[NHÁNH 1] [Chu kỳ #{cycle}] Đang quét video mới từ kênh ưu tiên (Chỉ 3 kênh chỉ định): {curr_ch}...")
            channel_vids = _get_channel_unprocessed_videos(curr_ch, existing_slugs=existing_slugs, min_duration=17100, limit=20)
            if channel_vids:
                target_item = channel_vids[0]
                ch_idx = (ch_idx + i + 1) % len(PRIORITY_CHANNELS)
                state["b1_ch_idx"] = ch_idx
                save_runner_state(state)
                log(f"[NHÁNH 1] 🎯 Tìm thấy video hợp lệ từ kênh: '{target_item['title']}' ({target_item['duration']/3600:.1f}h)")
                break

        # 2. Strict instruction: ONLY crawl 3 priority channels, NEVER search randomly across YouTube
        if not target_item:
            log(f"[NHÁNH 1] ⏸️ Cả 3 kênh ưu tiên hiện không có video mới chưa xử lý. Tạm nghỉ {interval_seconds * 3}s trước khi kiểm tra lại...")
            time.sleep(interval_seconds * 3)
            cycle += 1
            continue

        target_url_or_query = target_item["url"]

        try:
            res_y = run_orchestrator(worker="youtube", target=target_url_or_query, min_score=7.5, extra_args={"max_episodes": 30})
            status_y = res_y.get("status")
            if status_y == "SUCCESS":
                ep_cnt = res_y.get("episodes_count", 1)
                log(f"[NHÁNH 1] Kết quả: SUCCESS | Hoàn tất bộ {ep_cnt} tập | Tiêu đề: {res_y.get('title_vi', 'N/A')}")
            else:
                log(f"[NHÁNH 1] Kết quả: {status_y} | {res_y.get('reason', res_y.get('error', 'N/A'))}")
        except Exception as exc:
            log(f"[NHÁNH 1] Lỗi: {exc}")

        time.sleep(interval_seconds)
        cycle += 1


def branch2_worker(max_cycles: int = 100, interval_seconds: int = 10):
    """Branch 2: Continuous Novel Sagas >= 5h (Fanfic: Cô Gái Hoạt Ngôn | Học Đường: Nhỏ Ngọt Ngào)."""
    state = get_runner_state()
    f_idx = state.get("b2_topic_idx", 1)
    completed_topics = set(state.get("b2_completed_topics", []))
    cycle = 1
    log(f"[NHÁNH 2 - NOVEL & FANFIC] Worker song song đã khởi động (Chỉ mục đề tài: {f_idx})!")
    while cycle <= max_cycles:
        cfg = get_factory_config()
        if not cfg.get("branch2_enabled", True):
            log("[NHÁNH 2 - NOVEL & FANFIC] ⏸️ TẠM THỜI DỪNG theo cấu hình Dashboard.")
            time.sleep(30)
            continue
        check_and_clean_disk_space()
        # Advance topic if already completed or is Naruto Jiraiya (already has 18 chapters)
        for _ in range(len(FANFIC_NOVEL_TOPICS)):
            cand_topic = FANFIC_NOVEL_TOPICS[f_idx % len(FANFIC_NOVEL_TOPICS)]
            if any(k in cand_topic.lower() for k in ("jiraiya", "mộc độn", "làng lá")) and "naruto" in cand_topic.lower():
                log("[NHÁNH 2] ⏭️ Đề tài Naruto Jiraiya đã hoàn thành trọn bộ 18 chương (> 10 tiếng) trong kho. Chuyển sang đề tài mới...")
                f_idx += 1
                continue
            if cand_topic in completed_topics:
                f_idx += 1
                continue
            break

        f_topic = FANFIC_NOVEL_TOPICS[f_idx % len(FANFIC_NOVEL_TOPICS)]
        log(f"\n[NHÁNH 2 - NOVEL & FANFIC] [Chu kỳ #{cycle}] Sáng tác & sản xuất trường thiên >= 5h: '{f_topic}'...")
        try:
            # Generate long multi-chapter sagas (chapters=28) so total audiobook reaches >= 5 hours
            res_f = run_orchestrator(worker="fanfic", target=f_topic, min_score=7.5, extra_args={"chapters": 28})
            status_f = res_f.get("status")
            if status_f == "SUCCESS":
                ch_cnt = res_f.get("chapters_count", 1)
                dur_hours = (res_f.get("duration_seconds", 0) or 0) / 3600
                log(f"[NHÁNH 2] Kết quả: SUCCESS | Bộ {ch_cnt} chương | Tổng audio: {dur_hours:.1f}h | Tiêu đề: {res_f.get('title_vi', 'N/A')}")
                completed_topics.add(f_topic)
                f_idx += 1
                state["b2_topic_idx"] = f_idx
                state["b2_completed_topics"] = list(completed_topics)
                save_runner_state(state)
            else:
                log(f"[NHÁNH 2] Kết quả: {status_f} | {res_f.get('reason', res_f.get('error', 'N/A'))}")
                f_idx += 1
                state["b2_topic_idx"] = f_idx
                save_runner_state(state)
        except Exception as exc:
            log(f"[NHÁNH 2] Lỗi: {exc}")
            f_idx += 1
            state["b2_topic_idx"] = f_idx
            save_runner_state(state)

        time.sleep(interval_seconds)
        cycle += 1


def branch3_worker(max_cycles: int = 100, interval_seconds: int = 10):
    """Branch 3: Continuous 2D Chibi Novel Animation Học Đường & Ngọt Sủng (SubVid & Đa Giọng)."""
    state = get_runner_state()
    a_idx = state.get("b3_a_idx", 0)
    ch_idx = state.get("b3_ch_idx", 0)
    cycle = 1
    log(f"[NHÁNH 3 - HOẠT HÌNH 2D HỌC ĐƯỜNG] Worker song song đã khởi động (Chỉ mục: {a_idx})!")
    while cycle <= max_cycles:
        cfg = get_factory_config()
        if not cfg.get("branch3_enabled", False):
            log("[NHÁNH 3 - HOẠT HÌNH 2D HỌC ĐƯỜNG] ⏸️ TẠM THỜI DỪNG: Nhường 100% hạn mức Quota Gemini và tài nguyên cho Nhánh 1 & Nhánh 2.")
            time.sleep(30)
            continue
        check_and_clean_disk_space()

        target_url_or_query = None
        existing_slugs = get_existing_drive_slugs()

        # 1. First priority: Check curated 2D Chibi school romance channels (duration: 10m - 120m)
        for i in range(len(PRIORITY_ANIMATION_CHANNELS)):
            curr_ch = PRIORITY_ANIMATION_CHANNELS[(ch_idx + i) % len(PRIORITY_ANIMATION_CHANNELS)]
            log(f"[NHÁNH 3] [Chu kỳ #{cycle}] Đang quét video hoạt hình 2D học đường từ kênh ưu tiên: {curr_ch}...")
            channel_vids = _get_channel_unprocessed_videos(curr_ch, existing_slugs=existing_slugs, min_duration=180, max_duration=18000, limit=20)
            if channel_vids:
                target_item = channel_vids[0]
                ch_idx = (ch_idx + i + 1) % len(PRIORITY_ANIMATION_CHANNELS)
                state["b3_ch_idx"] = ch_idx
                save_runner_state(state)
                target_url_or_query = target_item["url"]
                log(f"[NHÁNH 3] 🎯 Tìm thấy video 2D học đường hợp lệ: '{target_item['title']}' ({target_item['duration']/60:.1f} phút)")
                break

        # 2. Fallback: Rotating keyword search
        if not target_url_or_query:
            a_query = AI_ANIMATION_TOPICS[a_idx % len(AI_ANIMATION_TOPICS)]
            a_idx += 1
            state["b3_a_idx"] = a_idx
            save_runner_state(state)
            target_url_or_query = a_query
            log(f"\n[NHÁNH 3 - HOẠT HÌNH 2D HỌC ĐƯỜNG] [Chu kỳ #{cycle}] Tìm kiếm theo từ khóa: '{a_query}'...")

        try:
            res_a = run_orchestrator(worker="animation", target=target_url_or_query, min_score=7.0, extra_args={"max_episodes": 10})
            status_a = res_a.get("status")
            if status_a == "SUCCESS":
                ep_cnt = res_a.get("episodes_count", 1)
                log(f"[NHÁNH 3] Kết quả: SUCCESS | Hoàn tất bộ {ep_cnt} tập | Tiêu đề: {res_a.get('title_vi', 'N/A')}")
            else:
                log(f"[NHÁNH 3] Kết quả: {status_a} | {res_a.get('reason', res_a.get('error', 'N/A'))}")
        except Exception as exc:
            log(f"[NHÁNH 3] Lỗi: {exc}")

        time.sleep(interval_seconds)
        cycle += 1


def run_overnight_daemon(max_cycles: int = 100, interval_seconds: int = 5):
    sys.stdout = StreamToLog(LOG_FILE)
    sys.stderr = StreamToLog(LOG_FILE)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        log("=" * 70)
        log("[START] KHỞI ĐỘNG CỖ MÁY SẢN XUẤT NỘI DUNG TỰ ĐỘNG XUYÊN ĐÊM (ROUTER V4)")
        log("[PARALLEL] TẬP TRUNG TỐI ĐA CHO NHÁNH 1 (AUDIOBOOK) & NHÁNH 2 (TRUYỆN CHỮ FANFIC)")
        log("=" * 70)

        existing_slugs = get_existing_drive_slugs()
        log(f"[INFO] Tổng số tác phẩm hiện có trên Drive: {len(existing_slugs)}")

        cfg = get_factory_config()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(branch1_worker, max_cycles, interval_seconds),
                executor.submit(branch2_worker, max_cycles, interval_seconds),
                executor.submit(branch3_worker, max_cycles, interval_seconds),
            ]

            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    log(f"[CRITICAL] Một nhánh gặp lỗi dừng: {exc}")

        log("[DONE] ĐÃ HOÀN THÀNH TOÀN BỘ CHU KỲ QUA ĐÊM.")
    finally:
        try:
            if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    run_overnight_daemon()


#!/usr/bin/env python3
"""
CapCut TTS - Giao dien Gradio local de tao 3 giong tieng Viet.

*** BAN DU PHONG (LEGACY) ***
Day la giao dien Gradio cua giai doan truoc, duoc giu lai nguyen ven lam phuong
an du phong. Ung dung chinh hien tai la desktop app "Fanfic Audio Studio"
(xem `app.py` + package `desktop_app/`).

Ung dung nay tai su dung `CapCutClient` cua package `capcut_tts_api` CHI de
dung (build) request da ky, con phan goi HTTP thi tu quan ly bang mot
`requests.Session` rieng de kiem soat timeout, poll va nut DUNG.
Package goc khong bi sua doi.

Chay:  python legacy_gradio_app.py   (hoac nhap dup run_gradio.bat)
"""

from __future__ import annotations

import inspect
import json
import sys
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import gradio as gr
import requests

sys.path.insert(0, str(Path(__file__).parent))

from capcut_tts_api import CapCutClient  # noqa: E402
from capcut_tts_api.exceptions import CapCutError  # noqa: E402

# -----------------------------------------------------------------------------
# Cau hinh
# -----------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent.resolve()
OUTPUT_ROOT = PROJECT_DIR / "outputs"

# (khoa_file, ten_hien_thi, voice_type)
VOICES: List[Tuple[str, str, str]] = [
    ("nho_ngot_ngao", "Nhỏ Ngọt Ngào", "BV421_vivn_streaming"),
    ("co_gai_hoat_ngon", "Cô Gái Hoạt Ngôn", "BV074_streaming"),
    ("review_phim_new", "Review Phim new", "multi_female_richgirl_uranus_bigtts"),
]

CONNECT_TIMEOUT = 8.0          # connect timeout cho moi request
READ_TIMEOUT_CREATE = 20.0     # read timeout khi tao task
READ_TIMEOUT_QUERY = 12.0      # read timeout khi kiem tra task
READ_TIMEOUT_DOWNLOAD = 30.0   # read timeout khi tai audio

POLL_TOTAL_SECONDS = 60.0      # tong thoi gian poll toi da
POLL_INTERVAL_SECONDS = 3.0    # chu ky poll
GAP_BETWEEN_VOICES = 5.0       # nghi giua cac giong (chay tuan tu)

DONE_STATUSES = {"success", "succeed", "completed", "done"}
FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}

SHARK_MARKERS = ("shark", "verify_center", "secsdk", "captcha", "risk_control")

UI_TICK_SECONDS = 0.4          # nhip cap nhat giao dien

MAX_CHARS_WARN = 3000          # chi canh bao, khong chan


# -----------------------------------------------------------------------------
# Loi co phan loai
# -----------------------------------------------------------------------------


class VoiceJobError(Exception):
    """Loi mot giong, co phan loai de hien thi ro rang tren giao dien."""

    def __init__(self, kind: str, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail


class StopRequested(Exception):
    """Nguoi dung bam DUNG."""


def _http_error(resp: requests.Response, label: str) -> VoiceJobError:
    """Phan loai loi HTTP tra ve tu API."""
    body = (resp.text or "")[:1500]
    shark = _shark_marker(body)
    if shark:
        return VoiceJobError(
            "shark_block",
            f"Bị chặn bởi hệ thống bảo vệ (shark/captcha) tại {label} — HTTP {resp.status_code}",
            f"Dấu hiệu: '{shark}'. Body: {body[:400]}",
        )
    if resp.status_code == 403:
        return VoiceJobError(
            "http_403",
            f"HTTP 403 Forbidden tại {label} — request bị từ chối (sign/device có thể đã hết hiệu lực)",
            body[:400],
        )
    if resp.status_code == 429:
        return VoiceJobError(
            "http_429",
            f"HTTP 429 Too Many Requests tại {label} — bị giới hạn tần suất, hãy chờ rồi thử lại",
            body[:400],
        )
    return VoiceJobError(
        "http_error",
        f"HTTP {resp.status_code} tại {label}",
        body[:400],
    )


def _shark_marker(text: str) -> Optional[str]:
    """Tim dau hieu shark/captcha trong noi dung tra ve (neu co)."""
    low = (text or "")[:4000].lower()
    for marker in SHARK_MARKERS:
        if marker in low:
            return marker
    return None


# -----------------------------------------------------------------------------
# Trang thai mot giong + trang thai ca phien chay
# -----------------------------------------------------------------------------


@dataclass
class VoiceState:
    key: str
    label: str
    voice_type: str
    state: str = "pending"       # pending | running | success | failed | skipped
    message: str = "Chờ đến lượt"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    file_path: Optional[str] = None
    file_size: int = 0
    task_id: Optional[str] = None
    audio_url: Optional[str] = None
    error_kind: Optional[str] = None
    error_detail: str = ""

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return max(0.0, end - self.started_at)

    def elapsed_text(self) -> str:
        if self.started_at is None:
            return "Đã chờ: 0s"
        return f"Đã chờ: {self.elapsed():.0f}s"

    def status_text(self) -> str:
        icon = {
            "pending": "⏳",
            "running": "🔄",
            "success": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }.get(self.state, "•")
        return f"{icon} {self.message}"

    def to_report(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "voice_type": self.voice_type,
            "state": self.state,
            "message": self.message,
            "elapsed_seconds": round(self.elapsed(), 2),
            "task_id": self.task_id,
            "audio_url": self.audio_url,
            "file": Path(self.file_path).name if self.file_path else None,
            "file_size_bytes": self.file_size,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail[:1000] if self.error_detail else "",
        }


@dataclass
class RunState:
    text: str
    run_dir: Path
    stop_event: threading.Event = field(default_factory=threading.Event)
    voices: List[VoiceState] = field(default_factory=list)
    overall: str = "Đang chuẩn bị..."
    zip_path: Optional[str] = None
    report_path: Optional[str] = None
    done: bool = False


# -----------------------------------------------------------------------------
# Tro giup: tim URL audio trong payload tra ve
# -----------------------------------------------------------------------------

_URL_KEY_HINTS = ("tts_url", "audio_url", "mp3_url", "download_url", "url", "uri", "link", "addr")


def _maybe_json(value: str) -> Optional[Any]:
    stripped = value.strip()
    if stripped[:1] in ("{", "[") and stripped[-1:] in ("}", "]"):
        try:
            return json.loads(stripped)
        except Exception:
            return None
    return None


def _collect_audio_urls(node: Any, key_path: str = "", depth: int = 0) -> List[Tuple[int, str]]:
    """
    Duyet de quy payload (ke ca chuoi JSON long nhau) va thu thap cac URL kem diem uu tien.
    Tra ve list (score, url).
    """
    if depth > 12:
        return []

    found: List[Tuple[int, str]] = []

    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(_collect_audio_urls(value, str(key).lower(), depth + 1))
    elif isinstance(node, (list, tuple)):
        for item in node:
            found.extend(_collect_audio_urls(item, key_path, depth + 1))
    elif isinstance(node, str):
        nested = _maybe_json(node)
        if nested is not None:
            found.extend(_collect_audio_urls(nested, key_path, depth + 1))
        elif node.startswith("http://") or node.startswith("https://"):
            score = 0
            if any(hint in key_path for hint in ("tts", "audio", "mp3", "voice", "speech")):
                score += 3
            if any(key_path == hint for hint in ("url", "uri", "link")):
                score += 1
            if any(hint in key_path for hint in _URL_KEY_HINTS):
                score += 1
            low = node.lower()
            if ".mp3" in low:
                score += 4
            if any(ext in low for ext in (".m4a", ".aac", ".wav", ".ogg")):
                score += 2
            found.append((score, node))

    return found


def _find_audio_url(payload: Any) -> Optional[str]:
    candidates = _collect_audio_urls(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _decode_payload(task: Dict[str, Any]) -> Any:
    """Giai ma truong payload cua task (co the la chuoi JSON)."""
    raw = task.get("payload")
    if isinstance(raw, str):
        decoded = _maybe_json(raw)
        return decoded if decoded is not None else raw
    return raw


# -----------------------------------------------------------------------------
# Goi API cho mot giong (tu quan ly HTTP, khong dung generate_speech)
# -----------------------------------------------------------------------------


def _post(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    body_text: str,
    read_timeout: float,
    label: str,
) -> Dict[str, Any]:
    """POST mot request da ky, bat va phan loai moi loi mang/HTTP."""
    try:
        resp = session.post(
            url,
            headers=headers,
            data=body_text.encode("utf-8"),
            timeout=(CONNECT_TIMEOUT, read_timeout),
        )
    except requests.exceptions.ConnectTimeout as exc:
        raise VoiceJobError(
            "connect_timeout",
            f"ConnectTimeout tại {label}: không kết nối được máy chủ trong {CONNECT_TIMEOUT:.0f}s",
            str(exc),
        ) from exc
    except requests.exceptions.ReadTimeout as exc:
        raise VoiceJobError(
            "read_timeout",
            f"ReadTimeout tại {label}: máy chủ không trả lời trong {read_timeout:.0f}s",
            str(exc),
        ) from exc
    except requests.exceptions.SSLError as exc:
        raise VoiceJobError("ssl_error", f"Lỗi SSL tại {label}", str(exc)) from exc
    except requests.exceptions.ProxyError as exc:
        raise VoiceJobError("proxy_error", f"Lỗi proxy tại {label}", str(exc)) from exc
    except requests.exceptions.Timeout as exc:
        raise VoiceJobError("timeout", f"Timeout tại {label}", str(exc)) from exc
    except requests.exceptions.ConnectionError as exc:
        raise VoiceJobError(
            "network_error",
            f"Lỗi mạng tại {label}: không kết nối được (kiểm tra internet/DNS/firewall)",
            str(exc),
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise VoiceJobError("request_error", f"Lỗi request tại {label}: {exc}", str(exc)) from exc

    if resp.status_code >= 400:
        raise _http_error(resp, label)

    shark = _shark_marker(resp.text)
    if shark:
        raise VoiceJobError(
            "shark_block",
            f"Bị chặn bởi hệ thống bảo vệ (shark/captcha) tại {label}",
            f"Dấu hiệu: '{shark}'. Body: {(resp.text or '')[:400]}",
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise VoiceJobError(
            "bad_response",
            f"{label} trả về nội dung không phải JSON (HTTP {resp.status_code})",
            (resp.text or "")[:400],
        ) from exc

    if not isinstance(data, dict):
        raise VoiceJobError(
            "bad_response", f"{label} trả về JSON không đúng định dạng", str(data)[:400]
        )
    return data


def _extract_created_task(data: Dict[str, Any]) -> Tuple[str, str, str]:
    """Lay task_id / token / bind_id tu phan hoi tao task."""
    ret = str(data.get("ret", "0"))
    errmsg = str(data.get("errmsg", ""))
    tasks = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("tasks") or []

    if not tasks:
        if ret not in ("0", ""):
            raise VoiceJobError(
                "api_error",
                f"API báo lỗi khi tạo task (ret={ret}): {errmsg or 'không có thông báo'}",
                json.dumps(data, ensure_ascii=False)[:600],
            )
        raise VoiceJobError(
            "no_task",
            "API không trả về task nào cho yêu cầu TTS",
            json.dumps(data, ensure_ascii=False)[:600],
        )

    task = tasks[0] or {}
    task_id = task.get("id")
    token = task.get("token")
    if not task_id or not token:
        raise VoiceJobError(
            "task_missing_fields",
            f"Task thiếu {'id' if not task_id else 'token'} — không thể theo dõi tiến trình",
            json.dumps(task, ensure_ascii=False)[:600],
        )
    return str(task_id), str(token), str(task.get("bind_id") or "")


def _download_audio(
    session: requests.Session,
    url: str,
    dest: Path,
    stop_event: threading.Event,
) -> int:
    """Tai file audio ve dia. Tra ve so byte da ghi."""
    try:
        with session.get(
            url,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT_DOWNLOAD),
            stream=True,
        ) as resp:
            if resp.status_code >= 400:
                raise _http_error(resp, "tải audio")
            total = 0
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if stop_event.is_set():
                        fp.close()
                        tmp.unlink(missing_ok=True)
                        raise StopRequested()
                    if chunk:
                        fp.write(chunk)
                        total += len(chunk)
            if total == 0:
                tmp.unlink(missing_ok=True)
                raise VoiceJobError("empty_audio", "File audio tải về rỗng (0 byte)", url[:300])
            tmp.replace(dest)
            return total
    except StopRequested:
        raise
    except VoiceJobError:
        raise
    except requests.exceptions.ConnectTimeout as exc:
        raise VoiceJobError(
            "connect_timeout",
            f"ConnectTimeout khi tải audio: không kết nối được trong {CONNECT_TIMEOUT:.0f}s",
            str(exc),
        ) from exc
    except requests.exceptions.ReadTimeout as exc:
        raise VoiceJobError(
            "read_timeout",
            f"ReadTimeout khi tải audio: quá {READ_TIMEOUT_DOWNLOAD:.0f}s không nhận được dữ liệu",
            str(exc),
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise VoiceJobError("network_error", f"Lỗi mạng khi tải audio: {exc}", str(exc)) from exc
    except OSError as exc:
        raise VoiceJobError("disk_error", f"Không ghi được file audio: {exc}", str(exc)) from exc


def generate_one_voice(
    client: CapCutClient,
    session: requests.Session,
    text: str,
    voice: VoiceState,
    run_dir: Path,
    stop_event: threading.Event,
    progress: Callable[[str], None],
) -> None:
    """
    Tao audio cho mot giong: tao task -> poll trang thai -> tai MP3.
    Cap nhat truc tiep vao `voice`. Nem VoiceJobError / StopRequested khi loi.
    """
    if stop_event.is_set():
        raise StopRequested()

    progress("Đang tạo task TTS...")
    url, headers, body_text = client.build_tts_new_request(
        texts=text,
        voice=voice.voice_type,
        rate="1.0",
    )
    create_data = _post(session, url, headers, body_text, READ_TIMEOUT_CREATE, "tạo task")
    task_id, token, bind_id = _extract_created_task(create_data)
    voice.task_id = task_id

    if stop_event.is_set():
        raise StopRequested()

    progress(f"Đã tạo task {task_id[:12]}..., đang chờ xử lý...")

    deadline = time.monotonic() + POLL_TOTAL_SECONDS
    attempt = 0
    last_status = "(chưa có)"
    audio_url: Optional[str] = None

    while True:
        if stop_event.is_set():
            raise StopRequested()

        attempt += 1
        q_url, q_headers, q_body = client.build_query_request(
            task_id, token, mode="tts", bind_id=bind_id
        )
        query_data = _post(session, q_url, q_headers, q_body, READ_TIMEOUT_QUERY, "kiểm tra task")

        q_tasks = ((query_data.get("data") or {}) if isinstance(query_data.get("data"), dict) else {}).get("tasks") or []
        if q_tasks:
            task = q_tasks[0] or {}
            raw_status = task.get("status")
            status = str(raw_status).strip().lower() if raw_status is not None else ""
            last_status = status or "(rỗng)"

            if status in DONE_STATUSES:
                payload = _decode_payload(task)
                audio_url = _find_audio_url(payload)
                if not audio_url:
                    raise VoiceJobError(
                        "no_audio_url",
                        f"Task báo thành công ({status}) nhưng không tìm thấy URL audio trong phản hồi",
                        json.dumps(payload, ensure_ascii=False)[:800]
                        if not isinstance(payload, str)
                        else payload[:800],
                    )
                break

            if status in FAILED_STATUSES:
                message = task.get("message") or task.get("err_msg") or task.get("errmsg") or ""
                raise VoiceJobError(
                    "task_failed",
                    f"Task thất bại với trạng thái '{status}'"
                    + (f": {message}" if message else ""),
                    json.dumps(task, ensure_ascii=False)[:600],
                )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise VoiceJobError(
                "poll_timeout",
                f"Hết {POLL_TOTAL_SECONDS:.0f}s chờ xử lý, trạng thái cuối: '{last_status}'",
                f"task_id={task_id}, số lần kiểm tra={attempt}",
            )

        progress(
            f"Đang xử lý (trạng thái: {last_status}, lần kiểm tra {attempt}, "
            f"còn {remaining:.0f}s)..."
        )
        # stop_event.wait() de nut DUNG co hieu luc ngay trong luc nghi
        if stop_event.wait(min(POLL_INTERVAL_SECONDS, max(0.1, remaining))):
            raise StopRequested()

    progress("Đang tải file MP3...")
    voice.audio_url = audio_url
    dest = run_dir / f"{voice.key}.mp3"
    size = _download_audio(session, audio_url, dest, stop_event)
    voice.file_path = str(dest)
    voice.file_size = size


# -----------------------------------------------------------------------------
# Luong chay ca 3 giong (chay trong thread rieng)
# -----------------------------------------------------------------------------


def _write_report(state: RunState) -> str:
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(state.run_dir),
        "text_length": len(state.text),
        "text": state.text,
        "settings": {
            "connect_timeout_s": CONNECT_TIMEOUT,
            "read_timeout_create_s": READ_TIMEOUT_CREATE,
            "read_timeout_query_s": READ_TIMEOUT_QUERY,
            "read_timeout_download_s": READ_TIMEOUT_DOWNLOAD,
            "poll_total_s": POLL_TOTAL_SECONDS,
            "poll_interval_s": POLL_INTERVAL_SECONDS,
            "gap_between_voices_s": GAP_BETWEEN_VOICES,
        },
        "stopped_by_user": state.stop_event.is_set(),
        "summary": {
            "success": sum(1 for v in state.voices if v.state == "success"),
            "failed": sum(1 for v in state.voices if v.state == "failed"),
            "skipped": sum(1 for v in state.voices if v.state == "skipped"),
        },
        "voices": [v.to_report() for v in state.voices],
    }
    report_path = state.run_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return str(report_path)


def _write_zip(state: RunState) -> Optional[str]:
    files = [Path(v.file_path) for v in state.voices if v.file_path and Path(v.file_path).exists()]
    report_path = Path(state.report_path) if state.report_path else None
    if not files and not (report_path and report_path.exists()):
        return None
    zip_path = state.run_dir / f"capcut_tts_{state.run_dir.name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, arcname=path.name)
            if report_path and report_path.exists():
                zf.write(report_path, arcname=report_path.name)
    except OSError:
        return None
    return str(zip_path)


def _run_all_voices(state: RunState) -> None:
    """Chay tuan tu 3 giong. Moi loi cua mot giong khong lam dung cac giong sau."""
    session = requests.Session()
    try:
        client = CapCutClient(session=session)
    except Exception as exc:  # pragma: no cover - phong ngua
        state.overall = f"❌ Không khởi tạo được CapCutClient: {exc}"
        state.done = True
        session.close()
        return

    try:
        for index, voice in enumerate(state.voices):
            if state.stop_event.is_set():
                for remaining in state.voices[index:]:
                    if remaining.state == "pending":
                        remaining.state = "skipped"
                        remaining.message = "Đã bỏ qua (người dùng bấm DỪNG)"
                break

            if index > 0:
                state.overall = (
                    f"⏸️ Nghỉ {GAP_BETWEEN_VOICES:.0f}s trước giọng "
                    f"{index + 1}/{len(state.voices)}: {voice.label}"
                )
                if state.stop_event.wait(GAP_BETWEEN_VOICES):
                    for remaining in state.voices[index:]:
                        if remaining.state == "pending":
                            remaining.state = "skipped"
                            remaining.message = "Đã bỏ qua (người dùng bấm DỪNG)"
                    break

            voice.state = "running"
            voice.started_at = time.monotonic()
            voice.message = "Bắt đầu..."
            state.overall = (
                f"🔄 Đang xử lý giọng {index + 1}/{len(state.voices)}: {voice.label}"
            )

            def progress(message: str, _voice: VoiceState = voice) -> None:
                _voice.message = message

            try:
                generate_one_voice(
                    client=client,
                    session=session,
                    text=state.text,
                    voice=voice,
                    run_dir=state.run_dir,
                    stop_event=state.stop_event,
                    progress=progress,
                )
                voice.state = "success"
                voice.message = f"Hoàn thành ({voice.file_size / 1024:.0f} KB)"
            except StopRequested:
                voice.state = "failed"
                voice.error_kind = "stopped"
                voice.message = "Đã dừng theo yêu cầu người dùng"
            except VoiceJobError as exc:
                voice.state = "failed"
                voice.error_kind = exc.kind
                voice.message = exc.message
                voice.error_detail = exc.detail
            except CapCutError as exc:
                voice.state = "failed"
                voice.error_kind = "capcut_error"
                voice.message = f"Lỗi thư viện CapCut: {exc}"
                voice.error_detail = traceback.format_exc()[-1500:]
            except Exception as exc:  # khong de exception lam sap app
                voice.state = "failed"
                voice.error_kind = "unexpected"
                voice.message = f"Lỗi không mong đợi: {type(exc).__name__}: {exc}"
                voice.error_detail = traceback.format_exc()[-1500:]
            finally:
                voice.finished_at = time.monotonic()

        ok = sum(1 for v in state.voices if v.state == "success")
        bad = sum(1 for v in state.voices if v.state == "failed")
        skipped = sum(1 for v in state.voices if v.state == "skipped")
        head = "🛑 Đã dừng." if state.stop_event.is_set() else "🏁 Xong."
        state.overall = (
            f"{head} Thành công: {ok}/{len(state.voices)}"
            + (f" · Thất bại: {bad}" if bad else "")
            + (f" · Bỏ qua: {skipped}" if skipped else "")
            + f" · Thư mục: {state.run_dir}"
        )
    except Exception as exc:  # pragma: no cover - lop bao ve cuoi
        state.overall = f"❌ Lỗi tổng: {type(exc).__name__}: {exc}"
    finally:
        try:
            state.report_path = _write_report(state)
            state.zip_path = _write_zip(state)
        except Exception as exc:
            state.overall += f" · (Không ghi được report/zip: {exc})"
        try:
            session.close()
        except Exception:
            pass
        state.done = True


# -----------------------------------------------------------------------------
# Giao dien Gradio
# -----------------------------------------------------------------------------

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_STATE: Optional[RunState] = None


def _make_run_dir() -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = OUTPUT_ROOT / stamp
    suffix = 2
    while run_dir.exists():
        run_dir = OUTPUT_ROOT / f"{stamp}_{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)
    return run_dir


def count_chars(text: str) -> str:
    text = text or ""
    note = ""
    if len(text) > MAX_CHARS_WARN:
        note = f" ⚠️ Văn bản dài hơn {MAX_CHARS_WARN} ký tự, API có thể từ chối hoặc chậm."
    return f"Số ký tự: {len(text)}{note}"


def _render(state: Optional[RunState]) -> List[Any]:
    """Dung danh sach gia tri cho cac output component."""
    if state is None:
        values: List[Any] = ["Chưa chạy."]
        for _key, label, voice_type in VOICES:
            values += [
                f"⏳ Chờ đến lượt  ·  {label} ({voice_type})",
                "Đã chờ: 0s",
                gr.update(value=None),
                gr.update(value=None),
            ]
        values.append(gr.update(value=None))
        return values

    values = [state.overall]
    for voice in state.voices:
        values += [
            voice.status_text(),
            voice.elapsed_text(),
            gr.update(value=voice.file_path) if voice.file_path else gr.update(value=None),
            gr.update(value=voice.file_path) if voice.file_path else gr.update(value=None),
        ]
    values.append(gr.update(value=state.zip_path) if state.zip_path else gr.update(value=None))
    return values


def generate_all(text: str):
    """
    Generator: khoi dong worker thread roi lien tuc yield trang thai
    de giao dien khong bao gio dung im khi dang goi API.
    """
    global _ACTIVE_STATE

    text = (text or "").strip()
    if not text:
        values = _render(None)
        values[0] = "⚠️ Vui lòng nhập văn bản trước khi tạo giọng."
        yield tuple(values)
        return

    with _ACTIVE_LOCK:
        if _ACTIVE_STATE is not None and not _ACTIVE_STATE.done:
            values = _render(_ACTIVE_STATE)
            values[0] = "⚠️ Đang có một phiên chạy khác. Hãy chờ hoặc bấm DỪNG."
            yield tuple(values)
            return

        try:
            run_dir = _make_run_dir()
        except OSError as exc:
            values = _render(None)
            values[0] = f"❌ Không tạo được thư mục kết quả: {exc}"
            yield tuple(values)
            return

        state = RunState(text=text, run_dir=run_dir)
        state.voices = [
            VoiceState(key=key, label=label, voice_type=voice_type)
            for key, label, voice_type in VOICES
        ]
        state.overall = f"🚀 Bắt đầu · Kết quả sẽ lưu vào: {run_dir}"
        _ACTIVE_STATE = state

    worker = threading.Thread(target=_run_all_voices, args=(state,), daemon=True)
    worker.start()

    yield tuple(_render(state))
    while worker.is_alive():
        worker.join(UI_TICK_SECONDS)
        yield tuple(_render(state))

    # lan yield cuoi de chac chan zip/report da xuat hien
    yield tuple(_render(state))


def request_stop() -> str:
    state = _ACTIVE_STATE
    if state is None or state.done:
        return "Không có phiên nào đang chạy."
    state.stop_event.set()
    return (
        "🛑 Đã gửi yêu cầu DỪNG. Lưu ý: một HTTP request đang chạy không thể bị hủy — "
        "app sẽ dừng ngay sau khi request hiện tại kết thúc hoặc hết timeout."
    )


def _on_start():
    return gr.update(interactive=False), gr.update(interactive=True)


def _on_end():
    return gr.update(interactive=True), gr.update(interactive=False)


def build_ui() -> gr.Blocks:
    voice_lines = "\n".join(
        f"- **{label}** — `{voice_type}` → `{key}.mp3`" for key, label, voice_type in VOICES
    )

    with gr.Blocks(title="CapCut TTS - Tạo 3 giọng tiếng Việt") as demo:
        gr.Markdown("# CapCut TTS - Tạo 3 giọng tiếng Việt")
        gr.Markdown(
            "Nhập văn bản, bấm **TẠO CẢ 3 GIỌNG**. App gọi API **tuần tự** "
            f"(nghỉ {GAP_BETWEEN_VOICES:.0f}s giữa các giọng), một giọng lỗi vẫn tiếp tục giọng sau.\n\n"
            + voice_lines
        )

        with gr.Row():
            with gr.Column(scale=3):
                text_input = gr.Textbox(
                    label="Văn bản tiếng Việt",
                    placeholder="Nhập nội dung cần đọc...",
                    lines=12,
                    max_lines=40,
                )
                char_count = gr.Markdown("Số ký tự: 0")
            with gr.Column(scale=1):
                run_btn = gr.Button("TẠO CẢ 3 GIỌNG", variant="primary", size="lg")
                stop_btn = gr.Button("DỪNG", variant="stop", size="lg", interactive=False)
                gr.Markdown(
                    "*Nút DỪNG dùng `threading.Event`. Không thể hủy một HTTP request "
                    "đang chạy — lệnh dừng có hiệu lực sau khi request hiện tại kết thúc "
                    "hoặc hết timeout.*"
                )

        overall_status = gr.Textbox(
            label="Tiến trình chung", value="Chưa chạy.", interactive=False, lines=2
        )

        outputs: List[Any] = [overall_status]

        for key, label, voice_type in VOICES:
            with gr.Group():
                gr.Markdown(f"### {label}  ·  `{voice_type}`")
                with gr.Row():
                    status_box = gr.Textbox(
                        label="Trạng thái",
                        value=f"⏳ Chờ đến lượt  ·  {label} ({voice_type})",
                        interactive=False,
                        scale=4,
                        lines=2,
                    )
                    elapsed_box = gr.Textbox(
                        label="Thời gian", value="Đã chờ: 0s", interactive=False, scale=1
                    )
                with gr.Row():
                    audio_player = gr.Audio(
                        label=f"Nghe thử — {label}",
                        type="filepath",
                        interactive=False,
                        scale=3,
                    )
                    file_download = gr.File(label=f"Tải MP3 — {key}.mp3", scale=2)
            outputs += [status_box, elapsed_box, audio_player, file_download]

        zip_download = gr.File(label="Tải ZIP (3 MP3 + report.json)")
        outputs.append(zip_download)

        # --- su kien
        text_input.change(
            fn=count_chars, inputs=text_input, outputs=char_count, show_progress="hidden"
        )

        run_btn.click(
            fn=_on_start, inputs=None, outputs=[run_btn, stop_btn], queue=False
        ).then(
            fn=generate_all, inputs=text_input, outputs=outputs
        ).then(
            fn=_on_end, inputs=None, outputs=[run_btn, stop_btn], queue=False
        )

        # queue=False de nut DUNG luon phan hoi ngay, khong cho hang doi
        stop_btn.click(fn=request_stop, inputs=None, outputs=overall_status, queue=False)

    return demo


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    demo = build_ui()
    demo.queue()

    # Loc kwargs theo phien ban gradio dang cai (4/5/6 khac nhau vai tham so)
    supported = set(inspect.signature(gr.Blocks.launch).parameters)
    wanted = {
        "server_name": "127.0.0.1",
        "inbrowser": True,
        "share": False,
        "show_api": False,
        "allowed_paths": [str(OUTPUT_ROOT)],
    }
    launch_kwargs = {k: v for k, v in wanted.items() if k in supported}

    last_error: Optional[BaseException] = None
    for port in range(7860, 7871):
        try:
            print(f"Đang mở giao diện tại http://127.0.0.1:{port} ...")
            demo.launch(server_port=port, **launch_kwargs)
            return
        except OSError as exc:
            last_error = exc
            print(f"Cổng {port} đang bị chiếm, thử cổng tiếp theo...")
    print(f"Không mở được cổng 7860-7870. Lỗi cuối: {last_error}")
    sys.exit(1)


if __name__ == "__main__":
    main()

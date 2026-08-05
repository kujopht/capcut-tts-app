"""
Goi API CapCut TTS.

Logic o day duoc PORT NGUYEN HANH VI tu ban Gradio da chay duoc:
tai su dung `CapCutClient` CHI de dung (build) request da ky, con phan HTTP thi
tu quan ly bang `requests.Session` rieng de kiem soat timeout theo tung buoc,
poll, va lenh dung.

Bo sung o giai doan nay:
- HTTP 429: backoff + thu lai toi da 3 lan (ky lai request moi lan thu).
- HTTP 403 / shark block: danh dau la loi nghiem trong de hang doi dung han.

Package `capcut_tts_api` goc khong bi sua doi.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from desktop_app.models import (
    CONNECT_TIMEOUT,
    DONE_STATUSES,
    FAILED_STATUSES,
    POLL_INTERVAL_SECONDS,
    POLL_TOTAL_SECONDS,
    RATE_LIMIT_BACKOFF_SECONDS,
    RATE_LIMIT_MAX_RETRIES,
    READ_TIMEOUT_CREATE,
    READ_TIMEOUT_DOWNLOAD,
    READ_TIMEOUT_QUERY,
    SHARK_MARKERS,
    ErrorKind,
    VoiceEntry,
    mask_secret,
)


# -----------------------------------------------------------------------------
# Loi & dieu khien dung
# -----------------------------------------------------------------------------


class TtsError(Exception):
    """Loi da phan loai khi goi API."""

    def __init__(self, kind: ErrorKind, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    @property
    def is_fatal_for_queue(self) -> bool:
        return self.kind.is_fatal_for_queue


class StopRequested(Exception):
    """Nguoi dung yeu cau dung."""


class CancelToken:
    """
    Bao boc `threading.Event` de truyen lenh dung xuong tan lop goi HTTP.

    Luu y trung thuc: KHONG the huy mot HTTP request dang chay giua duong.
    Token chi co hieu luc o cac diem kiem tra (giua cac buoc, trong luc nghi,
    va giua cac chunk khi tai file) — nghia la sau khi request hien tai ket
    thuc hoac het timeout.
    """

    def __init__(self, event: Optional[threading.Event] = None):
        self._event = event or threading.Event()

    @property
    def event(self) -> threading.Event:
        return self._event

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, seconds: float) -> bool:
        """Nghi toi da `seconds`; tra True neu bi yeu cau dung trong luc nghi."""
        return self._event.wait(max(0.0, seconds))

    def raise_if_set(self) -> None:
        if self._event.is_set():
            raise StopRequested()


# -----------------------------------------------------------------------------
# Ket qua mot part
# -----------------------------------------------------------------------------


class PartResult:
    """Ket qua tao audio cho mot part."""

    def __init__(
        self,
        file_path: str,
        file_size: int,
        task_id: Optional[str],
        token_masked: Optional[str],
        audio_host: Optional[str],
        attempts: int,
    ):
        self.file_path = file_path
        self.file_size = file_size
        self.task_id = task_id
        self.token_masked = token_masked
        self.audio_host = audio_host
        self.attempts = attempts


# -----------------------------------------------------------------------------
# Tro giup
# -----------------------------------------------------------------------------


def shark_marker(text: str) -> Optional[str]:
    """Tim dau hieu shark/captcha trong noi dung tra ve."""
    low = (text or "")[:4000].lower()
    for marker in SHARK_MARKERS:
        if marker in low:
            return marker
    return None


def safe_url_label(url: Optional[str]) -> Optional[str]:
    """
    Chi giu host + path cua URL audio de ghi manifest.
    Query string cua CDN co the chua token/chu ky nen bi bo di.
    """
    if not url:
        return None
    try:
        parts = urlsplit(url)
        return f"{parts.netloc}{parts.path}" or parts.netloc
    except Exception:
        return None


def _maybe_json(value: str) -> Optional[Any]:
    stripped = (value or "").strip()
    if stripped[:1] in ("{", "[") and stripped[-1:] in ("}", "]"):
        try:
            return json.loads(stripped)
        except Exception:
            return None
    return None


_URL_KEY_HINTS = ("tts_url", "audio_url", "mp3_url", "download_url", "url", "uri", "link", "addr")


def _collect_audio_urls(node: Any, key_path: str = "", depth: int = 0) -> List[Tuple[int, str]]:
    """Duyet de quy payload (ke ca chuoi JSON long nhau), thu thap URL kem diem."""
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
            if key_path in ("url", "uri", "link"):
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


def find_audio_url(payload: Any) -> Optional[str]:
    """Tim URL audio trong payload tra ve (khong doan cung mot ten khoa)."""
    candidates = _collect_audio_urls(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def decode_payload(task: Dict[str, Any]) -> Any:
    raw = task.get("payload")
    if isinstance(raw, str):
        decoded = _maybe_json(raw)
        return decoded if decoded is not None else raw
    return raw


def http_error(resp: requests.Response, label: str) -> TtsError:
    """Phan loai loi HTTP."""
    body = (resp.text or "")[:1500]
    marker = shark_marker(body)
    if marker:
        return TtsError(
            ErrorKind.SHARK_BLOCK,
            f"Bị chặn bởi hệ thống bảo vệ (shark/captcha) tại {label} — HTTP {resp.status_code}",
            f"Dấu hiệu: '{marker}'. Body: {body[:400]}",
        )
    if resp.status_code == 403:
        return TtsError(
            ErrorKind.HTTP_403,
            f"HTTP 403 Forbidden tại {label} — request bị từ chối "
            "(sign/device có thể đã hết hiệu lực)",
            body[:400],
        )
    if resp.status_code == 429:
        return TtsError(
            ErrorKind.HTTP_429,
            f"HTTP 429 Too Many Requests tại {label} — bị giới hạn tần suất",
            body[:400],
        )
    return TtsError(ErrorKind.HTTP_ERROR, f"HTTP {resp.status_code} tại {label}", body[:400])


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


class TtsService:
    """
    Bao boc CapCutClient + requests.Session voi timeout, poll va backoff ro rang.

    Mot instance dung cho mot worker (khong chia se giua nhieu thread).
    """

    def __init__(
        self,
        device_path: Optional[str] = None,
        session: Optional[requests.Session] = None,
        catalog_path: Optional[str] = None,
    ):
        self.device_path = device_path or None
        self.catalog_path = catalog_path
        self.session = session or requests.Session()
        self._client = None
        self._client_error: Optional[str] = None

    # -- khoi tao client ------------------------------------------------------

    @property
    def client(self):
        """Tao CapCutClient lan dau khi can (lazy) va nho lai loi neu that bai."""
        if self._client is None:
            if self._client_error:
                raise TtsError(ErrorKind.UNEXPECTED, self._client_error)
            try:
                from capcut_tts_api import CapCutClient
            except Exception as exc:
                self._client_error = f"Không import được capcut_tts_api: {exc}"
                raise TtsError(ErrorKind.UNEXPECTED, self._client_error) from exc
            try:
                if self.device_path and Path(self.device_path).is_file():
                    self._client = CapCutClient(device=self.device_path, session=self.session)
                else:
                    self._client = CapCutClient(session=self.session)
            except Exception as exc:
                self._client_error = f"Không khởi tạo được CapCutClient: {exc}"
                raise TtsError(ErrorKind.UNEXPECTED, self._client_error) from exc
        return self._client

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    # -- tang HTTP ------------------------------------------------------------

    def _post_once(
        self,
        url: str,
        headers: Dict[str, str],
        body_text: str,
        read_timeout: float,
        label: str,
    ) -> Dict[str, Any]:
        """Gui mot POST da ky, bat va phan loai moi loi mang/HTTP."""
        try:
            resp = self.session.post(
                url,
                headers=headers,
                data=body_text.encode("utf-8"),
                timeout=(CONNECT_TIMEOUT, read_timeout),
            )
        except requests.exceptions.ConnectTimeout as exc:
            raise TtsError(
                ErrorKind.CONNECT_TIMEOUT,
                f"ConnectTimeout tại {label}: không kết nối được máy chủ trong "
                f"{CONNECT_TIMEOUT:.0f}s",
                str(exc),
            ) from exc
        except requests.exceptions.ReadTimeout as exc:
            raise TtsError(
                ErrorKind.READ_TIMEOUT,
                f"ReadTimeout tại {label}: máy chủ không trả lời trong {read_timeout:.0f}s",
                str(exc),
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise TtsError(ErrorKind.SSL_ERROR, f"Lỗi SSL tại {label}", str(exc)) from exc
        except requests.exceptions.ProxyError as exc:
            raise TtsError(ErrorKind.PROXY_ERROR, f"Lỗi proxy tại {label}", str(exc)) from exc
        except requests.exceptions.Timeout as exc:
            raise TtsError(ErrorKind.TIMEOUT, f"Timeout tại {label}", str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise TtsError(
                ErrorKind.NETWORK_ERROR,
                f"Lỗi mạng tại {label}: không kết nối được (kiểm tra internet/DNS/firewall)",
                str(exc),
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise TtsError(
                ErrorKind.REQUEST_ERROR, f"Lỗi request tại {label}: {exc}", str(exc)
            ) from exc

        if resp.status_code >= 400:
            raise http_error(resp, label)

        marker = shark_marker(resp.text)
        if marker:
            raise TtsError(
                ErrorKind.SHARK_BLOCK,
                f"Bị chặn bởi hệ thống bảo vệ (shark/captcha) tại {label}",
                f"Dấu hiệu: '{marker}'. Body: {(resp.text or '')[:400]}",
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise TtsError(
                ErrorKind.BAD_RESPONSE,
                f"{label} trả về nội dung không phải JSON (HTTP {resp.status_code})",
                (resp.text or "")[:400],
            ) from exc

        if not isinstance(data, dict):
            raise TtsError(
                ErrorKind.BAD_RESPONSE,
                f"{label} trả về JSON không đúng định dạng",
                str(data)[:400],
            )
        return data

    def _post_with_backoff(
        self,
        build: Callable[[], Tuple[str, Dict[str, str], str]],
        read_timeout: float,
        label: str,
        cancel: CancelToken,
        on_retry: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """
        Gui POST, rieng HTTP 429 thi backoff va thu lai toi da RATE_LIMIT_MAX_RETRIES lan.

        `build` duoc goi lai moi lan thu de request duoc KY LAI (chu ky co chua
        device-time nen khong the dung lai chu ky cu sau khi cho lau).
        """
        attempts = 0
        last_error: Optional[TtsError] = None

        while attempts <= RATE_LIMIT_MAX_RETRIES:
            cancel.raise_if_set()
            attempts += 1
            url, headers, body_text = build()
            try:
                return self._post_once(url, headers, body_text, read_timeout, label), attempts
            except TtsError as exc:
                if exc.kind != ErrorKind.HTTP_429 or attempts > RATE_LIMIT_MAX_RETRIES:
                    raise
                last_error = exc
                index = min(attempts - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                delay = RATE_LIMIT_BACKOFF_SECONDS[index]
                if on_retry:
                    on_retry(
                        f"HTTP 429 tại {label} — chờ {delay:.0f}s rồi thử lại "
                        f"(lần {attempts}/{RATE_LIMIT_MAX_RETRIES})"
                    )
                if cancel.wait(delay):
                    raise StopRequested() from exc

        raise last_error or TtsError(ErrorKind.HTTP_429, f"HTTP 429 tại {label}")

    # -- doc phan hoi tao task ------------------------------------------------

    @staticmethod
    def extract_created_task(data: Dict[str, Any]) -> Tuple[str, str, str]:
        """Lay task_id / token / bind_id tu phan hoi tao task."""
        ret = str(data.get("ret", "0"))
        errmsg = str(data.get("errmsg", ""))
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        tasks = (payload or {}).get("tasks") or []

        if not tasks:
            if ret not in ("0", ""):
                raise TtsError(
                    ErrorKind.API_ERROR,
                    f"API báo lỗi khi tạo task (ret={ret}): {errmsg or 'không có thông báo'}",
                    json.dumps(data, ensure_ascii=False)[:600],
                )
            raise TtsError(
                ErrorKind.NO_TASK,
                "API không trả về task nào cho yêu cầu TTS",
                json.dumps(data, ensure_ascii=False)[:600],
            )

        task = tasks[0] or {}
        task_id = task.get("id")
        token = task.get("token")
        if not task_id or not token:
            missing = "id" if not task_id else "token"
            raise TtsError(
                ErrorKind.TASK_MISSING_FIELDS,
                f"Task thiếu {missing} — không thể theo dõi tiến trình",
                json.dumps(task, ensure_ascii=False)[:600],
            )
        return str(task_id), str(token), str(task.get("bind_id") or "")

    # -- tai audio ------------------------------------------------------------

    def download_audio(self, url: str, dest: Path, cancel: CancelToken) -> int:
        """Tai file audio ve dia, tra ve so byte da ghi."""
        dest = Path(dest)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with self.session.get(
                url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT_DOWNLOAD), stream=True
            ) as resp:
                if resp.status_code >= 400:
                    raise http_error(resp, "tải audio")
                total = 0
                with open(tmp, "wb") as fp:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if cancel.is_set():
                            raise StopRequested()
                        if chunk:
                            fp.write(chunk)
                            total += len(chunk)
            if total == 0:
                raise TtsError(ErrorKind.EMPTY_AUDIO, "File audio tải về rỗng (0 byte)")
            tmp.replace(dest)
            return total
        except StopRequested:
            tmp.unlink(missing_ok=True)
            raise
        except TtsError:
            tmp.unlink(missing_ok=True)
            raise
        except requests.exceptions.ConnectTimeout as exc:
            tmp.unlink(missing_ok=True)
            raise TtsError(
                ErrorKind.CONNECT_TIMEOUT,
                f"ConnectTimeout khi tải audio: không kết nối được trong {CONNECT_TIMEOUT:.0f}s",
                str(exc),
            ) from exc
        except requests.exceptions.ReadTimeout as exc:
            tmp.unlink(missing_ok=True)
            raise TtsError(
                ErrorKind.READ_TIMEOUT,
                f"ReadTimeout khi tải audio: quá {READ_TIMEOUT_DOWNLOAD:.0f}s không nhận được dữ liệu",
                str(exc),
            ) from exc
        except requests.exceptions.RequestException as exc:
            tmp.unlink(missing_ok=True)
            raise TtsError(
                ErrorKind.DOWNLOAD_ERROR, f"Lỗi mạng khi tải audio: {exc}", str(exc)
            ) from exc
        except OSError as exc:
            raise TtsError(
                ErrorKind.DISK_ERROR, f"Không ghi được file audio: {exc}", str(exc)
            ) from exc

    # -- tao audio cho mot part ----------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: VoiceEntry,
        dest: Path,
        cancel: CancelToken,
        rate: str = "1.0",
        progress: Optional[Callable[[str], None]] = None,
    ) -> PartResult:
        """
        Tao task -> poll trang thai -> tai MP3 cho MOT part.

        Nem TtsError (da phan loai) hoac StopRequested.
        """
        def notify(message: str) -> None:
            if progress:
                progress(message)

        if not (text or "").strip():
            raise TtsError(ErrorKind.EMPTY_TEXT, "Phần văn bản này rỗng")

        cancel.raise_if_set()
        client = self.client

        notify("Đang tạo task TTS...")
        create_data, attempts = self._post_with_backoff(
            build=lambda: client.build_tts_new_request(
                texts=text, voice=voice.voice_type, resource_id=voice.resource_id or None, rate=rate
            ),
            read_timeout=READ_TIMEOUT_CREATE,
            label="tạo task",
            cancel=cancel,
            on_retry=notify,
        )
        task_id, token, bind_id = self.extract_created_task(create_data)

        cancel.raise_if_set()
        notify(f"Đã tạo task, đang chờ xử lý...")

        deadline_wait = POLL_TOTAL_SECONDS
        import time as _time

        deadline = _time.monotonic() + deadline_wait
        poll_count = 0
        last_status = "(chưa có)"
        audio_url: Optional[str] = None

        while True:
            cancel.raise_if_set()
            poll_count += 1

            query_data, query_attempts = self._post_with_backoff(
                build=lambda: client.build_query_request(
                    task_id, token, mode="tts", bind_id=bind_id
                ),
                read_timeout=READ_TIMEOUT_QUERY,
                label="kiểm tra task",
                cancel=cancel,
                on_retry=notify,
            )
            attempts += query_attempts

            payload = query_data.get("data") if isinstance(query_data.get("data"), dict) else {}
            q_tasks = (payload or {}).get("tasks") or []
            if q_tasks:
                task = q_tasks[0] or {}
                raw_status = task.get("status")
                status = str(raw_status).strip().lower() if raw_status is not None else ""
                last_status = status or "(rỗng)"

                if status in DONE_STATUSES:
                    task_payload = decode_payload(task)
                    audio_url = find_audio_url(task_payload)
                    if not audio_url:
                        detail = (
                            task_payload[:800]
                            if isinstance(task_payload, str)
                            else json.dumps(task_payload, ensure_ascii=False)[:800]
                        )
                        raise TtsError(
                            ErrorKind.NO_AUDIO_URL,
                            f"Task báo thành công ({status}) nhưng không tìm thấy URL audio",
                            detail,
                        )
                    break

                if status in FAILED_STATUSES:
                    message = (
                        task.get("message") or task.get("err_msg") or task.get("errmsg") or ""
                    )
                    raise TtsError(
                        ErrorKind.TASK_FAILED,
                        f"Task thất bại với trạng thái '{status}'"
                        + (f": {message}" if message else ""),
                        json.dumps(task, ensure_ascii=False)[:600],
                    )

            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                raise TtsError(
                    ErrorKind.POLL_TIMEOUT,
                    f"Hết {POLL_TOTAL_SECONDS:.0f}s chờ xử lý, trạng thái cuối: '{last_status}'",
                    f"task_id={task_id}, số lần kiểm tra={poll_count}",
                )

            notify(
                f"Đang xử lý (trạng thái: {last_status}, lần kiểm tra {poll_count}, "
                f"còn {remaining:.0f}s)..."
            )
            if cancel.wait(min(POLL_INTERVAL_SECONDS, max(0.1, remaining))):
                raise StopRequested()

        notify("Đang tải file MP3...")
        size = self.download_audio(audio_url, dest, cancel)

        return PartResult(
            file_path=str(dest),
            file_size=size,
            task_id=task_id,
            token_masked=mask_secret(token),
            audio_host=safe_url_label(audio_url),
            attempts=attempts,
        )

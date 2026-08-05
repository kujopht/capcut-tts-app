"""
Doi tuong gia lap dung chung cho test — khong bao gio goi mang thuc.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from desktop_app.models import ErrorKind, VoiceEntry
from desktop_app.tts_service import PartResult, StopRequested, TtsError

FAKE_MP3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 4096


class FakeResponse:
    """Gia lap requests.Response."""

    def __init__(
        self,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        content: bytes = b"",
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {}, ensure_ascii=False)
        self._content = content

    def json(self) -> Dict[str, Any]:
        if self._payload is None:
            raise ValueError("không phải JSON")
        return self._payload

    def iter_content(self, chunk_size: int = 1):
        for i in range(0, len(self._content), max(1, chunk_size)):
            yield self._content[i:i + chunk_size]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


class FakeSession:
    """
    Gia lap requests.Session.

    `post_script` / `get_script` la danh sach phan hoi (hoac Exception de nem).
    Phan tu cuoi duoc dung lai neu bi goi nhieu hon so phan tu.
    """

    def __init__(
        self,
        post_script: Optional[Sequence[Any]] = None,
        get_script: Optional[Sequence[Any]] = None,
    ):
        self.post_script = list(post_script or [])
        self.get_script = list(get_script or [FakeResponse(200, None, "", FAKE_MP3)])
        self.post_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.closed = False

    @staticmethod
    def _take(script: List[Any], index: int) -> Any:
        if not script:
            raise AssertionError("script rỗng")
        item = script[min(index, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, headers=None, data=None, timeout=None, **kwargs):
        index = len(self.post_calls)
        self.post_calls.append({"url": url, "timeout": timeout, "headers": headers})
        return self._take(self.post_script, index)

    def get(self, url, timeout=None, stream=None, **kwargs):
        index = len(self.get_calls)
        self.get_calls.append({"url": url, "timeout": timeout})
        return self._take(self.get_script, index)

    def close(self) -> None:
        self.closed = True


class FakeCapCutClient:
    """
    Gia lap CapCutClient: chi tra ve (url, headers, body) gia.
    Dung de test tang HTTP ma khong phai ky RSA that.
    """

    def __init__(self):
        self.tts_calls: List[Dict[str, Any]] = []
        self.query_calls: List[Dict[str, Any]] = []

    def build_tts_new_request(self, texts=None, voice=None, resource_id=None, rate="1.0"):
        self.tts_calls.append(
            {"texts": texts, "voice": voice, "resource_id": resource_id, "rate": rate}
        )
        return ("https://fake/lv/v1/common_task/new", {"sign": "x"}, '{"fake":"new"}')

    def build_query_request(self, task_id, token, mode="tts", bind_id=""):
        self.query_calls.append({"task_id": task_id, "token": token, "bind_id": bind_id})
        return ("https://fake/lv/v1/common_task/query", {"sign": "x"}, '{"fake":"query"}')


def created_response(task_id: str = "task-1234567890", token: str = "tok-secret-value",
                     bind_id: str = "bind-1") -> FakeResponse:
    return FakeResponse(
        200,
        {
            "ret": "0",
            "errmsg": "success",
            "data": {"tasks": [{"id": task_id, "token": token, "bind_id": bind_id}]},
        },
    )


def query_response(status: str, url: Optional[str] = "https://cdn.fake/a/out.mp3") -> FakeResponse:
    payload: Dict[str, Any] = {"tts_url": url} if url else {"duration_ms": 1200}
    return FakeResponse(
        200,
        {
            "ret": "0",
            "data": {
                "tasks": [
                    {
                        "id": "task-1234567890",
                        "status": status,
                        "payload": json.dumps(payload, ensure_ascii=False),
                    }
                ]
            },
        },
    )


# -----------------------------------------------------------------------------
# TtsService gia lap (dung cho test hang doi)
# -----------------------------------------------------------------------------


class StubTtsService:
    """
    Thay the TtsService trong test hang doi.

    - `behaviour`: callable(part_text, call_index) -> None de thanh cong,
       hoac nem TtsError/StopRequested de mo phong loi.
    - `delay`: thoi gian gia lap moi part (giu that nho trong test).
    """

    def __init__(self, behaviour=None, delay: float = 0.0, write_file: bool = True):
        self.behaviour = behaviour
        self.delay = delay
        self.write_file = write_file
        self.calls: List[str] = []
        self.closed = False
        self.lock = threading.Lock()

    def synthesize(self, text, voice: VoiceEntry, dest, cancel, rate="1.0", progress=None):
        with self.lock:
            index = len(self.calls)
            self.calls.append(text)

        if progress:
            progress("stub: đang tạo task")

        if self.delay:
            if cancel.wait(self.delay):
                raise StopRequested()

        if self.behaviour is not None:
            self.behaviour(text, index)

        cancel.raise_if_set()

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.write_file:
            dest.write_bytes(FAKE_MP3)
        size = dest.stat().st_size if dest.is_file() else 0
        return PartResult(
            file_path=str(dest),
            file_size=size,
            task_id=f"stub-task-{index}",
            token_masked="tok…(đã che)",
            audio_host="cdn.fake/a/out.mp3",
            attempts=1,
        )

    def close(self) -> None:
        self.closed = True


def make_voice(
    voice_type: str = "BV421_vivn_streaming",
    display_name: str = "Nhỏ Ngọt Ngào",
    resource_id: str = "7252594014782755330",
    lang: str = "vi-VN",
    lan: str = "vi",
) -> VoiceEntry:
    return VoiceEntry(
        voice_type=voice_type,
        display_name=display_name,
        resource_id=resource_id,
        lang=lang,
        lan=lan,
    )


def fail_with(kind: ErrorKind, message: str = "lỗi giả lập"):
    """Tao behaviour luon nem TtsError."""

    def behaviour(text, index):
        raise TtsError(kind, message)

    return behaviour


def fail_part(part_number: int, kind: ErrorKind, message: str = "lỗi giả lập"):
    """Behaviour: chi part thu `part_number` (1-based theo thu tu goi) that bai."""

    def behaviour(text, index):
        if index + 1 == part_number:
            raise TtsError(kind, message)

    return behaviour

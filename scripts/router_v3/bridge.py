"""Cầu nối worker chạy TRONG phiên Windows đã đăng nhập — Router V3.2, Phase 4.

BÀI TOÁN: Router chạy trong phiên của người dùng chính. AG02 là một tài khoản
Google KHÁC, đã đăng nhập trong một hồ sơ Windows KHÁC. Router **không thể** và
**không được** chạy tiến trình dưới danh nghĩa người dùng đó — làm vậy cần mật
khẩu của họ.

CÁCH GIẢI: đảo chiều quyền sở hữu. Người dùng AG02 tự đăng nhập, tự chạy cầu
nối này TRONG phiên của mình. Cầu nối sở hữu tiến trình `agy` đã xác thực.
Router chỉ gửi **gói việc** và nhận **kết quả** qua localhost.

Router KHÔNG BAO GIỜ nhận: mật khẩu Windows, mật khẩu Google, OAuth token,
cookie, refresh token, hay bản xuất Credential Manager. Giao thức chỉ mang
văn bản việc và văn bản kết quả.

BÍ MẬT CỦA CẦU NỐI ≠ CREDENTIAL CỦA NHÀ CUNG CẤP. Cầu nối tự sinh một token
ngẫu nhiên và IN RA màn hình của chính nó để người vận hành chép sang Router.
Token đó chỉ cho phép **gửi việc**; nó không mở được gì thuộc về Google. Router
cầm nó là hợp lệ, cầm OAuth token thì không.

Chỉ nghe trên 127.0.0.1 — KHÔNG BAO GIỜ mở cổng ra mạng ngoài.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import socketserver
import threading
from dataclasses import dataclass
from typing import Callable, Optional

#: Trần kích thước một bản tin. Không có trần thì một client hỏng (hoặc cố ý)
#: có thể ép cầu nối cấp phát bộ nhớ vô hạn.
MAX_MESSAGE_BYTES = 1_000_000

LOOPBACK = "127.0.0.1"


def _doc_dong(sock: socket.socket) -> Optional[bytes]:
    """Đọc MỘT dòng, có trần.

    Đọc theo KHỐI, không theo từng byte: bản đầu tiên gọi `recv(1)` trong vòng
    lặp, nên một bản tin 1 MB thành một triệu lệnh gọi hệ thống và bài kiểm
    thử "bản tin khổng lồ" treo luôn. Đọc khối vừa nhanh vừa giữ nguyên trần.
    """
    buf = bytearray()
    while len(buf) <= MAX_MESSAGE_BYTES:
        khoi = sock.recv(65536)
        if not khoi:
            return None                   # phia kia dong truoc khi het dong
        buf += khoi
        vt = buf.find(b"\n")
        if vt >= 0:
            return bytes(buf[:vt])
    return None                           # vuot tran -> bo


@dataclass
class BridgeConfig:
    worker_id: str = "AG02"
    port: int = 0                     # 0 = HDH tu chon cong ranh
    token: str = ""                   # rong = tu sinh


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        srv = self.server                                   # type: ignore[assignment]
        raw = _doc_dong(self.request)
        if raw is None:
            return
        try:
            msg = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            self._tra({"status": "error", "error": "bản tin không phải JSON"})
            return

        # So sanh token bang `compare_digest` — so bang `==` de lo do dai
        # khop den dau qua thoi gian.
        if not hmac.compare_digest(str(msg.get("token") or ""), srv.token):
            self._tra({"status": "error", "error": "token không hợp lệ"})
            return

        loai = str(msg.get("op") or "")
        if loai == "health":
            dap = {"status": "ok", "worker_id": srv.worker_id,
                  "healthy": srv.health_fn()}
            if srv.state_fn is not None:
                dap["state"] = srv.state_fn()
            self._tra(dap)
            return
        if loai == "run":
            prompt = str(msg.get("prompt") or "")
            family = str(msg.get("family") or "")
            if not prompt:
                self._tra({"status": "error", "error": "thiếu prompt"})
                return
            try:
                kq = srv.run_fn(prompt, family)
            except Exception as exc:                        # noqa: BLE001
                self._tra({"status": "error",
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
                return
            self._tra({"status": "ok", **kq})
            return
        self._tra({"status": "error", "error": f"op lạ: {loai!r}"})

    def _tra(self, d: dict) -> None:
        try:
            self.request.sendall((json.dumps(d, ensure_ascii=False) + "\n")
                                 .encode("utf-8"))
        except OSError:
            pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, cfg: BridgeConfig, run_fn, health_fn, state_fn=None):
        # CHI 127.0.0.1. Bind 0.0.0.0 se mo cau noi ra ca mang LAN.
        super().__init__((LOOPBACK, cfg.port), _Handler)
        self.worker_id = cfg.worker_id
        self.token = cfg.token or secrets.token_urlsafe(32)
        self.run_fn = run_fn
        self.health_fn = health_fn
        self.state_fn = state_fn


class WorkerBridge:
    """Chạy TRONG phiên Windows của AG02, cạnh tiến trình `agy` đã xác thực."""

    def __init__(self, cfg: BridgeConfig, run_fn: Callable[[str, str], dict],
                 health_fn: Callable[[], bool] = lambda: True,
                 state_fn: Optional[Callable[[], str]] = None):
        """
        :param state_fn: nếu có, giá trị của nó (vd "warm_idle") đi kèm phản
            hồi "health" dưới khoá `state` — cho phép Router phân biệt
            KHOẺ-NHƯNG-BẬN với KHOẺ-VÀ-SẴN-SÀNG thay vì chỉ true/false.
        """
        self._srv = _Server(cfg, run_fn, health_fn, state_fn)
        self._t: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._srv.server_address[1]

    @property
    def token(self) -> str:
        return self._srv.token

    @property
    def worker_id(self) -> str:
        return self._srv.worker_id

    def start(self) -> None:
        if self._t is not None:
            return                        # da chay roi — khong dung hai vong
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()

    def stop(self) -> None:
        """Dừng cầu nối. An toàn cả khi CHƯA từng `start()`.

        `shutdown()` CHẶN VÔ HẠN nếu `serve_forever()` chưa từng chạy — nó đợi
        một vòng lặp không tồn tại báo đã dừng. Một cầu nối được dựng rồi bỏ
        (ví dụ trong một bài kiểm thử chỉ đọc `token`) sẽ treo luôn ở đây.
        Đã vấp thật.
        """
        if self._t is not None:
            self._srv.shutdown()
            self._t = None
        self._srv.server_close()


class BridgeClient:
    """Phía Router. Chỉ gửi việc, chỉ nhận kết quả."""

    def __init__(self, port: int, token: str, *, timeout: float = 300.0,
                 host: str = LOOPBACK):
        self._port = port
        self._token = token
        self._timeout = timeout
        self._host = host

    def _goi(self, payload: dict) -> dict:
        try:
            with socket.create_connection((self._host, self._port),
                                          timeout=self._timeout) as s:
                s.settimeout(self._timeout)
                s.sendall((json.dumps({**payload, "token": self._token},
                                      ensure_ascii=False) + "\n").encode("utf-8"))
                raw = _doc_dong(s)
        except OSError as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        if raw is None:
            return {"status": "error", "error": "cầu nối không trả lời"}
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return {"status": "error", "error": "trả lời không phải JSON"}

    def health(self) -> dict:
        return self._goi({"op": "health"})

    def run(self, prompt: str, family: str = "") -> dict:
        return self._goi({"op": "run", "prompt": prompt, "family": family})

"""Cầu nối worker Antigravity native — Router V3.1, Phase 2 + 3.

Dùng chế độ headless CHÍNH THỨC của `agy` (`--output-format json`), nên đo
tách bạch được **độ trễ model** với **thời gian dựng tiến trình** — hai thứ
mà một phép đo wall-clock trần gộp làm một.

GIỚI HẠN ĐÃ ĐO ĐƯỢC (2026-08-30) — `agy --print` KHÔNG THỰC THI CÔNG CỤ SỬA TỆP.

Đo trực tiếp, ba cấu hình, trong thư mục tạm sạch:

    không cờ            -> status=SUCCESS, num_turns=1, KHÔNG tạo tệp
    --mode accept-edits -> status=SUCCESS, num_turns=1, KHÔNG tạo tệp
    --dangerously-skip-permissions -> status=SUCCESS, trả lời "XONG.",
                           num_turns=1, VẪN KHÔNG tạo tệp

`num_turns=1` nghĩa là không hề có vòng gọi công cụ nào. Nguy hiểm ở chỗ nó
**trả lời như thể đã làm** — nên một bộ điều phối tin vào `status` sẽ ghi nhận
thành công cho một việc chưa từng xảy ra. Chính vì vậy mọi nút CÓ GHI phải
được kiểm bằng `WorktreeManager.verify_scope()` trên tệp THẬT, chứ không bao
giờ tin lời worker.

Hệ quả: worker Antigravity native qua giao diện headless chính thức dùng được
cho ĐỌC/PHÂN TÍCH/REVIEW (đã chứng minh), KHÔNG dùng được cho việc tự sửa tệp.
Nút CÓ GHI cần một executor khác.

RANH GIỚI CREDENTIAL — bất biến:
Module này KHÔNG BAO GIỜ đọc, sao chép, hay truyền credential. `agy` tự giữ
phiên đăng nhập trong hồ sơ người dùng của chính nó
(`~/.gemini/antigravity-cli/`) và trong keyring của HĐH. Router chỉ trao đổi
**gói việc và kết quả**. Không xoay tài khoản, không né giới hạn.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_AGY = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"


def find_agy() -> Optional[str]:
    tren_path = shutil.which("agy")
    if tren_path:
        return tren_path
    for ung_vien in (DEFAULT_AGY, DEFAULT_AGY.with_suffix("")):
        if ung_vien.exists():
            return str(ung_vien)
    return None


@dataclass
class NativeRun:
    """Một lần chạy, tách bạch từng phần thời gian.

    `model_seconds` do CHÍNH `agy` báo; `overhead_seconds` là phần còn lại —
    dựng tiến trình, nạp CLI, đọc/ghi ống. Tách ra vì chúng cải thiện được
    theo hai cách hoàn toàn khác nhau: một cái là chọn model, cái kia là gộp
    nhiều việc vào một tiến trình.
    """

    ok: bool = False
    status: str = ""
    response: str = ""
    wall_seconds: float = 0.0
    model_seconds: float = 0.0
    num_turns: int = 0
    usage: Dict[str, int] = field(default_factory=dict)
    error: str = ""

    @property
    def overhead_seconds(self) -> float:
        return round(max(0.0, self.wall_seconds - self.model_seconds), 3)

    @property
    def overhead_ratio(self) -> float:
        return round(self.overhead_seconds / self.wall_seconds, 3) if self.wall_seconds else 0.0


def run_native(prompt: str, *, model: str, timeout: int = 300,
               cwd: Optional[str] = None,
               binary: Optional[str] = None,
               allow_edits: bool = False) -> NativeRun:
    """Chạy MỘT lượt qua `agy` headless và tách bạch các phần thời gian.

    Prompt đi qua **stdin**, không phải argv: một gói việc thật dễ vượt giới
    hạn ~32 KB của dòng lệnh Windows, và argv sẽ cắt cụt hoặc lỗi.

    :param allow_edits: bật `--mode accept-edits`. MẶC ĐỊNH TẮT: một worker
        chỉ-đọc không được có quyền ghi. Không có cờ này, `agy` **không sửa
        được tệp nào** — đo được thật: một lượt "hai worker ghi" trả về 0/2
        vì worker không có quyền ghi, và nếu không kiểm từng tệp thì con số
        wall-clock trông vẫn "hợp lý" mà hoàn toàn vô nghĩa.

        CỐ Ý KHÔNG dùng `--dangerously-skip-permissions`: nó tự duyệt MỌI
        yêu cầu quyền, gồm cả chạy lệnh shell. `accept-edits` chỉ mở phần
        sửa tệp — đúng thứ một nút CÓ GHI cần, không hơn.
    """
    exe = binary or find_agy()
    if not exe:
        return NativeRun(status="unavailable", error="không tìm thấy agy")

    argv = [exe, "--model", model, "--output-format", "json",
            "--print-timeout", f"{timeout}s"]
    if allow_edits:
        argv += ["--mode", "accept-edits"]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                           timeout=timeout + 30, cwd=cwd, encoding="utf-8",
                           errors="replace")
    except subprocess.TimeoutExpired:
        return NativeRun(status="timeout", wall_seconds=round(time.perf_counter() - t0, 3),
                         error=f"vượt {timeout}s")
    wall = round(time.perf_counter() - t0, 3)

    raw = (p.stdout or "").strip()
    if p.returncode != 0 and not raw:
        return NativeRun(status="failed", wall_seconds=wall,
                         error=(p.stderr or "")[-300:])
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        # Khong doc duoc JSON la THAT BAI, khong bao gio la thanh cong voi du
        # lieu bia — xem cung nguyen tac o `packet.parse_result`.
        return NativeRun(status="failed", wall_seconds=wall,
                         error=f"đầu ra không phải JSON: {raw[:200]}")

    tt = str(d.get("status") or "").upper()
    return NativeRun(
        ok=(tt == "SUCCESS"), status=tt,
        response=str(d.get("response") or ""),
        wall_seconds=wall,
        model_seconds=round(float(d.get("duration_seconds") or 0.0), 3),
        num_turns=int(d.get("num_turns") or 0),
        usage={k: int(v) for k, v in (d.get("usage") or {}).items()
               if isinstance(v, (int, float))},
        error="" if tt == "SUCCESS" else str(d.get("error") or tt))

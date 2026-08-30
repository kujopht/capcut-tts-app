"""Cầu nối worker Antigravity native — Router V3.1, Phase 2 + 3.

Dùng chế độ headless CHÍNH THỨC của `agy` (`--output-format json`), nên đo
tách bạch được **độ trễ model** với **thời gian dựng tiến trình** — hai thứ
mà một phép đo wall-clock trần gộp làm một.

GHI TỆP HEADLESS — HOẠT ĐỘNG. (Sửa lại một kết luận SAI trước đó.)

Một bản ghi chú trước trong tệp này khẳng định `agy --print` "không thực thi
công cụ sửa tệp". Điều đó **SAI**, và nó sai vì phép đo hỏng theo hai cách
cùng lúc:

  1. Chạy trong một thư mục tạm TRẦN, không có `--add-dir`. `agy` có khái
     niệm WORKSPACE tách khỏi cwd, nên `write_file` không có đích hợp lệ.
  2. KHÔNG đọc stderr. Câu trả lời nằm nguyên ở đó:

        "a tool required the \"write_file\" permission that headless mode
         cannot prompt for, so it was auto-denied"

Công cụ CÓ chạy — nó bị TỪ CHỐI QUYỀN, không phải vắng mặt. Chế độ headless
không hỏi được nên tự động từ chối.

Đo lại trong một `git worktree` thật kèm `--add-dir` (tệp thật, nội dung
kiểm từng byte):

    không cờ                        -> KHÔNG ghi (tự động từ chối)
    --mode accept-edits             -> GHI ĐƯỢC, nội dung đúng
    --dangerously-skip-permissions  -> GHI ĐƯỢC, nội dung đúng

Bài học rút ra đáng giữ hơn kết luận: `status=SUCCESS` kèm `num_turns=1` và
một câu trả lời tự tin KHÔNG phải bằng chứng thực thi. Bằng chứng là tệp trên
đĩa. Đó vẫn là lý do mọi nút CÓ GHI phải qua `verify_scope()`.

`--add-dir` là BẮT BUỘC cho việc có ghi: thiếu nó, worker im lặng không làm gì.

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
               allow_edits: bool = False,
               workspace: Optional[str] = None) -> NativeRun:
    """Chạy MỘT lượt qua `agy` headless và tách bạch các phần thời gian.

    Prompt đi qua **stdin**, không phải argv: một gói việc thật dễ vượt giới
    hạn ~32 KB của dòng lệnh Windows, và argv sẽ cắt cụt hoặc lỗi.

    :param allow_edits: bật `--mode accept-edits`. MẶC ĐỊNH TẮT: một worker
        chỉ-đọc không được có quyền ghi. Thiếu cờ này, headless **tự động từ
        chối** quyền `write_file` (nó không hỏi được) và worker im lặng không
        làm gì.

        CỐ Ý KHÔNG dùng `--dangerously-skip-permissions`: nó tự duyệt MỌI
        yêu cầu quyền, gồm cả chạy lệnh shell. `accept-edits` đủ để ghi tệp —
        đã đo — và đó là đúng thứ một nút CÓ GHI cần, không hơn.

    :param workspace: thư mục đưa vào WORKSPACE qua `--add-dir`. BẮT BUỘC khi
        `allow_edits=True`: `agy` phân biệt workspace với cwd, và thiếu nó thì
        `write_file` không có đích hợp lệ. Bỏ sót đúng điểm này là lý do một
        phép đo trước kết luận nhầm rằng headless không ghi được.
    """
    if allow_edits and not workspace:
        return NativeRun(
            status="failed",
            error="allow_edits=True nhưng thiếu `workspace` — `--add-dir` là "
                  "bắt buộc cho việc có ghi, nếu không worker im lặng không "
                  "làm gì.")
    exe = binary or find_agy()
    if not exe:
        return NativeRun(status="unavailable", error="không tìm thấy agy")

    argv = [exe, "--model", model, "--output-format", "json",
            "--print-timeout", f"{timeout}s"]
    if workspace:
        argv += ["--add-dir", str(workspace)]
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


# ---------------------------------------------------------------------------
# Worker ẤM — một tiến trình, nhiều lượt
# ---------------------------------------------------------------------------

#: Hình dạng bản tin đầu vào cho `--input-format stream-json`.
#:
#: PHẢI có trường `event` (không phải `type`) và, với `event="user"`, phải có
#: `message`. Sai hình dạng thì CLI trả `status=ERROR` kèm đúng lý do — đã dò
#: từng dạng để tìm ra cái đúng:
#:     {"event":"user","message":{"role":"user","content":"..."}}
def _ban_tin(prompt: str) -> str:
    return json.dumps({"event": "user",
                       "message": {"role": "user", "content": prompt}})


@dataclass
class WarmResult:
    """Kết quả của MỘT lượt trong tiến trình ấm."""

    ok: bool
    response: str = ""
    error: str = ""


def run_warm_batch(prompts, *, model: str, timeout: int = 900,
                   cwd: Optional[str] = None,
                   binary: Optional[str] = None):
    """Chạy NHIỀU lượt trong MỘT tiến trình `agy`.

    VÌ SAO ĐÁNG LÀM — đo được (10 việc nhỏ, 10/10 thành công cả hai cách):

        sinh mới một tiến trình mỗi việc : 59.10s  (5.91s/việc, 77% là overhead)
        một tiến trình ấm                : 16.31s  (1.63s/việc)
        => nhanh hơn 3.62 lần

    Đây là khoản lợi LỚN HƠN việc thêm worker (đo trước đó: 2.19x ở 6 worker),
    và hai thứ này cộng dồn được: nhiều worker ấm chạy song song.

    ĐÁNH ĐỔI PHẢI BIẾT: cả lô dùng CHUNG một hội thoại, nên ngữ cảnh tích luỹ
    qua từng lượt. Với các việc ĐỘC LẬP thì đó là token lãng phí và có thể làm
    lượt sau nhiễu. Chỉ gộp những việc thật sự cùng một mạch, và giữ lô nhỏ.

    KHÔNG đọc `duration_seconds` của từng lượt ở chế độ này để suy ra độ trễ
    model: đo được nó là thời gian hội thoại TÍCH LUỸ (tổng 65.35s trong một
    lượt chạy chỉ mất 16.31s), nên trừ ra sẽ cho "overhead âm" vô nghĩa.
    """
    exe = binary or find_agy()
    if not exe:
        return [WarmResult(ok=False, error="không tìm thấy agy") for _ in prompts]

    argv = [exe, "--model", model, "--input-format", "stream-json",
            "--output-format", "stream-json", "--print-timeout", f"{timeout}s"]
    data = "".join(_ban_tin(p) + "\n" for p in prompts)
    try:
        p = subprocess.run(argv, input=data, capture_output=True, text=True,
                           timeout=timeout + 60, cwd=cwd, encoding="utf-8",
                           errors="replace")
    except subprocess.TimeoutExpired:
        return [WarmResult(ok=False, error=f"vượt {timeout}s") for _ in prompts]

    ra = []
    for dong in (p.stdout or "").splitlines():
        dong = dong.strip()
        if not dong.startswith("{"):
            continue
        try:
            o = json.loads(dong)
        except json.JSONDecodeError:
            continue
        if o.get("event") != "result":
            continue
        r = o.get("result") or {}
        ra.append(WarmResult(ok=(str(r.get("status")).upper() == "SUCCESS"),
                             response=str(r.get("response") or ""),
                             error=str(r.get("error") or "")))
    # Thieu ket qua = lo bi cat giua chung. KHONG im lang tra ve it hon so
    # viec da gui: noi goi se ghep nham ket qua voi viec.
    while len(ra) < len(prompts):
        ra.append(WarmResult(ok=False, error="không nhận được kết quả cho lượt này"))
    return ra[:len(prompts)]

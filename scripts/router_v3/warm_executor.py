"""Worker ấm làm executor CHÍNH THỨC của Scheduler — Router V3.2, Phase 1 + 3.

Trước module này, `WarmPool` chỉ là một thứ đứng riêng: có đo được lợi ích
(1.45s/lượt so với 5.91s mỗi lần sinh mới) nhưng bộ lập lịch không dùng tới
nó, nên trên thực tế mọi nút vẫn sinh một tiến trình mới. Đây là chỗ nối hai
thứ đó lại.

THỨ TỰ CHỌN (Phase 3), theo đúng thứ tự này:

    1. worker ẤM-RẢNH hợp việc (không phải tái tạo)  -> rẻ nhất
    2. worker ẤM-RẢNH nhưng phải tái tạo             -> ~4s
    3. sinh LẠNH một tiến trình mới                  -> ~5-6s
    4. không có gì -> hỏng RÕ RÀNG, không im lặng

"Đang ấm" KHÔNG BAO GIỜ thắng "hợp năng lực". Việc chọn worker theo năng lực
và rủi ro vẫn do `policy.choose_worker` quyết định TRƯỚC; ở đây chỉ chọn xem
DÙNG LẠI tiến trình nào cho worker đã được chọn. Đổi thứ tự đó sẽ tiết kiệm
được vài giây và đánh mất ranh giới rủi ro — một đổi chác tồi.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.router_v3.packet import TaskPacket
from scripts.router_v3.registry import WorkerSpec
from scripts.router_v3.warm_pool import (RecyclePolicy, WarmAgyWorker, WarmState)


@dataclass
class WarmMetrics:
    """Số đo để trả lời "worker ấm có thật sự giúp không"."""

    cold_starts: int = 0
    cold_start_seconds: float = 0.0
    warm_dispatches: int = 0
    warm_seconds: float = 0.0
    recycles: int = 0
    failures: int = 0

    @property
    def avg_warm_seconds(self) -> float:
        return round(self.warm_seconds / self.warm_dispatches, 3) \
            if self.warm_dispatches else 0.0

    @property
    def cold_starts_avoided(self) -> int:
        """Số lần lẽ ra phải dựng tiến trình mới nhưng đã dùng lại được.

        Đây mới là con số nói lên giá trị của bể ấm — không phải tổng số lượt.
        """
        return max(0, self.warm_dispatches - self.cold_starts)

    def snapshot(self) -> dict:
        return {
            "cold_starts": self.cold_starts,
            "cold_start_seconds": round(self.cold_start_seconds, 2),
            "warm_dispatches": self.warm_dispatches,
            "avg_warm_seconds": self.avg_warm_seconds,
            "cold_starts_avoided": self.cold_starts_avoided,
            "recycles": self.recycles,
            "failures": self.failures,
        }


def family_of(packet: TaskPacket) -> str:
    """Suy ra "họ việc" để quyết định có dùng lại ngữ cảnh hay không.

    Dùng THƯ MỤC GỐC của phạm vi ghi/đọc, không dùng `task_id`: hai nút cùng
    sửa `server/scraper` là cùng một mạch việc dù id khác nhau, còn hai nút
    cùng tên tiền tố mà đụng hai hệ con khác nhau thì không.
    """
    duong = list(packet.write_scope) or list(packet.read_scope)
    if not duong:
        return ""
    phan = [p for p in duong[0].replace("\\", "/").strip("/").split("/") if p]
    if not phan:
        return ""
    # Hai muc dau la du: `server/scraper/a.py` va `server/scraper/b.py` cung
    # mot mach viec, con `server/scraper` va `web/src` thi khong.
    return "/".join(phan[:2])


class WarmExecutor:
    """Executor cho `Scheduler`: `(packet, worker) -> (raw, seconds)`.

    Giữ MỘT tiến trình ấm cho mỗi `worker_id`, nên nhiều nút giao cho cùng
    một worker sẽ dùng lại tiến trình đó thay vì dựng mới mỗi lần.

    An toàn luồng: `Scheduler` chạy nhiều nút song song, nhưng MỘT tiến trình
    `agy` chỉ xử lý được một lượt tại một thời điểm — nó là một hội thoại nối
    tiếp. Mỗi worker vì thế có khoá riêng. Không có khoá đó, hai luồng ghi
    xen kẽ vào cùng một stdin và cả hai kết quả đều hỏng theo cách rất khó lần.
    """

    def __init__(self, *, model: str, workspace_for=None,
                 allow_edits: bool = False,
                 policy: Optional[RecyclePolicy] = None,
                 turn_timeout: float = 240.0):
        self._model = model
        self._allow_edits = allow_edits
        self._policy = policy or RecyclePolicy()
        self._turn_timeout = turn_timeout
        #: `(packet) -> đường dẫn workspace`. Nút có ghi cần `--add-dir`.
        self._workspace_for = workspace_for

        self._workers: Dict[str, WarmAgyWorker] = {}
        self._khoa_worker: Dict[str, threading.Lock] = {}
        self._khoa_bang = threading.Lock()
        self.metrics = WarmMetrics()

    # -- quan ly tien trinh --------------------------------------------------

    def _lay(self, spec: WorkerSpec, packet: TaskPacket) -> WarmAgyWorker:
        with self._khoa_bang:
            w = self._workers.get(spec.worker_id)
            if w is None:
                ws = (self._workspace_for(packet) if self._workspace_for
                      else (packet.workspace or None))
                w = WarmAgyWorker(
                    spec.worker_id, model=self._model, cwd=ws, workspace=ws,
                    allow_edits=self._allow_edits, policy=self._policy,
                    turn_timeout=self._turn_timeout)
                self._workers[spec.worker_id] = w
                self._khoa_worker[spec.worker_id] = threading.Lock()
            return w

    def state_of(self, worker_id: str) -> WarmState:
        w = self._workers.get(worker_id)
        return w.state if w else WarmState.COLD

    def snapshot(self) -> List[dict]:
        with self._khoa_bang:
            ws = list(self._workers.values())
        ra = []
        for w in ws:
            ra.append({
                "worker_id": w.worker_id,
                "state": w.state.value,
                "turns": w.stats.turns,
                "context_chars": w.stats.chars,
                "family": w.stats.family,
                "recycles": len(w.recycles),
            })
        return ra

    def close(self) -> None:
        with self._khoa_bang:
            ws = list(self._workers.values())
            self._workers.clear()
        for w in ws:
            w.close()

    # -- giao dien Executor --------------------------------------------------

    def __call__(self, packet: TaskPacket, spec: WorkerSpec):
        w = self._lay(spec, packet)
        khoa = self._khoa_worker[spec.worker_id]
        ho = family_of(packet)

        t0 = time.perf_counter()
        # MOT tien trinh = MOT hoi thoai noi tiep. Khoa theo tung worker de hai
        # nut song song khong ghi xen ke vao cung mot stdin.
        with khoa:
            lanh_truoc = w.cold_starts
            recycle_truoc = len(w.recycles)
            t = w.send(packet.render(), family=ho)
            self.metrics.warm_dispatches += 1
            self.metrics.warm_seconds += t.seconds
            them_lanh = w.cold_starts - lanh_truoc
            if them_lanh:
                self.metrics.cold_starts += them_lanh
                self.metrics.cold_start_seconds = sum(
                    x.cold_start_seconds for x in self._workers.values())
            self.metrics.recycles += len(w.recycles) - recycle_truoc
            if not t.ok:
                self.metrics.failures += 1

        giay = time.perf_counter() - t0
        if t.ok:
            return t.response, giay
        # Tra ve HINH DANG ket qua ma `parse_result` doc duoc, khong nem: mot
        # nut hong khong duoc lam sap ca luot chay.
        import json
        return json.dumps({
            "status": "failed",
            "summary": (t.error or "worker ấm hỏng")[:300],
        }, ensure_ascii=False), giay

"""Bộ lập lịch song song — Router V3, Phase 3.

Đo được (2026-08-30) trước khi viết module này: ba lần gọi `agy` tuần tự mất
18.62s, chạy song song mất 6.66s, và tổng song song ≈ việc chậm nhất (6.65s) —
tức là song song THẬT, không phải bị tuần tự hoá ở phía CLI hay phía máy chủ.
Nếu phép đo đó cho kết quả ngược lại thì module này vô nghĩa, nên nó được đo
trước tiên.

Mở khoá theo TỪNG NÚT, không theo lớp. Chờ hết một lớp rồi mới sang lớp sau là
cách cài đơn giản hơn nhưng bắt mọi lớp phải chịu thời gian của nút chậm nhất
trong lớp đó; ở đây một nút xong là các nút phụ thuộc nó được xét ngay.
"""
from __future__ import annotations

import concurrent.futures as cf
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from scripts.router_v3.dag import TaskDag, TaskNode
from scripts.router_v3.packet import TaskPacket, TaskResult, packet_for
from scripts.router_v3.policy import (NoWorkerAvailable, SpeedMode,
                                      choose_worker, plan_parallelism)
from scripts.router_v3.registry import WorkerRegistry, WorkerSpec

#: `(packet, worker) -> (raw_output, seconds)`. Tiêm vào để kiểm thử tất định
#: mà không gọi mạng — và để bộ lập lịch không phụ thuộc một CLI cụ thể.
Executor = Callable[[TaskPacket, WorkerSpec], "tuple[str, float]"]


@dataclass
class RunReport:
    results: Dict[str, TaskResult] = field(default_factory=dict)
    wall_seconds: float = 0.0
    worker_seconds: float = 0.0
    max_in_flight: int = 0
    skipped: List[str] = field(default_factory=list)
    parallelism: int = 1
    parallelism_reason: str = ""

    @property
    def ok(self) -> bool:
        return (not self.skipped
                and all(r.ok for r in self.results.values()))

    @property
    def speedup_vs_serial(self) -> float:
        """Tăng tốc SO VỚI tổng giờ worker thực đo.

        Đây là con số trung thực: nó so với thời gian các worker THỰC SỰ tiêu
        tốn trong chính lượt chạy này, chứ không phải một ước lượng.
        """
        return round(self.worker_seconds / self.wall_seconds, 2) if self.wall_seconds else 0.0


class Scheduler:
    def __init__(self, registry: WorkerRegistry, executor: Executor, *,
                 mode: SpeedMode = SpeedMode.NORMAL,
                 max_parallel: Optional[int] = None,
                 base_sha: str = "unknown"):
        self._reg = registry
        self._exec = executor
        self._mode = mode
        self._max_parallel = max_parallel
        self._base_sha = base_sha
        self._khoa = threading.Lock()

    def run(self, dag: TaskDag) -> RunReport:
        song_song, ly_do = plan_parallelism(dag, self._mode)
        if self._max_parallel is not None:
            song_song = max(1, self._max_parallel)
            ly_do = f"do người gọi ép: {song_song}"

        bao_cao = RunReport(parallelism=song_song, parallelism_reason=ly_do)
        xong: Set[str] = set()
        hong: Set[str] = set()
        dang_chay: Dict[cf.Future, TaskNode] = {}
        dang_id: Set[str] = set()
        t0 = time.perf_counter()

        with cf.ThreadPoolExecutor(max_workers=song_song) as ex:
            while True:
                # Nap them viec cho toi khi day cho.
                while len(dang_chay) < song_song:
                    san = [n for n in dag.ready(xong, dang_id)
                           if not self._bi_chan(n, hong, dag)]
                    if not san:
                        break
                    nut = san[0]
                    # Mot nut `parallelizable=False` phai chay MOT MINH.
                    if not nut.parallelizable and dang_chay:
                        break
                    try:
                        worker = choose_worker(self._reg, nut)
                    except NoWorkerAvailable:
                        # Khong co worker HOP LE ngay bay gio. Neu dang co viec
                        # chay thi cho — worker se ranh ra. Neu khong thi
                        # that su be tac.
                        if dang_chay:
                            break
                        bao_cao.skipped.append(nut.id)
                        hong.add(nut.id)
                        xong.add(nut.id)
                        continue
                    dang_id.add(nut.id)
                    self._reg.mark_started(worker.worker_id, nut.id)
                    fut = ex.submit(self._chay_mot, nut, worker, dag, bao_cao)
                    dang_chay[fut] = nut
                    if not nut.parallelizable:
                        break

                if not dang_chay:
                    break
                bao_cao.max_in_flight = max(bao_cao.max_in_flight, len(dang_chay))

                # CHO NUT DAU TIEN XONG, khong cho ca lop.
                hoan_tat, _ = cf.wait(dang_chay, return_when=cf.FIRST_COMPLETED)
                for fut in hoan_tat:
                    nut = dang_chay.pop(fut)
                    dang_id.discard(nut.id)
                    kq = fut.result()
                    with self._khoa:
                        bao_cao.results[nut.id] = kq
                        bao_cao.worker_seconds += kq.duration_seconds
                    xong.add(nut.id)
                    if not kq.ok:
                        hong.add(nut.id)

        # Nut nao phu thuoc mot nut hong thi khong bao gio chay.
        for n in dag.nodes():
            if n.id not in xong:
                bao_cao.skipped.append(n.id)
        bao_cao.wall_seconds = round(time.perf_counter() - t0, 2)
        return bao_cao

    def _bi_chan(self, nut: TaskNode, hong: Set[str], dag: TaskDag) -> bool:
        """Nút có phụ thuộc nào đã hỏng không.

        Lan truyền thất bại: chạy một nút mà đầu vào của nó không tồn tại chỉ
        tốn thời gian worker để nhận về một thất bại khó hiểu hơn.
        """
        return any(d in hong or d in dag.ancestors(nut.id) & hong
                   for d in nut.dependencies)

    def _chay_mot(self, nut: TaskNode, worker: WorkerSpec, dag: TaskDag,
                  bao_cao: RunReport) -> TaskResult:
        with self._khoa:
            tom_tat = {d: (bao_cao.results[d].summary
                           if d in bao_cao.results else "")
                       for d in nut.dependencies}
        goi = packet_for(nut, base_sha=self._base_sha,
                         dependency_summaries=tom_tat)
        t0 = time.perf_counter()
        try:
            raw, giay = self._exec(goi, worker)
            ok = True
        except Exception as exc:
            raw, giay, ok = "", time.perf_counter() - t0, False
            loi = f"{type(exc).__name__}: {exc}"
        from scripts.router_v3.packet import parse_result
        if ok:
            kq = parse_result(nut.id, worker.worker_id, raw, giay)
        else:
            kq = TaskResult(task_id=nut.id, worker_id=worker.worker_id,
                            status="failed", summary=loi[:300],
                            duration_seconds=round(giay, 2))
        self._reg.mark_finished(worker.worker_id, ok=kq.ok,
                                seconds=kq.duration_seconds,
                                error="" if kq.ok else kq.summary)
        return kq

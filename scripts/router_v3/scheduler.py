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
                 base_sha: str = "unknown",
                 node_timeout: Optional[float] = 900.0):
        self._reg = registry
        self._exec = executor
        self._mode = mode
        self._max_parallel = max_parallel
        self._base_sha = base_sha
        # Tran thoi gian cho MOI nut. Khong co no, mot executor treo se treo
        # CA bo lap lich vo han: `cf.wait(...)` cho mai va khong nut nao khac
        # duoc nap them. Neu ra qua review doc lap (Codex).
        self._node_timeout = node_timeout
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

        ex = cf.ThreadPoolExecutor(max_workers=song_song)
        try:
            while True:
                # Nap them viec cho toi khi day cho.
                # Duyet HET danh sach san sang, khong dung o nut dau tien.
                #
                # Truoc ban sua nay vong lap lay `san[0]`; neu dung nut do
                # khong co worker hop le (vd viec rui ro cao ma worker tin cay
                # dang ban) thi ca vong `break`, va MOI nut san sang khac —
                # ke ca nhung nut co worker ranh — bi chan sau no. Day la
                # nghen dau hang, neu ra qua review kien truc doc lap (Gemini).
                tien = True
                while len(dang_chay) < song_song and tien:
                    tien = False
                    san = [n for n in dag.ready(xong, dang_id)
                           if not self._bi_chan(n, hong, dag)]
                    if not san:
                        break
                    for nut in san:
                        if len(dang_chay) >= song_song:
                            break
                        # Mot nut `parallelizable=False` phai chay MOT MINH.
                        if not nut.parallelizable and dang_chay:
                            continue
                        try:
                            worker = choose_worker(self._reg, nut)
                        except NoWorkerAvailable:
                            # Nut NAY chua co worker. Thu nut khac thay vi
                            # chan ca hang doi.
                            if not dang_chay and len(san) == 1:
                                bao_cao.skipped.append(nut.id)
                                hong.add(nut.id)
                                xong.add(nut.id)
                                tien = True
                            continue
                        dang_id.add(nut.id)
                        self._reg.mark_started(worker.worker_id, nut.id)
                        fut = ex.submit(self._chay_mot, nut, worker, dag, bao_cao)
                        dang_chay[fut] = nut
                        tien = True
                        if not nut.parallelizable:
                            break

                if not dang_chay:
                    break
                bao_cao.max_in_flight = max(bao_cao.max_in_flight, len(dang_chay))

                # CHO NUT DAU TIEN XONG, khong cho ca lop.
                hoan_tat, con_cho = cf.wait(
                    dang_chay, timeout=self._node_timeout,
                    return_when=cf.FIRST_COMPLETED)
                if not hoan_tat:
                    # Het gio ma KHONG nut nao xong -> executor dang treo.
                    # Danh dau tat ca la timeout va dung, thay vi cho mai.
                    for fut, nut in list(dang_chay.items()):
                        fut.cancel()
                        bao_cao.results[nut.id] = TaskResult(
                            task_id=nut.id, worker_id="?", status="timeout",
                            summary=f"vuot tran {self._node_timeout}s",
                            duration_seconds=self._node_timeout or 0.0)
                        xong.add(nut.id)
                        hong.add(nut.id)
                        dang_id.discard(nut.id)
                    dang_chay.clear()
                    continue
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

        finally:
            # KHONG dung `with`: `__exit__` goi `shutdown(wait=True)` va se
            # CHO mot luong dang treo cho xong — nghia la tran thoi gian o
            # tren van dung nhung `run()` VAN khong tra ve duoc. Da do duoc:
            # tran 0.3s ma ca luot van mat 30s.
            #
            # `cancel_futures=True` bo cac viec CHUA chay; viec DANG chay thi
            # Python khong giet duoc, nhung executor that (`run_worker`) co
            # `subprocess.run(timeout=...)` rieng nen no tu ket thuc.
            ex.shutdown(wait=False, cancel_futures=True)

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

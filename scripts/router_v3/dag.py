"""Đồ thị phụ thuộc công việc — Router V3, Phase 2.

Router V2 điều phối **một** worker một lúc. Nút thắt không phải tốc độ worker
mà là chỗ mọi việc xếp hàng sau nhau dù phần lớn chúng độc lập.

Module này mô tả công việc thành một DAG để tầng lập lịch **nhìn thấy** phần
độc lập. Nó cố ý chỉ là cấu trúc + kiểm tra hợp lệ, không chạm mạng, không
chạm git — nhờ vậy phần khó nhất (thứ tự và phạm vi ghi) kiểm thử được tất
định, tách hẳn khỏi phần chậm và hay hỏng.

FAIL CLOSED: một DAG sai (chu trình, phụ thuộc treo, hai nút cùng ghi một chỗ)
bị từ chối lúc **dựng**, không phải lúc chạy — lúc chạy thì đã có worker sửa
file rồi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple


class RiskClass(str, Enum):
    """Quyết định định tuyến VÀ mức review. Xem `policy.py`."""

    LOW = "low"
    MEDIUM = "medium"
    #: Bảo mật/credential/ranh giới sản xuất/đồng thời khó. Không bao giờ
    #: được hạ xuống worker yếu hơn chỉ vì worker đó rảnh hơn.
    HIGH = "high"


class DagError(RuntimeError):
    """DAG không hợp lệ. Luôn ném lúc dựng, không bao giờ lúc chạy."""


@dataclass(frozen=True)
class TaskNode:
    """Một đơn vị công việc giao được cho đúng một worker."""

    id: str
    objective: str
    dependencies: Tuple[str, ...] = ()
    #: Đường dẫn (tương đối gốc kho) nút này ĐƯỢC PHÉP ghi. Rỗng = chỉ đọc.
    write_scope: Tuple[str, ...] = ()
    read_scope: Tuple[str, ...] = ()
    required_capabilities: Tuple[str, ...] = ()
    risk_class: RiskClass = RiskClass.LOW
    expected_output: str = ""
    preferred_provider: Optional[str] = None
    #: `False` buộc nút chạy một mình — dùng cho việc đụng trạng thái dùng
    #: chung mà phạm vi ghi không diễn tả được.
    parallelizable: bool = True
    estimated_seconds: float = 60.0

    @property
    def is_write(self) -> bool:
        return bool(self.write_scope)


def _chuan_hoa(p: str) -> str:
    return p.strip().replace("\\", "/").strip("/")


def scopes_overlap(a: Sequence[str], b: Sequence[str]) -> bool:
    """Hai phạm vi ghi có giẫm lên nhau không.

    So theo TIỀN TỐ THƯ MỤC, không phải so chuỗi: `server/scraper` và
    `server/scraper/dag.py` giẫm nhau, còn `server/scraper` và
    `server/scraper_ops.py` thì KHÔNG — dùng `startswith` trần sẽ nói nhầm là
    có, rồi tuần tự hoá hai nút vốn độc lập.
    """
    for x in a:
        nx = _chuan_hoa(x)
        for y in b:
            ny = _chuan_hoa(y)
            if nx == ny or nx.startswith(ny + "/") or ny.startswith(nx + "/"):
                return True
    return False


class TaskDag:
    """DAG đã kiểm tra hợp lệ. Dựng được nghĩa là chạy được."""

    def __init__(self, nodes: Iterable[TaskNode], *,
                 allow_overlapping_writes: bool = False):
        self._nodes: Dict[str, TaskNode] = {}
        for n in nodes:
            if n.id in self._nodes:
                raise DagError(f"trùng id nút: {n.id!r}")
            if not n.id.strip():
                raise DagError("nút thiếu id")
            self._nodes[n.id] = n

        for n in self._nodes.values():
            for d in n.dependencies:
                if d not in self._nodes:
                    raise DagError(
                        f"{n.id!r} phụ thuộc {d!r} không tồn tại — phụ thuộc "
                        f"treo sẽ làm nút này KHÔNG BAO GIỜ chạy, im lặng.")
                if d == n.id:
                    raise DagError(f"{n.id!r} phụ thuộc chính nó")

        chu_trinh = self._tim_chu_trinh()
        if chu_trinh:
            raise DagError("có chu trình: " + " -> ".join(chu_trinh))

        if not allow_overlapping_writes:
            xung_dot = self.overlapping_write_pairs()
            if xung_dot:
                a, b = xung_dot[0]
                raise DagError(
                    f"{a!r} và {b!r} cùng ghi vào một phạm vi và KHÔNG có quan "
                    f"hệ phụ thuộc — chạy song song sẽ giẫm lên nhau. Thêm phụ "
                    f"thuộc, tách phạm vi, hoặc bật `allow_overlapping_writes` "
                    f"nếu thật sự cố ý.")

    # -- truy vấn -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes

    def node(self, node_id: str) -> TaskNode:
        return self._nodes[node_id]

    def nodes(self) -> List[TaskNode]:
        return list(self._nodes.values())

    def ids(self) -> List[str]:
        return list(self._nodes)

    def dependents_of(self, node_id: str) -> List[str]:
        return sorted(n.id for n in self._nodes.values()
                      if node_id in n.dependencies)

    def _tim_chu_trinh(self) -> Optional[List[str]]:
        """DFS ba màu; trả về CHÍNH chu trình để thông báo đọc được."""
        TRANG, XAM, DEN = 0, 1, 2
        mau = {i: TRANG for i in self._nodes}
        duong: List[str] = []

        def di(i: str) -> Optional[List[str]]:
            mau[i] = XAM
            duong.append(i)
            for d in self._nodes[i].dependencies:
                if mau[d] == XAM:
                    return duong[duong.index(d):] + [d]
                if mau[d] == TRANG:
                    r = di(d)
                    if r:
                        return r
            duong.pop()
            mau[i] = DEN
            return None

        for i in self._nodes:
            if mau[i] == TRANG:
                r = di(i)
                if r:
                    return r
        return None

    def overlapping_write_pairs(self) -> List[Tuple[str, str]]:
        """Cặp nút ghi giẫm nhau mà KHÔNG có quan hệ phụ thuộc.

        Có quan hệ phụ thuộc thì không sao — chúng không bao giờ chạy cùng lúc.
        """
        ra: List[Tuple[str, str]] = []
        ghi = [n for n in self._nodes.values() if n.is_write]
        for i, a in enumerate(ghi):
            for b in ghi[i + 1:]:
                if not scopes_overlap(a.write_scope, b.write_scope):
                    continue
                if self._co_lien_he(a.id, b.id):
                    continue
                ra.append((a.id, b.id))
        return ra

    def _co_lien_he(self, a: str, b: str) -> bool:
        return b in self.ancestors(a) or a in self.ancestors(b)

    def ancestors(self, node_id: str) -> Set[str]:
        ra: Set[str] = set()
        stack = list(self._nodes[node_id].dependencies)
        while stack:
            cur = stack.pop()
            if cur in ra:
                continue
            ra.add(cur)
            stack.extend(self._nodes[cur].dependencies)
        return ra

    # -- lập lịch ------------------------------------------------------------

    def ready(self, done: Iterable[str],
              running: Iterable[str] = ()) -> List[TaskNode]:
        """Các nút chạy được NGAY BÂY GIỜ."""
        xong = set(done)
        dang = set(running)
        return [n for n in self._nodes.values()
                if n.id not in xong and n.id not in dang
                and all(d in xong for d in n.dependencies)]

    def waves(self) -> List[List[str]]:
        """Nhóm theo lớp — dùng để ước lượng và hiển thị, KHÔNG phải để chạy.

        Bộ lập lịch thật không chờ hết một lớp mới sang lớp sau (như vậy mỗi
        lớp phải chịu thời gian của nút chậm nhất). Nó mở khoá theo từng nút.
        """
        xong: Set[str] = set()
        ra: List[List[str]] = []
        while len(xong) < len(self._nodes):
            lop = [n.id for n in self.ready(xong)]
            if not lop:                       # pragma: no cover - da chan o ctor
                raise DagError("bế tắc — đáng lẽ chu trình phải bị bắt lúc dựng")
            ra.append(sorted(lop))
            xong.update(lop)
        return ra

    def critical_path(self) -> Tuple[List[str], float]:
        """Đường dài nhất theo `estimated_seconds` — cận dưới của tổng thời gian.

        Thêm worker KHÔNG rút ngắn được đường này; đó là lý do nó là con số
        quyết định khi chọn mức song song, chứ không phải tổng số nút.
        """
        nho: Dict[str, Tuple[float, List[str]]] = {}

        def tinh(i: str) -> Tuple[float, List[str]]:
            if i in nho:
                return nho[i]
            n = self._nodes[i]
            tot_t, tot_d = 0.0, []
            for d in n.dependencies:
                t, duong = tinh(d)
                if t > tot_t:
                    tot_t, tot_d = t, duong
            kq = (tot_t + n.estimated_seconds, tot_d + [i])
            nho[i] = kq
            return kq

        tot = (0.0, [])
        for i in self._nodes:
            t, duong = tinh(i)
            if t > tot[0]:
                tot = (t, duong)
        return tot[1], round(tot[0], 2)

    def recommended_workers(self, ceiling: int = 8) -> int:
        """Số worker ĐÁNG dùng — không phải số tối đa dùng được.

        Song song tối đa không phải lúc nào cũng nhanh nhất: mỗi worker thêm
        vào đều tốn chi phí điều phối (dựng worktree, đóng gói, gộp kết quả),
        và không worker nào rút ngắn được đường tới hạn. Trần thực tế là bề
        rộng LỚN NHẤT của đồ thị.
        """
        rong = max((len(w) for w in self.waves()), default=1)
        return max(1, min(rong, ceiling))

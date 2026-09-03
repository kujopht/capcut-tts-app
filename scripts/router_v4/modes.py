"""Chế độ thực thi + chính sách leo thang — Router V4, mission #9 + #10.

BA MẪU, và quy tắc chọn giữa chúng:

    SOLO                 worker -> kết quả.  Mặc định.
    PRIMARY_CRITIC       thực thi -> review độc lập khác họ -> sửa/tích hợp.
    PARALLEL_HYPOTHESES  N chẩn đoán song song -> người tích hợp so bằng chứng.

ĐIỀU QUAN TRỌNG NHẤT LÀ *KHÔNG* CHẠY BA WORKER CHO MỌI VIỆC. Song song suy
đoán tốn gấp N lần và chỉ đáng khi thật sự không biết câu trả lời nằm ở đâu:
một race condition chưa rõ, một sự cố sản xuất chưa xác định nguyên nhân,
một kiến trúc có hai hướng đều hợp lý.

Quy tắc leo thang, cấu hình được và kiểm thử được:

    điểm = impact × uncertainty, cộng phạt theo LỊCH SỬ HỎNG của chính việc

    điểm >= nguong_hypotheses  -> PARALLEL_HYPOTHESES
    điểm >= nguong_critic      -> PRIMARY_CRITIC
    còn lại                    -> SOLO

`impact` và `uncertainty` nằm trong hợp đồng việc, do bên lập kế hoạch đặt —
nên quyết định leo thang GIẢI THÍCH ĐƯỢC và không phụ thuộc một heuristic ẩn.

ĐA DẠNG HỌ MODEL (mission #10): "một tài khoản khác chạy CÙNG model không
tự động là người review độc lập". `family_khac()` biến câu đó thành một
ràng buộc máy đọc được — nhưng là TÍN HIỆU CHO ĐIỂM (`exclude_families` +
`independence_bonus`), không phải rào cứng: nếu bể chỉ còn một họ, có review
vẫn hơn không có.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v4.capabilities import Requirements
from scripts.router_v4.contract import TaskContract


class Mode(str, Enum):
    SOLO = "solo"
    PRIMARY_CRITIC = "primary_critic"
    PARALLEL_HYPOTHESES = "parallel_hypotheses"


@dataclass(frozen=True)
class EscalationPolicy:
    """Ngưỡng leo thang. Cấu hình được — không hằng số rải rác trong mã."""

    nguong_critic: float = 0.25
    nguong_hypotheses: float = 0.60
    #: Moi lan viec nay da hong truoc do cong them bao nhieu vao diem.
    phat_moi_lan_hong: float = 0.15
    #: So gia thuyet chay song song o che do HYPOTHESES. 3 la du de so
    #: bang chung; 4+ hiem khi doi thay ket luan va ton gap boi.
    so_gia_thuyet: int = 3
    #: Viec doi review doc lap thi LUON it nhat la PRIMARY_CRITIC, du diem
    #: thap — hop dong da noi ro no can review.
    ton_trong_yeu_cau_review: bool = True

    @staticmethod
    def from_dict(d: Optional[Dict]) -> "EscalationPolicy":
        d = dict(d or {})
        return EscalationPolicy(
            nguong_critic=float(d.get("nguong_critic", 0.25)),
            nguong_hypotheses=float(d.get("nguong_hypotheses", 0.60)),
            phat_moi_lan_hong=float(d.get("phat_moi_lan_hong", 0.15)),
            so_gia_thuyet=int(d.get("so_gia_thuyet", 3)),
            ton_trong_yeu_cau_review=bool(
                d.get("ton_trong_yeu_cau_review", True)))

    def to_dict(self) -> Dict:
        return {"nguong_critic": self.nguong_critic,
                "nguong_hypotheses": self.nguong_hypotheses,
                "phat_moi_lan_hong": self.phat_moi_lan_hong,
                "so_gia_thuyet": self.so_gia_thuyet,
                "ton_trong_yeu_cau_review": self.ton_trong_yeu_cau_review}


@dataclass
class ModeDecision:
    mode: Mode
    score: float
    reason: str
    replicas: int = 1

    def to_dict(self) -> Dict:
        return {"mode": self.mode.value, "score": round(self.score, 4),
                "reason": self.reason, "replicas": self.replicas}


def chon_che_do(c: TaskContract, *, policy: Optional[EscalationPolicy] = None,
                failure_history: int = 0) -> ModeDecision:
    """Chọn chế độ thực thi cho một hợp đồng. Hàm THUẦN, tất định."""
    p = policy or EscalationPolicy()
    diem = c.impact * c.uncertainty + p.phat_moi_lan_hong * max(0, failure_history)
    chi_tiet = (f"impact={c.impact:.2f} × uncertainty={c.uncertainty:.2f}"
                + (f" + {failure_history} lần hỏng trước" if failure_history else ""))

    if diem >= p.nguong_hypotheses:
        return ModeDecision(
            Mode.PARALLEL_HYPOTHESES, diem,
            f"{chi_tiet} = {diem:.2f} >= {p.nguong_hypotheses} — việc "
            f"tác động lớn VÀ chưa rõ nguyên nhân; chạy {p.so_gia_thuyet} "
            f"chẩn đoán độc lập rồi so bằng chứng.",
            replicas=p.so_gia_thuyet)
    if diem >= p.nguong_critic:
        return ModeDecision(
            Mode.PRIMARY_CRITIC, diem,
            f"{chi_tiet} = {diem:.2f} >= {p.nguong_critic} — đủ rủi ro để "
            f"đáng một lượt review độc lập khác họ model.")
    if p.ton_trong_yeu_cau_review and c.verification.independent_review_required:
        return ModeDecision(
            Mode.PRIMARY_CRITIC, diem,
            f"{chi_tiet} = {diem:.2f} dưới ngưỡng, NHƯNG hợp đồng đòi "
            f"`independent_review_required` — hợp đồng thắng ngưỡng.")
    return ModeDecision(
        Mode.SOLO, diem,
        f"{chi_tiet} = {diem:.2f} < {p.nguong_critic} — việc thường; chạy "
        f"ba worker cho mọi việc là lãng phí, không phải cẩn thận.")


def hop_dong_review(goc: TaskContract, *, author_family: str,
                    review_id: str = "") -> TaskContract:
    """Dựng hợp đồng REVIEW ĐỘC LẬP cho kết quả của `goc`.

    Hai điều làm nó thực sự độc lập, không chỉ trên danh nghĩa:
      - `exclude_families=(author_family,)` — không để cùng họ model tự chấm
        bài của mình. Đây là chỗ mission #10 thành mã.
      - KHÔNG có `repo_write` — người review đọc và báo cáo, không sửa. Một
        reviewer sửa được thì nó không còn là kiểm tra độc lập nữa, và không
        ai review phần sửa đó.
    """
    return TaskContract(
        task_id=review_id or f"{goc.task_id}-review",
        mission_id=goc.mission_id, type="review",
        objective=(
            f"Review ĐỘC LẬP kết quả của việc `{goc.task_id}`.\n"
            f"Mục tiêu gốc: {goc.objective.strip()}\n\n"
            f"Đọc thay đổi trên nhánh đã cho và báo cáo LỖI THẬT: sai logic, "
            f"phá vỡ hợp đồng, rủi ro bảo mật, thiếu kiểm thử cho nhánh mới. "
            f"KHÔNG sửa gì. Nếu không tìm thấy vấn đề thật, nói rõ như vậy — "
            f"đừng bịa ra phát hiện cho đủ số."),
        inputs=goc.expected_outputs,
        requirements=Requirements(
            coding=True, repo_read=True, structured_output=True,
            reasoning_level=goc.requirements.reasoning_level,
            exclude_families=(author_family,) if author_family else ()),
        execution=type(goc.execution)(
            expected_duration=min(goc.execution.expected_duration, 180.0),
            max_wall_time=min(goc.execution.max_wall_time, 900.0),
            destructive_actions_allowed=False, worktree_required=False),
        dependencies=(goc.task_id,),
        impact=goc.impact, uncertainty=0.2,
        stop_conditions=("Không đọc được nhánh/thay đổi cần review",))


def hop_dong_gia_thuyet(goc: TaskContract, n: int) -> List[TaskContract]:
    """N bản chẩn đoán ĐỘC LẬP của cùng một câu hỏi.

    Mỗi bản là việc CHỈ ĐỌC: chúng chẩn đoán, không sửa. Cho ba worker cùng
    sửa một thứ rồi hợp nhất là cách chắc chắn nhất tạo ra ba nhánh xung đột
    — mission nói "integrator compares evidence", không phải "hợp nhất ba
    bản vá".
    """
    ra: List[TaskContract] = []
    for i in range(1, max(1, n) + 1):
        ra.append(TaskContract(
            task_id=f"{goc.task_id}-h{i}", mission_id=goc.mission_id,
            type="diagnosis",
            objective=(
                f"{goc.objective.strip()}\n\n"
                f"Đây là CHẨN ĐOÁN ĐỘC LẬP #{i}/{n}. Đưa ra nguyên nhân gốc "
                f"KHẢ DĨ NHẤT kèm BẰNG CHỨNG CỤ THỂ (tệp, dòng, hành vi quan "
                f"sát được). KHÔNG sửa gì. Nếu bằng chứng không đủ để kết "
                f"luận, nói rõ điều đó thay vì đoán."),
            inputs=goc.inputs,
            requirements=Requirements(
                coding=True, repo_read=True, structured_output=True,
                long_context=goc.requirements.long_context,
                reasoning_level=goc.requirements.reasoning_level),
            execution=type(goc.execution)(
                expected_duration=goc.execution.expected_duration,
                max_wall_time=goc.execution.max_wall_time,
                destructive_actions_allowed=False, worktree_required=False),
            dependencies=goc.dependencies,
            impact=goc.impact, uncertainty=goc.uncertainty))
    return ra


def family_khac(a: str, b: str) -> bool:
    """Hai họ model có thật sự khác nhau không.

    Tồn tại như một hàm riêng vì mission #10 nói rõ: MỘT TÀI KHOẢN KHÁC CHẠY
    CÙNG MODEL KHÔNG PHẢI người review độc lập. So `runtime_id` (điều dễ
    nhầm) sẽ nói AG01 review AG02 là độc lập ngay cả khi cả hai chạy đúng
    một model Gemini.
    """
    return bool(a) and bool(b) and a != b

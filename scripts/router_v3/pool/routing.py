"""Chính sách định tuyến theo năng lực — Bể worker tự trị, Phase 3.

Mission: "Keep policy configurable rather than hard-coded."

Nhưng KHÔNG PHẢI mọi thứ đều nên cấu hình được. Ranh giới:

    CẤU HÌNH ĐƯỢC  — lớp việc nào ưu tiên pool/model nào, thứ tự ưu tiên,
                     số lượt thử, trần song song. Đây là những lựa chọn đánh
                     đổi tốc độ/chi phí, đổi theo ngày cũng không sao.

    KHÔNG BAO GIỜ   — rào an toàn. `security_review` không đi tới Codex.
                     Việc rủi ro cao chỉ tới worker được đánh dấu tin cậy.
                     Một tệp cấu hình mở được rào đó thì rào không còn là
                     rào: nó chỉ là một mặc định, và bất kỳ ai sửa JSON
                     (kể cả vô tình) đều gỡ được nó.

Nên chính sách ở đây chỉ ẢNH HƯỞNG ĐIỂM ƯU TIÊN. Việc lọc ứng viên vẫn do
`policy.choose_worker` làm, và rào cứng nằm trong mã ở đó. Cấu hình này chỉ
nói "trong số các worker HỢP LỆ, thích cái nào hơn".

Bằng chứng thật đằng sau rào Codex (2026-08-28): cùng một gói review 14 KB
gửi hai nơi — Antigravity trả review thật, Codex trả kết quả rỗng kèm
"flagged for possible cybersecurity risk". Định tuyến review bảo mật sang
Codex là một lần hỏng IM LẶNG, nên nó là rào cứng chứ không phải ưu tiên.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from scripts.router_v3.dag import RiskClass, TaskNode
from scripts.router_v3.registry import WorkerRegistry, WorkerSpec

#: Chinh sach mac dinh — dung theo bang nang luc cua mission (#10).
#: Moi muc: ten lop viec -> danh sach worker_id/pool uu tien, giam dan.
MAC_DINH: Dict[str, object] = {
    "version": 1,
    "note": "Ưu tiên MỀM. Rào an toàn nằm trong mã (policy.choose_worker), "
            "không cấu hình được ở đây — xem docstring routing.py.",
    "max_attempts": 2,
    "max_parallel": 6,
    "prefer": {
        # Viec thuc thi dang ke, go loi, tich hop: model manh nhat cua be.
        "implement":       ["GEMINI_FLASH_HIGH", "OPENCODE", "CODEX"],
        "integration":     ["GEMINI_FLASH_HIGH", "OPENCODE"],
        "frontend":        ["GEMINI_FLASH_HIGH", "GEMINI_FLASH_MEDIUM"],
        # Viec co hoc: model re hon truoc.
        "tests":           ["GEMINI_FLASH_MEDIUM", "GEMINI_FLASH_HIGH"],
        "recon":           ["GEMINI_FLASH_MEDIUM", "GEMINI_FLASH_HIGH",
                            "OPENCODE"],
        # Review doc lap: uu tien KHAC HO MODEL voi ben thuc thi.
        "review":          ["CODEX", "OPENCODE", "ANTIGRAVITY_GPT_OSS"],
        "challenger":      ["ANTIGRAVITY_GPT_OSS", "OPENCODE", "CODEX"],
        # Bao mat/kien truc: chi worker tin cay — rao CUNG loc truoc roi.
        "security_review": ["ANTIGRAVITY_CLAUDE_OPUS"],
        "architecture":    ["ANTIGRAVITY_CLAUDE_OPUS", "CLAUDE_OPUS"],
    },
    #: Diem cong cho moi bac uu tien. Nho hon `capability_fit` (40) trong
    #: `policy.score_worker` co chu dich: uu tien cau hinh khong duoc thang
    #: viec "worker nay co lam duoc viec nay khong".
    "bonus_top": 12.0,
    "bonus_step": 4.0,
}


def duong_cau_hinh(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "pool" / "routing.json"


@dataclass
class RoutingPolicy:
    prefer: Dict[str, List[str]] = field(default_factory=dict)
    max_attempts: int = 2
    max_parallel: int = 6
    bonus_top: float = 12.0
    bonus_step: float = 4.0

    def uu_tien_cho(self, node: TaskNode) -> List[str]:
        """Danh sách pool ưu tiên cho nút này, giảm dần.

        Gộp theo TỪNG năng lực nút yêu cầu, giữ thứ tự xuất hiện đầu tiên —
        một nút cần cả `implement` và `tests` nên nghiêng về worker mạnh
        (mục `implement` đứng trước trong `required_capabilities`), không
        phải về worker rẻ chỉ vì `tests` tình cờ khớp trước.
        """
        ra: List[str] = []
        for nl in node.required_capabilities:
            for pool in self.prefer.get(nl, ()):
                if pool not in ra:
                    ra.append(pool)
        return ra

    def diem_uu_tien(self, spec: WorkerSpec, node: TaskNode) -> float:
        """Điểm cộng ưu tiên cho một worker với một nút. 0 nếu không nằm
        trong danh sách ưu tiên — KHÔNG trừ điểm: một worker ngoài danh
        sách vẫn hợp lệ, nó chỉ không được ưu ái."""
        uu_tien = self.uu_tien_cho(node)
        for i, pool in enumerate(uu_tien):
            if spec.pool == pool or spec.worker_id == pool:
                return max(0.0, self.bonus_top - i * self.bonus_step)
        return 0.0


def nap(path: Optional[Path] = None, *, root: Optional[Path] = None
        ) -> RoutingPolicy:
    p = Path(path) if path else duong_cau_hinh(root)
    d = dict(MAC_DINH)
    if p.exists():
        try:
            tren_dia = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{p}: JSON hỏng — {exc}") from exc
        if not isinstance(tren_dia, dict):
            raise ValueError(f"{p}: cần một đối tượng JSON")
        d.update(tren_dia)
    prefer = d.get("prefer") or {}
    if not isinstance(prefer, dict):
        raise ValueError("`prefer` phải là đối tượng {năng_lực: [pool,...]}")
    return RoutingPolicy(
        prefer={str(k): [str(x) for x in (v or [])] for k, v in prefer.items()},
        max_attempts=int(d.get("max_attempts") or 2),
        max_parallel=int(d.get("max_parallel") or 6),
        bonus_top=float(d.get("bonus_top") or 12.0),
        bonus_step=float(d.get("bonus_step") or 4.0))


def ghi_mac_dinh(path: Optional[Path] = None, *,
                 root: Optional[Path] = None) -> Path:
    p = Path(path) if path else duong_cau_hinh(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(MAC_DINH, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def ung_vien_kha_thi(reg: WorkerRegistry, node: TaskNode, *,
                     loai_tru: Sequence[str] = ()) -> List[WorkerSpec]:
    """Worker CÓ THỂ làm việc này — bỏ qua tải và sức khoẻ tạm thời.

    Khác `reg.available()` ở đúng một điểm quan trọng: nó không quan tâm
    worker đang bận hay vừa hỏng, chỉ hỏi "về nguyên tắc, worker này có đủ
    tư cách nhận việc này không". Dùng để phân biệt *chờ một lát* với *chờ
    mãi mãi*.

    Trạng thái CẦN NGƯỜI VẬN HÀNH (`UNAVAILABLE`/`AUTH_REQUIRED`) vẫn bị
    loại: chúng không tự hồi, nên coi chúng là "sẽ rảnh sau" là sai.
    """
    from scripts.router_v3.registry import _KHONG_BAO_GIO_CHON

    bo = set(loai_tru)
    ra: List[WorkerSpec] = []
    for wid in reg.ids():
        spec = reg.spec(wid)
        if wid in bo:
            continue
        if reg.state(wid).health in _KHONG_BAO_GIO_CHON:
            continue
        if node.risk_class is RiskClass.HIGH and not spec.trusted_for_high_risk:
            continue
        if (node.required_capabilities
                and not set(node.required_capabilities) & set(spec.capabilities)):
            continue
        if ("security_review" in node.required_capabilities
                and spec.provider_family == "codex"):
            continue
        ra.append(spec)
    return ra


def co_ung_vien_kha_thi(reg: WorkerRegistry, node: TaskNode, *,
                        loai_tru: Sequence[str] = ()) -> bool:
    return bool(ung_vien_kha_thi(reg, node, loai_tru=loai_tru))


def chon_worker(reg: WorkerRegistry, node: TaskNode, *,
                policy: Optional[RoutingPolicy] = None,
                loai_tru: Sequence[str] = ()) -> WorkerSpec:
    """Chọn worker: rào cứng của `policy.choose_worker` + ưu tiên cấu hình.

    `loai_tru` là các worker ĐÃ THỬ và hỏng cho chính việc này — dùng cho
    việc ĐỔI WORKER (mission #9). Loại trừ ở đây chứ không ở tầng dưới vì
    tầng dưới không biết lịch sử của một việc cụ thể.

    Nếu loại trừ hết sạch ứng viên thì KHÔNG rơi ngược về worker đã hỏng:
    ném `NoWorkerAvailable` để bên gọi báo hỏng thật. Quay lại một worker
    vừa hỏng hai lần chỉ để "có cái mà chạy" là cách sinh ra vòng lặp.
    """
    from scripts.router_v3.policy import (NoWorkerAvailable, choose_worker,
                                          score_worker)

    pol = policy or RoutingPolicy(prefer=dict(MAC_DINH["prefer"]))  # type: ignore[arg-type]
    if not loai_tru:
        ung_vien_tho = None
    else:
        ung_vien_tho = set(loai_tru)

    cao = node.risk_class is RiskClass.HIGH
    ung_vien = reg.available(high_risk=cao)
    if node.required_capabilities:
        ung_vien = [w for w in ung_vien
                    if set(node.required_capabilities) & set(w.capabilities)]
    # RAO CUNG — lap lai co chu dich, KHONG doc tu cau hinh. Neu ham nay chi
    # goi `choose_worker` roi loc sau thi mot worker Codex van co the thang
    # o buoc chon va bi loai sau, tra ve "khong co worker" thay vi worker
    # dung thu hai. Loc TRUOC khi cham diem moi cho ket qua dung.
    if "security_review" in node.required_capabilities:
        ung_vien = [w for w in ung_vien if w.provider_family != "codex"]
    if ung_vien_tho:
        ung_vien = [w for w in ung_vien if w.worker_id not in ung_vien_tho]

    if not ung_vien:
        raise NoWorkerAvailable(
            f"{node.id}: không worker nào đủ điều kiện "
            f"(risk={node.risk_class.value}, cần={list(node.required_capabilities)}"
            f"{', đã loại ' + str(sorted(ung_vien_tho)) if ung_vien_tho else ''})."
            f" Fail closed — không hạ chuẩn tin cậy và không quay lại worker "
            f"vừa hỏng để lấp chỗ.")

    return max(ung_vien, key=lambda w: (score_worker(w, reg, node).total
                                        + pol.diem_uu_tien(w, node)))

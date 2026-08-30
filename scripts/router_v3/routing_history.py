"""Lịch sử định tuyến — Router LTS Phase 9.

Ghi lại KẾT QUẢ từng việc (không phải prompt/nội dung) để điểm định tuyến
ở `policy.py` dùng số THẬT thay vì chỉ số trong-bộ-nhớ-phiên-này. KHÁC với
`WorkerState` (registry.py, chỉ sống trong RAM của một lần chạy Router):
đây là NHẬT KÝ NỐI DUÔI trên đĩa, sống qua nhiều lần khởi động lại.

CHỈ THỐNG KÊ, KHÔNG HUẤN LUYỆN LẠI MÔ HÌNH — mission nói rõ "đây là định
tuyến/đo lường thống kê, KHÔNG fine-tune tự động", và module này chỉ tính
trung bình/tỉ lệ trên các bản ghi, không có gì học máy ở đây.

KHÔNG BAO GIỜ GHI: prompt, nội dung phản hồi, đường dẫn tệp thật, hay bất
cứ thứ gì giống credential — chỉ nhãn + số. Dùng lại `scan_for_secrets`
của `packet.py` để chặn ở cửa ghi, không tin người gọi luôn cẩn thận.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts.router_v3.packet import scan_for_secrets

TEN_TAP_MAC_DINH = ".router/telemetry/routing_history.jsonl"


@dataclass
class BanGhiKetQua:
    provider: str
    model: str = ""
    task_class: str = ""
    wall_seconds: float = 0.0
    tool_seconds: float = 0.0
    success: bool = True
    retry_count: int = 0
    review_findings: int = 0
    rework_required: bool = False
    merge_conflicts: bool = False
    test_result: str = ""             # "passed" | "failed" | "" (khong ro)
    tokens: int = 0
    cost_usd: float = 0.0
    #: KHÔNG dùng `time.time()` mặc định trong dataclass field — nơi gọi
    #: phải TỰ đưa timestamp vào, để không có randomness/thời gian ẩn nào
    #: lẻn vào một hàm được kỳ vọng thuần (khớp ràng buộc "không Date.now()
    #: ẩn" của toàn bộ hệ Router).
    ts: float = 0.0


def duong_mac_dinh(goc_du_an: Optional[Path] = None) -> Path:
    goc = Path(goc_du_an) if goc_du_an else Path.cwd()
    return goc / TEN_TAP_MAC_DINH


def ghi(ban_ghi: BanGhiKetQua, *, duong: Optional[Path] = None) -> None:
    p = duong or duong_mac_dinh()
    dong = json.dumps(asdict(ban_ghi), ensure_ascii=False)
    ro_ri = scan_for_secrets(dong)
    if ro_ri:
        raise ValueError(
            f"bản ghi lịch sử định tuyến chứa thứ giống credential "
            f"(mẫu {ro_ri!r}) — TỪ CHỐI ghi.")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(dong + "\n")


def doc_tat_ca(*, duong: Optional[Path] = None,
               limit_dong: Optional[int] = None) -> List[BanGhiKetQua]:
    """Đọc toàn bộ (hoặc `limit_dong` dòng CUỐI, nếu đặt).

    Nhật ký nối đuôi KHÔNG tự giới hạn kích thước — review độc lập
    (2026-08-30) đúng khi chỉ ra đọc/parse toàn bộ tệp trên MỖI lần gọi sẽ
    thành nút thắt I/O khi lịch sử lớn dần. `limit_dong` cho phép bên gọi
    chỉ lấy phần GẦN NHẤT (đủ cho hầu hết quyết định định tuyến, vốn quan
    tâm hiệu năng gần đây hơn lịch sử toàn thời gian) mà không phải đổi
    định dạng lưu trữ. Mặc định `None` = đọc hết, giữ hành vi cũ.
    """
    p = duong or duong_mac_dinh()
    if not p.exists():
        return []
    tat_ca_dong = p.read_text(encoding="utf-8").splitlines()
    if limit_dong is not None and limit_dong > 0:
        tat_ca_dong = tat_ca_dong[-limit_dong:]
    ra = []
    for dong in tat_ca_dong:
        dong = dong.strip()
        if not dong:
            continue
        try:
            d = json.loads(dong)
        except json.JSONDecodeError:
            continue          # mot dong hong khong lam hong ca lich su
        ra.append(BanGhiKetQua(**{k: d.get(k, v) for k, v in
                                 asdict(BanGhiKetQua(provider="")).items()}))
    return ra


@dataclass
class TongHop:
    so_luot: int = 0
    ty_le_thanh_cong: float = 1.0     # lac quan khi chua co du lieu
    ty_le_lam_lai: float = 0.0
    avg_wall_seconds: float = 0.0
    avg_cost_usd: float = 0.0
    avg_tokens: float = 0.0


def tong_hop(ban_ghi: List[BanGhiKetQua], *, provider: str,
            model: str = "", task_class: str = "") -> TongHop:
    """Gộp theo `provider` (bắt buộc), lọc thêm theo `model`/`task_class`
    nếu có — rỗng nghĩa là "không lọc theo trường đó"."""
    khop = [b for b in ban_ghi if b.provider == provider
           and (not model or b.model == model)
           and (not task_class or b.task_class == task_class)]
    if not khop:
        return TongHop()
    n = len(khop)
    return TongHop(
        so_luot=n,
        ty_le_thanh_cong=sum(1 for b in khop if b.success) / n,
        ty_le_lam_lai=sum(1 for b in khop if b.rework_required) / n,
        avg_wall_seconds=sum(b.wall_seconds for b in khop) / n,
        avg_cost_usd=sum(b.cost_usd for b in khop) / n,
        avg_tokens=sum(b.tokens for b in khop) / n)

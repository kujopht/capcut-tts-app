"""KẾT QUẢ ĐÃ KIỂM ĐỊNH -> LỊCH SỬ VAI — V0.9, §B.

V0.8 đã ghi một `Record` cho MỖI LƯỢT VAI, và con số `success` ở đó trả lời
đúng một câu: *"vai này có trả về thứ đọc được không?"* Đó là một phép đo về
VẬN CHUYỂN. Nó không biết gì về việc lời khuyên ấy, khi đem ra làm thật, có
đạt mục tiêu hay không.

Tệp này nối nốt quan hệ mà §B đòi:

    chiến lược -> kế hoạch -> thực thi -> kiểm định -> kết quả cuối

KHÔNG DỰNG HỆ THỐNG BENCHMARK THỨ HAI. Cùng `BenchmarkStore`, cùng tệp
`.router/v4/benchmark-reasoning.jsonl`, cùng `Record`, cùng `MAU_TOI_THIEU`.
Thứ duy nhất khác là `task_type`: `ketqua_<vai>` thay vì `reasoning_<vai>`.

VÌ SAO MỘT `task_type` RIÊNG, chứ không ghi đè bản ghi lượt vai:

* tệp là NỐI ĐUÔI, không sửa được tại chỗ — một `Record` đã ghi là một sự
  thật lịch sử;
* hai câu hỏi khác nhau thì hai con số khác nhau. `summary_for(model,
  "reasoning_strategist")` = "model này trả lời được không"; `summary_for(
  model, "ketqua_strategist")` = "khi lời khuyên của nó được đem làm thật,
  nó có đạt không". Trộn chúng vào một con số là làm hỏng cả hai.
* và `summary_for` có đường NỚI về chỉ-`model`, nên bản ghi kết quả vẫn góp
  vào bức tranh chung của model mà không bóp méo thống kê theo loại việc.

BA ĐIỀU KHÔNG ĐƯỢC LÀM, và mỗi điều là một cách nói dối bằng số:

1. **Một lần HUỶ không phải một mẫu.** Người dùng đổi ý giữa chừng không đo
   được gì về chất lượng của lời khuyên. Ghi nó thành `success=False` sẽ
   phạt một chiến lược có thể hoàn toàn đúng. Nên không ghi gì cả.
2. **Một cuộc trò chuyện không phải một kết quả.** Chỉ một lần thực thi
   THẬT, đã qua `VERIFYING`, mới sinh ra quan sát. Một đề xuất chưa ai làm
   thì chưa biết nó đúng hay sai.
3. **Một lần thực thi = ĐÚNG MỘT quan sát.** Khởi động lại, đối soát, hay
   một nhịp `tick` lặp không được đẻ thêm mẫu. Khoá chống trùng nằm ở
   `ghi_phan_hoi`, và nó BỀN (dùng chính bảng `ket_qua_da_bao`).

Và `MAU_TOI_THIEU` giữ nguyên. Một model thắng một lần không phải "100%
đáng tin" — đúng câu mà `router_v4/history.py` đã viết từ đầu.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from scripts.control_center.execution.kiem_dinh import BaoCaoKiemDinh
from scripts.control_center.execution.ket_qua import TrangThaiXacMinh
from scripts.control_center.execution.tiep_noi import DeXuat
from scripts.control_center.execution.trang_thai import TrangThaiThucThi
from scripts.control_center.execution.y_dinh import YDinhThucThi

#: Tiền tố `task_type` của bản ghi KẾT QUẢ. Đọc ra ngay là "kết quả của vai
#: X", không lẫn với `reasoning_X` của lượt vai.
TIEN_TO = "ketqua_"

#: Trạng thái KHÔNG sinh quan sát nào. `CANCELLED` ở đây — xem điều 1 của
#: docstring module.
KHONG_DO_DUOC = frozenset({TrangThaiThucThi.CANCELLED,
                           TrangThaiThucThi.PAUSED,
                           TrangThaiThucThi.WAITING_AUTHORITY})


@dataclass(frozen=True)
class QuanSatKetQua:
    """Một quan sát ĐÃ LIÊN KẾT. Dữ liệu thuần — bên gọi quyết định ghi hay không."""

    vai: str
    provider: str
    model_id: str
    runtime_id: str
    task_type: str
    execution_id: str
    de_xuat: str
    project_id: str
    ban_ke_hoach: int
    thanh_cong: bool
    xac_minh: str
    phan_xu: str
    so_lan_lap_lai: int
    so_lan_thu_lai: int
    giay: Optional[float]
    #: `None` khi không đo được — KHÔNG BAO GIỜ `0`. Cùng luật `UsageMetric`.
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {"vai": self.vai, "provider": self.provider,
                "model_id": self.model_id, "runtime_id": self.runtime_id,
                "task_type": self.task_type,
                "execution_id": self.execution_id, "de_xuat": self.de_xuat,
                "project_id": self.project_id,
                "ban_ke_hoach": self.ban_ke_hoach,
                "thanh_cong": self.thanh_cong, "xac_minh": self.xac_minh,
                "phan_xu": self.phan_xu,
                "so_lan_lap_lai": self.so_lan_lap_lai,
                "so_lan_thu_lai": self.so_lan_thu_lai,
                "giay": self.giay, "tokens": self.tokens,
                "cost_usd": self.cost_usd, "ts": self.ts}


def dung_quan_sat(y: YDinhThucThi, bc: Optional[BaoCaoKiemDinh], *,
                  de_xuat: Optional[DeXuat] = None,
                  phan_bien: Optional[Dict] = None,
                  giay: Optional[float] = None) -> Optional[QuanSatKetQua]:
    """`(ý định, báo cáo) -> quan sát`, hoặc `None` khi KHÔNG đo được gì.

    Trả `None` — chứ không trả một quan sát `success=False` — trong ba
    trường hợp, và cả ba đều là "chưa có gì để đo":

    * lần thực thi bị HUỶ / tạm dừng / còn chờ thẩm quyền;
    * chưa kiểm định (`bc is None`);
    * không truy được vai/model nào đã đề xuất việc này (`de_xuat` rỗng hoặc
      không mang `model`) — một quan sát không gắn được vào ai thì không nói
      lên điều gì về ai.
    """
    if y.trang_thai in KHONG_DO_DUOC or bc is None:
        return None
    if de_xuat is None or not (de_xuat.model or "").strip():
        return None
    return QuanSatKetQua(
        vai=de_xuat.tu_vai or "strategist",
        provider=de_xuat.provider, model_id=de_xuat.model,
        runtime_id=de_xuat.runtime_id,
        task_type=TIEN_TO + (de_xuat.tu_vai or "strategist"),
        execution_id=y.execution_id, de_xuat=de_xuat.ma,
        project_id=y.project_id, ban_ke_hoach=int(y.ban_ke_hoach or 1),
        thanh_cong=bool(bc.dat),
        xac_minh=bc.trang_thai.value,
        phan_xu=str((phan_bien or {}).get("phan_xu") or ""),
        so_lan_lap_lai=int(y.so_lan_lap_lai or 0),
        so_lan_thu_lai=int(y.so_lan_thu_lai or 0),
        giay=(float(giay) if giay is not None else None),
        tokens=None, cost_usd=None)


def ghi_phan_hoi(lich_su: Any, qs: Optional[QuanSatKetQua], *,
                 rubric: str = "") -> Optional[Dict]:
    """Ghi quan sát vào lịch sử VAI. `None` khi không có gì để ghi.

    `lich_su` là `BenchmarkStore` của tệp VAI. Không truyền (hoặc `None`) thì
    không ghi — mọi bài kiểm tất định chạy ở chế độ đó.

    `success` ở đây là KẾT QUẢ ĐÃ KIỂM ĐỊNH, không phải "vai có trả lời
    được". `SUY_GIAM` vẫn tính là thành công: nó nghĩa là mọi phép đo đạt
    nhưng thiếu phản biện độc lập — một thiếu sót của HẠ TẦNG lượt đó, không
    phải một lỗi của chiến lược. Phạt chiến lược vì thiếu một model khác họ
    là đo sai thứ.

    `retry_count`/`reassigned` mang số lần LẬP LẠI KẾ HOẠCH + THỬ LẠI của cả
    lần thực thi, nên `summary_for` hạ `quality` của một chiến lược phải sửa
    nhiều lần mới xong — đúng thứ ta muốn học.
    """
    if lich_su is None or qs is None:
        return None
    from scripts.router_v4.history import Record
    lich_su.record(Record(
        ts=qs.ts, task_type=qs.task_type, provider=qs.provider,
        model_id=qs.model_id, runtime_id=qs.runtime_id,
        wall_seconds=float(qs.giay or 0.0),
        success=bool(qs.thanh_cong),
        review_findings=0,
        retry_count=int(qs.so_lan_lap_lai + qs.so_lan_thu_lai),
        reassigned=bool(qs.so_lan_lap_lai > 0),
        tokens=None, cost_usd=None,          # KHONG do duoc -> None, khong 0
        project=qs.project_id, verdict=qs.phan_xu,
        quality=None, rubric=rubric))
    return qs.to_dict()


def tom_tat(lich_su: Any, *, vai: str = "strategist",
            model_id: str = "") -> Optional[Dict]:
    """Tổng hợp các quan sát KẾT QUẢ. `None` khi chưa đủ `MAU_TOI_THIEU`.

    Cửa duy nhất để đọc vòng phản hồi này, và nó cố ý KHÔNG có tham số hạ
    ngưỡng. Chưa đủ mẫu thì câu trả lời đúng là "chưa biết", không phải một
    con số dựng từ hai lần chạy.
    """
    if lich_su is None:
        return None
    return lich_su.summary_for(model_id=model_id, task_type=TIEN_TO + vai)

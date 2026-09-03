"""Kho lịch sử / benchmark — Router V4, mission #19.

MỤC ĐÍCH: không đóng cứng vĩnh viễn một bảng xếp hạng model chủ quan. Tiên
nghiệm trong cấu hình chỉ là ĐIỂM XUẤT PHÁT; lịch sử thực đo lấn át dần.

KHÔNG PHẢI HỌC MÁY. Đây là thống kê: trung bình, tỉ lệ, đếm. Mission nói rõ
"No ML scheduler is required", và một bộ lập lịch học máy ở đây sẽ vừa
không giải thích được vừa không kiểm thử tất định được — hai thứ V4 coi
trọng hơn.

KHÔNG BAO GIỜ GHI: prompt, nội dung phản hồi, đường dẫn tệp thật, hay bất
cứ thứ gì giống credential. Chỉ nhãn + số. Dùng lại `scan_for_secrets` của
`packet.py` chặn ở CỬA GHI thay vì tin người gọi luôn cẩn thận — cùng bất
biến `router_v3/routing_history.py` đã thiết lập.

NGƯỠNG MẪU: dưới `MAU_TOI_THIEU` bản ghi thì `summary_for` trả `None` và bộ
lập lịch dùng tiên nghiệm. Một model thắng một lần rồi được coi là "100%
đáng tin" là cách nhanh nhất để dồn toàn bộ việc vào một chỗ.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from scripts.router_v3.packet import scan_for_secrets

MAU_TOI_THIEU = 3
TEN_TEP = ".router/v4/benchmark.jsonl"


@dataclass
class Record:
    """Một lần chạy. Chỉ nhãn và số — không nội dung."""

    ts: float
    task_type: str
    provider: str
    model_id: str
    runtime_id: str
    wall_seconds: float
    success: bool
    test_passed: int = 0
    test_failed: int = 0
    review_findings: int = 0
    retry_count: int = 0
    reassigned: bool = False
    #: Uoc luong tai nguyen — `None` khi khong quan sat duoc (khong phai 0).
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def duong(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / TEN_TEP


class BenchmarkStore:
    """Nhật ký nối đuôi + tổng hợp. Sống qua nhiều lần khởi động Router."""

    def __init__(self, path: Optional[Path] = None, *,
                 root: Optional[Path] = None):
        self.path = Path(path) if path else duong(root)
        self._cache: Optional[List[Record]] = None

    # -- ghi ----------------------------------------------------------------

    def record(self, r: Record) -> None:
        dong = json.dumps(r.to_dict(), ensure_ascii=False)
        ro_ri = scan_for_secrets(dong)
        if ro_ri:
            # KHONG ghi mot ban ghi giong credential, va KHONG nem loi lam
            # hong ca luot chay vi mot dong telemetry. Bo qua co ghi nhan.
            dong = json.dumps({"ts": r.ts, "task_type": "REDACTED",
                               "provider": r.provider, "model_id": r.model_id,
                               "runtime_id": r.runtime_id,
                               "wall_seconds": r.wall_seconds,
                               "success": r.success,
                               "note": f"bỏ trường giống credential ({ro_ri})"},
                              ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(dong + "\n")
        self._cache = None

    # -- doc ----------------------------------------------------------------

    def all(self) -> List[Record]:
        if self._cache is not None:
            return self._cache
        ra: List[Record] = []
        if self.path.exists():
            for dong in self.path.read_text(encoding="utf-8",
                                            errors="replace").splitlines():
                dong = dong.strip()
                if not dong.startswith("{"):
                    continue
                try:
                    d = json.loads(dong)
                except json.JSONDecodeError:
                    continue
                try:
                    ra.append(Record(
                        ts=float(d.get("ts") or 0.0),
                        task_type=str(d.get("task_type") or ""),
                        provider=str(d.get("provider") or ""),
                        model_id=str(d.get("model_id") or ""),
                        runtime_id=str(d.get("runtime_id") or ""),
                        wall_seconds=float(d.get("wall_seconds") or 0.0),
                        success=bool(d.get("success")),
                        test_passed=int(d.get("test_passed") or 0),
                        test_failed=int(d.get("test_failed") or 0),
                        review_findings=int(d.get("review_findings") or 0),
                        retry_count=int(d.get("retry_count") or 0),
                        reassigned=bool(d.get("reassigned")),
                        tokens=d.get("tokens"), cost_usd=d.get("cost_usd")))
                except (TypeError, ValueError):
                    continue
        self._cache = ra
        return ra

    def summary_for(self, *, model_id: str = "", task_type: str = "",
                    provider: str = "", limit: int = 50) -> Optional[Dict]:
        """Tổng hợp N bản ghi GẦN NHẤT khớp bộ lọc. `None` nếu chưa đủ mẫu.

        Ưu tiên khớp CẢ model và loại việc; không đủ mẫu thì nới sang chỉ
        model. Một model có thể giỏi việc này và dở việc kia, nên khớp hẹp
        trước là đúng — nhưng khớp hẹp thường thiếu mẫu, nên phải có đường
        nới, nếu không lịch sử gần như không bao giờ được dùng.
        """
        ds = self.all()
        def _loc(hep: bool) -> List[Record]:
            ra = [r for r in ds
                  if (not model_id or r.model_id == model_id)
                  and (not provider or r.provider == provider)
                  and (not hep or not task_type or r.task_type == task_type)]
            return ra[-limit:]

        chon = _loc(True)
        pham_vi = "model+task_type"
        if len(chon) < MAU_TOI_THIEU:
            chon = _loc(False)
            pham_vi = "model"
        if len(chon) < MAU_TOI_THIEU:
            return None

        n = len(chon)
        thanh_cong = sum(1 for r in chon if r.success)
        tong_giay = sum(r.wall_seconds for r in chon)
        tong_thu_lai = sum(r.retry_count for r in chon)
        co_test = [r for r in chon if (r.test_passed + r.test_failed) > 0]
        ty_le_test = (sum(1 for r in co_test if r.test_failed == 0) / len(co_test)
                      if co_test else None)
        phat_hien = sum(r.review_findings for r in chon)

        # `quality` gop thanh cong + test xanh + it phat hien review + it
        # thu lai. Cong thuc CO Y don gian va giai thich duoc; mot diem so
        # phuc tap hon ma khong ai doc noi thi khong ai tin.
        chat_luong = thanh_cong / n
        if ty_le_test is not None:
            chat_luong = 0.6 * chat_luong + 0.4 * ty_le_test
        chat_luong *= max(0.5, 1.0 - 0.05 * (tong_thu_lai / n))
        chat_luong *= max(0.6, 1.0 - 0.02 * (phat_hien / n))

        return {
            "samples": n, "scope": pham_vi,
            "success_rate": round(thanh_cong / n, 4),
            "quality": round(max(0.0, min(1.0, chat_luong)), 4),
            "avg_wall_seconds": round(tong_giay / n, 2),
            "avg_retries": round(tong_thu_lai / n, 3),
            "test_pass_rate": (round(ty_le_test, 4)
                               if ty_le_test is not None else None),
            "review_findings_total": phat_hien,
            "reassign_rate": round(sum(1 for r in chon if r.reassigned) / n, 4),
        }

    def leaderboard(self, *, task_type: str = "") -> List[Dict]:
        """Bảng tổng hợp theo model — để `router explain`/báo cáo đọc được.
        KHÔNG dùng để định tuyến trực tiếp; bộ lập lịch gọi `summary_for`."""
        models = sorted({r.model_id for r in self.all() if r.model_id})
        ra = []
        for m in models:
            s = self.summary_for(model_id=m, task_type=task_type)
            if s:
                ra.append({"model_id": m, **s})
        return sorted(ra, key=lambda x: -x["quality"])

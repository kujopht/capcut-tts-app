"""HỢP ĐỒNG KẾT QUẢ và CHẶN "DONE GIẢ" — V0.9, §6.

HAI CÂU CỦA YÊU CẦU §6 LÀ TOÀN BỘ LÝ DO TỆP NÀY TỒN TẠI:

    *"A process exit code alone is NOT proof that a task succeeded."*
    *"No output produced" is not DONE.*

Router V4 đã có `ResultEnvelope` và nó tốt cho việc của nó: mô tả MỘT lượt
chạy. Thứ v0.9 cần thêm là một phán quyết — *lời khai này có ĐỦ BẰNG CHỨNG
để tính là xong không?* — và phán quyết đó phải là dữ liệu, không phải một
`if` nằm rải rác trong bộ điều phối.

BA MỨC, và `CHUA_DU_BANG_CHUNG` là mức quan trọng nhất:

    DU          có bằng chứng khớp loại việc -> đi tiếp tới kiểm định
    CHUA_DU     worker nói xong nhưng không chứng minh được -> KHÔNG DONE,
                và cũng KHÔNG FAILED: nó là một trạng thái CHỜ BẰNG CHỨNG,
                vì việc có thể đã làm đúng mà chỉ khai thiếu
    MAU_THUAN   lời khai chống lại chính nó (khai sửa tệp mà không tệp nào)
                -> hỏng thật

Gộp `CHUA_DU` vào `FAILED` sẽ vứt đi công việc thật của một worker chỉ vì nó
kể chuyện kém; gộp vào `DU` thì mở lại đúng cái cửa "exit 0 = xong".

`_doi_soat_khai_thieu` của V0.7 vẫn ở nguyên trong `engine.py` và vẫn chạy
trước. Tệp này là cổng THỨ HAI, ở mức LẦN THỰC THI: nó thấy được thứ một
việc đơn lẻ không thấy — ví dụ cả năm bước đều "ok" mà không bước nào chạm
đĩa.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.ke_hoach import BuocKeHoach, CheDoGhi
from scripts.control_center.execution.y_dinh import khong_suy_nghi


class MucBangChung(str, Enum):
    DU = "DU"
    CHUA_DU = "CHUA_DU"
    MAU_THUAN = "MAU_THUAN"

    @property
    def cho_di_tiep(self) -> bool:
        return self is MucBangChung.DU


class TrangThaiXacMinh(str, Enum):
    """Phán quyết KIỂM ĐỊNH của một bước hoặc cả lần thực thi."""

    CHUA_KIEM = "CHUA_KIEM"
    DAT = "DAT"
    KHONG_DAT = "KHONG_DAT"
    THIEU_BANG_CHUNG = "THIEU_BANG_CHUNG"
    #: Đã kiểm nhưng KHÔNG có phản biện độc lập khác họ model. Trung thực
    #: hơn `DAT`, và §7 đòi đúng chữ này: *"If independent review is
    #: unavailable, say DEGRADED."*
    SUY_GIAM = "SUY_GIAM"

    @property
    def dat(self) -> bool:
        return self in (TrangThaiXacMinh.DAT, TrangThaiXacMinh.SUY_GIAM)


def _ds(v: Any, *, toi_da: int = 60, dai: int = 400) -> Tuple[str, ...]:
    if isinstance(v, str):
        v = [v]
    ra: List[str] = []
    for x in (v or ()):
        s = khong_suy_nghi(x, toi_da=dai)
        if s and s not in ra:
            ra.append(s)
        if len(ra) >= toi_da:
            break
    return tuple(ra)


@dataclass
class HopDongKetQua:
    """Thứ MỘT bước trả về. Mọi trường đều có thể rỗng — trừ `task_id`."""

    task_id: str
    buoc_id: str = ""
    status: str = "failed"              # ok | failed | blocked | timeout | cancelled
    summary: str = ""
    artifacts: Tuple[str, ...] = ()
    files_changed: Tuple[str, ...] = ()
    tests_run: Dict = field(default_factory=dict)
    evidence: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    known_limitations: Tuple[str, ...] = ()
    mutation_summary: str = ""
    follow_up_needed: Tuple[str, ...] = ()

    #: Nguồn gốc định tuyến — §18 đòi ghi lại, và §19 đọc để tính chi phí.
    provider: str = ""
    model: str = ""
    runtime_id: str = ""
    duration: float = 0.0
    exit_code: Optional[int] = None
    commit: str = ""
    branch: str = ""
    raw_log_ref: str = ""
    #: WORKTREE mà bước này thực sự chạy trong đó. Bắt buộc cho kiểm định —
    #: xem `dieu_phoi.BoDieuPhoi._moi_gioi_cua`. Agent ghi vào worktree cô
    #: lập, nên chạy `git status` ở gốc kho sẽ thấy MỘT CÂY SẠCH và mọi phép
    #: kiểm "có thay đổi không" đều trả lời SAI. Đã vấp thật ở lát cắt dọc
    #: đầu tiên của V0.9: bốn bài kiểm kẹt vì lý do đó.
    worktree: str = ""
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not str(self.task_id or "").strip():
            raise ValueError("HopDongKetQua: thiếu `task_id`")
        self.summary = khong_suy_nghi(self.summary, toi_da=3000)
        self.mutation_summary = khong_suy_nghi(self.mutation_summary,
                                               toi_da=1200)
        self.artifacts = _ds(self.artifacts)
        self.files_changed = _ds(self.files_changed)
        self.evidence = _ds(self.evidence)
        self.warnings = _ds(self.warnings)
        self.known_limitations = _ds(self.known_limitations)
        self.follow_up_needed = _ds(self.follow_up_needed)
        self.tests_run = dict(self.tests_run or {})

    # ---------------------------------------------------------- tinh chat --

    @property
    def ok(self) -> bool:
        return str(self.status or "").strip().lower() == "ok"

    @property
    def co_test(self) -> bool:
        t = self.tests_run or {}
        try:
            return bool(t.get("ran")) or int(t.get("passed") or 0) > 0
        except (TypeError, ValueError):
            return False

    @property
    def test_hong(self) -> bool:
        try:
            return int((self.tests_run or {}).get("failed") or 0) > 0
        except (TypeError, ValueError):
            return False

    @property
    def rong(self) -> bool:
        """Lượt KHÔNG sinh ra gì. "No output produced" — §6."""
        return not (self.summary.strip() or self.artifacts
                    or self.files_changed or self.evidence
                    or self.co_test or self.commit)

    @property
    def chua_chay(self) -> bool:
        """KHÔNG CÓ LƯỢT NÀO — khác hẳn "có lượt nhưng lượt đó rỗng".

        `rong` một mình KHÔNG phân biệt được hai chuyện rất khác nhau:

        1. Agent đã chạy thật và trả về rỗng (headless tự chối một công cụ,
           lượt bị cắt, tiến trình chết) — đó là chuyện của NHÀ CUNG CẤP.
        2. Chưa hề có agent nào được giao việc — hết khe phiên, hết lease,
           xếp hàng mãi không tới lượt. Không nhà cung cấp nào được gọi.

        Phân biệt bằng dấu vết ĐỊNH TUYẾN: chỉ khi một lượt thật sự được
        gửi đi thì `provider`/`model`/`runtime_id` mới được điền và `duration`
        mới khác 0. Rỗng SẠCH cả ba trường đó nghĩa là không có lượt nào.

        Vì sao phải tách: gộp chúng lại đã làm cả một vòng chẩn đoán đi sai
        hướng — báo cáo kết luận "provider hỏng, phải giảm phụ thuộc nhà cung
        cấp" trong khi lần chạy đó KHÔNG gọi provider lần nào; thứ hỏng là
        luật cấp khe phiên (`sessions.py` luật 2b).
        """
        return (self.rong and not str(self.provider or "").strip()
                and not str(self.model or "").strip()
                and not str(self.runtime_id or "").strip()
                and not (self.duration or 0) > 0
                and self.exit_code is None)

    def to_dict(self) -> Dict:
        return {"task_id": self.task_id, "buoc_id": self.buoc_id,
                "status": self.status, "summary": self.summary,
                "artifacts": list(self.artifacts),
                "files_changed": list(self.files_changed),
                "tests_run": dict(self.tests_run),
                "evidence": list(self.evidence),
                "warnings": list(self.warnings),
                "known_limitations": list(self.known_limitations),
                "mutation_summary": self.mutation_summary,
                "follow_up_needed": list(self.follow_up_needed),
                "provider": self.provider, "model": self.model,
                "runtime_id": self.runtime_id,
                "duration": round(float(self.duration or 0.0), 2),
                "exit_code": self.exit_code, "commit": self.commit,
                "branch": self.branch, "raw_log_ref": self.raw_log_ref,
                "worktree": self.worktree, "ts": self.ts}

    @classmethod
    def tu_dict(cls, d: Dict) -> "HopDongKetQua":
        d = dict(d or {})
        return cls(task_id=str(d.get("task_id") or ""),
                   buoc_id=str(d.get("buoc_id") or ""),
                   status=str(d.get("status") or "failed"),
                   summary=str(d.get("summary") or ""),
                   artifacts=tuple(d.get("artifacts") or ()),
                   files_changed=tuple(d.get("files_changed") or ()),
                   tests_run=dict(d.get("tests_run") or {}),
                   evidence=tuple(d.get("evidence") or ()),
                   warnings=tuple(d.get("warnings") or ()),
                   known_limitations=tuple(d.get("known_limitations") or ()),
                   mutation_summary=str(d.get("mutation_summary") or ""),
                   follow_up_needed=tuple(d.get("follow_up_needed") or ()),
                   provider=str(d.get("provider") or ""),
                   model=str(d.get("model") or ""),
                   runtime_id=str(d.get("runtime_id") or ""),
                   duration=float(d.get("duration") or 0.0),
                   exit_code=d.get("exit_code"),
                   commit=str(d.get("commit") or ""),
                   branch=str(d.get("branch") or ""),
                   raw_log_ref=str(d.get("raw_log_ref") or ""),
                   worktree=str(d.get("worktree") or ""),
                   ts=float(d.get("ts") or time.time()))


def tu_envelope(pb: Any, *, buoc_id: str = "",
                bang_chung_them: Sequence[str] = ()) -> HopDongKetQua:
    """`ResultEnvelope` của Router V4 -> hợp đồng kết quả của V0.9.

    MỘT chỗ duy nhất làm ánh xạ này, cùng lý do `model.map_envelope_status`
    tồn tại: rải rác thì hai tầng sẽ lệch nhau lúc nào không biết.

    `exit_code` cố ý KHÔNG được suy từ `status`. Nó là thứ mà §6 nói KHÔNG
    phải bằng chứng, nên để trống còn trung thực hơn là điền một số bịa.
    """
    t = getattr(pb, "tests", None)
    tests = t.to_dict() if hasattr(t, "to_dict") else dict(t or {})
    bc = list(bang_chung_them)
    ref = str(getattr(pb, "raw_log_ref", "") or "")
    if ref:
        bc.append(f"log:{ref}")
    if getattr(pb, "commit", ""):
        bc.append(f"commit:{pb.commit}")
    return HopDongKetQua(
        task_id=str(getattr(pb, "task_id", "") or "?"),
        buoc_id=buoc_id,
        status=str(getattr(pb, "status", "failed") or "failed"),
        summary=str(getattr(pb, "summary", "") or ""),
        artifacts=tuple(getattr(pb, "artifacts", ()) or ()),
        files_changed=tuple(getattr(pb, "changes", ()) or ()),
        tests_run=tests,
        evidence=tuple(bc),
        warnings=tuple(getattr(pb, "warnings", ()) or ()),
        known_limitations=tuple(getattr(pb, "risks", ()) or ()),
        mutation_summary="; ".join(str(x) for x in
                                   (getattr(pb, "changes", ()) or ()))[:1200],
        follow_up_needed=tuple(getattr(pb, "followups", ()) or ()),
        provider=str(getattr(pb, "provider", "") or ""),
        model=str(getattr(pb, "model", "") or ""),
        runtime_id=str(getattr(pb, "worker", "") or ""),
        duration=float(getattr(pb, "duration", 0.0) or 0.0),
        commit=str(getattr(pb, "commit", "") or ""),
        branch=str(getattr(pb, "branch", "") or ""),
        raw_log_ref=ref)


@dataclass(frozen=True)
class PhanQuyetBangChung:
    muc: MucBangChung
    thieu: Tuple[str, ...] = ()
    ly_do: str = ""

    def to_dict(self) -> Dict:
        return {"muc": self.muc.value, "thieu": list(self.thieu),
                "ly_do": self.ly_do}


def du_bang_chung(kq: HopDongKetQua,
                  buoc: Optional[BuocKeHoach] = None) -> PhanQuyetBangChung:
    """Lời khai này có ĐỦ BẰNG CHỨNG không? Tất định, không LLM.

    Luật, theo thứ tự kiểm:

    1. `status != ok` -> không phải việc của hàm này; trả `DU` để tầng trên
       xử theo trạng thái thật. (Một việc `failed` không cần chứng minh là
       nó hỏng.)
    2. Lượt RỖNG -> `CHUA_DU`. Đây là câu *"No output produced is not DONE"*.
    3. Bước GHI mà không tệp nào đổi, không artifact, không commit ->
       `CHUA_DU`. Một bước ghi không chạm đĩa thì chưa chứng minh được gì.
    4. Khai sửa tệp mà `mutation_summary` rỗng VÀ không artifact nào ->
       không sao; `files_changed` tự nó đã là bằng chứng.
    5. Bước có `artifact_mong_doi` mà không artifact nào khớp -> `CHUA_DU`,
       và `thieu` nêu ĐÍCH DANH artifact nào — không chỉ đếm.
    6. Test khai có chạy mà `failed > 0` -> `MAU_THUAN` khi `status == ok`.
    """
    if not kq.ok:
        return PhanQuyetBangChung(MucBangChung.DU,
                                  ly_do="không khai `ok` — không phải DONE giả")
    if kq.rong:
        return PhanQuyetBangChung(
            MucBangChung.CHUA_DU, thieu=("mọi thứ",),
            ly_do=("worker khai `ok` nhưng lượt KHÔNG sinh ra gì: không tóm "
                   "tắt, không tệp đổi, không artifact, không test, không "
                   "commit. \"No output produced\" không phải DONE."))
    if kq.test_hong:
        return PhanQuyetBangChung(
            MucBangChung.MAU_THUAN, thieu=("test",),
            ly_do=(f"khai `ok` nhưng {kq.tests_run.get('failed')} bài kiểm "
                   f"HỎNG — lời khai chống lại chính nó"))

    thieu: List[str] = []
    if buoc is not None:
        if buoc.che_do_ghi is CheDoGhi.GHI and not (
                kq.files_changed or kq.artifacts or kq.commit):
            thieu.append("thay đổi trên đĩa (bước GHI)")
        con = [a for a in buoc.artifact_mong_doi
               if not any(_khop_artifact(a, x)
                          for x in list(kq.artifacts) + list(kq.files_changed))]
        thieu += [f"artifact `{a}`" for a in con]
    if thieu:
        return PhanQuyetBangChung(
            MucBangChung.CHUA_DU, thieu=tuple(thieu),
            ly_do=("worker khai `ok` nhưng thiếu bằng chứng ĐÍCH DANH: "
                   + ", ".join(thieu)))
    return PhanQuyetBangChung(MucBangChung.DU, ly_do="bằng chứng khớp loại bước")


def _khop_artifact(mong: str, co: str) -> bool:
    a = str(mong or "").replace("\\", "/").strip("/").lower()
    b = str(co or "").replace("\\", "/").strip("/").lower()
    if not a or not b:
        return False
    return a == b or b.endswith("/" + a) or a.endswith("/" + b) or a in b

# -*- coding: utf-8 -*-
"""BUS SỰ KIỆN CÓ KIỂU cho Team Activity — V1.0 (B7).

Backend dùng SỰ KIỆN CÓ KIỂU. Giao diện sau này có thể vẽ chúng ra trông như
một cuộc hội thoại, nhưng **không có chat tự do giữa các agent**: mỗi sự kiện
là một bản ghi có hình dạng cố định, có nguồn gốc, và có trần kích thước.

VÌ SAO KHÔNG PHẢI CHAT TỰ DO: một nhóm agent nói chuyện không giới hạn sinh
ra token vô hạn, không kiểm được, không phát lại được, và không ai truy ra
được quyết định đến từ đâu. Sự kiện có kiểu thì phát lại được, lọc được, và
mỗi cái trỏ về bằng chứng.

MỌI sự kiện BẮT BUỘC có: dự án, vai/agent, thời điểm. `execution` để rỗng
được (một sự cố có thể xảy ra ngoài một lần thực thi), nhưng dự án thì không.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class LoaiSuKien(str, Enum):
    PROPOSAL = "PROPOSAL"
    CHALLENGE = "CHALLENGE"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESULT = "TASK_RESULT"
    INCIDENT = "INCIDENT"
    REPAIR = "REPAIR"
    REVIEW = "REVIEW"
    BLOCKER = "BLOCKER"
    ESCALATION = "ESCALATION"


#: Trần kích thước THÂN sự kiện. Một sự kiện là một BẢN GHI, không phải một
#: nơi đổ nhật ký: thứ dài thì để trên đĩa và trỏ tới bằng `bang_chung`.
TRAN_THAN = 4000


@dataclass(frozen=True)
class SuKienDoi:
    """Một sự kiện trong dòng hoạt động của đội. Bất biến."""

    loai: LoaiSuKien
    project_id: str
    vai: str                                  # vai hoặc agent/runtime id
    than: str = ""
    execution_id: str = ""
    task_id: str = ""
    #: Tham chiếu BẰNG CHỨNG: đường dẫn, task_id, log ref, commit…
    bang_chung: Tuple[str, ...] = ()
    ts: float = field(default_factory=time.time)
    su_kien_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self):
        if not str(self.project_id or "").strip():
            raise ValueError("sự kiện đội PHẢI có project_id — không có dự án "
                             "thì không truy được nguồn gốc")
        if not str(self.vai or "").strip():
            raise ValueError("sự kiện đội PHẢI có vai/agent")
        if len(self.than or "") > TRAN_THAN:
            object.__setattr__(self, "than",
                               (self.than[:TRAN_THAN] + "…(cắt)"))

    def to_dict(self) -> Dict:
        return {"su_kien_id": self.su_kien_id, "loai": self.loai.value,
                "project_id": self.project_id, "vai": self.vai,
                "execution_id": self.execution_id, "task_id": self.task_id,
                "than": self.than, "bang_chung": list(self.bang_chung),
                "ts": self.ts}


class BusSuKien:
    """Nơi ghi và đọc sự kiện đội.

    Ghi vào sổ sự kiện CHUNG của Control Center khi có `store` — để không
    dựng một kho thứ hai cho cùng loại sự thật. Không có `store` thì giữ
    trong bộ nhớ (dùng cho bài kiểm).
    """

    def __init__(self, store=None, *, kind: str = "TEAM_EVENT"):
        self.store = store
        self.kind = kind
        self._trong_bo_nho: List[SuKienDoi] = []

    def phat(self, sk: SuKienDoi) -> SuKienDoi:
        self._trong_bo_nho.append(sk)
        if self.store is not None:
            try:
                self.store.ghi_su_kien(
                    self.kind, project_id=sk.project_id,
                    task_id=sk.task_id or "",
                    detail=f"{sk.loai.value}[{sk.vai}] {sk.than}"[:300],
                    meta=sk.to_dict())
            except Exception:                                 # noqa: BLE001
                # Mot bus su kien hong KHONG duoc lam chet duong thuc thi.
                pass
        return sk

    def doc(self, *, project_id: str = "", execution_id: str = "",
            loai: Optional[Sequence[LoaiSuKien]] = None,
            limit: int = 200) -> List[SuKienDoi]:
        ra = list(self._trong_bo_nho)
        if project_id:
            ra = [x for x in ra if x.project_id == project_id]
        if execution_id:
            ra = [x for x in ra if x.execution_id == execution_id]
        if loai:
            hop = {l for l in loai}
            ra = [x for x in ra if x.loai in hop]
        return ra[-limit:]

    # -- tien ich dung nhieu ------------------------------------------------

    def de_xuat(self, project_id: str, vai: str, than: str, **kw) -> SuKienDoi:
        return self.phat(SuKienDoi(LoaiSuKien.PROPOSAL, project_id, vai,
                                   than, **kw))

    def quyet_dinh(self, project_id: str, vai: str, than: str,
                   **kw) -> SuKienDoi:
        return self.phat(SuKienDoi(LoaiSuKien.DECISION, project_id, vai,
                                   than, **kw))

    def su_co(self, project_id: str, vai: str, than: str, **kw) -> SuKienDoi:
        return self.phat(SuKienDoi(LoaiSuKien.INCIDENT, project_id, vai,
                                   than, **kw))

    def sua_chua(self, project_id: str, vai: str, than: str,
                 **kw) -> SuKienDoi:
        return self.phat(SuKienDoi(LoaiSuKien.REPAIR, project_id, vai,
                                   than, **kw))

    def leo_thang(self, project_id: str, vai: str, than: str,
                  **kw) -> SuKienDoi:
        return self.phat(SuKienDoi(LoaiSuKien.ESCALATION, project_id, vai,
                                   than, **kw))

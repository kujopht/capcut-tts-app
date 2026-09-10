"""Người ghi — nghe ba chốt ghi của `ControlStore`, không sửa 60 chỗ gọi.

`engine.py` gọi `store.ghi_su_kien()` ~60 lần, `store.them_chat()` ~8 lần,
và mọi chuyển trạng thái việc đi qua `store.doi_trang_thai()` — hàm này
lại tự gọi `ghi_su_kien("TASK_STATE")`. Nên chỉ cần nghe HAI chốt:

    store.ghi_su_kien  -> mọi sự kiện, kể cả TASK_STATE/TASK_CREATED/
                          LEADER_DECISION/LIVE_PROBE/WORKER_*
    store.them_chat    -> mọi tin nhắn người dùng và Leader

`ControlStore.dang_ky_nguoi_theo()` gọi người ghi TRONG một `try/except`
nuốt mọi thứ: người ghi hỏng thì sổ chính vẫn ghi xong. Người ghi cũng tự
bọc — hai lớp, vì đây đúng là chỗ "ký ức không được giết Router".

CHƯNG CẤT TẤT ĐỊNH, KHÔNG LLM. Từ L0 ra L1 theo LUẬT, không theo model:
một việc DONE thành một ký ức episodic; FAILED thành incident; một lần
LIVE_PROBE thành episodic điểm thấp — ghi rõ đó là kết quả đo ĐÃ CŨ. Cách
này bỏ lỡ những thứ cần hiểu ngữ nghĩa mới thấy, nhưng nó không tốn quota,
không bịa, và lặp lại được trong bài kiểm. Quyết định/kiến trúc/quy trình
thì do NGƯỜI hoặc Leader ghi tường minh qua API — không tự suy từ chat,
vì một câu "tôi nghĩ nên..." không phải một quyết định.

KHÔNG có bí mật: người ghi chuyển văn bản qua kho, và kho lọc ở cổng vào.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from scripts.control_center.memory.model import (BangChung, KyUc, LoaiKyUc,
                                                 SuKien, TinCay)

#: Su kien cua store KHONG di vao ky uc: tieng on nhip (heartbeat, poll).
BO_QUA = {"FABRIC_PROBED", "LOCK_RENEWED", "SESSION_HEARTBEAT",
          "MEMORY_RECORDED", "MEMORY_CHECKPOINT", "MEMORY_ERROR",
          "MEMORY_CONTEXT", "MEMORY_UNAVAILABLE", "MEMORY_RESUMED",
          "ENGINE_STOPPED"}

#: Quan trong mac dinh theo loai su kien (1..10). Con lai = 4.
QUAN_TRONG = {
    "TASK_CREATED": 5, "TASK_STATE": 5, "WORKER_DONE": 6, "WORKER_FAILED": 7,
    "TASK_FAILED": 7, "GATE_REASSERTED": 6, "LEADER_DECISION": 4,
    "LIVE_PROBE": 3, "LIVE_PROBE_FAILED": 4, "PROJECT_ADDED": 6,
    "ATTACHMENT_REJECTED": 3, "LEADER_UNAVAILABLE": 5,
}


class NguoiGhi:
    """Chuyển sự kiện của sổ chính thành lịch sử L0 + ký ức L1 (khi đáng)."""

    def __init__(self, dich_vu):
        self.dv = dich_vu
        self.so_loi = 0
        self.loi_cuoi = ""
        self.so_ghi = 0

    # -- diem vao tu store --------------------------------------------------

    def __call__(self, loai: str, **kw) -> None:
        """Chốt gọi từ `ControlStore._bao`. KHÔNG BAO GIỜ ném."""
        try:
            if loai == "su_kien":
                self._su_kien(**kw)
            elif loai == "chat":
                self._chat(**kw)
        except Exception as exc:                            # noqa: BLE001
            self.so_loi += 1
            self.loi_cuoi = f"{type(exc).__name__}: {exc}"[:200]

    # -- su kien ------------------------------------------------------------

    def _su_kien(self, *, kind: str = "", project_id: str = "", task_id: str = "",
                 session_id: str = "", level: str = "", detail: str = "",
                 meta: Optional[Dict[str, Any]] = None, eid: int = 0) -> None:
        if not project_id or kind in BO_QUA:
            return
        p = self.dv.provider(project_id)
        if p is None:
            return
        meta = dict(meta or {})
        sk = SuKien(loai=f"event:{kind}", ts=time.time(), tom_tat=detail or kind,
                    nguon="store.event", task_id=task_id, session_id=session_id,
                    tham_chieu=str(eid or ""), meta={"level": level, **meta})
        sk = p.ghi_su_kien(sk)
        if sk is None:
            return
        self.so_ghi += 1
        self._chung_cat(p, project_id, kind, sk, task_id, detail, meta)

    def _chung_cat(self, p, project_id: str, kind: str, sk: SuKien,
                   task_id: str, detail: str, meta: Dict[str, Any]) -> None:
        """L0 -> L1 theo luật. Chỉ những gì đáng nhớ lâu hơn một dòng log."""
        qt = QUAN_TRONG.get(kind, 0)
        bc = (BangChung(su_kien_id=sk.id, blob_sha=sk.blob_sha,
                        ghi_chu=f"event:{kind}"),)
        if kind == "TASK_STATE":
            den = str(meta.get("to") or "")
            if den == "DONE":
                p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=6,
                                 tin_cay=TinCay.DO_DUOC,
                                 tieu_de=f"việc {task_id} hoàn thành",
                                 noi_dung=f"Việc {task_id} chuyển {meta.get('from')} "
                                          f"-> DONE. {detail}",
                                 the=("task", "done"), bang_chung=bc,
                                 meta={"task_id": task_id}))
                self.dv.diem_dung_tu_dong(project_id, f"việc {task_id} DONE",
                                          task_id=task_id)
            elif den == "FAILED":
                p.luu_ky_uc(KyUc(loai=LoaiKyUc.INCIDENT, quan_trong=7,
                                 tin_cay=TinCay.DO_DUOC,
                                 tieu_de=f"việc {task_id} thất bại",
                                 noi_dung=f"Việc {task_id} FAILED. {detail}",
                                 the=("task", "failed", "incident"),
                                 bang_chung=bc, meta={"task_id": task_id}))
                self.dv.diem_dung_tu_dong(project_id, f"việc {task_id} FAILED",
                                          task_id=task_id)
            elif den == "BLOCKED":
                p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=5,
                                 tin_cay=TinCay.DO_DUOC,
                                 tieu_de=f"việc {task_id} bị chặn (GATED)",
                                 noi_dung=f"Việc {task_id} BLOCKED. {detail}",
                                 the=("task", "blocked", "gate"),
                                 bang_chung=bc, meta={"task_id": task_id}))
            return
        if kind == "TASK_CREATED":
            p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=5,
                             tin_cay=TinCay.DO_DUOC,
                             tieu_de=f"tạo việc {task_id}",
                             noi_dung=f"Tạo việc {task_id}: {detail}",
                             the=("task", "created"), bang_chung=bc,
                             meta={"task_id": task_id,
                                   "permission": meta.get("permission", "")}))
            return
        if kind == "LIVE_PROBE":
            # KY UC VE MOT LAN DO, KHONG PHAI TRANG THAI HIEN TAI. Tieu de
            # noi thang dieu do, de Leader khong doc no thanh "dang chay".
            p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=3,
                             tin_cay=TinCay.DO_DUOC,
                             tieu_de="kết quả một lần đo sống (ĐÃ CŨ)",
                             noi_dung=f"Lúc đó live probe cho: {detail}. "
                                      f"Đây là lịch sử — trạng thái hiện tại "
                                      f"phải đo lại.",
                             the=("live_probe", "lich_su"), bang_chung=bc,
                             han_tuoi=7 * 24 * 3600.0))
            return
        if kind in ("LIVE_PROBE_FAILED", "LEADER_UNAVAILABLE", "GATE_REASSERTED",
                    "FABRIC_PROBE_FAILED"):
            p.luu_ky_uc(KyUc(loai=LoaiKyUc.INCIDENT, quan_trong=qt or 5,
                             tin_cay=TinCay.DO_DUOC, tieu_de=kind.lower(),
                             noi_dung=f"{kind}: {detail}", the=("incident",),
                             bang_chung=bc))
            return
        if kind == "LEADER_DECISION" and str(meta.get("y_dinh")) == "WORK":
            p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=4,
                             tin_cay=TinCay.GHI_NHAN,
                             tieu_de="Leader uỷ thác việc",
                             noi_dung=f"Leader quyết WORK: {detail}",
                             the=("leader", "work"), bang_chung=bc))
            return
        if kind == "PROJECT_ADDED":
            p.luu_ky_uc(KyUc(loai=LoaiKyUc.SEMANTIC, quan_trong=6,
                             tin_cay=TinCay.DO_DUOC, tieu_de="dự án được thêm",
                             noi_dung=f"Dự án {project_id} được thêm vào Control "
                                      f"Center. {detail}", the=("project",),
                             bang_chung=bc))

    # -- chat ---------------------------------------------------------------

    def _chat(self, *, project_id: str = "", role: str = "", text: str = "",
              message_id: int = 0, meta: Optional[Dict[str, Any]] = None) -> None:
        if not project_id:
            return
        p = self.dv.provider(project_id)
        if p is None:
            return
        meta = dict(meta or {})
        loai = "chat_user" if role == "user" else "chat_assistant"
        sk = p.ghi_su_kien(
            SuKien(loai=loai, ts=time.time(), tom_tat=text or "",
                   nguon="store.chat", tham_chieu=str(message_id or ""),
                   meta={"role": role, "loai_tin": str(meta.get("loai") or "")}),
            noi_dung_day=text or "")
        if sk is None:
            return
        self.so_ghi += 1
        # Ket qua worker bao ve chat: dang nho, keo theo bang chung day.
        if role != "user" and str(meta.get("loai")) == "ket_qua":
            p.luu_ky_uc(KyUc(
                loai=LoaiKyUc.EPISODIC, quan_trong=6, tin_cay=TinCay.GHI_NHAN,
                tieu_de=f"kết quả việc {meta.get('task_id', '')}".strip(),
                noi_dung=(text or "")[:1500],
                the=("ket_qua", str(meta.get("state") or "").lower()),
                bang_chung=(BangChung(su_kien_id=sk.id, blob_sha=sk.blob_sha,
                                      ghi_chu="chat:ket_qua"),),
                meta={"task_id": meta.get("task_id", ""),
                      "state": meta.get("state", "")}))

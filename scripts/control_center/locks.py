"""Khoá tài nguyên + phát hiện xung đột — Control Center V0.1, yêu cầu #6.

BÀI TOÁN, đúng như đề bài:

    Việc A đang sở hữu   web/admin/content-queue
    Việc B muốn          web/admin/content-queue
    => B phải CHỜ, không được chạy đua.

VÌ SAO KHÔNG DÙNG LẠI `router_v4/leases.py`: lease của V4 khoá **khe của
một runtime** ("AG01#0") — nó trả lời "tài khoản này còn chỗ chạy không".
Đó là câu hỏi khác hẳn "thư mục này có ai đang ghi không". Hai việc chạy
trên HAI tài khoản khác nhau vẫn giẫm lên cùng một thư mục, và lease của V4
sẽ vui vẻ cho cả hai chạy. Hai tầng khoá cho hai loại tài nguyên, không
tầng nào thay được tầng kia.

BA LỚP, và chúng KHÔNG cùng luật:

    FILESYSTEM  xung đột theo **giao nhau tiền tố đường dẫn**. `web/admin`
                xung đột với `web/admin/content-queue` theo CẢ HAI chiều —
                cha chặn con, con chặn cha. Chỉ so bằng nhau là để lọt đúng
                trường hợp hay gặp nhất.
    SERVICE     xung đột khi TRÙNG KHỚP định danh dịch vụ.
    PRODUCTION  như SERVICE, cộng thêm: **không bao giờ tự thu hồi**.

VÌ SAO KHOÁ PRODUCTION KHÔNG TỰ HẾT HẠN:

Khoá có hạn tồn tại để một tiến trình chết không khoá hệ thống vĩnh viễn.
Đánh đổi đó đúng cho worktree; nó SAI cho production. Một khoá production
hết hạn có hai khả năng — tiến trình đã chết, hoặc một thao tác production
đang chạy lâu hơn dự kiến. Đoán sai khả năng thứ hai nghĩa là để việc thứ
hai chạy vào giữa một lần cutover. Nên `reclaim()` chỉ đụng FILESYSTEM và
SERVICE; khoá production hết hạn được BÁO CÁO cho người, và chỉ người mới
gỡ được.

Đây cũng là hiện thân của luật "agent không được tự vượt cổng người dùng
đặt ra" — hết hạn không phải là sự cho phép.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.control_center.model import LockKind, ResourceLock
from scripts.control_center.store import ControlStore

#: Han mac dinh cua mot khoa FILESYSTEM/SERVICE. Phai lon hon mot luot agent
#: dien hinh; nho hon mot dem.
LOCK_TTL = 3600.0


def chuan_hoa(resource: str) -> str:
    """Chuẩn hoá định danh tài nguyên trước khi so sánh.

    Không chuẩn hoá thì `web/admin/`, `web\\admin` và `/web/admin` thành ba
    tài nguyên khác nhau, và hai việc cùng ghi một thư mục sẽ cùng lấy được
    khoá — đúng chế độ hỏng mà module này tồn tại để chặn.
    """
    return str(resource or "").strip().replace("\\", "/").strip("/").lower()


def xung_dot(kind: LockKind, a: str, b: str) -> bool:
    """Hai tài nguyên cùng lớp có tranh chấp nhau không.

    FILESYSTEM dùng giao nhau tiền tố THEO ĐOẠN. So chuỗi trần
    (`b.startswith(a)`) sẽ báo `web/admin` xung đột với `web/administration`
    — hai thư mục hoàn toàn khác nhau — nên phải so theo dấu `/`.
    """
    x, y = chuan_hoa(a), chuan_hoa(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if kind is not LockKind.FILESYSTEM:
        return False
    return x.startswith(y + "/") or y.startswith(x + "/")


def lock_id_cua(project_id: str, kind: LockKind, resource: str) -> str:
    return f"{project_id}:{kind.value}:{chuan_hoa(resource)}"


@dataclass(frozen=True)
class LockGrant:
    """Kết quả xin khoá. `granted=False` nghĩa là PHẢI chờ, không phải lỗi."""

    granted: bool
    locks: Tuple[ResourceLock, ...] = ()
    conflict_resource: str = ""
    conflict_holder_task: str = ""
    conflict_kind: Optional[LockKind] = None
    reason: str = ""

    def to_dict(self) -> Dict:
        return {"granted": self.granted,
                "locks": [l.lock_id for l in self.locks],
                "conflict_resource": self.conflict_resource,
                "conflict_holder_task": self.conflict_holder_task,
                "conflict_kind": (self.conflict_kind.value
                                  if self.conflict_kind else ""),
                "reason": self.reason}


class LockManager:
    """Quản lý khoá tài nguyên. Mọi trạng thái nằm trong `ControlStore`.

    KHÔNG giữ trạng thái trong bộ nhớ: hai tiến trình (TUI và CLI) cùng chạy
    là chuyện bình thường trong kho này, và một bộ khoá trong RAM sẽ để
    tiến trình thứ hai không thấy khoá của tiến trình thứ nhất.
    """

    def __init__(self, store: ControlStore, *, ttl: float = LOCK_TTL):
        self.store = store
        self.ttl = ttl

    # -- truy van -----------------------------------------------------------

    def dang_giu(self, project_id: str = "") -> List[ResourceLock]:
        return self.store.locks(project_id)

    def tim_xung_dot(self, project_id: str, kind: LockKind, resource: str, *,
                     bo_qua_task: str = "",
                     now: Optional[float] = None) -> Optional[ResourceLock]:
        """Khoá ĐANG SỐNG nào tranh chấp với `resource`.

        Khoá đã hết hạn của lớp tự thu hồi được coi như không tồn tại — nếu
        không, một tiến trình chết sẽ chặn vĩnh viễn. Khoá production hết
        hạn thì VẪN TÍNH LÀ XUNG ĐỘT: xem docstring module.
        """
        curr = time.time() if now is None else now
        for l in self.store.locks(project_id):
            if l.kind is not kind:
                continue
            if bo_qua_task and l.holder_task == bo_qua_task:
                continue
            if not l.con_han(now=curr) and l.kind.tu_thu_hoi_duoc:
                continue
            if xung_dot(kind, resource, l.resource):
                return l
        return None

    # -- xin / tra ----------------------------------------------------------

    def xin(self, project_id: str, requests: Sequence[Tuple[LockKind, str]], *,
            task_id: str, session_id: str = "",
            ttl: Optional[float] = None) -> LockGrant:
        """Xin MỘT TẬP khoá — tất cả hoặc không cái nào.

        NGUYÊN TỬ THEO TẬP có chủ đích: cấp lẻ từng cái sẽ tạo ra ôm khoá
        một phần, và hai việc mỗi cái ôm một nửa tập của nhau là định nghĩa
        của deadlock. Ở đây, không lấy đủ thì trả lại sạch và CHỜ.

        Thứ tự xin được SẮP XẾP (không theo thứ tự bên gọi truyền vào), nên
        hai việc xin cùng hai tài nguyên luôn xin theo cùng một thứ tự —
        cách chuẩn để hai bên không ôm chéo nhau.
        """
        curr = time.time()
        han = curr + (self.ttl if ttl is None else ttl)
        # Loai trung + sap xep on dinh: chong deadlock kieu om cheo.
        can = sorted({(k, chuan_hoa(r)) for k, r in requests if chuan_hoa(r)},
                     key=lambda x: (x[0].value, x[1]))
        if not can:
            return LockGrant(granted=True)
        # TOAN BO phep "do xung dot roi chen" phai nam trong MOT giao dich
        # ghi. Xem `ControlStore.giao_dich_ghi`: `ON CONFLICT(lock_id)` chi
        # che duoc truong hop hai ben tranh DUNG MOT khoa chinh, con luat
        # giao nhau TIEN TO cua khoa FILESYSTEM sinh ra hai `lock_id` khac
        # nhau cho hai tai nguyen dung nhau that. Da dung lai duoc 3/3 lan.
        with self.store.giao_dich_ghi():
            return self._xin_trong_giao_dich(project_id, can, task_id=task_id,
                                             session_id=session_id, curr=curr,
                                             han=han)

    def _xin_trong_giao_dich(self, project_id: str,
                             can: Sequence[Tuple[LockKind, str]], *,
                             task_id: str, session_id: str,
                             curr: float, han: float) -> LockGrant:
        da_lay: List[ResourceLock] = []

        for kind, res in can:
            va = self.tim_xung_dot(project_id, kind, res, bo_qua_task=task_id,
                                   now=curr)
            if va is not None:
                self._tra_lai(da_lay, task_id)
                self.store.them_waiter(va.lock_id, task_id)
                return LockGrant(
                    granted=False, conflict_resource=va.resource,
                    conflict_holder_task=va.holder_task, conflict_kind=va.kind,
                    reason=(f"{kind.value} {res!r} tranh chấp với khoá "
                            f"{va.kind.value} {va.resource!r} do việc "
                            f"{va.holder_task or '(không rõ)'} đang giữ"))

            l = ResourceLock(
                lock_id=lock_id_cua(project_id, kind, res),
                project_id=project_id, kind=kind, resource=res,
                holder_task=task_id, holder_session=session_id,
                acquired_at=curr,
                # Khoa PRODUCTION CO dau thoi gian het han, nhung no la
                # NGUONG BAO DONG chu khong phai han thue: `tim_xung_dot`
                # van coi khoa production qua han la xung dot, `reclaim`
                # van khong nha no, va `gia_han` khong keo dai no. Muc dich
                # duy nhat cua con so nay la de bang dieu khien noi duoc
                # "khoa production nay da giu qua lau — cutover con chay
                # khong?" thay vi im lang.
                expires_at=han)
            if not self.store.them_lock(l, now=curr):
                # Ai do vua chen dung lock_id nay giua hai buoc. Neu la khoa
                # cua chinh viec nay (thu lai) thi coi nhu da co; khong thi
                # chiu thua va CHO — day la duong dua that su, va thua o day
                # re hon nhieu so voi ghi de.
                dang = next((x for x in self.store.locks(project_id)
                             if x.lock_id == l.lock_id), None)
                if dang is not None and dang.holder_task == task_id:
                    da_lay.append(dang)
                    continue
                self._tra_lai(da_lay, task_id)
                if dang is not None:
                    self.store.them_waiter(dang.lock_id, task_id)
                return LockGrant(
                    granted=False, conflict_resource=res, conflict_kind=kind,
                    conflict_holder_task=(dang.holder_task if dang else ""),
                    reason=f"{kind.value} {res!r} vừa bị việc khác giành mất")
            da_lay.append(l)
            self.store.ghi_su_kien(
                "LOCK_ACQUIRED", project_id=project_id, task_id=task_id,
                session_id=session_id, detail=f"{kind.value} {res}",
                meta={"kind": kind.value, "resource": res})

        self.store.xoa_waiter(task_id)
        return LockGrant(granted=True, locks=tuple(da_lay))

    def _tra_lai(self, locks: Iterable[ResourceLock], task_id: str) -> None:
        for l in locks:
            self.store.xoa_lock(l.lock_id, holder_task=task_id)

    def tra(self, project_id: str, task_id: str) -> int:
        """Trả MỌI khoá của một việc. Trả về số khoá đã nhả.

        Gọi ở `finally`, luôn luôn — một việc hỏng giữa chừng mà không nhả
        khoá sẽ chặn mọi việc sau nó cho tới khi hết hạn (và với PRODUCTION
        thì là mãi mãi).
        """
        n = 0
        for l in self.store.locks(project_id):
            if l.holder_task == task_id and self.store.xoa_lock(
                    l.lock_id, holder_task=task_id):
                n += 1
                self.store.ghi_su_kien(
                    "LOCK_RELEASED", project_id=project_id, task_id=task_id,
                    detail=f"{l.kind.value} {l.resource}")
        self.store.xoa_waiter(task_id)
        return n

    def gia_han(self, project_id: str, task_id: str, *,
                ttl: Optional[float] = None) -> int:
        """Đập nhịp tim cho khoá của một việc đang chạy.

        Việc chạy lâu hơn TTL vẫn phải giữ được khoá của nó; không gia hạn
        thì một việc 2 tiếng sẽ tự mất khoá ở phút thứ 60 và một việc khác
        chen vào giữa.

        KHÔNG gia hạn khoá PRODUCTION có chủ đích: với lớp đó, dấu hết hạn
        là NGƯỠNG BÁO ĐỘNG chứ không phải hạn thuê. Tự đẩy nó ra xa mỗi 20
        giây sẽ làm cảnh báo "khoá production giữ quá lâu" không bao giờ nổ
        — đúng cảnh báo mà người vận hành cần nhất.
        """
        han = time.time() + (self.ttl if ttl is None else ttl)
        n = 0
        for l in self.store.locks(project_id):
            if l.holder_task != task_id or l.kind is LockKind.PRODUCTION:
                continue
            if self.store.gia_han_lock(l.lock_id, han):
                n += 1
        return n

    # -- phuc hoi -----------------------------------------------------------

    def reclaim(self, *, now: Optional[float] = None) -> Dict[str, List[str]]:
        """Dọn khoá CHẾT sau khi khởi động lại.

        Trả về hai danh sách tách bạch:

            `reclaimed` — khoá FILESYSTEM/SERVICE hết hạn, đã nhả.
            `needs_human` — khoá PRODUCTION hết hạn. KHÔNG nhả. Người quyết.

        Trộn hai danh sách này lại là cách một lần khởi động lại vô tình mở
        cổng production.
        """
        curr = time.time() if now is None else now
        da_nha: List[str] = []
        can_nguoi: List[str] = []
        for l in self.store.locks():
            if l.con_han(now=curr):
                continue
            if l.kind.tu_thu_hoi_duoc:
                if self.store.xoa_lock(l.lock_id):
                    da_nha.append(l.lock_id)
                    self.store.ghi_su_kien(
                        "LOCK_RECLAIMED", project_id=l.project_id,
                        task_id=l.holder_task, level="WARNING",
                        detail=f"khoá hết hạn đã thu hồi: {l.kind.value} "
                               f"{l.resource}")
            else:
                can_nguoi.append(l.lock_id)
                self.store.ghi_su_kien(
                    "LOCK_STALE_PRODUCTION", project_id=l.project_id,
                    task_id=l.holder_task, level="ALERT",
                    detail=(f"khoá PRODUCTION {l.resource!r} đã quá hạn nhưng "
                            f"KHÔNG tự thu hồi — cần người xác nhận thao tác "
                            f"production đã kết thúc trước khi gỡ."))
        return {"reclaimed": da_nha, "needs_human": can_nguoi}

    def snapshot(self, project_id: str = "") -> List[Dict]:
        cho = {}
        for w in self.store.waiters():
            cho.setdefault(w["lock_id"], []).append(w["task_id"])
        ra = []
        for l in self.store.locks(project_id):
            d = l.to_dict()
            d["waiters"] = sorted(cho.get(l.lock_id, []))
            ra.append(d)
        return ra

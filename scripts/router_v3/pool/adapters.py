"""Dựng `WorkerAdapter` THẬT từ danh tính — Bể worker tự trị, Phase 5.

Không có giao thức mới nào ở đây. Module này chỉ nối `Identity` (ai) với
adapter đã có (nói chuyện thế nào):

    Transport.NATIVE  + antigravity -> AntigravityNativeAdapter (có sẵn)
    Transport.BRIDGE  + antigravity -> AntigravityBridgeAdapter (có sẵn)
    Transport.HTTP    + opencode    -> OpenCodeAdapter          (có sẵn)
    Transport.CLI     + codex       -> CodexAdapter             (mới, dưới đây)

`CodexAdapter` là adapter duy nhất được viết mới, vì `codex` chưa từng có
một adapter theo hợp đồng chín phương thức — trước đây nó chỉ được gọi
thẳng trong `ai_router_dispatch.py`. Hình dạng lệnh lấy nguyên từ đó
(`codex exec --skip-git-repo-check -`, prompt qua stdin), không phát minh lại.

RÀO CỨNG được nhắc lại trong mã, không chỉ trong tài liệu: `CodexAdapter`
TỪ CHỐI mọi gói việc hình dạng bảo mật. Bằng chứng thật 2026-08-28 — Codex
trả kết quả RỖNG kèm "flagged for possible cybersecurity risk". Một lần
hỏng im lặng tệ hơn một lần từ chối rõ ràng.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from scripts.router_v3.antigravity_adapter import (AntigravityBridgeAdapter,
                                                   AntigravityNativeAdapter)
from scripts.router_v3.opencode_adapter import OpenCodeAdapter
from scripts.router_v3.packet import TaskPacket, TaskResult, parse_result
from scripts.router_v3.pool.identity import Identity, Transport
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.worker_adapter import (HealthReport, TransportKind,
                                              WorkerAdapter)
from scripts.router_v3 import worker_identity

#: Tu khoa lam mot goi viec mang HINH DANG bao mat. Co y RONG hon can:
#: mot lan tu choi nham chi ton mot lan dinh tuyen lai; mot lan gui nham
#: tra ve ket qua rong ma khong ai biet vi sao.
_HINH_DANG_BAO_MAT = ("security", "credential", "auth", "permission", "secret",
                      "token", "bảo mật", "xác thực", "quyền")


def find_codex() -> Optional[str]:
    tren_path = shutil.which("codex") or shutil.which("codex.exe")
    if tren_path:
        return tren_path
    import glob
    import os
    mau = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex",
                       "bin", "*", "codex.exe")
    ung_vien = sorted(glob.glob(mau))
    return ung_vien[-1] if ung_vien else None


class CodexAdapter(WorkerAdapter):
    """Codex CLI theo hợp đồng chín phương thức.

    `cancel()` KHÔNG huỷ được một lượt đang bay giữa chừng: `codex exec` là
    một tiến trình đồng bộ và adapter này giữ tham chiếu tới nó, nên huỷ =
    giết tiến trình. Đó là cách huỷ THẬT duy nhất ở đây, và nó làm mất kết
    quả của lượt đang chạy — ghi rõ thay vì giả vờ huỷ mềm.
    """

    provider = "codex"
    transport = TransportKind.STRUCTURED_CLI

    def __init__(self, worker_id: str, *, timeout: float = 900.0,
                 workspace: str = ""):
        self._worker_id = worker_id
        self._timeout = timeout
        self._workspace = workspace
        self._last: Optional[TaskResult] = None
        self._p: Optional[subprocess.Popen] = None
        self._cancelled = False

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="CODEX",
            capabilities=frozenset({"review", "implement"}),
            max_concurrent=1, auth_realm="codex-cli:default",
            workspace=self._workspace,
            notes="codex exec; KHÔNG BAO GIỜ review bảo mật")

    def health(self) -> HealthReport:
        exe = find_codex()
        if not exe:
            return HealthReport(Health.UNAVAILABLE, "không tìm thấy codex")
        try:
            p = subprocess.run([exe, "login", "status"], capture_output=True,
                               text=True, timeout=30, encoding="utf-8",
                               errors="replace")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return HealthReport(Health.UNAVAILABLE, f"{type(exc).__name__}")
        ra = ((p.stdout or "") + (p.stderr or "")).strip()
        if p.returncode != 0 or "not logged in" in ra.lower():
            return HealthReport(Health.AUTH_REQUIRED, "chưa đăng nhập codex")
        # KHONG in `ra` ra ngoai: no co the chua email/ID tai khoan.
        return HealthReport(Health.HEALTHY, "đã đăng nhập")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        self._cancelled = False
        if workspace:
            self._workspace = str(workspace)
        return find_codex() is not None

    def send_task(self, packet: TaskPacket) -> TaskResult:
        t0 = time.perf_counter()
        van_ban = packet.render()
        thap = van_ban.lower()
        if any(k in thap for k in _HINH_DANG_BAO_MAT):
            return TaskResult(
                task_id=packet.task_id, worker_id=self._worker_id,
                status="blocked", provider=self.provider,
                failure_reason="codex_security_shaped_refusal",
                summary="TỪ CHỐI ở phía Router: gói việc mang hình dạng bảo "
                        "mật và Codex trả kết quả RỖNG cho loại việc này "
                        "(bằng chứng 2026-08-28). Định tuyến sang worker khác.",
                duration_seconds=round(time.perf_counter() - t0, 2))
        exe = find_codex()
        if not exe:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              failure_reason="worker_unavailable",
                              summary="không tìm thấy codex")
        cwd = packet.workspace or self._workspace or None
        argv = [exe, "exec", "--skip-git-repo-check", "-"]
        try:
            self._p = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=cwd, text=True, encoding="utf-8",
                errors="replace")
            out, err = self._p.communicate(input=van_ban, timeout=self._timeout)
            rc = self._p.returncode
        except subprocess.TimeoutExpired:
            self._giet()
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="timeout", provider=self.provider,
                              failure_reason="timeout",
                              summary=f"vượt {self._timeout}s",
                              duration_seconds=round(time.perf_counter() - t0, 2))
        except OSError as exc:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              failure_reason="spawn_failed",
                              summary=f"{type(exc).__name__}: {exc}"[:300],
                              duration_seconds=round(time.perf_counter() - t0, 2))
        finally:
            self._p = None
        giay = time.perf_counter() - t0
        if self._cancelled:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="cancelled", provider=self.provider,
                            failure_reason="cancelled", summary="đã huỷ",
                            duration_seconds=round(giay, 2))
        elif rc != 0 and not (out or "").strip():
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="failed", provider=self.provider,
                            failure_reason=f"exit_{rc}",
                            summary=(err or "")[-300:],
                            duration_seconds=round(giay, 2))
        else:
            kq = parse_result(packet.task_id, self._worker_id, out or "", giay)
            kq.provider = self.provider
        self._last = kq
        return kq

    def _giet(self) -> None:
        p = self._p
        if p is None:
            return
        try:
            p.kill()
        except OSError:
            pass

    def cancel(self) -> None:
        self._cancelled = True
        self._giet()

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        # `codex exec` khong giu hoi thoai giua cac lan goi — moi lan la mot
        # tien trinh moi. Khong co ngu canh de bo, va noi "da reset" cho co
        # se che mat su that do.
        pass

    def shutdown(self) -> None:
        self._giet()
        self._p = None


class AdapterError(RuntimeError):
    pass


class PoolAntigravityAdapter(AntigravityNativeAdapter):
    """`AntigravityNativeAdapter` + quyền TỐI THIỂU theo TỪNG việc.

    Lớp cha nhận `dangerously_skip_permissions` một lần lúc dựng. Bể thì cần
    hai chế độ khác nhau trên CÙNG một danh tính:

        việc CÓ GHI   -> `--mode accept-edits` + `--add-dir <worktree>`
        việc CHỈ ĐỌC  -> KHÔNG cờ quyền nào

    **KHÔNG BAO GIỜ `--dangerously-skip-permissions`.** Cờ đó tự duyệt MỌI
    yêu cầu quyền, gồm cả chạy lệnh shell tuỳ ý — rộng hơn hẳn thứ một việc
    sửa tệp cần. Router V4 cấm nó ở mức chính sách, và `_KHONG_BAO_GIO_DUNG`
    dưới đây chặn nó ở mức mã để một lần "tạm bật cho tiện" về sau không lọt
    qua review.

    ĐÁNH ĐỔI ĐÃ BIẾT, ghi rõ thay vì giấu: `accept-edits` chỉ phủ công cụ
    GHI TỆP. Bằng chứng thật (2026-08-30, `native_worker.py`) cho thấy một
    model đôi khi chọn công cụ LỆNH SHELL để tạo tệp; lượt đó sẽ bị headless
    tự động từ chối và việc trả về "không sửa gì". Đó là hỏng THẤY ĐƯỢC —
    cổng `diff` của `validation.py` bắt đúng trường hợp này và việc được thử
    lại/đổi worker. Một lần hỏng nhìn thấy được đáng giá hơn nhiều so với
    cấp quyền chạy shell tuỳ ý cho mọi việc.
    """

    #: Co bi cam tuyet doi trong Router V4. Kiem o `start_session` chu khong
    #: chi trong tai lieu: mot quy tac an toan khong duoc thuc thi bang ma
    #: chi la mot loi khuyen.
    _KHONG_BAO_GIO_DUNG = ("--dangerously-skip-permissions",)

    #: Luot toi co duoc GHI khong. MAC DINH KHONG.
    #:
    #: Tach khoi `workspace` co chu dich, va day la mot phan biet THAT chu
    #: khong phai kieu cach: mot viec CHI DOC van can `--add-dir` de doc
    #: duoc tep trong kho (thieu no, `agy` khong thay gi ca), nhung no
    #: TUYET DOI khong duoc kem `--mode accept-edits`. Ban dau lop nay suy
    #: quyen ghi tu `bool(workspace)`, nghia la moi viec chi doc muon doc
    #: duoc kho deu vo tinh duoc cap quyen ghi. Fail closed: mac dinh False,
    #: nguoi goi phai NOI RO.
    _cho_ghi: bool = False

    def set_write_mode(self, cho_ghi: bool) -> None:
        self._cho_ghi = bool(cho_ghi)

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        """Dung tien trinh am voi `cwd` DAT VAO workspace.

        Lop cha khong dat `cwd`, nen `agy` ke thua thu muc lam viec cua tien
        trinh Python — thuong la GOC KHO CHINH. Bang chung that (2026-09-03):
        mot worker duoc bao tao `scripts/router_v4/report.py` (duong dan
        TUONG DOI) da giai ra thanh duong dan trong kho chinh, NGOAI
        `--add-dir`, nen lenh ghi bi tu choi va viec "thanh cong" ma khong
        co tep nao. Dat `cwd` = worktree lam duong dan tuong doi roi dung
        cho, va giu moi thao tac ben trong vung da cach ly.
        """
        from scripts.router_v3.warm_pool import RecyclePolicy, WarmAgyWorker
        self._dsp = False
        self._allow_edits = bool(workspace) and self._cho_ghi
        if self._worker is not None:
            self.shutdown()
        self._cancelled = False
        self._worker = WarmAgyWorker(
            self._worker_id, model=self._model, workspace=workspace,
            cwd=workspace or None,
            allow_edits=self._allow_edits,
            dangerously_skip_permissions=False,
            policy=RecyclePolicy(), turn_timeout=self._turn_timeout)
        return self._worker.start()


class MultiSlotAdapter(WorkerAdapter):
    """N bản adapter độc lập dưới MỘT `worker_id`.

    VÌ SAO CẦN: một danh tính Antigravity chạy được nhiều tiến trình `agy`
    song song (đo được: 3 lượt song song 6.66s so với 18.62s tuần tự). Nhưng
    `AntigravityNativeAdapter` giữ ĐÚNG MỘT `WarmAgyWorker` trong
    `self._worker`, và `start_session()` đóng cái cũ trước khi mở cái mới —
    nên hai luồng cùng dùng một thể hiện sẽ GIẾT tiến trình của nhau giữa
    chừng. Đó là một lỗi tranh chấp thật, và nó chỉ lộ ra khi chạy song song.

    Cách giải: mỗi LUỒNG mượn một khe riêng. Bộ chạy việc gọi
    `start_session()` rồi `send_task()` trong CÙNG một luồng cho mỗi việc,
    nên gắn khe theo luồng là đúng ngữ nghĩa và không cần khoá ở đường nóng.

    Đây KHÔNG phải nhiều danh tính: cả N khe dùng chung một tài khoản, một
    quota, một credential. Xem `identity.Identity.account_slot`.
    """

    def __init__(self, worker_id: str, factory, *, slots: int):
        self._worker_id = worker_id
        self._factory = factory
        self._slots = max(1, slots)
        self._ranh: List[WorkerAdapter] = []
        self._dang_muon: Dict[int, WorkerAdapter] = {}
        self._khoa = threading.Lock()
        self._da_tao = 0
        self._mau = factory()          # mot ban de tra loi health/capabilities

    provider = "antigravity"
    transport = TransportKind.STRUCTURED_CLI

    # -- muon/tra khe -------------------------------------------------------

    def _muon(self) -> Optional[WorkerAdapter]:
        tid = threading.get_ident()
        with self._khoa:
            if tid in self._dang_muon:
                return self._dang_muon[tid]
            if self._ranh:
                a = self._ranh.pop()
            elif self._da_tao < self._slots:
                a = self._factory()
                self._da_tao += 1
            else:
                return None
            self._dang_muon[tid] = a
            return a

    def _tra(self) -> None:
        tid = threading.get_ident()
        with self._khoa:
            a = self._dang_muon.pop(tid, None)
            if a is not None:
                self._ranh.append(a)

    # -- hop dong chin phuong thuc ------------------------------------------

    def register(self) -> WorkerSpec:
        return self._mau.register()

    def health(self) -> HealthReport:
        return self._mau.health()

    def capabilities(self) -> FrozenSet[str]:
        return self._mau.capabilities()

    def set_write_mode(self, cho_ghi: bool) -> None:
        """Chuyen tiep xuong khe cua LUONG hien tai.

        Phai muon khe TRUOC khi dat che do: dat len `self` roi hy vong khe
        doc duoc se im lang mat tac dung, va viec chi doc se chay voi quyen
        ghi (hoac nguoc lai) — dung loai loi khong ai thay cho toi luc mot
        worker ghi nham cho."""
        a = self._muon()
        if a is not None and hasattr(a, "set_write_mode"):
            a.set_write_mode(cho_ghi)

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        a = self._muon()
        if a is None:
            return False               # het khe — bo lap lich se thu lai sau
        return a.start_session(workspace=workspace)

    def send_task(self, packet: TaskPacket) -> TaskResult:
        a = self._dang_muon.get(threading.get_ident())
        if a is None:
            a = self._muon()
        if a is None:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              failure_reason="no_free_slot",
                              summary=f"{self._worker_id}: hết khe song song")
        try:
            kq = a.send_task(packet)
        finally:
            # Dong tien trinh am cua khe roi TRA khe. Khong dong thi tien
            # trinh `agy` cu con giu `--add-dir` tro toi worktree cua viec
            # VUA XONG, va viec sau muon dung khe do se ghi nham cho.
            try:
                a.shutdown()
            except Exception:                             # noqa: BLE001
                pass
            self._tra()
        kq.worker_id = self._worker_id
        return kq

    def cancel(self) -> None:
        with self._khoa:
            ds = list(self._dang_muon.values())
        for a in ds:
            try:
                a.cancel()
            except Exception:                             # noqa: BLE001
                pass

    def result(self) -> Optional[TaskResult]:
        a = self._dang_muon.get(threading.get_ident())
        return a.result() if a is not None else None

    def reset_context(self) -> None:
        a = self._dang_muon.get(threading.get_ident())
        if a is not None:
            a.reset_context()

    def shutdown(self) -> None:
        with self._khoa:
            ds = list(self._dang_muon.values()) + list(self._ranh)
            self._dang_muon.clear()
            self._ranh.clear()
            self._da_tao = 0
        for a in ds:
            try:
                a.shutdown()
            except Exception:                             # noqa: BLE001
                pass


def dung_adapter(idn: Identity, *, timeout: float = 1200.0
                 ) -> Optional[WorkerAdapter]:
    """Dựng adapter cho một danh tính, hoặc `None` nếu khe chưa cấp phát.

    KHÔNG ném lỗi cho khe chưa cấp phát: đó là trạng thái BÌNH THƯỜNG của
    AG03..AG08 và bể phải chạy được với các khe đó ở `OFFLINE`.
    """
    if not idn.provisioned:
        return None
    if idn.provider == "claude":
        return None                    # CLAUDE_LEAD la chinh phien nay
    if idn.provider == "antigravity":
        if idn.transport is Transport.NATIVE:
            def _tao():
                # `dangerously_skip_permissions=False` CO Y va la bat bien:
                # `PoolAntigravityAdapter.start_session` cung ep lai False moi
                # lan. Hai lop chan cho mot quy tac an toan la co y — mot cho
                # o noi DUNG adapter, mot cho o noi CHAY no.
                return PoolAntigravityAdapter(
                    idn.worker_id, model=idn.model, allow_edits=True,
                    dangerously_skip_permissions=False, turn_timeout=timeout)
            if idn.max_concurrent > 1:
                return MultiSlotAdapter(idn.worker_id, _tao,
                                        slots=idn.max_concurrent)
            return _tao()
        if idn.transport is Transport.BRIDGE:
            dt = worker_identity.doc(idn.worker_id)
            if dt is None:
                return None            # chua ghep — coi nhu chua cap phat
            return AntigravityBridgeAdapter(
                idn.worker_id, host=idn.host, port=idn.port or dt["port"],
                token=dt["token"], model=idn.model, timeout=timeout)
        raise AdapterError(f"{idn.worker_id}: transport {idn.transport} "
                           f"không dùng được với antigravity")
    if idn.provider == "opencode":
        return OpenCodeAdapter(idn.worker_id, host=idn.host,
                               port=idn.port or 4096, model=idn.model,
                               timeout=timeout)
    if idn.provider == "codex":
        return CodexAdapter(idn.worker_id, timeout=timeout,
                            workspace=idn.workspace)
    raise AdapterError(f"{idn.worker_id}: provider lạ {idn.provider!r}")


def dung_tat_ca(danh_sach, *, timeout: float = 1200.0
                ) -> Dict[str, WorkerAdapter]:
    ra: Dict[str, WorkerAdapter] = {}
    for idn in danh_sach:
        a = dung_adapter(idn, timeout=timeout)
        if a is not None:
            ra[idn.worker_id] = a
    return ra

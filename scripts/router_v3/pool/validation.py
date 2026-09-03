"""Kiểm định kết quả worker — Bể worker tự trị, Phase 4.

Mission #8: "Never trust a worker claiming PASS by itself."

Đây không phải một quy tắc lý thuyết. Bằng chứng thật đã ghi trong
`native_worker.py`: một lượt `agy` trả về `status=SUCCESS`, `num_turns=1`,
kèm một câu trả lời TỰ TIN — và KHÔNG có tệp nào được ghi. Công cụ ghi tệp
bị headless tự động từ chối quyền, model không biết, và nó báo thành công.
Bằng chứng là **tệp trên đĩa**, không phải lời khai của worker.

Bốn cổng, chạy theo thứ tự rẻ-trước:

    1. HÌNH DẠNG  — phong bì có đủ trường không, `status` có hợp lệ không.
    2. DIFF       — worker nói sửa tệp thì đĩa phải có thay đổi, và ngược
                    lại: nói "ok, đã sửa X" mà `git status` sạch là NÓI DỐI
                    (hoặc thất bại im lặng — cùng hậu quả).
    3. PHẠM VI    — thay đổi phải nằm trong `write_scope` (dùng lại
                    `WorktreeManager.verify_scope`, không viết lại).
    4. TEST       — lệnh test yêu cầu phải CHẠY THẬT và phải xanh.

Cộng một cổng BẢO MẬT chạy trên mọi kết quả có ghi: diff không được chứa
thứ giống credential, và không được đụng các đường nhạy cảm.

`ValidationReport.passed` là thứ DUY NHẤT bộ điều phối được tin. `status`
của worker chỉ là đầu vào cho cổng 1.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from scripts.router_v3.packet import TaskResult, scan_for_secrets
from scripts.router_v3.worktree import WorktreeError, WorktreeHandle, WorktreeManager

#: Duong dan KHONG worker nao duoc sua, du `write_scope` co noi gi. Day la
#: rao cuoi: mot goi viec dung sai (hoac mot worker tu y mo rong pham vi) van
#: khong cham duoc vao ha tang bao mat/CI cua kho.
DUONG_CAM = (
    ".git/", ".github/workflows/", ".claude/settings.json",
    ".claude/settings.local.json", ".claude/hooks/",
    "installer.iss", ".env",
)

#: Lenh test duoc phep chay trong kiem dinh. DANH SACH TRANG, khong phai
#: danh sach den: `tests_required` di qua goi viec va co the bi mot worker
#: (hoac mot goi viec dung sai) dat thanh bat ky chuoi shell nao. Chi cho
#: phep dung chuong trinh chay test cua kho nay.
_LENH_TEST_CHO_PHEP = ("python", "py", "npm", "npx", "node", "pytest")


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:                       # pragma: no cover - hien thi
        return f"{'PASS' if self.passed else 'FAIL'} {self.name}: {self.detail}"


@dataclass
class ValidationReport:
    gates: List[GateResult] = field(default_factory=list)
    #: Tep THAT SU doi tren dia — do bang git, khong lay tu loi khai worker.
    files_changed_observed: List[str] = field(default_factory=list)
    scope_violations: List[str] = field(default_factory=list)
    tests_ran: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def failed_gates(self) -> List[str]:
        return [g.name for g in self.gates if not g.passed]

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail}
                      for g in self.gates],
            "files_changed_observed": list(self.files_changed_observed),
            "scope_violations": list(self.scope_violations),
            "tests_ran": list(self.tests_ran),
        }


def _git(cwd: Path, *args: str, runner=subprocess.run):
    return runner(["git", "-C", str(cwd), *args], capture_output=True,
                  text=True, encoding="utf-8", errors="replace")


def tep_da_doi(worktree: Path, *, runner=subprocess.run) -> List[str]:
    """Tệp thực sự đổi trong worktree — theo `git`, không theo worker.

    Gồm cả tệp CHƯA theo dõi (`--porcelain` liệt kê `??`): một worker tạo
    tệp mới mà chưa `git add` vẫn là đã thay đổi cây làm việc, và bỏ sót
    chúng sẽ làm cổng "nói sửa mà không sửa" báo nhầm.

    `-uall` là BẮT BUỘC, không phải tuỳ chọn. Mặc định git GỘP một thư mục
    chưa theo dõi thành một dòng `?? pkg/` thay vì liệt kê từng tệp — nên
    một worker tạo `pkg/a.py` sẽ được ghi nhận là đã đổi `pkg/`, không khớp
    với lời khai `pkg/a.py`, và cổng diff báo hỏng NHẦM một việc làm đúng.
    Đã vấp thật trong kiểm thử.
    """
    p = _git(worktree, "status", "--porcelain", "-uall", runner=runner)
    if p.returncode != 0:
        raise WorktreeError(f"không đọc được git status: {(p.stderr or '')[:200]}")
    ra = []
    for dong in (p.stdout or "").splitlines():
        tep = dong[3:].strip().strip('"').replace("\\", "/")
        if " -> " in tep:
            tep = tep.split(" -> ", 1)[1]
        if tep:
            ra.append(tep)
    return sorted(set(ra))


def _diff_van_ban(worktree: Path, *, runner=subprocess.run) -> str:
    """Diff của các tệp đã theo dõi + nội dung tệp mới, để quét bí mật.

    `git diff` KHÔNG hiện tệp chưa theo dõi. Một worker tạo mới `secrets.py`
    sẽ lọt hoàn toàn qua cổng bảo mật nếu chỉ đọc `git diff` — nên tệp mới
    được đọc thẳng từ đĩa.
    """
    phan = [_git(worktree, "diff", runner=runner).stdout or ""]
    p = _git(worktree, "ls-files", "--others", "--exclude-standard", runner=runner)
    for ten in (p.stdout or "").splitlines():
        ten = ten.strip()
        if not ten:
            continue
        duong = worktree / ten
        try:
            if duong.is_file() and duong.stat().st_size <= 512_000:
                phan.append(duong.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(phan)


# ---------------------------------------------------------------------------
# Cong kiem dinh
# ---------------------------------------------------------------------------

def cong_hinh_dang(kq: TaskResult) -> GateResult:
    if kq.status not in ("ok", "failed", "blocked", "timeout", "cancelled"):
        return GateResult("shape", False, f"status lạ: {kq.status!r}")
    if kq.status == "ok" and not kq.summary.strip():
        return GateResult("shape", False,
                          "báo ok nhưng `summary` rỗng — một lượt thật không "
                          "bao giờ không có gì để nói")
    if kq.blockers and kq.status == "ok":
        return GateResult("shape", False, "báo ok nhưng có blockers")
    return GateResult("shape", True, f"status={kq.status}")


def cong_diff(kq: TaskResult, quan_sat: Sequence[str], *,
              la_viec_co_ghi: bool) -> GateResult:
    """So lời khai với đĩa. Hai chiều đều là lỗi:

    - Nói sửa mà đĩa sạch  -> thất bại im lặng (quyền bị từ chối, hoặc bịa).
    - Nói không sửa mà đĩa bẩn -> worker làm thứ nó không khai báo.
    """
    khai = {t.replace("\\", "/").strip("/") for t in kq.files_changed}
    that = {t.replace("\\", "/").strip("/") for t in quan_sat}
    if not la_viec_co_ghi:
        if that:
            return GateResult("diff", False,
                              f"việc CHỈ ĐỌC nhưng cây làm việc đổi "
                              f"{len(that)} tệp: {sorted(that)[:5]}")
        return GateResult("diff", True, "chỉ đọc, cây sạch")
    if kq.status == "ok" and khai and not that:
        return GateResult("diff", False,
                          f"worker khai sửa {sorted(khai)[:5]} nhưng `git "
                          f"status` SẠCH — thất bại im lặng, không phải thành công")
    if kq.status == "ok" and not khai and that:
        return GateResult("diff", False,
                          f"worker không khai sửa gì nhưng đĩa đổi "
                          f"{sorted(that)[:5]}")
    if kq.status == "ok" and not that:
        return GateResult("diff", False,
                          "báo ok cho một việc CÓ GHI nhưng không tệp nào đổi")
    thieu = sorted(khai - that)
    if thieu:
        return GateResult("diff", False,
                          f"khai sửa nhưng đĩa không có: {thieu[:5]}")
    return GateResult("diff", True, f"{len(that)} tệp đổi thật")


def cong_bao_mat(diff: str, quan_sat: Sequence[str]) -> GateResult:
    ro_ri = scan_for_secrets(diff)
    if ro_ri:
        return GateResult("security", False,
                          f"diff chứa thứ giống credential (mẫu {ro_ri!r}) — "
                          f"CHẶN gộp")
    cham = [t for t in quan_sat
            if any(t.replace("\\", "/").startswith(c.rstrip("/")) or
                   t.replace("\\", "/") == c.rstrip("/") for c in DUONG_CAM)]
    if cham:
        return GateResult("security", False,
                          f"đụng đường CẤM: {sorted(cham)[:5]}")
    return GateResult("security", True, "không thấy bí mật, không đụng đường cấm")


def _lenh_an_toan(lenh: Sequence[str]) -> bool:
    if not lenh:
        return False
    dau = Path(str(lenh[0])).name.lower()
    dau = dau[:-4] if dau.endswith(".exe") else dau
    return dau in _LENH_TEST_CHO_PHEP


def cong_test(lenh_test: Sequence[Sequence[str]], worktree: Path, *,
              timeout: float = 900.0, runner=subprocess.run
              ) -> tuple[GateResult, List[str]]:
    """Chạy THẬT các lệnh test yêu cầu. Không có lệnh nào = cổng bỏ qua.

    Lệnh đi qua `subprocess` dưới dạng DANH SÁCH, không phải chuỗi shell:
    không có `shell=True` ở đây, nên một chuỗi lạ trong `tests_required`
    không thành một lệnh shell chạy được.
    """
    if not lenh_test:
        return GateResult("tests", True, "không yêu cầu test"), []
    da_chay: List[str] = []
    for lenh in lenh_test:
        lenh = [str(x) for x in lenh]
        if not _lenh_an_toan(lenh):
            return GateResult("tests", False,
                              f"lệnh test không nằm trong danh sách trắng: "
                              f"{lenh[0]!r} (cho phép: "
                              f"{list(_LENH_TEST_CHO_PHEP)})"), da_chay
        try:
            p = runner(lenh, cwd=str(worktree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return GateResult("tests", False,
                              f"{' '.join(lenh)} vượt {timeout}s"), da_chay
        except OSError as exc:
            return GateResult("tests", False,
                              f"{' '.join(lenh)} không chạy được: {exc}"), da_chay
        da_chay.append(" ".join(lenh))
        if p.returncode != 0:
            duoi = ((p.stderr or "") + (p.stdout or "")).strip()[-400:]
            return GateResult("tests", False,
                              f"{' '.join(lenh)} rc={p.returncode}: {duoi}"), da_chay
    return GateResult("tests", True, f"{len(da_chay)} lệnh test xanh"), da_chay


def kiem_dinh(kq: TaskResult, *, worktree: Optional[Path] = None,
              write_scope: Sequence[str] = (),
              tests: Sequence[Sequence[str]] = (),
              wt_manager: Optional[WorktreeManager] = None,
              handle: Optional[WorktreeHandle] = None,
              runner=subprocess.run,
              test_timeout: float = 900.0) -> ValidationReport:
    """Chạy mọi cổng. Trả về báo cáo — KHÔNG ném lỗi cho một kết quả xấu;
    kết quả xấu là dữ liệu, không phải sự cố của bộ kiểm định."""
    bc = ValidationReport()
    bc.gates.append(cong_hinh_dang(kq))

    if worktree is None:
        # Viec chi doc khong co worktree rieng — chi kiem duoc hinh dang.
        # Noi ro thay vi de bao cao trong nhu da kiem day du.
        bc.gates.append(GateResult("diff", True,
                                   "không có worktree — bỏ qua (việc chỉ đọc)"))
        return bc

    wt = Path(worktree)
    try:
        bc.files_changed_observed = tep_da_doi(wt, runner=runner)
    except WorktreeError as exc:
        bc.gates.append(GateResult("diff", False, str(exc)[:200]))
        return bc

    bc.gates.append(cong_diff(kq, bc.files_changed_observed,
                              la_viec_co_ghi=bool(write_scope)))

    if write_scope:
        if wt_manager is not None and handle is not None:
            try:
                bc.scope_violations = wt_manager.verify_scope(handle, write_scope)
            except WorktreeError as exc:
                bc.scope_violations = [f"(không kiểm được: {exc})"]
        else:
            cho_phep = [s.replace("\\", "/").strip("/") for s in write_scope]
            bc.scope_violations = sorted(
                t for t in bc.files_changed_observed
                if not any(t == c or t.startswith(c + "/") for c in cho_phep))
        bc.gates.append(GateResult(
            "scope", not bc.scope_violations,
            "trong phạm vi" if not bc.scope_violations
            else f"ghi NGOÀI write_scope: {bc.scope_violations[:5]}"))

    bc.gates.append(cong_bao_mat(_diff_van_ban(wt, runner=runner),
                                 bc.files_changed_observed))

    cong, da_chay = cong_test(tests, wt, timeout=test_timeout, runner=runner)
    bc.tests_ran = da_chay
    bc.gates.append(cong)
    return bc

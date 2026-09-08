"""Lát cắt dọc ĐỌC + GHI bằng agent THẬT — Control Center V0.1.

Khác `control_center_real_proof.py` ở đúng một điểm, và đó là điểm của tệp
này: nó ép một việc **CÓ GHI** đi trọn đường, với allowlist `agy` đã bật.

    ô chat -> việc CÓ GHI -> worktree cô lập -> phiên agent thật
    -> agent GHI tệp -> agent chạy `cc_agent_tool changes` (lệnh được phép)
    -> agent khai `changes` -> cổng `diff` của V4 đối chiếu với `git` thật
    -> DONE

Cổng `diff` là lý do việc khai `changes` không phải thủ tục giấy tờ: nó so
lời khai với `git status` thật, và một lượt làm ĐÚNG từng bị đánh HỎNG chỉ
vì agent để `changes` rỗng (xem CONTROL_CENTER_V01_PROOF §4 #10). Giờ agent
có đúng một lệnh được phép để tự tra ra danh sách đó.

AN TOÀN: chỉ ghi trong worktree CÔ LẬP, phạm vi hẹp, không deploy, không
đụng tài nguyên trả phí, không `--dangerously-skip-permissions`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.control_center.engine import ControlCenter      # noqa: E402
from scripts.control_center.model import Project, TaskState  # noqa: E402
from scripts.router_v4.contract import TaskContract          # noqa: E402


def _d(s: str = "") -> None:
    print(s, flush=True)


def chay(*, root: Path, timeout: float, probe: bool) -> Dict:
    _d("=" * 74)
    _d("LÁT CẮT ĐỌC + GHI — agent THẬT, allowlist đã bật")
    _d("=" * 74)

    cc = ControlCenter(root=root, probe=probe, max_parallel=2)
    pid = "rw"
    cc.them_project(Project(
        project_id=pid, name="ReadWrite", repo_path=str(root),
        resources=("write:docs/reports", "prod:fanfic.world")))
    cc.recover()

    # -- 1. CONG AN TOAN: y dinh deploy phai bi chan TRUOC khi toi worker ---
    _d("")
    _d("A. CỔNG GATED — gửi một ý định deploy production:")
    g = cc.chat(pid, "deploy the web to production now")
    gated = [t for t in g["tasks"] if t["state"] == "BLOCKED"]
    for t in gated:
        _d(f"   [CHẶN] {t['task_id']}: {t['blocked_reason'][:120]}")
    # Kiem dung dieu can kiem: KHONG viec GATED nao duoc giao. Ban dau cho
    # nay doi "tick() khong giao gi ca", nhung du an nay con viec ton dong
    # tu cac lan chay truoc — mot viec HOP LE duoc giao lam bai kiem do
    # HONG mot cach vo nghia.
    ten_gated = {t["task_id"] for t in gated}
    truoc = cc.tick()["dispatched"]
    lot = sorted(ten_gated & set(truoc))
    _d(f"   tick() giao: {truoc or '(không giao gì)'}")
    _d(f"   trong đó GATED lọt qua: {lot or '(không có)'}")
    gate_ok = bool(gated) and not lot

    # -- 2. Viec CO GHI di tron duong ---------------------------------------
    # PHAM VI HEP CO CHU DICH. Ban dau cau nay la "... describing what
    # scripts/control_center does", nen `scripts/control_center` vao pham vi
    # va agent doc 12 tep truoc khi ghi. Do that 2026-09-08: ca ba luot deu
    # ket thuc bang van xuoi khong co JSON — model tieu het luot vao viec
    # doc. Bang chung can chung minh la DUONG DI (chat -> worktree -> ghi ->
    # khai `changes` -> cong `diff`), khong phai suc ben cua mot model tren
    # mot bai doc dai.
    y_dinh = ("create docs/reports/cc-readwrite-proof.md with three lines "
              "naming what Router Control Center V0.1 does")
    _d("")
    _d(f"B. VIỆC CÓ GHI:\n   {y_dinh}")
    kq = cc.chat(pid, y_dinh)
    ids = [t["task_id"] for t in kq["tasks"]]
    viec = [t for t in ids if cc.store.task(t).state is not TaskState.BLOCKED]
    if not viec:
        _d("   !! không có việc nào chạy được")
        cc.shutdown()
        return {"ok": False, "gate_ok": gate_ok}
    tid = viec[0]
    hd = TaskContract.from_dict(cc.store.task(tid).contract)
    _d(f"   task       : {tid}")
    _d(f"   repo_write : {hd.requirements.repo_write}")
    _d(f"   phạm vi    : {list(hd.allowed_scope)}")

    t0 = time.time()
    het = time.time() + timeout
    while time.time() < het:
        cc.tick()
        with cc._khoa:
            bay = set(cc._dang_chay)
        if cc.store.task(tid).state.terminal and not bay:
            break
        time.sleep(2.0)
    giay = time.time() - t0

    t = cc.store.task(tid)
    pb = ((t.result or {}).get("envelope") or {})
    val = (t.result or {}).get("validation") or {}
    s = cc.store.session(t.owner_session) if t.owner_session else None

    _d("")
    _d("=" * 74)
    _d("KẾT QUẢ")
    _d("=" * 74)
    _d(f"  trạng thái : {t.state.value}   ({giay:.0f}s, lượt {t.attempts})")
    _d(f"  vị trí     : {s.placement_key if s else '—'}   pid={s.pid if s else '—'}")
    _d(f"  worktree   : {t.worktree or '—'}")
    _d(f"  nhánh      : {t.branch or '—'}")
    _d(f"  agent khai : {pb.get('changes')}")
    _d(f"  tóm tắt    : {pb.get('summary', '')[:200]}")
    for c in (val.get("gates") or []):
        _d(f"  cổng {c['name']:<16} {'ĐẠT' if c['passed'] else 'HỎNG'}  "
           f"{c['detail'][:80]}")

    tep_that: List[str] = []
    if t.worktree:
        for p in Path(t.worktree).rglob("cc-readwrite-proof.md"):
            tep_that.append(str(p.relative_to(t.worktree)).replace("\\", "/"))
    _d(f"  tệp TRÊN ĐĨA trong worktree: {tep_that or '(không thấy)'}")
    goc_ban = (root / "docs" / "reports" / "cc-readwrite-proof.md").exists()
    _d(f"  rò ra kho gốc? {'CÓ — LỖI' if goc_ban else 'không'}")

    bc = {
        "ok": t.state is TaskState.DONE and bool(tep_that) and not goc_ban,
        "gate_ok": gate_ok, "task_id": tid, "state": t.state.value,
        "seconds": round(giay, 1), "attempts": t.attempts,
        "placement": s.placement_key if s else "", "pid": s.pid if s else None,
        "worktree": t.worktree, "branch": t.branch,
        "declared_changes": pb.get("changes"), "files_on_disk": tep_that,
        "leaked_to_main_checkout": goc_ban,
        "gates": val.get("gates"), "summary": pb.get("summary", "")[:400],
        "locks_left": len(cc.store.locks(pid)),
    }
    _d("")
    _d(f"  khoá còn giữ: {bc['locks_left']} (phải là 0)")
    _d(f"  GATED chặn  : {'ĐẠT' if gate_ok else 'HỎNG'}")
    _d(f"  ĐỌC+GHI     : {'ĐẠT' if bc['ok'] else 'HỎNG'}")
    cc.shutdown()
    return bc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lát cắt ĐỌC+GHI bằng agent thật")
    ap.add_argument("--root", default="")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--json-out", default="")
    a = ap.parse_args(argv)
    goc = Path(a.root).resolve() if a.root else Path.cwd()
    bc = chay(root=goc, timeout=a.timeout, probe=a.probe)
    if a.json_out:
        Path(a.json_out).write_text(
            json.dumps(bc, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        _d(f"\nsố đo đã ghi: {a.json_out}")
    return 0 if (bc.get("ok") and bc.get("gate_ok")) else 1


if __name__ == "__main__":
    sys.exit(main())

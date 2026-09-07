"""Bằng chứng THẬT cho Control Center V0.1 — agent thật, worktree thật.

Bài kiểm `scripts/tests/test_control_center_*.py` thay tiến trình agent bằng
`FakeExecutor` — đúng cho một bộ kiểm chạy được trong CI. Tệp này làm phần
còn lại: chạy đúng lát cắt dọc đó với **tiến trình agent thật** do Router V4
gọi ra, trên **kho thật**, rồi in số đo.

VÌ SAO PHẢI TÁCH RA MỘT TỆP RIÊNG chứ không nhét vào bộ kiểm:

  - nó TỐN QUOTA nhà cung cấp — một bộ kiểm tự tiêu quota mỗi lần chạy là
    một bộ kiểm không ai dám chạy;
  - nó KHÔNG TẤT ĐỊNH — model trả về khác nhau mỗi lượt;
  - nó CHẬM — mỗi lượt `agy` mất hàng chục giây kể cả khi mọi thứ đúng.

Ba lý do đó không làm nó bớt cần thiết. Cùng khuôn với
`scripts/router_v4_real_proof.py`, đã dùng để tìm ra 10 lỗi thật của V4.

AN TOÀN, không đàm phán:

  - việc CHỈ ĐỌC theo mặc định. `--write` mới cho một việc có ghi, và việc
    đó chạy trong worktree CÔ LẬP, phạm vi hẹp, không bao giờ trên cây chung.
  - KHÔNG deploy, KHÔNG đụng tài nguyên trả phí, KHÔNG `git push`.
  - `--dangerously-skip-permissions` không xuất hiện ở đây và không được
    phép xuất hiện.
  - một việc chạm lớp GATED bị Control Center chặn TRƯỚC khi tới worker —
    kịch bản dưới đây kiểm luôn điều đó.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.control_center.engine import ControlCenter      # noqa: E402
from scripts.control_center.model import (LockKind, Project,  # noqa: E402
                                          TaskState)


def _dong(s: str = "") -> None:
    print(s, flush=True)


def _cho_xong(cc: ControlCenter, ids: List[str], *, giay: float) -> bool:
    het = time.time() + giay
    while time.time() < het:
        cc.tick()
        with cc._khoa:
            bay = set(cc._dang_chay)
        if all(cc.store.task(x).state.terminal or
               cc.store.task(x).state in (TaskState.BLOCKED, TaskState.REVIEW)
               for x in ids) and not bay:
            return True
        time.sleep(1.0)
    return False


def chay(*, root: Path, cho_ghi: bool, timeout: float,
         probe: bool) -> Dict:
    _dong("=" * 74)
    _dong("CONTROL CENTER V0.1 — BẰNG CHỨNG THẬT (agent thật, kho thật)")
    _dong("=" * 74)

    cc = ControlCenter(root=root, probe=probe, max_parallel=2)
    cc.them_project(Project(
        project_id="proof", name="Proof", repo_path=str(root),
        resources=("write:docs/reports", "prod:fanfic.world")))
    cc.recover()

    # Runtime that su — in ra TRUOC khi chay, de bao cao khong bao gio nham
    # "51 placement" thanh "51 tai khoan".
    _dong("")
    _dong("TÀI KHOẢN ĐÃ CẤP PHÁT (thật, không phải placement):")
    for k, v in (cc.fabric.dem_tai_khoan() or {}).items():
        _dong(f"  {k}: {v}")
    chua = [r.runtime_id for r in cc.fabric.runtimes.values()
            if not r.provisioned]
    if chua:
        _dong(f"  chưa cấp phát: {', '.join(sorted(chua))}")

    # -- 1. O chat: mot y dinh -> nhieu viec -------------------------------
    # Cau CO GHI phai dung dong tu bo phan loai HIEU (`create`) VA neu ro
    # duong dan. Ban dau o day dung "summarise ... into docs/reports": bo
    # phan loai khong biet "summarise", nen viec roi ve `analysis` va ca
    # duong CO GHI khong bao gio duoc chung minh. Mot bang chung chay xanh
    # ma khong cham vao thu can chung minh thi te hon khong co bang chung.
    y_dinh = ("investigate how the TTS provider registry picks a provider"
              + (" and separately create docs/reports/cc-smoke.md describing "
                 "what scripts/control_center does" if cho_ghi else ""))
    _dong("")
    _dong(f"Ý ĐỊNH GỬI VÀO Ô CHAT:\n  {y_dinh}")
    kq = cc.chat("proof", y_dinh)
    _dong("")
    _dong("ROUTER TRẢ LỜI:")
    for d in kq["reply"].splitlines():
        _dong("  " + d)

    ids = [t["task_id"] for t in kq["tasks"]]

    # -- 2. Mot y dinh GATED phai bi chan TRUOC khi toi worker -------------
    _dong("")
    _dong("KIỂM CỔNG AN TOÀN — gửi một ý định deploy:")
    g = cc.chat("proof", "deploy the web to production now")
    gated = [t for t in g["tasks"] if t["state"] == "BLOCKED"]
    _dong(f"  việc tạo ra: {len(g['tasks'])}, bị chặn: {len(gated)}")
    for t in gated:
        _dong(f"  [CHẶN] {t['task_id']}: {t['blocked_reason'][:150]}")
    if not gated:
        _dong("  !! CẢNH BÁO: ý định deploy KHÔNG bị chặn — đây là lỗi thật.")

    # -- 3. Chay that -------------------------------------------------------
    _dong("")
    _dong(f"CHẠY {len(ids)} việc bằng agent THẬT (trần {timeout:.0f}s)…")
    t0 = time.time()
    xong = _cho_xong(cc, ids, giay=timeout)
    giay = time.time() - t0

    # -- 3b. DUNG LAI phien: mot viec tuong thich nua -----------------------
    #
    # Day la yeu cau LOI cua V0.1, va no chi chung minh duoc bang MOT viec
    # thu hai: mot viec don le khong noi len dieu gi ve viec dung lai.
    _dong("")
    _dong("KIỂM DÙNG LẠI PHIÊN — gửi một việc CHỈ ĐỌC tương thích nữa:")
    kq2 = cc.chat("proof", "look into how text chunking splits long text")
    ids2 = [t["task_id"] for t in kq2["tasks"]]
    _cho_xong(cc, ids2, giay=timeout)
    ids += ids2
    dung_lai = [s for s in cc.store.sessions("proof") if s.task_count > 1]
    _dong(f"  phiên nhận >1 việc: {len(dung_lai)}")
    for s in dung_lai:
        _dong(f"    {s.session_id} ({s.placement_key}) — {s.task_count} việc, "
              f"pid={s.pid}")
    if not dung_lai:
        _dong("  !! KHÔNG có phiên nào được dùng lại — kiểm lại `decide()`.")

    # -- 4. So do -----------------------------------------------------------
    _dong("")
    _dong("=" * 74)
    _dong("KẾT QUẢ")
    _dong("=" * 74)
    bang: List[Dict] = []
    for tid in ids:
        t = cc.store.task(tid)
        pb = ((t.result or {}).get("envelope") or {})
        s = cc.store.session(t.owner_session) if t.owner_session else None
        bang.append({
            "task_id": tid, "state": t.state.value,
            "placement": (s.placement_key if s else ""),
            "provider": pb.get("provider", ""),
            "seconds": round(t.runtime_seconds, 1),
            "attempts": t.attempts,
            "worktree": t.worktree, "branch": t.branch,
            "summary": pb.get("summary", "")[:200],
            "raw_log_ref": pb.get("raw_log_ref", "")})
        _dong(f"  {tid}")
        _dong(f"    trạng thái : {t.state.value}")
        _dong(f"    vị trí     : {bang[-1]['placement'] or '—'}")
        _dong(f"    thời gian  : {bang[-1]['seconds']}s  (lượt {t.attempts})")
        _dong(f"    worktree   : {t.worktree or '(chỉ đọc — không có)'}")
        _dong(f"    tóm tắt    : {bang[-1]['summary']}")

    phien = cc.store.sessions("proof")
    _dong("")
    song = [s for s in phien if s.state.alive]
    _dong(f"PHIÊN: {len(phien)} dựng ({len(song)} còn sống), "
          f"{sum(1 for s in phien if s.task_count > 1)} phiên nhận >1 việc "
          f"(bằng chứng DÙNG LẠI phiên)")
    for s in phien:
        _dong(f"  {s.session_id}  {s.placement_key}  {s.state.value}  "
              f"pid={s.pid or '—'}  việc={s.task_count}")

    _dong("")
    _dong(f"KHOÁ CÒN GIỮ SAU KHI CHẠY: {len(cc.store.locks('proof'))} "
          f"(phải là 0 — mọi khoá nhả trong `finally`)")
    _dong(f"WORKTREE (không cái nào bị xoá tự động): "
          f"{len(cc.store.worktrees('proof'))}")
    _dong(f"TỔNG THỜI GIAN TƯỜNG: {giay:.1f}s  "
          f"{'(xong)' if xong else '(HẾT GIỜ)'}")

    bc = {
        "ok": xong, "wall_seconds": round(giay, 1), "tasks": bang,
        "gated_blocked": len(gated), "gated_total": len(g["tasks"]),
        "sessions": [s.to_dict() for s in phien],
        "locks_left": len(cc.store.locks("proof")),
        "worktrees": cc.store.worktrees("proof"),
        "accounts": cc.fabric.dem_tai_khoan(),
        "usage": cc.usage.report("proof", probe_cli=False),
    }
    cc.shutdown()
    return bc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Bằng chứng thật cho Control Center V0.1")
    ap.add_argument("--root", default="", help="kho để chạy (mặc định: cwd)")
    ap.add_argument("--write", action="store_true",
                    help="cho phép MỘT việc có ghi trong worktree cô lập")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--probe", action="store_true",
                    help="dò sức khoẻ provider trước khi chạy (CHẬM)")
    ap.add_argument("--json-out", default="",
                    help="ghi số đo ra tệp JSON")
    a = ap.parse_args(argv)

    goc = Path(a.root).resolve() if a.root else Path.cwd()
    bc = chay(root=goc, cho_ghi=a.write, timeout=a.timeout, probe=a.probe)
    if a.json_out:
        Path(a.json_out).write_text(
            json.dumps(bc, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        _dong(f"\nsố đo đã ghi: {a.json_out}")
    return 0 if bc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

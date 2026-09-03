"""BẰNG CHỨNG THẬT cho Router V4 — mission #21.

KHÔNG MOCK, KHÔNG PHÁ HUỶ, KHÔNG XUẤT BẢN. Chạy một mission THẬT trên kho
Fanfic World với ba lớp việc mission yêu cầu, cộng một phép dò đa phương
thức trên một hiện vật sản xuất CÓ THẬT (chỉ đọc):

    T1  phân tích kho, CHỈ ĐỌC          (repo_read)
    T2  QA đa phương thức trên ảnh THẬT (image)      — chỉ đọc, không sửa
    T3  việc code nhỏ trong worktree CÔ LẬP (repo_write)
    T4  review ĐỘC LẬP kết quả T3       (khác họ model), phụ thuộc T3

Không nút nào chạm production, không nút nào deploy, không nút nào sửa hiện
vật có sẵn. T3 chỉ được ghi vào ĐÚNG một tệp mới trong worktree riêng của nó.

ĐO CÁI GÌ: thời gian tường song song, tổng thời gian worker, tăng tốc, tỉ lệ
thành công, số lượt thử lại, provider/tài khoản đã dùng thật, và kết quả
kiểm định của TỪNG nút. Nếu một provider không sẵn sàng thì nó được ghi là
KHÔNG SẴN SÀNG — không có thành công giả.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import Execution, TaskContract, Verification
from scripts.router_v4.orchestrator import Need, RouterV4
from scripts.router_v4.scheduler import Demand

ANH_THAT = "docs/screenshots/01-home-desktop.png"
TEP_T3 = "scripts/router_v4/report.py"


def dung_hop_dong(root: Path):
    t1 = TaskContract(
        task_id="T1-phan-tich",
        type="repo_analysis",
        objective=(
            "Đọc tệp `desktop_app/providers/registry.py` trong kho này và "
            "trả lời CHÍNH XÁC theo những gì đọc được:\n"
            "  1) Lớp/đối tượng nào đóng vai trò sổ đăng ký provider TTS?\n"
            "  2) Các provider được đăng ký tên là gì?\n"
            "  3) Một provider mới được thêm vào bằng cách nào?\n"
            "Đặt câu trả lời vào `summary` (tối đa 6 câu). Nếu không đọc "
            "được tệp, trả `blocked` và nói rõ — ĐỪNG đoán từ tên tệp."),
        inputs=("desktop_app/providers/registry.py",),
        requirements=Requirements(repo_read=True, structured_output=True,
                                  reasoning_level=Reasoning.MEDIUM,
                                  latency_priority=Priority.HIGH),
        execution=Execution(expected_duration=45.0, max_wall_time=420.0,
                            worktree_required=False),
        stop_conditions=("Không đọc được tệp registry.py",),
        impact=0.15, uncertainty=0.15)

    t2 = TaskContract(
        task_id="T2-qa-da-phuong-thuc",
        type="visual_qa",
        objective=(
            f"Mở ẢNH tại đường dẫn `{ANH_THAT}` (ảnh chụp màn hình THẬT của "
            f"trang chủ Fanfic World) và đánh giá giao diện.\n"
            "Trong `summary`: liệt kê 3-5 phần tử UI bạn THỰC SỰ NHÌN THẤY.\n"
            "Trong `findings`: tối đa 3 vấn đề khả dụng/trình bày quan sát "
            "được (tương phản, khoảng cách, phân cấp, chữ bị cắt...).\n"
            "TUYỆT ĐỐI KHÔNG sửa, di chuyển, hay ghi đè ảnh — chỉ ĐỌC.\n"
            "Nếu không đọc được nội dung ảnh, trả `blocked` với "
            "failure_reason='cannot_read_image'. ĐỪNG đoán từ tên tệp."),
        inputs=(ANH_THAT,),
        requirements=Requirements(image=True, repo_read=True,
                                  structured_output=True,
                                  reasoning_level=Reasoning.MEDIUM),
        execution=Execution(expected_duration=60.0, max_wall_time=420.0,
                            worktree_required=False),
        stop_conditions=("Không giải mã được nội dung ảnh",),
        impact=0.15, uncertainty=0.2)

    t3 = TaskContract(
        task_id="T3-viet-report",
        type="implementation",
        objective=(
            f"Tạo MỚI đúng một tệp: `{TEP_T3}`.\n\n"
            "Nội dung: một module Python THUẦN (không phụ thuộc ngoài, không "
            "I/O, không mạng) cung cấp:\n\n"
            "    def render_mission_report(data: dict) -> str\n\n"
            "`data` có dạng: {'mission_id': str, 'wall_seconds': float, "
            "'tasks': [{'task_id': str, 'status': str, 'worker': str, "
            "'model': str, 'duration': float}]}\n\n"
            "Hàm trả về một BẢNG văn bản nhiều dòng: một dòng tiêu đề, một "
            "dòng cho mỗi task (căn cột), và một dòng tổng kết có số task "
            "'ok' trên tổng số. Xử lý được `tasks` rỗng (trả bảng có tiêu đề "
            "và tổng kết 0/0, KHÔNG ném lỗi).\n\n"
            "YÊU CẦU: có docstring module tiếng Việt giải thích module dùng "
            "để làm gì; dùng type hints; KHÔNG import gì ngoài `typing`. "
            "Tệp phải biên dịch được bằng `python -m compileall`."),
        expected_outputs=(TEP_T3,),
        allowed_scope=(TEP_T3,),
        requirements=Requirements(coding=True, repo_read=True, repo_write=True,
                                  structured_output=True,
                                  reasoning_level=Reasoning.HIGH,
                                  quality_priority=Priority.HIGH),
        execution=Execution(expected_duration=120.0, max_wall_time=600.0,
                            destructive_actions_allowed=False,
                            worktree_required=True),
        verification=Verification(
            tests=(("python", "-m", "compileall", "-q", TEP_T3),),
            artifact_checks=(TEP_T3,)),
        stop_conditions=("Không ghi được tệp vào workspace",),
        impact=0.3, uncertainty=0.2)

    t4 = TaskContract(
        task_id="T4-review-doc-lap",
        type="review",
        objective=(
            f"Review ĐỘC LẬP module `{TEP_T3}` do một worker khác vừa viết "
            f"(xem DEPENDENCY_RESULTS).\n"
            "Kiểm: hàm có xử lý `tasks` rỗng không? có import ngoài `typing` "
            "không? type hints có đúng không? bảng có căn cột thật không?\n"
            "`findings`: chỉ LỖI THẬT, mỗi lỗi một dòng. Không tìm thấy vấn "
            "đề thật thì nói rõ như vậy — ĐỪNG bịa phát hiện cho đủ số.\n"
            "KHÔNG sửa gì cả."),
        inputs=(TEP_T3,),
        requirements=Requirements(coding=True, repo_read=True,
                                  structured_output=True,
                                  reasoning_level=Reasoning.HIGH),
        execution=Execution(expected_duration=60.0, max_wall_time=420.0,
                            worktree_required=False),
        dependencies=("T3-viet-report",),
        impact=0.2, uncertainty=0.2)
    return [t1, t2, t3, t4]


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="")
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=1500.0)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else _ROOT

    print("=" * 74)
    print("ROUTER V4 — BẰNG CHỨNG THẬT (không mock, không phá huỷ)")
    print("=" * 74)

    rv = RouterV4(root=root, probe=True)
    snap = rv.fabric.snapshot()
    san_sang = [r for r in snap["runtimes"] if r["status"] != "OFFLINE"
                and r["dispatchable"]]
    print(f"\nRuntime dispatch được: "
          + ", ".join(f"{r['runtime_id']}({r['provider']})" for r in san_sang))
    print(f"Tài khoản thật: {snap['accounts']}")

    # --- Yeu cau NANG LUC (khong ten tai khoan) ---------------------------
    print("\n--- CLAUDE LEAD YÊU CẦU NĂNG LỰC (không nêu tài khoản) ---")
    cap = rv.request([
        Need("1 worker thực thi mạnh", coding=True, repo_read=True,
             repo_write=True, structured_output=True,
             reasoning_level=Reasoning.HIGH),
        Need("1 worker phân tích kho giá rẻ", repo_read=True,
             structured_output=True, latency_priority=Priority.HIGH),
        Need("1 worker đa phương thức", image=True, repo_read=True,
             structured_output=True),
    ])
    for x in cap:
        got = ", ".join(p.key for p in x.placements) or "(THIẾU)"
        print(f"  {x.need.label:<34} -> {got}")

    # --- Lap ke hoach ------------------------------------------------------
    hds = dung_hop_dong(root)
    kh = rv.plan(hds, mission_id="proof-v4")
    print(f"\n--- KẾ HOẠCH ---")
    print(f"  lớp            : {kh.waves}")
    print(f"  đường tới hạn  : {kh.critical_path} = {kh.critical_seconds:.0f}s")
    print(f"  tổng ước lượng : {kh.total_estimated_seconds:.0f}s worker")
    print(f"  worker nên dùng: {kh.recommended_workers}")

    # --- Giai thich quyet dinh TRUOC khi chay ------------------------------
    print("\n--- QUYẾT ĐỊNH ĐỊNH TUYẾN (trước khi chạy) ---")
    nhu_cau = Demand.from_contracts(list(kh.dag.contracts.values()))
    for tid in kh.dag.ids():
        qd = rv.scheduler.decide(kh.dag.contract(tid), demand=nhu_cau)
        chon = qd.selected.key if qd.selected else "(KHÔNG CÓ)"
        print(f"  {tid:<22} -> {chon:<34} ({qd.eligible_count} ứng viên)")

    # --- Chay THAT ---------------------------------------------------------
    print(f"\n--- CHẠY THẬT (song song tối đa {a.max_parallel}) ---")
    su_kien = []
    t0 = time.time()
    kq = rv.run_mission(kh, max_parallel=a.max_parallel, timeout=a.timeout,
                        on_event=lambda k, p: su_kien.append((k, p)))
    wall = time.time() - t0

    # --- Do luong ----------------------------------------------------------
    # TONG THOI GIAN WORKER phai gom MOI thu da chay that: nut chinh, luot
    # review cua che do primary_critic, va cac gia thuyet song song. Ban dau
    # chi cong `o.envelope.duration` cua bon nut chinh, nen "tang toc" so mot
    # wall-clock CO ca review/thu lai voi mot tong worker KHONG co chung —
    # mot con so vo nghia. So sanh trung thuc duy nhat la wall song song so
    # voi wall TUAN TU cua CUNG mot DAG (chay lai voi --max-parallel 1).
    tong_worker = 0.0
    for o in kq.values():
        tong_worker += o.envelope.duration
        if o.review is not None:
            tong_worker += o.review.duration
        for h in o.hypotheses:
            tong_worker += h.duration
    ok = [t for t, o in kq.items() if o.ok]
    thu_lai = sum(max(0, o.attempts - 1) for o in kq.values())
    print(f"\n{'=' * 74}\nKẾT QUẢ\n{'=' * 74}")
    for tid in kh.dag.ids():
        o = kq[tid]
        nhan = "OK  " if o.ok else "HỎNG"
        w = f"{o.placement.key}" if o.placement else "-"
        print(f"  [{nhan}] {tid:<22} {w:<34} {o.envelope.duration:6.1f}s "
              f"lượt={o.attempts} chế_độ={o.mode}")
        if o.envelope.summary:
            print(f"         {o.envelope.summary[:150]}")
        if o.envelope.failure_reason:
            print(f"         lý do hỏng: {o.envelope.failure_reason}")
        for f in o.envelope.findings[:3]:
            print(f"         · {f[:130]}")

    tang_toc = round(tong_worker / wall, 2) if wall else 0.0
    print(f"\n  thời gian tường (song song) : {wall:.1f}s")
    print(f"  tổng thời gian worker        : {tong_worker:.1f}s")
    print(f"  tăng tốc thực đo             : {tang_toc}x")
    print(f"  thành công                   : {len(ok)}/{len(kq)}")
    print(f"  lượt thử lại                 : {thu_lai}")
    print(f"  nút có review độc lập        : "
          f"{sum(1 for o in kq.values() if o.review is not None)}")
    dung = sorted({o.placement.runtime_id for o in kq.values() if o.placement})
    print(f"  runtime đã dùng thật         : {dung}")
    ho = sorted({rv.fabric.model(o.placement.model_id).model_family
                 for o in kq.values() if o.placement})
    print(f"  họ model đã dùng             : {ho}")

    bao_cao = {
        "mission_id": kh.dag.mission_id, "wall_seconds": round(wall, 2),
        "worker_seconds": round(tong_worker, 2), "speedup": tang_toc,
        "success": f"{len(ok)}/{len(kq)}", "retries": thu_lai,
        "runtimes_used": dung, "families_used": ho,
        "plan": kh.to_dict(),
        "allocations": [x.to_dict() for x in cap],
        "tasks": {t: o.to_dict() for t, o in kq.items()},
    }
    if a.out:
        Path(a.out).write_text(json.dumps(bao_cao, ensure_ascii=False, indent=2,
                                          default=str), encoding="utf-8")
        print(f"\n  báo cáo đầy đủ: {a.out}")
    return 0 if len(ok) == len(kq) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Bể worker tự trị do Claude dẫn dắt — dựng TRÊN Router V3/LTS, không thay nó.

Router V3/LTS đã có: hợp đồng `WorkerAdapter`, `TaskDag`, `WorkerRegistry`,
`WorktreeManager`, `TaskPacket`/`TaskResult`, chấm điểm chọn worker. Gói này
KHÔNG viết lại thứ nào trong số đó — nó thêm đúng phần còn thiếu để Claude
điều phối được mà không ai phải gõ tay vào từng cửa sổ worker:

    identity    — danh tính CỐ ĐỊNH, một tài khoản một khe, cấm xoay tài khoản
    store       — sổ việc BỀN (SQLite) sống lâu hơn phiên Claude
    routing     — chính sách năng lực -> worker, đọc từ tệp, không nhúng cứng
    validation  — không tin worker tự khai PASS
    runner      — vòng chạy DAG bất đồng bộ: thử lại có chặn, đổi worker
    orchestrator— giao diện Claude gọi: plan/dispatch/wait_any/status/...
    daemon      — tiến trình nền bền, chạy tiếp sau khi phiên Claude đóng
    cli         — quan sát: một bảng, một lệnh

`scheduler.py` (đồng bộ, một lượt) VẪN giữ nguyên và vẫn dùng được — nó là
đường chạy trong-tiến-trình. `runner.py` là anh em BẤT ĐỒNG BỘ của nó: cùng
`TaskDag`, cùng `choose_worker`, cùng `WorktreeManager`, khác mô hình thực
thi (bền, huỷ được, thử lại được).
"""
from scripts.router_v3.pool.identity import (AG_SLOTS, Identity, IdentityError,
                                             Transport, validate_pool)

__all__ = ["AG_SLOTS", "Identity", "IdentityError", "Transport", "validate_pool"]

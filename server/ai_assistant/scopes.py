"""
Phạm vi của một lần từ chối vì hết hạn mức (`ai_budget_exhausted`).

Module riêng, KHÔNG import gì, để cả `limits.py` lẫn control plane dùng chung mà không tạo vòng import.
Giao diện dùng nó để nói đúng điều gì đã hết:

* ``user``   — lượt hỏi RIÊNG của người đó trong ngày (hạn mức của chính họ);
* ``global`` — công suất chung của site / nhà cung cấp. KHÔNG bao giờ kèm một con số nào ra người dùng:
  mức dùng toàn cục và công suất nhà cung cấp chỉ nằm ở `/admin/ai`;
* ``qa``     — hạn mức riêng của lần QA Owner (`qa: true`), xem `limits.qa_ledger_user`.
"""
from __future__ import annotations

SCOPE_USER = "user"
SCOPE_GLOBAL = "global"
SCOPE_QA = "qa"

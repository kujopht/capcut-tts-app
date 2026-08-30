"""Lớp năng lực CHUYÊN BIỆT — Router LTS Phase 12.

Đây là NHÃN gắn lên `WorkerSpec.capabilities` (đã có trong `registry.
CAPABILITIES`), không phải worker/adapter mới. Bất kỳ adapter nào đã có
(`AntigravityNativeAdapter`, `OpenCodeAdapter`, ...) đều có thể tự nhận
một trong các nhãn này khi `register()` khai đúng năng lực — không cần
viết provider riêng cho từng vai trò.

`frontend_prototyper` (Lovable): CHỈ LÀ MỘT NHÃN TUỲ CHỌN. Mission nói rõ
"không tích hợp Lovable trừ khi nó tầm thường sau khi có hệ plugin chung"
— hệ plugin (`WorkerAdapter`) ĐÃ CÓ, nhưng viết một `LovableAdapter` thật
đòi hỏi API/CLI thật của Lovable mà chưa tra cứu/kiểm chứng trong lượt này
— để trống có chủ đích, không đoán bừa giao diện của nó.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LopChuyenBiet:
    ten: str
    mo_ta: str
    nang_luc: str          # tuong ung mot khoa trong registry.CAPABILITIES
    vi_du_adapter: str     # goi y adapter nao THUONG hop vai tro nay nhat


CAC_LOP: tuple = (
    LopChuyenBiet(
        "frontend_prototyper", "Dựng nhanh giao diện/luồng người dùng thử "
        "nghiệm — KHÔNG phải công việc production frontend đầy đủ.",
        "frontend_prototyper", "OpenCodeAdapter hoặc AntigravityNativeAdapter"),
    LopChuyenBiet(
        "research_agent", "Đọc rộng, tổng hợp tài liệu/kho mã, KHÔNG ghi tệp.",
        "research_agent", "bất kỳ adapter chỉ-đọc (read_scope, write_scope rỗng)"),
    LopChuyenBiet(
        "scraping_agent", "Thu thập dữ liệu web có kiểm soát — PHẢI tuân "
        "robots.txt/điều khoản, không bypass CAPTCHA/paywall (bất biến "
        "toàn hệ thống, không riêng lớp này).",
        "scraping_agent", "AntigravityNativeAdapter, worktree cô lập bắt buộc"),
    LopChuyenBiet(
        "security_reviewer", "Review bảo mật/credential/ranh giới sản xuất "
        "— KHÔNG BAO GIỜ đi Codex (rào cứng đã có ở policy.py).",
        "security_reviewer", "AntigravityNativeAdapter (worker AG_OPUS)"),
    LopChuyenBiet(
        "test_generator", "Sinh bộ kiểm thử cho mã đã có — việc cơ học, "
        "phù hợp worker rẻ/nhanh hơn là worker mạnh nhất.",
        "test_generator", "OpenCodeAdapter hoặc GrokBuildAdapter"),
    LopChuyenBiet(
        "media_agent", "Xử lý audio/hình ảnh/video — KHÔNG có adapter thật "
        "nào trong repo này xử lý media; nhãn tồn tại cho worker TƯƠNG LAI.",
        "media_agent", "chưa có adapter nào phù hợp"),
)


def tra_cuu(ten: str) -> LopChuyenBiet:
    for lop in CAC_LOP:
        if lop.ten == ten:
            return lop
    raise KeyError(f"không có lớp chuyên biệt tên {ten!r}")

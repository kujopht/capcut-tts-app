"use client";

/**
 * Bắt lỗi RENDER của trang (Fanfic AI Support) — chỉ được gắn khi bật cờ
 * (`layout.tsx`); tắt cờ thì trang hỏng hiện đúng như trước.
 *
 * Thay vì màn hình trắng: một câu nói thật, nút "Thử lại", và lối sang trợ
 * giúp kèm ngữ cảnh. Lỗi được ghi (đã làm sạch) cho bộ thu lỗi — CHỈ thông
 * điệp, không stack.
 */
import { Component, type ReactNode } from "react";
import { ghiLoi } from "@/lib/support/collector";
import { SupportHint } from "./SupportHint";

type TrangThai = { loi: boolean; duong: string };

export class SupportErrorBoundary extends Component<{ children: ReactNode }, TrangThai> {
  state: TrangThai = { loi: false, duong: "" };

  static getDerivedStateFromError(): Partial<TrangThai> {
    return { loi: true, duong: typeof location === "undefined" ? "" : location.pathname };
  }

  componentDidCatch(error: unknown) {
    ghiLoi({ kind: "render_error", code: "render_error", message: error instanceof Error ? error.message : String(error) });
  }

  componentDidUpdate() {
    // Sang trang khac (dieu huong phia client) -> bo trang thai loi cu.
    if (this.state.loi && typeof location !== "undefined" && location.pathname !== this.state.duong) {
      this.setState({ loi: false, duong: "" });
    }
  }

  render() {
    if (!this.state.loi) return this.props.children;
    return (
      <div className="page">
        <div className="empty" role="alert">
          <span className="empty-icon" aria-hidden="true">🧩</span>
          <strong>Trang này gặp lỗi khi hiển thị</strong>
          <p className="hint">Không phải lỗi của bạn. Thử tải lại; nếu vẫn lỗi, trợ lý có thể kiểm tra giúp và gửi cho quản trị viên.</p>
          <div className="row">
            <button type="button" className="btn" onClick={() => this.setState({ loi: false, duong: "" })}>
              Thử lại
            </button>
            <SupportHint code="render_error" />
          </div>
        </div>
      </div>
    );
  }
}

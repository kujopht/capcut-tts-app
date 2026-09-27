"use client";

/**
 * Cổng vào Fanfic AI Support trên trang THƯỜNG — TẮT cờ thì không một byte mã
 * Support nào được tải (ngoài chính tệp nhỏ này).
 *
 * Hai điều đo được trên bản build quyết định hình dạng tệp này:
 *
 * 1. `app/layout.tsx` là SERVER component: mọi client component nó import — kể
 *    cả qua `next/dynamic` — thành client entry của route, tải ở MỌI trang dù
 *    không render. Nên `import()` phải nằm trong một client component.
 * 2. `next/dynamic` tự nó kéo runtime ~6 KB thô vào bundle MỌI trang. Nên ở đây
 *    chỉ dùng `import()` thuần trong `useEffect`, qua MỘT điểm (`napHoTro`) —
 *    Turbopack sinh một stub loader duy nhất.
 *
 * Tệp này cố ý nằm NGOÀI `components/support/` và không import tĩnh gì từ đó
 * (có test canh ở `tests/support-v1.test.mjs`).
 */
import { Component, useEffect, useState, type ReactNode } from "react";
import { SUPPORT_ENABLED } from "@/lib/features";

type GoiHoTro = typeof import("./support/lazy");
type HintProps = Parameters<GoiHoTro["SupportHint"]>[0];

let hua: Promise<GoiHoTro> | null = null;

/** MỘT điểm nạp cho mọi thứ Support. Hỏng (mất mạng) thì lần sau thử lại. */
function napHoTro(): Promise<GoiHoTro> {
  hua ??= import("./support/lazy").catch((e: unknown) => {
    hua = null;
    throw e;
  });
  return hua;
}

/** Nút "AI kiểm tra giúp tôi" ở trạng thái lỗi. Tắt cờ: `null`, không tải gì. */
export function SupportHintGate(props: HintProps) {
  const [goi, datGoi] = useState<GoiHoTro | null>(null);
  useEffect(() => {
    if (!SUPPORT_ENABLED) return;
    let song = true;
    napHoTro().then((g) => song && datGoi(g), () => {});
    return () => {
      song = false;
    };
  }, []);
  return goi ? <goi.SupportHint {...props} /> : null;
}

/** Gắn bộ thu lỗi client MỘT lần ở layout. Tắt cờ: không tải, không gắn gì. */
export function SupportCollectorGate() {
  useEffect(() => {
    if (!SUPPORT_ENABLED) return;
    let song = true;
    let go: (() => void) | null = null;
    napHoTro().then((g) => {
      if (song) go = g.ganBoThuLoi();
    }, () => {});
    return () => {
      song = false;
      go?.();
    };
  }, []);
  return null;
}

type TrangThai = { loi: boolean; duong: string };

/**
 * Bắt lỗi RENDER của trang — `layout.tsx` chỉ gắn khi bật cờ; tắt cờ thì trang
 * hỏng hiện đúng như trước. Thay vì màn hình trắng: một câu nói thật, nút "Thử
 * lại", và (khi chunk Support tải xong) lối sang trợ giúp kèm ngữ cảnh. Phần
 * dự phòng dùng được NGAY cả khi chunk không tải được. Lỗi đi qua móc
 * `window.__fanficSupport` (bộ thu lỗi tự gắn) — CHỈ thông điệp, không stack.
 */
export class SupportBoundaryGate extends Component<{ children: ReactNode }, TrangThai> {
  state: TrangThai = { loi: false, duong: "" };

  static getDerivedStateFromError(): Partial<TrangThai> {
    return { loi: true, duong: typeof location === "undefined" ? "" : location.pathname };
  }

  componentDidCatch(error: unknown) {
    window.__fanficSupport?.ghiLoi({
      kind: "render_error",
      code: "render_error",
      message: error instanceof Error ? error.message : String(error),
    });
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
            <SupportHintGate code="render_error" />
          </div>
        </div>
      </div>
    );
  }
}

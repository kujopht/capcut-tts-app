"use client";

/**
 * Quản lý TIÊU ĐIỂM cho một hộp thoại modal — cùng quy tắc với
 * `ReportDialog`/`ConfirmDialog`, gom lại để hộp soạn bài và trình sửa hồ sơ
 * (Social & Play V1) không chép thêm hai bản:
 *
 *   * mở: tiêu điểm vào phần tử `[data-autofocus]` (hoặc chính hộp thoại);
 *   * Tab/Shift+Tab xoay vòng TRONG hộp thoại;
 *   * Escape gọi `onClose` (người gọi quyết định có đóng hay hỏi lại);
 *   * đóng: trả tiêu điểm về đúng phần tử đã mở — thiếu bước này người dùng
 *     bàn phím rơi về `<body>` và mất chỗ đứng;
 *   * khoá cuộn nền để trang phía sau không trôi dưới ngón tay trên điện thoại.
 */

import { useEffect, useRef, type RefObject } from "react";

const CO_THE_FOCUS =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

export function useDialogFocus(
  hop: RefObject<HTMLElement | null>,
  onClose: () => void,
  mo = true,
): void {
  // Luon goi ban `onClose` MOI NHAT ma khong dua no vao phu thuoc cua effect:
  // noi goi hay truyen ham inline, dua vao phu thuoc la moi lan ve lai effect
  // chay lai va tieu diem bi giat ve dau hop thoai giua luc dang go.
  const dong = useRef(onClose);
  useEffect(() => {
    dong.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!mo) return;
    const opener = document.activeElement as HTMLElement | null;
    const el = hop.current;
    const dau = el?.querySelector<HTMLElement>("[data-autofocus]");
    (dau ?? el)?.focus();
    const cuonCu = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        dong.current();
        return;
      }
      if (e.key !== "Tab" || !hop.current) return;
      const ds = [...hop.current.querySelectorAll<HTMLElement>(CO_THE_FOCUS)].filter(
        (x) => x.offsetParent !== null || x === document.activeElement,
      );
      if (!ds.length) return;
      const dauTien = ds[0];
      const cuoi = ds[ds.length - 1];
      if (e.shiftKey && (document.activeElement === dauTien || document.activeElement === hop.current)) {
        e.preventDefault();
        cuoi.focus();
      } else if (!e.shiftKey && document.activeElement === cuoi) {
        e.preventDefault();
        dauTien.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = cuonCu;
      opener?.focus?.();
    };
  }, [hop, mo]);
}

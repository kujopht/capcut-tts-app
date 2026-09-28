"use client";

/**
 * Cổng Sentry của web — gắn ở `app/layout.tsx`. TẮT (không có `NEXT_PUBLIC_SENTRY_DSN`) thì
 * không gắn trình nghe nào, không `import()` gì.
 *
 * Chỉ nghe `error`/`unhandledrejection` CỦA TRANG (bỏ lỗi từ tiện ích trình duyệt/tệp khác nguồn,
 * bỏ nhiễu ResizeObserver). Có lỗi mới nạp SDK (`lib/observability/sentry-lazy`) — MỘT điểm
 * `import()` duy nhất. Tối đa `TRAN_SU_KIEN_MOI_TRANG` sự kiện mỗi lần tải trang, mỗi chữ ký lỗi
 * một lần: một vòng lặp lỗi không biến thành một cơn mưa sự kiện.
 */
import { useEffect } from "react";
import { SENTRY_DSN, TRAN_SU_KIEN_MOI_TRANG } from "@/lib/observability/config";

type GoiSentry = typeof import("@/lib/observability/sentry-lazy");

let hua: Promise<GoiSentry> | null = null;

function napSentry(): Promise<GoiSentry> {
  hua ??= import("@/lib/observability/sentry-lazy").catch((e: unknown) => {
    hua = null;
    throw e;
  });
  return hua;
}

const daGui = new Set<string>();
let soDaGui = 0;

function chuKy(loi: unknown): string {
  if (loi instanceof Error) return `${loi.name}:${loi.message}:${(loi.stack || "").split("\n")[1] || ""}`;
  return String(loi).slice(0, 200);
}

function bao(loi: unknown, nguon: string): void {
  if (!SENTRY_DSN || soDaGui >= TRAN_SU_KIEN_MOI_TRANG) return;
  const k = chuKy(loi);
  if (daGui.has(k)) return;
  daGui.add(k);
  soDaGui += 1;
  napSentry().then((g) => g.baoLoi(loi, nguon), () => {});
}

export function SentryGate() {
  useEffect(() => {
    if (!SENTRY_DSN) return;
    const khiLoi = (e: ErrorEvent) => {
      const tep = e.filename || "";
      if (tep && !tep.startsWith(location.origin)) return;
      if (/ResizeObserver loop/i.test(e.message || "")) return;
      bao(e.error ?? new Error(e.message || "window.error"), "window.error");
    };
    const khiTuChoi = (e: PromiseRejectionEvent) => {
      const r = e.reason;
      bao(r instanceof Error ? r : new Error(String(r ?? "unhandledrejection")), "unhandledrejection");
    };
    window.addEventListener("error", khiLoi);
    window.addEventListener("unhandledrejection", khiTuChoi);
    return () => {
      window.removeEventListener("error", khiLoi);
      window.removeEventListener("unhandledrejection", khiTuChoi);
    };
  }, []);
  return null;
}

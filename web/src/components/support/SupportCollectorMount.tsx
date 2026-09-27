"use client";

/**
 * Gắn bộ thu lỗi của Fanfic AI Support — MỘT lần, ở layout, CHỈ khi bật cờ
 * (`layout.tsx` không render component này khi `SUPPORT_ENABLED` tắt).
 *
 * Không thăm dò, không request nào lúc bình thường: chỉ nghe sự kiện lỗi và
 * lỗi API (mạng hỏng / 5xx). Lỗi của chính các route `/api/support/*` bị bỏ qua
 * — báo lỗi về việc báo lỗi hỏng là một vòng lặp.
 */
import { useEffect } from "react";
import { datBoNgheLoiApi } from "@/lib/api";
import { caiBoThuLoi, ghiLoi } from "@/lib/support/collector";

export function SupportCollectorMount() {
  useEffect(() => {
    caiBoThuLoi();
    datBoNgheLoiApi((path, status, code) => {
      if (path.startsWith("/api/support/")) return;
      ghiLoi({
        kind: "api_error",
        code: status === 0 ? "api_network" : "api_5xx",
        message: `${path.split("?")[0]} ${status || "network"}${code ? ` ${code}` : ""}`,
      });
    });
    return () => datBoNgheLoiApi(null);
  }, []);
  return null;
}

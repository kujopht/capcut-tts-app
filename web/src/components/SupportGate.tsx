"use client";

/**
 * Cong vao Fanfic AI Support cho `app/layout.tsx` — TAT co thi khong mot byte ma
 * Support nao duoc tai.
 *
 * Vi sao can mot client component rieng: `layout.tsx` la SERVER component, va moi
 * client component ma no import — ke ca qua `next/dynamic` — deu thanh client
 * entry cua route, tai ngay tu dau o MOI trang du khong bao gio render (do that
 * tren ban build: chunk bo thu loi + goi y ~3.6 KB van tai o `/` khi TAT co).
 * O day `import()` nam trong mot client component, nen no CHI chay khi cong
 * thuc su render — tuc khi co bat.
 *
 * Tep nay co y nam NGOAI `components/support/` va khong import tinh gi tu do
 * (co test canh o `tests/support-v1.test.mjs`).
 */
import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import { SUPPORT_ENABLED } from "@/lib/features";

const BoThuLoi = dynamic(
  () => import("./support/SupportCollectorMount").then((m) => m.SupportCollectorMount),
  { ssr: false },
);
const RanhGioiLoi = dynamic(() => import("./support/SupportErrorBoundary").then((m) => m.SupportErrorBoundary));

/** Gan bo thu loi client. Tat co: `null`, khong tai gi. */
export function SupportCollectorGate() {
  return SUPPORT_ENABLED ? <BoThuLoi /> : null;
}

/** Boc trang bang ranh gioi loi co goi y "AI kiểm tra giúp tôi". Tat co: tra nguyen `children`. */
export function SupportBoundaryGate({ children }: { children: ReactNode }) {
  return SUPPORT_ENABLED ? <RanhGioiLoi>{children}</RanhGioiLoi> : <>{children}</>;
}

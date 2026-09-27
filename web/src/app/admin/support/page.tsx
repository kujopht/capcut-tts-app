/**
 * /admin/support — Trung tâm hỗ trợ: web đang lỗi gì, ai bị ảnh hưởng, ở bản nào.
 * Tắt cờ `NEXT_PUBLIC_SUPPORT_ENABLED` -> 404 (và không có mục điều hướng).
 * Quyền do máy chủ quyết (`/api/admin/support/*` qua `admin_profile`).
 */
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { SUPPORT_ENABLED } from "@/lib/features";
import { Loading } from "@/components/ui";
import { TrungTamHoTro } from "./TrungTamHoTro";

export default function AdminSupportPage() {
  if (!SUPPORT_ENABLED) notFound();
  return (
    <Suspense fallback={<Loading />}>
      <TrungTamHoTro />
    </Suspense>
  );
}

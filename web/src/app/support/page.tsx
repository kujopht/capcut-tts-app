/**
 * /support — Trợ giúp Fanfic World (Fanfic AI Support V1).
 *
 * Tắt cờ `NEXT_PUBLIC_SUPPORT_ENABLED` -> 404, đúng như trang chưa tồn tại.
 * Ngữ cảnh đến từ URL do `SupportHint` đặt (`?from=/chapters/x&err=audio_media`)
 * — chỉ đường dẫn và mã, không bao giờ token hay nội dung.
 */
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { SUPPORT_ENABLED } from "@/lib/features";
import { Loading } from "@/components/ui";
import { TrangHoTro } from "./TrangHoTro";

export default function SupportPage() {
  if (!SUPPORT_ENABLED) notFound();
  return (
    <Suspense fallback={<div className="page"><Loading /></div>}>
      <TrangHoTro />
    </Suspense>
  );
}

"use client";

/**
 * Nút "AI kiểm tra giúp tôi" đặt NGAY Ở trạng thái lỗi (audio không phát, tải
 * dữ liệu hỏng, trang lỗi) — không bao giờ tự bật lên thành popup.
 *
 * Dẫn tới `/support` kèm NGỮ CẢNH AN TOÀN trên URL: đường dẫn trang (không
 * query), mã lỗi đã làm sạch, mã truyện/chương. Tắt cờ -> không render gì.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SUPPORT_ENABLED } from "@/lib/features";
import { duongDanAnToan, maLoi } from "@/lib/support/sanitize";
// KHONG import support.css o day: `ui.tsx` (moi trang) nap component nay, va
// mot import CSS la tac dung phu — tat co van keo CSS vao moi trang. Nut dung
// lop co san + style noi tuyen.

export function SupportHint({
  code,
  chapterId,
  novelId,
  mode,
  compact = false,
}: {
  code: string;
  chapterId?: string;
  novelId?: string;
  mode?: "read" | "listen" | "read_listen";
  compact?: boolean;
}) {
  const pathname = usePathname();
  if (!SUPPORT_ENABLED) return null;
  const q = new URLSearchParams({ from: duongDanAnToan(pathname), err: maLoi(code) || "load_error" });
  if (chapterId) q.set("chapter", chapterId);
  if (novelId) q.set("novel", novelId);
  if (mode) q.set("rm", mode);
  return (
    <Link href={`/support?${q.toString()}`} prefetch={false} className="btn btn-ghost btn-sm"
      style={compact ? { marginLeft: "auto", display: "inline-flex", gap: 6 } : { marginTop: 8, display: "inline-flex", gap: 6 }}>
      <span aria-hidden="true">🛟</span> AI kiểm tra giúp tôi
    </Link>
  );
}

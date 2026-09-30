"use client";

/**
 * `/assistant` — trợ lý AI toàn màn hình. Lối vào CHÍNH trên di động
 * (≤640px, không nút nổi — xem `AiLauncher.tsx`), cũng dùng được trên
 * desktop. An toàn vùng-an-toàn (`env(safe-area-inset-*)`, xem `.ai-trang`
 * trong `ai.css`), không tràn ngang ở 390px.
 *
 * Trang TĨNH ở build (không có `generateStaticParams`/data fetch phía
 * server) nhưng KHÔNG nằm trong danh sách `STATIC_HREFS` của
 * `static-link-prefetch.test.mjs` — link tới nó chỉ xuất hiện trong menu
 * tài khoản (đã đóng theo mặc định, ngoại lệ IntersectionObserver), nên
 * không bắt buộc `prefetch={false}` như 13 route tĩnh gốc, dù ta vẫn đặt
 * cho nhất quán với các mục khác trong cùng menu.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AiComposer } from "@/components/ai/AiComposer";
import { AiControls } from "@/components/ai/AiControls";
import { AiConversation } from "@/components/ai/AiConversation";
import { AiWriterBar } from "@/components/ai/AiWriterBar";
import { useAi } from "@/components/ai/AiProvider";
import { AiCompanionGate } from "@/components/ai/companion/AiCompanionGate";
import { AI_ASSISTANT_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";

export default function AssistantPage() {
  const { profile, loading } = useSession();
  const { availability, enterFullscreen } = useAi();
  const router = useRouter();

  // `enterFullscreen`, KHÔNG `openAssistant`: trang này thay chỗ panel nổi —
  // nó đóng panel nổi và xoá cờ mở, nên quay về trang thường panel VẪN ĐÓNG
  // tới khi người dùng tự mở (hội thoại/lịch sử/nháp được giữ nguyên).
  useEffect(() => {
    if (!AI_ASSISTANT_ENABLED || !profile) return;
    void enterFullscreen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id]);

  /** Nút X trên trang toàn màn hình: quay lại trang trước (nếu có lịch sử
   *  trong-app), rơi về trang chủ nếu người dùng vào thẳng /assistant
   *  (đánh dấu trang, gõ URL...) — KHÔNG chỉ tắt `open` (đó là hành vi của
   *  panel nổi, không có ý nghĩa trên một route riêng). */
  const veTruoc = () => {
    if (typeof window !== "undefined" && window.history.length > 1) router.back();
    else router.push("/");
  };

  if (!AI_ASSISTANT_ENABLED) {
    return (
      <main className="ai-trang wrap stack-2">
        <h1 className="page-title">Trợ lý AI</h1>
        <p className="hint">Tính năng này chưa được bật.</p>
      </main>
    );
  }

  if (loading) return null;

  if (!profile) {
    return (
      <main className="ai-trang wrap stack-2">
        <h1 className="page-title">Trợ lý AI</h1>
        <p className="hint">Đăng nhập để trò chuyện với trợ lý AI.</p>
        <Link href="/login" className="btn btn-primary btn-sm" prefetch={false}>
          Đăng nhập
        </Link>
      </main>
    );
  }

  if (availability === false || (availability && !availability.enabled)) {
    return (
      <main className="ai-trang wrap stack-2">
        <h1 className="page-title">Trợ lý AI</h1>
        <AiCompanionGate variant="inline" />
        <p className="hint">Trợ lý AI hiện chưa khả dụng trên máy chủ.</p>
      </main>
    );
  }

  return (
    <main className="ai-trang">
      <AiControls onClose={veTruoc} />
      {/* Linh vật nằm TRONG luồng nội dung (giữa đầu trang và hội thoại) — không
          bao giờ đè lên ô soạn; tự thu lại khi bàn phím ảo mở. */}
      <AiCompanionGate variant="inline" />
      <AiWriterBar />
      <AiConversation />
      <AiComposer />
    </main>
  );
}

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
import { AI_ASSISTANT_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";

export default function AssistantPage() {
  const { profile, loading } = useSession();
  const { availability, openAssistant } = useAi();
  const router = useRouter();

  useEffect(() => {
    if (!AI_ASSISTANT_ENABLED || !profile) return;
    void openAssistant();
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
        <p className="hint">Trợ lý AI hiện chưa khả dụng trên máy chủ.</p>
      </main>
    );
  }

  return (
    <main className="ai-trang">
      <AiControls onClose={veTruoc} />
      <AiWriterBar />
      <AiConversation />
      <AiComposer />
    </main>
  );
}

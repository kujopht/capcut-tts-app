"use client";

/**
 * Lối vào mode `story` của trợ lý AI trên trang đọc chương — nút nhỏ CẠNH
 * `AskAiPanel` (không phải bên trong nó: `AskAiPanel` là "Hỏi AI" V1 cũ,
 * một cuộc hỏi-đáp trong bộ nhớ tạm cho phiên xem trang; đây là trợ lý AI
 * V1 MỚI, có lịch sử/nhiều mode). Tự ẩn khi cờ tắt (`useAi().enabled`) hoặc máy
 * chủ chưa xác nhận người này dùng được AI (`useAi().eligible`, `/api/ai/access`).
 *
 * Desktop: mở `AiPanel` nổi ngay tại chỗ. Di động (≤1023px, cùng breakpoint
 * ẩn `AiLauncher`/`AiPanel`): chuyển sang `/assistant` — không có cửa sổ
 * nổi để mở ở đó.
 */
import { useRouter } from "next/navigation";
import { focusPanelAi, sauKhiVe } from "@/lib/ai/tieuDiem";
import { useAi } from "./AiProvider";
import { FanficIcon } from "@/components/icons/FanficIcon";

const MAN_HINH_NHO = "(max-width: 1023px)";

export function AskAiAssistantStoryEntry({
  novelId,
  chapterId,
  chapterIndex,
}: {
  novelId: string;
  chapterId: string;
  chapterIndex: number;
}) {
  const { enabled, eligible, openAssistant, ensureReady } = useAi();
  const router = useRouter();

  if (!enabled || !eligible) return null;

  const bam = async () => {
    const opts = {
      mode: "story" as const,
      context: { novel_id: novelId, chapter_id: chapterId, current_chapter_index: chapterIndex },
    };
    if (typeof window !== "undefined" && window.matchMedia(MAN_HINH_NHO).matches) {
      // Di động: chỉ chuẩn bị hội thoại rồi sang `/assistant` — KHÔNG bật
      // panel nổi (nó sẽ bật lại khi quay về hoặc xoay/phóng cửa sổ).
      await ensureReady(opts);
      router.push("/assistant");
    } else {
      const dangMo = openAssistant(opts);
      sauKhiVe(() => focusPanelAi());
      await dangMo;
    }
  };

  return (
    <button type="button" className="btn btn-sm btn-ghost" onClick={() => void bam()}>
      <FanficIcon name="ai" size={15} />
      <span>Hỏi Trợ lý AI về chương này</span>
    </button>
  );
}

"use client";

/**
 * Nút mở gọn nổi của Fanfic AI Assistant — CHỈ desktop (≥1024px, ẩn bằng CSS
 * `@media`, xem `ai.css`). Di động vào trợ lý qua mục "Trợ lý AI" trong menu
 * tài khoản (`NavAuth.tsx`) → `/assistant` toàn màn hình — KHÔNG nút nổi ở
 * đó, để không che nút chat/navbar/điều khiển đọc (§11 hợp đồng).
 *
 * `right:16px; bottom:88px; z-index:56` — nằm TRÊN nút Chat V1
 * (`.chat-dock` z-index 55, đáy 0/88px tuỳ mini player), và tự nâng thêm khi
 * `GlobalMiniPlayer` hiển thị (`body:has(.mini)` — cùng kỹ thuật `ai.css`
 * dùng cho `.chat-dock`, KHÔNG sửa `chat.css`).
 *
 * F1 (QA Chrome thật, 1600×900): trước đây launcher đứng yên trong khi
 * `AiPanel` tự dịch trái theo `.chat-dock` — launcher đè lên góc cửa sổ
 * Chat V1 đang mở. Sửa: dùng CHUNG `useChatDockOffset()` với `AiPanel`, và
 * ẩn hẳn khi panel đang mở (panel đã có nút Đóng riêng trong `AiControls`,
 * launcher không còn lý do đứng chồng lên góc panel nữa).
 */
import { usePathname } from "next/navigation";
import { useSession } from "@/lib/session";
import { useAi } from "./AiProvider";
import { useChatDockOffset } from "./useChatDockOffset";
import { FanficIcon } from "@/components/icons/FanficIcon";

export function AiLauncher() {
  const { profile } = useSession();
  const { enabled, availability, open, openAssistant } = useAi();
  const dockOffset = useChatDockOffset();
  const pathname = usePathname();

  if (pathname === "/assistant") return null;
  if (!enabled || !profile) return null;
  // Đã xin availability và máy chủ báo tắt/không đủ nhà cung cấp -> không vẽ nút.
  if (availability === false || (availability && !availability.enabled)) return null;
  // Panel đang mở -> panel đã che đúng góc này và có nút Đóng riêng; launcher
  // đứng yên ở đây sẽ đè lên góc dưới-phải của chính panel (F1).
  if (open) return null;

  return (
    <button
      type="button"
      className="ai-launcher"
      aria-haspopup="dialog"
      aria-expanded={false}
      aria-label="Mở trợ lý AI"
      onClick={() => void openAssistant()}
      style={dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
    >
      <FanficIcon name="ai" size={22} />
    </button>
  );
}

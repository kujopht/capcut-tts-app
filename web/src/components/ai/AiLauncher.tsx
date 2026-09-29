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
 */
import { useSession } from "@/lib/session";
import { useAi } from "./AiProvider";
import { FanficIcon } from "@/components/icons/FanficIcon";

export function AiLauncher() {
  const { profile } = useSession();
  const { enabled, availability, open, openAssistant, closeAssistant } = useAi();

  if (!enabled || !profile) return null;
  // Đã xin availability và máy chủ báo tắt/không đủ nhà cung cấp -> không vẽ nút.
  if (availability === false || (availability && !availability.enabled)) return null;

  return (
    <button
      type="button"
      className="ai-launcher"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
      onClick={() => (open ? closeAssistant() : void openAssistant())}
    >
      <FanficIcon name="ai" size={22} />
    </button>
  );
}

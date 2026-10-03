"use client";

/**
 * Cửa sổ trợ lý AI trên desktop — 380px × min(600px, 100dvh-160px), neo phải
 * dưới `AiLauncher`. Nếu `.chat-dock` (Chat V1) đang có cửa sổ mở, panel này
 * tự dịch sang TRÁI của dock bằng `useChatDockOffset()` (đo DOM trực tiếp,
 * KHÔNG sửa `components/chat/**`).
 *
 * KHÔNG mount trên `/assistant` — trang đó tự vẽ đúng ba component con
 * (`AiControls`/`AiWriterBar`/`AiConversation`/`AiComposer`) trong bố cục
 * toàn màn hình riêng của nó; mount thêm panel nổi ở đây từng khiến
 * `.ai-panel-tin` xuất hiện HAI LẦN trong DOM (bài học F3).
 */
import { useRef } from "react";
import { usePathname } from "next/navigation";
import { focusNutMoAi, sauKhiVe } from "@/lib/ai/tieuDiem";
import { useAi } from "./AiProvider";
import { useChatDockOffset } from "./useChatDockOffset";
import { AiControls } from "./AiControls";
import { AiConversation } from "./AiConversation";
import { AiComposer } from "./AiComposer";
import { AiWriterBar } from "./AiWriterBar";

export function AiPanel() {
  const { enabled, access, availability, open, closeAssistant } = useAi();
  const dockOffset = useChatDockOffset();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const pathname = usePathname();

  if (pathname === "/assistant") return null;
  if (!enabled || !open) return null;
  // Panel khôi phục từ phiên (tải lại trang) nhưng máy chủ nay báo không đủ quyền -> đóng.
  if (access === false) return null;
  if (availability === false || (availability && !availability.enabled)) return null;

  return (
    <div
      ref={panelRef}
      className="ai-panel"
      role="dialog"
      aria-modal="false"
      tabIndex={-1}
      aria-label={availability ? `${availability.name} — trợ lý AI` : "Trợ lý AI"}
      style={dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
      onKeyDown={(e) => {
        // Hộp thoại không-modal: Escape đóng và trả focus về nút mở (WAI-ARIA dialog). Bỏ qua khi đang gõ dấu bằng IME (Escape huỷ chữ
        // đang soạn), khi popover cài đặt đang mở (nó tự đóng bằng Escape — chỉ đóng MỘT lớp mỗi lần bấm), và khi sự kiện đã được xử lý.
        if (e.key !== "Escape" || e.defaultPrevented || e.nativeEvent.isComposing) return;
        if (panelRef.current?.querySelector(".ai-caidat")) return;
        e.stopPropagation();
        closeAssistant();
        sauKhiVe(() => focusNutMoAi());
      }}
    >
      <AiControls />
      <AiWriterBar />
      <AiConversation />
      <AiComposer />
    </div>
  );
}

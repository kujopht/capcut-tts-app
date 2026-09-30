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
import { useAi } from "./AiProvider";
import { useChatDockOffset } from "./useChatDockOffset";
import { AiControls } from "./AiControls";
import { AiConversation } from "./AiConversation";
import { AiComposer } from "./AiComposer";
import { AiWriterBar } from "./AiWriterBar";

export function AiPanel() {
  const { enabled, availability, open } = useAi();
  const dockOffset = useChatDockOffset();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const pathname = usePathname();

  if (pathname === "/assistant") return null;
  if (!enabled || !open) return null;
  if (availability === false || (availability && !availability.enabled)) return null;

  return (
    <div
      ref={panelRef}
      className="ai-panel"
      role="dialog"
      aria-modal="false"
      aria-label={availability ? `${availability.name} — trợ lý AI` : "Trợ lý AI"}
      style={dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
    >
      <AiControls />
      <AiWriterBar />
      <AiConversation />
      <AiComposer />
    </div>
  );
}

"use client";

/**
 * Cửa sổ trợ lý AI trên desktop — 380px × min(600px, 100dvh-160px), neo phải
 * dưới `AiLauncher`. Nếu `.chat-dock` (Chat V1) đang có cửa sổ mở, panel này
 * tự dịch sang TRÁI của dock bằng `ResizeObserver` đo trực tiếp DOM — KHÔNG
 * sửa `components/chat/**`, chỉ quan sát nó từ bên ngoài.
 */
import { useEffect, useRef, useState } from "react";
import { useAi } from "./AiProvider";
import { AiControls } from "./AiControls";
import { AiConversation } from "./AiConversation";
import { AiComposer } from "./AiComposer";

export function AiPanel() {
  const { enabled, availability, open } = useAi();
  const [dockOffset, setDockOffset] = useState(0);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (typeof document === "undefined") return;
    let ro: ResizeObserver | null = null;
    const capNhat = () => {
      const el = document.querySelector<HTMLElement>(".chat-dock");
      ro?.disconnect();
      if (el) {
        ro = new ResizeObserver((entries) => {
          for (const e of entries) setDockOffset(e.contentRect.width > 0 ? e.contentRect.width + 12 : 0);
        });
        ro.observe(el);
        const w = el.getBoundingClientRect().width;
        setDockOffset(w > 0 ? w + 12 : 0);
      } else {
        setDockOffset(0);
      }
    };
    capNhat();
    const mo = new MutationObserver(capNhat);
    mo.observe(document.body, { childList: true, subtree: true });
    return () => {
      ro?.disconnect();
      mo.disconnect();
    };
  }, []);

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
      <AiConversation />
      <AiComposer />
    </div>
  );
}

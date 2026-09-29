"use client";

/**
 * Cửa sổ trợ lý AI trên desktop — 380px × min(600px, 100dvh-160px), neo phải
 * dưới `AiLauncher`. Nếu `.chat-dock` (Chat V1) đang có cửa sổ mở, panel này
 * tự dịch sang TRÁI của dock bằng `ResizeObserver` đo trực tiếp DOM — KHÔNG
 * sửa `components/chat/**`, chỉ quan sát nó từ bên ngoài.
 *
 * V1 khung tối giản (đóng/mở + hiển thị tin nhắn thô + ô nhập) — tách thành
 * `AiConversation`/`AiComposer`/`AiControls` ở bước kế tiếp cho markdown an
 * toàn, trích dẫn, Dừng/Tạo lại/Lịch sử/chọn mode/usage.
 */
import { useEffect, useRef, useState } from "react";
import { useAi } from "./AiProvider";
import { FanficIcon } from "@/components/icons/FanficIcon";

export function AiPanel() {
  const { enabled, availability, open, closeAssistant, messages, streaming, streamingText, sendMessage } = useAi();
  const [dockOffset, setDockOffset] = useState(0);
  const [nhap, setNhap] = useState("");
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

  const gui = () => {
    if (!nhap.trim()) return;
    void sendMessage(nhap);
    setNhap("");
  };

  return (
    <div
      ref={panelRef}
      className="ai-panel"
      role="dialog"
      aria-modal="false"
      aria-label={availability ? `${availability.name} — trợ lý AI` : "Trợ lý AI"}
      style={dockOffset ? ({ ["--ai-dock-offset" as string]: `${dockOffset}px` } as React.CSSProperties) : undefined}
    >
      <header className="ai-panel-dau">
        <span className="ai-panel-ten">
          <FanficIcon name="ai" size={18} /> {availability ? availability.name : "Trợ lý AI"}
        </span>
        <button type="button" className="ai-nut ai-nut-nho" aria-label="Đóng trợ lý AI" onClick={closeAssistant}>
          <FanficIcon name="close" size={16} />
        </button>
      </header>
      <div className="ai-panel-tin">
        {messages.map((m) => (
          <div key={m.message_id} className={`ai-bong ai-bong-${m.role}`}>
            {m.content}
          </div>
        ))}
        {streaming && streamingText ? <div className="ai-bong ai-bong-assistant">{streamingText}</div> : null}
      </div>
      <form
        className="ai-panel-soan"
        onSubmit={(e) => {
          e.preventDefault();
          gui();
        }}
      >
        <textarea
          className="ai-o"
          rows={2}
          maxLength={4000}
          placeholder="Nhắn cho trợ lý AI…"
          value={nhap}
          onChange={(e) => setNhap(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              gui();
            }
          }}
        />
        <button type="submit" className="ai-nut" disabled={streaming || !nhap.trim()} aria-label="Gửi">
          <FanficIcon name="send" size={16} />
        </button>
      </form>
    </div>
  );
}

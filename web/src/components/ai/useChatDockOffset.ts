"use client";

/**
 * Đo bề rộng `.chat-dock` (Chat V1) SỐNG bằng `ResizeObserver` +
 * `MutationObserver` (dock chỉ tồn tại trong DOM khi có cửa sổ mở — xem
 * `ChatDock.tsx`, trả `null` khi rỗng). Dùng CHUNG cho `AiLauncher` VÀ
 * `AiPanel` — cả hai đều phải tự dịch trái ngần ấy để không bao giờ đè lên
 * cửa sổ Chat V1 đang mở (bài học F1: trước đây chỉ panel đo, launcher đứng
 * yên và đè lên góc cửa sổ chat).
 *
 * KHÔNG import gì từ `components/chat/**` — chỉ quan sát DOM đã render bằng
 * `querySelector(".chat-dock")` từ bên ngoài.
 */
import { useEffect, useState } from "react";

export function useChatDockOffset(): number {
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    if (typeof document === "undefined") return;
    let ro: ResizeObserver | null = null;
    const capNhat = () => {
      const el = document.querySelector<HTMLElement>(".chat-dock");
      ro?.disconnect();
      if (el) {
        ro = new ResizeObserver((entries) => {
          for (const e of entries) setOffset(e.contentRect.width > 0 ? e.contentRect.width + 12 : 0);
        });
        ro.observe(el);
        const w = el.getBoundingClientRect().width;
        setOffset(w > 0 ? w + 12 : 0);
      } else {
        setOffset(0);
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

  return offset;
}

"use client";

/**
 * Khung chat ben phai (DESKTOP) — mo tren trang truyen/cong dong ma KHONG dieu
 * huong di dau. Gan mot lan o `app/layout.tsx` nen doi trang van con nguyen
 * (ca nhap dang go, vi nhap nam o `ChatProvider`).
 *
 * Di dong (<=640px) khong co drawer: nut Tin nhan dua thang toi /messages.
 * O /messages drawer cung an (ChatProvider tra `drawer = null` o do).
 */
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef } from "react";
import { conversationIdFor } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatAvatar, tenHien } from "./ChatAvatar";
import { ChatComposer } from "./ChatComposer";
import { ChatErrorState, ChatNetBanner } from "./ChatErrorState";
import { ChatThread } from "./ChatThread";
import { ChatUserHeader } from "./ChatUserHeader";
import { UnreadBadge } from "./UnreadBadge";

export function ChatDrawer() {
  const { drawer, identityOf, minimizeDrawer, closeDrawer, status, conversations } = useChat();
  const router = useRouter();
  const tieuDe = useId();
  const hop = useRef<HTMLElement | null>(null);

  // Mo drawer (khong phai tu thu nho) -> dua tieu diem vao trong, de ban phim di tiep duoc.
  const peerId = drawer?.peerId ?? null;
  const thuNho = drawer?.minimized ?? false;
  useEffect(() => {
    if (peerId && !thuNho) hop.current?.querySelector<HTMLTextAreaElement>(".chat-soan-o")?.focus();
  }, [peerId, thuNho]);

  if (!drawer) return null;
  const it = identityOf(drawer.peerId);
  const ten = tenHien(it);
  const chuaDoc = conversations.find((c) => c.id === conversationIdFor(drawer.peerId))?.unread ?? 0;
  const dong = () => {
    closeDrawer();
    document.querySelector<HTMLButtonElement>(".chat-launcher")?.focus();
  };

  if (drawer.minimized) {
    return (
      <button type="button" className="chat-drawer-thu" onClick={() => minimizeDrawer(false)}
        aria-label={`Mở lại cuộc trò chuyện với ${ten}${chuaDoc > 0 ? `, ${chuaDoc} tin chưa đọc` : ""}`}>
        <ChatAvatar identity={it} size="sm" />
        <span className="truncate">{ten}</span>
        <UnreadBadge count={chuaDoc} />
      </button>
    );
  }

  const coNoiDung = status === "ready" || status === "reconnecting" || status === "offline";
  return (
    <section
      ref={hop}
      className="chat-drawer"
      role="dialog"
      aria-modal="false"
      aria-labelledby={tieuDe}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          dong();
        }
      }}
    >
      <ChatUserHeader identity={it} titleId={tieuDe}>
        <button type="button" className="chat-nut" aria-label="Mở trong trang Tin nhắn"
          title="Mở trong trang Tin nhắn"
          onClick={() => router.push(`/messages?c=${encodeURIComponent(drawer.peerId)}`)}>
          <span aria-hidden="true">⤢</span>
        </button>
        <button type="button" className="chat-nut" aria-label="Thu nhỏ" title="Thu nhỏ" onClick={() => minimizeDrawer(true)}>
          <span aria-hidden="true">—</span>
        </button>
        <button type="button" className="chat-nut" aria-label="Đóng cuộc trò chuyện" title="Đóng (Esc)" onClick={dong}>
          <span aria-hidden="true">✕</span>
        </button>
      </ChatUserHeader>
      <ChatErrorState status={status} compact />
      <ChatNetBanner status={status} />
      {coNoiDung ? <ChatThread peerId={drawer.peerId} /> : <div className="chat-tin-hop" />}
      <ChatComposer peerId={drawer.peerId} peerName={it?.found ? ten : undefined} />
    </section>
  );
}

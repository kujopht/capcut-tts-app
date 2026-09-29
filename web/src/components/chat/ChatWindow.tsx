"use client";

/**
 * MOT cua so chat noi trong Chat Dock (desktop/may tinh bang). Khong keo tha duoc (co y).
 *
 *   Mo       : dau (avatar + khung + ten + cap/danh xung, nut goi "sắp có", menu ⋯, thu nho, dong) +
 *              cuoc tro chuyen + o soan.
 *   Thu nho  : chi thanh dau — bam de mo lai; cham chua doc cua RIENG cuoc nay.
 *
 * "Da doc": chi khi cua so HIEN va khong thu nho (xem `ChatProvider` — `dangXem`). Mo/khoi phuc do nguoi
 * dung bam -> tieu diem vao o soan; phuc hoi sau khi tai lai trang thi KHONG cuop tieu diem.
 */
import { useEffect, useId, useRef } from "react";
import { conversationIdFor } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatAvatar, tenHien } from "./ChatAvatar";
import { ChatCallButtons } from "./ChatCallButtons";
import { ChatComposer } from "./ChatComposer";
import { ChatErrorState, ChatNetBanner } from "./ChatErrorState";
import { ChatThread, KhungCho } from "./ChatThread";
import { ChatThreadMenu } from "./ChatThreadMenu";
import { ChatUserHeader } from "./ChatUserHeader";
import { UnreadBadge } from "./UnreadBadge";

/** Dong mot cua so -> tieu diem sang o soan cua cua so CON MO khac, khong thi ve nut Tin nhan. */
function tieuDiemSauKhiDong(conLai: string | undefined) {
  requestAnimationFrame(() => {
    const o = conLai
      ? document.querySelector<HTMLTextAreaElement>(`[data-chat-win="${CSS.escape(conLai)}"] .chat-soan-o`)
      : null;
    (o ?? document.querySelector<HTMLButtonElement>(".chat-launcher"))?.focus();
  });
}

export function ChatWindow({ peerId, minimized }: { peerId: string; minimized: boolean }) {
  const { identityOf, status, conversations, minimizeChat, closeChat, ensureThread, openThread, focusRequest, dock } =
    useChat();
  const tieuDe = useId();
  const hop = useRef<HTMLElement | null>(null);
  const it = identityOf(peerId);
  const ten = tenHien(it);
  const chuaDoc = conversations.find((c) => c.id === conversationIdFor(peerId))?.unread ?? 0;
  const coNoiDung = status === "ready" || status === "reconnecting" || status === "offline";

  // Co ket noi -> tai lich su. Thu nho: KHONG danh dau da doc (nguoi dung chua xem).
  useEffect(() => {
    if (!coNoiDung) return;
    if (minimized) ensureThread(peerId);
    else openThread(peerId);
  }, [coNoiDung, minimized, peerId, ensureThread, openThread]);

  // Nguoi dung vua MO/KHOI PHUC cua so nay -> tieu diem vao o soan.
  useEffect(() => {
    if (minimized || focusRequest?.peerId !== peerId) return;
    const k = requestAnimationFrame(() => hop.current?.querySelector<HTMLTextAreaElement>(".chat-soan-o")?.focus());
    return () => cancelAnimationFrame(k);
  }, [focusRequest, peerId, minimized]);

  const dong = () => {
    const conLai = dock.find((w) => w.peerId !== peerId && !w.minimized)?.peerId;
    closeChat(peerId);
    tieuDiemSauKhiDong(conLai);
  };

  if (minimized) {
    return (
      <section className="chat-win chat-win-thu" data-chat-win={peerId} aria-label={`Trò chuyện với ${ten} — thu nhỏ`}>
        <div className="chat-win-dau">
          <button type="button" className="chat-win-mo" onClick={() => minimizeChat(peerId, false)}
            aria-label={`Mở lại cuộc trò chuyện với ${ten}${chuaDoc > 0 ? `, ${chuaDoc} tin chưa đọc` : ""}`}>
            <ChatAvatar identity={it} size="sm" />
            <span className="truncate chat-win-ten">{ten}</span>
            <UnreadBadge count={chuaDoc} />
          </button>
          <button type="button" className="chat-nut chat-nut-nho" aria-label={`Đóng cuộc trò chuyện với ${ten}`}
            title="Đóng" onClick={dong}>
            <span aria-hidden="true">✕</span>
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      ref={hop}
      className="chat-win"
      data-chat-win={peerId}
      role="dialog"
      aria-modal="false"
      aria-labelledby={tieuDe}
      onKeyDown={(e) => {
        // Hop thoai (chan / bao cao, render qua portal) van noi su kien React len day — Escape cua NO chi
        // dong no.
        if (e.key === "Escape" && !(e.target as Element | null)?.closest?.('.modal, [aria-modal="true"]')) {
          e.stopPropagation();
          dong();
        }
      }}
    >
      <div className="chat-win-dau">
        <ChatUserHeader identity={it} titleId={tieuDe}>
          <ChatCallButtons peerName={ten} />
          {coNoiDung ? <ChatThreadMenu key={peerId} peerId={peerId} peerName={ten} coTrangTin /> : null}
          <button type="button" className="chat-nut chat-nut-nho" aria-label={`Thu nhỏ cuộc trò chuyện với ${ten}`}
            title="Thu nhỏ" onClick={() => minimizeChat(peerId, true)}>
            <span aria-hidden="true">—</span>
          </button>
          <button type="button" className="chat-nut chat-nut-nho" aria-label={`Đóng cuộc trò chuyện với ${ten}`}
            title="Đóng (Esc)" onClick={dong}>
            <span aria-hidden="true">✕</span>
          </button>
        </ChatUserHeader>
      </div>
      <ChatErrorState status={status} compact />
      <ChatNetBanner status={status} />
      {coNoiDung ? <ChatThread peerId={peerId} /> : status === "connecting" ? <KhungCho /> : <div className="chat-tin-hop" />}
      {/* Loi / bi day sang tab khac: khong gui duoc — khong bay mot o soan vo dung. */}
      {status === "error" || status === "kicked" ? null : (
        <ChatComposer peerId={peerId} peerName={it?.found ? ten : undefined} />
      )}
    </section>
  );
}

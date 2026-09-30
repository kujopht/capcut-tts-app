"use client";

/**
 * Chat Dock — cac cua so chat NOI o goc duoi-phai, kieu Messenger desktop. Gan MOT lan o `app/layout.tsx`
 * (trong `ChatProvider`): doi trang chi thay `{children}`, nen cac cua so, nhap dang go va luong tin nhan
 * SONG XUYEN ROUTE; tai lai trang thi cua so + nhap duoc phuc hoi (`sessionStorage` cua tab).
 *
 *   >= 1024 px : toi da 3 cua so hien (vua be rong), phan du vao NGAN TRAN "+N".
 *   641–1023   : toi da 1 cua so.
 *   <= 640     : KHONG co dock — cuoc tro chuyen toan man hinh o /messages.
 *   /messages  : dock an (khong gian day du thay the); cac cua so van con, hien lai khi roi trang.
 */
import { useEffect, useRef, useState } from "react";
import { chiaCuaSo, type DockWindow } from "@/lib/chat/dock";
import { CHAT_V1_ENABLED } from "@/lib/features";
import { useChat } from "./ChatProvider";
import { ChatAvatar, tenHien } from "./ChatAvatar";
import { ChatWindow } from "./ChatWindow";
import { UnreadBadge } from "./UnreadBadge";
import { FanficIcon } from "@/components/icons/FanficIcon";

function NganTran({ items }: { items: DockWindow[] }) {
  const { identityOf, conversations, openChat, closeChat } = useChat();
  const [mo, setMo] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);
  const chuaDoc = (peerId: string) => conversations.find((c) => c.peerId === peerId)?.unread ?? 0;
  const tong = items.reduce((n, w) => n + chuaDoc(w.peerId), 0);

  useEffect(() => {
    if (!mo) return;
    const ngoai = (e: PointerEvent) => {
      if (!hop.current?.contains(e.target as Node)) setMo(false);
    };
    document.addEventListener("pointerdown", ngoai);
    return () => document.removeEventListener("pointerdown", ngoai);
  }, [mo]);

  return (
    <div ref={hop} className="chat-tran" onKeyDown={(e) => {
      if (e.key === "Escape" && mo) {
        e.stopPropagation();
        setMo(false);
      }
    }}>
      <button type="button" className="chat-tran-nut" aria-haspopup="menu" aria-expanded={mo}
        aria-label={`${items.length} cuộc trò chuyện khác${tong > 0 ? `, ${tong} tin chưa đọc` : ""}`}
        onClick={() => setMo((v) => !v)}>
        <span aria-hidden="true">+{items.length}</span>
        <UnreadBadge count={tong} className="chat-tran-cham" />
      </button>
      {mo ? (
        <ul className="chat-tran-ds" role="menu" aria-label="Cuộc trò chuyện đang mở khác">
          {items.map((w) => {
            const it = identityOf(w.peerId);
            const ten = tenHien(it);
            return (
              <li key={w.peerId} className="chat-tran-muc" role="none">
                <button type="button" role="menuitem" className="chat-tran-mo" onClick={() => {
                  setMo(false);
                  openChat(w.peerId);
                }}>
                  <ChatAvatar identity={it} size="sm" />
                  <span className="truncate">{ten}</span>
                  <UnreadBadge count={chuaDoc(w.peerId)} />
                </button>
                <button type="button" className="chat-nut chat-nut-nho" aria-label={`Đóng cuộc trò chuyện với ${ten}`}
                  onClick={() => closeChat(w.peerId)}>
                  <FanficIcon name="close" size={14} />
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export function ChatDock() {
  const { dock, maxVisible, available } = useChat();
  // Canary: tai khoan chua duoc mo (hoac dang hoi) -> khong cua so nao, ke ca cua so phuc hoi tu tab.
  if (!CHAT_V1_ENABLED || available !== true || maxVisible === 0 || dock.length === 0) return null;
  const { hien, tran } = chiaCuaSo(dock, maxVisible);
  return (
    <div className="chat-dock" role="region" aria-label="Cửa sổ tin nhắn">
      {/* flex-direction: row-reverse — cua so MOI NHAT sat mep phai, ngan tran o ben trai cung. */}
      {hien.map((w) => <ChatWindow key={w.peerId} peerId={w.peerId} minimized={w.minimized} />)}
      {tran.length ? <NganTran items={tran} /> : null}
    </div>
  );
}

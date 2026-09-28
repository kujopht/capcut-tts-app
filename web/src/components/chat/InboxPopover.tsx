"use client";

/** Bang Tin nhan nho duoi nut navbar (DESKTOP) — cung hinh voi bang thong bao. */
import Link from "next/link";
import { useChat } from "./ChatProvider";
import { ChatErrorState, ChatNetBanner } from "./ChatErrorState";
import { ConversationList } from "./ConversationList";

export function InboxPopover({ onClose }: { onClose: () => void }) {
  const { status, openDrawer, unreadTotal } = useChat();
  return (
    <div className="menu-panel chat-inbox" role="dialog" aria-label="Tin nhắn">
      <div className="chat-inbox-dau">
        <strong className="chat-inbox-tieu-de">
          Tin nhắn
          {unreadTotal > 0 ? <span className="hint"> · {unreadTotal} chưa đọc</span> : null}
        </strong>
        <Link href="/messages" className="btn btn-ghost btn-sm" prefetch={false} onClick={onClose}>
          Mở trang Tin nhắn
        </Link>
      </div>
      <ChatErrorState status={status} compact />
      <ChatNetBanner status={status} />
      <ConversationList
        compact
        limit={8}
        onSelect={(peerId) => {
          openDrawer(peerId);
          onClose();
        }}
      />
    </div>
  );
}

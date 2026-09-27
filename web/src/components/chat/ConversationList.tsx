"use client";

/** Danh sach hoi thoai — dung chung cho InboxPopover, trang /messages. */
import { khiNao } from "@/lib/time";
import type { ChatConversation } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatAvatar, tenHien } from "./ChatAvatar";
import { ChatEmptyState } from "./ChatEmptyState";
import { UnreadBadge } from "./UnreadBadge";

export function ConversationList({
  onSelect,
  activePeerId,
  limit,
  compact = false,
}: {
  onSelect: (peerId: string) => void;
  activePeerId?: string | null;
  limit?: number;
  compact?: boolean;
}) {
  const { conversations, identityOf, status } = useChat();
  const ds: ChatConversation[] = limit ? conversations.slice(0, limit) : conversations;

  if (status !== "ready" && status !== "reconnecting" && status !== "offline") return null;
  if (!ds.length) {
    return (
      <ChatEmptyState
        title="Chưa có cuộc trò chuyện nào"
        hint="Mở trang cá nhân của một bạn đọc hoặc tác giả rồi bấm “Nhắn tin” để bắt đầu."
      />
    );
  }

  return (
    <ul className={`chat-ds${compact ? " chat-ds-gon" : ""}`} aria-label="Cuộc trò chuyện">
      {ds.map((c) => {
        const it = identityOf(c.peerId);
        const ten = tenHien(it);
        const dang = c.peerId === activePeerId;
        return (
          <li key={c.id}>
            <button
              type="button"
              className={`chat-ds-muc${dang ? " chat-ds-muc-dang" : ""}${c.unread > 0 ? " chat-ds-muc-moi" : ""}`}
              onClick={() => onSelect(c.peerId)}
              aria-current={dang ? "true" : undefined}
              aria-label={`${ten}${c.unread > 0 ? `, ${c.unread} tin chưa đọc` : ""}`}
            >
              <ChatAvatar identity={it} size={compact ? "sm" : "md"} />
              <span className="chat-ds-chu">
                <span className="chat-ds-dong">
                  <strong className="truncate">{ten}</strong>
                  {c.lastTime ? (
                    <span className="hint chat-ds-luc">{khiNao(new Date(c.lastTime).toISOString())}</span>
                  ) : null}
                </span>
                <span className="chat-ds-dong">
                  <span className="hint truncate chat-ds-tin">
                    {c.lastFromMe ? "Bạn: " : ""}
                    {c.lastText || "…"}
                  </span>
                  <UnreadBadge count={c.unread} />
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

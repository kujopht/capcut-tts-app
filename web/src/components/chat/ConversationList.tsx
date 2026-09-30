"use client";

/** Danh sach hoi thoai — dung chung cho InboxPopover, trang /messages. */
import { khiNao } from "@/lib/time";
import type { ChatConversation } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatAvatar, tenHien } from "./ChatAvatar";
import { ChatEmptyState } from "./ChatEmptyState";
import { UnreadBadge } from "./UnreadBadge";
import { FanficIcon } from "@/components/icons/FanficIcon";

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

  if (status === "connecting") {
    return (
      <ul className="chat-ds" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <li key={i} className="chat-ds-sk">
            <span className="sk sk-tron" />
            <span className="chat-ds-chu">
              <span className="sk sk-text" style={{ width: `${[58, 44, 66][i]}%` }} />
              <span className="sk sk-text" style={{ width: `${[82, 70, 76][i]}%` }} />
            </span>
          </li>
        ))}
      </ul>
    );
  }
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
    <ul
      className={`chat-ds${compact ? " chat-ds-gon" : ""}`}
      aria-label="Cuộc trò chuyện"
      onKeyDown={(e) => {
        // Mui ten len/xuong di giua cac cuoc tro chuyen (Tab van di binh thuong).
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        const nut = [...e.currentTarget.querySelectorAll<HTMLButtonElement>(".chat-ds-muc")];
        const i = nut.indexOf(document.activeElement as HTMLButtonElement);
        if (i < 0) return;
        e.preventDefault();
        nut[(i + (e.key === "ArrowDown" ? 1 : nut.length - 1)) % nut.length]?.focus();
      }}
    >
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
              aria-label={`${ten}${c.unread > 0 ? `, ${c.unread} tin chưa đọc` : ""}${c.muted ? ", đã tắt thông báo" : ""}`}
            >
              <ChatAvatar identity={it} size={compact ? "sm" : "md"} />
              <span className="chat-ds-chu">
                <span className="chat-ds-dong">
                  <strong className="truncate">{ten}</strong>
                  {c.muted ? (
                    <span className="chat-ds-tat" aria-hidden="true" title="Đã tắt thông báo">
                      <FanficIcon name="mute" size={14} />
                    </span>
                  ) : null}
                  {c.lastTime ? (
                    <span className="hint chat-ds-luc">{khiNao(new Date(c.lastTime).toISOString())}</span>
                  ) : null}
                </span>
                <span className="chat-ds-dong">
                  <span className="hint truncate chat-ds-tin">
                    {c.lastFromMe ? "Bạn: " : ""}
                    {c.lastText || "…"}
                  </span>
                  <UnreadBadge count={c.unread} className={c.muted ? "chat-badge-tat" : ""} />
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

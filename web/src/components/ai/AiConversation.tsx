"use client";

/**
 * Danh sách tin nhắn của trợ lý AI. Văn bản streaming được render AN TOÀN
 * bằng markdown tối giản (`markdownLite.tsx`) — KHÔNG `dangerouslySetInnerHTML`
 * bất kể nội dung model trả về là gì. Trích dẫn (`citations`) là liên kết
 * thật tới `/novels/{id}` và `/chapters/{id}`.
 */
import { useEffect, useRef } from "react";
import Link from "next/link";
import { useAi } from "./AiProvider";
import { renderMarkdownLite } from "./markdownLite";
import { FanficIcon } from "@/components/icons/FanficIcon";

export function AiConversation() {
  const { messages, streaming, streamingText, conversationId, mode } = useAi();
  const cuoiRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, streamingText]);

  const trong = messages.length === 0 && !streaming;

  return (
    <div className="ai-panel-tin" aria-live="polite" aria-label="Cuộc trò chuyện với trợ lý AI">
      {trong ? (
        <div className="ai-trong">
          <FanficIcon name="ai" size={28} />
          <p className="hint">
            {conversationId
              ? "Bắt đầu cuộc trò chuyện mới."
              : mode === "story"
                ? "Hỏi trợ lý về chương bạn đang đọc."
                : "Hỏi trợ lý AI bất cứ điều gì."}
          </p>
        </div>
      ) : null}
      {messages.map((m) => (
        <div key={m.message_id} className={`ai-bong ai-bong-${m.role}${m.status === "error" ? " ai-bong-loi" : ""}`}>
          <div className="ai-bong-noidung">{renderMarkdownLite(m.content)}</div>
          {m.status === "stopped" ? <span className="ai-bong-ghichu">Đã dừng</span> : null}
          {m.citations.length ? (
            <ul className="ai-trichdan">
              {m.citations.map((c, i) => (
                <li key={i}>
                  <Link href={c.chapter_id ? `/chapters/${c.chapter_id}` : `/novels/${c.novel_id}`}>
                    {c.chapter_title || "Xem nguồn"}
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
      {streaming && streamingText ? (
        <div className="ai-bong ai-bong-assistant">
          <div className="ai-bong-noidung">{renderMarkdownLite(streamingText)}</div>
        </div>
      ) : null}
      {streaming && !streamingText ? (
        <div className="ai-bong ai-bong-assistant ai-dang-go" aria-label="Trợ lý đang soạn trả lời">
          <span />
          <span />
          <span />
        </div>
      ) : null}
      <div ref={cuoiRef} />
    </div>
  );
}

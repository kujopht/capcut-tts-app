"use client";

/**
 * Danh sách tin nhắn của trợ lý AI. Văn bản streaming được render AN TOÀN
 * bằng markdown tối giản (`markdownLite.tsx`) — KHÔNG `dangerouslySetInnerHTML`
 * bất kể nội dung model trả về là gì. Trích dẫn (`citations`) là liên kết
 * thật tới `/novels/{id}` và `/chapters/{id}`.
 */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAi } from "./AiProvider";
import { renderMarkdownLite } from "./markdownLite";
import { FanficIcon } from "@/components/icons/FanficIcon";
import { AI_PROJECT_FIELD_LABELS, type AiProjectField } from "@/lib/ai/types";

const CAC_TRUONG_DU_AN = Object.keys(AI_PROJECT_FIELD_LABELS) as AiProjectField[];

/**
 * "Lưu vào dự án" — CHỈ hiện ở mode `writer` khi đã chọn dự án
 * (`activeProjectId`), và LUÔN cần người dùng bấm chọn mục đích rõ ràng
 * (nối vào Ý tưởng/Dàn ý/Nhân vật/Thế giới/Ghi chú) — không có đường nào tự
 * lưu sau khi stream xong (§6: lưu vào dự án chỉ qua nút của người dùng).
 */
function AiSaveToProjectMenu({ content }: { content: string }) {
  const { activeProjectId, saveToProjectField } = useAi();
  const [mo, setMo] = useState(false);
  if (!activeProjectId) return null;
  return (
    <div className="ai-luu-hop">
      <button
        type="button"
        className="ai-nut ai-nut-nho"
        aria-label="Lưu vào dự án"
        aria-expanded={mo}
        title="Lưu vào dự án"
        onClick={() => setMo((v) => !v)}
      >
        <FanficIcon name="download" size={13} />
      </button>
      {mo ? (
        <ul className="ai-luu-ds" role="menu" aria-label="Lưu vào mục nào">
          {CAC_TRUONG_DU_AN.map((f) => (
            <li key={f}>
              <button
                type="button"
                className="ai-luu-muc"
                role="menuitem"
                onClick={() => {
                  void saveToProjectField(f, content, "append");
                  setMo(false);
                }}
              >
                {AI_PROJECT_FIELD_LABELS[f]}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function AiConversation() {
  const { messages, streaming, streamingText, conversationId, mode, regenerate } = useAi();
  const cuoiRef = useRef<HTMLDivElement | null>(null);
  // "Tao lai" la dieu khien THUONG cho tin tra loi CUOI (ke ca da dung/loi) — khong chi trong banner loi.
  const idCuoi = [...messages].reverse().find((m) => m.role === "assistant")?.message_id;

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
      {messages.map((m) => {
        const rong = m.role === "assistant" && !m.content.trim();
        return (
        <div key={m.message_id} className={`ai-bong ai-bong-${m.role}${m.status === "error" ? " ai-bong-loi" : ""}`}>
          {/*
            F2: trước đây một lượt bị dừng/lỗi TRƯỚC token đầu tiên để lại
            một bong bóng nội dung rỗng gần như vô hình — người dùng thấy
            câu hỏi của mình "rơi vào im lặng". Rỗng + stopped/error thì hiện
            một câu giải thích rõ ràng thay vì markdown của chuỗi rỗng.
          */}
          {rong && m.status === "stopped" ? (
            <div className="ai-bong-noidung ai-bong-rong">Đã dừng — chưa có nội dung.</div>
          ) : rong && m.status === "error" ? (
            <div className="ai-bong-noidung ai-bong-rong">Không có phản hồi do lỗi.</div>
          ) : (
            <div className="ai-bong-noidung">{renderMarkdownLite(m.content)}</div>
          )}
          {m.status === "stopped" && !rong ? <span className="ai-bong-ghichu">Đã dừng</span> : null}
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
          {mode === "writer" && m.role === "assistant" && m.status === "complete" ? (
            <AiSaveToProjectMenu content={m.content} />
          ) : null}
          {m.message_id === idCuoi && !streaming ? (
            <button type="button" className="ai-nut-tao-lai" onClick={() => void regenerate()}
              aria-label="Tạo lại câu trả lời">
              <FanficIcon name="refresh" size={14} />
              Tạo lại
            </button>
          ) : null}
        </div>
        );
      })}
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

"use client";

/**
 * Ô soạn tin của trợ lý AI — Enter gửi, Shift+Enter xuống dòng, nút
 * Gửi/Dừng đổi chỗ cho nhau khi đang stream (bấm Dừng huỷ `fetch` đang đọc,
 * KHÔNG chặn được lượt hỏi tiếp theo).
 */
import { useState } from "react";
import { useAi } from "./AiProvider";
import { FanficIcon } from "@/components/icons/FanficIcon";

const TOI_DA_KY_TU = 4000;

export function AiComposer() {
  const { streaming, sendMessage, stopStreaming, availability } = useAi();
  const [nhap, setNhap] = useState("");
  const tatDangNhap = availability !== null && availability !== false && !availability.enabled;

  const gui = () => {
    const trimmed = nhap.trim();
    if (!trimmed || streaming) return;
    void sendMessage(trimmed);
    setNhap("");
  };

  return (
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
        maxLength={TOI_DA_KY_TU}
        placeholder={tatDangNhap ? "Trợ lý AI hiện chưa khả dụng." : "Nhắn cho trợ lý AI…"}
        value={nhap}
        disabled={tatDangNhap}
        aria-label="Nội dung gửi trợ lý AI"
        onChange={(e) => setNhap(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            gui();
          }
        }}
      />
      {streaming ? (
        <button type="button" className="ai-nut ai-nut-dung" aria-label="Dừng trả lời" onClick={stopStreaming}>
          <FanficIcon name="stop" size={16} />
        </button>
      ) : (
        <button
          type="submit"
          className="ai-nut ai-nut-gui"
          disabled={tatDangNhap || !nhap.trim()}
          aria-label="Gửi"
        >
          <FanficIcon name="send" size={16} />
        </button>
      )}
    </form>
  );
}

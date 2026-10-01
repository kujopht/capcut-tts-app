"use client";

/**
 * Ô soạn tin của trợ lý AI — Enter gửi, Shift+Enter xuống dòng, nút
 * Gửi/Dừng đổi chỗ cho nhau khi đang stream (bấm Dừng huỷ `fetch` đang đọc,
 * KHÔNG chặn được lượt hỏi tiếp theo).
 *
 * Nội dung ô soạn (`draft`) nằm ở `AiProvider`, KHÔNG phải state cục bộ —
 * để các chip gợi ý mode `writer` (Brainstorm/Dàn ý/Nhân vật/...,
 * `AiWriterBar.tsx`) chèn được một câu mở đầu vào đây; người dùng VẪN phải
 * tự bấm Gửi (§6 — mọi hành động chỉ đọc, không có gì tự gửi thay người).
 */
import { useAi } from "./AiProvider";
import { daHetLuot, dinhDangGio } from "@/lib/ai/hanMuc";
import { FanficIcon } from "@/components/icons/FanficIcon";

const TOI_DA_KY_TU = 4000;

export function AiComposer() {
  const { streaming, sendMessage, stopStreaming, availability, draft, setDraft } = useAi();
  const tatDangNhap = availability !== null && availability !== false && !availability.enabled;
  // Hết lượt RIÊNG của người này: khoá ô soạn thay vì để họ gõ rồi bị từ chối. Quá giờ làm mới thì mở lại (để máy chủ quyết).
  const hanMuc = availability ? availability.limits : undefined;
  const hetLuot = daHetLuot(hanMuc);
  const gioLamMoi = hanMuc ? dinhDangGio(hanMuc.reset_at) : "";
  const khoa = tatDangNhap || hetLuot;

  const gui = () => {
    const trimmed = draft.trim();
    if (!trimmed || streaming || khoa) return;
    void sendMessage(trimmed);
    setDraft("");
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
        placeholder={
          tatDangNhap
            ? "Trợ lý AI hiện chưa khả dụng."
            : hetLuot
              ? `Bạn đã hết lượt hôm nay${gioLamMoi ? ` — làm mới lúc ${gioLamMoi}.` : "."}`
              : "Nhắn cho trợ lý AI…"
        }
        value={draft}
        disabled={khoa}
        aria-label="Nội dung gửi trợ lý AI"
        onChange={(e) => setDraft(e.target.value)}
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
          disabled={khoa || !draft.trim()}
          aria-label="Gửi"
        >
          <FanficIcon name="send" size={16} />
        </button>
      )}
    </form>
  );
}

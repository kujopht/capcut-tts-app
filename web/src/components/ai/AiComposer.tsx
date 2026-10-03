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
import { useLayoutEffect, useRef } from "react";
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

  // Ô soạn TỰ GIÃN theo nội dung (tới `max-height` của `.ai-o`, vượt thì cuộn trong ô): trước đây cố định 2 dòng nên tin dài/nhiều dòng
  // chỉ thấy 2 dòng. Đo `scrollHeight` sau khi trả `height` về auto; cộng viền vì `box-sizing: border-box`.
  const oRef = useRef<HTMLTextAreaElement | null>(null);
  useLayoutEffect(() => {
    const el = oRef.current;
    if (!el) return;
    el.style.height = "auto";
    // Đang ẩn (panel nổi `display:none` ở ≤1023px): `scrollHeight` = 0 — đừng ghim chiều cao 0, để CSS quyết khi hiện lại.
    const h = el.scrollHeight;
    el.style.height = h > 0 ? `${h + (el.offsetHeight - el.clientHeight)}px` : "";
  }, [draft]);

  const gui = () => {
    const trimmed = draft.trim();
    if (!trimmed || streaming || khoa) return;
    // `false`: một lượt khác đang giữ khoá gửi (vd. hội thoại mới còn đang được tạo, `streaming` chưa bật) — tin KHÔNG được
    // nhận, nên GIỮ bản nháp thay vì xoá: nếu không, chữ người dùng vừa gõ biến mất mà không có gì báo.
    if (sendMessage(trimmed)) setDraft("");
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
        ref={oRef}
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
          // Đang gõ dấu bằng IME (Telex/VNI của hệ điều hành, bộ gõ CJK…): Enter chỉ CHỐT chữ đang soạn, không phải
          // "gửi" — nếu không, tin bị gửi dở dang giữa lúc gõ. Safari báo `keyCode 229` thay vì `isComposing`.
          if (e.nativeEvent.isComposing || e.keyCode === 229) return;
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

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
import { daHetLuot } from "@/lib/ai/hanMuc";
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

/** Còn cách đáy bao nhiêu px thì vẫn coi là "đang ở đáy" (đủ rộng cho một dòng chữ mới, đủ hẹp để cuộn lên 1 vuốt là thoát). */
const NGUONG_DAY_PX = 80;

export function AiConversation() {
  const { messages, streaming, streamingText, conversationId, mode, regenerate, availability } = useAi();
  const danhSachRef = useRef<HTMLDivElement | null>(null);
  /** Người dùng đang ở (gần) đáy => tin mới/chữ mới tự cuộn theo; cuộn lên đọc thì KHÔNG bị giật xuống nữa. */
  const batDay = useRef(true);
  const soTinTruoc = useRef(0);
  const hoiThoaiTruoc = useRef<string | null>(null);
  /** Vị trí cuộn + chiều cao nội dung ngay sau lần vẽ trước: để phát hiện người dùng vừa kéo lên NGAY CẢ KHI sự kiện
   *  `scroll` (bắn ở khung hình kế tiếp) chưa kịp báo trước lần cập nhật chữ kế — không thì lần đó vẫn giật xuống đáy. */
  const viTriTruoc = useRef({ top: 0, height: 0 });
  // Hết lượt của chính người này: "Tạo lại" chắc chắn bị từ chối, nên không mời bấm.
  const hetLuot = daHetLuot(availability ? availability.limits : undefined);
  // "Tao lai" la dieu khien THUONG cho tin tra loi CUOI (ke ca da dung/loi) — khong chi trong banner loi.
  const idCuoi = [...messages].reverse().find((m) => m.role === "assistant")?.message_id;

  const khiCuon = () => {
    const el = danhSachRef.current;
    if (el) batDay.current = el.scrollHeight - el.scrollTop - el.clientHeight < NGUONG_DAY_PX;
  };

  useEffect(() => {
    const el = danhSachRef.current;
    if (!el) return;
    // Nội dung KHÔNG co lại mà vị trí cuộn lại nhỏ đi so với lần trước => người dùng vừa kéo lên: thôi bám đáy.
    // (Nội dung co lại, vd. bỏ câu trả lời cũ khi "Tạo lại", làm trình duyệt tự kẹp scrollTop — không phải do người dùng.)
    const truoc = viTriTruoc.current;
    if (el.scrollHeight >= truoc.height - 1 && el.scrollTop < truoc.top - 8) batDay.current = false;
    // Đổi hội thoại, hoặc người dùng vừa gửi tin mới: luôn xuống đáy. Chữ đang stream: chỉ theo khi đang ở đáy.
    const cuoi = messages[messages.length - 1];
    if (hoiThoaiTruoc.current !== conversationId) batDay.current = true;
    else if (messages.length > soTinTruoc.current && cuoi?.role === "user") batDay.current = true;
    hoiThoaiTruoc.current = conversationId;
    soTinTruoc.current = messages.length;
    // `scrollTop` của CHÍNH khung này, KHÔNG `scrollIntoView`: cái sau còn cuộn cả trang phía sau panel nổi.
    if (batDay.current) el.scrollTop = el.scrollHeight;
    viTriTruoc.current = { top: el.scrollTop, height: el.scrollHeight };
  }, [messages, streamingText, conversationId]);

  const trong = messages.length === 0 && !streaming;

  return (
    // `aria-busy` khi đang stream: trình đọc màn hình đợi câu trả lời xong rồi mới đọc, thay vì đọc từng mẩu chữ mới.
    <div
      ref={danhSachRef}
      className="ai-panel-tin"
      aria-live="polite"
      aria-busy={streaming}
      aria-label="Cuộc trò chuyện với trợ lý AI"
      onScroll={khiCuon}
    >
      {trong ? (
        <div className="ai-trong">
          <FanficIcon name="ai" size={28} />
          <p className="hint">
            {/* Story mode nói ĐÚNG phạm vi backend V1 — không hứa quá khả năng. */}
            {mode === "story"
              ? "Bản beta: trợ lý chỉ đọc phần đầu của chương bạn đang mở — chưa đọc được các chương khác hay cả bộ truyện."
              : conversationId
                ? "Bắt đầu cuộc trò chuyện mới."
                : "Hỏi trợ lý AI bất cứ điều gì."}
          </p>
        </div>
      ) : null}
      {messages.map((m) => {
        const rong = m.role === "assistant" && !m.content.trim();
        const chuaGui = m.role === "user" && m.status === "not_sent";
        return (
        <div
          key={m.message_id}
          className={`ai-bong ai-bong-${m.role}${m.status === "error" ? " ai-bong-loi" : ""}${chuaGui ? " ai-bong-chua-gui" : ""}`}
        >
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
          {/* Máy chủ từ chối lượt này TRƯỚC khi nhận (hết hạn mức, quá nhanh, mất mạng…): tin không có trong hội
              thoại thật — nói thẳng, đừng để nó trông như đã gửi. Lý do nằm ở khung báo lỗi phía trên. */}
          {chuaGui ? <span className="ai-bong-ghichu ai-bong-chua-gui-nhan" role="status">Chưa gửi</span> : null}
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
          {m.message_id === idCuoi && !streaming && !hetLuot ? (
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
    </div>
  );
}

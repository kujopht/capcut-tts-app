"use client";

/**
 * Thanh điều khiển của trợ lý AI: tên + chọn mode, Lịch sử (mở/xoá hội
 * thoại), Hội thoại mới, Tạo lại, usage/limit, và các trạng thái lỗi thân
 * thiện theo mã lỗi §10 — KHÔNG BAO GIỜ hiện tên provider/model.
 */
import { useEffect, useRef, useState } from "react";
import { useAi } from "./AiProvider";
import { AI_MODES, AI_MODE_LABELS, type AiErrorCode } from "@/lib/ai/types";
import { FanficIcon } from "@/components/icons/FanficIcon";

/**
 * Popover cài đặt ký ức — bật/tắt ghi nhớ (`memory_enabled`) và "Xoá toàn bộ
 * ký ức AI" (§5). Xoá dùng XÁC NHẬN TRONG TRANG hai bước (bấm lần 1 hiện
 * cảnh báo + nút "Xác nhận xoá", bấm lần 2 mới gọi API) — KHÔNG
 * `window.confirm` (chặn được bằng test tĩnh, và nhất quán với
 * `ConfirmDialog` dùng nơi khác trong kho).
 */
function AiSettingsPopover({ onClose }: { onClose: () => void }) {
  const { preferences, loadPreferences, setMemoryEnabled, deleteAllMemory } = useAi();
  const [xacNhanXoa, setXacNhanXoa] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void loadPreferences();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const ngoai = (e: MouseEvent) => {
      if (!hop.current?.contains(e.target as Node)) onClose();
    };
    const phim = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", ngoai);
    document.addEventListener("keydown", phim);
    return () => {
      document.removeEventListener("mousedown", ngoai);
      document.removeEventListener("keydown", phim);
    };
  }, [onClose]);

  const ghiNho = preferences?.memory_enabled ?? true;

  return (
    <div className="ai-caidat" ref={hop} role="dialog" aria-label="Cài đặt ký ức trợ lý AI">
      <label className="ai-caidat-dong">
        <span>Ghi nhớ hội thoại</span>
        <input
          type="checkbox"
          checked={ghiNho}
          onChange={(e) => void setMemoryEnabled(e.target.checked)}
          aria-label="Bật/tắt ghi nhớ hội thoại"
        />
      </label>
      <p className="hint ai-caidat-giaithich">
        {ghiNho
          ? "Hội thoại, tóm tắt và sở thích tường minh được lưu lại."
          : "Hội thoại mới sẽ KHÔNG được lưu quá phiên xem trang này."}
      </p>
      <div className="ai-caidat-sep" role="separator" />
      {!xacNhanXoa ? (
        <button type="button" className="btn btn-sm btn-ghost ai-caidat-xoa" onClick={() => setXacNhanXoa(true)}>
          Xoá toàn bộ ký ức AI
        </button>
      ) : (
        <div className="ai-caidat-xacnhan">
          <p className="hint">Xoá toàn bộ hội thoại, tóm tắt và sở thích đã lưu? Không thể hoàn tác.</p>
          <div className="row">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setXacNhanXoa(false)}>
              Huỷ
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void deleteAllMemory(false);
                setXacNhanXoa(false);
                onClose();
              }}
            >
              Xác nhận xoá
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function dinhDangGio(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/** Thông điệp thân thiện theo mã lỗi — KHÔNG lộ provider/model (§0.3, §11). */
function thongDiepLoi(code: AiErrorCode, resetAt?: string | null): string {
  switch (code) {
    case "ai_not_enabled":
      return "Trợ lý AI chưa được bật.";
    case "ai_no_provider":
    case "ai_provider_unavailable":
      return "Trợ lý AI đang tạm gián đoạn. Vui lòng thử lại sau ít phút.";
    case "ai_rate_limited":
      return "Bạn đang hỏi hơi nhanh — chờ một chút rồi thử lại.";
    case "ai_budget_exhausted":
      return resetAt ? `Đã dùng hết lượt hỏi hôm nay. Làm mới lúc ${dinhDangGio(resetAt)}.` : "Đã dùng hết lượt hỏi hôm nay.";
    case "ai_busy":
      return "Trợ lý AI đang bận, vui lòng thử lại sau.";
    case "ai_context_too_large":
      return "Cuộc trò chuyện đã quá dài — hãy bắt đầu một hội thoại mới.";
    case "ai_provider_interrupted":
      return "Phản hồi bị ngắt giữa chừng. Bấm \"Tạo lại\" để thử lần nữa.";
    case "ai_forbidden":
      return "Hội thoại này không thuộc về bạn.";
    case "ai_not_found":
      return "Không tìm thấy hội thoại.";
    default:
      return "Mất kết nối mạng. Kiểm tra đường truyền rồi thử lại.";
  }
}

export function AiControls({ onClose }: { onClose?: () => void } = {}) {
  const {
    availability,
    closeAssistant,
    historyOpen,
    toggleHistory,
    conversations,
    conversationId,
    selectConversation,
    deleteConversationById,
    newConversation,
    mode,
    setMode,
    error,
    regenerate,
    streaming,
    messages,
    ephemeral,
  } = useAi();
  const [caiDatMo, setCaiDatMo] = useState(false);

  const coTraLoiCuoi = messages.some((m) => m.role === "assistant");

  return (
    <div className="ai-panel-dieukhien">
      <header className="ai-panel-dau">
        <span className="ai-panel-ten">
          <FanficIcon name="ai" size={18} /> {availability ? availability.name : "Trợ lý AI"}
          {ephemeral ? <span className="ai-badge-ephemeral" title="Hội thoại này không được lưu quá phiên xem trang">Không lưu lịch sử</span> : null}
        </span>
        <div className="ai-panel-dau-nut">
          <select
            className="ai-mode"
            aria-label="Chọn chế độ trợ lý"
            value={mode}
            disabled={Boolean(conversationId)}
            title={conversationId ? "Chế độ áp dụng cho hội thoại mới" : undefined}
            onChange={(e) => setMode(e.target.value as (typeof AI_MODES)[number])}
          >
            {AI_MODES.map((m) => (
              <option key={m} value={m}>
                {AI_MODE_LABELS[m]}
              </option>
            ))}
          </select>
          <button type="button" className="ai-nut ai-nut-nho" aria-label="Hội thoại mới" title="Hội thoại mới"
            onClick={() => void newConversation()}>
            <FanficIcon name="plus" size={16} />
          </button>
          <button
            type="button"
            className="ai-nut ai-nut-nho"
            aria-label="Lịch sử hội thoại"
            aria-expanded={historyOpen}
            title="Lịch sử"
            onClick={toggleHistory}
          >
            <FanficIcon name="history" size={16} />
          </button>
          <span className="ai-caidat-hop">
            <button
              type="button"
              className="ai-nut ai-nut-nho"
              aria-label="Cài đặt ký ức"
              aria-expanded={caiDatMo}
              title="Cài đặt ký ức"
              onClick={() => setCaiDatMo((v) => !v)}
            >
              <FanficIcon name="settings" size={16} />
            </button>
            {caiDatMo ? <AiSettingsPopover onClose={() => setCaiDatMo(false)} /> : null}
          </span>
          <button
            type="button"
            className="ai-nut ai-nut-nho"
            aria-label="Đóng trợ lý AI"
            onClick={() => {
              closeAssistant();
              onClose?.();
            }}
          >
            <FanficIcon name="close" size={16} />
          </button>
        </div>
      </header>

      {availability && availability.limits ? (
        <div className="ai-usage hint">
          Đã dùng {availability.limits.used_today.toLocaleString("vi-VN")}/
          {availability.limits.limit_today.toLocaleString("vi-VN")} lượt hôm nay
        </div>
      ) : null}

      {error ? (
        <div className="ai-loi" role="alert">
          <span>{thongDiepLoi(error.code, error.reset_at)}</span>
          {error.code === "ai_provider_interrupted" && coTraLoiCuoi && !streaming ? (
            <button type="button" className="btn btn-sm" onClick={() => void regenerate()}>
              Tạo lại
            </button>
          ) : null}
        </div>
      ) : null}

      {historyOpen ? (
        <ul className="ai-lichsu" role="menu" aria-label="Lịch sử hội thoại">
          {conversations.length === 0 ? <li className="hint ai-lichsu-rong">Chưa có hội thoại nào.</li> : null}
          {conversations.map((c) => (
            <li key={c.conversation_id} className={c.conversation_id === conversationId ? "ai-lichsu-dangmo" : undefined}>
              <button type="button" className="ai-lichsu-mo" onClick={() => void selectConversation(c.conversation_id)}>
                <span className="truncate">{c.title || AI_MODE_LABELS[c.mode]}</span>
              </button>
              <button
                type="button"
                className="ai-nut ai-nut-nho"
                aria-label={`Xoá hội thoại ${c.title || AI_MODE_LABELS[c.mode]}`}
                onClick={() => void deleteConversationById(c.conversation_id)}
              >
                <FanficIcon name="trash" size={14} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

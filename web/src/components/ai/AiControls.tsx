"use client";

/**
 * Thanh điều khiển của trợ lý AI: tên + chọn mode, Lịch sử (mở/xoá hội
 * thoại), Hội thoại mới, Tạo lại, usage/limit, và các trạng thái lỗi thân
 * thiện theo mã lỗi §10 — KHÔNG BAO GIỜ hiện tên provider/model.
 */
import { useEffect, useRef, useState } from "react";
import { useAi } from "./AiProvider";
import { AI_MODES, AI_MODE_LABELS, type AiBudgetScope, type AiErrorCode } from "@/lib/ai/types";
import { daHetLuot, dinhDangGio, nhanHanMuc, thongDiepHetLuot } from "@/lib/ai/hanMuc";
import { focusNutMoAi, sauKhiVe } from "@/lib/ai/tieuDiem";
import { FanficIcon } from "@/components/icons/FanficIcon";
import { AI_COMPANION_ENABLED } from "@/lib/features";

/**
 * Mục cài đặt của linh vật (Ẩn / Giảm chuyển động / Đặt lại vị trí) nạp LƯỜI qua `import()` thuần — như `AiCompanionGate`. Cờ TẮT →
 * `settingsLoader` là `null` nên không còn nhánh nào tham chiếu module đó: không một byte mã linh vật nằm trong JS ban đầu (trước đây
 * `import` tĩnh kéo `companionPrefs` vào chunk chung dù cờ tắt, đo ≈ +0,4 KB gzip trên MỌI trang).
 */
type SettingsComponent = () => React.ReactNode;
const settingsLoader: (() => Promise<SettingsComponent>) | null = AI_COMPANION_ENABLED
  ? () => import("./companion/CompanionSettings").then((m) => m.CompanionSettings)
  : null;

function CompanionSettingsSlot() {
  const [Comp, setComp] = useState<SettingsComponent | null>(null);
  useEffect(() => {
    if (!settingsLoader) return;
    let alive = true;
    settingsLoader().then((c) => {
      if (alive) setComp(() => c);
    }).catch(() => { /* không tải được — popover vẫn đủ các mục của trợ lý */ });
    return () => {
      alive = false;
    };
  }, []);
  return Comp ? <Comp /> : null;
}

/*
 * Dòng hạn mức dưới tiêu đề (`nhanHanMuc`) CHỈ nói về hạn mức RIÊNG của người đang dùng: "Hôm nay còn 3/5 lượt hỏi ·
 * làm mới lúc 07:00". Không còn phần trăm, không còn số token, không bao giờ có mức dùng toàn site / công suất nhà
 * cung cấp (những thứ đó chỉ ở /admin/ai). Phần trăm "Đã dùng 51% hạn mức hôm nay" từng hiện cạnh câu "đã hết lượt":
 * nó đo ngân sách token cũ theo hạng tài khoản, còn trần thật là số LƯỢT — hai thước đo khác nhau đặt cạnh nhau.
 */

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
      {AI_COMPANION_ENABLED ? <CompanionSettingsSlot /> : null}
    </div>
  );
}

/** Thông điệp thân thiện theo mã lỗi — KHÔNG lộ provider/model (§0.3, §11). */
function thongDiepLoi(code: AiErrorCode, resetAt?: string | null, scope?: AiBudgetScope): string {
  switch (code) {
    case "ai_not_enabled":
      return "Trợ lý AI chưa được bật.";
    case "ai_no_provider":
    case "ai_provider_unavailable":
      return "Trợ lý AI đang tạm gián đoạn. Vui lòng thử lại sau ít phút.";
    case "ai_rate_limited":
      return "Bạn đang hỏi hơi nhanh — chờ một chút rồi thử lại.";
    case "ai_budget_exhausted":
      // Nói ĐÚNG điều gì đã hết (lượt của bạn / công suất chung "không phải do bạn" / hạn mức QA), không số liệu chung.
      return thongDiepHetLuot(scope, dinhDangGio(resetAt));
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
  const hanMuc = availability ? availability.limits : undefined;
  const dongHanMuc = hanMuc ? nhanHanMuc(hanMuc, dinhDangGio(hanMuc.reset_at)) : "";

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
              if (onClose) onClose();
              // Panel nổi: nút mở hiện lại ngay khi panel đóng — trả focus về đó (trang /assistant có `onClose` riêng).
              else sauKhiVe(() => focusNutMoAi());
            }}
          >
            <FanficIcon name="close" size={16} />
          </button>
        </div>
      </header>

      {hanMuc && dongHanMuc ? (
        <div className={`ai-usage hint${daHetLuot(hanMuc) ? " ai-usage-het" : ""}`}>{dongHanMuc}</div>
      ) : null}

      {error ? (
        <div className="ai-loi" role="alert">
          <span>{thongDiepLoi(error.code, error.reset_at, error.scope)}</span>
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

/**
 * Kiểu dữ liệu Fanfic AI Assistant V1 — khớp §10/§11 hợp đồng
 * (`server/ai_assistant/routes.py`, cùng kho backend). MỘT nguồn chân lý
 * duy nhất cho cả `client.ts`, `sse.ts` và các component `components/ai/*`.
 *
 * Tên/model provider KHÔNG có mặt ở đây — người dùng thường không bao giờ
 * thấy chúng (§0.3 hợp đồng).
 */

export type AiMode = "general" | "story" | "support" | "writer";

export const AI_MODES: AiMode[] = ["general", "story", "support", "writer"];

/** Nhãn tiếng Việt hiển thị cho người dùng — KHÔNG lộ tên provider/model. */
export const AI_MODE_LABELS: Record<AiMode, string> = {
  general: "Trợ lý chung",
  story: "Truyện",
  support: "Hỗ trợ",
  writer: "Studio viết",
};

export interface AiAvailability {
  enabled: boolean;
  reason: string | null;
  name: string;
  modes: AiMode[];
  web_search: boolean;
  limits?: {
    used_today: number;
    limit_today: number;
    reset_at: string | null;
  };
}

export interface AiConversationSummary {
  conversation_id: string;
  mode: AiMode;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export type AiMessageStatus = "complete" | "stopped" | "error";

export interface AiCitation {
  novel_id: string;
  chapter_id: string;
  chapter_title?: string;
  excerpt?: string;
}

export interface AiMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  status: AiMessageStatus;
  citations: AiCitation[];
  created_at: string;
}

export interface AiConversationDetail {
  conversation_id: string;
  mode: AiMode;
  title: string;
  messages: AiMessage[];
}

export interface AiConversationContext {
  novel_id?: string;
  chapter_id?: string;
  current_chapter_index?: number;
  project_id?: string;
}

/** Mã lỗi ổn định §10 — KHÔNG bịa thêm mã mới ở tầng giao diện. */
export type AiErrorCode =
  | "ai_not_enabled"
  | "ai_no_provider"
  | "ai_rate_limited"
  | "ai_budget_exhausted"
  | "ai_busy"
  | "ai_context_too_large"
  | "ai_provider_unavailable"
  | "ai_provider_interrupted"
  | "ai_forbidden"
  | "ai_not_found"
  | "network_error";

export interface AiErrorInfo {
  code: AiErrorCode;
  message: string;
  reset_at?: string | null;
}

/** Sự kiện SSE đã phân tích — hợp đồng §10. */
export type AiStreamEvent =
  | { type: "meta"; message_id: string; conversation_id: string }
  | { type: "delta"; text: string }
  | { type: "citations"; items: AiCitation[] }
  | { type: "usage"; input_tokens: number; output_tokens: number; used_today: number | null }
  | { type: "done"; status: AiMessageStatus }
  | { type: "error"; code: AiErrorCode; message: string; reset_at?: string | null };

export interface AiPreferences {
  memory_enabled: boolean;
  preferences: Record<string, unknown>;
}

export interface AiProjectSummary {
  project_id: string;
  title: string;
  updated_at: string;
}

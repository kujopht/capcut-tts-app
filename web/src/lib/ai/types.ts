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
  // Beta: backend V1 chỉ đưa phần đầu CHƯƠNG ĐANG MỞ vào ngữ cảnh (xem
  // docs/ai/AI_ASSISTANT_V1.md "Story mode — thực tế nhận được gì").
  story: "Truyện (beta)",
  support: "Hỗ trợ",
  writer: "Studio viết",
};

/**
 * Hạn mức RIÊNG của người đang đăng nhập — đúng thứ máy chủ sẽ thực thi ở lượt gửi kế tiếp. Không có mức dùng
 * toàn site hay công suất nhà cung cấp ở đây (chỉ `/admin/ai` thấy). Xem `lib/ai/hanMuc.ts`.
 */
export interface AiAllowance {
  requests_used: number;
  /** `null` = máy chủ không đặt trần số lượt: giao diện không có "x/y lượt" để hiện. */
  requests_limit: number | null;
  requests_remaining: number | null;
  exhausted: boolean;
  /** ISO (nửa đêm UTC kế tiếp); giao diện đổi sang giờ địa phương. */
  reset_at: string | null;
}

/** Điều gì đã hết khi `ai_budget_exhausted`: lượt của chính bạn / công suất chung của site / hạn mức QA của Owner. */
export type AiBudgetScope = "user" | "global" | "qa";

export interface AiAvailability {
  enabled: boolean;
  reason: string | null;
  name: string;
  modes: AiMode[];
  web_search: boolean;
  limits?: AiAllowance;
}

export interface AiConversationSummary {
  conversation_id: string;
  mode: AiMode;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  /** `true` khi hội thoại được tạo lúc `memory_enabled=false` — không được lưu lại quá phiên (§5). */
  ephemeral?: boolean;
}

/**
 * `not_sent` là trạng thái CHỈ có ở phía client: máy chủ từ chối lượt này TRƯỚC khi nhận (hết hạn mức, quá
 * nhanh, đang bận, mất mạng…) nên tin KHÔNG có trong hội thoại thật — giao diện phải nói đúng điều đó thay vì
 * để nó trông như đã gửi.
 */
export type AiMessageStatus = "complete" | "stopped" | "error" | "not_sent";

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
  /** `true` = hội thoại này KHÔNG lưu quá phiên (`memory_enabled=false` lúc tạo). */
  ephemeral?: boolean;
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
  /** Chỉ có ở `ai_budget_exhausted`; thiếu (máy chủ cũ) thì coi như "user". */
  scope?: AiBudgetScope;
}

/** Sự kiện SSE đã phân tích — hợp đồng §10. */
export type AiStreamEvent =
  | { type: "meta"; message_id: string; conversation_id: string }
  | { type: "delta"; text: string }
  | { type: "citations"; items: AiCitation[] }
  | {
      type: "usage";
      input_tokens: number;
      output_tokens: number;
      used_today: number | null;
      /** "qa" = lượt QA của Owner (hạn mức QA riêng); mặc định "user". */
      lane: "user" | "qa";
      /** Hạn mức riêng sau lượt này, CHƯA kiểm kiểu (bộ tách SSE không import gì): đọc bằng `docHanMuc`; `null` nếu máy chủ không gửi. */
      allowance: unknown;
    }
  | { type: "done"; status: AiMessageStatus }
  | { type: "error"; code: AiErrorCode; message: string; reset_at?: string | null; scope?: AiBudgetScope };

export interface AiPreferences {
  memory_enabled: boolean;
  preferences: Record<string, unknown>;
}

export interface AiProjectSummary {
  project_id: string;
  title: string;
  updated_at: string;
}

/**
 * Dự án viết (`writer` mode, §6) — `outline`/`characters`/`world` ở backend
 * là `Dict[str, Any]` (JSON tự do), KHÔNG phải chuỗi. Giao diện V1 chỉ cần
 * MỘT trường văn bản mỗi mục, nên quy ước lưu dưới khoá `text`
 * (`{ text: "..." }`) — xem `projectFieldText()`/`withProjectFieldText()`
 * trong `client.ts`. Bất kỳ hình dạng JSON nào khác (từ một bản ghi cũ hoặc
 * client khác) đều đọc được: field không đúng quy ước hiện NHƯ RỖNG thay vì
 * vỡ giao diện, và Lưu luôn ghi lại đúng quy ước `{ text }`.
 */
export interface AiProjectDetail {
  project_id: string;
  title: string;
  premise: string;
  outline: Record<string, unknown>;
  characters: Record<string, unknown>;
  world: Record<string, unknown>;
  notes: string;
  updated_at: string;
}

export type AiProjectJsonField = "outline" | "characters" | "world";
export type AiProjectTextField = "premise" | "notes";
/** Mọi mục có thể "Lưu vào dự án" từ một tin nhắn trợ lý. */
export type AiProjectField = AiProjectTextField | AiProjectJsonField;

export const AI_PROJECT_FIELD_LABELS: Record<AiProjectField, string> = {
  premise: "Ý tưởng",
  outline: "Dàn ý",
  characters: "Nhân vật",
  world: "Thế giới",
  notes: "Ghi chú",
};

/** Trần ký tự phía giao diện — khớp `ai_projects` §5 (premise/notes 4000,
 *  outline/characters/world_json 8000; trừ hao cho khung `{"text":"..."}`). */
export const AI_PROJECT_FIELD_MAX: Record<AiProjectField, number> = {
  premise: 4000,
  notes: 4000,
  outline: 7900,
  characters: 7900,
  world: 7900,
};

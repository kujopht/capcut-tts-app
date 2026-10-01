/**
 * Bảng điều khiển AI (`/admin/ai`) — client + kiểu dữ liệu cho
 * `server/ai_assistant/control/*`.
 *
 * Tự viết một `requestAi()` nhỏ thay vì tái dùng `request()` trong
 * `lib/api.ts` (hàm đó không export) — vẫn dùng LẠI đúng `API_BASE`,
 * `getToken()`, `ApiError` để không lệch quy ước xác thực/lỗi của kho.
 *
 * KHÔNG có bất kỳ hàm/kiểu nào nhận hoặc trả API key thật — chỉ
 * `secret_ref`, tên biến môi trường, và vân tay đã che (`fingerprint`).
 */

import { API_BASE, ApiError, getToken } from "@/lib/api";

export type AiProviderType =
  | "gemini"
  | "groq"
  | "workers_ai"
  | "qwen"
  | "azure_openai"
  | "openrouter";

export type AiSlotHealthStatus =
  | "HEALTHY"
  | "COOLDOWN"
  | "DISABLED"
  | "MISSING_SECRET"
  | "OVER_CAP"
  | "DEGRADED";

export type AiConfigState = "ok" | "empty" | "corrupt" | "unavailable" | "stale";

export interface AiProviderSummary {
  type: AiProviderType;
  label: string;
  enabled: boolean;
  healthy_slots: number;
  slots: number;
}

export interface AiOverview {
  state: AiConfigState;
  day: string;
  ai_enabled: boolean;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  errors: number;
  rate_limited: number;
  est_cost_micro_usd: number;
  /** `null` = không đo được (ledger chưa bật) — KHÔNG phải 0. */
  active_users: number | null;
  caps: {
    global_daily_request_cap: number;
    global_daily_token_cap: number;
    daily_cost_cap_micro_usd: number;
  };
  slots_by_status: Record<string, number>;
  providers: AiProviderSummary[];
}

export interface AiSlotSecret {
  ref: string;
  env_name: string;
  present: boolean;
  fingerprint: string;
}

export interface AiSlotUsage {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  errors: number;
  rate_limited: number;
  cost_micro_usd: number;
}

export interface AiSlotHealth {
  status: AiSlotHealthStatus;
  cooldown_s: number;
  consecutive_failures: number;
  recent_429: number;
  secret: AiSlotSecret;
  usage_today: AiSlotUsage;
  last_success_at: string | null;
  /** Lỗi provider gần nhất — mã đã làm sạch (`provider_http_404`…), không bao giờ là thông điệp của nhà cung cấp. */
  last_error_code?: string | null;
  /** Enum lỗi của nhà cung cấp (`NOT_FOUND`, `PERMISSION_DENIED:SERVICE_DISABLED`, `model_not_found`). */
  last_error_category?: string | null;
  last_error_at?: string | null;
}

export interface AiSlot {
  slot_id: string;
  provider_type: AiProviderType;
  label: string;
  secret_ref: string;
  model: string;
  enabled: boolean;
  endpoint: string;
  api_version: string;
  priority: number;
  weight: number;
  daily_request_cap: number;
  daily_token_cap: number;
  rpm_soft_cap: number;
  tpm_soft_cap: number;
  workloads: string[];
  price_in_micro_per_mtok: number;
  price_out_micro_per_mtok: number;
  effective_endpoint: string;
  health: AiSlotHealth;
}

export type AiMode = "general" | "story" | "support" | "writer";

export interface AiControls {
  ai_enabled: boolean;
  provider_types: Record<AiProviderType, boolean>;
  global_daily_request_cap: number;
  global_daily_token_cap: number;
  per_user_daily_request_cap: number;
  per_user_daily_token_cap: number;
  daily_cost_cap_micro_usd: number;
  max_output_tokens: number;
  max_context_tokens: number;
  mode_profiles: Record<AiMode, string>;
  web_search_profile: string;
  web_search_tool: string;
  version: number;
  updated_by: string;
  updated_at: string;
}

export interface AiProviderTypeInfo {
  type: AiProviderType;
  label: string;
  enabled: boolean;
  slot_count: number;
}

export interface AiRoutingProfile {
  name: string;
  steps: string[];
  enabled: boolean;
}

export interface AiConfigMeta {
  provider_types: AiProviderType[];
  workloads: string[];
  profiles: string[];
  modes: AiMode[];
  default_endpoints: Record<string, string>;
  /** Máy chủ được phép theo loại (".openai.azure.com" = mọi tên miền con). */
  endpoint_hosts: Record<string, string[]>;
  /** Loại BẮT BUỘC nhập endpoint (không có endpoint mặc định). */
  requires_endpoint: string[];
  /** Loại dùng `api_version`. */
  uses_api_version: string[];
  /** Mẫu endpoint hợp lệ theo loại — hiện dưới ô nhập. */
  endpoint_hints: Record<string, string>;
  secret_env_prefix: string;
}

export interface AiConfig {
  state: AiConfigState;
  controls: AiControls;
  provider_types: AiProviderTypeInfo[];
  slots: AiSlot[];
  profiles: AiRoutingProfile[];
  meta: AiConfigMeta;
}

export interface AiAuditItem {
  admin_id: string;
  at: string;
  entity: string;
  field: string;
  old_value: string;
  new_value: string;
}

export interface AiAuditResponse {
  items: AiAuditItem[];
}

/** Payload gửi lên khi tạo/sửa slot — KHÔNG có trường nào chứa key thật,
 *  chỉ `secret_ref` (tên tham chiếu, backend tự tra `FAS_AI_SECRET_<ref>`). */
export interface AiSlotInput {
  slot_id?: string;
  provider_type?: AiProviderType;
  label?: string;
  secret_ref?: string;
  model?: string;
  enabled?: boolean;
  endpoint?: string;
  api_version?: string;
  priority?: number;
  weight?: number;
  daily_request_cap?: number;
  daily_token_cap?: number;
  rpm_soft_cap?: number;
  tpm_soft_cap?: number;
  workloads?: string[];
  price_in_micro_per_mtok?: number;
  price_out_micro_per_mtok?: number;
}

export interface AiGlobalPatch {
  ai_enabled?: boolean;
  global_daily_request_cap?: number;
  global_daily_token_cap?: number;
  per_user_daily_request_cap?: number;
  per_user_daily_token_cap?: number;
  daily_cost_cap_micro_usd?: number;
  max_output_tokens?: number;
  max_context_tokens?: number;
  mode_profiles?: Partial<Record<AiMode, string>>;
  web_search_profile?: string;
  web_search_tool?: string;
  expected_version?: number;
}

/** Lỗi 422 riêng của bảng điều khiển AI: `{code, message, errors:[{field,message}]}`.
 *  `ApiError` (lib/api.ts) đọc được `code`/`message` nhưng bỏ mất `errors` —
 *  lớp con này giữ lại để form hiển thị lỗi CẠNH đúng trường. */
export class AiAdminApiError extends ApiError {
  fieldErrors: { field: string; message: string }[];
  constructor(
    message: string,
    status: number,
    code?: string,
    fieldErrors: { field: string; message: string }[] = [],
  ) {
    super(message, status, code);
    this.name = "AiAdminApiError";
    this.fieldErrors = fieldErrors;
  }
}

async function requestAi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      "Không kết nối được máy chủ. Kiểm tra kết nối mạng rồi thử lại.",
      0,
    );
  }

  if (!response.ok) {
    let message = `Máy chủ trả về lỗi ${response.status}.`;
    let code: string | undefined;
    let fieldErrors: { field: string; message: string }[] = [];
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (body?.detail && typeof body.detail === "object") {
        if (typeof body.detail.message === "string") message = body.detail.message;
        if (typeof body.detail.code === "string") code = body.detail.code;
        if (Array.isArray(body.detail.errors)) {
          fieldErrors = body.detail.errors
            .filter(
              (e: unknown): e is { field: string; message: string } =>
                typeof e === "object" && e !== null &&
                typeof (e as { field?: unknown }).field === "string" &&
                typeof (e as { message?: unknown }).message === "string",
            )
            .map((e: { field: string; message: string }) => ({ field: e.field, message: e.message }));
        }
      }
    } catch {
      /* giữ thông báo mặc định */
    }
    throw new AiAdminApiError(message, response.status, code, fieldErrors);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const aiControl = {
  getOverview: () => requestAi<AiOverview>("/api/admin/ai/overview"),

  getConfig: () => requestAi<AiConfig>("/api/admin/ai/config"),

  getAudit: (limit = 50) =>
    requestAi<AiAuditResponse>(`/api/admin/ai/audit?limit=${limit}`),

  updateGlobal: (patch: AiGlobalPatch) =>
    requestAi<{ controls: AiControls }>("/api/admin/ai/global", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  /** `expectedVersion`: bật một loại cần bản cấu hình hiện tại (409 nếu cũ);
   *  TẮT thì server luôn cho qua. */
  setProviderType: (type: AiProviderType, enabled: boolean, expectedVersion?: number) =>
    requestAi<{ ok: boolean }>(`/api/admin/ai/provider-types/${type}`, {
      method: "PUT",
      body: JSON.stringify({ enabled, expected_version: expectedVersion }),
    }),

  createSlot: (payload: AiSlotInput) =>
    requestAi<{ slot: AiSlot }>("/api/admin/ai/slots", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateSlot: (slotId: string, payload: AiSlotInput) =>
    requestAi<{ slot: AiSlot }>(`/api/admin/ai/slots/${encodeURIComponent(slotId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteSlot: (slotId: string) =>
    requestAi<{ deleted: boolean }>(`/api/admin/ai/slots/${encodeURIComponent(slotId)}`, {
      method: "DELETE",
    }),

  updateProfile: (name: string, payload: { steps: string[]; enabled: boolean }) =>
    requestAi<{ profile: AiRoutingProfile }>(`/api/admin/ai/profiles/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  resetCooldown: (slotId: string) =>
    requestAi<{ ok: boolean }>(`/api/admin/ai/slots/${encodeURIComponent(slotId)}/reset-cooldown`, {
      method: "POST",
    }),
};

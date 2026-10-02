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
  | "openrouter"
  | "alibaba";

export type AiSlotHealthStatus =
  | "HEALTHY"
  | "COOLDOWN"
  | "DISABLED"
  | "MISSING_SECRET"
  | "OVER_CAP"
  | "DEGRADED"
  /** Loại có cổng cấp máy chủ (biến môi trường) mà cổng đang ĐÓNG: không request nào tới nhà cung cấp. */
  | "GATE_CLOSED"
  /** Nhà cung cấp báo hết hạn mức: slot nghỉ tới 00:00 UTC (hoặc tới khi Owner reset). */
  | "QUOTA_EXHAUSTED"
  /** Siêu dữ liệu của slot trong kho bị hỏng — chỉ slot này bị bỏ qua. */
  | "META_CORRUPT";

/** Tầng năng lực của một model — KHÔNG phải tên model hay gói đăng ký; gói/tính năng sau này ánh xạ tới tầng. */
export type AiCapabilityTier = "FAST" | "SMART" | "ADVANCED" | "TRANSLATION" | "VISION" | "EMBEDDING";

/** Cổng cấp máy chủ của một loại provider: `env` là TÊN biến môi trường (đổi cần deploy), `open` = đang mở. */
export interface AiGateInfo {
  env: string;
  open: boolean;
}

export interface AiLatencyStat {
  p50: number | null;
  p95: number | null;
  last: number | null;
}

/** Độ trễ MỘT slot: cửa sổ trượt các lời gọi gần nhất, TRONG TIẾN TRÌNH (mất khi deploy). `ttft_ms` = tới token chữ đầu tiên. */
export interface AiSlotLatency {
  window: number;
  samples: number;
  ok: number;
  probe_samples: number;
  ttft_ms: AiLatencyStat;
  total_ms: AiLatencyStat;
  note: string;
}

export type AiFreeQuotaState = "none" | "active" | "expiring" | "expired" | "exhausted";

/** Hạn mức MIỄN PHÍ do Owner nhập (ẢNH CHỤP, không tự cập nhật — `updated_at` cho biết cũ bao lâu). */
export interface AiSlotQuota {
  state: AiFreeQuotaState;
  remaining: number | null;
  expires_at: string | null;
  days_left: number | null;
  only: boolean;
  updated_at: string | null;
  /** Tuổi của ảnh chụp (ngày); `null` = chưa có dấu thời gian của máy chủ. */
  snapshot_age_days: number | null;
  /** Token slot đã phục vụ từ ngày nhập ảnh chụp (đọc từ sổ sử dụng); `null` = không xác định được. */
  consumed_since_snapshot: number | null;
  /** Ảnh chụp trừ lượng đã dùng — ƯỚC TÍNH, không phải số liệu của nhà cung cấp. */
  estimated_remaining: number | null;
  /** Với slot `only`: lý do khoá "chỉ dùng hạn mức miễn phí" đang CHẶN slot ngay lúc này, `null` = không chặn. */
  lock_block: "expired" | "stale" | "unverifiable" | "exhausted" | null;
  /** Nhà cung cấp đã báo hết hạn mức hôm nay (không phải số liệu Owner nhập). */
  provider_exhausted_today: boolean;
}

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
  /**
   * Lần QA của Owner hôm nay (`qa: true` trong thân lượt gửi) — tách khỏi hạn mức người dùng thường nhưng NẰM TRONG
   * `requests` ở trên và trong các trần toàn cục. `null` = không đo được.
   */
  qa?: { requests: number; tokens: number; owners: number; per_owner_daily_cap: number } | null;
  /**
   * Thông tin RUNTIME không nằm trong kho cấu hình: khán giả đang áp (`FAS_AI_AUDIENCE`), RPM/người và số luồng SSE đang
   * chạy trên instance (chạm `streams_max` thì người dùng nhận 503 "đang bận"). Không có ID/danh sách nào. `null` = runtime
   * AI chưa dựng (backend tắt) hoặc không đo được.
   */
  runtime?: { audience: string; rpm_per_user: number; streams_active: number; streams_max: number } | null;
  /** Cổng cấp máy chủ của các loại provider có cổng: đóng = KHÔNG request nào tới nhà cung cấp đó. */
  gates?: Record<string, AiGateInfo>;
  /** "Ưu tiên hạn mức miễn phí sắp hết hạn" có đang bật không (mặc định TẮT). */
  free_quota_preference?: boolean;
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
  /** Ngân sách KIỂM riêng — không bao giờ cộng vào `usage_today` / hạn mức người dùng. */
  probes_today?: { count: number; ok: number; tokens: number; cap: number };
  /** Các lần kiểm gần nhất, mới nhất trước. */
  probe_history?: { at: string; ok: boolean; latency_ms: number | null; code: string | null }[];
  /** `true` khi các lần kiểm gần nhất đều đạt và đủ nhanh — gợi ý có thể bật (không tự bật). */
  probe_stable?: boolean;
  quota?: AiSlotQuota;
  latency?: AiSlotLatency;
  /** `null` = loại này không có cổng máy chủ. */
  gate?: AiGateInfo | null;
  meta_corrupt?: boolean;
}

export type AiPresetName = "canary" | "beta";

export interface AiRollout {
  active_preset: AiPresetName | "custom";
  presets: Record<AiPresetName, Record<string, number>>;
  probe_daily_cap_per_slot: number;
  probe_stable_rule: { run: number; max_latency_ms: number };
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
  /** Tầng năng lực slot phục vụ; rỗng = chưa phân loại. */
  tiers?: AiCapabilityTier[];
  /** Số dư hạn mức miễn phí (token) Owner nhập; `null` = không biết. */
  free_quota_remaining?: number | null;
  free_quota_expires_at?: string;
  /** `true` = slot KHÔNG BAO GIỜ được dùng khi hạn mức miễn phí hết/quá hạn (không để phát sinh phí). */
  free_quota_only?: boolean;
  free_quota_updated_at?: string;
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
  /** Cổng cấp máy chủ của loại này, hoặc `null`/vắng nếu loại không có cổng. */
  gate?: AiGateInfo | null;
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
  /** Các tầng năng lực chọn được cho một slot, và phần chat phục vụ được (EMBEDDING dùng API khác). */
  capability_tiers?: AiCapabilityTier[];
  chat_tiers?: AiCapabilityTier[];
  /** Loại có cổng cấp máy chủ → tên biến môi trường + đang mở hay không. */
  gated_types?: Record<string, AiGateInfo>;
  /** Loại mà slot LUÔN được tạo ở trạng thái tắt (bật bằng thao tác riêng sau khi Kiểm tra). */
  created_disabled_types?: string[];
  free_quota?: { expiring_soon_days: number; prefer_expiring_active: boolean };
}

export interface AiConfig {
  state: AiConfigState;
  controls: AiControls;
  rollout?: AiRollout;
  /** Tầng năng lực → id các slot khai báo phục vụ tầng đó. */
  capability_map?: Record<string, string[]>;
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
  tiers?: AiCapabilityTier[];
  /** `null` = xoá số liệu. Máy chủ tự đóng dấu thời điểm ảnh chụp (client không gửi được). */
  free_quota_remaining?: number | null;
  free_quota_expires_at?: string;
  free_quota_only?: boolean;
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

  /** OWNER: áp preset rollout (chỉ hạn mức — KHÔNG đụng công tắc khẩn cấp). */
  applyPreset: (name: AiPresetName, expectedVersion: number) =>
    requestAi<{ controls: AiControls }>(`/api/admin/ai/presets/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify({ expected_version: expectedVersion }),
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

  /** OWNER: MỘT request tối thiểu thật qua slot (chạy được khi slot tắt / công tắc tổng tắt). */
  probeSlot: (slotId: string) =>
    requestAi<{ probe: AiProbeResult }>(`/api/admin/ai/slots/${encodeURIComponent(slotId)}/probe`, {
      method: "POST",
    }),
};

/** Kết quả kiểm slot — chỉ ok, độ trễ và mã lỗi ĐÃ LÀM SẠCH; không bao giờ có văn bản của nhà cung cấp. */
export interface AiProbeResult {
  slot_id: string;
  model: string;
  ok: boolean;
  latency_ms: number | null;
  /** Thời gian tới token chữ đầu tiên — chỉ có khi kiểm qua luồng (stream). */
  ttft_ms?: number | null;
  code: string | null;
  category: string | null;
}

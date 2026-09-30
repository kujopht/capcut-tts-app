/**
 * Lớp gọi backend Fanfic AI Assistant V1 (`/api/ai/*`) — TỆP DUY NHẤT giao
 * diện dùng để nói chuyện với `server/ai_assistant/routes.py`. Cùng khuôn
 * với `lib/api.ts`: chỉ biết `API_BASE`, token qua `Authorization: Bearer`
 * (không bao giờ lên URL), không SDK/WebSocket nào khác.
 *
 * Luồng tin nhắn dùng `fetch` (không `EventSource`, vì `EventSource` không
 * gửi được header `Authorization`) — cùng lý do với
 * `lib/chat/fanficTransport.ts` — và trả về một `AbortController` để nơi gọi
 * huỷ (nút Dừng).
 */
import { API_BASE, ApiError, getToken } from "@/lib/api";
import { docLoiApi } from "./loiApi";
import { tachKhungSse, dienDichKhungAi } from "./sse";
import type {
  AiAvailability,
  AiConversationContext,
  AiConversationDetail,
  AiConversationSummary,
  AiMode,
  AiPreferences,
  AiProjectDetail,
  AiProjectField,
  AiProjectJsonField,
  AiProjectSummary,
  AiStreamEvent,
} from "./types";

const CAC_TRUONG_JSON: readonly AiProjectJsonField[] = ["outline", "characters", "world"];

/** Đọc phần văn bản của một mục JSON tự do (§6) theo quy ước `{ text }` —
 *  hình dạng khác (bản ghi cũ/client khác) đọc như RỖNG, không ném lỗi. */
export function docVanBanTruongDuAn(field: AiProjectField, value: unknown): string {
  if (!CAC_TRUONG_JSON.includes(field as AiProjectJsonField)) {
    return typeof value === "string" ? value : "";
  }
  if (value && typeof value === "object" && typeof (value as Record<string, unknown>).text === "string") {
    return (value as Record<string, unknown>).text as string;
  }
  return "";
}

interface ProjectPayload {
  title: string;
  premise: string;
  outline: Record<string, unknown>;
  characters: Record<string, unknown>;
  world: Record<string, unknown>;
  notes: string;
}

/** Dựng lại body `ProjectIn` đầy đủ từ một bản chi tiết + MỘT trường vừa đổi (PUT ghi đè toàn bộ, không patch từng phần). */
export function ghepBodyDuAn(hienTai: AiProjectDetail | null, doi: Partial<Record<AiProjectField, string> & { title: string }>): ProjectPayload {
  const layVanBan = (field: AiProjectTextFieldNoiBo) =>
    doi[field] !== undefined ? (doi[field] as string) : hienTai ? (hienTai[field] as string) : "";
  const layJson = (field: AiProjectJsonField) =>
    doi[field] !== undefined ? { text: doi[field] as string } : (hienTai ? hienTai[field] : {}) ?? {};
  return {
    title: doi.title !== undefined ? doi.title : hienTai?.title ?? "",
    premise: layVanBan("premise"),
    notes: layVanBan("notes"),
    outline: layJson("outline"),
    characters: layJson("characters"),
    world: layJson("world"),
  };
}
type AiProjectTextFieldNoiBo = "premise" | "notes";

function headers(json: boolean): HeadersInit {
  const token = getToken();
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** `ApiError` + `reset_at` của lỗi hết ngân sách ngày (để hiện "Làm mới lúc …"). */
export class AiApiError extends ApiError {
  resetAt: string | null;
  constructor(message: string, status: number, code?: string, resetAt: string | null = null) {
    super(message, status, code);
    this.name = "AiApiError";
    this.resetAt = resetAt;
  }
}

async function loiTuPhanHoi(res: Response, macDinh: string): Promise<AiApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // không phải JSON — giữ body = null
  }
  const l = docLoiApi(body, res.status, macDinh);
  return new AiApiError(l.message, l.status, l.code, l.resetAt);
}

async function doc<T>(res: Response): Promise<T> {
  if (!res.ok) throw await loiTuPhanHoi(res, res.statusText || "Lỗi máy chủ");
  return (await res.json()) as T;
}

export const aiApi = {
  async availability(): Promise<AiAvailability> {
    const res = await fetch(`${API_BASE}/api/ai/availability`, { headers: headers(false), cache: "no-store" });
    return doc<AiAvailability>(res);
  },

  async listConversations(limit = 30, cursor?: string): Promise<{ items: AiConversationSummary[] }> {
    const qs = new URLSearchParams({ limit: String(limit), ...(cursor ? { cursor } : {}) });
    const res = await fetch(`${API_BASE}/api/ai/conversations?${qs}`, { headers: headers(false), cache: "no-store" });
    return doc(res);
  },

  async createConversation(mode: AiMode, opts?: { title?: string; context?: AiConversationContext }): Promise<{
    conversation_id: string;
    mode: AiMode;
    title: string;
    created_at: string;
  }> {
    const res = await fetch(`${API_BASE}/api/ai/conversations`, {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify({ mode, title: opts?.title, context: opts?.context }),
    });
    return doc(res);
  },

  async getConversation(conversationId: string, limit = 50): Promise<AiConversationDetail> {
    const res = await fetch(`${API_BASE}/api/ai/conversations/${encodeURIComponent(conversationId)}?limit=${limit}`, {
      headers: headers(false),
      cache: "no-store",
    });
    return doc(res);
  },

  async deleteConversation(conversationId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/ai/conversations/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
      headers: headers(false),
    });
    await doc(res);
  },

  async getPreferences(): Promise<AiPreferences> {
    const res = await fetch(`${API_BASE}/api/ai/preferences`, { headers: headers(false), cache: "no-store" });
    return doc(res);
  },

  async putPreferences(prefs: AiPreferences): Promise<AiPreferences> {
    const res = await fetch(`${API_BASE}/api/ai/preferences`, {
      method: "PUT",
      headers: headers(true),
      body: JSON.stringify(prefs),
    });
    return doc(res);
  },

  async deleteMemory(includeProjects = false): Promise<void> {
    const res = await fetch(`${API_BASE}/api/ai/memory?include_projects=${includeProjects ? "true" : "false"}`, {
      method: "DELETE",
      headers: headers(false),
    });
    await doc(res);
  },

  async listProjects(): Promise<{ items: AiProjectSummary[] }> {
    const res = await fetch(`${API_BASE}/api/ai/projects`, { headers: headers(false), cache: "no-store" });
    return doc(res);
  },

  async createProject(payload: ProjectPayload): Promise<{ project_id: string }> {
    const res = await fetch(`${API_BASE}/api/ai/projects`, {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify(payload),
    });
    return doc(res);
  },

  async getProject(projectId: string): Promise<AiProjectDetail> {
    const res = await fetch(`${API_BASE}/api/ai/projects/${encodeURIComponent(projectId)}`, {
      headers: headers(false),
      cache: "no-store",
    });
    return doc(res);
  },

  async updateProject(projectId: string, payload: ProjectPayload): Promise<{ project_id: string; updated_at: string }> {
    const res = await fetch(`${API_BASE}/api/ai/projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      headers: headers(true),
      body: JSON.stringify(payload),
    });
    return doc(res);
  },

  async deleteProject(projectId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/ai/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
      headers: headers(false),
    });
    await doc(res);
  },

  /**
   * Gửi tin + đọc luồng SSE. Không ném lỗi cho sự kiện `error` của MÁY CHỦ —
   * sự kiện đó đi qua `onEvent` như mọi sự kiện khác, để nơi gọi tự quyết
   * định hiển thị (§10: `error` là một khung SSE hợp lệ, không phải throw).
   * Chỉ ném khi bản thân request thất bại (mạng hỏng / HTTP lỗi trước khi
   * luồng bắt đầu).
   */
  async streamMessage(
    conversationId: string,
    body: { content: string; client_id: string; regenerate_of?: string; use_web_search?: boolean; use_library?: boolean },
    onEvent: (ev: AiStreamEvent) => void,
    signal: AbortSignal,
  ): Promise<void> {
    const res = await fetch(`${API_BASE}/api/ai/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: { ...headers(true), Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
      cache: "no-store",
    });
    if (!res.ok || !res.body) throw await loiTuPhanHoi(res, "Không thể kết nối trợ lý AI.");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const { khung, conLai } = tachKhungSse(buffer);
      buffer = conLai;
      for (const k of khung) {
        const ev = dienDichKhungAi(k);
        if (ev) onEvent(ev);
      }
    }
  },
};

export function taoClientId(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

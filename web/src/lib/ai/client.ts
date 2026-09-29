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
import { tachKhungSse, dienDichKhungAi } from "./sse";
import type {
  AiAvailability,
  AiConversationContext,
  AiConversationDetail,
  AiConversationSummary,
  AiMode,
  AiPreferences,
  AiProjectSummary,
  AiStreamEvent,
} from "./types";

function headers(json: boolean): HeadersInit {
  const token = getToken();
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function doc<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      // không phải JSON — giữ detail = null
    }
    const obj = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
    const message = (obj && typeof obj.message === "string" && obj.message) || res.statusText || "Lỗi máy chủ";
    const code = obj && typeof obj.code === "string" ? obj.code : undefined;
    throw new ApiError(message, res.status, code);
  }
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
    if (!res.ok || !res.body) {
      let detail: unknown = null;
      try {
        detail = await res.json();
      } catch {
        // không phải JSON
      }
      const obj = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
      const message = (obj && typeof obj.message === "string" && obj.message) || "Không thể kết nối trợ lý AI.";
      const code = obj && typeof obj.code === "string" ? obj.code : undefined;
      throw new ApiError(message, res.status, code);
    }
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

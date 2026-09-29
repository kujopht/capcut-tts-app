"use client";

/**
 * AiProvider — nguồn trạng thái DUY NHẤT của Fanfic AI Assistant V1.
 *
 * Gắn ở `app/layout.tsx`, BÊN TRONG `SessionProvider`/`ChatProvider` (thứ tự
 * không quan trọng vì hai bên độc lập), NGANG HÀNG chứ không lồng vào Chat —
 * `components/chat/**` không bị chạm.
 *
 * LƯỜI (lazy): đăng nhập KHÔNG mở trợ lý, KHÔNG gọi `/api/ai/availability`
 * ngay lúc mount. Chỉ khi `openAssistant()` được gọi lần đầu (nút nổi, mục
 * menu, hoặc `/assistant`) mới xin `availability` — giữ đúng nguyên tắc
 * "idle gần như zero mạng". Đã mở một lần trong TAB này thì tải lại trang sẽ
 * tự mở lại (`sessionStorage`), giống hành vi Chat V1.
 *
 * Tên/model provider KHÔNG BAO GIỜ lộ ra ở tầng này — chỉ `availability.name`
 * (tên hiển thị) và `mode`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ApiError } from "@/lib/api";
import { aiApi, taoClientId } from "@/lib/ai/client";
import { AI_ASSISTANT_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import type {
  AiAvailability,
  AiConversationContext,
  AiConversationSummary,
  AiErrorInfo,
  AiMessage,
  AiMode,
} from "@/lib/ai/types";

const CO_MO = "fas.ai.open";
const CO_HOI_THOAI = "fas.ai.conv";

function docPhien(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function ghiPhien(key: string, value: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    // Chế độ riêng tư/hết hạn mức — bỏ qua, không phải lỗi nghiêm trọng.
  }
}

function loiTuApiError(e: unknown): AiErrorInfo {
  if (e instanceof ApiError) {
    const code = (e.code as AiErrorInfo["code"]) || "ai_provider_unavailable";
    return { code, message: e.message || "Có lỗi khi liên hệ trợ lý AI." };
  }
  return { code: "network_error", message: "Mất kết nối mạng." };
}

interface AiState {
  /** `null` = chưa xin (lười); `false`/object = đã xin. */
  availability: AiAvailability | null | false;
  loadingAvailability: boolean;
  open: boolean;
  conversationId: string | null;
  mode: AiMode;
  messages: AiMessage[];
  streaming: boolean;
  streamingText: string;
  conversations: AiConversationSummary[];
  historyOpen: boolean;
  error: AiErrorInfo | null;
  loadingConversation: boolean;
}

interface AiContextValue extends AiState {
  enabled: boolean;
  openAssistant: (opts?: { mode?: AiMode; context?: AiConversationContext }) => Promise<void>;
  closeAssistant: () => void;
  toggleHistory: () => void;
  selectConversation: (id: string) => Promise<void>;
  newConversation: (mode?: AiMode) => Promise<void>;
  deleteConversationById: (id: string) => Promise<void>;
  setMode: (mode: AiMode) => void;
  sendMessage: (text: string) => Promise<void>;
  stopStreaming: () => void;
  regenerate: () => Promise<void>;
}

const AiContext = createContext<AiContextValue | null>(null);

export function useAi(): AiContextValue {
  const ctx = useContext(AiContext);
  if (!ctx) throw new Error("useAi() phải nằm trong <AiProvider>");
  return ctx;
}

/** Bản chỉ-đọc, KHÔNG ném lỗi khi thiếu Provider — dùng cho nơi có thể mount ngoài layout (test/Storybook). */
export function useAiSafe(): AiContextValue | null {
  return useContext(AiContext);
}

export function AiProvider({ children }: { children: React.ReactNode }) {
  const { profile } = useSession();
  const [state, setState] = useState<AiState>({
    availability: null,
    loadingAvailability: false,
    open: false,
    conversationId: null,
    mode: "general",
    messages: [],
    streaming: false,
    streamingText: "",
    conversations: [],
    historyOpen: false,
    error: null,
    loadingConversation: false,
  });
  const ctrlRef = useRef<AbortController | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  const lastUserTextRef = useRef<string>("");

  // Khôi phục trạng thái mở/hội thoại của tab (chỉ khi đã đăng nhập).
  useEffect(() => {
    if (!AI_ASSISTANT_ENABLED || !profile) return;
    const daMo = docPhien(CO_MO) === "1";
    const hoiThoai = docPhien(CO_HOI_THOAI);
    if (daMo) {
      setState((s) => ({ ...s, open: true, conversationId: hoiThoai }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id]);

  const xinAvailability = useCallback(async (): Promise<AiAvailability | false> => {
    if (state.availability) return state.availability;
    setState((s) => ({ ...s, loadingAvailability: true }));
    try {
      const av = await aiApi.availability();
      setState((s) => ({ ...s, availability: av, loadingAvailability: false }));
      return av;
    } catch {
      setState((s) => ({ ...s, availability: false, loadingAvailability: false }));
      return false;
    }
  }, [state.availability]);

  const taiHoiThoai = useCallback(async (id: string) => {
    setState((s) => ({ ...s, loadingConversation: true, error: null }));
    try {
      const detail = await aiApi.getConversation(id);
      setState((s) => ({ ...s, conversationId: id, messages: detail.messages, mode: detail.mode, loadingConversation: false }));
      ghiPhien(CO_HOI_THOAI, id);
    } catch (e) {
      setState((s) => ({ ...s, loadingConversation: false, error: loiTuApiError(e) }));
    }
  }, []);

  const taiLichSu = useCallback(async () => {
    try {
      const r = await aiApi.listConversations();
      setState((s) => ({ ...s, conversations: r.items }));
    } catch {
      // Lịch sử là phụ — lỗi ở đây không chặn cuộc hội thoại hiện tại.
    }
  }, []);

  const openAssistant = useCallback(
    async (opts?: { mode?: AiMode; context?: AiConversationContext }) => {
      if (!AI_ASSISTANT_ENABLED || !profile) return;
      setState((s) => ({ ...s, open: true }));
      ghiPhien(CO_MO, "1");
      const av = await xinAvailability();
      if (!av) return;
      void taiLichSu();
      if (opts?.mode || opts?.context) {
        try {
          const conv = await aiApi.createConversation(opts.mode ?? "general", { context: opts.context });
          await taiHoiThoai(conv.conversation_id);
        } catch (e) {
          setState((s) => ({ ...s, error: loiTuApiError(e) }));
        }
        return;
      }
      const hoiThoaiLuu = docPhien(CO_HOI_THOAI);
      if (hoiThoaiLuu && !state.conversationId) {
        await taiHoiThoai(hoiThoaiLuu);
      }
    },
    [profile, xinAvailability, taiLichSu, taiHoiThoai, state.conversationId],
  );

  const closeAssistant = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    ghiPhien(CO_MO, null);
  }, []);

  const toggleHistory = useCallback(() => {
    setState((s) => ({ ...s, historyOpen: !s.historyOpen }));
  }, []);

  const selectConversation = useCallback(
    async (id: string) => {
      ctrlRef.current?.abort();
      await taiHoiThoai(id);
      setState((s) => ({ ...s, historyOpen: false }));
    },
    [taiHoiThoai],
  );

  const newConversation = useCallback(
    async (mode?: AiMode) => {
      ctrlRef.current?.abort();
      setState((s) => ({ ...s, error: null }));
      try {
        const conv = await aiApi.createConversation(mode ?? state.mode);
        setState((s) => ({ ...s, conversationId: conv.conversation_id, messages: [], mode: conv.mode, historyOpen: false }));
        ghiPhien(CO_HOI_THOAI, conv.conversation_id);
        void taiLichSu();
      } catch (e) {
        setState((s) => ({ ...s, error: loiTuApiError(e) }));
      }
    },
    [state.mode, taiLichSu],
  );

  const deleteConversationById = useCallback(
    async (id: string) => {
      try {
        await aiApi.deleteConversation(id);
        setState((s) => ({
          ...s,
          conversations: s.conversations.filter((c) => c.conversation_id !== id),
          ...(s.conversationId === id ? { conversationId: null, messages: [] } : {}),
        }));
        if (state.conversationId === id) ghiPhien(CO_HOI_THOAI, null);
      } catch (e) {
        setState((s) => ({ ...s, error: loiTuApiError(e) }));
      }
    },
    [state.conversationId],
  );

  const setMode = useCallback((mode: AiMode) => {
    setState((s) => ({ ...s, mode }));
  }, []);

  const guiVanBan = useCallback(
    async (text: string, regenerateOf?: string) => {
      const trimmed = text.trim();
      if (!trimmed || state.streaming) return;
      let convId = state.conversationId;
      if (!convId) {
        try {
          const conv = await aiApi.createConversation(state.mode);
          convId = conv.conversation_id;
          setState((s) => ({ ...s, conversationId: convId }));
          ghiPhien(CO_HOI_THOAI, convId);
        } catch (e) {
          setState((s) => ({ ...s, error: loiTuApiError(e) }));
          return;
        }
      }
      lastUserTextRef.current = trimmed;
      const clientId = taoClientId();
      if (!regenerateOf) {
        const userMsg: AiMessage = {
          message_id: `local_${clientId}`,
          role: "user",
          content: trimmed,
          status: "complete",
          citations: [],
          created_at: new Date().toISOString(),
        };
        setState((s) => ({ ...s, messages: [...s.messages, userMsg], streaming: true, streamingText: "", error: null }));
      } else {
        setState((s) => ({ ...s, streaming: true, streamingText: "", error: null }));
      }
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;
      assistantIdRef.current = null;
      try {
        await aiApi.streamMessage(
          convId,
          { content: trimmed, client_id: clientId, regenerate_of: regenerateOf },
          (ev) => {
            if (ev.type === "meta") {
              assistantIdRef.current = ev.message_id;
            } else if (ev.type === "delta") {
              setState((s) => ({ ...s, streamingText: s.streamingText + ev.text }));
            } else if (ev.type === "citations") {
              setState((s) => ({
                ...s,
                messages: s.messages.map((m) =>
                  m.message_id === assistantIdRef.current ? { ...m, citations: ev.items } : m,
                ),
              }));
            } else if (ev.type === "done") {
              setState((s) => {
                const assistantMsg: AiMessage = {
                  message_id: assistantIdRef.current ?? `local_asst_${clientId}`,
                  role: "assistant",
                  content: s.streamingText,
                  status: ev.status,
                  citations: [],
                  created_at: new Date().toISOString(),
                };
                return { ...s, messages: [...s.messages, assistantMsg], streaming: false, streamingText: "" };
              });
            } else if (ev.type === "error") {
              setState((s) => ({
                ...s,
                streaming: false,
                error: { code: ev.code, message: ev.message, reset_at: ev.reset_at },
                ...(s.streamingText
                  ? {
                      messages: [
                        ...s.messages,
                        {
                          message_id: assistantIdRef.current ?? `local_asst_${clientId}`,
                          role: "assistant" as const,
                          content: s.streamingText,
                          status: "error" as const,
                          citations: [],
                          created_at: new Date().toISOString(),
                        },
                      ],
                      streamingText: "",
                    }
                  : {}),
              }));
            }
          },
          ctrl.signal,
        );
      } catch (e) {
        if (ctrl.signal.aborted) {
          setState((s) => ({ ...s, streaming: false }));
        } else {
          setState((s) => ({ ...s, streaming: false, streamingText: "", error: loiTuApiError(e) }));
        }
      }
    },
    [state.streaming, state.conversationId, state.mode],
  );

  const sendMessage = useCallback((text: string) => guiVanBan(text), [guiVanBan]);

  const stopStreaming = useCallback(() => {
    ctrlRef.current?.abort();
  }, []);

  const regenerate = useCallback(async () => {
    const lastAssistant = [...state.messages].reverse().find((m) => m.role === "assistant");
    if (!lastAssistant || !lastUserTextRef.current) return;
    setState((s) => ({ ...s, messages: s.messages.filter((m) => m.message_id !== lastAssistant.message_id) }));
    await guiVanBan(lastUserTextRef.current, lastAssistant.message_id);
  }, [state.messages, guiVanBan]);

  const value = useMemo<AiContextValue>(
    () => ({
      ...state,
      enabled: AI_ASSISTANT_ENABLED,
      openAssistant,
      closeAssistant,
      toggleHistory,
      selectConversation,
      newConversation,
      deleteConversationById,
      setMode,
      sendMessage,
      stopStreaming,
      regenerate,
    }),
    [
      state,
      openAssistant,
      closeAssistant,
      toggleHistory,
      selectConversation,
      newConversation,
      deleteConversationById,
      setMode,
      sendMessage,
      stopStreaming,
      regenerate,
    ],
  );

  return <AiContext.Provider value={value}>{children}</AiContext.Provider>;
}

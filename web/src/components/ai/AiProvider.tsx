"use client";

/**
 * AiProvider — nguồn trạng thái DUY NHẤT của Fanfic AI Assistant V1.
 *
 * Gắn ở `app/layout.tsx`, BÊN TRONG `SessionProvider`/`ChatProvider` (thứ tự
 * không quan trọng vì hai bên độc lập), NGANG HÀNG chứ không lồng vào Chat —
 * `components/chat/**` không bị chạm.
 *
 * LƯỜI (lazy): đăng nhập KHÔNG mở trợ lý, KHÔNG gọi `/api/ai/availability`
 * ngay lúc mount. Chỉ khi `openAssistant()` (nút nổi) hoặc `ensureReady()`
 * (`/assistant`, lối vào Story trên di động) được gọi lần đầu mới xin
 * `availability` — giữ đúng nguyên tắc "idle gần như zero mạng". NGOẠI LỆ DUY
 * NHẤT: cổng hiển thị `/api/ai/access` (một bit, xem `lib/ai/quyenTruyCap.ts`)
 * — MỘT request mỗi người đăng nhập mỗi lần tải trang, CHỈ khi bản build bật cờ.
 * Không có nó thì nút nổi/menu/lối vào trang truyện hiện cho MỌI người đăng
 * nhập, kể cả người ngoài nhóm beta. Panel nổi đã
 * được NGƯỜI DÙNG mở trong TAB này thì tải lại trang sẽ tự mở lại
 * (`sessionStorage`), giống hành vi Chat V1 — còn `/assistant` thì KHÔNG bao
 * giờ bật panel nổi (xem `lib/ai/phienMo.ts`).
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
import { AiApiError, aiApi, docVanBanTruongDuAn, ghepBodyDuAn, taoClientId } from "@/lib/ai/client";
import { apDungHetLuot, boTinTraLoiCu, danhDauChuaGui, docHanMuc } from "@/lib/ai/hanMuc";
import {
  CO_HOI_THOAI, apDungHanhDongMo, docNhap, docPhien, ghiNhap, ghiPhien, khoiPhucMo, openSauKhiPhucHoi,
} from "@/lib/ai/phienMo";
import { type AiAccess, type AiAccessKetQua, hienLoiVao, nenHoiQuyen, quyenHienTai } from "@/lib/ai/quyenTruyCap";
import { AI_ASSISTANT_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import type {
  AiAvailability,
  AiConversationContext,
  AiConversationSummary,
  AiErrorInfo,
  AiMessage,
  AiMode,
  AiPreferences,
  AiProjectDetail,
  AiProjectField,
  AiProjectSummary,
} from "@/lib/ai/types";

function loiTuApiError(e: unknown): AiErrorInfo {
  if (e instanceof ApiError) {
    const code = (e.code as AiErrorInfo["code"]) || "ai_provider_unavailable";
    const reset_at = e instanceof AiApiError ? e.resetAt : null;
    const scope = e instanceof AiApiError ? e.scope : undefined;
    return { code, message: e.message || "Có lỗi khi liên hệ trợ lý AI.", reset_at, scope };
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
  /** Máy chủ ĐÃ bắt đầu trả lời lượt này (nhận `meta`). Trước đó: máy chủ còn dựng ngữ cảnh
   *  (truy chương, thư viện); sau đó và trước token đầu: chờ nhà cung cấp (kể cả failover). */
  responseStarted: boolean;
  conversations: AiConversationSummary[];
  historyOpen: boolean;
  error: AiErrorInfo | null;
  loadingConversation: boolean;
  /** `true` khi hội thoại ĐANG MỞ không được lưu quá phiên (`memory_enabled=false` lúc tạo, §5). */
  ephemeral: boolean;
  preferences: AiPreferences | null;
  /** Dự án viết đang chọn (mode `writer`, §6) — độc lập với hội thoại: chọn dự án KHÔNG tự tạo/đổi hội thoại. */
  projects: AiProjectSummary[];
  activeProjectId: string | null;
  activeProject: AiProjectDetail | null;
  loadingProject: boolean;
  /** Nội dung ô soạn — nâng lên Provider để chip gợi ý (Brainstorm/Dàn ý/...) chèn được vào composer. */
  draft: string;
}

interface AiContextValue extends AiState {
  enabled: boolean;
  /** Máy chủ đã xác nhận người ĐANG đăng nhập dùng được AI chưa (`null` = chưa biết). */
  access: AiAccess;
  /** Được VẼ lối vào (nút nổi, menu, trang truyện): cờ bật + đăng nhập + máy chủ xác nhận. */
  eligible: boolean;
  /** Người dùng MỞ panel nổi (tường minh) — ghi cờ phiên, rồi `ensureReady`. */
  openAssistant: (opts?: { mode?: AiMode; context?: AiConversationContext }) => Promise<void>;
  /** Nạp availability + lịch sử + hội thoại (tạo mới nếu có `mode`/`context`) — KHÔNG đổi `open`. */
  ensureReady: (opts?: { mode?: AiMode; context?: AiConversationContext }) => Promise<void>;
  /** Trang `/assistant` mount: đóng panel nổi + xoá cờ mở (không tự bật lại khi quay về), rồi `ensureReady`. */
  enterFullscreen: () => Promise<void>;
  closeAssistant: () => void;
  toggleHistory: () => void;
  selectConversation: (id: string) => Promise<void>;
  newConversation: (mode?: AiMode) => Promise<void>;
  deleteConversationById: (id: string) => Promise<void>;
  setMode: (mode: AiMode) => void;
  sendMessage: (text: string) => Promise<void>;
  loadPreferences: () => Promise<void>;
  setMemoryEnabled: (value: boolean) => Promise<void>;
  deleteAllMemory: (includeProjects?: boolean) => Promise<void>;
  stopStreaming: () => void;
  regenerate: () => Promise<void>;
  setDraft: (text: string) => void;
  loadProjects: () => Promise<void>;
  createProject: (title: string) => Promise<void>;
  selectProject: (id: string | null) => Promise<void>;
  renameProject: (id: string, title: string) => Promise<void>;
  deleteProjectById: (id: string) => Promise<void>;
  /** "Lưu vào dự án" từ một tin nhắn trợ lý — LUÔN do người dùng bấm, không bao giờ tự động. */
  saveToProjectField: (field: AiProjectField, text: string, appendMode?: "replace" | "append") => Promise<void>;
  /** Lưu (GHI ĐÈ) nhiều trường cùng lúc từ trình soạn dự án — MỘT lượt PUT, khác `saveToProjectField` (nối thêm, từng trường). */
  saveProjectFields: (patch: Partial<Record<AiProjectField, string>>) => Promise<void>;
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
    responseStarted: false,
    conversations: [],
    historyOpen: false,
    error: null,
    loadingConversation: false,
    ephemeral: false,
    preferences: null,
    projects: [],
    activeProjectId: null,
    activeProject: null,
    loadingProject: false,
    draft: "",
  });
  const ctrlRef = useRef<AbortController | null>(null);
  /** user_id hiện tại cho các trình xử lý không phụ thuộc render (bản nháp theo người dùng). */
  const uidRef = useRef<string | null>(null);
  uidRef.current = profile?.user_id ?? null;
  const assistantIdRef = useRef<string | null>(null);
  const lastUserTextRef = useRef<string>("");
  /** Kết quả `/api/ai/access` GẮN với user_id đã hỏi — đổi tài khoản thì `quyenHienTai` trả `null`. */
  const [quyen, setQuyen] = useState<AiAccessKetQua | null>(null);
  const access = quyenHienTai(quyen, profile?.user_id);
  const eligible = hienLoiVao(AI_ASSISTANT_ENABLED, profile?.user_id, access);

  // Cổng hiển thị: hỏi máy chủ MỘT lần cho mỗi người đăng nhập (xem docstring đầu tệp).
  // Cờ tắt hoặc khách: không request. setState chỉ trong callback của promise.
  useEffect(() => {
    const uid = profile?.user_id ?? null;
    if (!nenHoiQuyen(AI_ASSISTANT_ENABLED, uid) || !uid) return;
    let alive = true;
    void aiApi.access().then((ok) => {
      if (alive) setQuyen({ userId: uid, eligible: ok });
    });
    return () => {
      alive = false;
    };
  }, [profile?.user_id]);

  // Khôi phục trạng thái mở/hội thoại của tab (chỉ khi đã đăng nhập).
  useEffect(() => {
    if (!AI_ASSISTANT_ENABLED || !profile) return;
    const { open, conversationId } = khoiPhucMo();
    const draft = docNhap(profile.user_id);
    if (open) {
      setState((s) => ({ ...s, open: true, conversationId, draft: s.draft || draft }));
    } else if (draft) {
      setState((s) => ({ ...s, draft: s.draft || draft }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id]);

  // Back sau một điều hướng CỨNG: trình duyệt phục hồi trang từ bfcache với
  // bộ nhớ JS cũ (có thể panel đang mở) — đồng bộ lại theo cờ phiên (mà
  // `/assistant` đã xoá) + bản nháp mới nhất. Đo được ở QA release gate.
  useEffect(() => {
    if (!AI_ASSISTANT_ENABLED) return;
    const khiHien = (e: PageTransitionEvent) => {
      if (!e.persisted) return;
      setState((s) => ({ ...s, open: openSauKhiPhucHoi(s.open), draft: docNhap(uidRef.current) }));
    };
    window.addEventListener("pageshow", khiHien);
    return () => window.removeEventListener("pageshow", khiHien);
  }, []);

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
      setState((s) => ({
        ...s,
        conversationId: id,
        messages: detail.messages,
        mode: detail.mode,
        ephemeral: Boolean(detail.ephemeral),
        loadingConversation: false,
      }));
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

  const ensureReady = useCallback(
    async (opts?: { mode?: AiMode; context?: AiConversationContext }) => {
      if (!AI_ASSISTANT_ENABLED || !profile) return;
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

  const openAssistant = useCallback(
    async (opts?: { mode?: AiMode; context?: AiConversationContext }) => {
      if (!AI_ASSISTANT_ENABLED || !profile) return;
      const open = apDungHanhDongMo("mo_noi");
      setState((s) => ({ ...s, open }));
      await ensureReady(opts);
    },
    [profile, ensureReady],
  );

  const enterFullscreen = useCallback(async () => {
    if (!AI_ASSISTANT_ENABLED || !profile) return;
    const open = apDungHanhDongMo("vao_toan_man");
    setState((s) => ({ ...s, open }));
    await ensureReady();
  }, [profile, ensureReady]);

  const closeAssistant = useCallback(() => {
    const open = apDungHanhDongMo("dong_noi");
    setState((s) => ({ ...s, open }));
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
      const modeThat = mode ?? state.mode;
      try {
        const conv = await aiApi.createConversation(
          modeThat,
          modeThat === "writer" && state.activeProjectId ? { context: { project_id: state.activeProjectId } } : undefined,
        );
        setState((s) => ({
          ...s,
          conversationId: conv.conversation_id,
          messages: [],
          mode: conv.mode,
          historyOpen: false,
          ephemeral: s.preferences ? !s.preferences.memory_enabled : false,
        }));
        ghiPhien(CO_HOI_THOAI, conv.conversation_id);
        void taiLichSu();
      } catch (e) {
        setState((s) => ({ ...s, error: loiTuApiError(e) }));
      }
    },
    [state.mode, state.activeProjectId, taiLichSu],
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
          const conv = await aiApi.createConversation(
            state.mode,
            state.mode === "writer" && state.activeProjectId ? { context: { project_id: state.activeProjectId } } : undefined,
          );
          convId = conv.conversation_id;
          setState((s) => ({ ...s, conversationId: convId }));
          ghiPhien(CO_HOI_THOAI, convId);
        } catch (e) {
          setState((s) => ({ ...s, error: loiTuApiError(e) }));
          return;
        }
      }
      // Khôi phục nếu lượt này bị từ chối trước khi máy chủ nhận: "Tạo lại" phải nhắm vào lượt đã GỬI được, không phải
      // vào tin chưa gửi.
      const vanBanTruoc = lastUserTextRef.current;
      lastUserTextRef.current = trimmed;
      const clientId = taoClientId();
      const userMsgId = `local_${clientId}`;
      if (!regenerateOf) {
        const userMsg: AiMessage = {
          message_id: userMsgId,
          role: "user",
          content: trimmed,
          status: "complete",
          citations: [],
          created_at: new Date().toISOString(),
        };
        setState((s) => ({ ...s, messages: [...s.messages, userMsg], streaming: true, streamingText: "", responseStarted: false, error: null }));
      } else {
        setState((s) => ({ ...s, streaming: true, streamingText: "", responseStarted: false, error: null }));
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
              setState((s) => ({ ...s, responseStarted: true, messages: boTinTraLoiCu(s.messages, regenerateOf) }));
            } else if (ev.type === "usage") {
              // Hạn mức RIÊNG sau lượt này (lượt QA của Owner báo hạn mức QA, không phải của người dùng).
              const hanMuc = ev.lane === "qa" ? null : docHanMuc(ev.allowance);
              if (hanMuc) setState((s) => (s.availability ? { ...s, availability: { ...s.availability, limits: hanMuc } } : s));
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
              // F2: LUÔN thêm một bong bóng trợ lý — kể cả khi CHƯA có token
              // nào (`streamingText` rỗng) — để không có lượt hỏi nào "biến
              // mất" (tin người dùng hiện ra mà không có gì nối theo, và
              // "Tạo lại" trước đây nhắm nhầm vào câu trả lời TRƯỚC ĐÓ vì
              // không tìm thấy bong bóng trợ lý nào của lượt này).
              setState((s) => ({
                ...s,
                streaming: false,
                streamingText: "",
                error: { code: ev.code, message: ev.message, reset_at: ev.reset_at, scope: ev.scope },
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
              }));
            }
          },
          ctrl.signal,
        );
      } catch (e) {
        if (ctrl.signal.aborted) {
          // F2: người dùng bấm Dừng TRƯỚC token đầu tiên — trước đây không
          // để lại dấu vết gì (không bong bóng trợ lý, không "Đã dừng"), nên
          // lượt hỏi trông như biến mất và "Tạo lại" nhắm nhầm câu trả lời
          // trước. Luôn thêm một bong bóng `status:"stopped"` (nội dung rỗng
          // nếu chưa có token nào — `AiConversation` tự hiện chú thích).
          setState((s) => ({
            ...s,
            streaming: false,
            streamingText: "",
            messages: [
              ...s.messages,
              {
                message_id: assistantIdRef.current ?? `local_asst_${clientId}`,
                role: "assistant" as const,
                content: s.streamingText,
                status: "stopped" as const,
                citations: [],
                created_at: new Date().toISOString(),
              },
            ],
          }));
        } else {
          const loi = loiTuApiError(e);
          // Chưa nhận `meta` = máy chủ CHƯA nhận lượt này (hết hạn mức, quá nhanh, đang bận, mất mạng…): tin không
          // có trong hội thoại thật, nên phải hiện "Chưa gửi" thay vì trông như đã gửi. Đã có `meta` mà luồng đứt
          // giữa chừng thì tin ĐÃ ở máy chủ — giữ nguyên.
          const chuaNhan = assistantIdRef.current === null;
          if (chuaNhan) lastUserTextRef.current = vanBanTruoc;
          setState((s) => ({
            ...s,
            streaming: false,
            streamingText: "",
            error: loi,
            messages: chuaNhan && !regenerateOf ? danhDauChuaGui(s.messages, userMsgId) : s.messages,
            availability: loi.code === "ai_budget_exhausted" ? apDungHetLuot(s.availability, loi.scope, loi.reset_at) : s.availability,
          }));
        }
      }
    },
    [state.streaming, state.conversationId, state.mode, state.activeProjectId],
  );

  const sendMessage = useCallback((text: string) => guiVanBan(text), [guiVanBan]);

  const stopStreaming = useCallback(() => {
    ctrlRef.current?.abort();
  }, []);

  /**
   * "Tạo lại" luôn nhắm vào LƯỢT NGƯỜI DÙNG CUỐI CÙNG (§F2) — không đòi hỏi
   * phải có sẵn một bong bóng trợ lý mới hoạt động: nếu lượt cuối chưa có
   * trả lời (rất hiếm sau khi đã luôn thêm bong bóng `stopped`/`error` ở
   * trên, nhưng vẫn giữ làm lưới an toàn), vẫn gửi lại được — chỉ khi CÓ một
   * bong bóng trợ lý cuối mới xoá nó trước khi gửi lại.
   */
  const regenerate = useCallback(async () => {
    if (!lastUserTextRef.current) return;
    const lastAssistant = [...state.messages].reverse().find((m) => m.role === "assistant");
    // KHÔNG xoá câu trả lời cũ ở đây: `guiVanBan` chỉ bỏ nó khi máy chủ đã nhận lượt mới (`meta`), để một lượt tạo
    // lại bị từ chối (hết hạn mức…) không làm câu trả lời cũ biến mất.
    await guiVanBan(lastUserTextRef.current, lastAssistant?.message_id);
  }, [state.messages, guiVanBan]);

  /** Tải sở thích (bật/tắt ghi nhớ) — gọi khi mở popover cài đặt, KHÔNG lúc mount (idle gần như zero mạng). */
  const loadPreferences = useCallback(async () => {
    try {
      const prefs = await aiApi.getPreferences();
      setState((s) => ({ ...s, preferences: prefs }));
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, []);

  const setMemoryEnabled = useCallback(async (value: boolean) => {
    setState((s) => ({
      ...s,
      preferences: s.preferences ? { ...s.preferences, memory_enabled: value } : { memory_enabled: value, preferences: {} },
    }));
    try {
      const prefs = await aiApi.putPreferences({ memory_enabled: value, preferences: {} });
      setState((s) => ({ ...s, preferences: prefs }));
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, []);

  /** "Xoá toàn bộ ký ức AI" (§5) — hội thoại + tóm tắt + sở thích; KHÔNG xoá dự án viết trừ khi `includeProjects`. */
  const deleteAllMemory = useCallback(async (includeProjects = false) => {
    try {
      await aiApi.deleteMemory(includeProjects);
      setState((s) => ({ ...s, conversations: [], conversationId: null, messages: [] }));
      ghiPhien(CO_HOI_THOAI, null);
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, []);

  const setDraft = useCallback((text: string) => {
    setState((s) => ({ ...s, draft: text }));
    ghiNhap(uidRef.current, text);
  }, []);

  /** Tải danh sách dự án viết — gọi khi vào mode `writer`/mở thanh dự án, KHÔNG lúc mount. */
  const loadProjects = useCallback(async () => {
    try {
      const r = await aiApi.listProjects();
      setState((s) => ({ ...s, projects: r.items }));
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, []);

  const createProject = useCallback(async (title: string) => {
    try {
      const body = ghepBodyDuAn(null, { title });
      const { project_id } = await aiApi.createProject(body);
      await loadProjects();
      const detail = await aiApi.getProject(project_id);
      setState((s) => ({ ...s, activeProjectId: project_id, activeProject: detail }));
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, [loadProjects]);

  const selectProject = useCallback(async (id: string | null) => {
    if (!id) {
      setState((s) => ({ ...s, activeProjectId: null, activeProject: null }));
      return;
    }
    setState((s) => ({ ...s, loadingProject: true }));
    try {
      const detail = await aiApi.getProject(id);
      setState((s) => ({ ...s, activeProjectId: id, activeProject: detail, loadingProject: false }));
    } catch (e) {
      setState((s) => ({ ...s, loadingProject: false, error: loiTuApiError(e) }));
    }
  }, []);

  const renameProject = useCallback(async (id: string, title: string) => {
    try {
      const hienTai = state.activeProjectId === id ? state.activeProject : await aiApi.getProject(id);
      const body = ghepBodyDuAn(hienTai, { title });
      await aiApi.updateProject(id, body);
      await loadProjects();
      if (state.activeProjectId === id) {
        const detail = await aiApi.getProject(id);
        setState((s) => ({ ...s, activeProject: detail }));
      }
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, [state.activeProjectId, state.activeProject, loadProjects]);

  const deleteProjectById = useCallback(async (id: string) => {
    try {
      await aiApi.deleteProject(id);
      setState((s) => ({
        ...s,
        projects: s.projects.filter((p) => p.project_id !== id),
        ...(s.activeProjectId === id ? { activeProjectId: null, activeProject: null } : {}),
      }));
    } catch (e) {
      setState((s) => ({ ...s, error: loiTuApiError(e) }));
    }
  }, []);

  /**
   * "Lưu vào dự án" — LUÔN do người dùng bấm (nút trên mỗi tin nhắn trợ lý
   * hoặc nút Lưu trong trình soạn dự án), KHÔNG BAO GIỜ tự động sau khi
   * stream xong. `appendMode="append"` nối thêm dòng mới vào nội dung cũ.
   */
  const saveToProjectField = useCallback(
    async (field: AiProjectField, text: string, appendMode: "replace" | "append" = "append") => {
      if (!state.activeProjectId) return;
      try {
        const hienTai = state.activeProject ?? (await aiApi.getProject(state.activeProjectId));
        const cu = docVanBanTruongDuAn(field, hienTai[field]);
        const moi = appendMode === "append" && cu ? `${cu}\n\n${text}` : text;
        const body = ghepBodyDuAn(hienTai, { [field]: moi } as Partial<Record<AiProjectField, string>>);
        await aiApi.updateProject(state.activeProjectId, body);
        const detail = await aiApi.getProject(state.activeProjectId);
        setState((s) => ({ ...s, activeProject: detail }));
      } catch (e) {
        setState((s) => ({ ...s, error: loiTuApiError(e) }));
      }
    },
    [state.activeProjectId, state.activeProject],
  );

  /** Lưu từ trình soạn dự án (`AiProjectEditor`) — GHI ĐÈ một hoặc nhiều trường trong MỘT lượt PUT. */
  const saveProjectFields = useCallback(
    async (patch: Partial<Record<AiProjectField, string>>) => {
      if (!state.activeProjectId) return;
      try {
        const hienTai = state.activeProject ?? (await aiApi.getProject(state.activeProjectId));
        const body = ghepBodyDuAn(hienTai, patch);
        await aiApi.updateProject(state.activeProjectId, body);
        const detail = await aiApi.getProject(state.activeProjectId);
        setState((s) => ({ ...s, activeProject: detail }));
      } catch (e) {
        setState((s) => ({ ...s, error: loiTuApiError(e) }));
      }
    },
    [state.activeProjectId, state.activeProject],
  );

  const value = useMemo<AiContextValue>(
    () => ({
      ...state,
      enabled: AI_ASSISTANT_ENABLED,
      access,
      eligible,
      openAssistant,
      ensureReady,
      enterFullscreen,
      closeAssistant,
      toggleHistory,
      selectConversation,
      newConversation,
      deleteConversationById,
      setMode,
      sendMessage,
      stopStreaming,
      regenerate,
      loadPreferences,
      setMemoryEnabled,
      deleteAllMemory,
      setDraft,
      loadProjects,
      createProject,
      selectProject,
      renameProject,
      deleteProjectById,
      saveToProjectField,
      saveProjectFields,
    }),
    [
      state,
      access,
      eligible,
      openAssistant,
      ensureReady,
      enterFullscreen,
      closeAssistant,
      toggleHistory,
      selectConversation,
      newConversation,
      deleteConversationById,
      setMode,
      sendMessage,
      stopStreaming,
      regenerate,
      loadPreferences,
      setMemoryEnabled,
      deleteAllMemory,
      setDraft,
      loadProjects,
      createProject,
      selectProject,
      renameProject,
      deleteProjectById,
      saveToProjectField,
      saveProjectFields,
    ],
  );

  return <AiContext.Provider value={value}>{children}</AiContext.Provider>;
}

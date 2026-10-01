/**
 * Máy chủ giả CHẠY TRONG TRANG cho harness QA giao diện trợ lý AI: ghi đè `window.fetch` cho `http://qa.local/api/ai/*`
 * và nói đúng hợp đồng `server/ai_assistant/routes.py` (JSON + SSE, 401/403/404/429, hạn mức 5/ngày theo người dùng).
 * Dùng token `Bearer tok_<userId>` như phiên thật: chuyển tài khoản = đổi token. KHÔNG có gì đi ra mạng.
 *
 * Kịch bản cho lượt gửi kế tiếp: `__qa.script.push({...})` (hết thì dùng kịch bản "ok" mặc định):
 *   { kind: "ok", words?: number, delay?: number }            trả lời bình thường
 *   { kind: "text", text: string, chunk?: number, delay?: number }
 *   { kind: "http", status: number, body: unknown }          từ chối trước khi bắt đầu luồng (429, 503…)
 *   { kind: "sse_error", partial?: string, code: string, scope?: string }
 *   { kind: "hang" }                                         mở luồng rồi im lặng cho tới khi bị Dừng
 */

type Step =
  | { kind: "ok"; words?: number; delay?: number }
  | { kind: "text"; text: string; chunk?: number; delay?: number }
  | { kind: "http"; status: number; body: unknown }
  | { kind: "sse_error"; partial?: string; code: string; scope?: string }
  | { kind: "eof"; partial?: string }
  | { kind: "hang" };

interface Msg {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  citations: unknown[];
  created_at: string;
}

interface Conv {
  conversation_id: string;
  owner: string;
  mode: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Msg[];
}

const encoder = new TextEncoder();
const WORDS = ["xin", "chào", "bạn", "đây", "là", "câu", "trả", "lời", "thử", "nghiệm", "của", "trợ", "lý", "truyện",
  "đêm", "trăng", "thành", "phố", "ngôi", "nhà", "cổ", "cánh", "cửa", "sổ", "nhỏ", "gió", "thổi", "qua"];

function now(): string {
  return new Date().toISOString();
}

function nextMidnightUtc(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 1);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString();
}

function frame(event: string, data: unknown): Uint8Array {
  return encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function sleep(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

export function installFakeServer(): void {
  const convs = new Map<string, Conv>();
  const used = new Map<string, number>();
  let counter = 0;
  const qa = {
    script: [] as Step[],
    cap: 5,
    token: null as string | null,
    log: [] as string[],
    calls: [] as { method: string; path: string; user: string | null }[],
    /** Số lần gọi `/api/ai/availability` v.v. — để kiểm "idle gần như zero mạng". */
    count: (needle: string) => qa.calls.filter((c) => c.path.includes(needle)).length,
    usedBy: (u: string) => used.get(u) ?? 0,
    setUsed: (u: string, n: number) => used.set(u, n),
    convsOf: (u: string) => [...convs.values()].filter((c) => c.owner === u).length,
    /** Gieo sẵn một hội thoại cho `user` (tiêu đề dài, lịch sử dài…) mà không tốn lượt. Trả về conversation_id. */
    seed: (user: string, o: { title?: string; mode?: string; messages?: { role: "user" | "assistant"; content: string; status?: string }[] }) => {
      counter += 1;
      const stamp = now();
      const c: Conv = {
        conversation_id: `s${counter}_${user}`, owner: user, mode: o.mode ?? "general", title: o.title ?? "",
        created_at: stamp, updated_at: stamp,
        messages: (o.messages ?? []).map((m, i) => ({ message_id: `seed${counter}_${i}`, role: m.role, content: m.content,
                                                      status: m.status ?? "complete", citations: [], created_at: stamp })),
      };
      convs.set(c.conversation_id, c);
      return c.conversation_id;
    },
  };
  (window as unknown as { __qa: typeof qa }).__qa = qa;

  const realFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith("http://qa.local/api/ai/")) return realFetch(input, init);
    const u = new URL(url);
    const path = u.pathname;
    const method = (init?.method ?? "GET").toUpperCase();
    const auth = new Headers(init?.headers).get("authorization") ?? "";
    const tok = auth.startsWith("Bearer tok_") ? auth.slice("Bearer tok_".length) : null;
    qa.calls.push({ method, path, user: tok });
    if (!tok) return jsonResponse(401, { detail: "Cần đăng nhập." });

    const usedNow = used.get(tok) ?? 0;
    const allowance = () => {
      const n = used.get(tok) ?? 0;
      return { requests_used: n, requests_limit: qa.cap, requests_remaining: Math.max(0, qa.cap - n),
               exhausted: n >= qa.cap, reset_at: nextMidnightUtc() };
    };

    if (path === "/api/ai/access") return jsonResponse(200, { eligible: true });
    if (path === "/api/ai/availability") {
      return jsonResponse(200, {
        enabled: true, reason: null, name: "Fanfic AI", modes: ["general", "story", "support", "writer"],
        web_search: false, memory_enabled: true,
        limits: { used_today: usedNow * 400, limit_today: 30000, ...allowance() },
      });
    }
    if (path === "/api/ai/preferences") return jsonResponse(200, { memory_enabled: true, preferences: {} });
    if (path === "/api/ai/projects") return jsonResponse(200, { items: [] });

    if (path === "/api/ai/conversations" && method === "GET") {
      const items = [...convs.values()].filter((c) => c.owner === tok)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .map((c) => ({ conversation_id: c.conversation_id, mode: c.mode, title: c.title, created_at: c.created_at,
                       updated_at: c.updated_at, message_count: c.messages.length, ephemeral: false }));
      return jsonResponse(200, { items });
    }
    if (path === "/api/ai/conversations" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}"));
      counter += 1;
      const c: Conv = { conversation_id: `c${counter}_${tok}`, owner: tok, mode: body.mode ?? "general",
                        title: body.title ?? "", created_at: now(), updated_at: now(), messages: [] };
      convs.set(c.conversation_id, c);
      return jsonResponse(200, { conversation_id: c.conversation_id, mode: c.mode, title: c.title,
                                 created_at: c.created_at, ephemeral: false });
    }
    const m = path.match(/^\/api\/ai\/conversations\/([^/]+)(\/messages)?$/);
    if (m) {
      const c = convs.get(decodeURIComponent(m[1]));
      if (!c) return jsonResponse(404, { detail: { code: "ai_not_found", message: "Không tìm thấy hội thoại." } });
      if (c.owner !== tok) return jsonResponse(403, { detail: { code: "ai_forbidden", message: "Hội thoại này không thuộc về bạn." } });
      if (!m[2] && method === "GET") {
        return jsonResponse(200, { conversation_id: c.conversation_id, mode: c.mode, title: c.title, ephemeral: false,
                                   messages: c.messages });
      }
      if (!m[2] && method === "DELETE") {
        convs.delete(c.conversation_id);
        return jsonResponse(200, { deleted: true });
      }
      if (m[2] && method === "POST") return streamMessage(c, tok, JSON.parse(String(init?.body ?? "{}")), init?.signal ?? null, allowance);
    }
    return jsonResponse(404, { detail: "no route in fake server: " + path });
  };

  function streamMessage(c: Conv, user: string, body: { content: string }, signal: AbortSignal | null,
                         allowance: () => unknown): Response | Promise<Response> {
    const step: Step = qa.script.shift() ?? { kind: "ok" };
    if ((used.get(user) ?? 0) >= qa.cap) {
      return jsonResponse(429, { detail: { code: "ai_budget_exhausted", scope: "user", reset_at: nextMidnightUtc(),
                                           message: "Bạn đã dùng hết lượt hỏi hôm nay." } });
    }
    if (step.kind === "http") return jsonResponse(step.status, step.body);

    const assistantId = `a${++counter}`;
    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const onAbort = () => controller.error(new DOMException("Aborted", "AbortError"));
        if (signal?.aborted) return onAbort();
        signal?.addEventListener("abort", onAbort);
        const push = (e: string, d: unknown) => controller.enqueue(frame(e, d));
        try {
          c.messages.push({ message_id: `u${counter}`, role: "user", content: body.content, status: "complete",
                            citations: [], created_at: now() });
          push("meta", { message_id: assistantId, conversation_id: c.conversation_id });
          let text = "";
          if (step.kind === "hang") {
            await sleep(60_000, signal);
          } else if (step.kind === "eof") {
            // Đóng luồng SẠCH giữa chừng, không có `done`/`error` (lớp trung gian cắt êm khi máy chủ khởi động lại).
            if (step.partial) push("delta", { text: step.partial });
            controller.close();
            return;
          } else if (step.kind === "sse_error") {
            text = step.partial ?? "";
            if (text) push("delta", { text });
            used.set(user, (used.get(user) ?? 0) + (text ? 1 : 0));
            push("usage", { input_tokens: 10, output_tokens: 5, used_today: 15, lane: "user", allowance: allowance() });
            push("error", { code: step.code, message: "lỗi", scope: step.scope, reset_at: nextMidnightUtc() });
            controller.close();
            return;
          } else {
            const delay = ("delay" in step && step.delay) || 25;
            const parts: string[] = [];
            if (step.kind === "text") {
              const size = step.chunk ?? 12;
              for (let i = 0; i < step.text.length; i += size) parts.push(step.text.slice(i, i + size));
            } else {
              const n = step.words ?? 30;
              for (let i = 0; i < n; i += 1) parts.push(WORDS[i % WORDS.length] + " ");
            }
            for (const p of parts) {
              await sleep(delay, signal);
              text += p;
              push("delta", { text: p });
            }
          }
          used.set(user, (used.get(user) ?? 0) + 1);
          c.messages.push({ message_id: assistantId, role: "assistant", content: text, status: "complete",
                            citations: [], created_at: now() });
          c.updated_at = now();
          push("usage", { input_tokens: 10, output_tokens: 5, used_today: 15, lane: "user", allowance: allowance() });
          push("done", { status: "complete" });
          controller.close();
        } catch {
          // Dừng giữa chừng: luồng đã bị `controller.error` ở onAbort.
        } finally {
          signal?.removeEventListener("abort", onAbort);
        }
      },
    });
    return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  }
}

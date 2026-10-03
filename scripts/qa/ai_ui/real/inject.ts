/**
 * Mã QA chèn vào bản dựng Next THẬT (`run_real.mjs`) bằng `Page.addScriptToEvaluateOnNewDocument` — TRƯỚC mã của trang. Ứng dụng thật
 * (layout, header, footer, định tuyến, chunk lười, CSS thật) được dựng với `NEXT_PUBLIC_API_BASE=http://qa.local`, nên MỌI lời gọi API đều
 * rơi vào đây và không có gì đi ra mạng:
 *   * `/api/ai/*`   → máy chủ SSE giả (`harness/fakeServer.ts`, nói đúng hợp đồng `server/ai_assistant/routes.py`)
 *   * `/api/auth/me`→ hồ sơ giả của người có token `Bearer tok_<id>` (token đặt vào localStorage `fas.token` trước khi trang chạy)
 *   * mọi route khác của qa.local → 404 JSON ngay (không chờ DNS), như một backend không có route đó
 * Cộng `__qa.traceStart/…`, `__qa.setDock/setMini` (`harness/qaTools.ts`). KHÔNG phải mã sản phẩm.
 */
import { installFakeServer } from "../harness/fakeServer";
import { installQaTools } from "../harness/qaTools";

installFakeServer();
installQaTools();

const withFakeAi = window.fetch;
window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  if (url.startsWith("http://qa.local/api/auth/me")) {
    const auth = new Headers(init?.headers).get("authorization") ?? "";
    const tok = auth.startsWith("Bearer tok_") ? auth.slice("Bearer tok_".length) : null;
    if (!tok) return json(401, { detail: "Cần đăng nhập." });
    return json(200, {
      profile: {
        user_id: tok, email: `${tok}@qa.local`, display_name: tok, tier: "free", listened_minutes: 0, tts_characters_used: 0,
        created_at: new Date().toISOString(), username: tok, bio: "", author_status: "none", is_admin: false, admin_role: "none",
      },
    });
  }
  if (url.startsWith("http://qa.local/") && !url.startsWith("http://qa.local/api/ai/")) return json(404, { detail: "qa: không có route giả" });
  return withFakeAi(input, init);
};

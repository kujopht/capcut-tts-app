/**
 * Fanfic AI Assistant V1 — bat bien tinh (khong jsdom, dung quy uoc repo:
 * quet MA NGUON cho cac dieu KHONG DUOC hong lang le).
 *
 * TAT CA cac test o day chi doc file nguon roi assert bang regex/parse don
 * gian — khong render React, khong goi mang. Test hanh vi thuc (stream,
 * mo/dong panel...) thuoc ve QA Chrome thuc, khong phai node:test tinh.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
/** Bỏ comment khối/dòng trước khi quét — docstring của kho này hay NÊU TÊN
 *  đúng thứ nó cố ý KHÔNG dùng (vd "KHÔNG `dangerouslySetInnerHTML`"), nên
 *  quét thô sẽ tự báo lỗi vào chính lời giải thích của nó. */
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

function moiTep(dir = SRC) {
  const ra = [];
  for (const ten of readdirSync(dir)) {
    const p = `${dir}${dir.endsWith("/") ? "" : "/"}${ten}`;
    if (statSync(p).isDirectory()) ra.push(...moiTep(`${p}/`));
    else if (/\.(tsx?|mjs|js|css)$/.test(ten)) ra.push(p);
  }
  return ra;
}

const AI_FILES = moiTep(`${SRC}components/ai/`);
const LIB_AI_FILES = moiTep(`${SRC}lib/ai/`);
const TAT_CA_AI = [...AI_FILES, ...LIB_AI_FILES];
const tuongDoiSrc = (p) => p.slice(SRC.length).replace(/\\/g, "/");

test("1. cờ NEXT_PUBLIC_AI_ASSISTANT_ENABLED mặc định TẮT và là cờ MỘT chỗ", () => {
  const features = read("lib/features.ts");
  assert.match(
    features,
    /export const AI_ASSISTANT_ENABLED = process\.env\.NEXT_PUBLIC_AI_ASSISTANT_ENABLED === "1";/,
    "AI_ASSISTANT_ENABLED phải đọc đúng biến build-time, không có giá trị mặc định bật ngầm",
  );
});

test("2. AiLauncher/AiPanel tự trả null khi cờ tắt hoặc availability chưa bật", () => {
  const launcher = read("components/ai/AiLauncher.tsx");
  const panel = read("components/ai/AiPanel.tsx");
  assert.match(launcher, /if \(!enabled \|\| !profile\) return null;/);
  assert.match(launcher, /availability === false \|\| \(availability && !availability\.enabled\)/);
  assert.match(panel, /if \(!enabled \|\| !open\) return null;/);
  assert.match(panel, /availability === false \|\| \(availability && !availability\.enabled\)/);
});

test("3. AiProvider không gọi /api/ai/* lúc mount — chỉ khi openAssistant() được gọi (lười)", () => {
  const provider = read("components/ai/AiProvider.tsx");
  // Không có useEffect nào gọi thẳng aiApi.availability() vô điều kiện lúc mount.
  const cacUseEffect = provider.match(/useEffect\(\(\) => \{[\s\S]*?\n {2}\}, \[[^\]]*\]\);/g) ?? [];
  for (const doan of cacUseEffect) {
    assert.ok(!/aiApi\.(availability|listConversations|getConversation)/.test(doan),
      "một useEffect gọi thẳng /api/ai/* lúc mount — vi phạm nguyên tắc lười");
  }
  assert.match(provider, /const xinAvailability = useCallback/, "availability phải được xin qua một hàm gọi được, không tự động");
});

test("4. KHÔNG component nào trong components/ai/lib/ai dùng dangerouslySetInnerHTML", () => {
  const viPham = TAT_CA_AI.filter((p) => codeOnly(read(tuongDoiSrc(p))).includes("dangerouslySetInnerHTML"));
  assert.deepEqual(viPham.map(tuongDoiSrc), []);
});

test("5. Không tên provider/model/vendor nào lộ ra tầng giao diện (chỉ backend biết)", () => {
  const CAM = /qwen|azure|openai|dashscope|tencent/i;
  const viPham = TAT_CA_AI.filter((p) => CAM.test(codeOnly(read(tuongDoiSrc(p)))));
  assert.deepEqual(viPham.map(tuongDoiSrc), []);
});

test("6. Không khoá API/bí mật nào bị nhúng vào bundle web (chỉ NEXT_PUBLIC_API_BASE + cờ)", () => {
  const CAM = /NEXT_PUBLIC_\w*(KEY|SECRET|TOKEN)\w*/;
  const viPham = TAT_CA_AI.filter((p) => CAM.test(codeOnly(read(tuongDoiSrc(p)))));
  assert.deepEqual(viPham.map(tuongDoiSrc), []);
  // Không literal trông giống API key (sk-..., 32+ hex) trong mã nguồn AI.
  const GIONG_KHOA = /\b(sk-[A-Za-z0-9]{16,}|[A-Fa-f0-9]{32,})\b/;
  const viPhamKhoa = TAT_CA_AI.filter((p) => GIONG_KHOA.test(codeOnly(read(tuongDoiSrc(p)))));
  assert.deepEqual(viPhamKhoa.map(tuongDoiSrc), []);
});

test("7. AiLauncher: z-index 56, bottom offset, và ẩn hẳn ở màn hình <=1023px (bao trùm mốc ≤640px di động)", () => {
  const css = read("components/ai/ai.css");
  const khoiLauncher = css.match(/\.ai-launcher \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(khoiLauncher, /right:\s*16px/);
  assert.match(khoiLauncher, /bottom:\s*88px/);
  assert.match(khoiLauncher, /z-index:\s*56/);
  assert.match(css, /@media \(max-width:\s*1023px\)\s*\{\s*\.ai-launcher\s*\{\s*display:\s*none;/,
    "nút nổi phải ẩn hẳn ở màn hình hẹp (di động vào qua /assistant, không nút nổi)");
  // Nâng theo mini player, cùng kỹ thuật body:has(.mini) với chat.css — KHÔNG sửa chat.css.
  assert.match(css, /body:has\(\.mini\) \.ai-launcher/);
});

test("8. AiPanel neo phải z-index 56, kích thước 380px x min(600px, 100dvh-160px), và tự dịch trái theo .chat-dock", () => {
  const css = read("components/ai/ai.css");
  const khoiPanel = css.match(/\.ai-panel \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(khoiPanel, /width:\s*380px/);
  assert.match(khoiPanel, /height:\s*min\(600px,\s*calc\(100dvh - 160px\)\)/);
  assert.match(khoiPanel, /z-index:\s*56/);
  const panelTsx = read("components/ai/AiPanel.tsx");
  assert.match(panelTsx, /ResizeObserver/);
  assert.match(panelTsx, /querySelector<HTMLElement>\(".chat-dock"\)/);
  assert.match(panelTsx, /--ai-dock-offset/);
  // KHÔNG chạm file Chat V1.
  assert.ok(!/from "@\/components\/chat\//.test(panelTsx), "AiPanel không được import trực tiếp mã Chat V1");
});

test("9. /assistant tồn tại, an toàn vùng-an-toàn, và là lối vào chính trên di động (không nút nổi ở đó)", () => {
  const page = read("app/assistant/page.tsx");
  assert.match(page, /AiControls/);
  assert.match(page, /AiConversation/);
  assert.match(page, /AiComposer/);
  const css = read("components/ai/ai.css");
  const khoiTrang = css.match(/\.ai-trang \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(khoiTrang, /env\(safe-area-inset-top/);
  assert.match(khoiTrang, /env\(safe-area-inset-bottom/);
  assert.match(khoiTrang, /env\(safe-area-inset-left/);
  assert.match(khoiTrang, /env\(safe-area-inset-right/);
});

test("10. Mục \"Trợ lý AI\" trong menu tài khoản chỉ hiện khi cờ bật, dùng FanficIcon", () => {
  const nav = read("components/NavAuth.tsx");
  const doan = nav.match(/\{AI_ASSISTANT_ENABLED \? \([\s\S]*?Trợ lý AI[\s\S]*?\) : null\}/)?.[0];
  assert.ok(doan, "không tìm thấy khối mục menu Trợ lý AI được gate bởi cờ");
  assert.match(doan, /href="\/assistant"/);
  assert.match(doan, /<FanficIcon name="ai"/);
});

test("11. Trang chương có lối vào mode `story` cạnh AskAiPanel, gửi novel_id/chapter_id/current_chapter_index", () => {
  const page = read("app/chapters/[id]/page.tsx");
  assert.match(page, /<AskAiPanel/);
  assert.match(page, /<AskAiAssistantStoryEntry/);
  const entry = read("components/ai/AskAiAssistantStoryEntry.tsx");
  assert.match(entry, /mode:\s*"story"/);
  assert.match(entry, /novel_id:\s*novelId/);
  assert.match(entry, /chapter_id:\s*chapterId/);
  assert.match(entry, /current_chapter_index:\s*chapterIndex/);
});

test("12. Sự kiện SSE parse đúng §10: meta/delta/citations/usage/done/error, bỏ qua `: ping`", () => {
  const sse = read("lib/ai/sse.ts");
  for (const ten of ["meta", "delta", "citations", "usage", "done", "error"]) {
    assert.match(sse, new RegExp(`case "${ten}":`));
  }
  assert.match(sse, /dong\.startsWith\(":"\)/, "phải bỏ qua dòng nhịp tim `: ping` khi tách khung");
});

test("13. Luồng tin nhắn dùng fetch + Authorization Bearer, KHÔNG EventSource/token-trên-URL", () => {
  const client = read("lib/ai/client.ts");
  assert.match(client, /Authorization:\s*`Bearer \$\{token\}`/);
  assert.ok(!/new EventSource/.test(client), "không được dùng EventSource (không gửi được header Authorization)");
  assert.ok(!/\/api\/ai\/[^"'`]*\$\{[^}]*token[^}]*\}/i.test(client), "token không được lên URL");
});

test("14. Mã lỗi ổn định §10 được ánh xạ đầy đủ, không bịa mã mới", () => {
  const types = read("lib/ai/types.ts");
  const MA_CHUAN = [
    "ai_not_enabled", "ai_no_provider", "ai_rate_limited", "ai_budget_exhausted",
    "ai_busy", "ai_context_too_large", "ai_provider_unavailable",
    "ai_provider_interrupted", "ai_forbidden", "ai_not_found",
  ];
  for (const ma of MA_CHUAN) assert.match(types, new RegExp(`"${ma}"`));
  const controls = read("components/ai/AiControls.tsx");
  for (const ma of MA_CHUAN) assert.match(controls, new RegExp(`"${ma}"`), `AiControls thiếu thông điệp thân thiện cho ${ma}`);
});

test("15. Chế độ AI dùng đúng 4 mode + nhãn tiếng Việt, không tự thêm mode lạ", () => {
  const types = read("lib/ai/types.ts");
  assert.match(types, /"general" \| "story" \| "support" \| "writer"/);
  assert.match(types, /general: "Trợ lý chung"/);
  assert.match(types, /story: "Truyện"/);
  assert.match(types, /support: "Hỗ trợ"/);
  assert.match(types, /writer: "Studio viết"/);
});

test("16. Markdown tối giản dựng bằng phần tử React thật, không có đường nào chèn HTML thô", () => {
  const md = codeOnly(read("components/ai/markdownLite.tsx"));
  assert.ok(!md.includes("dangerouslySetInnerHTML"));
  assert.ok(!/document\.write|innerHTML/.test(md));
});

test("17. Ephemeral (memory_enabled=false) hiện huy hiệu, và xoá ký ức dùng xác nhận TRONG TRANG (không window.confirm)", () => {
  const controlsRaw = read("components/ai/AiControls.tsx");
  const controls = codeOnly(controlsRaw);
  assert.match(controlsRaw, /ai-badge-ephemeral/);
  assert.match(controlsRaw, /Không lưu lịch sử/);
  assert.match(controlsRaw, /Xoá toàn bộ ký ức AI/);
  assert.ok(!/window\.confirm/.test(controls), "phải dùng xác nhận trong trang (hai bước), không window.confirm");
  const provider = read("components/ai/AiProvider.tsx");
  assert.match(provider, /deleteAllMemory/);
  assert.match(provider, /setMemoryEnabled/);
});

test("18. Writer Studio: thanh dự án CHỈ hiện ở mode `writer`, không render khi mode khác", () => {
  const bar = read("components/ai/AiWriterBar.tsx");
  assert.match(bar, /if \(mode !== "writer"\) return null;/);
  // AiPanel/`/assistant` đều mount AiWriterBar KHÔNG ĐIỀU KIỆN theo mode ở
  // JSX (bản thân component tự gate) — panel/trang không được tự thêm một
  // điều kiện `mode === "writer"` NGOÀI component (một nguồn chân lý duy nhất).
  const panel = read("components/ai/AiPanel.tsx");
  const page = read("app/assistant/page.tsx");
  assert.match(panel, /<AiWriterBar \/>/);
  assert.match(page, /<AiWriterBar \/>/);
});

test("19. Không component nào trong components/ai dùng window.confirm/window.prompt (xác nhận LUÔN trong trang)", () => {
  const CAM = /window\.(confirm|prompt)/;
  const viPham = AI_FILES.filter((p) => CAM.test(codeOnly(read(tuongDoiSrc(p)))));
  assert.deepEqual(viPham.map(tuongDoiSrc), []);
});

test("20. Xoá dự án dùng xác nhận hai bước trong trang, có nút Huỷ", () => {
  const bar = codeOnly(read("components/ai/AiWriterBar.tsx"));
  assert.match(bar, /xoaXacNhan/);
  assert.match(bar, /Xác nhận xoá/);
  assert.match(bar, /Huỷ/);
});

test("21. \"Lưu vào dự án\" (nối thêm) và \"Lưu dự án\" (ghi đè) đều LUÔN do người dùng bấm, không tự động sau khi stream xong", () => {
  const provider = codeOnly(read("components/ai/AiProvider.tsx"));
  // Khối xử lý sự kiện `done` của luồng SSE không được gọi thẳng
  // saveToProjectField/saveProjectFields — hai hàm đó chỉ được gọi từ onClick
  // của component (AiConversation/AiProjectEditor), không từ vòng lặp stream.
  const doanDone = provider.match(/ev\.type === "done"\) \{[\s\S]*?\n {12}\}/)?.[0] ?? "";
  assert.ok(!/saveToProjectField|saveProjectFields/.test(doanDone),
    "xử lý sự kiện done không được tự lưu vào dự án");
  const conv = codeOnly(read("components/ai/AiConversation.tsx"));
  const editor = codeOnly(read("components/ai/AiProjectEditor.tsx"));
  assert.match(conv, /onClick=\{\(\) => \{\s*void saveToProjectField/);
  assert.match(editor, /onClick=\{\(\) => void luu\(\)\}/);
});

test("22. Chip gợi ý Studio viết chèn vào draft dùng chung của composer, không tự gửi", () => {
  const bar = codeOnly(read("components/ai/AiWriterBar.tsx"));
  for (const nhan of ["Brainstorm", "Premise", "Dàn ý", "Nhân vật", "Thế giới", "Viết nháp chương"]) {
    assert.match(bar, new RegExp(nhan.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(bar, /setDraft\(/);
  assert.ok(!/void sendMessage|sendMessage\(/.test(bar), "chip không được tự gửi tin thay người dùng");
});

test("23. /assistant: nút Đóng điều hướng lùi (router.back, fallback \"/\"), không chỉ tắt cờ open", () => {
  const page = read("app/assistant/page.tsx");
  assert.match(page, /router\.back\(\)/);
  assert.match(page, /router\.push\("\/"\)/);
  assert.match(page, /onClose=\{veTruoc\}/);
});

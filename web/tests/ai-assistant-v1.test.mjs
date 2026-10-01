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

test("7. AiLauncher: z-index 56, bottom offset, dịch trái theo .chat-dock (F1), và ẩn hẳn ở màn hình <=1023px", () => {
  const css = read("components/ai/ai.css");
  const khoiLauncher = css.match(/\.ai-launcher \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(khoiLauncher, /right:\s*calc\(16px \+ var\(--ai-dock-offset\)\)/,
    "F1: launcher phải dùng CÙNG offset dock với panel, không đứng yên right:16px");
  assert.match(khoiLauncher, /bottom:\s*88px/);
  assert.match(khoiLauncher, /z-index:\s*56/);
  assert.match(css, /@media \(max-width:\s*1023px\)\s*\{\s*\.ai-launcher\s*\{\s*display:\s*none;/,
    "nút nổi phải ẩn hẳn ở màn hình hẹp (di động vào qua /assistant, không nút nổi)");
  // Nâng theo mini player, cùng kỹ thuật body:has(.mini) với chat.css — KHÔNG sửa chat.css.
  assert.match(css, /body:has\(\.mini\) \.ai-launcher/);
  const launcherTsx = read("components/ai/AiLauncher.tsx");
  assert.match(launcherTsx, /useChatDockOffset/);
  assert.match(launcherTsx, /if \(open\) return null;/, "F1: launcher phải tự ẩn khi panel đang mở, không đè lên góc panel");
});

test("8. AiPanel neo phải z-index 56, kích thước 380px x min(600px, 100dvh-160px), và tự dịch trái theo .chat-dock", () => {
  const css = read("components/ai/ai.css");
  const khoiPanel = css.match(/\.ai-panel \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(khoiPanel, /width:\s*380px/);
  assert.match(khoiPanel, /height:\s*min\(600px,\s*calc\(100dvh - 160px\)\)/);
  assert.match(khoiPanel, /z-index:\s*56/);
  const panelTsx = read("components/ai/AiPanel.tsx");
  assert.match(panelTsx, /useChatDockOffset/);
  assert.match(panelTsx, /--ai-dock-offset/);
  // KHÔNG chạm file Chat V1.
  assert.ok(!/from "@\/components\/chat\//.test(panelTsx), "AiPanel không được import trực tiếp mã Chat V1");
  const hookTsx = read("components/ai/useChatDockOffset.ts");
  assert.match(hookTsx, /ResizeObserver/);
  assert.match(hookTsx, /querySelector<HTMLElement>\(".chat-dock"\)/);
});

test("F3. AiPanel/AiLauncher KHÔNG mount trên /assistant — tránh .ai-panel-tin nhân đôi trong DOM", () => {
  const panelTsx = read("components/ai/AiPanel.tsx");
  const launcherTsx = read("components/ai/AiLauncher.tsx");
  assert.match(panelTsx, /pathname === "\/assistant"\) return null;/);
  assert.match(launcherTsx, /pathname === "\/assistant"\) return null;/);
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

test("10. Mục \"Trợ lý AI\" trong menu tài khoản chỉ hiện khi cờ bật VÀ máy chủ xác nhận, dùng FanficIcon", () => {
  const nav = read("components/NavAuth.tsx");
  const doan = nav.match(/\{AI_ASSISTANT_ENABLED && ai\?\.eligible \? \([\s\S]*?Trợ lý AI[\s\S]*?\) : null\}/)?.[0];
  assert.ok(doan, "không tìm thấy khối mục menu Trợ lý AI được gate bởi cờ + `/api/ai/access`");
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
  assert.match(types, /story: "Truyện \(beta\)"/); // release gate B: phạm vi hạn chế
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

test("F2. Dừng/lỗi TRƯỚC token đầu tiên vẫn để lại một bong bóng trợ lý (không lượt hỏi nào biến mất)", () => {
  const provider = codeOnly(read("components/ai/AiProvider.tsx"));
  // Nhánh `catch` khi `ctrl.signal.aborted` phải LUÔN thêm một tin nhắn
  // `status: "stopped"` vào `messages`, kể cả khi `streamingText` rỗng —
  // không còn nhánh chỉ tắt `streaming` mà không để lại dấu vết.
  const doanAbort = provider.match(/if \(ctrl\.signal\.aborted\) \{[\s\S]*?\n {8}\} else \{/)?.[0] ?? "";
  assert.match(doanAbort, /status:\s*"stopped"\s*as const/, "nhánh abort phải luôn thêm bong bóng status:\"stopped\"");
  assert.match(doanAbort, /messages:\s*\[\s*\.\.\.s\.messages/, "phải nối vào messages, không bỏ qua");
  // Sự kiện `error` cũng LUÔN thêm bong bóng — không còn điều kiện
  // `s.streamingText ? {...} : {}` (đường cũ bỏ qua khi chưa có token nào).
  const doanError = provider.match(/\} else if \(ev\.type === "error"\) \{[\s\S]*?\n {12}\}\n {10}\}/)?.[0] ?? "";
  assert.ok(!/s\.streamingText\s*\?\s*\{/.test(doanError), "sự kiện error không được điều kiện theo streamingText nữa");
  assert.match(doanError, /messages:\s*\[\s*\.\.\.s\.messages/);
});

test("F2. Tạo lại luôn nhắm vào lượt người dùng CUỐI CÙNG, không đòi hỏi có sẵn bong bóng trợ lý", () => {
  const provider = codeOnly(read("components/ai/AiProvider.tsx"));
  const doanRegen = provider.match(/const regenerate = useCallback\(async \(\) => \{[\s\S]*?\n {2}\}, \[state\.messages, guiVanBan\]\);/)?.[0] ?? "";
  assert.ok(doanRegen, "không tìm thấy regenerate()");
  assert.ok(!/if \(!lastAssistant \|\|/.test(doanRegen), "regenerate không được bắt buộc phải có bong bóng trợ lý mới chạy");
  assert.match(doanRegen, /if \(!lastUserTextRef\.current\) return;/);
});

test("F2. Bong bóng trợ lý rỗng (dừng/lỗi) hiện câu giải thích rõ ràng, không phải markdown rỗng vô hình", () => {
  const conv = codeOnly(read("components/ai/AiConversation.tsx"));
  assert.match(conv, /Đã dừng — chưa có nội dung\./);
  assert.match(conv, /Không có phản hồi do lỗi\./);
  const css = read("components/ai/ai.css");
  assert.match(css, /\.ai-bong-rong/);
});

test("F3. /assistant là bố cục toàn màn hình CỐ ĐỊNH ở <=1023px (z-index 70, inset 0), không nằm trong luồng dưới header site", () => {
  const css = read("components/ai/ai.css");
  const khoiMedia = css.match(/@media \(max-width: 1023px\) \{\s*\.ai-trang \{[\s\S]*?\n {2}\}\n\}/)?.[0] ?? "";
  assert.match(khoiMedia, /position:\s*fixed/, "F3: /assistant phải position:fixed ở màn hình hẹp — nếu không nó nằm dưới header site và ô soạn tin lọt ra ngoài khung nhìn");
  assert.match(khoiMedia, /inset:\s*0/);
  assert.match(khoiMedia, /z-index:\s*70/, "cùng bậc z-index với overlay di động của Chat V1 (.chat-co-hoi-thoai .chat-cot-tin)");
  // Ô soạn tin luôn thấy được, tránh vùng an toàn đáy (home indicator iOS).
  assert.match(css, /\.ai-trang \.ai-panel-soan \{[\s\S]*?env\(safe-area-inset-bottom/);
});

test("F4. Nhãn hạn mức hiện PHẦN TRĂM (không phải số token thô) trong câu chính; số token chỉ ở tooltip", () => {
  const controls = codeOnly(read("components/ai/AiControls.tsx"));
  assert.match(controls, /Đã dùng \{phanTramSuDung\(/, "F4: câu chính phải hiện phần trăm, không phải used_today/limit_today thô");
  assert.match(controls, /hạn mức hôm nay/);
  assert.match(controls, /title=\{`\$\{availability\.limits\.used_today[\s\S]*?token`\}/, "số token thô chỉ nằm trong title (tooltip)");
  assert.ok(!/Đã dùng \{availability\.limits\.used_today\.toLocaleString\("vi-VN"\)\}\//.test(controls),
    "không còn hiện thẳng used_today/limit_today ở câu chính (dạng cũ gây hiểu lầm token = lượt hỏi)");
});

// ---------------------------------------------------------------- Release gate C
// Lỗi: mở /assistant rồi quay về trang thường -> panel nổi TỰ BẬT (vì trang
// /assistant gọi openAssistant() và ghi cờ mở vào sessionStorage).

function khoGia() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => void m.set(k, String(v)),
    removeItem: (k) => void m.delete(k),
    _m: m,
  };
}

test("RG-C1. Hành vi thật: vào /assistant rồi quay về -> panel nổi ĐÓNG; hội thoại/lịch sử giữ nguyên", async () => {
  const { apDungHanhDongMo, khoiPhucMo, ghiPhien, CO_HOI_THOAI } = await import("../src/lib/ai/phienMo.ts");

  // (a) Chưa từng mở panel: vào /assistant, quay về (tải lại/khôi phục) -> đóng.
  const kho = khoGia();
  ghiPhien(CO_HOI_THOAI, "conv_1", kho); // /assistant đã nạp/tạo một hội thoại
  assert.equal(apDungHanhDongMo("vao_toan_man", kho), false);
  assert.deepEqual(khoiPhucMo(kho), { open: false, conversationId: "conv_1" });

  // (b) Panel nổi ĐANG MỞ rồi sang /assistant (menu "Trợ lý AI"): quay về vẫn đóng.
  const kho2 = khoGia();
  assert.equal(apDungHanhDongMo("mo_noi", kho2), true);
  ghiPhien(CO_HOI_THOAI, "conv_2", kho2);
  apDungHanhDongMo("vao_toan_man", kho2);
  assert.deepEqual(khoiPhucMo(kho2), { open: false, conversationId: "conv_2" },
    "cờ mở phải bị xoá, hội thoại đang mở phải còn");

  // (c) Người dùng TỰ mở lại panel sau đó -> mở, cùng hội thoại cũ.
  assert.equal(apDungHanhDongMo("mo_noi", kho2), true);
  assert.deepEqual(khoiPhucMo(kho2), { open: true, conversationId: "conv_2" });

  // (d) Đóng bằng X -> đóng; hội thoại vẫn giữ.
  assert.equal(apDungHanhDongMo("dong_noi", kho2), false);
  assert.deepEqual(khoiPhucMo(kho2), { open: false, conversationId: "conv_2" });

  // (e) Không có sessionStorage (SSR/chế độ riêng tư chặn) -> không ném, đóng.
  assert.equal(apDungHanhDongMo("vao_toan_man", null), false);
  assert.deepEqual(khoiPhucMo(null), { open: false, conversationId: null });
});

test("RG-C2. Nối dây: /assistant dùng enterFullscreen, KHÔNG openAssistant; chỉ nút mở tường minh ghi 'mo_noi'", () => {
  const boChuThich = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const page = boChuThich(read("app/assistant/page.tsx"));
  assert.match(page, /void enterFullscreen\(\)/);
  assert.ok(!/openAssistant/.test(page), "/assistant không được gọi openAssistant (nó ghi cờ mở panel nổi)");

  const provider = read("components/ai/AiProvider.tsx");
  assert.ok(!/fas\.ai\.open|CO_MO/.test(provider), "cờ mở chỉ được đụng qua lib/ai/phienMo.ts");
  const moNoi = provider.match(/apDungHanhDongMo\("mo_noi"\)/g) ?? [];
  assert.equal(moNoi.length, 1, "chỉ đúng MỘT chỗ ghi cờ mở: openAssistant");
  const openFn = provider.slice(provider.indexOf("const openAssistant"), provider.indexOf("const enterFullscreen"));
  assert.match(openFn, /apDungHanhDongMo\("mo_noi"\)/);
  const fullFn = provider.slice(provider.indexOf("const enterFullscreen"), provider.indexOf("const closeAssistant"));
  assert.match(fullFn, /apDungHanhDongMo\("vao_toan_man"\)/);
  assert.match(fullFn, /await ensureReady\(\)/);
  // ensureReady KHÔNG được đổi `open` hay ghi cờ.
  const readyFn = provider.slice(provider.indexOf("const ensureReady"), provider.indexOf("const openAssistant"));
  assert.ok(!/open:\s*true|apDungHanhDongMo/.test(readyFn), "ensureReady phải trung lập với trạng thái mở");
  // Bản nháp không bị bất kỳ hành động mở/đóng nào xoá.
  for (const fn of [openFn, fullFn, readyFn]) assert.ok(!/draft:/.test(fn));

  // Di động: lối vào Story chuẩn bị hội thoại rồi sang /assistant, không bật panel nổi.
  const entry = boChuThich(read("components/ai/AskAiAssistantStoryEntry.tsx"));
  const nhanhNho = entry.slice(entry.indexOf("matchMedia(MAN_HINH_NHO)"), entry.indexOf("} else {"));
  assert.match(nhanhNho, /await ensureReady\(opts\)/);
  assert.match(nhanhNho, /router\.push\("\/assistant"\)/);
  assert.ok(!/openAssistant/.test(nhanhNho));
});

test("RG-B. Story mode trung thực: nhãn beta + nói rõ chỉ đọc chương đang mở", () => {
  const types = read("lib/ai/types.ts");
  assert.match(types, /story: "Truyện \(beta\)"/);
  const conv = read("components/ai/AiConversation.tsx");
  assert.match(conv, /chỉ đọc phần đầu của chương bạn đang mở/);
  assert.match(conv, /chưa đọc được các chương khác hay cả bộ truyện/);
  // Không nơi nào trong UI AI hứa "cả bộ truyện"/"toàn bộ truyện" như một khả năng.
  for (const f of readdirSync(`${SRC}components/ai`)) {
    if (!f.endsWith(".tsx")) continue;
    const s = read(`components/ai/${f}`);
    assert.ok(!/hiểu (cả|toàn bộ) (bộ )?truyện/i.test(s), `${f} hứa quá khả năng Story mode`);
  }
});

test("RG-QA. Lỗi HTTP /api/ai/* dạng FastAPI {detail:{code,...}} đọc đúng mã (429 hết ngân sách/RPM không còn thành 'gián đoạn')", async () => {
  const { docLoiApi } = await import("../src/lib/ai/loiApi.ts");
  const hetNganSach = docLoiApi(
    { detail: { code: "ai_budget_exhausted", message: "Đã dùng hết 400 token hôm nay.", reset_at: "2026-10-01T00:00:00+00:00" } },
    429, "mặc định");
  assert.equal(hetNganSach.code, "ai_budget_exhausted");
  assert.equal(hetNganSach.resetAt, "2026-10-01T00:00:00+00:00");
  assert.equal(hetNganSach.status, 429);
  assert.equal(docLoiApi({ detail: { code: "ai_rate_limited", message: "x" } }, 429, "m").code, "ai_rate_limited");
  assert.equal(docLoiApi({ detail: { code: "ai_busy", message: "x" } }, 503, "m").code, "ai_busy");
  // 401 của FastAPI: detail là CHUỖI.
  assert.deepEqual(docLoiApi({ detail: "Cần đăng nhập." }, 401, "m"), { message: "Cần đăng nhập.", status: 401, resetAt: null });
  // Dạng phẳng cũ + thân không phải JSON vẫn không ném.
  assert.equal(docLoiApi({ code: "ai_not_found", message: "y" }, 404, "m").code, "ai_not_found");
  assert.deepEqual(docLoiApi(null, 500, "mặc định"), { message: "mặc định", status: 500, code: undefined, resetAt: null });

  const client = read("lib/ai/client.ts");
  assert.ok(!/obj\.code/.test(client), "client.ts không còn tự đọc code ở tầng ngoài cùng");
  assert.match(client, /throw await loiTuPhanHoi\(res, "Không thể kết nối trợ lý AI\."\)/);
  const provider = read("components/ai/AiProvider.tsx");
  assert.match(provider, /e instanceof AiApiError \? e\.resetAt : null/);
});

test("RG-QA2. Back sau điều hướng cứng (bfcache) không giữ panel mở khi cờ đã xoá; bản nháp theo tab + theo người dùng", async () => {
  const { apDungHanhDongMo, openSauKhiPhucHoi, docNhap, ghiNhap, TRAN_NHAP } = await import("../src/lib/ai/phienMo.ts");
  const kho = khoGia();
  // Trang "/" có panel đang mở (ảnh chụp bfcache: open=true) -> /assistant (document khác) xoá cờ -> Back.
  apDungHanhDongMo("mo_noi", kho);
  apDungHanhDongMo("vao_toan_man", kho);
  assert.equal(openSauKhiPhucHoi(true, kho), false, "panel phải đóng khi phục hồi từ bfcache");
  // Người dùng tự mở lại rồi Back tới một trang khác -> vẫn mở (cờ còn), và KHÔNG bao giờ tự mở.
  apDungHanhDongMo("mo_noi", kho);
  assert.equal(openSauKhiPhucHoi(true, kho), true);
  assert.equal(openSauKhiPhucHoi(false, kho), false, "phục hồi không bao giờ tự mở panel");
  // Bản nháp: sống qua document khác, tách theo người dùng, có trần, xoá khi rỗng.
  ghiNhap("usr_a", "nháp của A", kho);
  assert.equal(docNhap("usr_a", kho), "nháp của A");
  assert.equal(docNhap("usr_b", kho), "", "người khác cùng tab không thấy nháp của A");
  assert.equal(docNhap(null, kho), "");
  ghiNhap("usr_a", "x".repeat(TRAN_NHAP + 50), kho);
  assert.equal(docNhap("usr_a", kho).length, TRAN_NHAP);
  ghiNhap("usr_a", "", kho);
  assert.equal(docNhap("usr_a", kho), "");

  const provider = read("components/ai/AiProvider.tsx");
  assert.match(provider, /addEventListener\("pageshow", khiHien\)/);
  assert.match(provider, /openSauKhiPhucHoi\(s\.open\)/);
  assert.match(provider, /ghiNhap\(uidRef\.current, text\)/);
});

test("RG-QA3. Không tràn ngang ở 1024px/390px với font hệ thống rộng: icon nav ẩn ≤1100px, nhãn chữ giữ nguyên", () => {
  const css = read("app/globals.css");
  assert.match(css, /@media \(max-width: 1100px\) \{\s*\.nav-link-icon \{ display: none; \}/);
  const nav = read("components/NavAuth.tsx");
  assert.match(nav, /<FanficIcon name=\{link\.icon\} size=\{18\} className="nav-link-icon" \/>/);
});

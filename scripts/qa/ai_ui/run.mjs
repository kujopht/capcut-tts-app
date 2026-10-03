/**
 * QA giao diện Trợ lý AI bằng Chrome headless THẬT (CDP) trên harness (`harness/`): đo bố cục ở nhiều cỡ màn hình và chạy
 * các luồng người dùng (gửi, dừng, tạo lại, hết lượt, đổi tài khoản, focus, giảm chuyển động…) với máy chủ giả.
 *
 *   node scripts/qa/ai_ui/run.mjs [--only <regex>] [--shots <thư mục>] [--json <tệp>]
 *
 * Chrome chạy với --user-data-dir tạm RIÊNG (không đụng cửa sổ Chrome của người dùng), mỗi viewport một browser context mới.
 * Mã thoát 1 nếu có kiểm tra FAIL. Mức "INFO" chỉ để báo số đo, không làm hỏng lần chạy.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildHarness } from "./build.mjs";
import { ONLY, SHOTS, JSON_OUT, CHROME, results, record, check, info, sleep, serve, launchChrome, Cdp, Page, openPage } from "./lib.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));

// ----------------------------------------------------------------------------------------- dữ liệu thử
const LONG_WORD = "Siêuthanhlịchsửvĩđạiphithườngkhôngthểchiara".repeat(4);
const URL_LONG = "https://example.com/rất/dài/" + "a".repeat(140);
const MD_BODY = [
  "**Tiêu đề đậm** và `mã_nội_tuyến_rất_dài_không_có_khoảng_trắng_nào_cả_" + "x".repeat(70) + "`",
  "- mục một\n- mục hai " + LONG_WORD,
  "1. bước một\n2. bước hai",
  "```js\nconst a = 1; // " + "dòng mã rất dài ".repeat(12) + "\n```",
  URL_LONG,
  "Một đoạn văn thường khá dài để kiểm tra việc xuống dòng tự nhiên của tiếng Việt có dấu trong một khung hẹp 320px.",
].join("\n\n");

const VIEWPORTS = [
  { name: "320", width: 320, height: 568, mobile: true },
  { name: "360", width: 360, height: 740, mobile: true },
  { name: "390", width: 390, height: 844, mobile: true },
  { name: "430", width: 430, height: 932, mobile: true },
  { name: "tablet", width: 768, height: 1024, mobile: true },
  { name: "desktop", width: 1280, height: 800, mobile: false },
  { name: "1024", width: 1024, height: 768, mobile: false },
];
const isPageView = (vp) => vp.width < 1024;

// ----------------------------------------------------------------------------------------- đo bố cục (chạy trong trang)
const MEASURE = `(() => {
  const root = document.querySelector('.ai-trang, .ai-panel');
  const vw = innerWidth, vh = innerHeight;
  const out = { vw, vh, docScrollW: document.documentElement.scrollWidth, hasRoot: !!root, overflow: [], controls: [] };
  if (!root) return out;
  const vis = (el) => { const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const name = (el) => (el.getAttribute('aria-label') || (el.className && el.className.toString().split(' ')[0]) || el.tagName).slice(0, 36);
  for (const el of root.querySelectorAll('*')) {
    if (!vis(el)) continue;
    // Bên trong khối mã (\`pre.ai-md-code\`, tự cuộn ngang trong chính nó) phần tử con DÀI HƠN khung là chủ ý — chính khối \`pre\` vẫn bị kiểm.
    if (!el.matches('pre.ai-md-code') && el.closest('pre.ai-md-code')) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) out.overflow.push(name(el) + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
  }
  // Vùng chạm HIỆU DỤNG: kích thước phần tử + phần ::after mở rộng (inset âm), hoặc cả <label> bao ô tích.
  const eff = (el, r) => {
    let w = r.width, h = r.height;
    const a = getComputedStyle(el, '::after');
    if (a && a.content !== 'none' && a.position === 'absolute') {
      const l = parseFloat(a.left), rr = parseFloat(a.right), t = parseFloat(a.top), b = parseFloat(a.bottom);
      if (![l, rr, t, b].some(Number.isNaN)) { w = w - l - rr; h = h - t - b; }
    }
    if (el.matches('input[type=checkbox],input[type=radio]')) { const lab = el.closest('label'); if (lab) { const lr = lab.getBoundingClientRect(); w = Math.max(w, lr.width); h = Math.max(h, lr.height); } }
    return [Math.round(w), Math.round(h)];
  };
  for (const el of root.querySelectorAll('button, select, textarea, input, a[href], [role=menuitem]')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    const [ew, eh] = eff(el, r);
    out.controls.push({ name: name(el), w: ew, h: eh, inView: r.left >= -1 && r.right <= vw + 1 && r.top >= -1 && r.bottom <= vh + 1 });
  }
  const ta = root.querySelector('textarea.ai-o');
  if (ta) { const cs = getComputedStyle(ta); out.textareaFont = parseFloat(cs.fontSize); const r = ta.getBoundingClientRect(); out.composer = { top: Math.round(r.top), bottom: Math.round(r.bottom), inView: r.top >= 0 && r.bottom <= vh + 1 }; }
  const sel = root.querySelector('select.ai-mode'); if (sel) out.selectFont = parseFloat(getComputedStyle(sel).fontSize);
  const list = root.querySelector('.ai-panel-tin'); if (list) out.list = { client: list.clientHeight, scroll: list.scrollHeight, top: Math.round(list.getBoundingClientRect().top) };
  return out;
})()`;

async function measure(page, vp, label, { strictTouch = false } = {}) {
  const m = await page.ev(MEASURE);
  check(`${label}: có khung AI`, vp.name, m.hasRoot, "không thấy .ai-trang/.ai-panel");
  if (!m.hasRoot) return m;
  check(`${label}: không tràn ngang (trang)`, vp.name, m.docScrollW <= m.vw, `scrollWidth=${m.docScrollW} > ${m.vw}`);
  check(`${label}: không phần tử nào vượt khung nhìn`, vp.name, m.overflow.length === 0, m.overflow.slice(0, 5).join("; "));
  const outside = m.controls.filter((c) => !c.inView);
  check(`${label}: mọi nút/ô nhập nằm trong khung nhìn`, vp.name, outside.length === 0, outside.map((c) => c.name).join(", "));
  if (m.composer) check(`${label}: ô soạn thấy được`, vp.name, m.composer.inView, JSON.stringify(m.composer));
  if (isPageView(vp)) {
    const small = m.controls.filter((c) => Math.min(c.w, c.h) < 44);
    const tiny = m.controls.filter((c) => Math.min(c.w, c.h) < 24);
    check(`${label}: không điều khiển nào nhỏ hơn 24px`, vp.name, tiny.length === 0, tiny.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    if (strictTouch) check(`${label}: điều khiển chạm >= 44px`, vp.name, small.length === 0, small.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    else if (small.length) info(`${label}: điều khiển < 44px`, vp.name, small.map((c) => `${c.name} ${c.w}x${c.h}`).join(", "));
    if (m.textareaFont !== undefined) check(`${label}: ô soạn >= 16px (iOS không tự phóng to)`, vp.name, m.textareaFont >= 16, `font=${m.textareaFont}px`);
    if (m.selectFont !== undefined) check(`${label}: ô chọn chế độ >= 16px`, vp.name, m.selectFont >= 16, `font=${m.selectFont}px`);
  }
  return m;
}

// ----------------------------------------------------------------------------------------- thao tác
async function login(page, user) {
  await page.ev(`__qa.setUser(${JSON.stringify(user)})`);
}
async function openDesktop(page) {
  await page.wait("document.querySelector('.ai-launcher')", 8000, "nút nổi");
  await page.click(".ai-launcher");
  await page.wait("document.querySelector('.ai-panel')", 4000, "panel");
}
async function ready(page, vp, user = "alice") {
  await login(page, user);
  if (isPageView(vp)) await page.wait("document.querySelector('.ai-trang textarea.ai-o')", 8000, "ô soạn");
  else {
    await openDesktop(page);
    await page.wait("document.querySelector('.ai-panel textarea.ai-o')", 8000, "ô soạn");
  }
}
async function send(page, text, { script, wait = "done" } = {}) {
  if (script) await page.ev(`__qa.script.push(${JSON.stringify(script)})`);
  const before = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type(text);
  await page.key("Enter");
  if (wait === "done") {
    try {
      // `inflight === 0`: máy chủ giả đã đóng luồng. Chỉ nhìn "đã có request và chưa thấy nút Dừng" là sai: ngay sau khi
      // gửi, React chưa kịp vẽ `streaming: true` nên nút Dừng chưa hiện — kịch bản sẽ chạy tiếp khi luồng còn đang chạy.
      await page.wait(`__qa.count('/messages') > ${before} && __qa.inflight === 0 && !document.querySelector('.ai-nut-dung')`, 15000, "xong lượt gửi");
    } catch (e) {
      const st = await page.ev(`({ requests: __qa.count('/messages'), dung: !!document.querySelector('.ai-nut-dung'), nhap: document.querySelector('textarea.ai-o')?.value ?? null, khoa: !!document.querySelector('textarea.ai-o')?.disabled, loi: document.querySelector('.ai-loi')?.innerText ?? null, hanMuc: document.querySelector('.ai-usage')?.innerText ?? null, daDung: __qa.usedBy(__qa.calls.length ? __qa.calls[__qa.calls.length - 1].user : ''), cuoi: __qa.calls.slice(-4).map((c) => c.method + ' ' + c.path.replace('/api/ai/', '')) })`).catch(() => ({}));
      throw new Error(`${e.message} — gửi "${text.slice(0, 24)}": trước=${before}, ${JSON.stringify(st)}`);
    }
    await sleep(60);
  }
}

// ----------------------------------------------------------------------------------------- các kịch bản
const SCENARIOS = [];
const scenario = (id, fn, { viewports = VIEWPORTS, reducedMotion = false } = {}) => SCENARIOS.push({ id, fn, viewports, reducedMotion });

scenario("layout", async (page, vp) => {
  await ready(page, vp);
  await page.wait("document.querySelector('.ai-trong')", 5000, "trạng thái rỗng");
  await measure(page, vp, "rỗng");
  await page.shot(`${vp.name}-01-empty`);

  await send(page, "Xin chào " + LONG_WORD + " " + URL_LONG, { script: { kind: "text", text: MD_BODY, chunk: 40, delay: 5 } });
  await measure(page, vp, "hội thoại dài (từ/URL/mã dài)");
  const code = await page.ev(`(() => { const p = document.querySelector('pre.ai-md-code'); if (!p) return null; const b = p.closest('.ai-bong').getBoundingClientRect(), r = p.getBoundingClientRect(); return { scrolls: p.scrollWidth > p.clientWidth, inBubble: r.right <= b.right + 1 && r.left >= b.left - 1, inView: r.right <= innerWidth + 1 && r.left >= -1, tab: p.tabIndex, fence: document.querySelector('.ai-bong-assistant')?.innerText.includes('\`\`\`') }; })()`);
  check("khối mã rào ba dấu huyền: dựng thành <pre>, cuộn ngang trong chính nó, không tràn bong bóng/khung, bàn phím cuộn được, không còn dấu rào thô", vp.name,
    !!code && code.scrolls && code.inBubble && code.inView && code.tab === 0 && !code.fence, JSON.stringify(code));
  await page.shot(`${vp.name}-02-convo`);

  // hết lượt: dùng hết 5 lượt rồi xem khung báo
  await page.ev(`__qa.setUsed('alice', 4)`);
  await send(page, "lượt cuối", { script: { kind: "ok", words: 8, delay: 5 } });
  await page.wait("document.querySelector('textarea.ai-o').disabled", 4000, "ô soạn bị khoá khi hết lượt");
  await measure(page, vp, "hết lượt");
  await page.shot(`${vp.name}-03-exhausted`);
});

scenario("layout-states", async (page, vp) => {
  await ready(page, vp, "carol");
  const longTitle = "Một cuộc trò chuyện có tiêu đề rất rất dài " + LONG_WORD;
  await page.ev(`__qa.seed('carol', { title: ${JSON.stringify(longTitle)}, messages: [{ role: 'user', content: 'a' }, { role: 'assistant', content: 'b' }] })`);
  for (let i = 0; i < 6; i += 1) await page.ev(`__qa.seed('carol', { title: 'Hội thoại số ${i + 1}', messages: [] })`);
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "danh sách lịch sử");
  await sleep(150);
  await measure(page, vp, "lịch sử mở (tiêu đề dài)");
  await page.shot(`${vp.name}-04-history`);
  await page.click("button[aria-label='Lịch sử hội thoại']");

  await page.click("button[aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat')", 3000, "popover cài đặt");
  await measure(page, vp, "popover cài đặt");
  await page.shot(`${vp.name}-05-settings`);
  await page.click("button[aria-label='Cài đặt ký ức']");

  // lỗi: bị từ chối trước khi nhận => "Chưa gửi" + khung báo
  await send(page, "tin bị từ chối " + LONG_WORD, { script: { kind: "http", status: 503, body: { detail: { code: "ai_busy", message: "Máy chủ đang bận — vui lòng thử lại sau ít giây." } } } });
  await page.wait("document.querySelector('.ai-loi')", 4000, "khung báo lỗi");
  await measure(page, vp, "lỗi + 'Chưa gửi'");
  check("tin bị từ chối hiện 'Chưa gửi'", vp.name, await page.ev(`!!document.querySelector('.ai-bong-chua-gui-nhan')`));
  await page.shot(`${vp.name}-06-notsent`);

  // chế độ viết
  await page.ev(`(() => { const s = document.querySelector('select.ai-mode'); if (s && !s.disabled) { const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, 'writer'); s.dispatchEvent(new Event('change', { bubbles: true })); } })()`);
  await sleep(150);
  await measure(page, vp, "chế độ viết");
  await page.shot(`${vp.name}-07-writer`);
});

scenario("behaviour-send-stop-regenerate", async (page, vp) => {
  await ready(page, vp, "dave");
  const calls0 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.key("Enter");
  await page.type("   ");
  await page.key("Enter");
  check("Enter với ô trống/khoảng trắng không gửi", vp.name, (await page.ev(`__qa.count('/messages')`)) === calls0);
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(ta, ''); ta.dispatchEvent(new Event('input', { bubbles: true })); ta.focus(); })()`);

  await page.type("dòng một");
  await page.key("Enter", { shift: true });
  await page.type("dòng hai");
  const draft = await page.ev(`document.querySelector('textarea.ai-o').value`);
  check("Shift+Enter xuống dòng, không gửi", vp.name, draft === "dòng một\ndòng hai" && (await page.ev(`__qa.count('/messages')`)) === calls0, JSON.stringify(draft));

  // IME: Enter khi đang gõ dấu (isComposing) KHÔNG được gửi
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, isComposing: true })); })()`);
  await sleep(80);
  check("Enter trong lúc IME đang soạn (isComposing) không gửi", vp.name, (await page.ev(`__qa.count('/messages')`)) === calls0, "tin bị gửi giữa chừng khi đang gõ dấu");

  await page.key("Enter");
  await page.wait(`__qa.count('/messages') > ${calls0} && !document.querySelector('.ai-nut-dung')`, 12000, "gửi xong");
  check("gửi bằng Enter: ô soạn được xoá", vp.name, (await page.ev(`document.querySelector('textarea.ai-o').value`)) === "");
  const bubbles = await page.ev(`[...document.querySelectorAll('.ai-bong')].map((b) => b.className.includes('ai-bong-user') ? 'U' : 'A').join('')`);
  check("đúng một lượt user + một trả lời", vp.name, bubbles === "UA", bubbles);

  // Tạo lại
  await page.click(".ai-nut-tao-lai");
  await page.wait(`!document.querySelector('.ai-nut-dung') && document.querySelector('.ai-nut-tao-lai')`, 12000, "tạo lại xong");
  const assistants = await page.ev(`document.querySelectorAll('.ai-bong-assistant').length`);
  check("Tạo lại thay câu trả lời cũ (chỉ còn 1 bong bóng trợ lý)", vp.name, assistants === 1, `assistants=${assistants}`);

  // Dừng giữa chừng
  await page.ev(`__qa.script.push({ kind: 'ok', words: 400, delay: 30 })`);
  await page.focus("textarea.ai-o");
  await page.type("trả lời thật dài");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "nút Dừng");
  await page.wait("document.querySelectorAll('.ai-bong-assistant').length >= 1 && document.body.innerText.includes('xin chào')", 6000, "đã có chữ");
  await page.shot(`${vp.name}-08-streaming`);
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 4000, "dừng xong");
  check("Dừng: hiện 'Đã dừng' và ô soạn dùng lại được", vp.name, (await page.ev(`document.body.innerText.includes('Đã dừng')`)) && !(await page.ev(`document.querySelector('textarea.ai-o').disabled`)));
  const stillHasSend = await page.ev(`!!document.querySelector('.ai-nut-gui')`);
  check("Dừng: nút Gửi quay lại", vp.name, stillHasSend);
});

scenario("behaviour-quota-and-errors", async (page, vp) => {
  await ready(page, vp, "erin");
  // máy chủ từ chối (429 user) dù giao diện chưa biết: "Chưa gửi" + khung báo + KHÔNG có % toàn cục
  await page.ev(`__qa.setUsed('erin', 5)`);
  await send(page, "gửi khi đã hết", { wait: "none" });
  await page.wait("document.querySelector('.ai-loi')", 6000, "khung báo hết lượt");
  const banner = await page.ev(`document.querySelector('.ai-loi').innerText`);
  check("báo hết lượt của CHÍNH người dùng, kèm giờ làm mới", vp.name, /hết lượt/i.test(banner) && /làm mới|lúc/i.test(banner), banner);
  check("không có phần trăm/dung lượng toàn site trong giao diện", vp.name, !/\d+\s?%/.test(await page.ev(`document.querySelector('.ai-trang, .ai-panel').innerText`)));
  check("tin hiện 'Chưa gửi' (không trông như đã gửi)", vp.name, await page.ev(`!!document.querySelector('.ai-bong-chua-gui-nhan')`));
  check("ô soạn bị khoá, không còn mời 'Tạo lại'", vp.name, (await page.ev(`document.querySelector('textarea.ai-o').disabled`)) && !(await page.ev(`!!document.querySelector('.ai-nut-tao-lai')`)));

  // hết công suất chung (scope global) giữa chừng: nói rõ không phải lỗi của người dùng
  await page.ev(`__qa.setUsed('erin', 0)`);
  await page.click("button[aria-label='Hội thoại mới']");
  await sleep(200);
  await login(page, "frank");
  if (!isPageView(vp)) await openDesktop(page); // người mới đăng nhập: panel nổi bắt đầu ở trạng thái đóng
  await page.wait("document.querySelector('textarea.ai-o')", 5000, "ô soạn của frank");
  await send(page, "hỏi", { script: { kind: "sse_error", code: "ai_budget_exhausted", scope: "global" } });
  await page.wait("document.querySelector('.ai-loi')", 5000, "khung báo global");
  const g = await page.ev(`document.querySelector('.ai-loi').innerText`);
  check("hết công suất chung: không đổ lỗi cho người dùng", vp.name, /không phải|công suất|hệ thống|chung/i.test(g), g);
  await send(page, "hỏi nữa", { script: { kind: "sse_error", code: "ai_busy" } });
  const b = await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`);
  check("ai_busy hiện 'đang bận'", vp.name, /bận/i.test(b), b);
});

scenario("behaviour-entry-visibility", async (page, vp) => {
  // Khách: không lối vào, KHÔNG một request /api/ai/* nào (idle zero mạng) — kể cả /api/ai/access.
  await sleep(500);
  check("khách: không nút mở / ô soạn AI", vp.name, !(await page.ev(`!!document.querySelector('.ai-launcher, textarea.ai-o')`)));
  check("khách: 0 request /api/ai/*", vp.name, (await page.ev(`__qa.calls.length`)) === 0, `calls=${await page.ev("__qa.calls.length")}`);
  if (isPageView(vp)) check("khách trên /assistant: mời đăng nhập, không có ô soạn", vp.name, /Đăng nhập/.test(await page.ev(`document.body.innerText`)));

  // Người NGOÀI khán giả: máy chủ nói eligible:false -> không nút mở; /assistant báo chưa khả dụng, không ô soạn.
  await login(page, "outsider1");
  await sleep(700);
  check("ngoài khán giả: không nút mở", vp.name, !(await page.ev(`!!document.querySelector('.ai-launcher')`)));
  if (isPageView(vp)) {
    await page.wait("/chưa khả dụng/i.test(document.body.innerText)", 5000, "thông báo chưa khả dụng");
    check("ngoài khán giả trên /assistant: không ô soạn", vp.name, !(await page.ev(`!!document.querySelector('textarea.ai-o')`)));
  }
  const rapKhac = await page.ev(`__qa.calls.filter((c) => !c.path.endsWith('/access') && !c.path.endsWith('/availability')).length`);
  check("ngoài khán giả: không gọi route nào ngoài access/availability", vp.name, rapKhac === 0, `calls=${rapKhac}`);

  // Công tắc khẩn cấp BẬT trong lúc người dùng đang mở panel: lượt gửi bị 503 -> 'Chưa gửi' + báo lỗi rõ ràng.
  await login(page, "tho");
  if (!isPageView(vp)) await openDesktop(page);
  await page.wait("document.querySelector('textarea.ai-o')", 5000, "ô soạn");
  await page.ev(`__qa.killed = true`);
  await send(page, "hỏi khi đã tắt khẩn cấp", { wait: "none" });
  await page.wait("document.querySelector('.ai-loi')", 5000, "khung báo lỗi");
  const t = await page.ev(`document.querySelector('.ai-loi').innerText`);
  check("tắt khẩn cấp giữa chừng: báo 'chưa được bật'", vp.name, /chưa được bật/i.test(t), t);
  check("tắt khẩn cấp giữa chừng: tin hiện 'Chưa gửi'", vp.name, await page.ev(`!!document.querySelector('.ai-bong-chua-gui-nhan')`));
  await page.ev(`__qa.killed = false`);
});

scenario("behaviour-double-submit", async (page, vp) => {
  await ready(page, vp, "lan");
  // Hai lần Enter CÙNG MỘT nhịp (trước khi React kịp vẽ lại `streaming: true`): chỉ một request được gửi đi.
  const before = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("gửi hai lần");
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); for (let i = 0; i < 2; i += 1) ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); })()`);
  await page.wait(`__qa.count('/messages') > ${before} && !document.querySelector('.ai-nut-dung')`, 12000, "xong lượt gửi");
  await sleep(300);
  check("Enter hai lần cùng nhịp chỉ gửi MỘT lần", vp.name, (await page.ev(`__qa.count('/messages')`)) === before + 1, `requests=${(await page.ev(`__qa.count('/messages')`)) - before}`);
  const users = await page.ev(`document.querySelectorAll('.ai-bong-user').length`);
  check("không có bong bóng người dùng bị nhân đôi", vp.name, users === 1, `users=${users}`);
  // Hai lần bấm nút Gửi cùng nhịp.
  const b2 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("bấm hai lần");
  await page.ev(`(() => { const f = document.querySelector('form.ai-panel-soan'); const btn = f.querySelector('button[type=submit]'); btn.click(); btn.click(); })()`);
  await page.wait(`__qa.count('/messages') > ${b2} && !document.querySelector('.ai-nut-dung')`, 12000, "xong lượt thứ hai");
  await sleep(300);
  check("bấm Gửi hai lần cùng nhịp chỉ gửi MỘT lần", vp.name, (await page.ev(`__qa.count('/messages')`)) === b2 + 1, `requests=${(await page.ev(`__qa.count('/messages')`)) - b2}`);

  // Gửi LIỀN ngay khi câu trả lời vừa hiện xong (người dùng đã gõ sẵn tin kế trong lúc đang stream, bấm Enter đúng khoảnh
  // khắc nút Dừng biến mất — vài ms trước khi luồng mạng đóng hẳn). Khoá chống gửi đôi KHÔNG được nuốt tin này.
  const b3 = await page.ev(`__qa.count('/messages')`);
  await page.ev(`__qa.script.push({ kind: 'ok', words: 8, delay: 40 })`);
  await page.focus("textarea.ai-o");
  await page.type("tin thứ nhất");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "đang stream");
  await page.focus("textarea.ai-o");
  await page.type("tin gửi liền");
  await page.ev(`(() => {
    const mo = new MutationObserver(() => {
      if (document.querySelector('.ai-nut-dung')) return;
      mo.disconnect();
      document.querySelector('textarea.ai-o').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    });
    mo.observe(document.body, { childList: true, subtree: true });
  })()`);
  await page.wait(`__qa.count('/messages') >= ${b3 + 2} && !document.querySelector('.ai-nut-dung')`, 12000, "cả hai lượt đã gửi");
  await sleep(300);
  check("gửi liền ngay khi câu trả lời vừa xong: tin KHÔNG bị nuốt", vp.name, (await page.ev(`__qa.count('/messages')`)) === b3 + 2 && (await page.ev(`__qa.lastContent`)) === "tin gửi liền", `requests=${(await page.ev(`__qa.count('/messages')`)) - b3}, last=${await page.ev("__qa.lastContent")}`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-late-transport-error", async (page, vp) => {
  await ready(page, vp, "mai");
  // Đứt mạng đúng lúc đóng luồng, SAU khi khung `done` đã tới: lượt đã xong, lỗi vận chuyển đến muộn không còn ý nghĩa. Khoá
  // gửi nhả ngay khi `done`, nên người dùng gửi tin kế được trước khi lỗi muộn ấy xảy ra — lỗi muộn của lượt CŨ không được tắt
  // "đang trả lời" của lượt MỚI, không được hiện biểu ngữ lỗi, không được đánh dấu "Chưa gửi" lên tin đã được trả lời.
  const B = "đây là câu trả lời dài của lượt thứ hai, phải hiện đủ từ đầu đến cuối dù lượt trước đứt mạng muộn";
  await page.ev(`__qa.failAfterDone = true; __qa.closeDelayMs = 150; __qa.script.push({ kind: 'ok', words: 6, delay: 20 }, { kind: 'text', text: ${JSON.stringify(B)}, chunk: 4, delay: 30 })`);
  const b0 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("lượt thứ nhất");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "đang stream");
  await page.focus("textarea.ai-o");
  await page.type("lượt thứ hai");
  // Bấm Enter đúng khoảnh khắc nút Dừng biến mất (lượt 1 vừa xong về mặt logic; luồng mạng của nó còn mở thêm 150ms).
  await page.ev(`(() => {
    const mo = new MutationObserver(() => {
      if (document.querySelector('.ai-nut-dung')) return;
      mo.disconnect();
      document.querySelector('textarea.ai-o').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    });
    mo.observe(document.body, { childList: true, subtree: true });
  })()`);
  await page.wait("__qa.lateErrors >= 1", 6000, "lỗi mạng muộn của lượt thứ nhất");
  await sleep(100);
  const giua = await page.ev(`({ dung: !!document.querySelector('.ai-nut-dung'), inflight: __qa.inflight, loi: document.querySelector('.ai-loi')?.innerText ?? null, chuaGui: !!document.querySelector('.ai-bong-chua-gui-nhan') })`);
  check("lỗi mạng muộn của lượt cũ: lượt mới vẫn 'đang trả lời' (nút Dừng còn)", vp.name, giua.dung && giua.inflight === 1, JSON.stringify(giua));
  check("lỗi mạng muộn của lượt cũ: không hiện biểu ngữ lỗi / 'Chưa gửi' giữa chừng", vp.name, giua.loi === null && !giua.chuaGui, JSON.stringify(giua));
  await page.wait(`__qa.count('/messages') >= ${b0 + 2} && __qa.inflight === 0 && !document.querySelector('.ai-nut-dung')`, 12000, "cả hai lượt xong");
  await sleep(250);
  const cuoi = await page.ev(`({ loi: document.querySelector('.ai-loi')?.innerText ?? null, chuaGui: !!document.querySelector('.ai-bong-chua-gui-nhan'), tro: [...document.querySelectorAll('.ai-bong-assistant .ai-bong-noidung')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim()), nguoi: document.querySelectorAll('.ai-bong-user').length })`);
  check("lỗi mạng muộn của lượt cũ: kết thúc không có biểu ngữ lỗi, không có tin 'Chưa gửi'", vp.name, cuoi.loi === null && !cuoi.chuaGui, JSON.stringify(cuoi));
  check("lỗi mạng muộn của lượt cũ: câu trả lời lượt mới hiện ĐỦ (không bị cắt đầu)", vp.name, cuoi.tro.length === 2 && cuoi.tro[1] === B, JSON.stringify(cuoi.tro));
  check("lỗi mạng muộn của lượt cũ: đúng hai lượt người dùng", vp.name, cuoi.nguoi === 2, `nguoi=${cuoi.nguoi}`);
  await page.ev(`__qa.failAfterDone = false; __qa.closeDelayMs = 60`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-second-message-while-creating", async (page, vp) => {
  await ready(page, vp, "noi");
  // Hội thoại MỚI: lượt đầu còn chờ máy chủ tạo hội thoại (chậm), `streaming` CHƯA bật nên ô soạn vẫn mở. Tin thứ hai gõ + Enter
  // trong khoảng đó bị khoá gửi từ chối — ô soạn KHÔNG được xoá bản nháp (trước đây chữ biến mất mà không có gì báo).
  await page.ev(`__qa.createDelayMs = 1500; __qa.script.push({ kind: 'ok', words: 6, delay: 20 }, { kind: 'ok', words: 6, delay: 20 })`);
  const b0 = await page.ev(`__qa.count('/messages')`);
  await page.focus("textarea.ai-o");
  await page.type("tin thứ nhất");
  await page.key("Enter");
  await page.wait("__qa.calls.some((c) => c.method === 'POST' && c.path === '/api/ai/conversations')", 3000, "đang tạo hội thoại");
  const dangTao = await page.ev(`({ dung: !!document.querySelector('.ai-nut-dung'), msgs: __qa.count('/messages') })`);
  check("tiền đề: đang tạo hội thoại, chưa stream, ô soạn còn mở", vp.name, !dangTao.dung && dangTao.msgs === b0, JSON.stringify(dangTao));
  await page.focus("textarea.ai-o");
  await page.type("tin thứ hai");
  await page.key("Enter");
  const giu = await page.ev(`document.querySelector('textarea.ai-o').value`);
  check("khoá gửi từ chối tin thứ hai: bản nháp được GIỮ nguyên (không nuốt chữ)", vp.name, giu === "tin thứ hai", JSON.stringify(giu));
  await page.wait(`__qa.count('/messages') >= ${b0 + 1} && __qa.inflight === 0 && !document.querySelector('.ai-nut-dung')`, 15000, "lượt đầu xong");
  await sleep(150);
  check("lượt đầu vẫn đi đúng một request", vp.name, (await page.ev(`__qa.count('/messages')`)) === b0 + 1, `requests=${(await page.ev(`__qa.count('/messages')`)) - b0}`);
  await page.focus("textarea.ai-o");
  await page.key("Enter");
  await page.wait(`__qa.count('/messages') >= ${b0 + 2} && __qa.inflight === 0 && !document.querySelector('.ai-nut-dung')`, 15000, "tin thứ hai được gửi lại");
  check("gửi lại bản nháp đã giữ: tin thứ hai đến máy chủ nguyên văn", vp.name, (await page.ev(`__qa.lastContent`)) === "tin thứ hai", `last=${await page.ev("__qa.lastContent")}`);
  await page.ev(`__qa.createDelayMs = 0`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-resilience", async (page, vp) => {
  // Gieo trước khi đăng nhập: danh sách lịch sử được nạp một lần lúc mở panel.
  await page.ev(`__qa.seed('kim', { title: 'Cuộc trò chuyện cũ', messages: [{ role: 'user', content: 'câu hỏi cũ' }, { role: 'assistant', content: 'trả lời cũ' }] })`);
  await ready(page, vp, "kim");
  // Luồng đóng SẠCH giữa chừng (không done/error): giao diện KHÔNG được kẹt ở "đang trả lời".
  await send(page, "hỏi rồi bị cắt", { script: { kind: "eof", partial: "một phần câu trả lời " }, wait: "none" });
  await page.wait("!document.querySelector('.ai-nut-dung') && document.body.innerText.includes('một phần câu trả lời')", 6000, "thoát khỏi trạng thái streaming");
  check("EOF giữa chừng: ô soạn dùng lại được, nút Gửi quay lại", vp.name, !(await page.ev(`document.querySelector('textarea.ai-o').disabled`)) && !!(await page.ev(`!!document.querySelector('.ai-nut-gui')`)));
  check("EOF giữa chừng: báo 'bị ngắt giữa chừng' + giữ phần đã nhận", vp.name, /ngắt giữa chừng/i.test(await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`)));
  // "Tạo lại" sau khi mở một hội thoại cũ từ lịch sử (chưa gửi lượt nào trong phiên này) phải thật sự gửi.
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "lịch sử");
  await page.ev(`[...document.querySelectorAll('.ai-lichsu-mo')].find((b) => b.innerText.includes('Cuộc trò chuyện cũ')).click()`);
  await page.wait("document.body.innerText.includes('trả lời cũ')", 4000, "mở hội thoại cũ");
  const before = await page.ev(`__qa.count('/messages')`);
  await page.click(".ai-nut-tao-lai");
  await sleep(800);
  check("'Tạo lại' trên hội thoại vừa mở từ lịch sử gửi lại câu hỏi cũ", vp.name, (await page.ev(`__qa.count('/messages')`)) === before + 1, "bấm Tạo lại mà không có request nào");
  // Chống hồi quy (reviewer): trước đó trong PHIÊN này đã gửi "hỏi rồi bị cắt" ở một hội thoại KHÁC. "Tạo lại" ở hội thoại cũ
  // phải gửi câu hỏi CỦA hội thoại cũ vào ĐÚNG hội thoại cũ, không phải câu hỏi của hội thoại kia.
  const gui = await page.ev(`({ content: __qa.lastContent, conv: __qa.lastConv })`);
  check("'Tạo lại' gửi câu hỏi của hội thoại đang xem vào đúng hội thoại đó", vp.name, gui.content === "câu hỏi cũ" && String(gui.conv).startsWith("s"), JSON.stringify(gui));
});

scenario("behaviour-account-switch", async (page, vp) => {
  await ready(page, vp, "alice2");
  await send(page, "BÍ MẬT CỦA ALICE");
  await page.wait("document.body.innerText.includes('BÍ MẬT CỦA ALICE')", 3000, "tin của alice hiện");
  const aliceConv = await page.ev(`sessionStorage.getItem('fas.ai.conv')`);
  const callsBefore = await page.ev(`__qa.calls.length`);
  await login(page, "bob2");
  await sleep(700);
  if (!isPageView(vp)) {
    // panel nổi: bob có thể phải mở lại
    const open = await page.ev(`!!document.querySelector('.ai-panel')`);
    if (!open) await openDesktop(page).catch(() => {});
    await sleep(500);
  }
  const text = await page.ev(`document.body.innerText`);
  check("đổi tài khoản: không còn nội dung của người trước trên màn hình", vp.name, !text.includes("BÍ MẬT CỦA ALICE"), "nội dung của alice vẫn hiện cho bob");
  const bobCalls = await page.ev(`__qa.calls.slice(${callsBefore}).filter((c) => c.user === 'alice2').length`);
  check("sau khi đổi tài khoản không còn request nào mang token của người trước", vp.name, bobCalls === 0, `alice2 calls=${bobCalls}`);
  const forbidden = await page.ev(`__qa.calls.slice(${callsBefore}).filter((c) => c.user === 'bob2' && c.path.includes(${JSON.stringify(aliceConv ?? "zzz")})).length`);
  check("bob không cố mở hội thoại của alice (cờ phiên không bị thừa kế)", vp.name, forbidden === 0, `bob requested alice's conversation ${forbidden}x`);
  const errShown = await page.ev(`!!document.querySelector('.ai-loi')`);
  check("bob không thấy khung lỗi 'không thuộc về bạn'", vp.name, !errShown, await page.ev(`document.querySelector('.ai-loi')?.innerText ?? ''`));
  const quotaBob = await page.ev(`document.querySelector('.ai-usage')?.innerText ?? ''`);
  check("hạn mức hiển thị là của bob (chưa dùng), không phải của alice", vp.name, !quotaBob || /5\/5|còn 5/.test(quotaBob), quotaBob);
  // đăng xuất: không còn gì
  await login(page, null);
  await sleep(300);
  const after = await page.ev(`document.body.innerText`);
  check("đăng xuất: nội dung hội thoại biến mất", vp.name, !after.includes("BÍ MẬT CỦA ALICE") && !after.includes("xin chào"));
});

scenario("behaviour-focus", async (page, vp) => {
  await ready(page, vp, "gina");
  const inside = await page.ev(`!!document.activeElement && !!document.activeElement.closest('.ai-panel')`);
  check("mở panel: focus chuyển vào panel (ô soạn)", vp.name, inside, `activeElement=${await page.ev("document.activeElement?.tagName + '.' + document.activeElement?.className")}`);
  await page.click("button[aria-label='Đóng trợ lý AI']");
  await page.wait("!document.querySelector('.ai-panel')", 3000, "panel đóng");
  await sleep(100);
  const onLauncher = await page.ev(`document.activeElement?.classList?.contains('ai-launcher')`);
  check("đóng panel: focus trả về nút mở", vp.name, onLauncher, `activeElement=${await page.ev("document.activeElement?.tagName + '.' + document.activeElement?.className")}`);
}, { viewports: VIEWPORTS.filter((v) => !isPageView(v)) });

// Tương phản chữ (WCAG 1.4.3, ≥ 4.5:1 cho chữ thường): chữ tính từ `color` đã phân giải, nền = các lớp nền (rgba/color(srgb)) xếp chồng trong
// chuỗi tổ tiên rồi đặt lên `--bg` của trang. Kính mờ (`backdrop-filter`) coi như trong suốt phía trên nền trang tối — xấp xỉ, thiên về an toàn.
const CONTRAST = `(() => {
  const parse = (s) => {
    if (!s || s === 'transparent') return { r: 0, g: 0, b: 0, a: 0 };
    let m = s.match(/^rgba?\\(([^)]+)\\)$/);
    if (m) { const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; }
    m = s.match(/^color\\(srgb ([^)]+)\\)$/);
    if (m) { const p = m[1].split(/[\\s\\/]+/).filter(Boolean).map(Number); return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 }; }
    return null;
  };
  const over = (t, b) => { const a = t.a + b.a * (1 - t.a); return a === 0 ? { r: 0, g: 0, b: 0, a: 0 } : { r: (t.r * t.a + b.r * b.a * (1 - t.a)) / a, g: (t.g * t.a + b.g * b.a * (1 - t.a)) / a, b: (t.b * t.a + b.b * b.a * (1 - t.a)) / a, a }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const page = parse(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().startsWith('#') ? (() => { const h = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(); return 'rgb(' + parseInt(h.slice(1, 3), 16) + ',' + parseInt(h.slice(3, 5), 16) + ',' + parseInt(h.slice(5, 7), 16) + ')'; })() : 'rgb(8,9,15)');
  const bgOf = (el) => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) layers.push(c); } let acc = { ...page, a: 1 }; for (let i = layers.length - 1; i >= 0; i -= 1) acc = over(layers[i], acc); return acc; };
  const out = [];
  const targets = [['.ai-usage', 'dòng hạn mức'], ['.ai-usage-het', 'hết lượt (dòng hạn mức)'], ['.ai-loi span', 'banner lỗi'], ['.ai-bong-user', 'bong bóng người dùng'], ['.ai-bong-assistant .ai-bong-noidung', 'bong bóng trợ lý'],
    ['.ai-bong-ghichu', 'ghi chú (Đã dừng)'], ['.ai-bong-chua-gui-nhan', 'nhãn Chưa gửi'], ['.ai-trong .hint', 'câu trạng thái rỗng'], ['.ai-bong-rong', 'bong bóng rỗng (Đã dừng/lỗi)'],
    ['.ai-mode', 'ô chọn chế độ'], ['.ai-nut-tao-lai', 'nút Tạo lại'], ['.ai-panel-ten, .ai-trang .ai-panel-ten', 'tên trợ lý'], ['.ai-badge-ephemeral', 'huy hiệu không lưu'], ['.ai-lichsu-mo', 'mục lịch sử'], ['.ai-md-code', 'khối mã'], ['.ai-caidat-dong span', 'dòng cài đặt']];
  for (const [sel, name] of targets) {
    const el = document.querySelector(sel); if (!el) continue;
    const cs = getComputedStyle(el); const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el); const f = over(fg, bg);
    const L1 = lum(f), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    out.push({ name, sel, ratio: Math.round(ratio * 100) / 100, size: parseFloat(cs.fontSize) });
  }
  const ta = document.querySelector('textarea.ai-o');
  if (ta) { const ph = parse(getComputedStyle(ta, '::placeholder').color); const bg = bgOf(ta); if (ph) { const f = over(ph, bg); const L1 = lum(f), L2 = lum(bg); out.push({ name: 'placeholder ô soạn', sel: 'textarea::placeholder', ratio: Math.round(((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)) * 100) / 100, size: parseFloat(getComputedStyle(ta).fontSize) }); } }
  return out;
})()`;

scenario("a11y-contrast", async (page, vp) => {
  await ready(page, vp, "cora");
  const seen = new Map();
  const audit = async (label) => {
    for (const r of await page.ev(CONTRAST)) {
      const prev = seen.get(r.name);
      if (!prev || r.ratio < prev.ratio) seen.set(r.name, { ...r, label });
    }
  };
  await audit("rỗng");
  await send(page, "tương phản", { script: { kind: "text", text: "Một đoạn trả lời có `mã nội tuyến`.\n\n```js\nconst a = 1;\n```", chunk: 30, delay: 5 } });
  await audit("hội thoại");
  await send(page, "gây lỗi", { script: { kind: "sse_error", code: "ai_provider_unavailable" } });
  await audit("lỗi");
  await page.ev(`__qa.script.push({ kind: 'hang' })`);
  await page.focus("textarea.ai-o"); await page.type("dừng"); await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "Dừng");
  await page.click(".ai-nut-dung");
  await page.wait("!document.querySelector('.ai-nut-dung')", 4000, "đã dừng");
  await audit("đã dừng");
  await page.ev(`__qa.setUsed('cora', 4)`);
  await send(page, "lượt cuối", { script: { kind: "ok", words: 4 } });
  await audit("hết lượt");
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 3000, "lịch sử");
  await audit("lịch sử");
  await page.click("button[aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat')", 3000, "cài đặt");
  await audit("cài đặt");
  const rows = [...seen.values()].sort((a, b) => a.ratio - b.ratio);
  for (const r of rows) {
    const ok = r.ratio >= 4.5;
    record(`tương phản ${r.name} (${r.label}, ${r.size}px)`, vp.name, ok ? "PASS" : "FAIL", ok ? "" : `${r.ratio}:1 < 4.5:1 — ${r.sel}`);
  }
  info("tương phản thấp nhất", vp.name, rows.slice(0, 3).map((r) => `${r.name} ${r.ratio}`).join(" · "));
}, { viewports: VIEWPORTS.filter((v) => v.name === "desktop" || v.name === "390") });

scenario("behaviour-escape-close", async (page, vp) => {
  await ready(page, vp, "hana");
  // Popover cài đặt đang mở: Escape chỉ đóng MỘT lớp (popover), panel còn nguyên.
  await page.click("button[aria-label='Cài đặt ký ức']");
  await page.wait("document.querySelector('.ai-caidat')", 3000, "popover");
  await page.focus("textarea.ai-o");
  await page.key("Escape");
  await sleep(150);
  check("Escape khi popover cài đặt mở: popover đóng, panel vẫn mở", vp.name, !(await page.ev(`!!document.querySelector('.ai-caidat')`)) && (await page.ev(`!!document.querySelector('.ai-panel')`)));
  // Escape khi chỉ có panel: đóng panel và trả focus về nút mở.
  await page.focus("textarea.ai-o");
  await page.key("Escape");
  await page.wait("!document.querySelector('.ai-panel')", 3000, "panel đóng bằng Escape");
  await sleep(150);
  check("Escape: panel đóng, focus trả về nút mở", vp.name, await page.ev(`document.activeElement?.classList?.contains('ai-launcher')`), await page.ev("document.activeElement?.tagName + '.' + document.activeElement?.className"));
  // Đang gõ dấu bằng IME: Escape huỷ chữ đang soạn, KHÔNG đóng panel.
  await page.click(".ai-launcher");
  await page.wait("document.querySelector('.ai-panel textarea.ai-o')", 4000, "panel");
  await page.ev(`(() => { const ta = document.querySelector('textarea.ai-o'); ta.focus(); ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true, isComposing: true })); })()`);
  await sleep(150);
  check("Escape khi đang soạn bằng IME: panel không đóng", vp.name, await page.ev(`!!document.querySelector('.ai-panel')`));
}, { viewports: VIEWPORTS.filter((v) => !isPageView(v)) });

scenario("behaviour-composer-grow", async (page, vp) => {
  await ready(page, vp, "ivy");
  const h = () => page.ev(`(() => { const t = document.querySelector('textarea.ai-o'); return { client: t.clientHeight, offset: t.offsetHeight, scroll: t.scrollHeight, max: parseFloat(getComputedStyle(t).maxHeight) }; })()`);
  const h0 = await h();
  await page.focus("textarea.ai-o");
  await page.type("dòng một\ndòng hai\ndòng ba\ndòng bốn\ndòng năm");
  await sleep(100);
  const h1 = await h();
  check("ô soạn nhiều dòng: GIÃN cao hơn lúc rỗng (không chỉ 2 dòng)", vp.name, h1.offset > h0.offset + 10, `${h0.offset} → ${h1.offset}`);
  check("ô soạn giãn không vượt max-height", vp.name, h1.offset <= h1.max + 1, `${h1.offset} > max ${h1.max}`);
  await page.type("\n" + "dòng thêm\n".repeat(12));
  await sleep(100);
  const h2 = await h();
  check("ô soạn rất dài: dừng ở max-height rồi cuộn trong ô", vp.name, h2.offset <= h2.max + 1 && h2.scroll > h2.client, JSON.stringify(h2));
  await page.ev(`(() => { const t = document.querySelector('textarea.ai-o'); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; set.call(t, ''); t.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await sleep(100);
  const h3 = await h();
  check("xoá hết chữ: ô soạn co lại như lúc đầu", vp.name, Math.abs(h3.offset - h0.offset) <= 2, `${h0.offset} → ${h3.offset}`);
  await measure(page, vp, "ô soạn giãn");
});

scenario("behaviour-scroll-follow", async (page, vp) => {
  // Hai điều mà bài kiểm "cuộn lên thì không bị giật xuống" KHÔNG phủ (reviewer): vẫn bám đáy khi người dùng không cuộn,
  // và mở một hội thoại dài từ lịch sử thì nhảy xuống đáy; cộng với khung cao lên giữa chừng thì không mất bám đáy.
  const msgs = Array.from({ length: 30 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: `tin số ${i + 1} ` + "nội dung dài ".repeat(12) }));
  await page.ev(`__qa.seed('mai', { title: 'Hội thoại rất dài', messages: ${JSON.stringify(msgs)} })`);
  await ready(page, vp, "mai");
  const gan = `(() => { const el = document.querySelector('.ai-panel-tin'); return el.scrollHeight - el.scrollTop - el.clientHeight; })()`;
  await page.click("button[aria-label='Lịch sử hội thoại']");
  await page.wait("document.querySelector('.ai-lichsu')", 4000, "lịch sử");
  await page.ev(`[...document.querySelectorAll('.ai-lichsu-mo')].find((b) => b.innerText.includes('Hội thoại rất dài')).click()`);
  await page.wait("document.body.innerText.includes('tin số 30')", 4000, "mở hội thoại dài");
  await sleep(200);
  const khoang = await page.ev(gan);
  check("mở hội thoại dài từ lịch sử: nhảy xuống đáy", vp.name, khoang < 80, `còn cách đáy ${khoang}px`);
  await page.ev(`__qa.script.push({ kind: 'ok', words: 300, delay: 10 })`);
  await page.focus("textarea.ai-o");
  await page.type("viết dài đi");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-nut-dung')", 4000, "bắt đầu stream");
  await sleep(500);
  // Khung cao lên giữa chừng (như xoay màn hình): việc bám đáy KHÔNG được tắt.
  await page.s("Emulation.setDeviceMetricsOverride", { width: vp.width, height: vp.height + 120, deviceScaleFactor: vp.mobile ? 2 : 1, mobile: vp.mobile });
  await page.wait("!document.querySelector('.ai-nut-dung')", 20000, "stream xong");
  await sleep(150);
  const sau = await page.ev(gan);
  check("không cuộn gì + khung cao lên giữa chừng: vẫn ở đáy khi stream xong", vp.name, sau < 80, `còn cách đáy ${sau}px`);
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-scroll-anchor", async (page, vp) => {
  await ready(page, vp, "hana");
  await page.ev(`__qa.script.push({ kind: 'ok', words: 500, delay: 12 })`);
  await page.focus("textarea.ai-o");
  await page.type("viết dài");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-panel-tin').scrollHeight > document.querySelector('.ai-panel-tin').clientHeight + 200", 8000, "đủ dài để cuộn");
  await page.ev(`document.querySelector('.ai-panel-tin').scrollTop = 0`);
  await sleep(500);
  const top = await page.ev(`document.querySelector('.ai-panel-tin').scrollTop`);
  check("người dùng cuộn lên đọc trong lúc stream: khung KHÔNG bị giật xuống đáy", vp.name, top < 80, `scrollTop=${top}`);
  await page.wait("!document.querySelector('.ai-nut-dung')", 20000, "stream xong");
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)) });

scenario("behaviour-reduced-motion", async (page, vp) => {
  await ready(page, vp, "ivy");
  await page.ev(`__qa.script.push({ kind: 'hang' })`);
  await page.focus("textarea.ai-o");
  await page.type("đợi");
  await page.key("Enter");
  await page.wait("document.querySelector('.ai-dang-go')", 4000, "chấm đang gõ");
  // Hoạt ảnh THẬT SỰ chuyển động = thời lượng > 20ms (quy tắc giảm-chuyển-động toàn cục của site rút còn ~0,01ms).
  const anims = await page.ev(`document.getAnimations().filter((a) => a.playState === 'running' && a.effect?.target?.closest?.('.ai-trang, .ai-panel') && a.effect.getComputedTiming().duration > 20).map((a) => (a.animationName || a.transitionProperty || '?') + ':' + a.effect.getComputedTiming().duration)`);
  check("giảm chuyển động: không có hoạt ảnh nào đang chạy trong khung AI", vp.name, anims.length === 0, anims.slice(0, 6).join(", "));
  await page.click(".ai-nut-dung");
  if (!isPageView(vp)) {
    await page.click("button[aria-label='Đóng trợ lý AI']");
    await page.wait("document.querySelector('.ai-launcher')", 3000, "nút mở");
    const tr = await page.ev(`getComputedStyle(document.querySelector('.ai-launcher')).transitionDuration`);
    const worst = Math.max(...tr.split(",").map((x) => parseFloat(x) * (x.includes("ms") ? 0.001 : 1)));
    check("giảm chuyển động: nút mở không có transition đáng kể", vp.name, worst <= 0.02, tr);
  }
}, { viewports: VIEWPORTS.filter((v) => ["390", "desktop"].includes(v.name)), reducedMotion: true });

scenario("perf-idle-and-reopen", async (page, vp) => {
  await login(page, "jack");
  await sleep(600);
  const accessCalls = await page.ev(`__qa.count('/api/ai/access')`);
  check("khi đóng: chỉ 1 request /access, chưa gọi availability/lịch sử", vp.name, accessCalls === 1 && (await page.ev(`__qa.count('/availability')`)) === 0, `access=${accessCalls}`);
  await openDesktop(page);
  await sleep(800);
  const baseCalls = await page.ev(`__qa.calls.length`);
  await sleep(3000);
  check("panel mở nhưng rỗng: không có request nền nào trong 3 giây", vp.name, (await page.ev(`__qa.calls.length`)) === baseCalls, `+${(await page.ev(`__qa.calls.length`)) - baseCalls}`);
  await page.s("HeapProfiler.collectGarbage");
  const m0 = await page.ev(`performance.memory.usedJSHeapSize`);
  const n0 = await page.ev(`document.getElementsByTagName('*').length`);
  for (let i = 0; i < 40; i += 1) {
    await page.click("button[aria-label='Đóng trợ lý AI']");
    await page.wait("document.querySelector('.ai-launcher')", 3000, "nút mở");
    await page.click(".ai-launcher");
    await page.wait("document.querySelector('.ai-panel')", 3000, "panel");
  }
  await sleep(300);
  await page.s("HeapProfiler.collectGarbage");
  const m1 = await page.ev(`performance.memory.usedJSHeapSize`);
  const n1 = await page.ev(`document.getElementsByTagName('*').length`);
  check("mở/đóng 40 lần: số phần tử DOM không tăng", vp.name, n1 <= n0 + 2, `${n0} -> ${n1}`);
  check("mở/đóng 40 lần: heap JS tăng < 2 MB", vp.name, m1 - m0 < 2 * 1024 * 1024, `${((m1 - m0) / 1024).toFixed(0)} KB`);
  // luồng dài: không có long task đáng kể
  await page.ev(`window.__lt = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lt.push(e.duration))).observe({ entryTypes: ['longtask'] }); __qa.script.push({ kind: 'ok', words: 600, delay: 8 })`);
  await page.focus("textarea.ai-o");
  await page.type("dài");
  await page.key("Enter");
  await page.wait("!document.querySelector('.ai-nut-dung') && document.body.innerText.includes('xin chào')", 20000, "stream dài xong");
  const lt = await page.ev(`window.__lt`);
  info("long task trong stream 600 từ", vp.name, `${lt.length} cái, lớn nhất ${Math.max(0, ...lt).toFixed(0)}ms`);
  check("stream 600 từ: không có long task > 200ms", vp.name, Math.max(0, ...lt) < 200, `${Math.max(0, ...lt).toFixed(0)}ms`);
}, { viewports: VIEWPORTS.filter((v) => v.name === "desktop") });

// ----------------------------------------------------------------------------------------- chạy
async function main() {
  const out = await buildHarness();
  const { server, port } = await serve(out);
  const base = `http://127.0.0.1:${port}`;
  const chrome = await launchChrome();
  let cdp;
  try {
    cdp = await Cdp.connect(chrome.wsUrl);
    for (const sc of SCENARIOS) {
      if (ONLY && !ONLY.test(sc.id)) continue;
      for (const vp of sc.viewports) {
        if (ONLY && ONLY.test(sc.id) === false) continue;
        const page = await openPage(cdp, base, {
          width: vp.width, height: vp.height, mobile: vp.mobile, hash: isPageView(vp) ? "/assistant" : "/", reducedMotion: sc.reducedMotion,
        });
        try {
          await sc.fn(page, vp);
          const errs = page.errors.filter((e) => !/Failed to load resource|favicon|net::ERR/.test(e ?? ""));
          check(`${sc.id}: không có lỗi console`, vp.name, errs.length === 0, errs.slice(0, 2).join(" | "));
        } catch (e) {
          record(`${sc.id}: ngoại lệ trong kịch bản`, vp.name, "FAIL", String(e.message ?? e).slice(0, 300));
          await page.shot(`${vp.name}-${sc.id}-ERROR`).catch(() => {});
        } finally {
          await page.close();
        }
      }
    }
  } finally {
    try { cdp?.ws.close(); } catch { /* bỏ qua */ }
    chrome.proc.kill();
    server.close();
    await sleep(300);
    try { fs.rmSync(chrome.userDir, { recursive: true, force: true }); } catch { /* Chrome còn giữ tệp: bỏ qua */ }
  }
  if (results.length === 0) {
    console.error(ONLY ? `Không kịch bản nào khớp --only ${ONLY}` : "Không chạy được kiểm tra nào");
    process.exit(2);
  }
  const fail = results.filter((r) => r.status === "FAIL");
  console.log(`\n${results.filter((r) => r.status === "PASS").length} PASS, ${fail.length} FAIL, ${results.filter((r) => r.status === "INFO").length} INFO`);
  if (JSON_OUT) fs.writeFileSync(JSON_OUT, JSON.stringify(results, null, 2));
  process.exit(fail.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});

/**
 * Cách ly phiên của Trợ lý AI giữa các tài khoản + các sửa lỗi giao diện đo được bằng Chrome thật
 * (scripts/qa/ai_ui/run.mjs): bám đáy khi stream, IME, focus panel, ô nhập 16px trên di động…
 *
 * Hai lớp (không jsdom — quy ước của repo): hành vi THUẦN của `lib/ai/phienMo.ts` + `lib/ai/tieuDiem.ts`, và bất biến
 * tĩnh trên mã nguồn (hành vi React được kiểm bằng harness Chrome, không chạy trong CI).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pm = await import("../src/lib/ai/phienMo.ts");
const td = await import("../src/lib/ai/tieuDiem.ts");

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

function kho(init = {}) {
  const m = new Map(Object.entries(init));
  return {
    m,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => void m.set(k, String(v)),
    removeItem: (k) => void m.delete(k),
  };
}

// ---------------------------------------------------------------- cờ phiên thuộc về một người dùng

test("khách không làm thay đổi cờ phiên", () => {
  const k = kho({ [pm.CO_MO]: "1", [pm.CO_HOI_THOAI]: "c1" });
  pm.lamSachNeuDoiNguoi(null, k);
  pm.lamSachNeuDoiNguoi(undefined, k);
  pm.lamSachNeuDoiNguoi("", k);
  assert.deepEqual([...k.m.keys()].sort(), [pm.CO_HOI_THOAI, pm.CO_MO].sort());
});

test("cờ chưa có chủ (bản cũ / lần đầu): người đăng nhập nhận làm chủ và GIỮ cờ", () => {
  const k = kho({ [pm.CO_MO]: "1", [pm.CO_HOI_THOAI]: "c1" });
  assert.deepEqual(pm.khoiPhucMoChoNguoi("alice", k), { open: true, conversationId: "c1" });
  assert.equal(k.getItem(pm.CO_CHU), "alice");
});

test("đăng nhập TÀI KHOẢN KHÁC trong cùng tab không thừa kế panel đang mở hay hội thoại của người trước", () => {
  const k = kho();
  pm.khoiPhucMoChoNguoi("alice", k);
  pm.apDungHanhDongMo("mo_noi", k);
  pm.ghiPhien(pm.CO_HOI_THOAI, "conv_cua_alice", k);
  assert.deepEqual(pm.khoiPhucMoChoNguoi("alice", k), { open: true, conversationId: "conv_cua_alice" }, "alice quay lại vẫn khôi phục");
  assert.deepEqual(pm.khoiPhucMoChoNguoi("bob", k), { open: false, conversationId: null });
  assert.equal(k.getItem(pm.CO_CHU), "bob");
  assert.equal(pm.docHoiThoaiLuu("bob", k), null, "bob không nhận id hội thoại của alice");
});

test("docHoiThoaiLuu cũng kiểm chủ cờ (đường /assistant đọc cờ trước effect của Provider)", () => {
  const k = kho({ [pm.CO_CHU]: "alice", [pm.CO_HOI_THOAI]: "conv_cua_alice" });
  assert.equal(pm.docHoiThoaiLuu("alice", k), "conv_cua_alice");
  assert.equal(pm.docHoiThoaiLuu("bob", k), null);
  assert.equal(k.getItem(pm.CO_HOI_THOAI), null, "cờ của alice bị xoá hẳn");
});

test("dọn cờ không đụng bản nháp theo người dùng", () => {
  const k = kho();
  pm.khoiPhucMoChoNguoi("alice", k);
  pm.ghiNhap("alice", "dòng nháp của alice", k);
  pm.khoiPhucMoChoNguoi("bob", k);
  assert.equal(pm.docNhap("alice", k), "dòng nháp của alice");
  assert.equal(pm.docNhap("bob", k), "");
});

test("kho sessionStorage không dùng được (chế độ riêng tư) thì không ném lỗi", () => {
  assert.doesNotThrow(() => pm.lamSachNeuDoiNguoi("alice", null));
  assert.deepEqual(pm.khoiPhucMoChoNguoi("alice", null), { open: false, conversationId: null });
  assert.equal(pm.docHoiThoaiLuu("alice", null), null);
});

// ---------------------------------------------------------------- focus panel

function domGia({ panel = true, oSoan = true, khoa = false, nut = true } = {}) {
  const log = [];
  const phanTu = (ten, extra = {}) => ({ ten, focus: (o) => log.push([ten, o]), ...extra });
  const els = {
    ".ai-panel": panel ? phanTu("panel") : null,
    ".ai-panel textarea.ai-o": panel && oSoan ? phanTu("o-soan", { disabled: khoa }) : null,
    ".ai-launcher": nut ? phanTu("nut-mo") : null,
  };
  return { log, goc: { querySelector: (s) => els[s] ?? null } };
}

test("focusPanelAi: vào ô soạn; ô bị khoá (hết lượt) thì vào chính panel; không có panel thì false", () => {
  let d = domGia();
  assert.equal(td.focusPanelAi(d.goc), true);
  assert.deepEqual(d.log, [["o-soan", { preventScroll: true }]]);
  d = domGia({ khoa: true });
  assert.equal(td.focusPanelAi(d.goc), true);
  assert.deepEqual(d.log, [["panel", { preventScroll: true }]]);
  d = domGia({ panel: false });
  assert.equal(td.focusPanelAi(d.goc), false);
  assert.deepEqual(d.log, []);
  assert.equal(td.focusPanelAi(null), false);
});

test("focusNutMoAi: trả focus về nút mở khi nó có mặt", () => {
  let d = domGia();
  assert.equal(td.focusNutMoAi(d.goc), true);
  assert.deepEqual(d.log, [["nut-mo", { preventScroll: true }]]);
  d = domGia({ nut: false });
  assert.equal(td.focusNutMoAi(d.goc), false);
});

test("sauKhiVe chạy hàm được truyền vào (kể cả khi không có requestAnimationFrame)", async () => {
  let n = 0;
  td.sauKhiVe(() => { n += 1; });
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(n, 1);
});

// ---------------------------------------------------------------- bất biến tĩnh trên mã nguồn

/** Cắt ra thân các `useCallback(...)` (ngoặc cân bằng) kèm tên biến được gán. */
function cacUseCallback(src) {
  const out = [];
  const re = /const (\w+) = useCallback\(/g;
  let m;
  while ((m = re.exec(src))) {
    let depth = 1;
    let i = re.lastIndex;
    while (i < src.length && depth > 0) {
      const c = src[i];
      if (c === "(") depth += 1;
      else if (c === ")") depth -= 1;
      i += 1;
    }
    out.push({ ten: m[1], than: src.slice(re.lastIndex, i) });
  }
  return out;
}

test("AiProvider: bỏ sạch trạng thái khi đổi người dùng và huỷ luồng của người trước", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  assert.match(src, /const TRANG_THAI_DAU: AiState = \{/);
  assert.match(src, /useState<AiState>\(TRANG_THAI_DAU\)/);
  assert.match(src, /if \(uidDaThay !== uidHienTai\) \{\s*setUidDaThay\(uidHienTai\);\s*setState\(TRANG_THAI_DAU\);/);
  assert.match(src, /return \(\) => \{\s*ctrlRef\.current\?\.abort\(\);[\s\S]*?\}, \[uidHienTai\]\)/);
});

test("AiProvider: sau mỗi await không có setState thẳng — mọi cập nhật muộn đi qua giuNguoi", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  const khoi = cacUseCallback(src).filter((k) => /\bawait\b/.test(k.than));
  assert.ok(khoi.length >= 14, `chỉ tìm thấy ${khoi.length} hành động bất đồng bộ`);
  let dungGiuNguoi = 0;
  for (const k of khoi) {
    const sauAwait = k.than.slice(k.than.search(/\bawait\b/));
    // Một phản hồi muộn của người đã đăng xuất mà `setState` thẳng sẽ ghi vào màn hình của người đăng nhập sau.
    assert.doesNotMatch(sauAwait, /\bsetState\(/, `${k.ten}: setState thẳng sau await`);
    if (/giuNguoi\(\)/.test(k.than)) dungGiuNguoi += 1;
    else assert.doesNotMatch(sauAwait, /\bcn\(/, `${k.ten}: dùng cn() mà không lấy từ giuNguoi()`);
  }
  assert.ok(dungGiuNguoi >= 12, `chỉ ${dungGiuNguoi} hành động dùng giuNguoi()`);
});

test("AiProvider: cờ phiên chỉ được đọc/ghi cho đúng chủ", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  assert.match(src, /khoiPhucMoChoNguoi\(profile\.user_id\)/);
  assert.match(src, /docHoiThoaiLuu\(profile\.user_id\)/);
  assert.doesNotMatch(src, /\bdocPhien\(/, "đọc cờ phiên thô sẽ thừa kế hội thoại của người trước");
  assert.doesNotMatch(src, /\bkhoiPhucMo\(\)/);
  // id hội thoại của người vừa đăng xuất không được ghi cho người sau
  assert.match(src, /if \(cn\.conHieuLuc\(\)\) ghiPhien\(CO_HOI_THOAI, id\)/);
});

test("AiProvider: luồng đóng sạch không có done/error không được kẹt ở 'đang trả lời'; Tạo lại dùng câu hỏi trong hội thoại", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  assert.match(src, /let ketThuc = false/);
  assert.match(src, /if \(!ketThuc && cn\.conHieuLuc\(\) && !ctrl\.signal\.aborted\)/);
  assert.match(src, /code: "ai_provider_interrupted"/);
  assert.doesNotMatch(src, /lastUserTextRef/, "ref 'lượt gửi gần nhất' gửi nhầm câu hỏi của hội thoại khác sau khi chuyển hội thoại");
  assert.match(src, /find\(\(m\) => m\.role === "user" && m\.status !== "not_sent"\)\?\.content/);
});

test("AiComposer: Enter trong lúc IME đang soạn không gửi", () => {
  const src = codeOnly(read("components/ai/AiComposer.tsx"));
  const i = src.indexOf("onKeyDown");
  const kt = src.indexOf("isComposing", i);
  const gui = src.indexOf('e.key === "Enter"', i);
  assert.ok(kt > i && gui > kt, "kiểm isComposing phải đứng TRƯỚC khi xử lý Enter");
  assert.match(src, /keyCode === 229/);
});

test("AiConversation: bám đáy có điều kiện, không scrollIntoView, aria-busy khi stream", () => {
  const src = codeOnly(read("components/ai/AiConversation.tsx"));
  assert.doesNotMatch(src, /scrollIntoView/, "scrollIntoView còn cuộn cả trang phía sau và giật khung khi người dùng đang đọc");
  assert.match(src, /el\.scrollTop = el\.scrollHeight/);
  assert.match(src, /batDay\.current/);
  assert.match(src, /onScroll=\{khiCuon\}/);
  assert.match(src, /aria-busy=\{streaming\}/);
});

test("Focus panel nổi: mở -> vào panel, đóng -> về nút mở; panel có tabIndex=-1", () => {
  assert.match(codeOnly(read("components/ai/AiLauncher.tsx")), /sauKhiVe\(\(\) => focusPanelAi\(\)\)/);
  assert.match(codeOnly(read("components/ai/AskAiAssistantStoryEntry.tsx")), /sauKhiVe\(\(\) => focusPanelAi\(\)\)/);
  assert.match(codeOnly(read("components/ai/AiControls.tsx")), /sauKhiVe\(\(\) => focusNutMoAi\(\)\)/);
  assert.match(codeOnly(read("components/ai/AiPanel.tsx")), /tabIndex=\{-1\}/);
});

test("ai.css: ô nhập >= 16px và vùng chạm lớn ở khối di động (iOS tự phóng to khi focus ô < 16px)", () => {
  const css = read("components/ai/ai.css");
  const kho = css.match(/@media \(max-width: 1023px\) \{\s*\.ai-trang \.ai-panel-dau \{[\s\S]*?\n\}/);
  assert.ok(kho, "không thấy khối @media di động của /assistant");
  assert.match(kho[0], /\.ai-trang \.ai-o,[\s\S]*?font-size: 16px/);
  assert.match(kho[0], /\.ai-trang \.ai-mode \{[^}]*font-size: 16px/);
  assert.match(kho[0], /\.ai-trang \.ai-nut \{ width: 44px; height: 44px; \}/);
  assert.match(kho[0], /\.ai-trang \.ai-panel-dau \{ flex-wrap: wrap/);
});

test("useChatDockOffset: không dựng lại ResizeObserver mỗi lần DOM đổi", () => {
  const src = codeOnly(read("components/ai/useChatDockOffset.ts"));
  assert.match(src, /if \(el === dangDo && \(el === null \|\| ro !== null\)\) return;/);
});

test("AiProvider: khoá ĐỒNG BỘ chống gửi đôi trong cùng một nhịp (Enter lặp, nhấn đúp nút Gửi)", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  assert.match(src, /const dangGuiRef = useRef\(false\)/);
  assert.match(src, /if \(dangGuiRef\.current\) return;\s*dangGuiRef\.current = true;\s*try \{\s*await chayLuotGui\(text, regenerateOf\);\s*\} finally \{\s*dangGuiRef\.current = false;/);
  assert.match(src, /const sendMessage = useCallback\(\(text: string\) => guiVanBan\(text\)/);
  // đổi người dùng cũng nhả khoá (luồng cũ đã bị huỷ)
  assert.match(src, /assistantIdRef\.current = null;\s*dangGuiRef\.current = false;/);
});

test("AiProvider.ensureReady dừng khi máy chủ báo không dùng được (không nạp lịch sử vào một route chắc chắn bị từ chối)", () => {
  const src = codeOnly(read("components/ai/AiProvider.tsx"));
  const ensure = src.match(/const ensureReady = useCallback\([\s\S]*?\n {2}\);/)?.[0] ?? "";
  assert.ok(ensure, "không tìm thấy ensureReady");
  const dung = ensure.indexOf("if (!av || !av.enabled) return;");
  const lichSu = ensure.indexOf("void taiLichSu();");
  assert.ok(dung > 0 && lichSu > dung, "kiểm av.enabled phải đứng TRƯỚC khi nạp lịch sử");
});

test("AiConversation: mốc cuộn đi theo sự kiện scroll (khung cao lên thì trình duyệt tự kẹp scrollTop)", () => {
  const src = codeOnly(read("components/ai/AiConversation.tsx"));
  const khiCuon = src.match(/const khiCuon = \(\) => \{[\s\S]*?\n {2}\};/)?.[0] ?? "";
  assert.ok(khiCuon, "không tìm thấy khiCuon");
  assert.match(khiCuon, /viTriTruoc\.current = \{ top: el\.scrollTop, height: el\.scrollHeight \}/);
});

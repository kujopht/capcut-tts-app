/**
 * Quota UX của Trợ lý AI: giao diện người dùng chỉ hiện hạn mức RIÊNG của họ; lượt bị từ chối hiện "Chưa gửi".
 *
 * Hai lớp: hành vi THUẦN (gọi thẳng `lib/ai/hanMuc.ts`, `sse.ts`, `loiApi.ts`) + bất biến tĩnh trên mã nguồn
 * (không jsdom — quy ước của repo, xem ai-assistant-v1.test.mjs).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const hm = await import("../src/lib/ai/hanMuc.ts");
const { tachKhungSse, dienDichKhungAi } = await import("../src/lib/ai/sse.ts");
const { docLoiApi } = await import("../src/lib/ai/loiApi.ts");

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

const RESET = "2026-10-02T00:00:00+00:00";
const TRUOC_RESET = Date.parse("2026-10-01T16:00:00+00:00");
const SAU_RESET = Date.parse("2026-10-02T00:00:01+00:00");
const hanMuc = (o = {}) => ({
  requests_used: 0, requests_limit: 5, requests_remaining: 5, exhausted: false, reset_at: RESET, ...o,
});

// ---------------------------------------------------------------- docHanMuc

test("docHanMuc đọc đúng hình dạng mới và từ chối mọi thứ khác (không bịa 'x/y lượt' từ số token)", () => {
  assert.deepEqual(hm.docHanMuc(hanMuc({ requests_used: 3, requests_remaining: 2 })),
    hanMuc({ requests_used: 3, requests_remaining: 2 }));
  // Hình dạng CŨ của máy chủ (chỉ token): không đủ để nói về lượt.
  assert.equal(hm.docHanMuc({ used_today: 15300, limit_today: 30000, reset_at: RESET }), null);
  for (const xau of [null, undefined, 0, "x", [], {}, { requests_used: -1, exhausted: false },
    { requests_used: 1 }, { requests_used: "1", exhausted: false }, { requests_used: 1, exhausted: "false" },
    { requests_used: Number.NaN, exhausted: false }]) {
    assert.equal(hm.docHanMuc(xau), null, JSON.stringify(xau));
  }
});

test("docHanMuc: thiếu 'còn lại' thì tự tính; không trần lượt thì 'còn lại' là null", () => {
  const a = hm.docHanMuc({ requests_used: 2, requests_limit: 5, exhausted: false, reset_at: RESET });
  assert.equal(a.requests_remaining, 3);
  const b = hm.docHanMuc({ requests_used: 9, requests_limit: null, requests_remaining: 4, exhausted: false });
  assert.equal(b.requests_limit, null);
  assert.equal(b.requests_remaining, null);
  assert.equal(b.reset_at, null);
});

// ---------------------------------------------------------------- daHetLuot / nhanHanMuc

test("daHetLuot: hết lượt chỉ khoá TRƯỚC giờ làm mới; sau đó để máy chủ quyết", () => {
  assert.equal(hm.daHetLuot(hanMuc({ exhausted: true, requests_remaining: 0, requests_used: 5 }), TRUOC_RESET), true);
  assert.equal(hm.daHetLuot(hanMuc({ exhausted: true, requests_remaining: 0, requests_used: 5 }), SAU_RESET), false);
  assert.equal(hm.daHetLuot(hanMuc(), TRUOC_RESET), false);
  assert.equal(hm.daHetLuot(null), false);
  assert.equal(hm.daHetLuot(undefined), false);
  // Không có giờ làm mới + đã hết: giữ khoá (không có căn cứ để mở).
  assert.equal(hm.daHetLuot(hanMuc({ exhausted: true, reset_at: null }), SAU_RESET), true);
});

test("nhanHanMuc: số lượt còn lại + giờ làm mới của CHÍNH người dùng; không phần trăm, không token", () => {
  assert.equal(hm.nhanHanMuc(hanMuc(), "07:00", TRUOC_RESET), "Hôm nay còn 5/5 lượt hỏi · làm mới lúc 07:00");
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_used: 3, requests_remaining: 2 }), "07:00", TRUOC_RESET),
    "Hôm nay còn 2/5 lượt hỏi · làm mới lúc 07:00");
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_used: 5, requests_remaining: 0, exhausted: true }), "07:00", TRUOC_RESET),
    "Bạn đã hết lượt hỏi hôm nay (0/5). Làm mới lúc 07:00.");
  // Hết vì trần token trong khi còn lượt: vẫn nói đúng là hết (0/5), không mâu thuẫn "còn 2/5".
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_used: 3, requests_remaining: 0, exhausted: true }), "07:00", TRUOC_RESET),
    "Bạn đã hết lượt hỏi hôm nay (0/5). Làm mới lúc 07:00.");
  for (const h of [hanMuc(), hanMuc({ requests_used: 5, requests_remaining: 0, exhausted: true })]) {
    const t = hm.nhanHanMuc(h, "07:00", TRUOC_RESET);
    assert.ok(!/%|token|toàn|công suất/i.test(t), t);
  }
});

test("nhanHanMuc: không trần lượt / đã qua giờ làm mới / không có dữ liệu -> không nói gì sai", () => {
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_limit: null, requests_remaining: null }), "07:00", TRUOC_RESET), "");
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_limit: null, requests_remaining: null, exhausted: true }), "07:00", TRUOC_RESET),
    "Bạn đã hết lượt hỏi hôm nay. Làm mới lúc 07:00.");
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_used: 5, requests_remaining: 0, exhausted: true }), "07:00", SAU_RESET), "",
    "đã qua giờ làm mới: con số cũ không còn đúng");
  assert.equal(hm.nhanHanMuc(null, "07:00"), "");
  assert.equal(hm.nhanHanMuc(hanMuc({ requests_used: 5, requests_remaining: 0, exhausted: true }), "", TRUOC_RESET),
    "Bạn đã hết lượt hỏi hôm nay (0/5).");
});

test("ca 'Đã dùng 51%' cạnh 'đã hết lượt': dữ liệu toàn site không có đường nào vào dòng hạn mức", () => {
  // Máy chủ chỉ gửi hạn mức riêng; kể cả khi (giả sử) kèm thêm trường toàn cục, docHanMuc làm rơi chúng.
  const a = hm.docHanMuc({ ...hanMuc({ requests_used: 5, requests_remaining: 0, exhausted: true }),
    used_today: 15300, limit_today: 30000, global_used: 77, global_cap: 150, percent: 51 });
  assert.deepEqual(Object.keys(a).sort(), ["exhausted", "requests_limit", "requests_remaining", "requests_used", "reset_at"]);
  const t = hm.nhanHanMuc(a, "07:00", TRUOC_RESET);
  assert.ok(!/51|77|150|%/.test(t), t);
  assert.equal(t, "Bạn đã hết lượt hỏi hôm nay (0/5). Làm mới lúc 07:00.");
});

// ---------------------------------------------------------------- thông điệp theo phạm vi

test("thongDiepHetLuot: ba phạm vi, ba câu khác nhau; công suất chung nói 'không phải do bạn' và không kèm số", () => {
  const u = hm.thongDiepHetLuot("user", "07:00");
  const g = hm.thongDiepHetLuot("global", "07:00");
  const q = hm.thongDiepHetLuot("qa", "07:00");
  assert.equal(u, "Bạn đã hết lượt hỏi hôm nay. Làm mới lúc 07:00.");
  assert.match(g, /không phải do bạn/);
  assert.match(q, /QA/);
  assert.equal(new Set([u, g, q]).size, 3);
  assert.equal(hm.thongDiepHetLuot(undefined, "07:00"), u, "máy chủ cũ không gửi scope -> như lượt của bạn");
  assert.ok(!/\d/.test(hm.thongDiepHetLuot("global", "")), "không giờ thì không có chữ số nào");
  assert.ok(!/%/.test(g));
});

// ---------------------------------------------------------------- tin 'chưa gửi'

const tin = (id, role, status = "complete", content = id) => ({
  message_id: id, role, content, status, citations: [], created_at: "2026-10-01T16:00:00Z",
});

test("danhDauChuaGui chỉ đổi đúng tin người dùng đó, không đổi mảng gốc", () => {
  const goc = [tin("u1", "user"), tin("a1", "assistant"), tin("local_x", "user")];
  const sau = hm.danhDauChuaGui(goc, "local_x");
  assert.equal(sau[2].status, "not_sent");
  assert.equal(sau[2].content, "local_x");
  assert.equal(sau[0].status, "complete");
  assert.equal(sau[1].status, "complete");
  assert.equal(goc[2].status, "complete", "không đổi mảng gốc");
  // Id lạ -> không đổi gì. Tin TRỢ LÝ trùng id cũng không bị đánh dấu.
  assert.deepEqual(hm.danhDauChuaGui(goc, "khong-co"), goc);
  assert.equal(hm.danhDauChuaGui([tin("a1", "assistant")], "a1")[0].status, "complete");
});

test("boTinTraLoiCu: 'Tạo lại' chỉ bỏ câu trả lời cũ khi máy chủ ĐÃ nhận lượt mới", () => {
  const ds = [tin("u1", "user"), tin("a1", "assistant")];
  assert.equal(hm.boTinTraLoiCu(ds, undefined), ds, "không phải tạo lại -> giữ nguyên (cùng tham chiếu)");
  assert.deepEqual(hm.boTinTraLoiCu(ds, "a1").map((m) => m.message_id), ["u1"]);
  assert.deepEqual(hm.boTinTraLoiCu(ds, "khong-co").map((m) => m.message_id), ["u1", "a1"]);
});

test("apDungHetLuot: hết lượt CỦA BẠN khoá ngay; hết công suất chung / hạn mức QA thì KHÔNG đụng tới hạn mức riêng", () => {
  const av = { enabled: true, reason: null, name: "Fanfic AI", modes: ["general"], web_search: false, limits: hanMuc({ requests_used: 3, requests_remaining: 2 }) };
  const het = hm.apDungHetLuot(av, "user", RESET);
  assert.equal(het.limits.exhausted, true);
  assert.equal(het.limits.requests_remaining, 0);
  assert.equal(het.limits.requests_limit, 5);
  assert.equal(het.limits.requests_used, 3);
  assert.equal(hm.daHetLuot(het.limits, TRUOC_RESET), true);
  assert.equal(hm.apDungHetLuot(av, undefined, RESET).limits.exhausted, true, "scope thiếu (máy chủ cũ) = lượt của bạn");
  assert.equal(hm.apDungHetLuot(av, "global", RESET), av, "công suất chung: hạn mức riêng nguyên vẹn");
  assert.equal(hm.apDungHetLuot(av, "qa", RESET), av);
  assert.equal(hm.apDungHetLuot(null, "user", RESET), null);
  assert.equal(hm.apDungHetLuot(false, "user", RESET), false);
  assert.equal(av.limits.exhausted, false, "không đổi đối tượng gốc");
  // Chưa có `limits` (chưa biết trần): vẫn khoá được, không bịa 'x/y'.
  const khong = hm.apDungHetLuot({ ...av, limits: undefined }, "user", RESET);
  assert.equal(khong.limits.requests_limit, null);
  assert.equal(khong.limits.exhausted, true);
  assert.equal(hm.nhanHanMuc(khong.limits, "07:00", TRUOC_RESET), "Bạn đã hết lượt hỏi hôm nay. Làm mới lúc 07:00.");
});

test("kịch bản cả luồng: tin bị từ chối vì hết lượt -> 'Chưa gửi', ô soạn khoá, câu trả lời cũ còn nguyên", () => {
  const tin1 = tin("u1", "user"); const tra1 = tin("a1", "assistant"); const moi = tin("local_k", "user", "complete", "câu mới");
  let messages = [tin1, tra1, moi]; // tin tạm đã thêm lạc quan, status "complete"
  assert.equal(moi.status, "complete");
  // máy chủ trả 429 ai_budget_exhausted scope user, không có `meta`
  messages = hm.danhDauChuaGui(messages, "local_k");
  const av = hm.apDungHetLuot({ enabled: true, reason: null, name: "x", modes: [], web_search: false, limits: hanMuc({ requests_used: 5, requests_remaining: 0 }) }, "user", RESET);
  assert.deepEqual(messages.map((m) => m.status), ["complete", "complete", "not_sent"]);
  assert.equal(messages[1].content, "a1");
  assert.equal(hm.daHetLuot(av.limits, TRUOC_RESET), true);
  assert.equal(hm.nhanHanMuc(av.limits, "07:00", TRUOC_RESET), "Bạn đã hết lượt hỏi hôm nay (0/5). Làm mới lúc 07:00.");
});

test("docPhamVi chỉ nhận ba giá trị hợp lệ", () => {
  for (const v of ["user", "global", "qa"]) assert.equal(hm.docPhamVi(v), v);
  for (const v of ["admin", "", null, undefined, 1, {}]) assert.equal(hm.docPhamVi(v), undefined);
});

// ---------------------------------------------------------------- đọc lỗi + SSE

test("docLoiApi mang `scope` của ai_budget_exhausted; mọi lỗi khác không có khoá scope", () => {
  const u = docLoiApi({ detail: { code: "ai_budget_exhausted", message: "m", reset_at: RESET, scope: "user" } }, 429, "d");
  assert.equal(u.scope, "user");
  assert.equal(docLoiApi({ detail: { code: "ai_budget_exhausted", scope: "global" } }, 429, "d").scope, "global");
  assert.equal(docLoiApi({ detail: { code: "ai_budget_exhausted", scope: "bậy" } }, 429, "d").scope, undefined);
  assert.ok(!("scope" in docLoiApi({ detail: { code: "ai_busy", message: "x" } }, 503, "d")));
  assert.ok(!("scope" in docLoiApi({ detail: "Cần đăng nhập." }, 401, "d")));
});

test("SSE: `usage` mang hạn mức riêng + làn; `error` mang scope", () => {
  const raw = 'event: usage\ndata: {"input_tokens":10,"output_tokens":5,"used_today":15,"limit_today":30000,"lane":"qa",'
    + '"allowance":{"requests_used":2,"requests_limit":20,"requests_remaining":18,"exhausted":false,"reset_at":"' + RESET + '"}}\n\n'
    + 'event: usage\ndata: {"input_tokens":1,"output_tokens":1,"used_today":2,"limit_today":30000}\n\n'
    + 'event: error\ndata: {"code":"ai_budget_exhausted","message":"m","scope":"global","reset_at":"' + RESET + '"}\n\n';
  const evs = tachKhungSse(raw).khung.map(dienDichKhungAi);
  assert.equal(evs[0].lane, "qa");
  assert.deepEqual(hm.docHanMuc(evs[0].allowance), hanMuc({ requests_used: 2, requests_limit: 20, requests_remaining: 18 }));
  assert.equal(evs[1].lane, "user", "thiếu lane (máy chủ cũ) = user");
  assert.equal(evs[1].allowance, null);
  assert.equal(evs[2].scope, "global");
  assert.equal(evs[2].reset_at, RESET);
});

// ---------------------------------------------------------------- bất biến tĩnh

test("giao diện người dùng không còn đường nào hiện phần trăm / token / mức dùng toàn site", () => {
  const tep = [];
  const duyet = (dir) => {
    for (const ten of readdirSync(dir)) {
      const p = `${dir}${dir.endsWith("/") ? "" : "/"}${ten}`;
      if (statSync(p).isDirectory()) duyet(`${p}/`);
      else if (/\.tsx?$/.test(ten)) tep.push(p);
    }
  };
  duyet(`${SRC}components/ai/`);
  const viPham = tep.filter((p) => /\b(used_today|limit_today|phanTramSuDung)\b/.test(codeOnly(readFileSync(p, "utf8"))))
    .map((p) => p.slice(SRC.length).replace(/\\/g, "/"));
  assert.deepEqual(viPham, [], "components/ai/** không dùng token thô / phần trăm");
  const hanMucSrc = codeOnly(read("lib/ai/hanMuc.ts"));
  assert.ok(!/used_today|limit_today|global_daily|caps|overview/.test(hanMucSrc), "hanMuc.ts không biết gì về số liệu toàn cục");
  const client = codeOnly(read("lib/ai/client.ts"));
  assert.match(client, /docHanMuc\(limits\)/, "availability() chỉ cho hạn mức riêng đã kiểm kiểu lên giao diện");
});

test("AiProvider: tin bị từ chối trước `meta` -> 'chưa gửi'; 'Tạo lại' không xoá câu cũ trước khi máy chủ nhận", () => {
  const p = codeOnly(read("components/ai/AiProvider.tsx"));
  assert.match(p, /const chuaNhan = assistantIdRef\.current === null;/);
  assert.match(p, /if \(chuaNhan\) lastUserTextRef\.current = vanBanTruoc;/);
  assert.match(p, /messages: chuaNhan && !regenerateOf \? danhDauChuaGui\(s\.messages, userMsgId\) : s\.messages/);
  assert.match(p, /apDungHetLuot\(s\.availability, loi\.scope, loi\.reset_at\)/);
  assert.match(p, /ev\.type === "usage"[\s\S]{0,260}docHanMuc\(ev\.allowance\)/, "hạn mức cập nhật sau mỗi lượt từ sự kiện usage");
  assert.match(p, /ev\.lane === "qa" \? null/, "lượt QA không đụng hạn mức người dùng trên giao diện");
  const meta = p.match(/ev\.type === "meta"\) \{[\s\S]*?\} else if/)?.[0] ?? "";
  assert.match(meta, /boTinTraLoiCu\(s\.messages, regenerateOf\)/);
  const regen = p.match(/const regenerate = useCallback\([\s\S]*?\[state\.messages, guiVanBan\]\);/)?.[0] ?? "";
  assert.ok(regen && !/filter\(/.test(regen), "regenerate không tự xoá câu trả lời cũ");
  assert.match(p, /error: \{ code: ev\.code, message: ev\.message, reset_at: ev\.reset_at, scope: ev\.scope \}/);
});

test("AiComposer khoá khi hết lượt; AiConversation hiện 'Chưa gửi' và ẩn 'Tạo lại' khi hết lượt", () => {
  const c = codeOnly(read("components/ai/AiComposer.tsx"));
  assert.match(c, /const hetLuot = daHetLuot\(hanMuc\)/);
  assert.match(c, /disabled=\{khoa\}/);
  assert.match(c, /if \(!trimmed \|\| streaming \|\| khoa\) return;/, "kể cả Enter cũng không gửi khi đang khoá");
  assert.match(c, /Bạn đã hết lượt hôm nay/);
  const conv = codeOnly(read("components/ai/AiConversation.tsx"));
  assert.match(conv, /m\.role === "user" && m\.status === "not_sent"/);
  assert.match(conv, />Chưa gửi</);
  assert.match(conv, /m\.message_id === idCuoi && !streaming && !hetLuot/);
  const css = read("components/ai/ai.css");
  assert.match(css, /\.ai-bong-chua-gui \{/);
  assert.match(css, /\.ai-bong-chua-gui-nhan/);
  assert.match(css, /\.ai-usage-het/);
});

test("AiControls: thông điệp lỗi hết ngân sách đi theo phạm vi; không còn phần trăm", () => {
  const c = codeOnly(read("components/ai/AiControls.tsx"));
  assert.match(c, /thongDiepHetLuot\(scope, dinhDangGio\(resetAt\)\)/);
  assert.match(c, /thongDiepLoi\(error\.code, error\.reset_at, error\.scope\)/);
  assert.ok(!/Math\.round\(\(used/.test(c));
});

test("Trang quản trị /admin/ai là nơi thấy mức dùng toàn cục + lượt QA; kiểu AiOverview có `qa`", () => {
  const cards = codeOnly(read("components/admin/ai/AiOverviewCards.tsx"));
  assert.match(cards, /Hạn mức toàn cục hôm nay/);
  assert.match(cards, /Lượt QA của Owner/);
  assert.match(cards, /overview\.qa\.per_owner_daily_cap/);
  assert.match(read("lib/admin/aiControl.ts"), /qa\?: \{ requests: number; tokens: number; owners: number; per_owner_daily_cap: number \} \| null;/);
});

/**
 * `/admin/ai` — hỗ trợ slot Alibaba Model Studio + tầng năng lực + hạn mức miễn phí (docs/ai/ALIBABA_PROVIDER.md).
 * Quy ước repo: không jsdom — hàm thuần được `import()` thẳng, còn lại là bất biến tĩnh trên mã nguồn. Có thêm các bài "chống
 * trôi" giữa kiểu TS và backend Python (loại provider, trạng thái sức khoẻ, trường slot) để hai phía không lệch nhau âm thầm.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const readPy = (p) => readFileSync(new URL(`../../server/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

const v = await import("../src/lib/admin/aiSlotView.ts");

// ------------------------------------------------------------------ hàm thuần

test("dinhDangMs / moTaDoTre: không số liệu thì nói thẳng, có số liệu thì TTFT + tổng + số mẫu", () => {
  assert.equal(v.dinhDangMs(null), "—");
  assert.equal(v.dinhDangMs(undefined), "—");
  assert.equal(v.dinhDangMs(Number.NaN), "—");
  assert.match(v.dinhDangMs(1234), /^1[.,]?234 ms$/);
  assert.match(v.moTaDoTre(undefined), /chưa có số liệu/);
  const rong = { window: 200, samples: 0, ok: 0, probe_samples: 0, ttft_ms: { p50: null, p95: null, last: null }, total_ms: { p50: null, p95: null, last: null }, note: "" };
  assert.match(v.moTaDoTre(rong), /chưa có số liệu/);
  const co = { ...rong, samples: 7, ok: 6, probe_samples: 2, ttft_ms: { p50: 400, p95: 900, last: 410 }, total_ms: { p50: 1500, p95: 3000, last: 1400 } };
  const t = v.moTaDoTre(co);
  assert.match(t, /TTFT p50 400 ms · p95 900 ms · gần nhất 410 ms/);
  assert.match(t, /tổng p50 1[.,]?500 ms/);
  assert.match(t, /7 mẫu, 6 thành công, 2 lần Kiểm tra/);
  const chiTtft = { ...co, ttft_ms: { p50: null, p95: null, last: null } };
  assert.match(v.moTaDoTre(chiTtft), /TTFT —/);
});

test("nhanHanMuc: đủ năm trạng thái, trạng thái lạ rơi về 'Chưa nhập' chứ không ném lỗi", () => {
  const casos = { none: "Chưa nhập", active: "Còn hạn mức", expiring: "Sắp hết hạn", expired: "Đã hết hạn", exhausted: "Hết hạn mức" };
  for (const [state, nhan] of Object.entries(casos)) assert.equal(v.nhanHanMuc({ state }).nhan, nhan);
  assert.equal(v.nhanHanMuc(undefined).nhan, "Chưa nhập");
  assert.equal(v.nhanHanMuc({ state: "ky-la" }).nhan, "Chưa nhập");
  assert.match(v.nhanHanMuc({ state: "expired" }).lop, /^tt-/);
});

test("coThongTinHanMuc: hiện dòng khi có siêu dữ liệu, khoá chỉ-miễn-phí, hoặc nhà cung cấp báo hết hôm nay", () => {
  const nen = { state: "none", remaining: null, expires_at: null, days_left: null, only: false, updated_at: null, provider_exhausted_today: false };
  assert.equal(v.coThongTinHanMuc(undefined), false);
  assert.equal(v.coThongTinHanMuc(nen), false);
  assert.equal(v.coThongTinHanMuc({ ...nen, state: "active" }), true);
  assert.equal(v.coThongTinHanMuc({ ...nen, only: true }), true);
  assert.equal(v.coThongTinHanMuc({ ...nen, provider_exhausted_today: true }), true);
});

test("moTaKhoaChan / moTaUocTinh: nói thẳng vì sao khoá chặn và ước tính đã trừ lượng đã dùng", () => {
  const q = (kw) => ({ state: "active", remaining: 50000, expires_at: null, days_left: null, only: true, updated_at: null, snapshot_age_days: 3,
    consumed_since_snapshot: 44000, estimated_remaining: 6000, lock_block: null, provider_exhausted_today: false, ...kw });
  assert.equal(v.moTaKhoaChan(undefined), null);
  assert.equal(v.moTaKhoaChan(q({})), null);
  for (const r of ["expired", "stale", "unverifiable", "exhausted"]) assert.match(v.moTaKhoaChan(q({ lock_block: r })), /\S/);
  assert.match(v.moTaKhoaChan(q({ lock_block: "stale" })), /quá cũ|thiếu dấu thời gian/);
  assert.match(v.moTaKhoaChan(q({ lock_block: "exhausted" })), /dự phòng 5%/);
  assert.equal(v.moTaUocTinh(undefined), null);
  assert.equal(v.moTaUocTinh(q({ estimated_remaining: null })), null);
  assert.equal(v.moTaUocTinh(q({ consumed_since_snapshot: null })), null);
  assert.match(v.moTaUocTinh(q({})), /ước còn 6[.,]?000 token \(đã trừ 44[.,]?000 token/);
});

test("moTaHanDung: còn / đã quá bao nhiêu ngày, null khi không có hạn", () => {
  const q = (days_left, expires_at = "2026-12-31T00:00:00+00:00") => ({ state: "active", remaining: 1, expires_at, days_left, only: false, updated_at: null, provider_exhausted_today: false });
  assert.equal(v.moTaHanDung(q(2.5)), "còn 2.5 ngày");
  assert.equal(v.moTaHanDung(q(-3)), "đã quá 3 ngày");
  assert.equal(v.moTaHanDung(q(null)), null);
  assert.equal(v.moTaHanDung(q(5, null)), null);
  assert.equal(v.moTaHanDung(undefined), null);
});

test("hostCuaEndpoint: chỉ máy chủ, không đường dẫn/query; sai thì '—'", () => {
  assert.equal(v.hostCuaEndpoint("https://dashscope-intl.aliyuncs.com/compatible-mode/v1"), "dashscope-intl.aliyuncs.com");
  assert.equal(v.hostCuaEndpoint("https://host.example/x?token=abc"), "host.example");
  assert.equal(v.hostCuaEndpoint(""), "—");
  assert.equal(v.hostCuaEndpoint(undefined), "—");
  assert.equal(v.hostCuaEndpoint("không phải URL"), "—");
});

test("datetime-local <-> ISO: khứ hồi giữ nguyên thời điểm (đến phút), máy chủ luôn nhận múi giờ tường minh", () => {
  assert.equal(v.isoSangDatetimeLocal(""), "");
  assert.equal(v.isoSangDatetimeLocal("rác"), "");
  assert.equal(v.datetimeLocalSangIso(""), "");
  assert.equal(v.datetimeLocalSangIso("rác"), "");
  const iso = "2026-12-31T05:30:00+00:00";
  const local = v.isoSangDatetimeLocal(iso);
  assert.match(local, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  assert.equal(v.datetimeLocalSangIso(local), iso, "khứ hồi không lệch giờ dù máy ở múi giờ nào");
  assert.match(v.datetimeLocalSangIso("2026-10-02T12:00"), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/);
});

// ------------------------------------------------------------------ giao diện: không tên provider, đọc từ meta

test("giao diện không viết cứng tên provider/nhà cung cấp nào — nhãn, cổng, quy tắc đều đến từ máy chủ", () => {
  const PROVIDER = /gemini|groq|workers_ai|qwen|azure|openrouter|dashscope|cloudflare|alibaba|aliyun/i;
  const files = ["components/admin/ai/AiSlotForm.tsx", "components/admin/ai/AiSlotList.tsx", "components/admin/ai/AiProviderTypes.tsx",
    "components/admin/ai/AiOverviewCards.tsx", "lib/admin/aiSlotView.ts", "app/admin/ai/page.tsx"];
  for (const f of files) {
    const code = codeOnly(read(f));
    assert.doesNotMatch(code, PROVIDER, `${f}: có tên provider viết cứng: ${code.match(PROVIDER)?.[0]}`);
  }
  const client = codeOnly(read("lib/admin/aiControl.ts")).replace(/export type AiProviderType =[\s\S]*?;/, "");
  assert.doesNotMatch(client, PROVIDER, "aiControl.ts: tên provider ngoài kiểu union");
});

test("form: slot loại 'luôn tạo ở trạng thái tắt' khoá ô Bật theo meta của server và gửi enabled=false", () => {
  const src = codeOnly(read("components/admin/ai/AiSlotForm.tsx"));
  assert.match(src, /meta\.created_disabled_types \?\? \[\]\)\.includes\(providerType\)/);
  assert.match(src, /enabled: taoMacDinhTat \? false : enabled/);
  assert.match(src, /disabled=\{taoMacDinhTat\}/);
});

test("form: tầng năng lực lấy từ meta, số dư để trống = null (không phải 0), thời điểm ảnh chụp KHÔNG gửi từ client", () => {
  const src = codeOnly(read("components/admin/ai/AiSlotForm.tsx"));
  assert.match(src, /meta\.capability_tiers \?\? \[\]\)\.map/);
  assert.match(src, /free_quota_remaining: quotaRemaining\.trim\(\) === "" \? null : Number\(quotaRemaining\)/);
  assert.match(src, /free_quota_expires_at: datetimeLocalSangIso\(quotaExpires\)/);
  assert.match(src, /free_quota_only: quotaOnly/);
  assert.doesNotMatch(src, /free_quota_updated_at/, "máy chủ đóng dấu; client không gửi");
  for (const f of ["tiers", "free_quota_remaining", "free_quota_expires_at", "free_quota_only"]) {
    assert.match(src, new RegExp(`"${f}"`), `${f} phải nằm trong TRUONG_FORM để lỗi hiện cạnh ô`);
  }
});

test("danh sách slot: hiện cổng, tầng, độ trễ, hạn mức miễn phí, endpoint; nút Kiểm tra khoá khi cổng đóng", () => {
  const src = codeOnly(read("components/admin/ai/AiSlotList.tsx"));
  assert.match(src, /h\.gate \? \(/);
  assert.match(src, /moTaDoTre\(h\.latency\)/);
  assert.match(src, /coThongTinHanMuc\(h\.quota\)/);
  assert.match(src, /hostCuaEndpoint\(slot\.effective_endpoint\)/);
  assert.match(src, /slot\.tiers && slot\.tiers\.length/);
  assert.match(src, /\(!!h\.gate && !h\.gate\.open\)/, "cổng đóng thì không cho gửi request Kiểm tra");
  assert.match(src, /không tự cập nhật/, "số hạn mức là ảnh chụp Owner nhập, phải nói rõ");
});

test("loại provider + tổng quan: cổng cấp máy chủ hiện rõ và không thể bật từ giao diện", () => {
  const types = codeOnly(read("components/admin/ai/AiProviderTypes.tsx"));
  assert.match(types, /p\.gate \? \(/);
  assert.match(types, /bật ở đây không thay thế được/);
  const ov = codeOnly(read("components/admin/ai/AiOverviewCards.tsx"));
  assert.match(ov, /overview\.gates && Object\.keys\(overview\.gates\)\.length > 0/);
  assert.match(ov, /overview\.free_quota_preference \? "BẬT" : "TẮT"/);
  const page = codeOnly(read("app/admin/ai/page.tsx"));
  assert.match(page, /probe\.ttft_ms != null/);
});

// ------------------------------------------------------------------ chống trôi giữa TS và backend

test("AiProviderType (TS) liệt kê đúng PROVIDER_TYPES của backend", () => {
  const py = readPy("ai_assistant/control/model.py");
  const tuple = py.match(/PROVIDER_TYPES: Tuple\[str, \.\.\.\] = \(([^)]*)\)/)[1];
  const backend = [...tuple.matchAll(/"(\w+)"/g)].map((m) => m[1]).sort();
  const ts = read("lib/admin/aiControl.ts").match(/export type AiProviderType =([\s\S]*?);/)[1];
  const front = [...ts.matchAll(/"(\w+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(front, backend);
});

test("AiSlotHealthStatus (TS) có mọi trạng thái mà slot_health của backend có thể trả, và danh sách vẽ đủ nhãn", () => {
  const svc = readPy("ai_assistant/control/service.py");
  const body = svc.match(/def slot_health\([\s\S]*?return \{"status": status/)[0];
  const backend = [...new Set([...body.matchAll(/status = "([A-Z_]+)"/g)].map((m) => m[1]))].sort();
  assert.ok(backend.length >= 8, `đọc được ${backend.length} trạng thái`);
  const ts = read("lib/admin/aiControl.ts").match(/export type AiSlotHealthStatus =([\s\S]*?);/)[1];
  const front = [...new Set([...ts.matchAll(/"([A-Z_]+)"/g)].map((m) => m[1]))].sort();
  assert.deepEqual(front, backend);
  const list = read("components/admin/ai/AiSlotList.tsx");
  for (const s of backend) {
    assert.match(list, new RegExp(`\\b${s}: "`), `AiSlotList thiếu nhãn/lớp cho ${s}`);
  }
});

test("AiSlot (TS) có đủ các trường slot_to_dict của backend (kể cả trường mới)", () => {
  const py = readPy("ai_assistant/control/model.py");
  const fn = py.match(/def slot_to_dict[\s\S]*?(?=\n\ndef |\nclass |\n#)/)[0];
  const backend = [...new Set([...fn.matchAll(/"(\w+)":/g)].map((m) => m[1]))];
  assert.ok(backend.includes("free_quota_only") && backend.includes("tiers"));
  const ts = read("lib/admin/aiControl.ts").match(/export interface AiSlot \{([\s\S]*?)\n\}/)[1];
  for (const k of backend) assert.match(ts, new RegExp(`\\b${k}\\??:`), `AiSlot thiếu trường ${k}`);
});

test("AiSlotQuota (TS) có đủ các trường mà backend trả trong health.quota", () => {
  const cap = readPy("ai_assistant/control/capability.py");
  const fn = cap.match(/def free_quota_state[\s\S]*?(?=\n\ndef )/)[0];
  const svc = readPy("ai_assistant/control/service.py");
  const view = svc.match(/def _quota_view[\s\S]*?(?=\n    def )/)[0];
  const backend = new Set([...fn.matchAll(/"(\w+)":/g)].map((m) => m[1]));
  for (const k of ["lock_block", "provider_exhausted_today"]) assert.match(view, new RegExp(`"${k}"`));
  backend.add("lock_block");
  backend.add("provider_exhausted_today");
  for (const k of ["state", "estimated_remaining", "consumed_since_snapshot", "snapshot_age_days"]) assert.ok(backend.has(k), k);
  const ts = read("lib/admin/aiControl.ts").match(/export interface AiSlotQuota \{([\s\S]*?)\n\}/)[1];
  for (const k of backend) assert.match(ts, new RegExp(`\\b${k}\\??:`), `AiSlotQuota thiếu trường ${k}`);
});

test("danh sách slot hiện ước tính còn lại và lý do khoá chặn", () => {
  const src = codeOnly(read("components/admin/ai/AiSlotList.tsx"));
  assert.match(src, /moTaUocTinh\(h\.quota\)/);
  assert.match(src, /moTaKhoaChan\(h\.quota\)/);
  assert.match(src, /khoá đang CHẶN slot/);
});

test("AiSlotInput (TS) chỉ gửi các trường client được phép đặt", () => {
  const ts = read("lib/admin/aiControl.ts").match(/export interface AiSlotInput \{([\s\S]*?)\n\}/)[1];
  for (const k of ["tiers", "free_quota_remaining", "free_quota_expires_at", "free_quota_only"]) assert.match(ts, new RegExp(`\\b${k}\\?:`));
  assert.doesNotMatch(ts, /free_quota_updated_at/, "dấu thời gian ảnh chụp do máy chủ đóng");
  assert.doesNotMatch(ts, /meta_corrupt|health/, "trạng thái chỉ-đọc không nằm trong payload");
});

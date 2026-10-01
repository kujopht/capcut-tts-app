/**
 * `/admin/ai` — khối "Ai đang dùng được · hàng đợi luồng" + dòng "Còn lại hôm nay" (docs/ai/AI_OPERATIONS_RUNBOOK.md §4/§6).
 * Bất biến tĩnh (quy ước repo: không jsdom): kiểu dữ liệu khớp backend, khối chỉ vẽ khi có `runtime`, nhãn khán giả đủ giá
 * trị hợp lệ, và giao diện không có đường nào hiện danh sách người dùng.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

test("AiOverview.runtime khớp backend: đúng bốn trường, không ID/danh sách", () => {
  const t = read("lib/admin/aiControl.ts");
  const m = t.match(/runtime\?: \{([^}]*)\} \| null;/);
  assert.ok(m, "thiếu AiOverview.runtime");
  const fields = [...m[1].matchAll(/(\w+):/g)].map((x) => x[1]).sort();
  assert.deepEqual(fields, ["audience", "rpm_per_user", "streams_active", "streams_max"]);
});

test("AiOverviewCards: khối runtime chỉ vẽ khi có dữ liệu và dùng nhãn khán giả đầy đủ", () => {
  const src = codeOnly(read("components/admin/ai/AiOverviewCards.tsx"));
  assert.match(src, /overview\.runtime \? \(/);
  assert.match(src, /nhanKhanGia\(overview\.runtime\.audience\)/);
  for (const gt of ["all", "beta", "canary"]) assert.match(src, new RegExp(`case "${gt}":`));
  assert.match(src, /case "":\s*return "KHÔNG AI/, "khán giả rỗng = cấu hình sai, AI tắt — phải nói thẳng");
  assert.match(src, /overview\.runtime\.streams_active/);
  assert.match(src, /overview\.runtime\.streams_max/);
  assert.doesNotMatch(src, /beta_users|canary_users|owner_user/, "giao diện không có đường nào hiện danh sách người dùng");
});

test("AiOverviewCards: hạn mức toàn cục có dòng 'Còn lại hôm nay' chỉ khi có trần", () => {
  const src = codeOnly(read("components/admin/ai/AiOverviewCards.tsx"));
  assert.match(src, /global_daily_request_cap > 0 \? \(/);
  assert.match(src, /Math\.max\(0, overview\.caps\.global_daily_request_cap - overview\.requests\)/);
  assert.match(src, /00:00 UTC = 07:00 giờ Việt Nam/);
});

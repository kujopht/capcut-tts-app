/**
 * Admin Control Center V2, Phase 7 — Analytics/AI-Credits/System.
 *
 * Cung phong cach voi cac test admin-*.test.mjs khac: doc THANG source va
 * khang dinh cac dac diem quan trong bang regex, khong dung DOM gia lap.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const api = () => read("../src/lib/api.ts");
const analytics = () => read("../src/app/admin/analytics/page.tsx");
const aiCredits = () => read("../src/app/admin/ai-credits/page.tsx");
const system = () => read("../src/app/admin/system/page.tsx");

// -- lop api ---------------------------------------------------------------

test("adminApi: analyticsDetail goi dung duong Phase 7", () => {
  const src = api();
  assert.match(src, /analyticsDetail:[\s\S]{0,200}\/api\/admin\/analytics\/detail/);
});

test("AdminAnalyticsDetail: khong bia DAU\\/WAU\\/MAU, deu la ChiSo", () => {
  const src = api();
  const at = src.indexOf("export interface AdminAnalyticsDetail");
  const doan = src.slice(at, at + 1200);
  assert.match(doan, /active_daily: ChiSo/);
  assert.match(doan, /active_weekly: ChiSo/);
  assert.match(doan, /active_monthly: ChiSo/);
  assert.match(doan, /active_note: string/);
  assert.match(doan, /novel_reads: ChiSo/);
  assert.match(doan, /chapter_completions: ChiSo/);
  assert.match(doan, /animation_views: ChiSo/);
  assert.match(doan, /content_activity_note: string/);
});

test("AdminImageStudioSpending: mo rong Phase 7 khong xoa truong cu", () => {
  const src = api();
  const at = src.indexOf("export interface AdminImageStudioSpending");
  const doan = src.slice(at, at + 900);
  // Truong CU tu Phase 2 phai con nguyen.
  assert.match(doan, /spent_usd: number/);
  assert.match(doan, /kill_switch_engaged: boolean/);
  // Truong MOI Phase 7.
  assert.match(doan, /translation_jobs_by_status:/);
  assert.match(doan, /tts_jobs_by_status:/);
  assert.match(doan, /byok_connections_by_status: Record<string, number>/);
  assert.match(doan, /wallet_note: string/);
});

test("AdminOverview.system: co du bon truong Phase 7 (YouTube\\/WebSub\\/statuses)", () => {
  const src = api();
  const at = src.indexOf("export interface AdminOverview");
  const doan = src.slice(at, src.indexOf("Danh tính kèm theo đơn"));
  assert.match(doan, /youtube_data_api_configured: boolean/);
  assert.match(doan, /youtube_websub_configured: boolean/);
  assert.match(doan, /statuses: \{/);
  assert.match(doan, /youtube_websub: TrangThaiHeThong/);
  assert.match(doan, /reconciliation: TrangThaiHeThong/);
});

test("TrangThaiHeThong: dung bon gia tri, khong hon", () => {
  const src = api();
  const at = src.indexOf("export type TrangThaiHeThong");
  const dong = src.slice(at, at + 200).split("\n")[0];
  for (const gia_tri of ["healthy", "degraded", "error", "not_configured"]) {
    assert.ok(dong.includes(gia_tri), `thiếu giá trị ${gia_tri}`);
  }
});

// -- trang Analytics ---------------------------------------------------------

test("Analytics: co bo chuyen doi pham vi Hom nay\\/7 ngay\\/30 ngay", () => {
  const src = analytics();
  assert.match(src, /"today"[\s\S]{0,40}"Hôm nay"/);
  assert.match(src, /"7d"[\s\S]{0,40}"7 ngày"/);
  assert.match(src, /"30d"[\s\S]{0,40}"30 ngày"/);
  assert.match(src, /adminApi\.analyticsDetail\(pham_vi\)/);
});

test("Analytics: hien ro ghi chu khi DAU\\/WAU\\/MAU va hoat dong noi dung chua co", () => {
  const src = analytics();
  assert.match(src, /data\.users\.active_note/);
  assert.match(src, /data\.content\.content_activity_note/);
});

test("Analytics: khong con goi adminApi\\.overview\\(\\) truc tiep (dung analyticsDetail)", () => {
  const src = analytics();
  assert.ok(!/adminApi\.overview\(\)/.test(src),
    "trang Analytics vẫn gọi adminApi.overview() thay vì analyticsDetail");
});

// -- trang AI\/Credits ---------------------------------------------------------

test("AI/Credits: hien tinh trang dich\\/TTS\\/BYOK va ghi chu vi", () => {
  const src = aiCredits();
  assert.match(src, /data\.translation_jobs_by_status\.completed/);
  assert.match(src, /data\.tts_jobs_by_status\.pending/);
  assert.match(src, /data\.byok_connections_by_status/);
  assert.match(src, /data\.wallet_note/);
});

test("AI/Credits: khong bao gio hien encrypted_secret\\/api key", () => {
  const src = aiCredits();
  assert.ok(!/encrypted_secret/.test(src), "trang AI/Credits nhắc tới encrypted_secret");
  assert.ok(!/api_key/i.test(src), "trang AI/Credits nhắc tới api key");
});

// -- trang System ---------------------------------------------------------

test("System: dung chung mot vocab bon trang thai qua TrangThaiHang", () => {
  const src = system();
  assert.match(src, /Record<TrangThaiHeThong, string>/);
  assert.match(src, /data\.system\.statuses\.youtube_data_api/);
  assert.match(src, /data\.system\.statuses\.youtube_websub/);
  assert.match(src, /data\.system\.statuses\.reconciliation/);
});

test("System: hien ghi chu can HTTPS cong khai khi WebSub chua cau hinh", () => {
  const src = system();
  assert.match(src, /youtube_websub_configured[\s\S]{0,120}HTTPS/);
});

test("System: hien lan doi chieu gan nhat hoac \"Chua tung chay\"", () => {
  const src = system();
  assert.match(src, /reconciliation_last_run_at/);
  assert.match(src, /Chưa từng chạy/);
});

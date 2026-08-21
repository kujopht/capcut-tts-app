/**
 * Admin Control Center V2, Phase 6 — YouTube WebSub + đồng bộ tự động.
 *
 * Cung phong cach voi `admin-trusted-sources.test.mjs`: doc THANG source va
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
const chiTiet = () => read("../src/app/admin/animation/sources/[id]/page.tsx");

// -- lop api ------------------------------------------------------------

test("adminApi: subscribe/unsubscribe/reconciliation goi dung duong Phase 6", () => {
  const src = api();
  assert.match(src, /subscribeTrustedSource:[\s\S]{0,300}\/subscribe`/);
  assert.match(src, /unsubscribeTrustedSource:[\s\S]{0,300}\/unsubscribe`/);
  assert.match(src, /runReconciliation:[\s\S]{0,400}\/api\/admin\/animation\/reconciliation\/run"/);
});

test("TrustedSource: co du cac truong WebSub Phase 6", () => {
  const src = api();
  const at = src.indexOf("export interface TrustedSource {");
  const doan = src.slice(at, src.indexOf("export interface AdminTrustedSourceRow"));
  assert.match(doan, /last_subscription_attempt_at: string/);
  assert.match(doan, /last_notification_at: string/);
  assert.match(doan, /last_websub_error: string/);
  assert.match(doan, /last_successful_sync_at: string/);
  // websub_secret KHONG BAO GIO duoc khai bao LA MOT TRUONG o phia frontend
  // — bi mat chi ton tai o server (co the duoc NHAC toi trong doc comment
  // giai thich vi sao truong do vang mat, nen chi kiem dinh dang KHAI BAO
  // truong `websub_secret:`, khong phai bat ky chuoi con nao).
  assert.ok(!/\bwebsub_secret\s*:/.test(doan),
    "kiểu TrustedSource khai báo trường websub_secret");
});

test("AdminTrustedSourceDetail: co truong websub_configured (su that TOAN CUC)", () => {
  const src = api();
  const at = src.indexOf("export interface AdminTrustedSourceDetail {");
  const doan = src.slice(at, at + 500);
  assert.match(doan, /websub_configured: boolean/);
});

// -- trang chi tiet nguon -------------------------------------------------

test("Chi tiet nguon: co khoi Dong bo tu dong, ChuaCauHinh khi chua co URL callback", () => {
  const src = chiTiet();
  assert.match(src, /Đồng bộ tự động/);
  assert.match(src, /!data\.websub_configured \? \(/);
  assert.match(src, /<ChuaCauHinh/);
});

test("Chi tiet nguon: nut Dang ky goi subscribeTrustedSource", () => {
  const src = chiTiet();
  assert.match(src, /adminApi\.subscribeTrustedSource\(sourceId\)/);
});

test("Chi tiet nguon: nut Chay doi chieu goi runReconciliation VOI sourceId (khong phai toan cuc)", () => {
  const src = chiTiet();
  assert.match(src, /adminApi\.runReconciliation\(sourceId\)/);
});

test("Chi tiet nguon: hien du bon chi so trang thai dang ky (thong bao/dong bo/han/loi)", () => {
  const src = chiTiet();
  assert.match(src, /Thông báo gần nhất/);
  assert.match(src, /Đối chiếu thành công gần nhất/);
  assert.match(src, /Hạn đăng ký/);
  assert.match(src, /s\.last_websub_error/);
});

test("Chi tiet nguon: nhan trang thai dang ky co du 5 gia tri enum", () => {
  const src = chiTiet();
  const at = src.indexOf("NHAN_DANG_KY");
  const doan = src.slice(at, at + 400);
  for (const gia_tri of ["none", "pending", "active", "expired", "failed"]) {
    assert.match(doan, new RegExp(`${gia_tri}:`));
  }
});

test("Chi tiet nguon: KHONG bao gio hien thi websub_secret o bat ky dau", () => {
  const src = chiTiet();
  assert.ok(!src.includes("websub_secret"), "trang chi tiết nguồn nhắc tới websub_secret");
});

/**
 * Trung tâm hỗ trợ (/admin/support) — bất biến:
 *   * tắt cờ = không có mục điều hướng, trang 404;
 *   * KHÔNG thăm dò (không setInterval, không tự làm mới);
 *   * KHÔNG tự tạo issue: chỉ bản nháp + liên kết quản trị tự bấm;
 *   * dùng được ở 390px (một cột, danh sách/chi tiết tách màn).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");
const trang = () => codeOnly(read("app/admin/support/TrungTamHoTro.tsx"));

test("tat co: khong muc dieu huong, trang 404", () => {
  assert.match(codeOnly(read("components/AdminShell.tsx")),
    /\.\.\.\(SUPPORT_ENABLED \? \[\{ muc: \[\{ href: "\/admin\/support", nhan: "Hỗ trợ & sự cố", icon: IconInbox \}\] \}\] : \[\]\)/);
  assert.match(codeOnly(read("app/admin/support/page.tsx")), /if \(!SUPPORT_ENABLED\) notFound\(\);/);
});

test("khong tham do: khong setInterval, khong tu lam moi; status may chu goi MOT lan", () => {
  const p = trang();
  assert.ok(!/setInterval\s*\(/.test(p));
  assert.equal((p.match(/supportApi\.status\(\)/g) ?? []).length, 1);
  assert.match(p, /onClick=\{tai\}>↻ Làm mới<\/button>/);
});

test("khong tu tao issue GitHub: chi ban nhap + lien ket quan tri tu bam", () => {
  const p = trang();
  assert.ok(!/github\.com/.test(p), "trang khong duoc tu dung URL GitHub — may chu chuan bi, quan tri tu bam");
  assert.ok(!/fetch\(/.test(p), "chi goi qua adminSupportApi");
  assert.match(p, /href=\{nhap\.new_issue_url\} target="_blank" rel="noopener noreferrer"/);
  assert.match(p, /Mở trang tạo issue \(bạn tự bấm tạo\)/);
  assert.match(p, /Bản nháp — chưa tạo gì trên GitHub/);
});

test("goi dung API quan tri (quyen do may chu kiem) — o lib/support/adminApi.ts, KHONG o lib/api.ts dung chung", () => {
  const api = codeOnly(read("lib/support/adminApi.ts"));
  for (const d of ["/api/admin/support/summary", "/api/admin/support/incidents", "/api/admin/support/reports"]) {
    assert.ok(api.includes(d), d);
  }
  // lib/api.ts vao bundle MOI trang; Support tat co mac dinh -> khong mot duong dan nao o do.
  assert.ok(!/api\/admin\/support/.test(codeOnly(read("lib/api.ts"))), "lib/api.ts chua API quan tri Support");
  assert.match(api, /\/api\/admin\/support\/incidents\/\$\{encodeURIComponent\(id\)\}\/status/);
  assert.match(api, /\/api\/admin\/support\/incidents\/\$\{encodeURIComponent\(id\)\}\/issue-draft/);
});

test("390px: mot cot, danh sach/chi tiet tach man, vung bam 44px; chon su co day ?i= len URL", () => {
  const css = read("app/admin/support/admin-support.css");
  assert.match(css, /\.ht-co-chon \.ht-cot-ds, \.ht-co-chon \.ht-tong, \.ht-co-chon \.ht-ghi-chu \{ display: none; \}/);
  assert.match(css, /\.ht:not\(\.ht-co-chon\) \.ht-cot-ct \{ display: none; \}/);
  assert.match(css, /min-height: 44px/);
  assert.match(trang(), /router\.push\(`\/admin\/support\?i=\$\{encodeURIComponent\(id\)\}`, \{ scroll: false \}\)/);
});

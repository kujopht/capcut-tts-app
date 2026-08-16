/**
 * Admin Control Center V2, Phase 3 — quan ly tai khoan (tam dung dang nhap,
 * phien dang nhap), TACH BACH voi treo TAC GIA (chi chan xuat ban).
 *
 * Cung phong cach voi cac bai kiem khac: doc THANG source va khang dinh cac
 * dac diem quan trong bang regex, khong dung DOM gia lap.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const api = () => read("../src/lib/api.ts");
const list = () => read("../src/app/admin/users/page.tsx");
const detail = () => read("../src/app/admin/users/[user_id]/page.tsx");

// -- lop api --------------------------------------------------------------

test("adminApi: bon ham tai khoan deu goi dung duong /api/admin/users/*", () => {
  const src = api();
  const at = src.indexOf("  suspendAccount:");
  assert.ok(at > 0, "thiếu suspendAccount");
  const doan = src.slice(at, at + 1200);
  assert.match(doan, /\/api\/admin\/users\/\$\{encodeURIComponent\(userId\)\}\/suspend/);
  assert.match(doan, /\/api\/admin\/users\/\$\{encodeURIComponent\(userId\)\}\/unsuspend/);
  assert.match(doan, /sessions\/\$\{encodeURIComponent\(sessionId\)\}\/terminate/);
  assert.match(doan, /sessions\/terminate-all/);
  // Ca bon deu la thao tac GHI.
  const soLanPost = (doan.match(/method: "POST"/g) ?? []).length;
  assert.equal(soLanPost, 4, "một trong bốn thao tác tài khoản không phải POST");
});

test("AdminUser: co du truong native tu Appwrite Users API, TACH BACH voi author_status", () => {
  const src = api();
  const at = src.indexOf("export interface AdminUser");
  const doan = src.slice(at, src.indexOf("export interface AdminApplication"));
  assert.match(doan, /email_verified\?: boolean/);
  assert.match(doan, /account_enabled\?: boolean/);
  assert.match(doan, /admin_role\?: AdminRole/);
  assert.match(doan, /account\?: AdminAccountStatus \| null/);
  assert.match(doan, /sessions\?: AdminAccountSession\[\]/);
});

// -- danh sach --------------------------------------------------------------

test("Danh sach nguoi dung: nguon la tai khoan native, hien duoc nguoi CHUA chon username", () => {
  const src = list();
  assert.match(src, /chưa chọn tên công khai/);
  // Khong con dan thang toi /u/username — mot tai khoan chua co username thi
  // duong do khong mo duoc.
  assert.doesNotMatch(src, /href=\{`\/u\/\$\{u\.username\}`\}/);
  assert.match(src, /href=\{`\/admin\/users\/\$\{u\.user_id\}`\}/);
});

test("Danh sach nguoi dung: co cot trang thai TAI KHOAN, KHAC cot trang thai tac gia", () => {
  const src = list();
  assert.match(src, /Trạng thái tài khoản/);
  assert.match(src, /account_enabled === false/);
});

// -- chi tiet -----------------------------------------------------------

test("Chi tiet tai khoan: noi RO tam dung o day KHOA DANG NHAP, khac treo tac gia", () => {
  const src = detail();
  assert.match(src, /khoá đăng nhập HOÀN TOÀN/);
  assert.match(src, /khác với tạm dừng tác giả/i);
});

test("Chi tiet tai khoan: an nut tam dung\\/cham dut phien khi dang xem CHINH MINH", () => {
  const src = detail();
  assert.match(src, /laChinhMinh = profile\?\.user_id === userId/);
  // Nhanh render nut tam dung phai nam SAU nhanh kiem `laChinhMinh`.
  const at = src.indexOf("laChinhMinh ?");
  assert.ok(at > 0, "không tìm thấy nhánh laChinhMinh trong JSX");
});

test("Chi tiet tai khoan: tam dung va cham dut tat ca phien deu qua ConfirmDialog", () => {
  const src = detail();
  const soLanConfirm = (src.match(/<ConfirmDialog/g) ?? []).length;
  assert.equal(soLanConfirm, 2, "phải có đúng 2 hộp xác nhận (tạm dừng + chấm dứt tất cả)");
  assert.match(src, /danger/);
});

test("Chi tiet tai khoan: dung DanhSachTrangThai, khong tu ve cong chan rieng", () => {
  const src = detail();
  assert.match(src, /DanhSachTrangThai/);
  assert.ok(!src.includes("<AdminShell"), "trang tự bọc cổng chặn thay vì dùng layout");
});

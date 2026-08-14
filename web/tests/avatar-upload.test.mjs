/**
 * V4 Phase 6 — tai/doi/xoa avatar o /account. Cung phong cach voi
 * `novel-cover.test.mjs`: doc THANG source, khang dinh bang regex.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const account = () => read("../src/app/account/page.tsx");
const api = () => read("../src/lib/api.ts");
const limits = () => read("../src/lib/limits.ts");
const session = () => read("../src/lib/session.tsx");
const navAuth = () => read("../src/components/NavAuth.tsx");

test("/account dung MAX_AVATAR_EDGE tu lib/limits, khong tu bia con so", () => {
  const src = account();
  assert.match(src, /import\s*\{[^}]*MAX_AVATAR_EDGE[^}]*\}\s*from\s*"@\/lib\/limits"/);
  assert.match(src, /xuLyAnh\(tep,\s*MAX_AVATAR_EDGE\)/);
});

test("MAX_AVATAR_EDGE la mot hang so duoc dan, khong phai gia tri tinh", () => {
  assert.match(limits(), /export const MAX_AVATAR_EDGE\s*=\s*\d+/);
});

test("/account goi api.setAvatar va api.removeAvatar", () => {
  const src = account();
  assert.match(src, /api\.setAvatar\(/);
  assert.match(src, /api\.removeAvatar\(/);
});

test("lib/api.ts: duong REST dung cho tai/xoa avatar", () => {
  const src = api();
  assert.match(src, /setAvatar:[\s\S]{0,220}\/api\/creator\/avatar/);
  assert.match(src, /setAvatar:[\s\S]{0,260}method:\s*"PUT"/);
  assert.match(src, /removeAvatar:[\s\S]{0,120}\/api\/creator\/avatar/);
  assert.match(src, /removeAvatar:[\s\S]{0,120}method:\s*"DELETE"/);
});

test("cap nhat ho so sau khi doi avatar KHONG tao mot phien moi", () => {
  /*
    `adoptSession` doi ca token — dung sai cho mot thao tac chi doi ho so.
    Phai co mot lo rieng chi thay `profile`, khong dung toi token.
  */
  assert.match(session(), /updateProfile:\s*setProfile/);
  assert.match(account(), /updateProfile\(result\.profile\)/);
});

test("URL xem truoc tam thoi cua avatar duoc thu hoi sau khi tai len xong", () => {
  assert.match(account(), /URL\.revokeObjectURL\(anh\.xemTruoc\)/);
});

test("o chon avatar bi khoa trong luc dang luu, chi nhan anh", () => {
  const src = account();
  const at = src.indexOf('type="file"');
  const doan = src.slice(at, at + 200);
  assert.match(doan, /accept="image\/\*"/);
  assert.match(doan, /disabled=\{savingAvatar\}/);
});

test("nut Go avatar chi hien khi DA co avatar", () => {
  const src = account();
  const at = src.indexOf("Gỡ avatar");
  assert.ok(at > 0, "không tìm thấy nút Gỡ avatar");
  const truoc = src.slice(Math.max(0, at - 500), at);
  assert.match(truoc, /profile\.avatar_url\s*\?/);
});

test("menu tai khoan (NavAuth) dung component Avatar dung chung, truyen avatar_url", () => {
  /*
    Logic "anh that hay chu cai dau" gio song trong `components/Avatar.tsx`
    (dung chung cho NavAuth, /account, PostCard, CommentThread, SearchOverlay,
    trang ho so cong khai) — bai kiem ve dac diem HIEN THI thuoc ve file do;
    o day chi con kiem NavAuth truyen dung prop.
  */
  const src = navAuth();
  assert.match(src, /import\s*\{\s*Avatar\s*\}\s*from\s*"@\/components\/Avatar"/);
  assert.match(src, /<Avatar\s+name=\{name\}\s+avatarUrl=\{profile\.avatar_url\}/);
});

test("components/Avatar.tsx: anh that hay chu cai dau ten, khong de chu chong len anh", () => {
  const src = read("../src/components/Avatar.tsx");
  assert.match(src, /backgroundImage:\s*`url\("\$\{avatarUrl\}"\)`/);
  assert.match(src, /avatarUrl\s*\?\s*null\s*:/);
});

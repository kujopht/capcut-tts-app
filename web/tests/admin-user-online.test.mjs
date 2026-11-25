/*
 * HIEN DIEN USER: heartbeat + trang quan tri "User online".
 *
 * - `SessionProvider` ping `POST /api/auth/me/heartbeat` 60s/lan khi tab
 *   dang hien (chi khi da dang nhap).
 * - Trang `/admin/users/online` goi `adminApi.usersOnline` (duoi
 *   `/api/admin/`), hien cham online + lan online gan nhat.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const api = () => read("../src/lib/api.ts");
const trang = () => read("../src/app/admin/users/online/page.tsx");

test("heartbeat POST dung duong /api/auth/me/heartbeat", () => {
  const src = api();
  assert.match(src, /heartbeat: \(\) =>/);
  assert.match(src, /"\/api\/auth\/me\/heartbeat"/);
  assert.match(src, /method: "POST"/);
});

test("adminApi.usersOnline nam duoi /api/admin/users/online", () => {
  const src = api();
  assert.match(src, /usersOnline: \(q = "", limit = 50, offset = 0\) =>/);
  assert.match(src, /`\/api\/admin\/users\/online\?q=/);
  assert.match(src, /export interface AdminUserOnline/);
  const kieu = src.slice(src.indexOf("export interface AdminUserOnline"));
  for (const truong of ["user_id: string", "email: string",
                        "last_seen_at: string | null", "is_online: boolean"]) {
    assert.ok(kieu.includes(truong), `thiếu trường ${truong}`);
  }
});

test("SessionProvider ping heartbeat 60s/lan, chi khi tab hien", () => {
  const src = read("../src/lib/session.tsx");
  assert.match(src, /api\.heartbeat\(\)/);
  assert.match(src, /60_000/);
  assert.match(src, /document\.visibilityState === "visible"/);
  assert.match(src, /visibilitychange/);
  // Chi chay khi DA dang nhap.
  const at = src.indexOf("api.heartbeat()");
  const hieu = src.slice(Math.max(0, at - 400), at);
  assert.match(hieu, /if \(!profile\) return/);
  // Loi mang khong duoc hien cho nguoi dung.
  assert.match(src, /api\.heartbeat\(\)\.catch\(\(\) => \{\}\)/);
});

test("trang online co tim kiem, tai them, tu tai lai", () => {
  const src = trang();
  assert.match(src, /adminApi\.usersOnline\(/);
  assert.match(src, /DanhSachTrangThai/);
  assert.match(src, /Tải thêm/);
  assert.match(src, /setSoTrang\(\(s\) => s \+ 1\)/);
  // Tu tai lai 60s/lan, chi khi tab hien.
  assert.match(src, /60_000/);
  assert.match(src, /document\.visibilityState !== "visible"/);
});

test("trang online hien cham xanh + lan online tuong doi va gio SG", () => {
  const src = trang();
  assert.match(src, /Đang online/);
  assert.match(src, /dot-pulse/);
  assert.match(src, /formatRelative\(u\.last_seen_at/);
  assert.match(src, /formatDateTimeSG\(u\.last_seen_at\)/);

  const dinhDang = read("../src/lib/format.ts");
  assert.match(dinhDang, /export function formatRelative/);
  assert.match(dinhDang, /export function formatDateTimeSG/);
  assert.match(dinhDang, /timeZone: "Asia\/Ho_Chi_Minh"/);
  assert.match(dinhDang, /Chưa từng online/);
});

test("dieu huong quan tri co muc User online", () => {
  const src = read("../src/components/AdminShell.tsx");
  assert.match(src, /href: "\/admin\/users\/online"/);
  assert.match(src, /nhan: "User online"/);
});

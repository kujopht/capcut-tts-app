/*
 * Lượt xem + lượt tim truyện.
 *
 * Og chốt: mở trang truyện tính 1 lượt xem. Tim thì 1 người 1 lần, bật/tắt
 * được. Bài này khóa bằng kiểm tĩnh như các bài admin/AI khác: API lộ đủ
 * hàm, thẻ thư viện + trang chi tiết vẽ đủ số, nút Tim + beacon đếm xem
 * tồn tại và giữ đúng hành vi của nút theo dõi (lạc quan, hoàn lại khi lỗi,
 * chưa đăng nhập thì dẫn tới đăng nhập).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const codeOnly = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const api = read("../src/lib/api.ts");
const thuVien = read("../src/app/library/page.tsx");
const trangChu = read("../src/app/page.tsx");
const chiTiet = read("../src/app/novels/[id]/page.tsx");
const nutTim = read("../src/components/LikeButton.tsx");
const beacon = read("../src/components/NovelViewBeacon.tsx");

// ------------------------------------------------------------------ API

test("Novel mang view_count + like_count; getNovel mang like + view_count", () => {
  assert.match(api, /view_count\?: number;/);
  assert.match(api, /like_count\?: number;/);
  assert.match(api, /like\?: LikeState;/);
  assert.match(api, /export interface LikeState \{\s+liked: boolean;\s+like_count: number;\s+\}/);
});

test("api co recordNovelView (POST view, nuot loi) + social co likeStory/unlikeStory", () => {
  assert.match(api, /recordNovelView: \(novelId: string\)/);
  assert.match(api, /\/api\/novels\/\$\{encodeURIComponent\(novelId\)\}\/view/);
  assert.match(api, /likeStory: \(novelId: string\)/);
  assert.match(api, /unlikeStory: \(novelId: string\)/);
  assert.match(api, /\/api\/novels\/\$\{encodeURIComponent\(novelId\)\}\/like/);
});

// ------------------------------------------------------------- the + trang chi tiet

test("the thu vien (grid + list) ve ca luot xem va luot tim, thieu so thi coi nhu 0", () => {
  const soThe = (thuVien.match(/n\.view_count \?\? 0/g) || []).length;
  const soTim = (thuVien.match(/n\.like_count \?\? 0/g) || []).length;
  assert.equal(soThe, 2, "grid + list, moi dang mot cho ve luot xem");
  assert.equal(soTim, 2, "grid + list, moi dang mot cho ve luot tim");
  assert.match(thuVien, /title="Lượt xem"/);
  assert.match(thuVien, /title="Lượt tim"/);
});

test("trang chu showcase ve ca luot xem va luot tim", () => {
  assert.match(trangChu, /n\.view_count \?\? 0/);
  assert.match(trangChu, /n\.like_count \?\? 0/);
});

test("trang chi tiet ve luot xem + luot tim, ban nhap thi an (khong co du lieu)", () => {
  assert.match(chiTiet, /data\?\.view_count !== undefined/);
  assert.match(chiTiet, /data\?\.like/);
  assert.match(chiTiet, /<LikeButton/);
  assert.match(chiTiet, /<NovelViewBeacon novelId=\{novel\.novel_id\} \/>/);
});

// ------------------------------------------------------------- nut Tim + beacon

test("LikeButton: lac quan, hoan lai khi loi, so may chu thang, khach thi dan toi dang nhap", () => {
  const code = codeOnly(nutTim);
  assert.match(code, /setDaTim\(!truoc\)/);
  assert.match(code, /setDaTim\(truoc\)/);
  assert.match(code, /setDaTim\(ra\.liked\)/);
  assert.match(code, /setSo\(ra\.like_count\)/);
  assert.match(code, /social\.unlikeStory\(targetId\)/);
  assert.match(code, /social\.likeStory\(targetId\)/);
  assert.match(code, /loginHref\(pathname\)/);
  assert.match(code, /aria-pressed=\{daTim\}/);
});

test("beacon: mot effect ban mot lan khi mount, khong render gi", () => {
  assert.match(beacon, /useRef\(false\)/);
  assert.match(beacon, /api\.recordNovelView\(novelId\)/);
  assert.match(beacon, /return null;/);
});

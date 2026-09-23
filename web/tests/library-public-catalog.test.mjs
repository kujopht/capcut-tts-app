/**
 * Kiểm định Thư viện Công khai, Semantics Tủ sách cá nhân & Cập nhật Trang chủ.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const library = () => read("../src/app/library/page.tsx");
const home = () => read("../src/app/page.tsx");
const catalog = () => read("../src/lib/catalog.ts");

test("Thư viện: Tải danh mục tác phẩm thật bằng api.listNovels, không chỉ theo dõi cá nhân", () => {
  const src = library();
  assert.match(src, /api\.listNovels\(/, "Thư viện phải gọi api.listNovels để tải tác phẩm thật");
  assert.match(src, /social\.followedStories\(/, "Vẫn giữ followedStories cho mục cá nhân");
});

test("Thư viện: Phân chia 3 tab rành mạch gồm Fanfic, Sách tuyển tập và Tủ sách cá nhân", () => {
  const src = library();
  assert.match(src, /Fanfic &amp; Tiểu thuyết/);
  assert.match(src, /Sách &amp; Tuyển tập/);
  assert.match(src, /Tủ sách của tôi/);
});

test("Thư viện: Truyền coverUrl={n.cover_url} vào NovelCover để hiển thị ảnh bìa thật", () => {
  const src = library();
  assert.match(src, /<NovelCover[\s\S]{0,120}coverUrl=\{n\.cover_url\}/);
});

test("Thư viện: Có đầy đủ bộ lọc tìm kiếm, vũ trụ fandom, audio và chế độ hiển thị", () => {
  const src = library();
  assert.match(src, /searchQuery/);
  assert.match(src, /fandomFilter/);
  assert.match(src, /audioFilter/);
  assert.match(src, /sortMode/);
  assert.match(src, /viewMode/);
});

test("Thư viện: Tab Sách & Tuyển tập có trạng thái trung thực, không bịa sách giả", () => {
  const src = library();
  assert.match(src, /Tuyển tập & Tuyển tập đặc biệt đang được tuyển chọn/);
  assert.ok(!src.includes("test-b-"), "Không được chứa mock sách giả");
});

test("Trang chủ: Showcase Truyện mới dùng dữ liệu thật, đã loại bỏ TEST_NOVELS và TEST_POSTS", () => {
  const src = home();
  assert.ok(!src.includes("TEST_NOVELS"), "TEST_NOVELS phải bị loại bỏ");
  assert.ok(!src.includes("TEST_POSTS"), "TEST_POSTS phải bị loại bỏ");
  assert.match(src, /novels\.slice\(0,\s*3\)/);
  assert.match(src, /novelHasAudio\(n\)/);
  assert.match(src, /formatAuthor\(n\)/);
  assert.match(src, /formatChapterCount\(/);
});

test("Trang chủ: Cột bên phải đổi tên thành 'Bài đăng mới', phân tách với Thông báo cá nhân", () => {
  const src = home();
  assert.match(src, /Bài đăng mới/);
  assert.ok(!src.includes("Cập nhật mới"));
  assert.ok(!src.includes("Thông báo & Bài viết"));
});

test("Catalog helpers: Kiểm định nhận diện audio, fandom và số chương", () => {
  const src = catalog();
  assert.match(src, /export function novelHasAudio/);
  assert.match(src, /export function novelFandom/);
  assert.match(src, /export function formatAuthor/);
  assert.match(src, /export function formatChapterCount/);
});

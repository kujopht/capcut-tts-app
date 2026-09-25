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

test("Thư viện: Tải danh mục tác phẩm thật (phân trang ở máy chủ), không chỉ theo dõi cá nhân", () => {
  /*
    Product UX Sprint 2: tai bang `api.browseNovels` (phan trang, loc o may
    chu) + anh chup kho (`lib/catalogSnapshot.ts`). KHONG con am tham roi ve
    `api.listNovels` khi loi — ban truoc lam vay nen loi mang bi GIAU va trang
    tai het kho khong phan trang; nay loi hien kem nut "Thử lại".
  */
  const src = library();
  assert.match(src, /api\s*\.browseNovels\(/, "Thư viện phải tải tác phẩm thật từ backend");
  assert.match(src, /taiAnhChupKho/, "dùng ảnh chụp kho chung");
  assert.ok(!/api\.listNovels\(/.test(src), "không được âm thầm rơi về listNovels");
  assert.match(src, /<ErrorState message=\{loi\} onRetry=\{thuLai\}/, "lỗi phải hiện, có Thử lại");
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
  // Sprint 2: trang thai nam TREN URL (`lib/libraryQuery.ts`), khong con la
  // nam `useState` roi rac — Back/Forward va chia se lien ket giu dung bo loc.
  const q = read("../src/lib/libraryQuery.ts");
  for (const truong of ["q: string", "fandom: string", "audio: LocAudio", "status: LocTrangThai", "sort: SapXep", "view: KieuXem", "page: number"]) {
    assert.ok(q.includes(truong), `thiếu trường ${truong}`);
  }
  const src = library();
  assert.match(src, /docTuUrl\(searchParams\)/, "trang phải đọc trạng thái từ URL");
  assert.match(src, /router\.push\(href, \{ scroll: false \}\)/, "đổi bộ lọc phải vào lịch sử (Back được)");
  assert.match(src, /router\.replace\(href, \{ scroll: false \}\)/, "gõ tìm không được nhồi lịch sử");
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

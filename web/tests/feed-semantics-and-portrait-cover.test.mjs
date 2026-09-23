import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const homeSrc = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const novelSrc = readFileSync(new URL("../src/app/novels/[id]/page.tsx", import.meta.url), "utf8");
const librarySrc = readFileSync(new URL("../src/app/library/page.tsx", import.meta.url), "utf8");
const novelCoverSrc = readFileSync(new URL("../src/components/NovelCover.tsx", import.meta.url), "utf8");
const cssSrc = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("Homepage Hero chứa đúng 2 cột tinh gọn Truyện mới và Bài đăng mới, không có khối cộng đồng bên dưới", () => {
  // homepage contains Truyện mới
  assert.match(homeSrc, /<strong>Truyện mới<\/strong>/);

  // homepage contains Bài đăng mới
  assert.match(homeSrc, /<strong>Bài đăng mới<\/strong>/);

  // homepage does NOT contain heading Cộng đồng đang nói gì
  assert.ok(
    !homeSrc.includes("Cộng đồng đang nói gì"),
    "Trang chủ không được chứa tiêu đề Cộng đồng đang nói gì"
  );

  // homepage does NOT contain heading Cập nhật mới
  assert.ok(
    !homeSrc.includes("Cập nhật mới"),
    "Trang chủ không được chứa tiêu đề Cập nhật mới"
  );

  // Bài đăng mới uses communityPosts
  assert.match(
    homeSrc,
    /danhSachBaiDang\.map\(\(bai\)/,
    "Bài đăng mới phải map từ danhSachBaiDang (communityPosts)"
  );
  assert.match(
    homeSrc,
    /<HomeHeroShowcase novels=\{novels\} communityPosts=\{communityPosts\} \/>/,
    "Truyền communityPosts vào HomeHeroShowcase"
  );

  // Link header/action của Bài đăng mới dẫn sang /community
  assert.match(
    homeSrc,
    /href="\/community"[^>]*className="showcase-more"[^>]*>\s*Xem cộng đồng →/,
    "Hành động cột Bài đăng mới dẫn sang /community"
  );

  // maximum 3 novels
  assert.match(
    homeSrc,
    /const danhSachTruyen = novels\.slice\(0,\s*3\);/,
    "Truyện mới lấy tối đa 3 tác phẩm"
  );

  // maximum 3 posts
  assert.match(
    homeSrc,
    /const danhSachBaiDang = communityPosts\.slice\(0,\s*3\);/,
    "Bài đăng mới lấy tối đa 3 bài viết"
  );

  // no duplicated community post in Home
  const matches = (homeSrc.match(/communityPosts\.slice/g) || []).length;
  assert.equal(matches, 1, "communityPosts chỉ được dùng tại một vị trí duy nhất trong Hero");
  assert.ok(
    !homeSrc.includes("community-preview-grid"),
    "Không còn khối community-preview-grid trùng lặp ở dưới"
  );
});

test("Chuẩn hoá tỷ lệ ảnh bìa: 16:9 landscape cho catalog/browse và 2:3 portrait cho trang chi tiết", () => {
  // NovelCover hỗ trợ size="portrait" và "landscape"
  assert.match(
    novelCoverSrc,
    /size\?:\s*"card"\s*\|\s*"wide"\s*\|\s*"thumb"\s*\|\s*"portrait"\s*\|\s*"landscape"/,
    "NovelCover hỗ trợ size portrait và landscape"
  );

  // .cover-portrait định nghĩa aspect-ratio: 2 / 3
  assert.match(
    cssSrc,
    /\.cover-portrait\s*\{\s*aspect-ratio:\s*2\s*\/\s*3;\s*\}/,
    "CSS .cover-portrait phải có aspect-ratio: 2 / 3"
  );

  // .cover-landscape định nghĩa aspect-ratio: 16 / 9
  assert.match(
    cssSrc,
    /\.cover-landscape\s*\{\s*aspect-ratio:\s*16\s*\/\s*9;/,
    "CSS .cover-landscape phải có aspect-ratio: 16 / 9"
  );

  // .novel-head-cover .cover có aspect-ratio: 2 / 3 (Detail page giữ 2:3 portrait)
  assert.match(
    cssSrc,
    /\.novel-head-cover \.cover\s*\{[\s\S]*?aspect-ratio:\s*2\s*\/\s*3;/,
    "Bìa trang chi tiết truyện phải có aspect-ratio: 2 / 3"
  );

  // .lib-card-cover-wrap có aspect-ratio: 16 / 9 (Catalog chuyển sang 16:9 landscape)
  assert.match(
    cssSrc,
    /\.lib-card-cover-wrap\s*\{[\s\S]*?aspect-ratio:\s*16\s*\/\s*9;/,
    "Khung bìa thư viện /library phải có aspect-ratio: 16 / 9"
  );

  // Trang chi tiết truyện /novels/[id] gọi size="portrait"
  assert.match(
    novelSrc,
    /<NovelCover[\s\S]*?size="portrait"/,
    "Trang chi tiết truyện gọi NovelCover với size portrait"
  );

  // Trang thư viện /library gọi size="landscape"
  assert.match(
    librarySrc,
    /<NovelCover[\s\S]*?size="landscape"/,
    "Trang thư viện gọi NovelCover với size landscape"
  );
});

test("Bố cục responsive của bìa trang chi tiết truyện cân đối trên desktop và mobile", () => {
  // Desktop .novel-head đặt cột bìa 200px
  assert.match(
    cssSrc,
    /\.novel-head\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*200px\)\s*minmax\(0,\s*1fr\);/,
    "Desktop .novel-head đặt cột bìa 200px"
  );

  // .novel-head-cover max-width 200px
  assert.match(
    cssSrc,
    /\.novel-head-cover\s*\{\s*width:\s*100%;\s*max-width:\s*200px;\s*\}/,
    ".novel-head-cover max-width 200px"
  );

  // Mobile small screen giới hạn max-width 160px để không choán màn hình
  assert.match(
    cssSrc,
    /\.novel-head-cover\s*\{\s*max-width:\s*160px;\s*margin:\s*0 auto;\s*\}/,
    "Mobile .novel-head-cover max-width 160px và căn giữa"
  );
});

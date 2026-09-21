import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const homeSrc = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const novelSrc = readFileSync(new URL("../src/app/novels/[id]/page.tsx", import.meta.url), "utf8");
const librarySrc = readFileSync(new URL("../src/app/library/page.tsx", import.meta.url), "utf8");
const novelCoverSrc = readFileSync(new URL("../src/components/NovelCover.tsx", import.meta.url), "utf8");
const cssSrc = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("HomeHeroShowcase không mượn bài viết cộng đồng và chỉ dùng EDITORIAL_UPDATES", () => {
  // HomeHeroShowcase chỉ nhận novels, không nhận posts
  assert.ok(
    /function HomeHeroShowcase\(\s*\{\s*novels,?\s*\}\s*:\s*\{\s*novels:\s*Novel\[\];?\s*\}\)/.test(homeSrc),
    "HomeHeroShowcase không nhận posts prop"
  );

  // HomeHeroShowcase Column 2 ("Cập nhật mới") maps EDITORIAL_UPDATES
  assert.match(
    homeSrc,
    /<strong>Cập nhật mới<\/strong>[\s\S]*?EDITORIAL_UPDATES\.map/,
    "Cột 2 Cập nhật mới phải map EDITORIAL_UPDATES"
  );

  // HomeHeroShowcase Column 2 link leads to /library (Khám phá) instead of /community
  assert.match(
    homeSrc,
    /href="\/library"[^>]*className="showcase-more"[^>]*>\s*Khám phá →/,
    "Cột 2 dẫn tới /library"
  );

  // HomeHeroShowcase invocation on home page does not pass posts
  assert.match(
    homeSrc,
    /<HomeHeroShowcase novels=\{novels\} \/>/,
    "Gọi HomeHeroShowcase chỉ truyền novels"
  );
});

test("Cộng đồng đang nói gì chỉ dùng communityPosts và có trạng thái rỗng trung thực", () => {
  // Khu vực Cộng đồng đang nói gì
  assert.match(
    homeSrc,
    /IconMegaphone size=\{20\} \/> Cộng đồng đang nói gì/,
    "Có khu vực Cộng đồng đang nói gì"
  );

  // Dùng communityPosts.map(TheCongDong)
  assert.match(
    homeSrc,
    /communityPosts\.length > 0 \? \([\s\S]*?communityPosts\.map\(\(bai\)/,
    "Hiển thị bài viết từ communityPosts"
  );

  // Hiển thị trạng thái rỗng trung thực KeTrongGon khi không có bài viết
  assert.match(
    homeSrc,
    /<KeTrongGon[\s\S]*?icon="💬"[\s\S]*?text="Chưa có thảo luận mới từ cộng đồng\."/,
    "Hiển thị KeTrongGon khi communityPosts rỗng"
  );

  // EDITORIAL_UPDATES không xuất hiện trong khu vực Cộng đồng (slice từ thẻ h2 tới lối tắt)
  const lastIndex = homeSrc.lastIndexOf("IconMegaphone size={20} /> Cộng đồng đang nói gì");
  assert.ok(lastIndex !== -1, "Tìm thấy tiêu đề Cộng đồng đang nói gì");
  const communitySection = homeSrc.slice(
    lastIndex,
    homeSrc.indexOf("home-discovery-strip", lastIndex)
  );
  assert.ok(
    !communitySection.includes("EDITORIAL_UPDATES"),
    "EDITORIAL_UPDATES không được mượn vào khu vực cộng đồng"
  );
});

test("Chuẩn hoá tỷ lệ ảnh bìa chân dung 2:3 trên toàn bộ hệ thống", () => {
  // NovelCover hỗ trợ size="portrait"
  assert.match(
    novelCoverSrc,
    /size\?:\s*"card"\s*\|\s*"wide"\s*\|\s*"thumb"\s*\|\s*"portrait"/,
    "NovelCover hỗ trợ size portrait"
  );

  // .cover-portrait định nghĩa aspect-ratio: 2 / 3
  assert.match(
    cssSrc,
    /\.cover-portrait\s*\{\s*aspect-ratio:\s*2\s*\/\s*3;\s*\}/,
    "CSS .cover-portrait phải có aspect-ratio: 2 / 3"
  );

  // .novel-head-cover .cover có aspect-ratio: 2 / 3
  assert.match(
    cssSrc,
    /\.novel-head-cover \.cover\s*\{[\s\S]*?aspect-ratio:\s*2\s*\/\s*3;/,
    "Bìa trang chi tiết truyện phải có aspect-ratio: 2 / 3"
  );

  // .lib-card-cover-wrap có aspect-ratio: 2 / 3
  assert.match(
    cssSrc,
    /\.lib-card-cover-wrap\s*\{[\s\S]*?aspect-ratio:\s*2\s*\/\s*3;/,
    "Khung bìa thư viện /library phải có aspect-ratio: 2 / 3"
  );

  // Trang chi tiết truyện /novels/[id] gọi size="portrait"
  assert.match(
    novelSrc,
    /<NovelCover[\s\S]*?size="portrait"/,
    "Trang chi tiết truyện gọi NovelCover với size portrait"
  );

  // Trang thư viện /library gọi size="portrait"
  assert.match(
    librarySrc,
    /<NovelCover[\s\S]*?size="portrait"/,
    "Trang thư viện gọi NovelCover với size portrait"
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

/**
 * Animation YouTube — UX polish (phan lien quan TRINH PHAT).
 *
 * Cung phong cach voi cac bai kiem khac trong thu muc nay: doc THANG source
 * va khang dinh cac dac diem quan trong bang regex, khong dung DOM gia lap
 * (repo khong co jsdom/testing-library, khong co loader TypeScript cho
 * `node --test` — xem package.json).
 *
 * PHAM VI DA THU HEP so voi ban goc tren `feature/animation-youtube-polish-v1`.
 * Ban goc con kiem ca nhung thu KHONG CO tren nhanh chinh, nen giu lai se chi
 * tao ra bai kiem noi doi:
 * - `components/YoutubeUrlPreview.tsx` (xem truoc URL YouTube khi nhap form)
 *   — tep nay chua duoc mang sang.
 * - Luong "Sua tap" + gan truyen goc trong `animation/[id]/page.tsx` — bo cuc
 *   trang series tren nhanh chinh khac ban tren nhanh do.
 * - Header CSP trong `next.config.mjs` — nhanh chinh khong cau hinh CSP;
 *   them mot chinh sach CSP toan site la viec RIENG, khong nen di lot vao
 *   mot thay doi trinh phat.
 * - Khung trang tri `.yt-cinema` (Fanfic Cinema Shell) — trang xem tren nhanh
 *   chinh giu bo cuc rieng cua no (dieu huong tap luon hien, bo chon tap, dong
 *   nguon Trusted Channels, chia se, binh luan) va CO Y khong bi thay the.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const youtubeUrl = () => read("../src/lib/youtubeUrl.ts");
const youtubeIframeApi = () => read("../src/lib/youtubeIframeApi.ts");
const facadePlayer = () => read("../src/components/YouTubeFacadePlayer.tsx");
const playerControls = () => read("../src/components/YouTubePlayerControls.tsx");
const watchPage = () => read("../src/app/animation/watch/[id]/page.tsx");
const globalsCss = () => read("../src/app/globals.css");

// -- Phan tich URL YouTube phia trinh duyet --------------------------------

test("lib/youtubeUrl.ts: parseYoutubeVideoId khop CUNG danh sach domain voi server", () => {
  const src = youtubeUrl();
  assert.match(src, /YOUTUBE_ID_RE\s*=\s*\/\^\[A-Za-z0-9_-\]\{11\}\$\//);
  for (const host of [
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
    "youtu.be", "www.youtu.be",
  ]) {
    assert.match(src, new RegExp(`"${host.replace(/\./g, "\\.")}"`),
      `thiếu host ${host} trong YOUTUBE_HOSTS`);
  }
  assert.match(src, /KHONG BAO GIO tai\/goi mang toi YouTube/i);
});

test("lib/youtubeUrl.ts: khong bao gio goi mang, chi phan tich chuoi (khong co fetch/XMLHttpRequest)", () => {
  const src = youtubeUrl();
  assert.doesNotMatch(src, /\bfetch\(/);
  assert.doesNotMatch(src, /XMLHttpRequest/);
});

test("lib/youtubeUrl.ts: youtubeThumbnailUrl tro thang toi i.ytimg.com (khong qua backend)", () => {
  assert.match(youtubeUrl(), /https:\/\/i\.ytimg\.com\/vi\/\$\{videoId\}\/hqdefault\.jpg/);
});

test("components/YouTubeFacadePlayer.tsx: dung chung mot youtubeThumbnailUrl, khong tu dinh nghia lai", () => {
  const src = facadePlayer();
  assert.match(src, /import\s*\{[^}]*youtubeThumbnailUrl[^}]*\}\s*from\s*"@\/lib\/youtubeUrl"/);
  assert.doesNotMatch(src, /export function youtubeThumbnailUrl/);
});

// -- Trang thai video khong xem duoc ---------------------------------------

test("lib/youtubeIframeApi.ts: ho tro onError voi tai lieu ro ma loi YouTube", () => {
  const src = youtubeIframeApi();
  assert.match(src, /onError\?\s*:\s*\(event:\s*\{\s*data:\s*number\s*\}\)\s*=>\s*void/);
  assert.match(src, /100 = video khong ton tai/);
  assert.match(src, /101\/150 = chu video/);
});

test("lib/youtubeIframeApi.ts: thongBaoLoiVideo anh xa dung ma loi YouTube sang tieng Viet", () => {
  const src = youtubeIframeApi();
  assert.match(src, /export function thongBaoLoiVideo\(maLoi: number\): string/);
  assert.match(src, /case 100:[\s\S]{0,120}không còn tồn tại/);
  assert.match(src, /case 101:\s*\n\s*case 150:[\s\S]{0,150}tắt tính năng phát trên trang khác/);
});

test("components/YouTubeFacadePlayer.tsx: wire onError vao YT.Player va hien trang thai loi thay vi iframe hong", () => {
  const src = facadePlayer();
  assert.match(src, /onError:\s*\(e\)\s*=>\s*\{/);
  assert.match(src, /thongBaoLoiVideo\(e\.data\)/);
  assert.match(src, /setGiaiDoan\("loi-video"\)/);
  assert.match(src, /giaiDoan === "loi-video"/);
  assert.match(src, /role="alert"/);
});

test("components/YouTubeFacadePlayer.tsx: trang thai loi la state cuc bo, khong dat lai dong bo trong than effect", () => {
  const src = facadePlayer();
  assert.match(src, /const \[thongDiepLoi, setThongDiepLoi\] = useState/);
  // Dat setState dong bo trong than effect vi pham react-hooks/set-state-in-effect.
  assert.doesNotMatch(src, /useEffect\(\(\) => \{\s*set(GiaiDoan|ThongDiepLoi)/);
});

test("animation/watch/[id]/page.tsx: dieu huong tap KHONG phu thuoc trang thai loi cua trinh phat", () => {
  // Trang xem khong con giu state loi nao ca (chuyen het vao component) — nav
  // vi vay LUON hien khong dieu kien, nam TRUOC diem gan trinh phat.
  const src = watchPage();
  const viTriDieuHuong = src.indexOf('aria-label="Điều hướng tập"');
  const viTriTrinhPhat = src.indexOf("<YouTubeFacadePlayer");
  assert.ok(viTriDieuHuong > 0, "không tìm thấy khối điều hướng tập");
  assert.ok(viTriTrinhPhat > 0, "không tìm thấy điểm gắn trình phát");
  assert.ok(
    viTriDieuHuong < viTriTrinhPhat,
    "điều hướng tập phải nằm TRƯỚC điểm gắn trình phát, không lồng trong điều kiện nào phụ thuộc nó",
  );
  assert.doesNotMatch(src, /loiVideo/);
});

// -- Nguon nhung an toan ----------------------------------------------------

test("lib/youtubeUrl.ts: YOUTUBE_EMBED_ORIGIN la hang so co dinh, dung cho CSP/test", () => {
  assert.match(youtubeUrl(), /export const YOUTUBE_EMBED_ORIGIN\s*=\s*"https:\/\/www\.youtube-nocookie\.com"/);
});

test("components/YouTubeFacadePlayer.tsx: CHI nhung youtube-nocookie.com, khong bao gio youtube.com/embed", () => {
  const src = facadePlayer();
  // Chi xet KHOI iframe THAT SU render (bo qua docstring dau file, noi co
  // nhac lai `youtube.com/embed` nhu MOT VI DU VE VIEC KHONG lam).
  const khoiIframe = src.slice(src.indexOf("const goc ="));
  assert.match(khoiIframe, /\$\{YOUTUBE_EMBED_ORIGIN\}\/embed\/\$\{videoId\}/);
  assert.doesNotMatch(khoiIframe, /youtube\.com\/embed/);
});

// -- Trang xem: nhung phan bo cuc PHAI con nguyen --------------------------

test("animation/watch/[id]/page.tsx: hiển thị Truyện gốc công khai khi series có related_novel_id", () => {
  const src = watchPage();
  assert.match(src, /series\.related_novel_id\s*\?\s*\(/);
  assert.match(src, /Truyện gốc/);
  assert.match(src, /href=\{`\/novels\/\$\{series\.related_novel_id\}`\}/);
});

test("animation/watch/[id]/page.tsx: dong nguon Trusted Channels + link video goc con nguyen, khong bia ten kenh", () => {
  const src = watchPage();
  assert.match(
    src,
    /episode\.source_channel_title \? `Nguồn: \$\{episode\.source_channel_title\} · ` : ""/,
  );
  assert.match(src, /Xem video gốc trên YouTube/);
});

test("animation/watch/[id]/page.tsx: bo chon tap, chia se va binh luan con nguyen", () => {
  const src = watchPage();
  assert.match(src, /aria-label="Chọn tập để xem"/);
  assert.match(src, /Danh sách tập \(\{chiSoHienTai\}\/\{episodes\.length\}\)/);
  assert.match(src, /onClick=\{chiaSe\}/);
  assert.match(src, /<EpisodeComments episodeId=\{episode\.episode_id\} \/>/);
});

// -- CSS ------------------------------------------------------------------

test("globals.css: .yt-facade (iframe THAT) khong bi thanh dieu khien moi thu nho/cat them", () => {
  const css = globalsCss();
  // `.yt-facade` van giu nguyen aspect-ratio 16:9 + kich thuoc day du — thanh
  // dieu khien chi nam BEN DUOI, khong co CSS nao ep lai kich thuoc iframe.
  assert.match(css, /\.yt-facade \{[\s\S]{0,120}aspect-ratio: 16 \/ 9;[\s\S]{0,60}width: 100%;/);
});

test("components/YouTubePlayerControls.tsx: hien thoi gian MM:SS qua dongHo tu lib/time", () => {
  assert.match(playerControls(), /import\s*\{\s*dongHo\s*\}\s*from\s*"@\/lib\/time"/);
});

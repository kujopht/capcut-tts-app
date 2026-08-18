/**
 * Animation YouTube V1 — UX polish (feature/animation-youtube-polish-v1).
 *
 * Cung phong cach voi cac bai kiem khac trong thu muc nay: doc THANG source
 * va khang dinh cac dac diem quan trong bang regex, khong dung DOM gia lap
 * (repo khong co jsdom/testing-library, khong co loader TypeScript cho
 * `node --test` — xem package.json).
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
const urlPreview = () => read("../src/components/YoutubeUrlPreview.tsx");
const seriesPage = () => read("../src/app/animation/[id]/page.tsx");
const watchPage = () => read("../src/app/animation/watch/[id]/page.tsx");
const nextConfig = () => read("../next.config.mjs");
const globalsCss = () => read("../src/app/globals.css");

// -- Phan 2: xem truoc URL YouTube truoc khi gui ---------------------------

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

test("components/YoutubeUrlPreview.tsx: URL rong khong hien gi, URL khong hop le hien loi ro rang", () => {
  const src = urlPreview();
  assert.match(src, /if\s*\(!raw\)\s*return null;/);
  assert.match(src, /if\s*\(!videoId\)\s*\{[\s\S]{0,200}Không đọc được ID video YouTube/);
  assert.match(src, /role="alert"/);
});

test("components/YoutubeUrlPreview.tsx: hien anh dai dien qua youtubeThumbnailUrl, khong tai/proxy video", () => {
  const src = urlPreview();
  assert.match(src, /import\s*\{[^}]*youtubeThumbnailUrl[^}]*\}\s*from\s*"@\/lib\/youtubeUrl"/);
  assert.match(src, /src=\{youtubeThumbnailUrl\(videoId\)\}/);
  assert.doesNotMatch(src, /<video/);
  assert.doesNotMatch(src, /<iframe/);
});

test("lib/youtubeUrl.ts: youtubeThumbnailUrl tro thang toi i.ytimg.com (khong qua backend)", () => {
  assert.match(youtubeUrl(), /https:\/\/i\.ytimg\.com\/vi\/\$\{videoId\}\/hqdefault\.jpg/);
});

test("components/YouTubeFacadePlayer.tsx: dung chung mot youtubeThumbnailUrl, khong tu dinh nghia lai", () => {
  const src = facadePlayer();
  assert.match(src, /import\s*\{[^}]*youtubeThumbnailUrl[^}]*\}\s*from\s*"@\/lib\/youtubeUrl"/);
  assert.doesNotMatch(src, /export function youtubeThumbnailUrl/);
});

// -- Phan 1 + 2: form Them tap / Sua tap co xem truoc + khoa khi URL sai ---

test("animation/[id]/page.tsx: form Thêm tập dùng YoutubeUrlPreview và khoá nút gửi khi URL sai", () => {
  const src = seriesPage();
  assert.match(src, /import\s*\{\s*YoutubeUrlPreview\s*\}\s*from\s*"@\/components\/YoutubeUrlPreview"/);
  assert.match(src, /<YoutubeUrlPreview url=\{urlTap\}\s*\/>/);
  assert.match(src, /urlTapHopLe\s*=\s*!urlTap\.trim\(\)\s*\|\|\s*parseYoutubeVideoId\(urlTap\.trim\(\)\)\s*!==\s*null/);
  assert.match(src, /disabled=\{dangXuLy \|\| !urlTap\.trim\(\) \|\| !urlTapHopLe\}/);
});

test("animation/[id]/page.tsx: co luong SUA tap goi api.updateAnimationEpisode (Phần 1)", () => {
  const src = seriesPage();
  assert.match(src, /api\.updateAnimationEpisode\(\s*dangSuaTapId,\s*\{/);
  assert.match(src, /title:\s*suaTenTap/);
  assert.match(src, /order_index:\s*suaThuTuTap/);
  // URL moi la TUY CHON khi sua — khong bat nguoi dung nhap lai URL cu.
  assert.match(src, /suaUrlTap\.trim\(\)\s*\?\s*\{\s*youtube_url:\s*suaUrlTap\.trim\(\)\s*\}\s*:\s*\{\}/);
});

test("animation/[id]/page.tsx: form Sửa tập cũng xem trước URL và khoá nút khi URL sai", () => {
  const src = seriesPage();
  const at = src.indexOf("Sửa tập");
  assert.ok(at > 0, "không tìm thấy form Sửa tập");
  const doan = src.slice(at, at + 2500);
  assert.match(doan, /<YoutubeUrlPreview url=\{suaUrlTap\}\s*\/>/);
  assert.match(doan, /disabled=\{dangXuLy \|\| !suaUrlTapHopLe\}/);
});

test("animation/[id]/page.tsx: khong cho phep nhap iframe/embed HTML tuy y (khong co dangerouslySetInnerHTML)", () => {
  assert.doesNotMatch(seriesPage(), /dangerouslySetInnerHTML/);
});

// -- Phan 4: gan truyen goc (related_novel_id) -----------------------------

test("animation/[id]/page.tsx: co UI (khong bắt buộc) gắn series với truyện qua api.updateAnimationSeries", () => {
  const src = seriesPage();
  assert.match(src, /api\.listNovels\(true\)/);
  assert.match(src, /<select[\s\S]{0,60}id="series-novel"/);
  assert.match(src, /Không gắn với truyện nào/);
  assert.match(src,
    /api\.updateAnimationSeries\(series\.series_id,\s*\{[\s\S]{0,120}related_novel_id:\s*suaTruyenGoc/);
});

test("animation/watch/[id]/page.tsx: hiển thị Truyện gốc công khai khi series có related_novel_id", () => {
  const src = watchPage();
  assert.match(src, /series\.related_novel_id\s*\?\s*\(/);
  assert.match(src, /Truyện gốc/);
  assert.match(src, /href=\{`\/novels\/\$\{series\.related_novel_id\}`\}/);
});

// -- Trusted Channels: nguon goc canh trinh phat -----------------------------

test("animation/watch/[id]/page.tsx: co khoi nguon goc TACH BIET voi thanh dieu khien, luon dan toi dung video YouTube", () => {
  const src = watchPage();
  assert.match(src, /className="yt-cinema-source/, "thiếu khối .yt-cinema-source riêng cho nguồn gốc");
  assert.match(src,
    /href=\{`https:\/\/www\.youtube\.com\/watch\?v=\$\{episode\.external_id\}`\}/,
    "liên kết YouTube gốc phải dùng ĐÚNG external_id của tập đang xem, không hard-code");
  assert.match(src, /target="_blank"/);
  assert.match(src, /rel="noreferrer"/);
});

test("animation/watch/[id]/page.tsx: chi hien 'Nguồn: <kênh>' khi THAT SU biet ten kenh, khong bia", () => {
  const src = watchPage();
  assert.match(src, /episode\.source_channel_title\s*\?\s*`Nguồn:\s*\$\{episode\.source_channel_title\}/,
    "phải đọc source_channel_title thật của tập, không hard-code một tên kênh");
});

test("lib/api.ts: AnimationEpisode co source_channel_id/source_channel_title (Trusted Channels)", () => {
  const src = read("../src/lib/api.ts");
  const at = src.indexOf("export interface AnimationEpisode");
  const than = src.slice(at, src.indexOf("}", at));
  assert.match(than, /source_channel_id:\s*string;/);
  assert.match(than, /source_channel_title:\s*string;/);
});

// -- Phan 3: trang thai video khong xem duoc --------------------------------

test("lib/youtubeIframeApi.ts: ho tro onError voi tai lieu ro ma loi YouTube", () => {
  const src = youtubeIframeApi();
  assert.match(src, /onError\?\s*:\s*\(event:\s*\{\s*data:\s*number\s*\}\)\s*=>\s*void/);
  assert.match(src, /100 = video khong ton tai/);
  assert.match(src, /101\/150 = chu video/);
});

test("lib/youtubeIframeApi.ts: thongBaoLoiVideo anh xa dung ma loi YouTube sang tieng Viet", () => {
  // Chuyen tu watch/[id]/page.tsx sang lib/youtubeIframeApi.ts trong
  // animation-player-v2-custom-controls, de YouTubeFacadePlayer dung chung.
  const src = youtubeIframeApi();
  assert.match(src, /export function thongBaoLoiVideo\(maLoi: number\): string/);
  assert.match(src, /case 100:[\s\S]{0,120}không còn tồn tại/);
  assert.match(src, /case 101:\s*\n\s*case 150:[\s\S]{0,150}tắt tính năng phát trên trang khác/);
});

test("components/YouTubeFacadePlayer.tsx: wire onError vao YT.Player va hien trang thai loi thay vi iframe hong", () => {
  // Vong doi YT.Player (bao gom onError) chuyen tu trang xem vao CHINH
  // component nay trong animation-player-v2-custom-controls.
  const src = facadePlayer();
  assert.match(src, /onError:\s*\(e\)\s*=>\s*\{/);
  assert.match(src, /thongBaoLoiVideo\(e\.data\)/);
  assert.match(src, /setGiaiDoan\("loi-video"\)/);
  assert.match(src, /giaiDoan === "loi-video"/);
  assert.match(src, /role="alert"/);
});

test("animation/watch/[id]/page.tsx: dieu huong tap KHONG phu thuoc trang thai loi cua trinh phat", () => {
  // Trang xem khong con giu state loi nao ca (chuyen het vao component) — nav
  // vi vay LUON hien khong dieu kien, nam TRUOC diem gan trinh phat.
  const src = watchPage();
  const viTriDieuHuong = src.indexOf('aria-label="Điều hướng tập"');
  const viTriStage = src.indexOf('className="yt-cinema-stage"');
  assert.ok(viTriDieuHuong > 0, "không tìm thấy khối điều hướng tập");
  assert.ok(viTriStage > 0, "không tìm thấy điểm gắn trình phát");
  assert.ok(
    viTriDieuHuong < viTriStage,
    "điều hướng tập phải nằm TRƯỚC điểm gắn trình phát, không lồng trong điều kiện nào phụ thuộc nó",
  );
  assert.doesNotMatch(src, /loiVideo/);
});

test("components/YouTubeFacadePlayer.tsx: trang thai loi la state cuc bo, khong dat lai dong bo trong than effect", () => {
  const src = facadePlayer();
  assert.match(src, /const \[thongDiepLoi, setThongDiepLoi\] = useState/);
  // Dat setState dong bo trong than effect vi pham react-hooks/set-state-in-effect.
  assert.doesNotMatch(src, /useEffect\(\(\) => \{\s*set(GiaiDoan|ThongDiepLoi)/);
});

// -- Phan 5: CSP + nguon nhung an toan --------------------------------------

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

test("next.config.mjs: CSP co frame-src/connect-src/script-src toi thieu cho YouTube, khong dung wildcard rong", () => {
  const src = nextConfig();
  assert.match(src, /frame-src 'self' https:\/\/www\.youtube-nocookie\.com/);
  assert.match(src, /script-src 'self' 'unsafe-inline' https:\/\/www\.youtube\.com/);
  // Chi xet MANG CSP THAT SU dung (bo qua docstring giai thich phia tren, noi
  // nhac lai `*.youtube.com`/`*.google.com` nhu VI DU VE VIEC KHONG mo rong).
  const khoiCSP = src.slice(src.indexOf("const CSP = ["));
  assert.doesNotMatch(khoiCSP, /\*\.youtube\.com/);
  assert.doesNotMatch(khoiCSP, /\*\.google\.com/);
});

test("next.config.mjs: co header CSP + cac header bao ve co ban qua headers()", () => {
  const src = nextConfig();
  assert.match(src, /key:\s*"Content-Security-Policy"/);
  assert.match(src, /object-src 'none'/);
  assert.match(src, /frame-ancestors 'self'/);
  assert.match(src, /key:\s*"X-Content-Type-Options",\s*value:\s*"nosniff"/);
});

test("next.config.mjs: CSP noi long eval/websocket CHI o dev, khong anh huong production", () => {
  const src = nextConfig();
  assert.match(src, /const isDev = process\.env\.NODE_ENV !== "production"/);
  assert.match(src, /\$\{isDev \? " 'unsafe-eval'" : ""\}/);
});

// -- Fanfic Cinema Shell: khung trang tri quanh trinh phat -----------------

test("animation/watch/[id]/page.tsx: khung .yt-cinema bao quanh toolbar/stage/foot, khong thay the chung", () => {
  const src = watchPage();
  assert.match(src, /<div className="yt-cinema">/);
  assert.match(src, /yt-cinema-toolbar/);
  assert.match(src, /className="yt-cinema-stage">/);
  assert.match(src, /className="yt-cinema-foot">/);
});

test("globals.css: .yt-cinema la khung TRANG TRI, khong dat overflow/clip len iframe", () => {
  const css = globalsCss();
  const at = css.indexOf(".yt-cinema {");
  assert.ok(at > 0, "không tìm thấy .yt-cinema");
  const khoi = css.slice(at, css.indexOf("}", at));
  // Trang tri chi la padding/border/box-shadow — KHONG co overflow/clip-path
  // o chinh khoi nay (do se cat iframe con nam sau trong `.yt-cinema-stage`).
  assert.doesNotMatch(khoi, /overflow:/);
  assert.doesNotMatch(khoi, /clip-path:/);
  assert.match(khoi, /padding:/);
});

test("globals.css: .yt-facade (iframe THAT) khong bi component cinema shell thu nho/cat them", () => {
  const css = globalsCss();
  // `.yt-facade` van giu nguyen aspect-ratio 16:9 + kich thuoc day du — cinema
  // shell chi bao NGOAI bang padding, khong co CSS nao ep lai kich thuoc iframe.
  assert.match(css, /\.yt-facade \{[\s\S]{0,120}aspect-ratio: 16 \/ 9;[\s\S]{0,60}width: 100%;/);
});

test("components/YouTubePlayerControls.tsx: hien thoi gian MM:SS qua dongHo tu lib/time (Phan V2)", () => {
  // Thanh tien do THU DONG cua V1 (`.yt-cinema-progress`) da duoc thay bang
  // thanh dieu khien tuong tac cua V2 — xem
  // tests/animation-player-v2-custom-controls.test.mjs de biet chi tiet.
  const src = read("../src/components/YouTubePlayerControls.tsx");
  assert.match(src, /import\s*\{\s*dongHo\s*\}\s*from\s*"@\/lib\/time"/);
});

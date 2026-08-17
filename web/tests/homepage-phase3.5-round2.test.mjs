/*
 * Fanfic World Visual Renaissance — Phase 3.5 vòng 2 (2026-08).
 *
 * BOI CANH: vòng 1 đã xong Hero contrast + ảnh minh hoạ Truyện/Animation/CTA
 * sáng tác. Vòng này giải quyết ba phần còn lại có thể làm KHÔNG cần sinh
 * thêm ảnh (ngân sách ảnh của vòng này đã dùng hết theo yêu cầu người dùng):
 *
 *   (8)  Hover micro-interaction cho portal — lớp nghệ thuật + icon phản ứng
 *        rất nhẹ, không neon/glow lớn.
 *   (12) "Bảng vàng tuần" ở trang chủ — CHỈ dùng API bảng xếp hạng thật đã
 *        có (`GET /api/leaderboard?mode=weekly`), không bịa hai hạng mục
 *        "tác giả"/"độc giả" tách riêng vì backend không có.
 *   (13) "Animation mới" chỉ có MỘT series thật không còn nằm lọt thỏm
 *        trong lưới — dùng lại đúng mẫu "một mục nổi bật" đã có cho Truyện
 *        (`.story-card-featured`).
 *
 * (9) Pointer-depth và (10) AmbientScene: đánh giá riêng, không cần test CSS
 * ở đây (xem báo cáo — AmbientScene đã đủ thưa, giữ nguyên không đổi).
 *
 * Chuẩn hoá CRLF -> LF (xem bài học ở `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const home = () => read("../src/app/page.tsx");

const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

function rule(selector) {
  const text = css();
  const at = text.search(
    new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{`, "m"),
  );
  assert.notEqual(at, -1, `không tìm thấy quy tắc ${selector}`);
  return text.slice(at, text.indexOf("}", at));
}

/* ===================================== Phan 8: hover micro-interaction ==== */

test(".portal-art dich/phong RAT nhe khi ru chuot vao .portal-card (2-4px, scale <= 1.01)", () => {
  const art = rule(".portal-art");
  assert.match(art, /transition:[^;]*transform/);
  const hover = rule(".portal-card:hover .portal-art");
  const m = hover.match(/scale\(([\d.]+)\)/);
  assert.ok(m, "thiếu scale trên .portal-art lúc hover");
  assert.ok(Number(m[1]) <= 1.01, `scale ${m[1]} vượt trần 1.01`);
  assert.match(hover, /translateY\(-[234]px\)/, "art layer phải dịch 2-4px");
});

test(".portal-icon phan ung rat nhe khi ru chuot vao ca cong, khong scale lon", () => {
  const icon = rule(".portal-icon");
  assert.match(icon, /transition:[^;]*transform/);
  const hover = rule(".portal-card:hover .portal-icon");
  const m = hover.match(/scale\(([\d.]+)\)/);
  if (m) assert.ok(Number(m[1]) <= 1.1, `icon scale ${m[1]} quá lớn cho "subtle"`);
});

test("KHONG co box-shadow/neon glow moi tren hover portal (chi border/value/transform)", () => {
  const hoverArt = rule(".portal-card:hover .portal-art");
  const hoverIcon = rule(".portal-card:hover .portal-icon");
  for (const block of [hoverArt, hoverIcon]) {
    assert.ok(!/box-shadow|filter:\s*drop-shadow|blur\(/.test(block));
  }
});

test("reduced-motion: .portal-card, .portal-art, .portal-icon deu ve transform:none khi hover", () => {
  const c = css();
  const at = c.indexOf("@media (prefers-reduced-motion: reduce)");
  const khoi = c.slice(at, at + 1400);
  assert.match(
    khoi,
    /\.portal-card:hover,\s*\.portal-card:hover \.portal-art,\s*\.portal-card:hover \.portal-icon\s*\{\s*transform:\s*none;/,
  );
});

/* ============================================ Phan 12: Bang vang tuan ===== */

test("trang chu goi getLeaderboard(weekly) — KHONG bia hai hang muc tac gia/doc gia rieng", () => {
  const src = codeOnly(home());
  assert.match(src, /api\.getLeaderboard\("weekly",\s*BANG_VANG_COUNT,\s*0\)/);
  // Chi MOT section "Bảng vàng tuần" — khong co section "Tác giả nổi bật"/
  // "Độc giả năng nổ" tách rời bịa ra (backend không tách được theo mode).
  assert.ok(!/Tác giả nổi bật/.test(src));
  assert.ok(!/Độc giả năng nổ/.test(src));
});

test("Bảng vàng tuần TU AN khi rong (khong ai co XP trong tuan) — khong ve hop rong", () => {
  const src = codeOnly(home());
  assert.match(src, /bangVangTuan\.length > 0 \? \(/);
});

test("HangBangVang dung LAI dung lop .lb-* cua trang /leaderboard — khong bia CSS rieng", () => {
  const src = codeOnly(home());
  const at = src.indexOf("function HangBangVang");
  assert.notEqual(at, -1);
  const than = src.slice(at, at + 900);
  for (const cls of ["lb-row", "lb-rank", "lb-info", "lb-xp"]) {
    assert.match(than, new RegExp(`"${cls}"`), `HangBangVang thiếu class ${cls}`);
  }
});

test("HangBangVang dung CosmeticFrame cho avatar_frame — 'existing rank cosmetics if available'", () => {
  const src = codeOnly(home());
  const at = src.indexOf("function HangBangVang");
  const than = src.slice(at, at + 800);
  assert.match(than, /CosmeticFrame/);
  assert.match(than, /avatar_frame/);
});

test("khong them polling nao cho Bảng vàng tuần — chi mot lan goi trong Promise.all chung", () => {
  const src = codeOnly(home());
  assert.ok(!/setInterval/.test(src));
});

/* =========================================== Phan 13: Animation featured == */

test("Animation CHI MOT series that: dung the noi bat (khong con lot trong luoi anim-grid)", () => {
  const src = codeOnly(home());
  assert.match(src, /animationSeries\.length === 1 \? \(/);
  assert.match(src, /<TheAnimNoiBat series=\{animationSeries\[0\]\}\s*\/>/);
});

test("TheAnimNoiBat dung LAI dung .story-card-featured* — cung ngu phap voi 'mot muc duy nhat' cua Truyen", () => {
  const src = codeOnly(home());
  const at = src.indexOf("function TheAnimNoiBat");
  assert.notEqual(at, -1);
  const than = src.slice(at, src.indexOf("export default function HomePage"));
  for (const cls of [
    "story-card-featured",
    "story-card-featured-cover",
    "story-card-featured-body",
    "story-card-featured-title",
  ]) {
    assert.match(than, new RegExp(`"${cls}"`), `TheAnimNoiBat thiếu class ${cls}`);
  }
  // KHONG bia mot bo class rieng "anim-featured*" — dung dung bo da co.
  assert.ok(!/anim-featured/.test(than));
});

test("nhieu hon MOT series thi VAN dung luoi anim-grid-shelf cu (khong doi hanh vi da dung)", () => {
  const src = codeOnly(home());
  assert.match(src, /animationSeries\.length > 1 \? \(/);
  const at = src.indexOf("animationSeries.length > 1");
  const than = src.slice(at, at + 600);
  assert.match(than, /anim-grid anim-grid-shelf/);
});

test("ca hai nhanh (1 va >1) déu rong thi tra null — khong ve gi khi khong co series", () => {
  const src = codeOnly(home());
  const at = src.indexOf("animationSeries.length === 1 ? (");
  assert.notEqual(at, -1);
  const than = src.slice(at, at + 1700);
  assert.match(than, /\) : null\}/);
});

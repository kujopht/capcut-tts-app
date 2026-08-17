/*
 * Homepage Hub V2 + khung sang o tim (2026-08) — rang buoc cua vong thiet ke
 * nay. Chuan hoa CRLF -> LF truoc khi so khop chuoi chinh xac (checkout tren
 * Windows co the ghi CRLF, xem bai hoc o `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const home = () => read("../src/app/page.tsx");

/** Bo chu thich truoc khi quet — xem `redesign.test.mjs`. */
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

/* ==================================================== khung sang o tim ==== */

test("khung nang luong: dung transform xoay + mask kep, KHONG dung JS rAF", () => {
  const css_ = css();
  assert.match(css_, /@keyframes tim-vien-xoay \{\s*to \{ transform: rotate\(1turn\); \}/);
  assert.match(css_, /mask-composite: exclude;/);
  assert.match(css_, /-webkit-mask-composite: xor;/);
  // KHONG dung requestAnimationFrame o component tim kiem cho hieu ung trang tri.
  for (const f of ["../src/components/SearchOverlay.tsx", "../src/components/SiteSearch.tsx"]) {
    assert.ok(!read(f).includes("requestAnimationFrame"), `${f} dùng rAF cho hiệu ứng`);
  }
});

test("khung nang luong ap dung cho CA nut go gon lan hop tim mo rong", () => {
  const css_ = css();
  assert.match(css_, /\.tim-nut::before,\s*\n\.tim-hop::before \{/);
});

test("nut go gon: sang len muot khi ro chuot (transition, khong nhay cung)", () => {
  const nut = rule(".tim-nut");
  assert.match(nut, /position: relative;/);
  assert.match(nut, /box-shadow:.*var\(--brand-glow\)/);
  assert.match(nut, /transition:[\s\S]*box-shadow/);
  const hover = rule(".tim-nut:hover");
  assert.match(hover, /box-shadow:/);
});

test("hop tim mo rong: vien sang hon IDLE va co mach nhe (opacity, khong scale rung)", () => {
  const css_ = css();
  // dung lastIndexOf: ".tim-hop::before {" cung xuat hien o dong 2 cua quy
  // tac chung ".tim-nut::before,\n.tim-hop::before {" phia truoc — chi quy
  // tac RIENG (sau cung) moi co mach nhe + inset:0.
  const at = css_.lastIndexOf(".tim-hop::before {");
  assert.notEqual(at, -1);
  const than = css_.slice(at, css_.indexOf("}", at));
  assert.match(than, /animation: tim-vien-xoay[^,]+,\s*tim-vien-mach/);
  assert.match(than, /inset: 0;/, "phải dùng inset:0 (không âm) vì .tim-hop có overflow:hidden");
});

test("trang thai DANG TIM tang nhip nang luong, khong ve rieng mot thanh tien do", () => {
  const css_ = css();
  assert.match(css_, /\.tim-hop\.tim-hop-dang-tim::before \{/);
  const overlay = read("../src/components/SearchOverlay.tsx");
  assert.match(overlay, /tim-hop-dang-tim/);
  assert.match(overlay, /trangThai === "dang-tai"/);
});

test("placeholder o tim phan anh toan bo nen tang, khong chi truyen", () => {
  const btn = read("../src/components/SiteSearch.tsx");
  const overlay = read("../src/components/SearchOverlay.tsx");
  for (const src of [btn, overlay]) {
    assert.match(src, /Tìm truyện, tác giả, Animation/);
  }
});

test("moi hieu ung khung sang deu nam duoi mai reduced-motion toan cuc, khong tu y !important rieng", () => {
  // Rang buoc CHUNG (redesign.test.mjs) da khoa: `*, *::before, *::after` bi
  // ep `animation-duration: 0.01ms !important` duoi `prefers-reduced-motion:
  // reduce`. O day chi can xac nhan cac keyframes/animation MOI khong tu y
  // dat `!important` rieng — neu co thi se THANG ca luat toan cuc do va pha
  // rang buoc "tat duoc bang prefers-reduced-motion".
  const css_ = css();
  const at = css_.indexOf(".tim-nut::before,");
  const khoi = css_.slice(at, css_.indexOf("tim-hop-dang-tim::before {") + 200);
  assert.ok(!khoi.includes("!important"), "khung sáng dùng !important — sẽ thắng cả luật reduced-motion");
});

/* ==================================================== homepage hub ======== */

test("hero moi la mot vung noi dung, khong phai chia doi 50/50", () => {
  for (const m of css().matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (/hero/i.test(m[1])) {
      assert.ok(
        !/grid-template-columns:\s*1fr\s+1fr/.test(m[2]),
        `khu hero chia đôi 50/50: ${m[1].trim().slice(0, 60)}`,
      );
    }
  }
});

test("luoi tinh nang LUON ve, khong phu thuoc so truyen/animation/cong dong", () => {
  const src = home();
  const at = src.indexOf("<LuoiTinhNang");
  assert.notEqual(at, -1);
  // Phai nam TRUOC nhanh dieu kien cua ke "Đang nổi bật" (loading/error/rong) —
  // nghia la khong bi mot `&&`/ternary nao cua du lieu truyen bao quanh.
  assert.ok(at < src.indexOf('id="home-noi-bat"'));
  const truoc = src.slice(Math.max(0, at - 200), at);
  assert.ok(!/animationSeries\.length|communityPosts\.length|novels\.length/.test(truoc),
    "lưới tính năng bị một điều kiện dữ liệu bao quanh");
});

test("6 the tinh nang CHI tro toi duong da co that", () => {
  const src = home();
  const atDanhSach = src.indexOf("DANH_SACH_TINH_NANG");
  const than = src.slice(atDanhSach, src.indexOf("function LuoiTinhNang"));
  const hrefs = [...than.matchAll(/href:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(hrefs, [
    "/fanfic", "/animation", "/studio", "/community", "/write", "/image-studio",
  ]);
  // Va cac thu muc route nay phai THAT SU ton tai trong web/src/app.
  for (const href of hrefs) {
    const dir = new URL(`../src/app${href}`, import.meta.url);
    assert.ok(existsSync(dir), `route ${href} không tồn tại`);
  }
});

test("ke Animation moi / cong dong TU AN khi rong, khong ve hop rong to", () => {
  const src = home();
  assert.match(src, /animationSeries\.length > 0 \? \(/);
  assert.match(src, /communityPosts\.length > 0 \? \(/);
  // Rong thi tra `null` (khong ve gi), khong phai mot `EmptyState` day du —
  // `EmptyState` chi con danh cho ke truyen (ke quan trong nhat).
  const soLanEmptyState = (src.match(/<EmptyState/g) ?? []).length;
  assert.equal(soLanEmptyState, 1, "chỉ đúng MỘT EmptyState (ke truyện)");
});

test("khong bia so lieu backend khong ho tro (luot xem/nghe/theo doi gia)", () => {
  const src = home();
  for (const bia of [
    "lượt đọc", "lượt nghe", "lượt xem", "nổi bật nhất",
    "người theo dõi", "đang xem cùng", "trending",
  ]) {
    assert.ok(!src.includes(bia), `trang chủ bịa số liệu: ${bia}`);
  }
  // KHONG co ke "Mới cập nhật"/"Nghe ngay" rieng — hai muc nay doi hoi du
  // lieu backend KHONG ho tro (xem docstring dau `page.tsx`). Bo chu thich
  // truoc khi quet, vi chinh docstring do nhac lai hai cum tu nay khi giai
  // thich ly do KHONG dung (khong phai chuoi hien ra man hinh).
  const ma = codeOnly(src);
  assert.ok(!ma.includes("Mới cập nhật"));
  assert.ok(!ma.includes("Nghe ngay"));
});

test("khach vang lai KHONG thay dai thanh vien/tiep tuc — chi CTA dang nhap o Hero", () => {
  const src = home();
  const atHero = src.indexOf("function Hero(");
  const thanHero = src.slice(atHero, src.indexOf("function DaiThanhVien"));
  assert.match(thanHero, /!daDangNhap \? \(/);
  assert.match(thanHero, /hero-v2-guest-hint/);

  const atThanhVien = src.indexOf("function DaiThanhVien(");
  const thanThanhVien = src.slice(atThanhVien, src.indexOf("interface TinhNang"));
  assert.match(thanThanhVien, /if \(!gamification\) return null;/);

  // "Tiếp tục của bạn" chỉ dựng bên trong nhánh `daDangNhap ? (`.
  const atTiepTuc = src.indexOf('id="home-tiep-tuc"');
  const truocDo = src.slice(Math.max(0, atTiepTuc - 200), atTiepTuc);
  assert.match(truocDo, /daDangNhap \? \(/);
});

test("da dang nhap nhung chua co gi de tiep tuc: mot dong onboarding GON, khong phai khoi rong to", () => {
  const src = home();
  assert.match(src, /<KeTrongGon/);
  const atKe = src.indexOf("function KeTrongGon");
  const than = src.slice(atKe, src.indexOf("function TheCongDong"));
  assert.match(than, /shelf-empty-compact/);
  // KHONG dung `EmptyState` day du (qua to) cho truong hop nay.
  assert.ok(!than.includes("<EmptyState"));
});

test("ke cong dong dung API cong khai /api/feed, khong bia du lieu", () => {
  const src = home();
  assert.match(src, /social\.feed\(/);
  assert.match(src, /import\s*\{[^}]*api,\s*\n?\s*social,/s);
});

test("moi ke co section rieng voi aria-labelledby", () => {
  const src = home();
  for (const id of [
    "home-hero-title", "home-tiep-tuc", "home-tinh-nang", "home-noi-bat",
    "home-animation", "home-cong-dong", "home-the", "home-kham-pha-nhanh",
    "home-tac-gia",
  ]) {
    assert.ok(
      src.includes(`id="${id}"`),
      `thiếu id "${id}" cho aria-labelledby`,
    );
  }
});

test("responsive: hero va luoi tinh nang co quy tac rieng o mobile (640px)", () => {
  const text = css();
  const at = text.indexOf("@media (max-width: 640px)");
  assert.notEqual(at, -1);
  const mobile = text.slice(at);
  assert.match(mobile, /\.hero-v2 \{/);
  assert.match(mobile, /\.hero-v2-cta \.btn \{ flex: 1 1 auto; \}/);
});

test("trang chu KHONG dung style inline (media query khong voi toi duoc)", () => {
  assert.ok(!/style=\{\{/.test(home()), "trang chủ còn style inline");
});

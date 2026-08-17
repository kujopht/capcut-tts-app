/*
 * Navigation Active Frame — Visual + Motion Correction V2 (2026-08).
 *
 * BOI CANH: vong truoc tuyen bo vach dieu huong (`.nav-vach`) da "truot"
 * giua cac muc, nhung nguoi dung KHONG thay no di chuyen — chi thay vach cu
 * bien mat roi vach moi xuat hien tai dich. Nguyen nhan goc: `NavIndicator`
 * an (`return null`) moi khi `o.moc !== moc`, dieu kien nay THANG NGAY khi
 * route doi (truoc khi layout effect kip do lai) — React GO HAN the
 * `<span class="nav-vach">` roi MOUNT LAI mot the HOAN TOAN MOI tai dich.
 * Transition CSS khong bao gio co co hoi chay vi no can HAI khung hinh da ve
 * tren CUNG MOT phan tu de noi suy, ma phan tu do da bi thay the.
 *
 * Chuan hoa CRLF -> LF (xem bai hoc o `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const navIndicator = () => read("../src/components/NavIndicator.tsx");

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

/* ===================================== kien truc: MOT vach dung chung ===== */

test("chi CO MOT <NavIndicator> dung chung, khong ve rieng tren tung muc", () => {
  const navAuth = read("../src/components/NavAuth.tsx");
  const soLan = (navAuth.match(/<NavIndicator/g) ?? []).length;
  assert.equal(soLan, 1, "phải đúng MỘT NavIndicator dùng chung");
});

test("NavAuth nam trong layout GOC — khong bi remount giua cac route", () => {
  // `NavLinks`/`NavIndicator` phai duoc goi tu `app/layout.tsx` (ben ngoai
  // `{children}`), khong phai tu mot layout con hay tung `page.tsx` — neu
  // khong Next se go va gan lai ca thanh dieu huong moi lan doi route.
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /<NavLinks\s*\/>/);
  const atMain = layout.indexOf("<main");
  const atNav = layout.indexOf("<NavLinks");
  assert.ok(atNav !== -1 && atMain !== -1 && atNav < atMain,
    "NavLinks phải nằm ngoài <main> (vùng {children} đổi theo route)");
});

/* ============================== loi da sua: KHONG go/gan lai theo route === */

test("SUA LOI GOC: vien thuoc KHONG con an theo o.moc !== moc (gay go/gan lai)", () => {
  const src = codeOnly(navIndicator());
  // Dieu kien an cu — neu con ton tai nghia la loi da tai phat.
  assert.ok(!/o\.moc !== moc/.test(src),
    "vẫn còn so sánh o.moc !== moc để ẩn — đây chính là nguyên nhân gây mount lại");
  // Dieu kien MOI: chi an khi CHINH route hien tai khong co muc nao khop.
  assert.match(src, /if \(!moc \|\| !o\) return null;/);
});

test("vien thuoc LUON dung toa do MOI NHAT da do, khong doi o.moc khop moc moi ve", () => {
  // Sau dong `if (!moc || !o) return null;`, phan con lai phai dung `o.x`/`o.w`
  // truc tiep — khong co mot nhanh `if (o.moc !== moc)` nao khac chen vao giua.
  const src = codeOnly(navIndicator());
  const atGuard = src.indexOf("if (!moc || !o) return null;");
  assert.notEqual(atGuard, -1);
  const sau = src.slice(atGuard, src.indexOf("return (", atGuard));
  assert.ok(!/o\.moc/.test(sau), "vẫn còn nhánh so sánh o.moc giữa guard và render");
});

/* ==================================== mau/chat lieu trang thai nghi (idle) */

test("vien thuoc KHONG con quang trang bloom (da bo cac lop mau #ffffff*)", () => {
  const than = rule(".nav-vach");
  assert.ok(!/#ffffff/i.test(than),
    "vẫn còn thành phần màu trắng thuần — đây là nguyên nhân của quầng trắng bị phản hồi");
});

test("noi that vach la NAVY TOI (tu --bg), khong phai nen sang", () => {
  const than = rule(".nav-vach");
  assert.match(than, /background: color-mix\(in srgb, var\(--bg\)/);
});

test("vien vach pha tron cyan+tim cua khu vuc (--sac-1/--sac-2), KHONG vien trang", () => {
  const than = rule(".nav-vach");
  // Navigation Motion Correction V3: border con 1px (tu 1.25px) — van net,
  // van pha tron sac khu vuc, khong doi mau.
  assert.match(than, /border: 1px solid color-mix\(in srgb, var\(--sac-1/);
  assert.match(than, /var\(--sac-2/);
});

test("V3: KHONG CON box-shadow/glow nao tren vach dang xem — chi vien + nen + chu", () => {
  // Phan hoi V3: ke ca "quang rat nho" cua V2 van bi coi la glow. Phan biet
  // trang thai active gio CHI den tu do tuong phan be mat, vien net, mau chu
  // — khong tu do sang.
  const than = rule(".nav-vach");
  assert.ok(!/box-shadow/.test(than), "vẫn còn box-shadow trên .nav-vach");
});

test("chu muc dang xem la GAN-TRANG (--text), khong con nhan sac rieng", () => {
  const than = rule('.nav-link[aria-current="page"]');
  assert.match(than, /color: var\(--text\)/);
  assert.ok(!/--sac-2/.test(than), "chữ vẫn nhận sắc riêng của khu vực");
});

/* ======================================== chuyen dong: thoi luong + duong cong */

test("thoi luong truot trong khoang 420-560ms, duong cong ep-out co kiem soat", () => {
  const than = rule(".nav-vach");
  const t = Number(than.match(/transform (\d+)ms/)?.[1]);
  const w = Number(than.match(/width (\d+)ms/)?.[1]);
  assert.ok(t >= 420 && t <= 560, `transform ${t}ms ngoài khoảng 420-560`);
  assert.ok(w >= 420 && w <= 560, `width ${w}ms ngoài khoảng 420-560`);
  assert.match(than, /cubic-bezier\(\.22, \.8, \.2, 1\)/);
});

test("vet sang mot lan dung mau khu vuc (cyan/tim), khong con mau trang thuan", () => {
  const than = rule(".nav-vach-streak");
  assert.ok(!/#ffffff[0-9a-f]{0,2}[,;)]/i.test(than.replace(/white/g, "")),
    "vệt sáng vẫn dùng một khối màu trắng thuần");
  assert.match(than, /var\(--sac-1/);
  assert.match(than, /var\(--sac-2/);
  assert.match(than, /animation: sheen \d+ms var\(--ease\) 1\b/);
});

/* ==================================================== reduced motion ====== */

test("reduced motion: vach nhay tuc thi, vet sang tat han, trang thai active van thay ro", () => {
  const c = css();
  const khoi = c.slice(
    c.indexOf("@media (prefers-reduced-motion: reduce)"),
    c.indexOf("@media (prefers-reduced-motion: reduce)") + 4000,
  );
  assert.match(khoi, /\.nav-vach \{ transition: none; \}/);
  assert.match(khoi, /\.nav-vach-streak \{ display: none; \}/);
  // Mau/chu cua trang thai active KHONG bi mai reduced-motion dong lai —
  // chi chuyen dong bi tat, khong phai chinh trang thai active.
  assert.ok(!/\.nav-vach \{ display: none/.test(khoi));
  assert.ok(!/\.nav-link\[aria-current="page"\] \{ display: none/.test(khoi));
});

test("khong dung requestAnimationFrame, van do bang ResizeObserver + useLayoutEffect", () => {
  const src = codeOnly(navIndicator());
  assert.ok(!/requestAnimationFrame/.test(src));
  assert.match(src, /useLayoutEffect/);
  assert.match(src, /ResizeObserver/);
});

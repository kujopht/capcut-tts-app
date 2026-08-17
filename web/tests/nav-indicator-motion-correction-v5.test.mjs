/*
 * Navigation Active Frame — Single Frame + Shape Morph V5 (2026-08).
 *
 * BOI CANH: "Viết truyện" da co khung CTA rieng (`.nav-cta`, vien + nen luon
 * hien). Khi `NavIndicator` dung chung chon no, MOT khung KHAC ve de len
 * CUNG vi tri — "vien trong vien". SUA: (1) NavIndicator "hoa hinh" — do
 * `radius` tu `data-nav-shape` cua chinh phan tu dang do, ve khung CTA gan
 * pill dung hinh dang/vi tri that; (2) `.nav-cta[aria-current="page"]` tat
 * han vien/nen RIENG cua no trong luc dang xem, de vien thuoc dung chung la
 * KHUNG DUY NHAT; (3) mot khoang lang (`data-nav-leaving="write"`) giu vien
 * rieng an THEM mot chut sau khi `aria-current` da mat, cho toi khi vach
 * dung chung THAT SU roi khoi hinh dang CTA — tranh vien rieng hien lai qua
 * som luc vach con dang truot ngang qua vi tri cu.
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
const navAuth = () => read("../src/components/NavAuth.tsx");

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

/* ================== V6: hinh hoc DO THAT, khong con "hinh dang" tra bang == */

test("V6: KHONG con NAV_RADIUS/data-nav-shape — bo goc doc THANG tu getComputedStyle", () => {
  // Xem nav-indicator-motion-correction-v6.test.mjs cho dac ta day du cua co
  // che moi (do x/y/w/h/radius THAT tu getBoundingClientRect/getComputedStyle).
  const src = codeOnly(navIndicator());
  assert.ok(!/NAV_RADIUS/.test(src), "vẫn còn bảng tra NAV_RADIUS — V6 yêu cầu đo thật");
  assert.match(src, /getComputedStyle\(muc\)\.borderTopLeftRadius/);
  const authSrc = codeOnly(navAuth());
  assert.ok(!/data-nav-shape/.test(authSrc), "vẫn còn data-nav-shape — đã đổi sang data-nav-cta (V6)");
});

/* ============================= mot ban sac radius dung CHUNG (Phan 8) ===== */

test("O co truong radius/y/h, tinh CUNG luc voi x/w trong setO — khong tach roi", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /radius:\s*number/);
  assert.match(src, /return \{ moc, x, y, w, h, radius, truot \};/);
});

test(".nav-vach dat border-radius tu o.radius — cung mot nguon voi ca hai rect SVG", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /borderRadius:\s*`\$\{o\.radius\}px`/);
  const rxCount = (src.match(/rx:\s*`\$\{o\.radius\}px`/g) ?? []).length;
  const ryCount = (src.match(/ry:\s*`\$\{o\.radius\}px`/g) ?? []).length;
  assert.equal(rxCount, 2, "phải đúng HAI rect (base + tracer) dùng chung o.radius cho rx");
  assert.equal(ryCount, 2, "phải đúng HAI rect (base + tracer) dùng chung o.radius cho ry");
});

test("rx/ry dat qua CSS style (chuyen dan duoc), khong phai thuoc tinh XML tinh", () => {
  const src = codeOnly(navIndicator());
  assert.ok(!/rx="\d/.test(src), "vẫn còn rx là thuộc tính XML tĩnh — không chuyển dần được");
  assert.ok(!/ry="\d/.test(src), "vẫn còn ry là thuộc tính XML tĩnh — không chuyển dần được");
  assert.match(src, /style=\{\{ rx: `\$\{o\.radius\}px`, ry: `\$\{o\.radius\}px` \} as React\.CSSProperties\}/g);
});

/* ============================ hoat hinh hinh dang: 380-480ms nhu de nghi = */

test(".nav-vach: border-radius chuyen dan CUNG duong cong voi transform, trong khoang hop ly", () => {
  const than = rule(".nav-vach");
  const m = than.match(/border-radius (\d+)ms cubic-bezier\(\.22, \.8, \.2, 1\)/);
  assert.notEqual(m, null, "không tìm thấy transition border-radius đúng easing");
  const ms = Number(m[1]);
  assert.ok(ms >= 380 && ms <= 560, `border-radius ${ms}ms ngoài khoảng hợp lý`);
});

test(".nav-vach-base-stroke va .nav-vach-tracer-stroke deu co transition rx/ry", () => {
  for (const sel of [".nav-vach-base-stroke", ".nav-vach-tracer-stroke"]) {
    const than = rule(sel);
    assert.match(than, /transition:[^;]*\brx\b[^;]*;/, `${sel} thiếu transition cho rx`);
    assert.match(than, /transition:[^;]*\bry\b[^;]*;/, `${sel} thiếu transition cho ry`);
  }
});

/* ==================== khung duy nhat: .nav-cta tat vien rieng luc duoc chon */

test(".nav-cta[aria-current=page] tat han background/border-color rieng (trong suot)", () => {
  const than = rule('.nav-cta[aria-current="page"]');
  assert.match(than, /background:\s*transparent/);
  assert.match(than, /border-color:\s*transparent/);
});

test("hover luc DANG la trang hien tai KHONG lam vien rieng hien lai (tranh vien-trong-vien khi ru chuot)", () => {
  const than = rule('.nav-cta[aria-current="page"]:hover');
  assert.match(than, /background:\s*transparent/);
  assert.match(than, /border-color:\s*transparent/);
});

test(".nav-cta co transition CO DINH, KHONG co transition-delay rieng (delay do co che khac dam nhiem)", () => {
  const than = rule(".nav-cta");
  assert.match(than, /transition:\s*background 200ms var\(--ease\), border-color 200ms var\(--ease\);/);
});

test("dau cham CTA (::before) khong bi dong theo trang thai duoc chon", () => {
  const c = codeOnly(css());
  assert.ok(!/\.nav-cta\[aria-current="page"\]::before/.test(c),
    "::before bị ghi đè riêng cho trạng thái được chọn — dấu chấm phải giữ nguyên");
});

/* ============================ khoang lang: roi CTA khong hien vien qua som */

test("globals.css: [data-nav-leaving=write] giu vien CTA trong suot du aria-current da mat", () => {
  const than = rule('body[data-nav-leaving="write"] .nav-cta:not([aria-current="page"])');
  assert.match(than, /background:\s*transparent/);
  assert.match(than, /border-color:\s*transparent/);
});

test("NavIndicator: co hang so khoang lang, >= thoi luong width dai nhat cua .nav-vach", () => {
  const srcIndicator = codeOnly(navIndicator());
  const grace = Number(srcIndicator.match(/CTA_LEAVE_GRACE_MS\s*=\s*(\d+)/)?.[1]);
  assert.ok(Number.isFinite(grace), "không tìm thấy CTA_LEAVE_GRACE_MS");
  const than = rule(".nav-vach");
  const w = Number(than.match(/width (\d+)ms/)?.[1]);
  assert.ok(grace >= w, `CTA_LEAVE_GRACE_MS (${grace}ms) phải >= width transition (${w}ms)`);
});

test("NavIndicator: bat data-nav-leaving CHI khi roi TU muc co data-nav-cta, dung setTimeout tu go, khong requestAnimationFrame", () => {
  // V6: co "la CTA hay khong" tach RIENG khoi hinh hoc (khong con suy tu
  // radius === 999, vi radius gio la mot GIA TRI DO duoc co the trung nhau
  // giua CTA va muc thuong). Doc thang tu `data-nav-cta` — xem NavAuth.tsx.
  const src = codeOnly(navIndicator());
  assert.match(src, /document\.body\.dataset\.navLeaving = "write"/);
  assert.match(src, /muc\.dataset\.navCta !== undefined/);
  assert.match(src, /laCtaTruocRef\.current && !laCta/);
  assert.match(src, /setTimeout\(/);
  assert.ok(!/requestAnimationFrame/.test(src));
});

test("cleanup cua useLayoutEffect KHONG clearTimeout dong ho khoang lang (tranh ket dinh data-nav-leaving)", () => {
  // Bug da tranh: cleanup chay lai o MOI lan doi route (khong chi luc unmount
  // that). Neu no clearTimeout dong ho dang cho ma khong chay callback, thuoc
  // tinh data-nav-leaving="write" se ket dinh vinh vien tren <body>.
  const src = codeOnly(navIndicator());
  const atReturn = src.lastIndexOf("return () => {");
  const cleanup = src.slice(atReturn, src.indexOf("};", atReturn));
  assert.ok(!/clearTimeout\(heTimerRef\.current\)/.test(cleanup),
    "cleanup vẫn clearTimeout dòng chờ khoảng lặng — có thể kẹt data-nav-leaving mãi mãi");
});

/* ========================================= khong dung o cac phan khac ===== */

test("chi CO MOT <NavIndicator> dung chung — V5 khong tach rieng mot NavIndicator khac cho CTA", () => {
  const soLan = (codeOnly(navAuth()).match(/<NavIndicator/g) ?? []).length;
  assert.equal(soLan, 1);
});

test("khong dung requestAnimationFrame o NavIndicator (van do bang ResizeObserver + useLayoutEffect)", () => {
  const src = codeOnly(navIndicator());
  assert.ok(!/requestAnimationFrame/.test(src));
  assert.match(src, /useLayoutEffect/);
  assert.match(src, /ResizeObserver/);
});

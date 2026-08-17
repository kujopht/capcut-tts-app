/*
 * Navigation Active Frame — Exact CTA Geometry V6 (2026-08).
 *
 * BOI CANH: V5 lam CTA "Viết truyện" gan-dung hinh (bo goc 999px tu-clamp,
 * nhung CHIEU CAO cua vien thuoc dung chung (`.nav-vach`) van co dinh 32px
 * qua CSS (`top:50%; margin-top:-16px; height:32px`), gia dinh MOI muc cao
 * bang nhau. Do that tren staging: CTA cao 38.14px, muc thuong ~36.14px —
 * vien thuoc luon THAP hon khung CTA that ~6px, doc ra dung nhu phan hoi
 * "khung khac, nho hon dat de len tren".
 *
 * SUA (V6): NavIndicator do CA BON so (x/y/w/h) tu getBoundingClientRect()
 * THAT cua chinh muc dang xem, VA bo goc tu getComputedStyle(...).
 * borderTopLeftRadius THAT — khong con qua bang tra "hinh dang"
 * (`data-nav-shape`/`NAV_RADIUS` cua V5). Vi tri dung (`translate(x,y)`) +
 * kich thuoc dung (`width`/`height`) + bo goc dung → vien thuoc dung chung
 * TRUNG KHIT khung CTA that, bat ke chieu cao thuc te la bao nhieu.
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

/* =============================== C: do THAT ca bon chieu, khong doan ====== */

test("do_lai() do CA x/y/w/h tu getBoundingClientRect THAT cua muc dang xem", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /const x = b\.left - a\.left \+ hop\.scrollLeft;/);
  assert.match(src, /const y = b\.top - a\.top;/);
  assert.match(src, /const w = b\.width;/);
  assert.match(src, /const h = b\.height;/);
});

test("bo goc doc tu getComputedStyle(muc).borderTopLeftRadius THAT — khong hardcode 999", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /getComputedStyle\(muc\)\.borderTopLeftRadius/);
  assert.ok(!/= 999/.test(src), "vẫn còn hardcode 999 ở đâu đó trong phép đo");
});

test("do KHONG do phan tu con/wrapper chu — do THANG chinh muc (the <a> ngoai cung) tu bang tham chieu", () => {
  // `muc` den tu `bang.current.get(moc)` — CHINH la phan tu <Link> nguoi goi
  // dang ky (xem NavAuth.tsx: ref gan thang len <Link>), khong phai mot the
  // <span> con ben trong.
  const src = codeOnly(navIndicator());
  const atDoLai = src.indexOf("const do_lai = () => {");
  const than = src.slice(atDoLai, src.indexOf("const bao = ", atDoLai) === -1
    ? atDoLai + 1800
    : src.indexOf("const bao = ", atDoLai));
  assert.match(than, /const muc = moc \? bang\.current\.get\(moc\) : undefined;/);
  assert.ok(!/querySelector/.test(than), "đo qua querySelector thay vì bảng tham chiếu trực tiếp");
});

/* ==================== D: vi tri/kich thuoc dat qua GIA TRI DO, khong CSS co dinh */

test(".nav-vach KHONG con top/height co dinh trong CSS — tat ca qua transform/inline", () => {
  const than = codeOnly(rule(".nav-vach"));
  assert.match(than, /top:\s*0;/);
  assert.ok(!/height:\s*\d/.test(than), "vẫn còn height cố định trong CSS");
  assert.ok(!/margin-top:\s*-/.test(than), "vẫn còn margin-top căn giữa cố định kiểu cũ");
});

test("NavIndicator dat transform: translate(x, y) VA width/height tu o.w/o.h — khop khung That", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /transform: `translate\(\$\{o\.x\}px, \$\{o\.y\}px\)`/);
  assert.match(src, /width: `\$\{o\.w\}px`/);
  assert.match(src, /height: `\$\{o\.h\}px`/);
});

test("height co transition CUNG duong cong voi width (ca hai la kich thuoc hinh hoc)", () => {
  const than = rule(".nav-vach");
  assert.match(than, /height \d+ms cubic-bezier\(\.22, \.8, \.2, 1\)/);
});

/* =========================== khoang lang: tach BACH khoi hinh hoc (D+E) === */

test("co 'la CTA' (data-nav-cta) TACH BACH khoi hinh hoc — khong con suy tu gia tri radius", () => {
  const authSrc = codeOnly(navAuth());
  assert.match(authSrc, /data-nav-cta=\{link\.cta \? "" : undefined\}/);
  const src = codeOnly(navIndicator());
  assert.match(src, /const laCta = muc\.dataset\.navCta !== undefined;/);
});

/* ============================================== H: active nav KHONG glow = */

test("khu vien LOP A/tracer KHONG co box-shadow/filter/text-shadow (khong 'phat sang' de gia lam fantasy)", () => {
  for (const sel of [".nav-vach", ".nav-vach-base-stroke", ".nav-vach-tracer-stroke", ".nav-link[aria-current=\"page\"]"]) {
    const than = codeOnly(rule(sel));
    assert.ok(!/box-shadow|text-shadow|filter:\s*drop-shadow|blur\(/.test(than),
      `${sel} vẫn còn glow/shadow — tracer đã đủ chuyển động, không cần phát sáng`);
  }
});

test("chu muc dang xem la GAN-TRANG co dinh, khong gradient/neon underline", () => {
  const than = codeOnly(rule('.nav-link[aria-current="page"]'));
  assert.match(than, /color:\s*var\(--text\)/);
  assert.ok(!/gradient|underline/.test(than));
});

/* ============== hoi quy toan file: khong con dau vet co che V5 cu ========= */

test("khong con bat ky tham chieu nao toi NAV_RADIUS/data-nav-shape trong toan bo web/src", () => {
  for (const f of [
    "../src/components/NavIndicator.tsx",
    "../src/components/NavAuth.tsx",
    "../src/app/globals.css",
  ]) {
    const src = codeOnly(read(f));
    assert.ok(!/NAV_RADIUS/.test(src), `${f} vẫn còn NAV_RADIUS`);
    assert.ok(!/data-nav-shape/.test(src), `${f} vẫn còn data-nav-shape`);
  }
});

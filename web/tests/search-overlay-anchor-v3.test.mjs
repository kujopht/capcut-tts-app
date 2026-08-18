/*
 * Global Search V3 (2026-08, hotfix) — sua loi "thanh ngang khong lo mo duoi
 * navbar" khi bam/focus o tim header.
 *
 * NGUYEN NHAN GOC (do luong that qua DevTools, xem bao cao): `<SearchOverlay>`
 * (`.tim-lop { position: fixed; inset: 0 }`) render BEN TRONG cay DOM cua
 * `<header class="site-header">` — header do co `backdrop-filter` (kinh mo
 * cho thanh dieu huong). Theo dac ta CSS, MOT to tien co `backdrop-filter`
 * (giong `filter`/`transform`/`perspective`/`contain`) tao containing block
 * MOI cho con `position: fixed`. Ket qua: `inset: 0` khong con neo vao
 * KHUNG NHIN that ma neo vao HOP CUA `.site-header` (~106px cao luc do),
 * ep `.tim-hop` (dat giua theo `10vh` CUA HOP DO, khong phai khung nhin
 * that) xep con gan nhu 0px chieu cao — do la thanh ngang mo/toi nguoi
 * dung thay.
 *
 * SUA: `createPortal` ra thang `document.body` (thoat containing block cua
 * header HOAN TOAN, bat ke header co bao nhieu lop hieu ung trong tuong
 * lai) + doi kien truc tu "hop thoai giua trang, co backdrop toi" sang
 * "popover nho neo canh nut tim, KHONG backdrop toan man hinh".
 *
 * Quet MA NGUON, khong render — dung quy uoc repo (khong co jsdom).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const overlay = () => read("../src/components/SearchOverlay.tsx");
const siteSearch = () => read("../src/components/SiteSearch.tsx");

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

/* ============================================ portal thoat containing block */

test("SearchOverlay dung createPortal ra document.body — khong con render INLINE trong cay header", () => {
  const src = codeOnly(overlay());
  assert.match(src, /import\s*\{\s*createPortal\s*\}\s*from\s*"react-dom";/);
  assert.match(src, /return createPortal\(/);
  assert.match(src, /document\.body,\s*\);?\s*$/m, "phải portal đích danh document.body");
});

test("SiteSearch truyen anchorRef (ref cua chinh nut tim) xuong SearchOverlay", () => {
  const src = codeOnly(siteSearch());
  assert.match(src, /const nutRef = useRef<HTMLButtonElement \| null>\(null\);/);
  assert.match(src, /ref=\{nutRef\}/, "nút tìm phải gắn ref để SearchOverlay đo vị trí");
  assert.match(src, /<SearchOverlay\s+mo=\{mo\}\s+onDong=\{[^}]+\}\s+anchorRef=\{nutRef\}\s*\/>/);
});

test("KHONG con RULE .tim-lop (backdrop toan man hinh position:fixed;inset:0) — ten cu co the con trong prose lich su", () => {
  assert.ok(!css().includes(".tim-lop {"), "globals.css vẫn còn định nghĩa rule .tim-lop");
  assert.ok(!overlay().includes('"tim-lop"'), "SearchOverlay.tsx vẫn còn gán className tim-lop");
});

/* =============================================== popover neo canh, khong modal */

test(".tim-pop la popover position:fixed, KHONG co inset:0/width:100vw (khong con la backdrop toan man hinh)", () => {
  const than = codeOnly(rule(".tim-pop"));
  assert.match(than, /position:\s*fixed/);
  assert.ok(!/inset:\s*0\b/.test(than), ".tim-pop không được có inset:0 — đó là dấu hiệu quay lại kiến trúc backdrop toàn màn hình");
  assert.ok(!/width:\s*100vw/.test(than), ".tim-pop không được hard-code width:100vw trong CSS — kích thước phải tính động theo anchor/viewport");
});

test("vi tri/kich thuoc .tim-pop tinh DONG trong JS tu boundingClientRect cua anchor — khong hard-code", () => {
  const src = codeOnly(overlay());
  assert.match(src, /const neo = anchorRef\.current;/, "phải đọc vị trí THẬT từ anchorRef.current");
  assert.match(src, /neo\.getBoundingClientRect\(\)/, "phải đo boundingClientRect của nút tìm, không đoán tọa độ");
  assert.match(src, /useLayoutEffect/, "phải tính vị trí TRƯỚC khi trình duyệt paint (tránh nháy sai vị trí)");
});

test("desktop: rong popover CLAMP trong khoang ~360-560px theo dac ta B2 (khong bao gio het khung nhin)", () => {
  const src = codeOnly(overlay());
  assert.match(src, /Math\.min\(560,\s*Math\.max\(360,\s*vw\s*\*\s*0\.36\)\)/,
    "công thức clamp(360px, 36vw, 560px) không khớp đặc tả B2");
});

test("mobile (<=640px): rong popover = vw - 24 (dac ta B7), KHONG con chiem toan man hinh/height:100vh", () => {
  const src = codeOnly(overlay());
  assert.match(src, /vw\s*-\s*24/, "thiếu công thức width: vw-24 cho màn hẹp");
  assert.ok(!css().includes("height: 100vh"), "vẫn còn CSS ép popover cao 100vh (kiểu hộp thoại toàn màn hình cũ)");
});

test("KHONG con backdrop toi/mo toan trang cho popover desktop (dac ta B5 'prefer NO backdrop')", () => {
  const css_ = codeOnly(css());
  // Truoc day `.tim-lop` co `background: #05070fb8; backdrop-filter: blur(3px);`
  // phu KHAP man hinh — gio khong con phan tu nao dam nhan vai tro do nua.
  assert.ok(!/backdrop-filter:\s*blur\(3px\)/.test(css_), "vẫn còn backdrop-filter toàn màn hình kiểu cũ");
});

test("bam ra ngoai dong bang document mousedown listener (khong con div nen bao phu ca trang)", () => {
  const src = codeOnly(overlay());
  assert.match(src, /document\.addEventListener\("mousedown", bam\)/);
  assert.match(src, /popRef\.current\?\.contains\(dich\)/, "phải kiểm tra bấm có nằm trong popover không");
  assert.match(src, /anchorRef\.current\?\.contains\(dich\)/, "phải kiểm tra bấm có nằm trên chính nút tìm không (tránh đóng-rồi-mở ngay)");
});

/* ==================================================== ban phim khong doi */

test("Escape van dong popup sach se — logic ban phim (Escape/Arrow/Enter) khong bi dong cham", () => {
  const src = codeOnly(overlay());
  assert.match(src, /if \(e\.key === "Escape"\) \{/);
  assert.match(src, /onDong\(\);/);
  assert.match(src, /e\.key === "ArrowDown"/);
  assert.match(src, /e\.key === "ArrowUp"/);
  assert.match(src, /e\.key === "Enter"/);
});

test("vi tri tinh lai khi resize khung nhin trong luc popup dang mo (khong ket qua vi tri cu)", () => {
  const src = codeOnly(overlay());
  assert.match(src, /window\.addEventListener\("resize", dat\)/);
});

test("khong dung requestAnimationFrame cho popup neo canh (van giu ky luat cu cua khu vuc tim kiem)", () => {
  assert.ok(!overlay().includes("requestAnimationFrame"));
});

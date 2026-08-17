/*
 * Nav Indicator Reset V4 — remove gradient fill + SVG stroke tracer (2026-08).
 *
 * NGUYEN NHAN GOC (da xac nhan) cua "quang mau dinh trong khung dang xem":
 * `.nav-vach-streak` (vet sang MOT LAN khi doi route, V1/V3) chay animation
 * `sheen` nhung KHONG dat `animation-fill-mode: forwards`. Het 480ms,
 * `transform` cua no quay ve gia tri TAC GIA (khong khai bao => `none`) THAY
 * VI dung yen o cuoi keyframe (`translateX(280%)`, ra ngoai khung) — mot
 * khoi `background: linear-gradient(cyan, tim)` phu `inset: 0` (KIN long
 * trong) dung yen tai vi tri `transform: none` CHINH LA vung sang bi phan
 * hoi, khong lien quan gi den `box-shadow`.
 *
 * SUA: bo HAN moi background/pseudo-element tren `.nav-vach`. Ca vien tinh
 * lan tracer deu la <rect fill="none"> trong mot <svg> con — `fill="none"`
 * nghia la KHONG CO CACH NAO mot lop mau co the phu kin long trong nua.
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

/* ==================================== loi da bi go: streak khong forwards = */

test("SUA LOI GOC: .nav-vach-streak (vet sang khong fill-mode) da bi XOA HOAN TOAN", () => {
  const c = codeOnly(css());
  assert.ok(!c.includes(".nav-vach-streak"), "vẫn còn .nav-vach-streak trong CSS");
  const t = codeOnly(navIndicator());
  assert.ok(!t.includes("nav-vach-streak"), "vẫn còn nav-vach-streak trong markup");
});

test("SUA LOI GOC: khung tracer conic-gradient + mask (V3) da bi XOA, khong vha lai", () => {
  const c = codeOnly(css());
  assert.ok(!c.includes("nav-tracer-xoay"), "vẫn còn keyframe xoay cũ");
  assert.ok(!/\.nav-vach::before/.test(c), "vẫn còn pseudo-element ::before trên .nav-vach");
  assert.ok(!c.includes("conic-gradient") || !rule(".nav-vach-base-stroke").includes("conic-gradient"));
});

/* ============================ kien truc: MOT svg, hai <rect fill="none"> == */

test("NavIndicator ve DUNG MOT <svg> chua hai <rect fill=\"none\">", () => {
  const src = codeOnly(navIndicator());
  const soLanSvg = (src.match(/<svg/g) ?? []).length;
  assert.equal(soLanSvg, 1, "phải đúng MỘT <svg> trong NavIndicator");
  const rects = [...src.matchAll(/<rect[^>]*\/>/gs)];
  assert.equal(rects.length, 2, "phải đúng HAI <rect> (vạch tĩnh + tracer)");
  for (const r of rects) {
    assert.match(r[0], /fill="none"/, `<rect> thiếu fill="none": ${r[0].slice(0, 60)}`);
  }
});

test("hai rect dung CHUNG hinh hoc (x/y/width/height) — khop chinh xac vien vach", () => {
  // V7: khong con "x=0/width=100%" tinh — hinh hoc gio TUONG MINH, quy ve
  // viewBox (o.w/o.h) va thu vao STROKE_INSET o ca bon canh (xem
  // nav-indicator-motion-correction-v7.test.mjs cho chi tiet).
  const src = codeOnly(navIndicator());
  const base = src.match(/<rect\s+className="nav-vach-base-stroke"[\s\S]*?\/>/)?.[0] ?? "";
  const tracer = src.match(/<rect\s+className="nav-vach-tracer-stroke"[\s\S]*?\/>/)?.[0] ?? "";
  assert.notEqual(base, "");
  assert.notEqual(tracer, "");
  for (const attr of [
    "x={STROKE_INSET}", "y={STROKE_INSET}",
    "width={Math.max(0, o.w - STROKE_INSET * 2)}",
    "height={Math.max(0, o.h - STROKE_INSET * 2)}",
  ]) {
    assert.ok(base.includes(attr), `base-stroke thiếu ${attr}`);
    assert.ok(tracer.includes(attr), `tracer-stroke thiếu ${attr}`);
  }
  assert.match(tracer, /pathLength="100"/);
});

test("chi MOT NavIndicator dung chung trong NavAuth — khong ve rieng tren tung muc", () => {
  const nav = codeOnly(read("../src/components/NavAuth.tsx"));
  const soLan = (nav.match(/<NavIndicator/g) ?? []).length;
  assert.equal(soLan, 1);
});

/* ==================== .nav-vach: KHONG con lop mau/hieu ung nao gay "dinh" = */

test("Phan 12: .nav-vach KHONG co background-image/box-shadow/filter/text-shadow", () => {
  const than = codeOnly(rule(".nav-vach"));
  assert.ok(!/background-image/.test(than));
  assert.ok(!/box-shadow/.test(than));
  assert.ok(!/text-shadow/.test(than));
  assert.ok(!/(?<!-webkit-)filter:/.test(than), "còn filter (không tính -webkit- prefix hợp lệ khác)");
  // `background:` (khong phai background-image) phai la MOT gia tri PHANG —
  // khong duoc chua "gradient" duoi bat ky dang nao.
  const bg = than.match(/\n\s*background:\s*([^;]+);/)?.[1] ?? "";
  assert.ok(!/gradient/.test(bg), `background của .nav-vach vẫn là gradient: ${bg}`);
});

test("khong con pseudo-element nao (::before/::after) tren .nav-vach", () => {
  const c = codeOnly(css());
  assert.ok(!/\.nav-vach::before/.test(c));
  assert.ok(!/\.nav-vach::after/.test(c));
});

/* ===================================== LOP A: vien tinh, khong hoat hinh == */

test("nav-vach-base-stroke: TINH (khong animation/transition mau), stroke ~1-1.25px", () => {
  const than = codeOnly(rule(".nav-vach-base-stroke"));
  assert.ok(!/animation:/.test(than), "vạch tĩnh vẫn có animation");
  assert.match(than, /stroke:/);
  assert.ok(!/box-shadow|filter|drop-shadow/.test(than));
  const w = Number(than.match(/stroke-width:\s*([\d.]+)px/)?.[1]);
  assert.ok(w >= 1 && w <= 1.5, `stroke-width ${w}px ngoài khoảng 1-1.5px`);
});

/* ============================================ LOP B: tracer stroke-dash === */

test("nav-vach-tracer-stroke: dasharray ~14/86 (pathLength=100), dashoffset 0->-100", () => {
  const than = codeOnly(rule(".nav-vach-tracer-stroke"));
  assert.match(than, /stroke-dasharray:\s*14\s+86/);
  assert.ok(!/box-shadow|filter|drop-shadow/.test(than), "tracer vẫn có glow/blur");
  const c = css();
  assert.match(c, /@keyframes nav-tracer-dash \{ to \{ stroke-dashoffset: -100; \} \}/);
});

test("tracer chi doi stroke-dashoffset — KHONG dung transform: rotate (khac V3)", () => {
  const than = codeOnly(rule(".nav-vach-tracer-stroke"));
  assert.ok(!/transform:\s*rotate/.test(than), "vẫn xoay cả SVG — spec yêu cầu chỉ dash chạy");
  assert.match(than, /animation: nav-tracer-dash (\d+(?:\.\d+)?)s linear infinite/);
  const s = Number(than.match(/nav-tracer-dash (\d+(?:\.\d+)?)s/)?.[1]);
  assert.ok(s >= 5.0 && s <= 5.8, `${s}s ngoài khoảng 5.0-5.8s`);
});

test("khong dung requestAnimationFrame, khong dung mask/conic-gradient nao nua cho tracer", () => {
  const t = codeOnly(navIndicator());
  assert.ok(!t.includes("requestAnimationFrame"));
  const c = codeOnly(rule(".nav-vach-tracer-stroke"));
  assert.ok(!/mask|conic-gradient/.test(c));
});

/* ==================================================== reduced motion ====== */

test("reduced motion: CHI tracer tat hoat hinh, vien LOP A + trang thai active van thay ro", () => {
  const c = css();
  const at = c.indexOf("@media (prefers-reduced-motion: reduce)");
  const khoi = c.slice(at, at + 4200);
  assert.match(khoi, /\.nav-vach-tracer-stroke \{ animation: none; \}/);
  assert.ok(!/\.nav-vach-base-stroke \{ display: none/.test(khoi));
  assert.ok(!/\.nav-vach \{ display: none/.test(khoi));
});

/* =============================================== hoi quy toan file CSS ==== */

test("khong con tham chieu nao den khung xoay/vet sang cu trong toan bo globals.css", () => {
  const c = codeOnly(css());
  for (const cu of ["nav-tracer-xoay", ".nav-vach-streak", ".nav-vach::before"]) {
    assert.ok(!c.includes(cu), `còn sót tham chiếu cũ: ${cu}`);
  }
});

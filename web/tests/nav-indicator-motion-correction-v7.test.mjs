/*
 * Navigation Active Frame — V7 "SVG Ellipse Fix + Desktop Nav Actions + Hero
 * Scrim" (2026-08).
 *
 * BOI CANH (goc loi elip): moi `.nav-link` (ke ca "Trang chủ") dung
 * `border-radius: var(--r-full)` — mot gia tri PILL rat lon (bo goc lon hon
 * nua kich thuoc that). CSS `border-radius` tu CLAMP CA HAI TRUC (ngang/doc)
 * THEO CUNG MOT TY LE khi vuot qua kich thuoc hop — giu duong tron o goc
 * (mot vien-thuoc dung nghia). NHUNG SVG `rx`/`ry` tu clamp THEO TUNG TRUC
 * RIENG BIET (rx ve width/2, ry ve height/2 doc lap) — tren mot hop RONG hon
 * nhieu so voi CAO (vi du "Trang chủ" ~88x36), dat rx=ry=999 khien SVG tu
 * clamp thanh rx=44 (width/2) NHUNG ry=18 (height/2) — HAI GIA TRI KHAC
 * NHAU, ve ra mot goc HINH ELIP thay vi hinh tron nhu CSS.
 *
 * SUA: clamp TRUOC trong JS thanh MOT gia tri hieu dung DUY NHAT
 * (`Math.min(targetRadius, w/2, h/2)`) — dung CHO CA outer border-radius LAN
 * ca hai rect SVG, nen khong con co hoi de hai co che clamp khac nhau lech
 * ket qua.
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

/* ==================================== 3: MOT ban kinh hieu dung DUY NHAT == */

test("radius hieu dung = min(targetRadius, w/2, h/2) — khong dung THANG computed-style tho", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /const targetRadius = parseFloat\(getComputedStyle\(muc\)\.borderTopLeftRadius\) \|\| 0;/);
  assert.match(src, /const radius = Math\.min\(targetRadius, w \/ 2, h \/ 2\);/);
});

test("standard nav (Trang chủ) KHONG bi ep ve ban kinh pill 999 — radius phu thuoc w/h THAT", () => {
  const src = codeOnly(navIndicator());
  // Khong con hardcode 999 hay bang tra "shape" nao — moi con duong dan toi
  // `radius` deu di qua phep tinh min() o tren.
  assert.ok(!/radius = 999/.test(src));
  assert.ok(!/NAV_RADIUS/.test(src));
});

test("outer border-radius VA ca hai rect SVG dung CHUNG mot bien `radius` da clamp — khong tinh doc lap", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /borderRadius:\s*`\$\{o\.radius\}px`/);
  // 2 rect x (rx + ry) = 4 lan xuat hien cua cung mot cong thuc.
  const rectRadiusUses = (src.match(/o\.radius - STROKE_INSET/g) ?? []).length;
  assert.equal(rectRadiusUses, 4, "cả hai rect (rx+ry mỗi cái) phải cùng dùng công thức o.radius - STROKE_INSET");
});

/* ============================================== 4: hinh hoc SVG tuong minh */

test("SVG dung viewBox TUONG MINH khop o.w/o.h — khong con dua vao width=100% suy ngam", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /viewBox=\{`0 0 \$\{o\.w\} \$\{o\.h\}`\}/);
});

test("hai rect dung so THUC (khong phai chuoi phan tram) cho x/y/width/height", () => {
  const src = codeOnly(navIndicator());
  const base = src.match(/<rect\s+className="nav-vach-base-stroke"[\s\S]*?\/>/)?.[0] ?? "";
  const tracer = src.match(/<rect\s+className="nav-vach-tracer-stroke"[\s\S]*?\/>/)?.[0] ?? "";
  for (const r of [base, tracer]) {
    assert.ok(!/x="0"|y="0"|width="100%"|height="100%"/.test(r), "vẫn còn hình học phần trăm kiểu cũ");
    assert.match(r, /x=\{STROKE_INSET\}/);
    assert.match(r, /y=\{STROKE_INSET\}/);
    assert.match(r, /width=\{Math\.max\(0, o\.w - STROKE_INSET \* 2\)\}/);
    assert.match(r, /height=\{Math\.max\(0, o\.h - STROKE_INSET \* 2\)\}/);
  }
});

test("khong dung rx/ry='50%' — bo goc CHI den tu radius da do/clamp", () => {
  const src = codeOnly(navIndicator());
  assert.ok(!/rx="50%"|ry="50%"/.test(src));
});

/* ======================================== 5/6: chuan/Viet truyen + tracer = */

test("tracer van giu pathLength=100 va dasharray ~14/86, chay quanh CHINH VIEWBOX vua sua", () => {
  const src = codeOnly(navIndicator());
  assert.match(src, /pathLength="100"/);
  const than = codeOnly(rule(".nav-vach-tracer-stroke"));
  assert.match(than, /stroke-dasharray:\s*14\s+86/);
});

/* ==================================== 7-9: desktop nav actions ngang hang = */

test(".nav-right KHONG bao gio xuong dong o desktop — flex-wrap: nowrap + khong bi ep hep", () => {
  const than = codeOnly(rule(".nav-right"));
  assert.match(than, /flex-wrap:\s*nowrap/);
  assert.match(than, /flex-shrink:\s*0/);
});

test("nut tim kiem header co the co lai (min-width:0) de nhuong cho cum hanh dong", () => {
  const than = codeOnly(rule(".tim-nut"));
  assert.match(than, /min-width:\s*0/);
});

test("Công cụ (.btn-ghost) van la be mat trung tinh, khong nen tim nang/glow", () => {
  const than = codeOnly(rule(".btn-ghost"));
  assert.match(than, /background:\s*transparent/);
  assert.match(than, /box-shadow:\s*none/, "phải tường minh box-shadow: none, không kế thừa glow của .btn-primary");
  assert.ok(!/#8b6cff/i.test(than), "vẫn còn tô màu tím thương hiệu — Công cụ phải trung tính");
});

/* ============================================== 11-15: suong doc hero/page = */

test(".hero-v2::before: elip NHO GON (chieu cao <= 90%), khong con 128% cu — tranh 'tam panel'", () => {
  const than = codeOnly(rule(".hero-v2::before"));
  const m = than.match(/radial-gradient\((\d+)% (\d+)% at/);
  assert.notEqual(m, null);
  const h = Number(m[2]);
  assert.ok(h <= 90, `chiều cao elip ${h}% vẫn quá lớn — dễ đọc ra như một tấm phẳng`);
  assert.match(than, /transparent 80%/, "phải tan biến hoàn toàn ở stop rõ ràng");
});

test(".page-head::before: cung nguyen tac elip nho gon — Explore/Animation dung chung component nay", () => {
  const than = codeOnly(rule(".page-head::before"));
  const m = than.match(/radial-gradient\((\d+)% (\d+)% at/);
  assert.notEqual(m, null);
  const h = Number(m[2]);
  assert.ok(h <= 90, `chiều cao elip ${h}% vẫn quá lớn (trước là 145%)`);
});

test("KHONG co lop overlay hinh CHU NHAT (background thang, khong phai ::before elip) tren .page-head/.hero-v2", () => {
  for (const sel of [".page-head", ".hero-v2"]) {
    const than = codeOnly(rule(sel));
    assert.ok(!/background:/.test(than), `${sel} chính không được có background riêng — chỉ ::before lo readability`);
  }
});

test("hero/page-head KHONG dung text-shadow nang tren tieu de", () => {
  for (const sel of [".hero-v2-title", ".page-title"]) {
    const than = codeOnly(rule(sel));
    // Cho phep KHONG co text-shadow nao, hoac neu co thi phai rat nhe (kiem
    // tra khong co chu "nang" — o day don gian la khong dung nhieu lop
    // text-shadow dam nhu ban rat cu tung bi phan hoi).
    const shadows = than.match(/text-shadow:\s*([^;]+);/);
    if (shadows) {
      const layers = shadows[1].split(",").length;
      assert.ok(layers <= 2, `${sel} có ${layers} lớp text-shadow — quá nặng`);
    }
  }
});

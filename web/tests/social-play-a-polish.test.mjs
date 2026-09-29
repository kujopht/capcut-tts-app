/*
 * SOCIAL & PLAY V1 — goi A, luot chinh thi giac dem 2026-09-26 (Chrome QA hien,
 * 1600/1440/1366/390). Moi bai khoa lai MOT loi da DO THAT tren trang:
 *   1. xem truoc trong trinh sua ho so bi ep con 1px (o luoi overflow:hidden);
 *   2. khung "Go Moc"/"Bac Co" net xam gan nhu vo hinh tren nen toi;
 *   3. bo dem "305 ký tự" doc nhu do dai, thuc ra la so con lai;
 *   4. chan trang o dien thoai mat padding doc (shorthand `.wrap`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = read("../src/app/globals.css");

function khoi(selector) {
  const i = css.indexOf(`${selector} {`);
  assert.ok(i >= 0, `khong thay khoi ${selector}`);
  return css.slice(i, css.indexOf("}", i) + 1);
}

test("than hop thoai (luoi tu cuon) giu moi hang du cao noi dung", () => {
  assert.match(khoi(".soan-hop-than"), /grid-auto-rows:\s*max-content/);
  // xem truoc van dinh va cat goc bo tron, nhung khong con bi hang luoi ep
  assert.match(khoi(".ho-so-xem-truoc"), /position:\s*sticky/);
});

test("khung anh gan data-khung de nhuom lai theo tung khung", () => {
  const src = read("../src/components/cosmetics/Cosmetics.tsx");
  assert.match(src, /data-khung=\{assetRef\}/);
  for (const khung of ["frame_go", "frame_bac"]) {
    const i = css.indexOf(`.cosmetic-frame-img[data-khung="${khung}"]`);
    assert.ok(i >= 0, `thieu luat nhuom cho ${khung}`);
    assert.match(css.slice(i, css.indexOf("}", i)), /filter:[^;]*brightness\(/, `${khung} phai duoc lam sang`);
  }
  // khung da ro net (Ngoc/Vang/Tinh Tu) giu nguyen mau goc
  assert.ok(!css.includes('[data-khung="frame_vang"]'));
});

test("bo dem ky tu noi ro la so CON LAI", () => {
  assert.match(read("../src/components/ProfileEditor.tsx"), /Còn \{tranBio - bio\.length\} ký tự/);
  assert.match(read("../src/components/PostComposer.tsx"), /Còn \{conLai\} ký tự/);
});

test("chan trang o dien thoai tra lai padding doc bi `.wrap` xoa", () => {
  const i = css.indexOf(".wrap { padding: 0 var(--s4); }");
  assert.ok(i >= 0);
  const sau = css.slice(i, i + 900);
  assert.match(sau, /\.footer-grid \{ padding-block:/);
  assert.match(sau, /\.footer-note \{ padding-block:/);
  // `.wrap` chung KHONG doi (thanh phat nho dung no)
  assert.match(sau, /^\.wrap \{ padding: 0 var\(--s4\); \}/);
});

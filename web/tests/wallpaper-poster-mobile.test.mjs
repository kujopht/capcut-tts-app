/**
 * Dien thoai chi tai MOT tam anh nen (ban 960px), khong phai tam 1672px + tam 960px.
 *
 * Do tren fanfic.world o 390px truoc khi sua: poster `<img>` cua LiveBackground
 * luon tai tam lon (vd. 01-home-sunny-harbor.webp 436 KB) trong khi CSS
 * `.page-bg-lop::before` tai them ban `-sm` (151 KB) — va tam lon che mat tam nho.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("anhNenNho tra ve dung tep -sm ma CSS --anh-nho dung, cung diem gay 640px", () => {
  const lib = read("../src/lib/backgrounds.ts");
  assert.match(lib, /export function anhNenNho\(ten: string\): string \{[\s\S]*?\$\{tep\}-sm\.webp/);
  assert.match(lib, /export const MAN_HINH_NHO = "\(max-width: 640px\)";/);
  const css = read("../src/app/globals.css");
  const khoi = css.lastIndexOf("@media (max-width: 640px) {", css.indexOf("background-image: var(--anh-nho, var(--anh))"));
  assert.ok(khoi > 0, "khối CSS đặt --anh-nho phải nằm trong @media (max-width: 640px)");
  for (const m of css.matchAll(/--anh: url\("\/artwork\/fantasy-backgrounds\/([\w-]+)\.webp"\);\s+--anh-nho: url\("\/artwork\/fantasy-backgrounds\/([\w-]+)\.webp"\)/g)) {
    assert.equal(m[2], `${m[1]}-sm`, `--anh-nho của ${m[1]} phải là ${m[1]}-sm`);
  }
});

test("poster LiveBackground chon ban nho duoi 640px bang <picture>, van giu img du phong", () => {
  const lb = read("../src/components/LiveBackground.tsx");
  assert.match(lb, /<picture>\s*\{posterNho \? <source media="\(max-width: 640px\)" srcSet=\{posterNho\} \/> : null\}/);
  assert.match(lb, /<img\s+src=\{poster\}/);
});

test("PageBackground truyen ban nho cho CA HAI lop", () => {
  const pb = read("../src/components/PageBackground.tsx");
  assert.match(pb, /posterNho=\{anhNenNho\(ten\)\}/);
  assert.match(pb, /posterNho=\{anhNenNho\(tenMoi\)\}/);
});

/*
 * PRODUCT UX SPRINT 2 — muc dieu huong chinh dang sang + thanh dieu huong mobile.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mucDangXem } from "../src/lib/navActive.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("doc truyen / chuong -> 'Thư viện' sang; bai dang / trang ca nhan -> 'Cộng đồng'", () => {
  assert.equal(mucDangXem("/"), "/");
  assert.equal(mucDangXem("/library"), "/library");
  assert.equal(mucDangXem("/novels/nov_rr_136586"), "/library");
  assert.equal(mucDangXem("/chapters/ch_1"), "/library");
  assert.equal(mucDangXem("/fanfic"), "/library");
  assert.equal(mucDangXem("/community"), "/community");
  assert.equal(mucDangXem("/posts/p1"), "/community");
  assert.equal(mucDangXem("/u/nam"), "/community");
  assert.equal(mucDangXem("/entertainment"), "/entertainment");
  assert.equal(mucDangXem("/animation/s1"), "/entertainment");
});

test("'Trang chủ' KHONG sang o moi trang; trang ngoai bon muc khong sang gi", () => {
  assert.equal(mucDangXem("/studio"), "");
  assert.equal(mucDangXem("/account"), "");
  assert.equal(mucDangXem("/librarything"), "", "không khớp tiền tố nửa chừng");
  assert.equal(mucDangXem("/novels"), "", "chỉ trang CON của /novels");
});

test("NavAuth dung chung ham; vach truot va aria-current di theo no", () => {
  const nav = read("../src/components/NavAuth.tsx");
  assert.match(nav, /const dangXem = mucDangXem\(pathname\);/);
  assert.match(nav, /aria-current=\{active \? "page" : undefined\}/);
  assert.match(nav, /<NavIndicator bao=\{hop\} bang=\{bang\} moc=\{dangXem\} \/>/);
});

test("mobile 380-640px: bon muc chia deu mot hang, khong vet mo cat chu", () => {
  const css = read("../src/app/globals.css");
  const at = css.indexOf("@media (min-width: 380px) and (max-width: 640px)");
  assert.ok(at > 0);
  const khoi = css.slice(at, css.indexOf("\n}\n", at));
  assert.match(khoi, /mask-image: none/);
  assert.match(khoi, /\.nav-link \{[^}]*flex: 1 1 auto/);
});

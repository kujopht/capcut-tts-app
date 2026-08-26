/*
 * Khoa lai ba quyet dinh giao dien cua dot visual polish:
 *   1. Header dung nguyen ban floating dock V7 da duoc duyet o staging.
 *   2. Cum ben phai khong duoc vo thanh hai dong tren desktop.
 *   3. Page/reader hero dung cung ngon ngu glass card voi listen player.
 *
 * Day la source-regression test; build va screenshot moi la lop kiem tra
 * hanh vi/thi giac sau cung.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

const rule = (selector) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
};

test("site header giu floating dock V7 nhung da nen theo phan hoi moi", () => {
  const header = rule(".site-header");
  assert.match(header, /top:\s*14px/);
  assert.match(header, /margin:\s*14px auto 0/);
  assert.match(header, /width:\s*min\(1100px, calc\(100% - 32px\)\)/);
  assert.match(header, /border-radius:\s*14px/);
  assert.match(header, /--blur:\s*14px/);
  assert.match(header, /backdrop-filter:\s*blur\(var\(--blur\)\) saturate\(1\.25\)/);

  assert.match(rule(".site-header .wrap"), /min-height:\s*52px/);
});

test("homepage gom hero va cong dieu huong vao mot dai desktop gon", () => {
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /className="home-entry-grid"/);
  const entry = rule(".home-entry-grid");
  assert.match(entry, /display:\s*grid/);
  assert.match(entry, /grid-template-columns:/);
  assert.match(rule(".home-entry-grid .portal-truyen"), /min-height:\s*224px/);
  assert.match(rule('.page[data-hero-theme="home"]'), /padding-top:\s*var\(--s4\)/);
});

test("homepage dung bang bien tap hai cot va chi lay sau truyen", () => {
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /const GRID_COUNT = 6;/);
  assert.match(home, /className="home-editorial-grid/);
  assert.match(home, /className="home-editorial-stories/);
  assert.match(home, /className="home-editorial-members/);
  assert.match(home, /Truyện mới đáng chú ý/);
  assert.match(home, /Thành viên nổi bật/);

  const editorial = rule(".home-editorial-grid");
  assert.match(editorial, /grid-template-areas:\s*"members stories"/);
  assert.match(rule(".home-editorial-stories"), /grid-area:\s*stories/);
  assert.match(rule(".home-editorial-members"), /grid-area:\s*members/);
});

test("animation va cong dong cung chia mot hang phu gon", () => {
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /className="home-secondary-grid/);
  assert.match(rule(".home-secondary-grid"), /grid-template-columns:\s*repeat\(2/);
  assert.match(home, /const ANIM_SHELF_COUNT = 4;/);
  assert.match(home, /const FEED_SHELF_COUNT = 3;/);
});

test("cum nav ben phai khong vo hai hang tren desktop", () => {
  const navRight = rule(".nav-right");
  assert.match(navRight, /flex-wrap:\s*nowrap/);
  assert.match(navRight, /flex-shrink:\s*0/);
});

test("page head va reader head cung ngon ngu glass voi listen player", () => {
  for (const selector of [".page-head", ".reader-head"]) {
    const hero = rule(selector);
    assert.match(hero, /border:\s*1px solid/);
    assert.match(hero, /border-radius:\s*var\(--r4\)/);
    assert.match(hero, /radial-gradient/);
    assert.match(hero, /linear-gradient/);
    assert.match(hero, /box-shadow:\s*var\(--shadow-2\), var\(--edge\)/);
  }

  const sharedGlass = css.slice(css.indexOf(".kinh,"), css.indexOf("{", css.indexOf(".kinh,")));
  assert.match(sharedGlass, /\.page-head/);
  assert.match(sharedGlass, /\.reader-head/);
  assert.match(css, /\.page-head::after,\s*\.reader-head::after,\s*\.listen-hero::after/);
});

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

test("homepage tinh gian, bo trung lap cong the gioi va tap trung vao noi dung", () => {
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /className="home-hero-wrap"/);
  assert.ok(!home.includes("<TheGioiCong"), "Không còn TheGioiCong trùng lặp cổng");
  const heroWrap = rule(".home-hero-wrap");
  assert.match(heroWrap, /display:\s*flex/);
  assert.match(rule('.page[data-hero-theme="home"]'), /padding-top:\s*var\(--s4\)/);
});

test("homepage dung bang bien tap hai cot va chi lay sau truyen", () => {
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /const GRID_COUNT = 6;/);
  assert.match(home, /home-editorial-grid/);
  assert.match(home, /className="home-editorial-stories/);
  assert.match(home, /className="home-editorial-members/);
  assert.match(home, /Truyện mới đáng chú ý/);
  assert.match(home, /Thành viên nổi bật/);

  const editorial = rule(".home-editorial-grid");
  assert.match(editorial, /grid-template-areas:\s*"members stories"/);
  assert.match(rule(".home-editorial-stories"), /grid-area:\s*stories/);
  assert.match(rule(".home-editorial-members"), /grid-area:\s*members/);
});

test("cot thanh vien KHONG duoc dat cho khi tuan do khong ai ghi XP", () => {
  /*
    Hai cot la hinh dang khi CO du lieu, khong phai mot hang so.

    Truoc day cot "Thành viên nổi bật" luon duoc ve, nen o mot san pham chua
    dong nguoi thi mot phan ba be ngang man hinh danh cho dong chu "Chưa có
    thành viên ghi XP trong tuần này" — ngay canh ke truyen that. Cai gia
    khong chi la cho trong: no noi rang hai thu do ngang hang nhau.
  */
  const home = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  assert.match(home, /const coBangVang = !loading && bangVangTuan\.length > 0;/,
    "trang chủ không còn phân biệt có/không có dữ liệu bảng vàng");
  assert.match(home, /coBangVang \? "" : " home-editorial-grid-mot-cot"/,
    "lưới không đổi sang một cột khi bảng vàng rỗng");
  assert.match(home, /\{coBangVang \? \(/,
    "cột thành viên vẫn được vẽ khi không có dữ liệu");

  const mot = rule(".home-editorial-grid-mot-cot");
  assert.match(mot, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  // Vung "members" phai bi GO khoi so do: mot vung da khai bao ma rong van
  // giu cho cua no, nen chi doi so cot thi khong du.
  assert.match(mot, /grid-template-areas:\s*"stories"/);
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

test("page head khong con hop toi dong khung, reader head giu ngon ngu glass", () => {
  const pageHead = rule(".page-head");
  assert.ok(!pageHead.includes("border: 1px solid"), "page-head không còn border hộp tối");
  assert.ok(!pageHead.includes("box-shadow"), "page-head không còn box-shadow hộp tối");

  const readerHead = rule(".reader-head");
  assert.match(readerHead, /border:\s*1px solid/);
  assert.match(readerHead, /border-radius:\s*var\(--r4\)/);
  assert.match(readerHead, /box-shadow:\s*var\(--shadow-2\), var\(--edge\)/);

  const sharedGlass = css.slice(css.indexOf(".kinh,"), css.indexOf("{", css.indexOf(".kinh,")));
  assert.match(sharedGlass, /\.reader-head/);
  assert.match(css, /\.reader-head::after,\s*\.listen-hero::after/);
});

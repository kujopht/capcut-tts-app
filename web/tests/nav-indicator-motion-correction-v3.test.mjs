/*
 * Modern Anime Fantasy Style Correction + Nav Route State Fix V3 (2026-08).
 *
 * HAI VAN DE rieng biet nhung sua chung mot dot:
 *
 *   1. `/write` (khach vang lai) tu doi huong client sang
 *      `/login?next=%2Fwrite`. Vien thuoc dua vao `pathname` tho nen an di
 *      luc do (KHONG khop muc nao), roi "tai xuat hien tu vi tri Viết truyện
 *      cu" khi dieu huong tiep — sai, vi ve mat nguoi dung ho VAN dang o
 *      giua luong Viet truyen. Sua bang `resolveNavHref` (lib/nav.ts).
 *
 *   2. Vien thuoc dang xem con box-shadow/quang (du da giam nhieu o V2) —
 *      phan hoi noi ro KHONG duoc glow chut nao. Bo het box-shadow, doi bo
 *      goc tu pill sang vuong vuc hon, them "tracer" — mot doan vien NGAN
 *      chay quanh chu vi luc dung yen (khac han khung nang luong ca vien da
 *      bo o o tim, Phase 1).
 *
 * Chuan hoa CRLF -> LF (xem bai hoc o `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");

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

/* ==================================== resolveNavHref (khoa dieu huong) ==== */

test("resolveNavHref: /login?next=/write tinh la 'write', khong phai rong", async () => {
  const { resolveNavHref } = await import("../src/lib/nav.ts");
  const HREFS = ["/", "/fanfic", "/animation", "/community", "/library", "/write"];
  assert.equal(resolveNavHref("/write", null, HREFS), "/write");
  assert.equal(resolveNavHref("/login", "/write", HREFS), "/write");
  // `next` da duoc URLSearchParams.get() giai ma san — truyen thang chuoi
  // "/write" (khong con "%2Fwrite") la dung API thuc te.
  assert.equal(resolveNavHref("/register", "/write", HREFS), "/write");
});

test("resolveNavHref: /login KHONG next hop le thi rong (khong bia muc active)", () => {
  return import("../src/lib/nav.ts").then(({ resolveNavHref }) => {
    const HREFS = ["/", "/fanfic", "/write"];
    assert.equal(resolveNavHref("/login", null, HREFS), "");
    assert.equal(resolveNavHref("/login", "", HREFS), "");
    // next tro toi mot duong KHONG nam trong thanh dieu huong (vi du trang
    // thong bao) cung khong duoc bia ra mot muc gan nhat.
    assert.equal(resolveNavHref("/login", "/notifications", HREFS), "");
  });
});

test("resolveNavHref: tu choi next khong an toan (open-redirect), dung lai safeNext", () => {
  return import("../src/lib/nav.ts").then(({ resolveNavHref }) => {
    const HREFS = ["/", "/write"];
    // `safeNext` da tu choi cac dang nay — resolveNavHref phai THUA HUONG
    // hanh vi do (khong bypass sang mot muc dieu huong gia).
    assert.equal(resolveNavHref("/login", "https://x.tld/write", HREFS), "");
    assert.equal(resolveNavHref("/login", "//x.tld", HREFS), "");
  });
});

test("resolveNavHref: trang co that trong thanh dieu huong khong bi ghi de boi next", () => {
  return import("../src/lib/nav.ts").then(({ resolveNavHref }) => {
    const HREFS = ["/", "/fanfic", "/write"];
    // Dang o /fanfic that (khong phai trang trung gian xac thuc) thi PHAI
    // tra ve /fanfic, bat ke query string co gi.
    assert.equal(resolveNavHref("/fanfic", "/write", HREFS), "/fanfic");
  });
});

test("NavAuth dung resolveNavHref + useSearchParams, boc trong Suspense", () => {
  const nav = codeOnly(read("../src/components/NavAuth.tsx"));
  assert.match(nav, /useSearchParams/);
  assert.match(nav, /resolveNavHref\(pathname, searchParams\.get\("next"\), HREFS\)/);
  assert.match(nav, /<Suspense fallback=/, "useSearchParams cần Suspense — build tĩnh sẽ lỗi nếu thiếu");
});

/* ============================ NavIndicator: xoa hinh hoc an khi moc rong == */

test("NavIndicator xoa sach 'o' khi moc rong — khong con hien lai tu vi tri an cu", () => {
  const src = codeOnly(read("../src/components/NavIndicator.tsx"));
  assert.match(src, /if \(!moc\) \{/);
  // Phai goi setO(null) (hoac tuong duong) NGAY trong nhanh do — khong chi
  // `return` suong nhu ban truoc (day chinh la loi da sua).
  const at = src.indexOf("if (!moc) {");
  const than = src.slice(at, src.indexOf("if (!hop || !muc) return;", at));
  assert.match(than, /setO\(/, "nhánh moc rỗng không dọn state 'o' — hình học cũ sẽ còn sót lại");
});

/* ==================================== khong con box-shadow/glow nao ======= */

test("V3: .nav-vach KHONG con box-shadow — chi vien + nen + chu tao tuong phan", () => {
  const than = rule(".nav-vach");
  assert.ok(!/box-shadow/.test(than));
  assert.ok(!codeOnly(than).includes("filter"));
});

test("V3: khong con drop-shadow/text-shadow tren nhan muc dang xem", () => {
  const than = rule('.nav-link[aria-current="page"]');
  assert.ok(!/box-shadow|text-shadow|filter|drop-shadow/.test(than));
});

test("V3: bo goc doi tu pill (--r-full) sang vuong vuc hon (--r2)", () => {
  const than = rule(".nav-vach");
  assert.match(than, /border-radius: var\(--r2\)/);
  assert.ok(!/var\(--r-full\)/.test(than));
});

/*
  Khung tracer conic-gradient + mask (LOP B cua V3) da bi thay bang SVG stroke
  o V4 — xem `nav-indicator-motion-correction-v4.test.mjs` cho cac test
  tracer moi. Cac test cu cho `.nav-vach::before` da bi XOA khoi day (khong
  con quy tac do trong CSS nua).
*/

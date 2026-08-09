/*
 * Ban thiet ke lai 2026-08: rang buoc cua he thiet ke moi.
 *
 * Bo test nay KHONG kiem "trong co dep khong" — khong bai test nao lam duoc
 * viec do. No kiem nhung thu se lang le truot di khi co nguoi sua tiep:
 *
 *   1. mau va kich thuoc chi ton tai MOT cho (khoi token), khong rai ra tung
 *      trang duoi dang hex;
 *   2. moi hieu ung chuyen dong deu tat duoc bang `prefers-reduced-motion`;
 *   3. vung bam tren dien thoai du 44px;
 *   4. ban thiet ke lai khong lam mat mot loi vao dieu huong nao.
 *
 * Cac rang buoc ve HANH VI (tien do, khoi phuc sau reload, dang nhap) nam o
 * `job-progress-shared`, `job-recovery`, `studio-job` va `author-workspace-oauth`
 * — chung khong thuoc ve ban thiet ke lai va khong duoc noi long o day.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");

/** Than cua mot quy tac CSS, de rang buoc noi ve DUNG khoi do. */
function rule(selector) {
  const text = css();
  const at = text.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `khong tim thay quy tac ${selector}`);
  return text.slice(at, text.indexOf("}", at));
}

/* ============================================================ khoi token */

test("bang mau moi la TIM + LO, va ca hai deu la token", () => {
  const text = css();
  assert.match(text, /--brand: #8b6cff;/, "màu hành động không còn là tím");
  assert.match(text, /--accent: #22d3ee;/, "màu bổ trợ không còn là lơ");
  assert.match(text, /--grad-brand: linear-gradient\([^)]*var\(--brand\)/);
});

test("token moi cho kinh mo, quang, chieu cao va nhip deu co mat", () => {
  const text = css();
  for (const token of [
    "--glass:", "--glass-strong:", "--blur:",
    "--edge:", "--lift-brand:", "--lift-accent:",
    "--h-sm:", "--h-md:", "--h-lg:", "--h-input:",
    "--dur-fast:", "--dur:", "--dur-slow:", "--ring:",
  ]) {
    assert.ok(text.includes(token), `thiếu token ${token}`);
  }
});

test("mau chu tren nen tim la token, khong phai hex rai rac", () => {
  // Truoc day moi cho tu viet `#080a10`. Doi do dam cua nut chinh la phai di
  // sua tung cho mot, va chac chan se sot.
  assert.match(css(), /--on-brand: #[0-9a-f]{6,8};/);
});

test("KHONG trang nao hardcode mau tim/lo moi", () => {
  // Hex duoc phep o KHOI TOKEN va o cac quy tac trang tri trong `globals.css`
  // (quang, gradient) — nhung khong duoc lot vao tep JSX.
  for (const f of [
    "../src/app/page.tsx",
    "../src/app/library/page.tsx",
    "../src/app/account/page.tsx",
    "../src/app/login/page.tsx",
    "../src/app/studio/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/fanfic/page.tsx",
    "../src/components/JobProgress.tsx",
    "../src/components/SiteHeader.tsx",
    "../src/components/StoryCard.tsx",
    "../src/components/NavAuth.tsx",
  ]) {
    const hex = read(f).match(/#[0-9a-fA-F]{6,8}\b/g) ?? [];
    assert.deepEqual(hex, [], `${f} còn màu hardcode: ${hex.join(" ")}`);
  }
});

/* =========================================================== dieu huong */

test("header la lop kinh mo va biet trang da cuon chua", () => {
  const head = rule(".site-header");
  assert.match(head, /backdrop-filter: blur\(var\(--blur\)\)/);
  assert.match(head, /background: var\(--glass\)/);
  // Dac them khi da cuon — luc do moi co chu chay qua duoi.
  assert.match(css(), /\.site-header\[data-scrolled="true"\]/);

  const shell = read("../src/components/SiteHeader.tsx");
  assert.match(shell, /window\.addEventListener\("scroll"/);
  assert.match(shell, /\{ passive: true \}/, "listener cuộn phải là passive");
  assert.match(shell, /removeEventListener\("scroll"/, "không gỡ listener");
});

test("'Viết truyện' noi bat hon muc dieu huong thuong", () => {
  const nav = read("../src/components/NavAuth.tsx");
  // Van la muc thu tu trong `LINKS` — thu tu san pham khong doi, va
  // `ui.test.mjs` cung `author-workspace-oauth.test.mjs` khoa lai dieu do.
  assert.match(nav, /href: "\/write", label: "Viết truyện", cta: true/);
  assert.match(nav, /link\.cta \? "nav-link nav-cta" : "nav-link"/);
  const cta = rule(".nav-cta");
  assert.match(cta, /var\(--brand-line\)/, "nút CTA không có viền tím");
});

test("muc dang xem danh dau bang vach duoi, khong to ca nen", () => {
  // To ca nen o mot thanh bon muc thi khoi mau do to ngang mot cai nut va hut
  // mat truoc ca ten san pham.
  assert.match(css(), /\.nav-link\[aria-current="page"\]::after/);
  const active = rule('.nav-link[aria-current="page"]');
  assert.match(active, /background: transparent/);
});

/* ============================================================= trang chu */

test("trang chu co dai mo dau, va no LUON ve", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /<HomeHero daDangNhap=/);
  // Ve TRUOC nhanh loading/error/empty, nen kho trong thi van con thu noi cho
  // nguoi vao lan dau biet ho dang o dau.
  const at = home.indexOf("<HomeHero");
  assert.ok(at < home.indexOf("loading ?"), "dải mở đầu nằm sau nhánh loading");
});

test("dai mo dau noi ve TRUYEN, khong phai ve cong cu", () => {
  const home = read("../src/app/page.tsx");
  const at = home.indexOf("function HomeHero");
  const than = home.slice(at, home.indexOf("export default"));
  assert.match(than, /href="\/fanfic"/, "thiếu lối vào khám phá truyện");
  assert.match(than, /href="\/write"/, "thiếu lối vào viết truyện");
  // Va van khong dan bang logo khong lo — `ui.test.mjs` giu rang buoc do.
  assert.ok(!than.includes("LogoMark"));
});

test("da dang nhap thi co loi tat vao thu vien", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /daDangNhap \? \(/);
  assert.match(home, /href="\/library"/);
});

test("trang chu VAN lay truyen that, khong thanh landing tinh", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /api\.browseNovels/);
  assert.match(home, /<StoryHero novel=\{hero\}/);
  assert.match(home, /<StoryCard key=/);
});

test("trang chu KHONG bia so lieu backend khong co", () => {
  const home = read("../src/app/page.tsx");
  for (const bia of ["lượt đọc", "lượt nghe", "lượt xem", "nổi bật nhất"]) {
    assert.ok(!home.includes(bia), `trang chủ bịa số liệu: ${bia}`);
  }
});

/* ====================================================== chuyen dong co kiem */

test("moi hieu ung deu tat duoc bang prefers-reduced-motion", () => {
  const text = css();
  const at = text.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.notEqual(at, -1, "không còn khối reduced-motion");
  const than = text.slice(at, at + 700);
  assert.match(than, /animation-duration: 0\.01ms !important/);
  assert.match(than, /transition-duration: 0\.01ms !important/);
});

test("do tre cua hieu ung vao trang la CLASS, khong phai style inline", () => {
  // Media query va `prefers-reduced-motion` khong voi toi style inline duoc.
  const text = css();
  assert.match(text, /\.rise-1 \{ animation-delay:/);
  assert.ok(!/style=\{\{/.test(read("../src/app/page.tsx")));
});

test("thanh tien do co vet sang khi CHAY, va thoi khi xong", () => {
  const text = css();
  assert.match(text, /\.progress-bar::after/, "thanh tiến độ không có vệt sáng");
  assert.match(text, /\.progress-done \.progress-bar::after \{ display: none; \}/,
    "xong rồi mà vệt sáng vẫn chạy");
  assert.match(text, /\.progress-indeterminate \.progress-bar::after/);
});

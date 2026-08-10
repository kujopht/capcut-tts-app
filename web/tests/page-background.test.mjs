/*
 * Tranh nen toan trang.
 *
 * Day la KHONG KHI, khong phai noi dung. Bo test giu ba dieu:
 *
 *   1. moi duong dan tro dung mot tam, va tam mac dinh ton tai;
 *   2. anh KHONG bao gio bi dung lam bia truyen — bia rieng cho tung truyen la
 *      mot tinh nang khac, lam sau;
 *   3. lop phu du toi de chu van la thu doc duoc truoc tien, va trang doc
 *      chuong toi nhat.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, readdirSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");
const comp = () => read("../src/components/PageBackground.tsx");
const anhXa = () => read("../src/lib/backgrounds.ts");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const THU_MUC = new URL("../public/artwork/backgrounds/", import.meta.url);

/* ================================================================ tep anh */

test("du tam anh, va nam dung cho", () => {
  const co = readdirSync(THU_MUC).filter((f) => f.endsWith(".webp")).sort();
  assert.equal(co.length, 8, `có ${co.length} tấm, cần 8`);
  for (const ten of [
    "01-home-neon-night.webp",
    "02-explore-cyber-rain.webp",
    "03-reader-moonlit-shrine.webp",
    "04-studio-audio-nebula.webp",
    "05-write-creator-room.webp",
    "06-library-starry-archive.webp",
    "07-account-sakura-night.webp",
    "08-auth-starry-sky.webp",
  ]) {
    assert.ok(co.includes(ten), `thiếu ${ten}`);
  }
});

test("moi tam duoc CSS tro toi, va duong dan co that", () => {
  const text = css();
  const dan = [...text.matchAll(/url\("(\/artwork\/backgrounds\/[^"]+)"\)/g)]
    .map((m) => m[1]);
  assert.equal(dan.length, 8, `CSS trỏ tới ${dan.length} tấm, cần 8`);
  for (const d of dan) {
    const ten = d.split("/").pop();
    assert.ok(
      existsSync(new URL(ten, THU_MUC)),
      `CSS trỏ tới tệp không tồn tại: ${d}`,
    );
  }
});

/* ============================================================== anh xa route */

test("moi duong dan tro dung tam da dinh", async () => {
  const { tenNen } = await import("../src/lib/backgrounds.ts");
  const mong_doi = [
    ["/", "home"],
    ["/fanfic", "explore"],
    ["/fanfic?tag=One%20Piece", "explore"],
    ["/chapters/chp_1", "reader"],
    ["/novels/nov_1", "reader"],
    ["/studio", "studio"],
    ["/write", "write"],
    ["/library", "library"],
    ["/account", "account"],
    ["/login", "auth"],
    ["/auth/callback", "auth"],
  ];
  for (const [duong, ten] of mong_doi) {
    assert.equal(tenNen(duong), ten, `${duong} -> ${tenNen(duong)}, cần ${ten}`);
  }
});

test("'/' so khop CHINH XAC, khong bat moi trang", () => {
  // `startsWith("/")` se lam moi trang trong site dinh nen trang chu.
  assert.match(anhXa(), /\[\/\^\\\/\$\/, "home"\]/);
});

test("duong dan la se dung tam mac dinh, khong de trong", async () => {
  const { tenNen } = await import("../src/lib/backgrounds.ts");
  assert.equal(tenNen("/khong-ton-tai"), "auth");
  assert.equal(tenNen("/"), "home");
});

/* ============================================================== lop phu */

test("moi tam co lop phu, va trang doc chuong TOI NHAT", () => {
  const text = css();
  const muc = {};
  for (const m of text.matchAll(
    /\.page-bg\[data-bg="([^"]+)"\][^\n]*--toi: ([\d.]+);/g,
  )) {
    muc[m[1]] = Number(m[2]);
  }
  assert.equal(Object.keys(muc).length, 8, "có tấm chưa đặt mức tối");

  for (const [ten, v] of Object.entries(muc)) {
    assert.ok(v >= 0.7 && v <= 0.88, `${ten} tối ${v}, cần trong 0.70–0.88`);
  }
  // Hai trang chu dai nhat phai toi nhat.
  const toi_nhat = Math.max(...Object.values(muc));
  assert.equal(muc.reader, toi_nhat, "trang đọc chương phải tối nhất");
  assert.equal(muc.write, toi_nhat, "khu vực tác giả phải tối nhất");
  // Va trang dang nhap nhat nhat — noi dung ngan, khong khi duoc phep thay ro.
  assert.equal(muc.auth, Math.min(...Object.values(muc)));
});

test("co vignette chu khong chi mot lop toi phang", () => {
  const text = css();
  // Tim quy tac DUNG RIENG: `.page-bg::after {` o dau dong. Khoi gop
  // `.page-bg::before,` phia tren cung chua chuoi nay.
  // Co HAI quy tac `.page-bg::after`: mot khoi gop dat `content`/`inset`,
  // mot khoi rieng dat lop phu. Tim theo NOI DUNG chu khong theo ten.
  const moc = text.indexOf("rgb(8 9 15 / var(--toi");
  assert.notEqual(moc, -1, "khong tim thay lop toi phang");
  const than = text.slice(text.lastIndexOf(".page-bg::after", moc),
                          text.indexOf("}", moc));
  assert.match(than, /radial-gradient/, "thiếu vignette");
  assert.match(than, /rgb\(8 9 15 \/ var\(--toi/, "thiếu lớp tối phẳng");
});

/* ============================================== KHONG phai bia truyen */

test("tranh nen KHONG lot vao he thong bia truyen", () => {
  // Bia rieng cho tung truyen la mot tinh nang khac, lam sau. Cac tam nay la
  // khong khi toan trang.
  for (const f of ["../src/components/NovelCover.tsx", "../src/lib/cover.ts",
                   "../src/components/StoryCard.tsx"]) {
    assert.ok(
      !read(f).includes("artwork/backgrounds"),
      `${f} dùng tranh nền làm bìa truyện`,
    );
  }
});

/* ================================================================ hieu nang */

test("MOT lop nen, khong phai mot the <img> tham gia bo cuc", () => {
  // `codeOnly`: chu thich co trich `<img>` de noi vi sao KHONG dung no.
  const src = codeOnly(comp());
  assert.ok(!/<img/.test(src), "dùng thẻ <img> — sẽ gây xô layout khi tải xong");
  assert.match(src, /className="page-bg"/);
  // Anh dat bang CSS qua `data-bg`, khong phai style inline tung trang.
  assert.ok(!/style=\{\{/.test(src));
});

test("lop nen KHONG cuon theo trang va khong nhan chuot", () => {
  const text = css();
  const at = text.indexOf(".page-bg {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /position: fixed/);
  assert.match(than, /pointer-events: none/);
  assert.match(than, /z-index: -1/);
  // `position: fixed` tren MOT phan tu, khong phai `background-attachment:
  // fixed` tren body — cai sau lam trinh duyet ve lai nen moi khung khi cuon.
  assert.ok(!/background-attachment: fixed/.test(than));
});

test("dien thoai lam mo NHE hon", () => {
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /--blur: \d+px;/, "chưa hạ bán kính mờ ở điện thoại");
  assert.match(mobile, /--blur-the: \d+px;/);
  assert.match(mobile, /\.page-bg::before \{ filter: none; \}/);
});

/* ================================================================ hat sang */

test("hat sang CHI o ba trang, va KHONG o trang doc chuong", () => {
  const text = css();
  const at = text.indexOf("> .hat,");
  assert.notEqual(at, -1, "không có lớp hạt");
  const khoi = text.slice(text.lastIndexOf(".page-bg[", at), text.indexOf("}", at));
  for (const ten of ["home", "auth", "account"]) {
    assert.ok(khoi.includes(`data-bg="${ten}"`), `thiếu hạt ở ${ten}`);
  }
  // Khong duoc co gi chuyen dong sau mot doan van dai.
  assert.ok(!khoi.includes('data-bg="reader"'), "hạt sáng nằm sau chương truyện");
});

test("hat sang tat han khi nguoi dung chon giam chuyen dong", () => {
  const text = css();
  const at = text.indexOf("@media (prefers-reduced-motion: reduce)");
  const than = text.slice(at, at + 1400);
  assert.match(than, /\.hat \{ display: none; \}/);
  assert.match(than, /\.btn-primary::after \{ display: none; \}/);
  assert.match(than, /\.play-btn\.is-playing::after \{ animation: none; \}/);
});

/* ============================================== kinh dung co chung muc */

test("kinh chi ap cho cac khoi NOI, khong phai moi the", () => {
  const text = css();
  const so_lan = (text.match(/backdrop-filter: blur\(var\(--blur-the\)\)/g) ?? []).length;
  // Moi khoi khai CA `backdrop-filter` lan `-webkit-backdrop-filter`, nen so
  // dem la GAP DOI so be mat. 16 = 8 be mat.
  assert.ok(so_lan >= 8 && so_lan <= 24, `${so_lan / 2} bề mặt kính — quá nhiều/ít`);
  // The truyen trong luoi va than bai KHONG duoc lam mo nen.
  for (const sel of [".story-card {", ".reader {", ".card {"]) {
    const at = text.indexOf(sel);
    const than = text.slice(at, text.indexOf("}", at));
    assert.ok(!/backdrop-filter/.test(than), `${sel} bị biến thành kính`);
  }
});

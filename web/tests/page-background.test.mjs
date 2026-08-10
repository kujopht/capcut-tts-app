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
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");
const comp = () => read("../src/components/PageBackground.tsx");
const anhXa = () => read("../src/lib/backgrounds.ts");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const THU_MUC = new URL("../public/artwork/fantasy-backgrounds/", import.meta.url);

/* ================================================================ tep anh */

const TAM = [
  "01-home-sunny-harbor",
  "02-explore-sky-kingdom",
  "03-reader-moonlit-shrine",
  "04-studio-sky-workshop",
  "05-write-creators-room",
  "06-library-arcane-archive",
  "07-account-blossom-realm",
  "08-login-starlight-gate",
];

test("du tam anh, moi tam co ban lon va ban cho dien thoai", () => {
  const co = new Set(readdirSync(THU_MUC).filter((f) => f.endsWith(".webp")));
  assert.equal(co.size, 16, `có ${co.size} tệp webp, cần 16 (8 lớn + 8 nhỏ)`);
  for (const ten of TAM) {
    assert.ok(co.has(`${ten}.webp`), `thiếu ${ten}.webp`);
    assert.ok(co.has(`${ten}-sm.webp`), `thiếu bản điện thoại ${ten}-sm.webp`);
  }
});

test("ban WebP nho hon HAN ban PNG goc", () => {
  // PNG goc ~2.7 MB moi tam. Phuc vu chung thang cho trinh duyet la bat nguoi
  // dung tai 21 MB cho thu ho khong bao gio nhin thang vao.
  for (const ten of TAM) {
    const png = new URL(`${ten}.png`, THU_MUC);
    if (!existsSync(png)) continue;   // ban goc khong duoc commit
    const goc = statSync(png).size;
    const web = statSync(new URL(`${ten}.webp`, THU_MUC)).size;
    assert.ok(web < goc / 3, `${ten}: ${Math.round(web / 1024)} KB chưa đủ nhẹ`);
  }
});

test("KHONG tep PNG nao bi commit", () => {
  // Chung nam trong `.gitignore`; CSS khong bao gio tro toi `.png`.
  const bo_qua = readFileSync(new URL("../../.gitignore", import.meta.url), "utf8");
  assert.match(bo_qua, /fantasy-backgrounds\/\*\.png/);
  assert.ok(!css().includes(".png"), "CSS trỏ tới tệp PNG nặng");
});

test("moi tam duoc CSS tro toi, va duong dan co that", () => {
  const text = css();
  const dan = [...text.matchAll(/url\("(\/artwork\/fantasy-backgrounds\/[^"]+)"\)/g)]
    .map((m) => m[1]);
  assert.equal(dan.length, 16, `CSS trỏ tới ${dan.length} tệp, cần 16`);
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
    ["/novels/nov_1", "explore"],
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

  /*
    Muc phu KHONG chon bang mat: no duoc tinh nguoc tu do sang THAT cua tung
    tam (do bang Pillow) va do sang mong muon sau khi phu.

        tam                       do sang    muc phu    con lai
        02-explore-sky-kingdom      150        0.83        26
        01-home-sunny-harbor        119        0.71        34
        04-studio-sky-workshop       85        0.69        26
        07-account-blossom-realm     80        0.60        32
        05-write-creators-room       76        0.74        20
        06-library-arcane-archive    46        0.39        28
        03-reader-moonlit-shrine     45        0.51        22
        08-login-starlight-gate      41        0.27        30

    Nen bai test nay kiem KET QUA chu khong kiem muc phu: moi trang phai cho ra
    mot nen co do sang gan nhau, va trang co vai tro doc lau thi toi hon.
  */
  const SANG = {
    home: 119, explore: 150, reader: 45, studio: 85,
    write: 76, library: 46, account: 80, auth: 41,
  };
  const con_lai = {};
  for (const [ten, v] of Object.entries(muc)) {
    assert.ok(v > 0.2 && v < 0.9, `${ten} tối ${v} — ngoài khoảng hợp lý`);
    con_lai[ten] = Math.round(SANG[ten] * (1 - v));
  }
  for (const [ten, v] of Object.entries(con_lai)) {
    assert.ok(v >= 18 && v <= 36,
      `${ten} còn lại ${v}/255 — quá ${v < 18 ? "tối, tranh biến mất" : "sáng, chữ khó đọc"}`);
  }
  // Khu vuc tac gia toi nhat: form la thu phai doc duoc truoc tien.
  assert.equal(con_lai.write, Math.min(...Object.values(con_lai)),
    "khu vực tác giả phải là nền tối nhất");
});

test("co vignette chu khong chi mot lop toi phang", () => {
  const text = css();
  // Tim quy tac DUNG RIENG: `.page-bg::after {` o dau dong. Khoi gop
  // `.page-bg::before,` phia tren cung chua chuoi nay.
  // Co HAI quy tac `.page-bg::after`: mot khoi gop dat `content`/`inset`,
  // mot khoi rieng dat lop phu. Tim theo NOI DUNG chu khong theo ten.
  const moc = text.indexOf("rgb(6 7 13 / var(--toi");
  assert.notEqual(moc, -1, "khong tim thay lop toi phang");
  const than = text.slice(text.lastIndexOf(".page-bg::after", moc),
                          text.indexOf("}", moc));
  assert.match(than, /radial-gradient/, "thiếu vignette");
  assert.match(than, /rgb\(6 7 13 \/ var\(--toi/, "thiếu lớp tối phẳng");
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
  assert.match(mobile, /background-image: var\(--anh-nho, var\(--anh\)\)/,
    "điện thoại vẫn tải bản ảnh lớn");
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

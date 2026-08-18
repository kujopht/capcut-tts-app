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
  /*
    Loc theo TIEN TO cua 8 tam (khong dem MOI tep .webp trong thu muc): Live
    Wallpaper V2 them mot mask chuyen dong `.webp` cung thu muc (xem
    `live-background-home-integration.test.mjs`) — mot tai san khac loai,
    khong phai tranh nen toan trang, khong nen troi buoc dem nay.
  */
  const co = new Set(
    readdirSync(THU_MUC).filter(
      (f) => f.endsWith(".webp") && TAM.some((ten) => f === `${ten}.webp` || f === `${ten}-sm.webp`),
    ),
  );
  assert.equal(co.size, 16, `có ${co.size} tệp webp nền trang, cần 16 (8 lớn + 8 nhỏ)`);
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

test("muc phu nam trong khoang da dat cho tung trang", () => {
  const text = css();
  const muc = {};
  for (const m of text.matchAll(
    /\.page-bg-lop\[data-bg="([^"]+)"\][^\n]*--toi: ([\d.]+);/g,
  )) {
    muc[m[1]] = Number(m[2]);
  }
  assert.equal(Object.keys(muc).length, 8, "có tấm chưa đặt mức tối");

  /*
    Huong my thuat: DE TRANH THO. Muc phu ha han so ban truoc, va de doc gio
    den tu hai thu khac — mang toi CUC BO sau chu tieu de, va be mat kinh cua
    cac khoi noi. Lam toi ca trang chi vi mot vung chu la cach de nhat nhung
    cung la cach giet buc tranh.

    Khoang duoi day do chu du an dat, khong phai do toi chon.
  */
  const KHOANG = {
    home:    [0.30, 0.38],
    explore: [0.38, 0.45],
    library: [0.35, 0.42],
    studio:  [0.45, 0.52],
    write:   [0.50, 0.58],
    account: [0.32, 0.40],
    auth:    [0.25, 0.35],
    reader:  [0.35, 0.42],
  };
  for (const [ten, v] of Object.entries(muc)) {
    const [min, max] = KHOANG[ten];
    assert.ok(v >= min && v <= max,
      `${ten} phủ ${v}, cần trong ${min}–${max}`);
  }
  // Khu vuc tac gia van phai toi nhat: form la thu phai doc duoc truoc tien.
  assert.equal(muc.write, Math.max(...Object.values(muc)));
  // Trang dang nhap nhat nhat — the dang nhap noi tren mot tam tranh lon.
  assert.equal(muc.auth, Math.min(...Object.values(muc)));
});

test("co mang toi CUC BO sau chu tieu de trang", () => {
  // Day la thu thay cho viec lam toi ca trang. Khong co no, tieu de nam truc
  // tiep tren tranh sang (02-explore sang 150/255) se mat tuong phan.
  const text = css();
  assert.match(text, /\.page-head::before/, "thiếu mảng tối sau tiêu đề trang");
  assert.match(text, /\.reader-head::before/, "thiếu mảng tối sau tên chương");
});

test("co vignette chu khong chi mot lop toi phang", () => {
  const text = css();
  // Tim quy tac DUNG RIENG: `.page-bg::after {` o dau dong. Khoi gop
  // `.page-bg::before,` phia tren cung chua chuoi nay.
  // Co HAI quy tac `.page-bg::after`: mot khoi gop dat `content`/`inset`,
  // mot khoi rieng dat lop phu. Tim theo NOI DUNG chu khong theo ten.
  const moc = text.indexOf("rgb(5 7 15 / var(--toi");
  assert.notEqual(moc, -1, "khong tim thay lop toi phang");
  const than = text.slice(text.lastIndexOf(".page-bg-lop::after", moc),
                          text.indexOf("}", moc));
  assert.match(than, /radial-gradient/, "thiếu vignette");
  assert.match(than, /rgb\(5 7 15 \/ var\(--toi/, "thiếu lớp tối phẳng");
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
  const at = text.indexOf('.hat[data-bg="home"]');
  assert.notEqual(at, -1, "khong co lop hat");
  const khoi = text.slice(at, text.indexOf("}", at));
  for (const ten of ["home", "auth", "account"]) {
    assert.ok(khoi.includes(`data-bg="${ten}"`), `thiếu hạt ở ${ten}`);
  }
  // Khong duoc co gi chuyen dong sau mot doan van dai.
  assert.ok(!khoi.includes('data-bg="reader"'), "hạt sáng nằm sau chương truyện");

  // Va mac dinh la TAT — chi ba trang tren duoc bat.
  const mac_dinh = text.slice(
    text.indexOf(".hat {"),
    text.indexOf("}", text.indexOf(".hat {")),
  );
  assert.match(mac_dinh, /opacity: 0/, "hạt sáng bật ở mọi trang");
});

test("hat sang tat han khi nguoi dung chon giam chuyen dong", () => {
  const text = css();
  const at = text.indexOf("@media (prefers-reduced-motion: reduce)");
  // Cat theo DAU NGOAC, khong theo mot so ky tu co dinh: them mot dong chu
  // thich vao khoi nay tung lam cua so 1400 ky tu truot mat cac dong duoi.
  const than = text.slice(at, text.indexOf("\n}", at));
  assert.match(than, /\.hat \{ display: none; \}/);
  assert.match(than, /\.btn-primary::after \{ display: none; \}/);
  assert.match(than, /\.play-btn\.is-playing::after \{ animation: none; \}/);
});

/* ============================================== kinh dung co chung muc */

test("kinh la MOT cong thuc gop, ap cho danh sach be mat co gioi han", () => {
  const text = css();
  // Chi mot cho khai co che kinh — truoc day moi be mat tu khai lay va de lech.
  const so_khai = (text.match(/backdrop-filter: blur\(var\(--blur-the\)\)/g) ?? []).length;
  assert.ok(so_khai <= 4, `${so_khai} chỗ khai báo kính — phải gộp về một`);

  const at = text.indexOf(".kinh,");
  assert.notEqual(at, -1, "không có công thức kính gộp");
  const chon = text.slice(at, text.indexOf("{", at));
  const be_mat = chon.split(",").map((x) => x.trim()).filter(Boolean);
  assert.ok(be_mat.length <= 14, `${be_mat.length} bề mặt kính — quá nhiều`);

  // The truyen trong luoi, than bai va `.card` thuong KHONG duoc la kinh.
  for (const cam of [".story-card", ".reader", ".card"]) {
    assert.ok(!be_mat.includes(cam), `${cam} bị biến thành kính`);
  }
});

test("tranh nen luon SAC — chi tiet la thu tao ban sac", () => {
  /*
    Rang buoc nay da doi HAI lan, va lan nay la lan cuoi:

      phase I-K  cam han `blur` tren lop anh
      phase L    cho lam mo tung trang (6px o studio/write) — SAI, chu du an
                 khong muon, va no nem di chinh chi tiet cua tranh
      phase M    cam lai, va de doc den tu mang toi cuc bo + be mat kinh

    Chi tiet day du nam o `route-crossfade.test.mjs`.
  */
  const text = css();
  const at = text.indexOf(".page-bg-lop::before {");
  // `codeOnly`: chu thich ngay trong khoi do co trich `filter: blur` de noi vi
  // sao KHONG dung no — quet ca khoi se bat trung chinh loi giai thich.
  const than = codeOnly(text.slice(at, text.indexOf("}", at)));
  assert.ok(!/filter: blur/.test(than), "tranh nền bị làm mờ");
});

test("the thuong co CHIEU SAU de tach khoi tranh nen", () => {
  const text = css();
  assert.match(text, /--do-sau: 0 8px 32px/, "thiếu token chiều sâu");
  const at = text.indexOf(".card {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /box-shadow: var\(--do-sau\)/);
});


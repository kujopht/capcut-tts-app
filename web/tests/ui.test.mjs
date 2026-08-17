// Regression cho hai lo hong giao dien da phat hien va sua o lan nay.
import { test } from "node:test";
import assert from "node:assert/strict";
import { kiemHoEndpoint } from "./_ho-endpoint.mjs";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const has = (p) => existsSync(new URL(p, import.meta.url));

/* ------------------------------------------------------------------ route */

test("du cac route cua hai khu vuc san pham", () => {
  for (const route of [
    "../src/app/page.tsx",           // trang chu
    "../src/app/studio/page.tsx",    // Audio Studio
    "../src/app/fanfic/page.tsx",    // kham pha fanfic
    "../src/app/write/page.tsx",     // khu vuc tac gia
    "../src/app/library/page.tsx",   // thu vien audio chung
    "../src/app/account/page.tsx",   // tai khoan
    "../src/app/login/page.tsx",
    "../src/app/novels/[id]/page.tsx",
    "../src/app/chapters/[id]/page.tsx",
  ]) {
    assert.ok(has(route), `thieu route ${route}`);
  }
});

test("thanh dieu huong chinh dung SAU muc, theo dung thu tu", () => {
  const nav = read("../src/components/NavAuth.tsx");
  // Thu tu la mot quyet dinh san pham, khong phai chuyen thu hang muc. So khop
  // theo VI TRI chu khong phai theo tap hop.
  //
  // "Viết truyện" ngang hang voi "Khám phá" va "Thư viện": khong co tac gia
  // thi khong co gi de doc, nen giau no trong menu tai khoan la noi rang viec
  // do la phu.
  //
  // "Animation" (V6, overnight Phase 5) dung NGAY SAU "Khám phá" — xem ghi
  // chu tren `LINKS` trong `NavAuth.tsx`.
  const order = [...nav.matchAll(/href: "([^"]+)", label: "([^"]+)"/g)].map(
    (m) => [m[1], m[2]],
  );
  assert.deepEqual(order, [
    ["/", "Trang chủ"],
    ["/fanfic", "Khám phá"],
    ["/animation", "Animation"],
    ["/community", "Cộng đồng"],
    ["/library", "Thư viện"],
    ["/write", "Viết truyện"],
  ]);
});

test("Audio Studio ra khoi thanh chinh nhung VAN toi duoc tu header", () => {
  const nav = read("../src/components/NavAuth.tsx");
  // Ra khoi `LINKS`...
  const links = nav.slice(nav.indexOf("const LINKS"), nav.indexOf("export function NavLinks"));
  assert.ok(!links.includes("/studio"), "/studio vẫn nằm trong thanh chính");
  // ...nhung khong bien mat: no o menu ben phai. Xoa han se lam nguoi dung
  // khong con duong nao vao cong cu tu header.
  assert.match(nav, /href="\/studio"/, "header mất lối vào Audio Studio");
  assert.match(nav, /\/account/, "header thiếu khu vực tài khoản");
});

test("trang chu la trang KHAM PHA TRUYEN, khong phai landing gioi thieu cong cu", () => {
  const home = read("../src/app/page.tsx");
  // Phai that su lay truyen ve — truoc day trang chu khong goi mot API nao.
  assert.match(home, /api\.browseNovels/, "trang chủ không lấy truyện");
  // `StoryHero` (khối bìa+chữ chia đôi trang) đã bị bỏ từ V4 visual
  // completion, thay bằng `StoryCard variant="featured"` khi kho chỉ có
  // đúng một truyện — xác nhận KHÔNG có `StoryHero` quay lại.
  assert.ok(!home.includes("StoryHero"), "StoryHero cũ đã quay lại");
  assert.match(home, /StoryCard/);
  // Hai the tinh nang cu da bien mat: chung dat cong cu ngang hang voi noi
  // dung, dung thu ma ban thiet ke lai nay bo di.
  assert.equal((home.match(/className="feature[ "]/g) ?? []).length, 0);

  // Va KHONG duoc goi `getNovel` tung truyen de dem chuong: do la N+1.
  assert.ok(!home.includes("api.getNovel("), "trang chủ gọi getNovel — N+1");

  const css = read("../src/app/globals.css");
  /*
    Lenh cam nay tung quet CA TEP — va no vo khi gallery anh (V3) dung
    `1fr 1fr` cho luoi hai cot mot cach hoan toan chinh dang. Y dinh that cua
    no la: khu HERO cua trang chu khong duoc chia doi man hinh co dinh. Quet
    dung pham vi do: moi khoi co selector chua "hero".
  */
  for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (/hero/i.test(m[1])) {
      assert.ok(
        !/grid-template-columns:\s*1fr\s+1fr/.test(m[2]),
        `khu hero chia doi 50/50: ${m[1].trim().slice(0, 60)}`,
      );
    }
  }
});

/* -------------------------------------------- LOI 1: khong co nut xuat ban */

test("khu vuc tac gia goi publishNovel", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /api\.publishNovel\(/, "phai goi api.publishNovel");
  assert.match(write, /Xuất bản/, "phai co nut Xuat ban");
});

test("xuat ban co hop thoai xac nhan", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /ConfirmDialog/);
  assert.match(write, /confirmPublish/);
});

/* ------------------------------- LOI 2: the <audio> khong gui duoc token */

test("trinh phat khong gan thang /api/audio vao src", () => {
  const player = read("../src/components/AudioPlayer.tsx");
  assert.ok(
    !player.includes("api.audioUrl("),
    "audioUrl tra URL khong kem xac thuc — the <audio> se nhan 401",
  );
  assert.match(player, /resolveAudio/, "phai lay URL qua resolveAudio");
});

test("resolveAudio hoi backend URL thay vi tu ghep", () => {
  const audio = read("../src/lib/audio.ts");
  assert.match(audio, /api\.audioLink\(/);
  // Che do R2 dung URL ky; che do cuc bo stream kem token roi doi thanh blob
  assert.match(audio, /createObjectURL/);
  assert.match(audio, /Authorization/);
});

test("lop api co ham xin URL audio", () => {
  const api = read("../src/lib/api.ts");
  assert.match(api, /audioLink:/);
  assert.match(api, /\/url\$\{download \? "\?download=true" : ""\}/);
});

test("co nut tai MP3", () => {
  const player = read("../src/components/AudioPlayer.tsx");
  assert.match(player, /download=\{audioFileName/);
  assert.match(player, /Tải MP3/);
});

/* ------------------------------------------------------ tach hai khu vuc */

test("audio tu Studio khong tro thanh chuong fanfic", () => {
  const workspace = read("../src/lib/workspace.ts");
  assert.match(workspace, /STUDIO_TAG = "audio-studio"/);
  assert.match(workspace, /export function fanficOnly/);

  // Ca hai noi liet ke truyen fanfic deu phai loc kho chua cua Studio
  for (const page of ["../src/app/fanfic/page.tsx", "../src/app/write/page.tsx"]) {
    assert.match(read(page), /fanficOnly\(/, `${page} phai loc kho Studio`);
  }
});

test("thu vien chung phan biet nguon audio", () => {
  const library = read("../src/app/library/page.tsx");
  assert.match(library, /isStudioNovel\(/);
  assert.match(library, /fromStudio/);
});

/* --------------------------------------------------- Audio Studio day du */

test("Audio Studio co du cac dieu khien bat buoc", () => {
  const studio = read("../src/app/studio/page.tsx");
  assert.match(studio, /textarea/, "phai co o dan van ban tu do");
  assert.match(studio, /MAX_CHARS/, "phai hien gioi han ky tu");
  assert.match(studio, /ký tự/, "phai hien so ky tu");
  assert.match(studio, /RATES/, "phai chon duoc toc do");
  // `chapterId` chu khong phai `created.chapter.chapter_id`: bam lai voi cung
  // noi dung thi dung lai chuong cu, de khoa van tay o backend nhan ra hai lan
  // bam la mot. Rate van phai di kem.
  assert.match(studio, /api\.createJob\(chapterId, voiceId, rate\)/,
    "phai gui rate len backend");
  assert.match(studio, /Thử lại/, "job that bai phai co nut thu lai");
  assert.match(studio, /Lịch sử audio/, "phai co lich su");
});

test("bon trang thai job deu duoc xu ly", () => {
  const ui = read("../src/components/ui.tsx");
  for (const status of ["pending", "running", "completed", "failed"]) {
    assert.ok(ui.includes(status), `thieu trang thai ${status}`);
  }
  // Trang thai phai co CHU, khong chi dua vao mau
  assert.match(ui, /Đang xếp hàng/);
  assert.match(ui, /Đang xử lý/);
  assert.match(ui, /Hoàn tất/);
  assert.match(ui, /Thất bại/);
});

/* --------------------------------------------------------- design system */

test("design system co du token va thanh phan", () => {
  const css = read("../src/app/globals.css");
  for (const token of ["--bg:", "--text:", "--brand:", "--s4:", "--r2:", "--t-base:"]) {
    assert.ok(css.includes(token), `thieu token ${token}`);
  }
  for (const part of [".btn", ".card", ".badge", ".input", ".modal", ".toast", ".sk", ".progress"]) {
    assert.ok(css.includes(part), `thieu thanh phan ${part}`);
  }
});

test("ho tro desktop, tablet va mobile", () => {
  const css = read("../src/app/globals.css");
  assert.match(css, /@media \(max-width: 900px\)/, "thieu breakpoint tablet");
  assert.match(css, /@media \(max-width: 640px\)/, "thieu breakpoint mobile");
});

test("widget audio duoc ep ve dark theme", () => {
  const css = read("../src/app/globals.css");
  assert.match(css, /color-scheme: dark/);
  assert.match(css, /\.player audio/);
});

test("link phan biet duoc voi van ban thuong", () => {
  const css = read("../src/app/globals.css");
  assert.ok(
    !/^a \{[^}]*color: inherit/ms.test(css),
    "link khong duoc lay mau chu xung quanh",
  );
  assert.match(css, /a \{\s*color: var\(--brand\)/);
});

test("ton trong prefers-reduced-motion", () => {
  assert.match(read("../src/app/globals.css"), /prefers-reduced-motion/);
});

/* -------------------------------------------------------- kha nang tiep can */

test("layout co skip-link, lang va viewport", () => {
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /lang="vi"/);
  assert.match(layout, /skip-link/);
  assert.match(layout, /id="main"/);
  assert.match(layout, /export const viewport/, "thieu khai bao viewport");
});

test("trang thai dong deu duoc thong bao cho doc man hinh", () => {
  const ui = read("../src/components/ui.tsx");
  assert.match(ui, /role="status"/);
  assert.match(ui, /role="alert"/);
  assert.match(ui, /role="progressbar"/);
  assert.match(read("../src/lib/toast.tsx"), /aria-live="polite"/);
});

test("hop thoai xac nhan bay focus va dong bang Escape", () => {
  const ui = read("../src/components/ui.tsx");
  assert.match(ui, /role="dialog"/);
  assert.match(ui, /aria-modal="true"/);
  assert.match(ui, /"Escape"/);
  assert.match(ui, /event\.key !== "Tab"/, "phai bay focus trong hop thoai");
});

test("ConfirmDialog: effect bay focus KHONG chay lai theo moi phim go trong body", () => {
  /*
   * Bug that da gap (Phase 4, Admin Control Center V2, phat hien qua QA
   * trinh duyet that): effect bay focus/Escape cu co `onCancel` trong mang
   * phu thuoc. MOI noi goi <ConfirmDialog> truyen `onCancel` la mot ham NEN
   * inline (vd `() => setHoi(null)`) — mot THAM CHIEU MOI moi lan cha render
   * lai. Neu body la mot o nhap co kiem soat (textarea ghi ly do), MOI phim
   * go goi setState -> cha render lai -> effect DON ROI CHAY LAI -> tieu
   * diem bi giat ra khoi o nhap ve nut da mo hop thoai. Ket qua: nguoi dung
   * KHONG BAO GIO go duoc qua mot ky tu vao o ly do.
   *
   * Sua bang mot ref giu ham `onCancel` MOI NHAT, effect chinh chi con phu
   * thuoc `open`.
   */
  const ui = read("../src/components/ui.tsx");
  const at = ui.indexOf("export function ConfirmDialog");
  const than = ui.slice(at, ui.indexOf("export function", at + 1));
  assert.match(than, /const onCancelRef = useRef\(onCancel\)/,
    "thieu ref giu onCancel moi nhat");
  assert.match(than, /onCancelRef\.current\(\)/,
    "effect bay focus phai goi qua ref, khong goi thang onCancel");
  assert.match(than, /\},\s*\[open\]\)/,
    "effect bay focus phai CHI phu thuoc `open` — `onCancel` trong mang phu thuoc se lam no chay lai theo moi phim go");
});

test("khong dung eslint-disable de lam ngo canh bao", () => {
  for (const file of [
    "../src/components/AudioPlayer.tsx",
    "../src/components/ui.tsx",
    "../src/app/studio/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/library/page.tsx",
    "../src/lib/useAsyncData.ts",
  ]) {
    assert.ok(!read(file).includes("eslint-disable"), `${file} co eslint-disable`);
  }
});

/* ------------------------------- giong mac dinh (loi tim thay khi chay that) */

test("giong mac dinh khop TOAN BO id, khong phai chuoi con", async () => {
  const { defaultVoiceId, VERIFIED_VOICE_ID } = await import(
    "../src/lib/voices.ts"
  );
  const v = (voice_id, installed = true) => ({ voice_id, installed });

  // Bay da tung sap: mot giong CapCut cung ten "HoaiMy" bi chon nham,
  // CapCut tra ve TTSInvalidSpeaker ngay lan tao dau tien.
  assert.equal(
    defaultVoiceId([v("capcut:BV074_HoaiMy"), v(VERIFIED_VOICE_ID)]),
    VERIFIED_VOICE_ID,
  );
  // Khong co giong da kiem chung -> uu tien Edge tieng Viet
  assert.equal(
    defaultVoiceId([v("capcut:BV074_HoaiMy"), v("edge:vi-VN-NamMinhNeural")]),
    "edge:vi-VN-NamMinhNeural",
  );
  // Bo qua giong chua cai
  assert.equal(
    defaultVoiceId([v(VERIFIED_VOICE_ID, false), v("capcut:x")]),
    "capcut:x",
  );
  assert.equal(defaultVoiceId([]), "");
});

test("hai trang dung chung bo chon giong", () => {
  for (const page of ["../src/app/studio/page.tsx", "../src/app/write/page.tsx"]) {
    const src = read(page);
    assert.match(src, /defaultVoiceId\(/, `${page} phai dung defaultVoiceId`);
    assert.ok(
      !src.includes('includes("HoaiMy")'),
      `${page} khong duoc so khop chuoi con ten giong`,
    );
  }
});

/* ------------------------------------------------------- CRUD fanfic */

test("lop api co du CRUD truyen va chuong", () => {
  const api = read("../src/lib/api.ts");
  for (const fn of [
    "updateNovel:", "deleteNovel:", "unpublishNovel:",
    "updateChapter:", "deleteChapter:",
  ]) {
    assert.ok(api.includes(fn), `lop api thieu ${fn}`);
  }
  assert.match(api, /method: "PATCH"/);
  assert.match(api, /method: "DELETE"/);
});

test("khu vuc tac gia noi day du CRUD", () => {
  const write = read("../src/app/write/page.tsx");
  for (const call of [
    "api.updateNovel(", "api.deleteNovel(", "api.publishNovel(",
    "api.unpublishNovel(", "api.updateChapter(", "api.deleteChapter(",
  ]) {
    assert.ok(write.includes(call), `khu vuc tac gia chua goi ${call}`);
  }
});

test("moi thao tac xoa deu phai qua modal xac nhan", () => {
  const write = read("../src/app/write/page.tsx");
  // Khong duoc goi thang api.delete* tu onClick
  assert.ok(
    !/onClick=\{\(\)\s*=>\s*api\.delete/.test(write),
    "khong duoc xoa ngay khi bam, phai qua xac nhan",
  );
  assert.match(write, /setPendingDelete\(\{\s*\n?\s*kind: "novel"/s);
  assert.match(write, /setPendingDelete\(\{\s*\n?\s*kind: "chapter"/s);
  assert.match(write, /confirmLabel="Xoá vĩnh viễn"/);
  assert.match(write, /danger/, "hop thoai xoa phai o dang canh bao");
});

test("xac nhan xoa noi ro se mat nhung gi", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /toàn bộ \{chapters\.length\} chương/);
  assert.match(write, /không hoàn tác được/);
  assert.match(write, /file audio/);
});

test("nut xuat ban va go xuat ban deu co xac nhan rieng", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /setConfirmPublish\("publish"\)/);
  assert.match(write, /setConfirmPublish\("unpublish"\)/);
  assert.match(write, /Gỡ xuất bản truyện này\?/);
  assert.match(write, /Xuất bản truyện này\?/);
});

test("moi thao tac ghi deu co trang thai dang chay va toast", () => {
  const write = read("../src/app/write/page.tsx");
  for (const busy of [
    "creatingNovel", "savingNovel", "creatingChapter", "savingChapter",
    "togglingPublish", "deleting",
  ]) {
    assert.ok(write.includes(busy), `thieu trang thai dang chay: ${busy}`);
  }
  assert.match(write, /toast\.ok\(/);
  assert.match(write, /toast\.error\(errorMessage\(cause\)\)/);
});

test("giao dien cap nhat ngay sau khi xoa, khong doi tai lai trang", () => {
  const write = read("../src/app/write/page.tsx");
  // Xoa truyen: bo khoi danh sach va chon lai truyen khac ngay trong bo nho
  assert.match(write, /novels\.filter\(\(n\) => n\.novel_id !== target\.id\)/);
  assert.match(write, /setSelectedId\(left\[0\]\?\.novel_id \?\? ""\)/);
  // Xoa chuong: bo khoi danh sach chuong
  assert.match(write, /current\.filter\(\(c\) => c\.chapter_id !== target\.id\)/);
  // Khong duoc tai lai ca trang
  assert.ok(!write.includes("location.reload"), "khong duoc tai lai trang");
});

test("sua truyen khong gui truong do server quyet dinh", () => {
  const api = read("../src/lib/api.ts");
  const block = api.slice(api.indexOf("updateNovel:"), api.indexOf("deleteNovel:"));
  for (const field of ["state", "owner_id", "novel_id"]) {
    assert.ok(!block.includes(`${field}?:`), `updateNovel khong duoc nhan ${field}`);
  }
});

test("khong goi setState long trong ham cap nhat cua setState", () => {
  // Bay da tung sap: setSelectedId nam trong updater cua setNovels khien React
  // chan lai, backend xoa xong ma giao dien khong doi va khong co toast.
  const write = read("../src/app/write/page.tsx");
  const nested = /set[A-Z]\w*\(\((?:current|prev)\)\s*=>\s*\{[^}]*\bset[A-Z]\w*\(/s;
  assert.ok(!nested.test(write), "hàm cập nhật của setState phải thuần khiết");
});

/* ------------------------------------------------- nhan dien thuong hieu */

test("co du bon bien the logo", () => {
  assert.ok(has("../src/components/Logo.tsx"), "thieu component logo");
  assert.ok(has("../src/app/icon.svg"), "thieu favicon");
  assert.ok(has("../public/brand/logo-mark.svg"), "thieu bieu tuong vuong");
  assert.ok(has("../public/brand/logo-full.svg"), "thieu logo day du");
  assert.ok(has("../public/brand/logo-mono.svg"), "thieu ban mot mau");
  assert.ok(has("../src/app/apple-icon.tsx"), "thieu apple-touch-icon");
  assert.ok(has("../src/app/opengraph-image.tsx"), "thieu anh Open Graph");
});

test("logo la SVG nguyen ban, khong nhung anh ngoai", () => {
  for (const f of [
    "../src/app/icon.svg",
    "../public/brand/logo-full.svg",
    "../public/brand/logo-mono.svg",
  ]) {
    const svg = read(f);
    assert.match(svg, /^<svg[\s\S]*<\/svg>\s*$/, `${f} phai la SVG`);
    assert.ok(!/<image\b/.test(svg), `${f} khong duoc nhung anh bitmap`);
    assert.ok(!/href="http/.test(svg), `${f} khong duoc tai tai nguyen ngoai`);
    assert.match(svg, /<title>/, `${f} thieu <title> cho doc man hinh`);
  }
});

test("mot bieu tuong duy nhat cho ca hai khu vuc", () => {
  // Ban DAY DU dung chung tung toa do o moi noi
  const key = 'd="M4.6 16.4 14.6 18 14.6 26.8 4.6 25.2Z"';
  for (const f of [
    "../src/components/Logo.tsx",
    "../src/components/BrandMark.tsx",
    "../public/brand/logo-mark.svg",
    "../public/brand/logo-full.svg",
  ]) {
    assert.ok(read(f).includes(key), `${f} dung hinh khac — phai la mot logo`);
  }
});

test("favicon la ban rut gon cua cung mot logo, khong phai logo khac", () => {
  const favicon = read("../src/app/icon.svg");
  const full = read("../public/brand/logo-mark.svg");

  // Cung ngon ngu hinh: o bo tron gradient thuong hieu + hinh mau muc dam
  for (const token of ['#7c8cff', '#4dd6c1', '#0b0d12', '<rect width="32" height="32"']) {
    assert.ok(favicon.includes(token), `favicon thieu ${token}`);
    assert.ok(full.includes(token), `logo day du thieu ${token}`);
  }

  // Ban favicon phai co KHOI DAY HON de con doc duoc o 16px.
  // Lay be rong cua thanh song am (nhan ra qua rx rieng cua tung ban).
  // String.raw: trong template literal thuong, `\d` bi nuot mat dau gach cheo
  // va lop ky tu thanh [d.] — khong khop chu so nao.
  const barWidth = (svg, rx) =>
    Number(
      new RegExp(String.raw`<rect[^>]*width="([\d.]+)"[^>]*rx="` + rx + `"`).exec(
        svg,
      )?.[1],
    );

  const wFavicon = barWidth(favicon, "2.2");
  const wFull = barWidth(full, "1.6");
  assert.ok(wFavicon > 0 && wFull > 0, `khong doc duoc be rong: ${wFavicon} / ${wFull}`);
  assert.ok(
    wFavicon > wFull,
    `thanh song am cua favicon phai day hon: ${wFavicon} vs ${wFull}`,
  );
});

test("bieu tuong ket hop trang sach va song am", () => {
  // Ca hai ban deu la: 3 thanh song am + 2 trang sach
  for (const [f, barRx, pageWidth] of [
    ["../src/app/icon.svg", "2.2", "1.5"],
    ["../public/brand/logo-mark.svg", "1.6", "1.8"],
  ]) {
    const svg = read(f);
    assert.equal(
      (svg.match(new RegExp(`<rect[^>]*rx="${barRx}"`, "g")) ?? []).length, 3,
      `${f} phai co 3 thanh song am`,
    );
    assert.equal(
      (svg.match(new RegExp(`<path[^>]*stroke-width="${pageWidth}"`, "g")) ?? []).length, 2,
      `${f} phai co 2 trang sach`,
    );
  }
});

test("favicon khong chua chu", () => {
  const svg = read("../src/app/icon.svg");
  assert.ok(!/<text/.test(svg), "favicon khong duoc co chu");
  // <title> la nhan cho doc man hinh, khong phai chu ve tren hinh
  assert.match(svg, /<title>Fanfic Audio Studio<\/title>/);
});

test("co du bo favicon: ico, svg, png va apple-touch-icon", () => {
  assert.ok(has("../src/app/favicon.ico"), "thieu favicon.ico");
  assert.ok(has("../src/app/icon.svg"), "thieu icon.svg");
  assert.ok(has("../src/app/apple-icon.tsx"), "thieu apple-touch-icon");
  for (const s of [16, 32, 48, 192, 512]) {
    assert.ok(has(`../public/brand/icon-${s}.png`), `thieu icon-${s}.png`);
  }
});

test("favicon.ico chua du ba kich thuoc nho", () => {
  const buf = readFileSync(new URL("../src/app/favicon.ico", import.meta.url));
  assert.equal(buf.readUInt16LE(0), 0, "khong phai file ICO");
  assert.equal(buf.readUInt16LE(2), 1, "khong phai file ICO");
  const count = buf.readUInt16LE(4);
  assert.equal(count, 3, "phai co 3 kich thuoc (16, 32, 48)");
  // Byte 0 cua moi muc la chieu rong; 0 nghia la 256
  const widths = [0, 1, 2].map((i) => buf.readUInt8(6 + i * 16) || 256).sort((a, b) => a - b);
  assert.deepEqual(widths, [16, 32, 48]);
});

test("web manifest tro dung bo icon lon", () => {
  const manifest = read("../src/app/manifest.ts");
  assert.match(manifest, /\/brand\/icon-192\.png/);
  assert.match(manifest, /\/brand\/icon-512\.png/);
  assert.match(manifest, /purpose: "maskable"/);
  assert.match(manifest, /theme_color: "#0b0d12"/);
});

test("ban mot mau va logo day du hop ca nen sang lan nen toi", () => {
  for (const f of ["../public/brand/logo-mono.svg", "../public/brand/logo-full.svg"]) {
    assert.match(read(f), /prefers-color-scheme: dark/, `${f} thieu bien the nen toi`);
  }
});

test("logo duoc dat o header, footer va trang dang nhap", () => {
  // Trang chu KHONG con logo khong lo. No dan bang mot TRUYEN — do la ca y
  // nghia cua ban thiet ke lai. Thuong hieu van co mat o header va footer,
  // hai cho xuat hien tren MOI trang.
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /<Logo size=\{30\}/, "header thieu logo");
  assert.match(layout, /<Logo size=\{26\}/, "footer thieu logo");
  assert.match(read("../src/app/login/page.tsx"), /<LogoMark size=\{54\}/);
  assert.ok(
    !read("../src/app/page.tsx").includes("LogoMark"),
    "trang chu khong nen dan bang logo nua",
  );
});

test("metadata co Open Graph va tieu de theo mau", () => {
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /template: "%s · Fanfic Audio Studio"/);
  assert.match(layout, /openGraph:/);
  assert.match(layout, /locale: "vi_VN"/);
  assert.match(layout, /twitter: \{ card: "summary_large_image" \}/);
});

test("anh sinh phia may chu khai bao dung kich thuoc", () => {
  const apple = read("../src/app/apple-icon.tsx");
  assert.match(apple, /width: 180, height: 180/);
  assert.match(apple, /contentType = "image\/png"/);

  const og = read("../src/app/opengraph-image.tsx");
  assert.match(og, /width: 1200, height: 630/);
  assert.match(og, /export const alt/);
});

test("logo khong pha bo cuc header hien co", () => {
  const css = read("../src/app/globals.css");
  // Logo la SVG that nen o gia lap bang CSS phai bi go
  assert.ok(!css.includes(".brand-mark {"), "còn CSS chết của ô giả lập cũ");
  assert.match(css, /\.brand svg \{ flex: 0 0 auto; \}/, "logo phải không bị co");
});

/* ------------------------------------------------- H1: tran ngang mobile */

test("khong con kich thuoc cung gay tran ngang", () => {
  // Bay da tung sap: <select> co minWidth 200 noi tuyen day /write rong 578px
  // trong khung 375px tren dien thoai.
  for (const f of [
    "../src/app/write/page.tsx",
    "../src/app/studio/page.tsx",
    "../src/app/library/page.tsx",
    "../src/app/fanfic/page.tsx",
    "../src/app/novels/[id]/page.tsx",
    "../src/app/chapters/[id]/page.tsx",
  ]) {
    const src = read(f);
    // `minWidth: 0` la nguoc lai — no CHO PHEP co lai, phai giu
    const xau = [...src.matchAll(/minWidth:\s*(\d+)/g)].filter((m) => m[1] !== "0");
    assert.equal(xau.length, 0, `${f} con minWidth cung: ${xau.map((m) => m[1])}`);
    assert.ok(!/width:\s*"auto"/.test(src), `${f} con width auto noi tuyen`);
  }
});

test("select trong hang co lop rieng, co lai duoc tren mobile", () => {
  const css = read("../src/app/globals.css");
  assert.match(css, /\.select-inline \{[^}]*max-width: 100%/s, "thieu max-width");
  assert.match(
    css,
    /@media \(max-width: 640px\)[\s\S]*\.select-inline \{ min-width: 0; width: 100%; \}/,
    "mobile phai cho select chiem tron hang",
  );
  assert.match(read("../src/app/write/page.tsx"), /className="select select-inline"/);
});

/* ------------------------------------------------------------ anh bia */

test("co component anh bia dung chung", () => {
  assert.ok(has("../src/components/NovelCover.tsx"));
  const src = read("../src/components/NovelCover.tsx");
  assert.match(src, /export function NovelCover/);
  assert.match(src, /size = "card"/);
});

test("anh bia du phong sinh tu du lieu, khong phai anh gia", () => {
  const src = read("../src/components/NovelCover.tsx");
  // Khong duoc tro toi bat ky anh nao ben ngoai
  assert.ok(!/https?:\/\//.test(src), "khong duoc nhung URL anh");
  assert.ok(!/placeholder|unsplash|picsum|dummy/i.test(src), "khong dung anh gia");
  // Mau du phong sinh tu ham bam cua id -> on dinh
  const logic = read("../src/lib/cover.ts");
  assert.match(logic, /export function paletteFor/);
  assert.match(logic, /hash \* 31/);
});

test("anh du phong on dinh: cung id luon ra cung mau", async () => {
  const { paletteFor, coverInitial } = await import("../src/lib/cover.ts");
  assert.deepEqual(paletteFor("nov_abc"), paletteFor("nov_abc"));
  assert.notDeepEqual(paletteFor("nov_abc"), paletteFor("nov_xyz"));
  assert.equal(coverInitial("hải tặc"), "H");
  assert.equal(coverInitial("   "), "?");
  assert.equal(coverInitial(""), "?");
});

test("bia that nam tren, bia du phong nam duoi", () => {
  const src = read("../src/components/NovelCover.tsx");
  // Lop du phong LUON duoc ve; lop bia that chi them khi co URL.
  // Bia hong thi lop tren khong ve gi va lop duoi lo ra — khong can bat loi.
  assert.ok(
    src.indexOf("cover-fallback") < src.indexOf("cover-image"),
    "lop du phong phai o duoi",
  );
  assert.match(src, /coverUrl \? \(/);
  assert.ok(!/<img[\s/>]/.test(src), "phai dung background-image, khong dung the anh");
});

test("anh bia duoc dung o ca bon noi", () => {
  for (const f of [
    "../src/app/novels/[id]/page.tsx",     // chi tiet truyen
    "../src/components/ChapterPlayer.tsx", // luong nghe o trang doc chuong
    "../src/app/library/page.tsx",         // thu vien
    "../src/components/StoryCard.tsx",     // the truyen dung chung
  ]) {
    assert.match(read(f), /<NovelCover/, `${f} chua dung anh bia`);
  }
  // Kham pha va trang chu KHONG goi thang `NovelCover` nua — ca hai di qua
  // `StoryCard`, nen mot truyen trong giong nhau o hai noi.
  for (const f of ["../src/app/fanfic/page.tsx", "../src/app/page.tsx"]) {
    assert.match(read(f), /<StoryCard/, `${f} chua dung the truyen chung`);
  }
  // Emoji 📖 cu da duoc thay het
  assert.ok(!read("../src/app/fanfic/page.tsx").includes("📖"));
});

test("trang doc lay chuong trong DUNG MOT request, khong con can bia/audio", () => {
  // Overnight Phase 2 (Phan 2A): trang doc khong con ve trinh phat/bia nua
  // (chi chu), nen no cung khong con ly do de goi `api.getNovel(` — bat biet
  // "mot request" van dung, chi khac ly do.
  const src = read("../src/app/chapters/[id]/page.tsx");
  assert.match(src, /api\.getChapter\(id\)/);
  assert.ok(!src.includes("api.getNovel("));
});

test("trang Nghe dung DUNG HAI request bat ke truyen co bao nhieu chuong", () => {
  // `getChapter` (chuong + audio + bia truyen) + `getNovel` (danh sach
  // chuong cho tap truoc/sau + chon tap) — KHONG lap trong vong for, KHONG
  // goi lai moi chuong: day chinh la rang buoc "khong N+1" cua Phan 2D.
  const src = read("../src/app/listen/[id]/page.tsx");
  assert.match(src, /api\.getChapter\(id\)/);
  assert.match(src, /api\.getNovel\(novelBrief\.novel_id\)/);
  assert.equal((src.match(/api\.getNovel\(/g) ?? []).length, 1,
    "chi duoc goi getNovel dung MOT lan trong load()");
  assert.match(src, /coverUrl={novel\.cover_url}/);
});

test("lop api khai bao truong moi la tuy chon", () => {
  const api = read("../src/lib/api.ts");
  // `?:` de client cu chua biet truong nay van bien dich duoc
  assert.match(api, /cover_url\?: string \| null;/);
  assert.match(api, /export interface NovelBrief/);
  assert.match(api, /novel\?: NovelBrief \| null;/);
});

test("CSS anh bia co du ba bien the", () => {
  const css = read("../src/app/globals.css");
  //  thay cho : bia du phong khong con chu cai
  // dau, ma la mot dau an hinh hoc — xem `components/StoryCoverFallback.tsx`.
  for (const cls of [".cover-card", ".cover-wide", ".cover-thumb", ".cover-fallback",
                     ".cover-image", ".cover-sigil"]) {
    assert.ok(css.includes(cls), `thieu ${cls}`);
  }
  assert.match(css, /\.cover-image \{ background-size: cover/);
});

/* ===================================================================
   N+1: trang chi tiet truyen chi duoc goi MOT request
   =================================================================== */

test("trang chi tiet truyen khong con goi API cho tung chuong", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  // Bat CA hai cach viet: `api.getChapter(` va `api` xuong dong roi `.getChapter(`
  // — ban cu viet kieu thu hai, nen chi kiem tra chuoi lien nhau la vo nghia.
  assert.ok(
    !/\.getChapter\(/.test(src),
    "khong duoc goi /api/chapters cho tung chuong nua",
  );
  assert.match(src, /api\.getNovel\(id\)/);
});

test("khong con vong lap goi API tren danh sach chuong", () => {
  for (const f of ["../src/app/novels/[id]/page.tsx", "../src/app/write/page.tsx"]) {
    const src = read(f);
    // `chapters.map(... api.` la dau hieu cua N+1: mot request moi chuong
    assert.ok(
      !/chapters\.map\(\s*\([^)]*\)\s*=>\s*\n?\s*api\b/.test(src),
      `${f} van goi API trong vong lap chuong`,
    );
  }
});

test("co bao nhieu chuong cung chi mot lan goi getNovel", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  const goi = src.match(/api\.get\w+\(/g) || [];
  assert.equal(goi.length, 1, `phai dung 1 loi goi, dang co ${goi.length}`);
});

test("trang soan bai lay has_audio tu danh sach chuong", () => {
  const src = read("../src/app/write/page.tsx");
  assert.match(src, /c\.has_audio/);
  assert.ok(
    !/getChapter\([^)]*\)\s*\n?\s*\.then\(\(r\) => \[chapter\.chapter_id/.test(src),
    "khong con doc audio bang cach hoi tung chuong",
  );
});

test("has_audio khai bao tuy chon de khong pha client cu", () => {
  const api = read("../src/lib/api.ts");
  assert.match(api, /has_audio\?: boolean;/);
});

test("danh sach chuong dung has_audio chu khong dung state rieng", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  assert.match(src, /chapter\.has_audio \?/);
  assert.ok(!src.includes("audioReady"), "bo state trung gian da khong con can");
});

/* ===================================================================
   M1 — vung bam tren mobile toi thieu 44x44
   =================================================================== */

/** Cat lay khoi `@media (max-width: 640px)` trong globals.css. */
function mobileBlock() {
  const css = read("../src/app/globals.css");
  const start = css.indexOf("@media (max-width: 640px)");
  assert.ok(start >= 0, "khong tim thay khoi mobile");
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error("khoi mobile khong dong ngoac");
}

test("moi lop bam duoc deu cao it nhat 44px o mobile", () => {
  const block = mobileBlock();
  const rule = block.match(/([^{}]*)\{[^{}]*min-height:\s*44px[^{}]*\}/);
  assert.ok(rule, "khoi mobile khong co lop nao dat min-height 44px");
  // Tach danh sach selector ra roi so khop CHINH XAC, thay vi ghep regex —
  // ghep chuoi vao regex trong template literal rat de nuot mat dau gach cheo
  // va bien thanh mot assertion khong bao gio doi duoc gi.
  const selectors = rule[1]
    .replace(/\/\*[\s\S]*?\*\//g, "")   // bo chu thich
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  for (const cls of [".btn", ".btn-sm", ".chip", ".seg-item", ".nav-link",
                     ".account-link", ".brand"]) {
    assert.ok(
      selectors.includes(cls),
      `${cls} chua duoc nang len 44px o mobile (dang co: ${selectors.join(" ")})`,
    );
  }
});

test("nut co CHU dung min-height chu khong phai height co dinh", () => {
  // `height: 44px` se cat cut nut co chu dai xuong hai dong.
  //
  // Tru `.btn-icon` va `.play-btn-sm`: ca hai chi chua MOT ky hieu, vuong
  // 44x44 la dung y muon va khong co chu nao de tran ra. Bo dong dinh nghia
  // chung ra roi moi kiem.
  const block = mobileBlock()
    .split("\n")
    .filter((line) => !line.includes(".btn-icon") && !line.includes(".play-btn-sm"))
    .join("\n");
  assert.ok(
    !/[^-]height:\s*44px/.test(block.replace(/min-height/g, "MIN")),
    "phai dung min-height, khong duoc dat height cung",
  );
});

test("nut bieu tuong vuong du 44x44 o mobile", () => {
  const block = mobileBlock();
  const icon = block.match(/\.btn-icon \{[^}]*\}/);
  assert.ok(icon, "thieu ghi de .btn-icon o mobile");
  assert.match(icon[0], /width:\s*44px/);
  assert.match(icon[0], /height:\s*44px/);
});

test("chi ep 44px o mobile, khong ap len desktop", () => {
  const css = read("../src/app/globals.css");
  const before = css.slice(0, css.indexOf("@media (max-width: 640px)"));
  assert.ok(
    !/\.btn[^{]*\{[^}]*min-height:\s*44px/.test(before),
    "khong duoc ep 44px o desktop — con tro chuot chinh xac hon nhieu",
  );
});

test("nhom nut cuoi hang xuong dong rieng o mobile", () => {
  const block = mobileBlock();
  assert.match(block, /\.list-item\s*\{[^}]*flex-wrap:\s*wrap/);
  assert.match(block, /\.list-actions\s*\{[^}]*width:\s*100%/);
});

test("hang chuong dung .list-actions o ca hai trang", () => {
  for (const f of ["../src/app/novels/[id]/page.tsx", "../src/app/write/page.tsx"]) {
    assert.match(read(f), /className="list-actions"/, `${f} thieu .list-actions`);
  }
});

test("kich thuoc lien ket tai khoan nam trong CSS chu khong phai style inline", () => {
  const nav = read("../src/components/NavAuth.tsx");
  // Media query khong voi toi duoc style inline — day la bai hoc cua H1
  assert.match(nav, /"account-link"/);
  assert.match(nav, /"avatar"/);
  assert.ok(
    !/width:\s*28\b/.test(nav),
    "khong duoc dat lai kich thuoc avatar bang style inline",
  );
  const css = read("../src/app/globals.css");
  assert.match(css, /\.avatar\s*\{/);
  assert.match(css, /\.account-link\s*\{/);
});

/* ===================================================================
   M2 — nghe tai trang chi tiet truyen

   Vong overnight Phase 2 (Phan 2A): trinh phat KHONG con mo NGAY TRONG
   HANG nua — hang gio chi co hai lien ket [Đọc]/[Nghe], "Nghe" dan sang
   trang rieng `/listen/[id]` (dong co toan cuc DUY NHAT, xem
   `chapter-player.test.mjs`). Cac bai cu kiem hanh vi mo-tai-cho da bi
   XOA/THAY vi hanh vi do khong con nua, khong phai vi long lo test.
   =================================================================== */

test("trang chi tiet truyen KHONG con mo trinh phat ngay trong hang — dan sang /listen", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  assert.ok(
    !/import \{ AudioPlayer \}/.test(src) && !/<AudioPlayer/.test(src),
    "trang chi tiet truyen khong duoc tu mo AudioPlayer rieng nua — dung dong co toan cuc qua /listen",
  );
  assert.match(src, /href={`\/listen\/\$\{chapter\.chapter_id\}`}/);
  assert.match(src, /href={`\/chapters\/\$\{chapter\.chapter_id\}`}/);
});

test("chi chuong CO audio moi hien nut nghe", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  assert.match(src, /chapter\.has_audio \?/);
  const noAudio = src.slice(src.indexOf("chapter.has_audio ?"));
  assert.match(noAudio, /Chưa có audio/);
});

test("hang khong con boc ca trong the <a>", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  // <a> khong duoc chua <button>/<a> khac; ban cu boc ca hang trong
  // <Link className="list-item">.
  assert.ok(
    !/<Link[^>]*className="list-item"/.test(src),
    "the <a> khong duoc chua <button>/<a> khac",
  );
  assert.match(src, /className="list-item"/);
});

test("vung bam cua hang khong bi thu nho lai", () => {
  const css = read("../src/app/globals.css");
  // Lop phu trong suot keo vung bam cua lien ket tieu de ra kin ca hang
  assert.match(css, /\.list-title::after\s*\{[^}]*position:\s*absolute/);
  assert.match(css, /\.list-title::after\s*\{[^}]*inset:\s*0/);
  assert.match(css, /\.list-item\s*\{[^}]*position:\s*relative/);
  for (const f of ["../src/app/novels/[id]/page.tsx", "../src/app/write/page.tsx"]) {
    assert.match(read(f), /list-title/, `${f} thieu lop list-title`);
  }
});

test("nut nam TREN lop phu nen van bam duoc", () => {
  const css = read("../src/app/globals.css");
  // Cat khoi lenh dau tien cua mot selector, khong ghep selector vao regex
  const ruleFor = (cls) => {
    const at = css.indexOf(cls + " {");
    assert.notEqual(at, -1, `thieu ${cls}`);
    return css.slice(at, css.indexOf("}", at) + 1);
  };
  for (const cls of [".list-actions", ".list-player"]) {
    const rule = ruleFor(cls);
    assert.match(rule, /z-index:\s*1/, `${cls} phai nam tren lop phu`);
    assert.match(rule, /position:\s*relative/,
      `${cls} can position de z-index co tac dung`);
  }
});

test("hang dang phat cho xuong dong de trinh phat du rong", () => {
  const css = read("../src/app/globals.css");
  const rule = css.match(/\.list-item-open\s*\{[^}]*\}/);
  assert.ok(rule, "thieu .list-item-open");
  assert.match(rule[0], /flex-wrap:\s*wrap/);
  assert.match(css, /\.list-player\s*\{[^}]*width:\s*100%/);
});

test("dung lai AudioPlayer san co, khong tu ve trinh phat moi", () => {
  const src = read("../src/app/novels/[id]/page.tsx");
  // Tai lai component nen nut tai MP3, retry 404 va che do kho cuc bo giu nguyen
  assert.ok(!/<audio\b/.test(src), "phai dung AudioPlayer, khong tu dat the <audio>");
  assert.ok(!/resolveAudio|audioLink/.test(src), "khong duoc tu goi lai lop audio");
});

test("khong them ho endpoint nao ma khong di qua day", () => {

  // MOT nguon cho danh sach nay — xem `tests/_ho-endpoint.mjs`.

  const api = read("../src/lib/api.ts");

  kiemHoEndpoint(api);

  // Nghe tai cho dung dung duong da co, khong tao duong rieng
  assert.match(api, /audioLink:/);
  assert.match(api, /\/api\/audio\/\$\{chapterId\}\/url/);
});

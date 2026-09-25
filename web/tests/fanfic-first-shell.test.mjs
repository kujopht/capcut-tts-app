/*
 * Vo site huong FANFIC-FIRST.
 *
 * Thay doi o day la mot quyet dinh SAN PHAM, khong phai chuyen tham my: nen
 * tang nay de doc va nghe fanfic, con Audio Studio la cong cu phu. Neu khong
 * khoa lai, mot lan sap xep "cho tien tay" se dua cong cu ve lai vi tri dau
 * tien va nguoi doc lan dau se lai tuong day la trang tao giong noi.
 *
 * Cac test o day quet MA NGUON. Chung khong the chung minh giao dien DEP,
 * nhung chung chung minh duoc nhung dieu co the sai mot cach im lang:
 * route bi xoa, muc dieu huong bi doi thu tu, the truyen hien field khong co
 * that trong API, footer tro toi trang khong ton tai.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");

/* ============================================ khong pha thu dang chay tot */

test("moi route cu VAN con nguyen", () => {
  // Thiet ke lai vo site khong duoc lam mat mot trang nao. `/studio` la muc
  // quan trong nhat: no ra khoi thanh dieu huong chinh, KHONG ra khoi san pham.
  for (const route of [
    "../src/app/page.tsx",
    "../src/app/studio/audio/page.tsx",
    "../src/app/fanfic/page.tsx",
    "../src/app/studio/write/page.tsx",
    "../src/app/studio/library/page.tsx",
    "../src/app/account/page.tsx",
    "../src/app/login/page.tsx",
    "../src/app/novels/[id]/page.tsx",
    "../src/app/chapters/[id]/page.tsx",
  ]) {
    assert.ok(existsSync(new URL(route, import.meta.url)), `mất route ${route}`);
  }
});

test("Audio Studio giu nguyen chuc nang, chi doi cho VA doi khung", () => {
  /*
    "chi doi cho dung trong dieu huong" dung mot lan (Audio Studio thanh mot
    diem den o thanh ben). Lan nay (feat/studio-media-workspace) di xa hon:
    Audio/Phu de/Video gop thanh Media Studio, va logic vi the RAI tren nhieu
    tep hon mot trang don — moi dau hieu duoi day duoc do tren dung tep con
    giu no, khong phai tren MOT tep duy nhat nhu truoc.

    Hai dau hieu THAT SU bien mat, va co y: "AudioPlayer" (nghe tai cho qua
    mot trinh phat rieng cho danh sach lich su) va "Lịch sử audio" (mot khoi
    rieng duoi form). Ca hai duoc thay bang thu tot hon trong Media Studio —
    nghe qua `<Preview>` dung chung (cung mot dong ho voi video/phu de) va
    lich su qua Media Bin (kho tai san doc THANG tu backend, khong phai mot
    ban sao suy tu job) — nen bai nay kiem CHUC NANG thay the, khong doi lai
    ten cu.
  */
  const trang = read("../src/app/studio/media/page.tsx");
  const panel = read("../src/components/media/TtsPanel.tsx");
  const inspector = read("../src/components/media/Inspector.tsx");
  const preview = read("../src/components/media/Preview.tsx");

  for (const [dau_hieu, o_dau] of [
    ["MAX_CHARS", panel],          // gioi han ky tu
    [".createJob(", trang],        // tao job that
    ["useJobTracker", trang],      // theo doi tien trinh — dung chung voi `/write`
    ["ensureStudioNovel", trang],  // kho chua rieng cua Studio
    ["voiceSections", panel],      // bo chon giong
  ]) {
    assert.ok(o_dau.includes(dau_hieu), `Media Studio mất "${dau_hieu}"`);
  }

  // Nghe tai cho: khong con la mot <AudioPlayer> rieng, ma la <audio> dung
  // chung mot dong ho voi video/phu de trong Preview.
  assert.match(preview, /<audio /);
  // Tai MP3: khong con trong AudioPlayer, ma la mot lien ket tai xuong o
  // Inspector khi dang chon clip loi doc.
  assert.match(inspector, /href=\{urlAudio\} download/);
});

/* ============================================================ dieu huong */

test("thanh chinh khong con tung cong cu, chi con MOT loi vao Studio", () => {
  const nav = read("../src/components/NavAuth.tsx");
  const links = nav.slice(
    nav.indexOf("const LINKS"),
    nav.indexOf("export function NavLinks"),
  );
  assert.ok(!links.includes('"/studio/audio"'));
  assert.ok(!links.includes("Audio Studio"));

  // Tung cong cu KHONG con dung ten rieng o header. Chung la module ben
  // trong mot san pham, va ten cua san pham do la "Studio".
  const studio = nav.slice(
    nav.indexOf("function StudioLink"),
    nav.indexOf("function AccountMenu"),
  );
  assert.match(studio, /href="\/studio"/, "header thiếu lối vào Studio");
  // Khop tren DUONG DAN da ve, khong tren ca tep: chu thich trong `NavAuth`
  // van nhac ten cu de giai thich VI SAO menu bien mat, va mot bai kiem cam
  // nhac lich su la mot bai kiem cam viet chu thich.
  for (const cu of ["/image-studio", "/tools/subtitles", "/translate"]) {
    assert.ok(!nav.includes(`href="${cu}"`), `header vẫn trỏ tới ${cu}`);
  }
});

test("menu ben phai dung duoc bang ban phim va bang doc man hinh", () => {
  const nav = read("../src/components/NavAuth.tsx");
  assert.match(nav, /aria-haspopup="menu"/);
  assert.match(nav, /aria-expanded=\{open\}/);
  assert.match(nav, /role="menu"/);
  assert.match(nav, /role="menuitem"/);
  // Escape phai dong menu VA tra tieu diem ve nut mo — neu khong, nguoi dung
  // ban phim mat cho dung va phai Tab lai tu dau trang.
  assert.match(nav, /e\.key !== "Escape"/);
  assert.match(nav, /buttonRef\.current\?\.focus\(\)/);
  // Bam ra ngoai cung phai dong.
  assert.match(nav, /mousedown/);
});

test("muc dieu huong 'Trang chu' khop CHINH XAC, khong dung startsWith", () => {
  // `"/".startsWith` khop moi duong dan, nen moi trang trong site se cung sang
  // muc "Trang chủ". Day la mot loi de mac va kho thay.
  //
  // Phep so khop da chuyen len mot cho: `dangXem` duoc tinh MOT lan cho ca
  // `aria-current` lan vien thuoc dieu huong. Rang buoc thi y nguyen.
  //
  // Sprint 2: phep so khop chuyen vao `lib/navActive.ts` (trang truyen/chuong
  // sang "Thư viện") — hanh vi co bai kiem rieng o `nav-active.test.mjs`.
  const nav = read("../src/components/NavAuth.tsx");
  assert.match(nav, /const dangXem = mucDangXem\(pathname\);/);
  assert.match(read("../src/lib/navActive.ts"), /if \(pathname === "\/"\) return "\/";/);
  assert.match(nav, /const active = link\.href === dangXem;/);
});

test("Studio VAN co loi vao o footer cho nguoi khong mo menu", () => {
  /*
    Rang buoc la CO MOT LOI VAO Studio o footer, khong phai lien ket do tro
    toi dung `/studio/audio`.

    Ban dau bai nay chot `/studio/audio` vi luc ay Audio la cong cu duy nhat
    dang ke. Tu #197, `/studio` la trang chu cua ca bo cong cu, va chi thang
    toi mot module con o footer thi vua hep hon vua nguoc voi quyet dinh
    "tung cong cu khong con mang ten rieng o dieu huong".
  */
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /href="\/studio(\/[a-z]+)?"/,
    "footer khong con loi vao Studio");
});

/* ============================================================ tim kiem */

test("o tim nam trong header, khong phai mot thanh khong lo giua trang", () => {
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /<SiteSearch \/>/);
  // Trang chu KHONG duoc tu dung o tim thu hai.
  assert.ok(!read("../src/app/page.tsx").includes("SiteSearch"));

  // Y cua rang buoc la o tim phai NHO va co chan tren, khong phai mot con so
  // cu the: ban thiet ke lai gop o tim va nut "Tìm" thanh mot cum co chung
  // vien, nen be rong cua rieng o nhap doi theo.
  const rule = css().match(/\.input-search\s*\{[^}]*\}/)?.[0] ?? "";
  const rong = Number(rule.match(/width:\s*(\d+)px/)?.[1] ?? 0);
  assert.ok(rong > 0 && rong <= 240,
    `ô tìm ở header phải nhỏ, không tràn — đang là ${rong || "không đặt"}px`);
});

test("tim kiem khong nhan ban duong LOC thu hai", () => {
  /*
    Rang buoc nay da doi hinh nhung khong doi noi dung.

    Ban truoc: o tim o header CHI dieu huong sang `/fanfic?q=`, va bai test cam
    no goi API. V2 co mot overlay hien ket qua ngay, nen no PHAI goi API —
    nhung moi quan tam that su van y nguyen: khong duoc co mot duong LOC thu hai.

    Cu the:
      - overlay goi dung `browseNovels`, tuc la dung endpoint ma `/fanfic` dung;
      - no KHONG tu loc o trinh duyet;
      - va no luon co duong giao lai cho `/fanfic?q=` de xem day du.
  */
  /*
    Product UX Sprint 2: overlay hien them GOI Y TUC THI (fandom / tac gia /
    ten truyen) tu anh chup kho (`lib/searchSuggest.ts`) trong luc backend con
    tra loi — do that, vai giay moi truy van, va backend KHONG tim theo tac gia.
    Do la loi tat, KHONG phai danh sach ket qua thu hai: logic khop nam trong
    MOT module thuan co bai kiem rieng (`tests/search-suggest.test.mjs`), ket
    qua day du van cua `browseNovels`, va trang ket qua day du la Thu vien
    (`/library?q=`, nut tren thanh dieu huong) thay cho `/fanfic?q=`.
  */
  const overlay = read("../src/components/SearchOverlay.tsx");
  assert.match(overlay, /api\.browseNovels\(\{ query: tu/,
    "overlay không dùng lại đường tìm của backend");
  assert.match(overlay, /\/library\?q=\$\{encodeURIComponent\(tu\)\}/,
    "overlay không giao lại cho trang Thư viện");
  assert.match(overlay, /goiYTimKiem\(/, "gợi ý tức thì phải đi qua module thuần");
  assert.ok(!/\.filter\(/.test(overlay),
    "overlay tự lọc ở trình duyệt ngoài module gợi ý — đó là đường lọc thứ hai");

  // Va o header van chi la mot cai nut mo overlay, khong tu tim gi ca.
  const search = read("../src/components/SiteSearch.tsx");
  assert.ok(!search.includes("api."), "SiteSearch không được tự gọi API");
});

test("trang Kham pha nhan duoc ?q= va ?tag= tu URL", () => {
  const page = read("../src/app/fanfic/page.tsx");
  assert.match(page, /useSearchParams/);
  assert.match(page, /params\.get\("q"\)/);
  assert.match(page, /params\.get\("tag"\)/);
  // `useSearchParams` bat buoc phai co ranh gioi Suspense, neu khong
  // `next build` hong chu khong phai hong luc chay.
  assert.match(page, /<Suspense/);
});

/* ========================================================== the truyen */

test("the truyen CHI hien field co that trong API", () => {
  const card = read("../src/components/StoryCard.tsx");
  for (const field of ["title", "tags", "description", "updated_at", "cover_url"]) {
    assert.ok(card.includes(field), `thẻ truyện thiếu ${field}`);
  }
  // Ba thu KHONG co trong `Novel`, va bia ra la noi doi voi nguoi doc:
  //   * `Novel` chi co `owner_id`, khong co ten tac gia va khong co endpoint
  //     doi id sang ten;
  //   * so chuong chi lay duoc qua `getNovel` tung truyen — N+1;
  //   * luot nghe/luot xem khong ton tai o bat ky bang nao.
  for (const bia of ["chapter_count", "author_name", "view_count", "listen_count"]) {
    assert.ok(!card.includes(bia), `thẻ truyện bịa field "${bia}"`);
  }
});

test("the truyen dat BIA len tren cung", () => {
  const card = read("../src/components/StoryCard.tsx");
  const cover = card.indexOf("<NovelCover");
  const title = card.indexOf("story-title");
  assert.ok(cover > 0 && title > 0);
  assert.ok(cover < title, "bìa phải đứng trước tiêu đề");
});

test("trang chu va Kham pha dung CHUNG bo ve bia truyen", () => {
  // /fanfic dung the day du; trang chu chu dinh dung hang doc gon. Ca hai
  // van chia se NovelCover de cung URL bia/fallback va khong lech hien thi.
  for (const f of ["../src/app/page.tsx", "../src/components/StoryCard.tsx"]) {
    assert.match(read(f), /from "@\/components\/NovelCover"/, f);
  }
  assert.match(read("../src/app/fanfic/page.tsx"), /from "@\/components\/StoryCard"/);
});

test("trang chu chi goi so request CO DINH, khong phu thuoc so truyen", () => {
  // V4 visual completion, Phan B: them `getContinueProgress` cho module Tiep
  // tuc doc/nghe — VAN co dinh (mot lan cho ho so nguoi dang nhap), khong
  // tang theo so truyen, nen khong pha rang buoc N+1 ma bai test nay giu.
  //
  // Vong 2, Buoc 12: them `getProgress`/`getAchievements` cho dong nho
  // gamification o dau trang — CUNG co dinh (mot lan cho ho so nguoi dang
  // nhap, khong lap theo so truyen).
  //
  // V2 Homepage Hub: them `listAnimationSeries` cho ke "Animation mới" —
  // MOT lan goi CO DINH (limit co dinh, khong phu thuoc so truyen/series),
  // goi SONG SONG trong cung `Promise.all`. `social.feed(...)` (ke cong
  // dong) nam o namespace `social.`, khong khop regex `api\.\w+\(` nen
  // khong can liet ke o day — van la MOT request co dinh, xem than ham
  // `load`.
  //
  // Phuc hoi Storyworld Portal (2026-08-24): them `getLeaderboard` cho ke
  // "Bảng vàng tuần" — CUNG co dinh (mode/limit/offset co dinh, khong phu
  // thuoc so truyen), goi SONG SONG trong cung `Promise.all`.
  const home = read("../src/app/page.tsx");
  const calls = home.match(/api\.\w+\(/g) ?? [];
  assert.deepEqual(
    calls.sort(),
    [
      "api.browseNovels(",
      "api.getAchievements(",
      "api.getContinueProgress(",
      "api.getLeaderboard(",
      "api.getProgress(",
      "api.listAnimationSeries(",
      "api.novelTags(",
    ],
  );
});

test("trang chu goi dung ten thu no co: 'Truyen moi', khong phai 'noi bat'", () => {
  // `GET /api/novels` chi `orderDesc(created_at)` va KHONG nhan tham so sort.
  // Nen khong the co muc "mới cập nhật", "nổi bật" hay "nghe nhiều" that —
  // dat nhung nhan do len mot danh sach sap theo ngay tao la noi sai.
  const home = read("../src/app/page.tsx");
  assert.match(home, /Truyện mới/);
  for (const nhan of ["Nổi bật", "Đề cử", "Nghe nhiều", "Xem nhiều", "Thịnh hành"]) {
    assert.ok(!home.includes(nhan), `trang chủ dùng nhãn "${nhan}" mà không có dữ liệu`);
  }
});

/* ============================================================== footer */

test("footer chi tro toi route CO THAT", () => {
  const layout = read("../src/app/layout.tsx");
  const footer = layout.slice(layout.indexOf('<footer className="site-footer">'));
  const hrefs = [...footer.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(hrefs.length >= 5, "footer quá nghèo nàn");

  const co_that = new Set([
    "/", "/fanfic", "/account",
    // Cong cu nay nam duoi `/studio/*` (Fanfic Studio). Duong dan cu van
    // chay nho chuyen huong 308 trong `next.config.mjs`, nhung footer thi
    // tro THANG toi dia chi moi — mot lien ket noi bo khong nen ton mot
    // vong chuyen huong.
    "/studio", "/studio/library", "/studio/write", "/studio/audio",
    // Thu vien CUA NGUOI DOC (`src/app/library/page.tsx`) — truyen dang theo
    // doi + cho doc do. Khac `/studio/library`, von la thu vien AUDIO cua
    // nguoi sang tac; xem ghi chu tren `LINKS` trong `NavAuth.tsx`.
    "/library",
  ]);
  for (const href of hrefs) {
    assert.ok(co_that.has(href), `footer trỏ tới route không tồn tại: ${href}`);
  }
});

test("footer KHONG tao trang phap ly gia", () => {
  // Mot lien ket "Điều khoản" tro toi trang khong ton tai la lien ket hong;
  // tao mot trang phap ly rong con te hon, vi no ngu y mot cam ket ma khong
  // ai viet ra.
  const layout = read("../src/app/layout.tsx");
  const footer = layout.slice(layout.indexOf('<footer className="site-footer">'));
  for (const gia of ["Điều khoản", "Chính sách", "Bảo mật", "Liên hệ", "Về chúng tôi"]) {
    assert.ok(!footer.includes(gia), `footer có mục pháp lý giả: ${gia}`);
  }
});

/* ========================================================== responsive */

test("luoi truyen co quy tac cho mobile, the featured gioi han rong o moi be", () => {
  // `.hero-story` (luoi 2 cot bia/chu) da bi thay boi `.story-card-featured`
  // (V4 visual completion, Phan A/E) — mot cot flex don, KHONG can quy tac
  // rieng cho tablet vi no khong bao gio la luoi nhieu cot de phai gap lai.
  // Rang buoc con lai la `max-width`: the KHONG duoc phep rong het container
  // o BAT KY be nao, do chinh la thu ngan no thanh hero nua trang.
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  assert.match(text, /\.story-card-featured \{[^}]*max-width:\s*\d+px/s);
  assert.match(mobile, /\.story-grid \{ grid-template-columns/);
  assert.match(mobile, /\.footer-grid \{ grid-template-columns/);
});

test("luoi truyen o mobile KHONG rut ve mot cot", () => {
  // Hai cot bia hep van doc duoc ten va cho thay nhieu truyen hon trong mot
  // man hinh — dung y cua trang kham pha. Mot cot thi phai cuon rat nhieu moi
  // thay duoc truyen thu ba.
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  const rule = mobile.match(/\.story-grid \{([^}]*)\}/)?.[1] ?? "";
  assert.match(rule, /auto-fill/);
  assert.ok(!/minmax\(0, 1fr\)/.test(rule), "lưới truyện bị rút về một cột");
});

test("nhan trong the truyen KHONG bi nang len 44px o mobile", () => {
  // Khoi M1 nang MOI `.chip` len 44px vi chip thuong la vung bam. Nhan trong
  // the truyen thi khong bam duoc, va 44px se lam the phinh ra vo co.
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.chip-static \{[^}]*min-height:\s*0/);
});

test("khong co mau hex nao trong cac tep giao dien moi", () => {
  for (const f of [
    "../src/app/page.tsx",
    "../src/components/StoryCard.tsx",
    "../src/components/SiteSearch.tsx",
    "../src/components/NavAuth.tsx",
  ]) {
    const hex = read(f).match(/#[0-9a-fA-F]{6,8}\b/g) ?? [];
    assert.deepEqual(hex, [], `${f} còn màu hardcode: ${hex.join(" ")}`);
  }
});

test("hex duy nhat trong layout la themeColor, va no BUOC phai la hex", () => {
  // `themeColor` to mau thanh trinh duyet, khong phai to mot phan tu trong
  // trang — trinh duyet doc no truoc khi co CSS nao chay, nen `var(--bg)`
  // khong dung duoc o day. Khoa lai de no khong tro thanh cai co cho mot mau
  // hardcode thu hai lot vao.
  const layout = read("../src/app/layout.tsx");
  const hex = layout.match(/#[0-9a-fA-F]{6,8}\b/g) ?? [];
  assert.deepEqual(hex, ["#08090f"]);
  assert.match(layout, /themeColor: "#08090f"/);

  // Va no phai BANG DUNG `--bg`. Lech nhau thi thanh trinh duyet vien mot mau
  // khac han nen trang — thay ro nhat tren dien thoai.
  const css = read("../src/app/globals.css");
  assert.match(css, /--bg: #08090f;/, "themeColor không còn khớp `--bg`");
});

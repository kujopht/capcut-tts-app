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
    "../src/app/studio/page.tsx",
    "../src/app/fanfic/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/library/page.tsx",
    "../src/app/account/page.tsx",
    "../src/app/login/page.tsx",
    "../src/app/novels/[id]/page.tsx",
    "../src/app/chapters/[id]/page.tsx",
  ]) {
    assert.ok(existsSync(new URL(route, import.meta.url)), `mất route ${route}`);
  }
});

test("Audio Studio giu nguyen chuc nang, chi doi cho dung trong dieu huong", () => {
  const studio = read("../src/app/studio/page.tsx");
  for (const dau_hieu of [
    "MAX_CHARS",          // gioi han ky tu
    ".createJob(",        // tao job that
    ".getJob(",           // theo doi tien trinh
    "ensureStudioNovel",  // kho chua rieng cua Studio
    "voiceSections",      // bo chon giong
    "AudioPlayer",        // nghe tai cho
    "Lịch sử audio",
  ]) {
    // So khop `.getJob(` chu khong phai `api.getJob`: vong poll viet la
    // `api\n  .getJob(...)`, nen chuoi lien tuc `api.getJob` khong ton tai.
    assert.ok(studio.includes(dau_hieu), `Audio Studio mất "${dau_hieu}"`);
  }
});

/* ============================================================ dieu huong */

test("thanh chinh khong con Audio Studio, nhung menu Cong cu thi co", () => {
  const nav = read("../src/components/NavAuth.tsx");
  const links = nav.slice(
    nav.indexOf("const LINKS"),
    nav.indexOf("export function NavLinks"),
  );
  assert.ok(!links.includes("/studio"));
  assert.ok(!links.includes("Audio Studio"));

  // Audio Studio la mot CONG CU rieng, khong phai mot khu vuc san pham. Cho
  // cua no la menu "Công cụ" — tach han khoi menu tai khoan.
  const tools = nav.slice(
    nav.indexOf("function ToolsMenu"),
    nav.indexOf("function AccountMenu"),
  );
  assert.match(tools, /Công cụ/);
  assert.match(tools, /href="\/studio"/, "menu Công cụ thiếu Audio Studio");
  assert.match(tools, /Audio Studio/);
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
  const nav = read("../src/components/NavAuth.tsx");
  assert.match(nav, /link\.href === "\/"\s*\n?\s*\?\s*pathname === "\/"/);
});

test("Audio Studio VAN co loi vao o footer cho nguoi khong mo menu", () => {
  assert.match(read("../src/app/layout.tsx"), /href="\/studio"/);
});

/* ============================================================ tim kiem */

test("o tim nam trong header, khong phai mot thanh khong lo giua trang", () => {
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /<SiteSearch \/>/);
  // Trang chu KHONG duoc tu dung o tim thu hai.
  assert.ok(!read("../src/app/page.tsx").includes("SiteSearch"));

  const rule = css().match(/\.input-search\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rule, /width:\s*200px/, "ô tìm ở header phải nhỏ, không tràn");
});

test("o tim chi DIEU HUONG, khong nhan ban duong tim thu hai", () => {
  const search = read("../src/components/SiteSearch.tsx");
  assert.match(search, /\/fanfic\?q=/);
  assert.match(search, /encodeURIComponent/);
  // Toan bo tim/loc/phan trang da do BACKEND lam o `/fanfic`. Goi thang API o
  // day la tao duong thu hai, va hai duong se lech nhau.
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

test("trang chu va Kham pha dung CHUNG mot the truyen", () => {
  for (const f of ["../src/app/page.tsx", "../src/app/fanfic/page.tsx"]) {
    assert.match(read(f), /from "@\/components\/StoryCard"/, f);
  }
});

test("trang chu chi goi HAI request, khong phu thuoc so truyen", () => {
  const home = read("../src/app/page.tsx");
  const calls = home.match(/api\.\w+\(/g) ?? [];
  assert.deepEqual(calls.sort(), ["api.browseNovels(", "api.novelTags("]);
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

  const co_that = new Set(["/", "/fanfic", "/library", "/write", "/studio", "/account"]);
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

test("hero va luoi truyen deu co quy tac cho tablet va mobile", () => {
  const text = css();
  const tablet = text.slice(text.indexOf("@media (max-width: 900px)"));
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  assert.match(tablet, /\.hero-story \{ grid-template-columns/);
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
  assert.deepEqual(hex, ["#0b0d12"]);
  assert.match(layout, /themeColor: "#0b0d12"/);
});

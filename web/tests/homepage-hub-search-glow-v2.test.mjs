/*
 * Homepage Hub V2 + sua lai hieu ung dieu huong (2026-08) — rang buoc cua
 * vong thiet ke nay. Chuan hoa CRLF -> LF truoc khi so khop chuoi chinh xac
 * (checkout tren Windows co the ghi CRLF, xem bai hoc o
 * `admin-trusted-sources.test.mjs`).
 *
 * SUA LAI (Navigation Motion Correction v1): vong truoc hieu nham yeu cau va
 * ve mot khung nang luong XOAY LIEN TUC quanh o tim. Nguoi dung KHONG muon
 * vay — o tim tra ve tinh gian, va hieu ung "di chuyen" ho thuc su muon nam o
 * VACH DIEU HUONG dang xem (`.nav-vach`, `NavIndicator.tsx`). Cac test cu cho
 * khung xoay o tim da bi XOA va thay bang test cho hanh vi MOI o duoi day.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const home = () => read("../src/app/page.tsx");

/** Bo chu thich truoc khi quet — xem `redesign.test.mjs`. */
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

/* ============================================== o tim: TINH GIAN, khong xoay */

test("KHONG con khung nang luong xoay lien tuc quanh o tim (da bi loai bo)", () => {
  const css_ = css();
  assert.ok(!css_.includes("tim-vien-xoay"), "vẫn còn keyframe xoay đã bị gỡ");
  assert.ok(!css_.includes("tim-vien-mach"), "vẫn còn keyframe mạch đã bị gỡ");
  assert.ok(!css_.includes("tim-hop-dang-tim"), "vẫn còn lớp trạng thái của khung xoay cũ");
  assert.ok(!/\.tim-nut::before/.test(css_), "nút gọn vẫn có pseudo-element viền xoay");
  assert.ok(!/\.tim-hop::before/.test(css_), "hộp tìm vẫn có pseudo-element viền xoay");
});

test("o tim go gon: IDLE tinh, HOVER chi sang vien (khong them glow/animation)", () => {
  const nut = codeOnly(rule(".tim-nut"));
  assert.ok(!/box-shadow:/.test(nut), "IDLE vẫn có box-shadow — spec yêu cầu viền tĩnh, không glow");
  assert.ok(!/animation:/.test(nut));
  assert.match(nut, /border: 1px solid var\(--line\)/);
  const hover = codeOnly(rule(".tim-nut:hover"));
  assert.match(hover, /border-color: var\(--line-strong\)/);
  assert.ok(!/box-shadow:/.test(hover), "HOVER thêm box-shadow — spec yêu cầu CHỈ viền sáng hơn");
});

test("hop tim mo rong (FOCUS): quang TINH, khong keyframe, co vien accessible", () => {
  const hop = codeOnly(rule(".tim-hop"));
  assert.match(hop, /box-shadow:/);
  assert.ok(!/animation:/.test(hop), "FOCUS vẫn có animation liên tục");
  // O nhap ben trong van co vien tieu diem ro rang khi dieu huong bang ban phim.
  const dau = rule(".tim-dau:focus-within");
  assert.match(dau, /box-shadow: var\(--ring\)/);
});

test("SEARCHING: chi bao nho o BEN TRONG (spinner), khong phai ca khung tim quay", () => {
  const overlay = read("../src/components/SearchOverlay.tsx");
  assert.match(overlay, /trangThai === "dang-tai"/);
  assert.match(overlay, /className="spinner"/);
  // KHONG con class trang thai rieng cho ca hop tim (do la co che cua khung xoay cu).
  assert.ok(!overlay.includes("tim-hop-dang-tim"));
});

test("KHONG dung requestAnimationFrame o component tim kiem", () => {
  for (const f of ["../src/components/SearchOverlay.tsx", "../src/components/SiteSearch.tsx"]) {
    assert.ok(!read(f).includes("requestAnimationFrame"), `${f} dùng rAF cho hiệu ứng`);
  }
});

test("placeholder o tim phan anh toan bo nen tang, khong chi truyen", () => {
  const btn = read("../src/components/SiteSearch.tsx");
  const overlay = read("../src/components/SearchOverlay.tsx");
  for (const src of [btn, overlay]) {
    assert.match(src, /Tìm truyện, tác giả, Animation/);
  }
});

/* ===================================== vach dieu huong: "cong dich" di chuyen */

test("vach dieu huong TRUOT bang transform/width, KHONG dung JS rAF", () => {
  // Loai bo chu thich truoc: docstring cua file GIAI THICH vi sao KHONG dung
  // rAF, nen ban than chu "requestAnimationFrame" xuat hien trong prose.
  const src = codeOnly(read("../src/components/NavIndicator.tsx"));
  assert.ok(!src.includes("requestAnimationFrame"));
  const nav = rule(".nav-vach");
  assert.match(nav, /transform \d+ms/);
  assert.match(nav, /width \d+ms/);
});

test("width TOI DICH cham hon transform mot chut — tao cam giac gian/nen nhe", () => {
  // Khong dung mot thuoc tinh/animation rieng cho "stretch": chi lech thoi
  // luong giua hai transition da co (transform vs width) la du tao cam giac
  // khung tam thoi gian dai hon dich roi mem lai.
  const nav = rule(".nav-vach");
  const t = Number(nav.match(/transform (\d+)ms/)?.[1]);
  const w = Number(nav.match(/width (\d+)ms/)?.[1]);
  assert.ok(t > 0 && w > 0);
  assert.ok(w > t, `width (${w}ms) phải chậm hơn transform (${t}ms) để tạo hiệu ứng giãn nhẹ`);
  assert.ok(w - t <= 150, "lệch quá xa sẽ trông như lỗi, không phải hiệu ứng có chủ đích");
});

test("vet sang 'cong dich' chay MOT LAN khi vach den noi, dung lai keyframe sheen da co", () => {
  const css_ = css();
  const streak = rule(".nav-vach-streak");
  assert.match(streak, /animation: sheen \d+ms var\(--ease\) 1\b/, "phải chỉ định 1 lần lặp, không phải infinite");
  assert.ok(!css_.match(/\.nav-vach-streak[^}]*infinite/s), "vệt sáng lặp vô hạn — spec yêu cầu MỘT LẦN rồi tắt hẳn");

  const src = read("../src/components/NavIndicator.tsx");
  assert.match(src, /key=\{o\.tick\}/, "vệt sáng phải remount theo tick để animation chạy lại mỗi lần đổi route");
  // tick CHI tang khi MUC that su doi — khong tang khi do lai vi resize/cuon.
  assert.match(src, /truoc\.moc !== moc/);
});

test("vach + vet sang deu duoc tat/nhay tuc thi duoi prefers-reduced-motion", () => {
  const css_ = css();
  const khoi = css_.slice(
    css_.indexOf("@media (prefers-reduced-motion: reduce)"),
    css_.indexOf("@media (prefers-reduced-motion: reduce)") + 4000,
  );
  assert.match(khoi, /\.nav-vach \{ transition: none; \}/);
  assert.match(khoi, /\.nav-vach-streak \{ display: none; \}/);
});

/* ==================================================== homepage hub ======== */

test("hero moi la mot vung noi dung, khong phai chia doi 50/50", () => {
  for (const m of css().matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (/hero/i.test(m[1])) {
      assert.ok(
        !/grid-template-columns:\s*1fr\s+1fr/.test(m[2]),
        `khu hero chia đôi 50/50: ${m[1].trim().slice(0, 60)}`,
      );
    }
  }
});

test("luoi tinh nang LUON ve, khong phu thuoc so truyen/animation/cong dong", () => {
  const src = home();
  const at = src.indexOf("<LuoiTinhNang");
  assert.notEqual(at, -1);
  // Phai nam TRUOC nhanh dieu kien cua ke "Đang nổi bật" (loading/error/rong) —
  // nghia la khong bi mot `&&`/ternary nao cua du lieu truyen bao quanh.
  assert.ok(at < src.indexOf('id="home-noi-bat"'));
  const truoc = src.slice(Math.max(0, at - 200), at);
  assert.ok(!/animationSeries\.length|communityPosts\.length|novels\.length/.test(truoc),
    "lưới tính năng bị một điều kiện dữ liệu bao quanh");
});

test("6 the tinh nang CHI tro toi duong da co that", () => {
  const src = home();
  const atDanhSach = src.indexOf("DANH_SACH_TINH_NANG");
  const than = src.slice(atDanhSach, src.indexOf("function LuoiTinhNang"));
  const hrefs = [...than.matchAll(/href:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(hrefs, [
    "/fanfic", "/animation", "/studio", "/community", "/write", "/image-studio",
  ]);
  // Va cac thu muc route nay phai THAT SU ton tai trong web/src/app.
  for (const href of hrefs) {
    const dir = new URL(`../src/app${href}`, import.meta.url);
    assert.ok(existsSync(dir), `route ${href} không tồn tại`);
  }
});

test("ke Animation moi / cong dong TU AN khi rong, khong ve hop rong to", () => {
  const src = home();
  assert.match(src, /animationSeries\.length > 0 \? \(/);
  assert.match(src, /communityPosts\.length > 0 \? \(/);
  /*
    Rong thi tra `null` (khong ve gi), khong phai mot `EmptyState` day du.
    Ke truyen (ke quan trong nhat) TUNG la ngoai le DUY NHAT dung `EmptyState`
    — phuc hoi 2026-08-23 tu `feature/fanfic-visual-renaissance-v1` thay no
    bang `KeTrongNoiBat` (o trong co hoa tiet minh hoa, xem `globals.css`
    `.empty-noibat`), nen gio KHONG con `<EmptyState` nao tren trang chu nua.
  */
  assert.equal((src.match(/<EmptyState/g) ?? []).length, 0,
    "trang chủ không còn dùng EmptyState nữa — ke truyện dùng KeTrongNoiBat");
  assert.match(src, /<KeTrongNoiBat \/>/, "thiếu ô trống minh hoạ cho kệ truyện");
});

test("KeTrongNoiBat dung hoa tiet rieng, KHONG dinh vao he thong Storyworld Portal", () => {
  /*
    Phuc hoi 2026-08-23: ban goc tren `feature/fanfic-visual-renaissance-v1`
    dung chung ten class voi The Gioi Cong (tien to "portal-"), nhung The
    Gioi Cong CHU DINH khong duoc phuc hoi (xem bao cao Phase A). Bai nay
    khoa lai rang lan phuc hoi nay dung TEN CLASS RIENG, khong vo tinh keo
    theo phu thuoc nao cua he thong Portal.
  */
  const src = home();
  assert.match(src, /import \{ MotifManuscript, MotifWaveArcs \} from "@\/components\/Ornaments"/);
  assert.match(src, /className="empty-noibat"/);
  assert.match(src, /className="empty-noibat-motif"/);
  assert.match(src, /className="empty-noibat-body"/);
  assert.ok(!/className="portal-/.test(src), "trang chủ không được dùng class hệ thống Portal");

  const than = rule(".empty-noibat");
  assert.match(than, /border-radius: var\(--r4\)/);
  assert.match(than, /display: flex/);
});

test("khong bia so lieu backend khong ho tro (luot xem/nghe/theo doi gia)", () => {
  const src = home();
  for (const bia of [
    "lượt đọc", "lượt nghe", "lượt xem", "nổi bật nhất",
    "người theo dõi", "đang xem cùng", "trending",
  ]) {
    assert.ok(!src.includes(bia), `trang chủ bịa số liệu: ${bia}`);
  }
  // KHONG co ke "Mới cập nhật"/"Nghe ngay" rieng — hai muc nay doi hoi du
  // lieu backend KHONG ho tro (xem docstring dau `page.tsx`). Bo chu thich
  // truoc khi quet, vi chinh docstring do nhac lai hai cum tu nay khi giai
  // thich ly do KHONG dung (khong phai chuoi hien ra man hinh).
  const ma = codeOnly(src);
  assert.ok(!ma.includes("Mới cập nhật"));
  assert.ok(!ma.includes("Nghe ngay"));
});

test("khach vang lai KHONG thay dai thanh vien/tiep tuc — chi CTA dang nhap o Hero", () => {
  const src = home();
  const atHero = src.indexOf("function Hero(");
  const thanHero = src.slice(atHero, src.indexOf("function DaiThanhVien"));
  assert.match(thanHero, /!daDangNhap \? \(/);
  assert.match(thanHero, /hero-v2-guest-hint/);

  const atThanhVien = src.indexOf("function DaiThanhVien(");
  const thanThanhVien = src.slice(atThanhVien, src.indexOf("interface TinhNang"));
  assert.match(thanThanhVien, /if \(!gamification\) return null;/);

  // "Tiếp tục của bạn" chỉ dựng bên trong nhánh `daDangNhap ? (`.
  const atTiepTuc = src.indexOf('id="home-tiep-tuc"');
  const truocDo = src.slice(Math.max(0, atTiepTuc - 200), atTiepTuc);
  assert.match(truocDo, /daDangNhap \? \(/);
});

test("da dang nhap nhung chua co gi de tiep tuc: mot dong onboarding GON, khong phai khoi rong to", () => {
  const src = home();
  assert.match(src, /<KeTrongGon/);
  const atKe = src.indexOf("function KeTrongGon");
  const than = src.slice(atKe, src.indexOf("function TheCongDong"));
  assert.match(than, /shelf-empty-compact/);
  // KHONG dung `EmptyState` day du (qua to) cho truong hop nay.
  assert.ok(!than.includes("<EmptyState"));
});

test("ke cong dong dung API cong khai /api/feed, khong bia du lieu", () => {
  const src = home();
  assert.match(src, /social\.feed\(/);
  assert.match(src, /import\s*\{[^}]*api,\s*\n?\s*social,/s);
});

test("moi ke co section rieng voi aria-labelledby", () => {
  const src = home();
  for (const id of [
    "home-hero-title", "home-tiep-tuc", "home-tinh-nang", "home-noi-bat",
    "home-animation", "home-cong-dong", "home-the", "home-kham-pha-nhanh",
    "home-tac-gia",
  ]) {
    assert.ok(
      src.includes(`id="${id}"`),
      `thiếu id "${id}" cho aria-labelledby`,
    );
  }
});

test("responsive: hero va luoi tinh nang co quy tac rieng o mobile (640px)", () => {
  const text = css();
  const at = text.indexOf("@media (max-width: 640px)");
  assert.notEqual(at, -1);
  const mobile = text.slice(at);
  assert.match(mobile, /\.hero-v2 \{/);
  assert.match(mobile, /\.hero-v2-cta \.btn \{ flex: 1 1 auto; \}/);
});

test("trang chu KHONG dung style inline (media query khong voi toi duoc)", () => {
  assert.ok(!/style=\{\{/.test(home()), "trang chủ còn style inline");
});

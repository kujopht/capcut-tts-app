/*
 * Fanfic World Visual Renaissance — Phase 3.6 (2026-08).
 *
 * "NAV V6 + FLOATING NAVBAR + PAGE HEADER SYSTEM + HOMEPAGE RHYTHM".
 *
 * Bon nhom thay doi kiem trong file nay:
 *   1. Nav V6: hinh hoc Write CTA do THAT (xem thêm
 *      nav-indicator-motion-correction-v6.test.mjs cho chi tiet do luong).
 *   2. Navbar noi (floating dock) + nut Đăng nhập rieng, khong dung glow tim
 *      to cua `.btn-primary` toan cuc.
 *   3. He thong page-header: khong con "hop chu nhat den" — scrim cuc bo,
 *      hoa tiet SVG rieng cho tung khu vuc, khong bia icon rong.
 *   4. Phan biet LOADING/EMPTY: EmptyState co the nhan hoa tiet SVG
 *      (`art`) thay emoji cho cac trang thai rong quan trong.
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

/* ===================================== F/G: floating navbar dock ========= */

test(".site-header noi tach khoi mep trang: co margin-top VA sticky top CUNG mot gia tri (khong nhay)", () => {
  const than = codeOnly(rule(".site-header"));
  const top = than.match(/top:\s*(\d+)px/)?.[1];
  const margin = than.match(/margin:\s*(\d+)px auto 0/)?.[1];
  assert.notEqual(top, undefined, "thiếu top (sticky offset)");
  assert.notEqual(margin, undefined, "thiếu margin-top tĩnh khớp với sticky offset");
  assert.equal(top, margin, "top và margin-top lệch nhau — sẽ có một cú nhảy lúc bắt đầu cuộn");
  assert.match(than, /border-radius:\s*1[4-8]px/, "bo góc phải trong khoảng 14-18px đặc tả");
  assert.ok(!/width:\s*100%/.test(than), "vẫn full-bleed — phải tách khỏi mép trang");
});

test(".site-header KHONG co quang mau (box-shadow trung tinh, khong nhuom tim/cyan)", () => {
  const than = codeOnly(rule(".site-header"));
  assert.match(than, /box-shadow:\s*0 \d+px \d+px #00000/, "box-shadow phải là màu đen trung tính");
  assert.ok(!/#8b6cff|#22d3ee|var\(--brand\)|var\(--accent\)/.test(than),
    "box-shadow/border không được nhuộm màu thương hiệu — cấm glow màu");
});

test("cuon xuong CHI doi do dac be mat (opacity), khong to/nho lai, khong nay", () => {
  const than = codeOnly(rule('.site-header[data-scrolled="true"]'));
  assert.ok(!/width:|height:|transform:|scale/.test(than),
    "trạng thái cuộn không được đổi kích thước/transform — cấm shrink/bounce");
});

test("SUA LOI PHAT HIEN: khong tu tay viet ca backdrop-filter LAN -webkit-backdrop-filter cho cung mot lop kinh", () => {
  // Phat hien luc lam navbar noi: viet CA HAI dong tay lam buoc build gop
  // nham chi con lai ban `-webkit-` — ma Chrome/Firefox hien dai KHONG nhan
  // bien alias do (da xac minh bang CSS.supports trong trinh duyet that),
  // nen ca lop kinh MAT HAN hieu ung mo (chi con mau nen trong suot). Chi
  // viet thuoc tinh CHUAN; build tu them ban `-webkit-` dung (da xac nhan
  // tren CSS bien dich thuc te).
  const text = codeOnly(css());
  const lines = text.split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    const a = lines[i].match(/^\s*backdrop-filter:\s*(.+);\s*$/);
    const b = lines[i + 1]?.match(/^\s*-webkit-backdrop-filter:\s*(.+);\s*$/);
    if (a && b && a[1] !== "none") {
      assert.ok(a[1] !== b[1], `dòng ${i + 1}: vẫn tự viết tay cả hai dạng cùng giá trị "${a[1]}"`);
    }
  }
});

test("khong dung requestAnimationFrame/vong lap JS cho hieu ung cuon — chi mot co scroll passive", () => {
  const src = codeOnly(read("../src/components/SiteHeader.tsx"));
  assert.ok(!/requestAnimationFrame/.test(src));
  assert.match(src, /\{ passive: true \}/);
});

/* ============================================= I: nut Dang nhap rieng ==== */

test("nut Đăng nhập trong header dung lop rieng (.nav-login), KHONG doi .btn-primary toan cuc", () => {
  const navAuth = codeOnly(read("../src/components/NavAuth.tsx"));
  assert.match(navAuth, /className="btn btn-primary btn-sm nav-login"/);
  const than = codeOnly(rule(".nav-login"));
  assert.ok(!/box-shadow:\s*(?!none)/.test(than) || /box-shadow:\s*none/.test(than),
    "nav-login vẫn còn box-shadow màu — cấm 'purple box-shadow lớn'");
  // Cac CTA khac (Khám phá, Bắt đầu viết...) van dung .btn-primary nguyen ban
  // — xac nhan .btn-primary GOC khong bi doi (van co --lift-brand).
  assert.match(codeOnly(rule(".btn-primary")), /var\(--lift-brand\)/);
});

test("nav-login: hover chi dich chuyen nho (-1px), khong vet sang quet lap", () => {
  const hover = codeOnly(rule(".nav-login:hover:not(:disabled)"));
  assert.match(hover, /translateY\(-1px\)/);
  const after = codeOnly(rule(".nav-login::after"));
  assert.match(after, /display:\s*none/);
});

/* ===================================== H: active nav KHONG glow (V6 audit) */

test("khong co pulsing/looping glow moi tren nut Đăng nhập hay .site-header", () => {
  for (const sel of [".nav-login", ".nav-login:hover:not(:disabled)", ".site-header"]) {
    const than = codeOnly(rule(sel));
    assert.ok(!/animation:\s*(?!none)/.test(than), `${sel} không được có animation lặp`);
  }
});

/* ============================== J/K: page-head KHONG con hop chu nhat den = */

test(".page-head: nen chinh trong suot — CHI ::before (radial-gradient cuc bo) tao do tuong phan", () => {
  const than = codeOnly(rule(".page-head"));
  assert.ok(!/background:/.test(than), ".page-head chính không được có background riêng (phải để ::before lo)");
  const before = codeOnly(rule(".page-head::before"));
  assert.match(before, /radial-gradient\(/);
  assert.match(before, /transparent/, "phải tàn dần vào tranh nền — không phải một khối đặc");
});

test(".page-head::before feather ra ngoai NHIEU DIEM DUNG (khong phai mot lop mo dong deu)", () => {
  const before = codeOnly(rule(".page-head::before"));
  const stops = before.match(/\d+%/g) ?? [];
  assert.ok(stops.length >= 4, "cần nhiều điểm dừng để tan dần tự nhiên, không phải một khối phẳng");
});

/* =============================================== M: hoa tiet rieng tung trang */

test("Cộng đồng co icon rieng trong PageHeader (truoc day thieu hoan toan)", () => {
  const src = codeOnly(read("../src/app/community/page.tsx"));
  assert.match(src, /icon=\{<IconMegaphone \/>\}/);
});

/* ===================================== N: search bar Explore/Animation === */

test(".filter-bar .input nhe hon .input mac dinh — khong con la 'thanh den nang'", () => {
  const base = codeOnly(rule(".input, .textarea, .select"));
  assert.match(base, /background:\s*#0b0d14/, "input mặc định (form thật) vẫn nên đặc — không đổi ở đây");
  // Themed Page Hero V1, Phan 16: mau nen gio tron theo `--hero-mist-2` cua
  // theme (fallback ve `--bg-1` khi chua co theme — giu dung tinh than "trong
  // suot hon" ban dau, chi doi NGUON mau tu mot hang so sang mot bien theme).
  const filterInput = codeOnly(rule(".filter-bar .input"));
  assert.match(filterInput, /color-mix\(in srgb, var\(--hero-mist-2, var\(--bg-1\)\)/, "phải trong suốt hơn để tranh nền tham gia, và tô theo theme khi có");
  assert.ok(!/^background:\s*#0b0d14/m.test(filterInput));
});

/* ==================================== R: Creator closing section full-bleed */

test(".cta-band pha vo gioi han .wrap — full-bleed, khong con la the-kinh cung kich thuoc voi card khac", () => {
  const than = codeOnly(rule(".cta-band"));
  assert.match(than, /width:\s*100vw/);
  assert.match(than, /margin-inline:\s*calc\(50% - 50vw\)/);
  assert.ok(!/border-radius:\s*var\(--r/.test(than), "vẫn còn bo góc kiểu card — phải là 0 (full-bleed)");
});

test(".cta-band KHONG con vien/glow trang tri — kich thuoc va anh nen tao kich tinh", () => {
  const than = codeOnly(rule(".cta-band"));
  assert.ok(!/#8b6cff/.test(than), "vẫn còn màu glow tím cũ");
  assert.ok(!/box-shadow:\s*0 0 \d+px #[0-9a-f]{6,8}(?!0d)/.test(than), "vẫn còn box-shadow phát sáng (không phải --edge trung tính)");
});

/* ============================================= S/U: LOADING vs EMPTY that = */

test("EmptyState nhan duoc hoa tiet SVG rieng (art), tach biet voi Skeleton (loading)", () => {
  const src = codeOnly(read("../src/components/ui.tsx"));
  const atEmpty = src.indexOf("export function EmptyState");
  const than = src.slice(atEmpty, src.indexOf("export function ErrorState"));
  assert.match(than, /art\?:\s*React\.ReactNode/);
  assert.match(than, /empty-art/);
  // Skeleton va EmptyState la HAI ham TACH BIET — khong co logic loading nao
  // lẫn vào EmptyState (đúng yêu cầu "do not confuse loading with empty").
  assert.ok(!/loading/i.test(than));
});

test("3 trang thai rong quan trong (Truyện/Cộng đồng/Animation) dung hoa tiet SVG that, khong con emoji", () => {
  const fanfic = codeOnly(read("../src/app/fanfic/page.tsx"));
  assert.match(fanfic, /art=\{<MotifManuscript \/>\}/);
  const community = codeOnly(read("../src/app/community/page.tsx"));
  assert.match(community, /art=\{<MotifCampfire \/>\}/);
  const animation = codeOnly(read("../src/app/animation/page.tsx"));
  assert.match(animation, /art=\{<MotifFilmFrame \/>\}/);
});

test("MotifCampfire moi la SVG trau tuong, dung currentColor — khong tu dat mau, khong pixel art", () => {
  const src = codeOnly(read("../src/components/Ornaments.tsx"));
  const at = src.indexOf("export function MotifCampfire");
  const than = src.slice(at, src.indexOf("export function MotifWaveform"));
  assert.match(than, /stroke="currentColor"/);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b/.test(than), "họa tiết mới tự đặt mã màu — phải dùng currentColor");
});

/* =================================================== V: chu so ket qua === */

test("khong con '1-1 trong 1 series/truyện' — cau ngan tu nhien khi chi mot ket qua", () => {
  for (const [file, word] of [
    ["../src/app/animation/page.tsx", "series"],
    ["../src/app/fanfic/page.tsx", "truyện"],
  ]) {
    const src = codeOnly(read(file));
    assert.match(src, new RegExp(`total === 1 \\? "1 ${word}"`));
  }
});

/* ============================================ X/Y: audit khong the thieu = */

test("khong co custom cursor toan cuc / pointer trail nao trong CSS", () => {
  const text = codeOnly(css());
  assert.ok(!/cursor:\s*url\(/.test(text), "vẫn còn custom cursor toàn cục");
});

test("khong phu thuoc RPGUI/NES.css trong package.json", () => {
  const pkg = read("../package.json");
  assert.ok(!/rpgui/i.test(pkg));
  assert.ok(!/nes\.css/i.test(pkg));
});

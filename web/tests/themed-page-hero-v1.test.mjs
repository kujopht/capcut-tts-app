/*
 * Themed Page Hero V3 "Copy-Local Art Direction" (2026-08) — moi khu vuc
 * chinh co mot ban sac rieng (mau suong/motif/accent) thay vi dung CHUNG mot
 * lop mau navy-den cho MOI trang. Kien truc: cau truc dung chung
 * (`PageHeader`), mau/hoa tiet den tu bien CSS theo `[data-hero-theme]` —
 * khong hardcode mau rieng cho tung trang o noi khac.
 *
 * V1 -> V2: nguoi dung phan hoi V1 van doc ra nhu "mot tam kinh den mo chu
 * nhat" du DA theo theme (mist gan den + MOT elip DUY NHAT). V2 sang hoa
 * mist va doi elip DUY NHAT thanh BA lop lech tam + mask-image — nhung VAN
 * ve tren pseudo-element cua CA PageHero (`.page-head`/`.hero-v2`/
 * `.auth-head`), nen vung phu ao van bam theo BE RONG CA HERO.
 *
 * V2 -> V3 (hotfix nay): nguoi dung phan hoi LAN NUA — van la "mot vung mau
 * to tu trai qua giua man hinh", chi mem hon. Sua tan goc: `.page-head`/
 * `.hero-v2`/`.auth-head` gio KHONG con `::before` NAO CA (PageHero wrapper
 * phai "gan nhu trong suot"). Khi quyen doc chuyen HOAN TOAN xuong
 * `.hero-copy` — mot the CON MOI, chi rong bang CHINH doan van ban
 * (`--hero-copy-width`), dung CHUNG mot cong thuc (hai lop radial-gradient +
 * mask-image) o ba noi: `.page-head-body` (PageHeader), `.hero-v2 >
 * .hero-copy` (Trang chu), `.auth-head > .hero-copy` (/login).
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

const THEMES = [
  "home", "explore", "animation", "community", "library", "audio",
  "image-studio", "creator", "write", "account", "auth",
];
const REQUIRED_TOKENS = [
  "--hero-accent", "--hero-accent-secondary", "--hero-mist-1", "--hero-mist-2",
  "--hero-highlight", "--hero-motif-color", "--hero-motif-opacity", "--hero-copy-width",
];

/* ========================================== ban do theme day du 11 khu vuc */

test("ca 11 theme deu duoc khai bao voi DU 8 bien bat buoc", () => {
  for (const theme of THEMES) {
    const than = codeOnly(rule(`[data-hero-theme="${theme}"]`));
    for (const tok of REQUIRED_TOKENS) {
      assert.match(than, new RegExp(`${tok.replace(/-/g, "\\-")}:`), `theme "${theme}" thiếu ${tok}`);
    }
  }
});

test("moi trang chinh gan DUNG mot data-hero-theme tren the bao ngoai cung", () => {
  const map = {
    "../src/app/page.tsx": "home",
    "../src/app/fanfic/page.tsx": "explore",
    "../src/app/animation/page.tsx": "animation",
    "../src/app/community/page.tsx": "community",
    "../src/app/library/page.tsx": "library",
    "../src/app/studio/page.tsx": "audio",
    "../src/app/image-studio/page.tsx": "image-studio",
    "../src/app/write/page.tsx": "write",
    "../src/app/account/page.tsx": "account",
    "../src/app/login/page.tsx": "auth",
  };
  for (const [file, theme] of Object.entries(map)) {
    const src = codeOnly(read(file));
    assert.match(src, new RegExp(`data-hero-theme="${theme}"`), `${file} thiếu data-hero-theme="${theme}"`);
  }
});

/* ============================== khong con MOT lop mau navy-den chung cho MOI trang */

test("V3: PageHero wrapper (.page-head/.hero-v2/.auth-head) KHONG con background/::before NAO — phai 'gan nhu trong suot'", () => {
  for (const sel of [".page-head", ".hero-v2", ".auth-head"]) {
    const than = codeOnly(rule(sel));
    assert.ok(!/background:/.test(than), `${sel} không được có background riêng (kiến trúc "generic black slab" cũ)`);
  }
  const css_ = codeOnly(css());
  for (const sel of [".page-head::before", ".hero-v2::before", ".auth-head::before"]) {
    assert.ok(!css_.includes(`${sel} {`), `${sel} vẫn tồn tại — hotfix V3 yêu cầu PageHero wrapper không còn readability backdrop nào, chỉ .hero-copy mới được có`);
  }
});

test("V3: .hero-copy la noi DUY NHAT giu khi quyen doc, doc mau tu theme, tan bien hoan toan", () => {
  const than = codeOnly(rule(".hero-copy::before"));
  assert.match(than, /var\(--hero-mist-1/, ".hero-copy::before phải đọc màu từ --hero-mist-1 theo theme");
  assert.match(than, /var\(--hero-mist-2/, ".hero-copy::before phải đọc màu từ --hero-mist-2 theo theme");
  assert.match(than, /transparent/, ".hero-copy::before phải tan biến hoàn toàn, không phải một khối đặc");
});

test("cac theme KHAC NHAU thi mau THAT SU khac nhau — khong phai bia 11 cai ten cho CUNG mot mau", () => {
  const mists = THEMES.map((t) => {
    const than = codeOnly(rule(`[data-hero-theme="${t}"]`));
    return than.match(/--hero-mist-1:\s*([^;]+);/)?.[1]?.trim();
  });
  const uniq = new Set(mists);
  assert.ok(uniq.size >= 8, `chỉ có ${uniq.size} màu --hero-mist-1 khác nhau trong ${THEMES.length} theme — không đủ đa dạng`);
});

/* ================================== V2: khong con MOT elip den doc duoc */

function hexLightness(hex) {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  return (max + min) / 2;
}

test("V2: --hero-mist-1/2 hardcode (hex) phai SANG hon nguong gan-den cu (khong con doc ra la den)", () => {
  for (const theme of THEMES) {
    const than = codeOnly(rule(`[data-hero-theme="${theme}"]`));
    for (const tok of ["--hero-mist-1", "--hero-mist-2"]) {
      const m = than.match(new RegExp(`${tok}:\\s*(#[0-9a-fA-F]{6});`));
      if (!m) continue; // gia tri qua bien khac (vd var(...)) — bo qua o day
      const l = hexLightness(m[1]);
      assert.ok(l >= 0.14, `${theme} ${tok} = ${m[1]} có lightness ${l.toFixed(2)} — vẫn quá gần đen (< 0.14)`);
    }
  }
});

test("V3: .hero-copy::before KHONG la MOT radial-gradient duy nhat — 1-2 lop lech tam + mask-image feather (dac ta B6)", () => {
  const than = codeOnly(rule(".hero-copy::before"));
  // Chi dem lop trong `background:` — `mask-image`/`-webkit-mask-image` cung
  // dung `radial-gradient(...)` cho rieng no (mot lop feather khac muc dich).
  const nenChinh = than.match(/background:\s*([\s\S]*?);/)?.[1] ?? "";
  const soLopGradient = (nenChinh.match(/radial-gradient\(/g) ?? []).length;
  assert.ok(soLopGradient >= 1 && soLopGradient <= 2,
    `.hero-copy::before có ${soLopGradient} lớp radial-gradient trong background — đặc tả V3 muốn đúng 1-2 lớp nhỏ, không phải 3 lớp lớn như V2`);
  assert.match(than, /mask-image:/, ".hero-copy::before thiếu mask-image feather");
});

test("V3: .hero-copy::before KHONG dung mau den thuan (rgba(0,0,0,...)) lam chat lieu chinh", () => {
  const than = codeOnly(rule(".hero-copy::before"));
  assert.ok(!/rgba\(\s*0\s*,\s*0\s*,\s*0/.test(than), ".hero-copy::before dùng rgba(0,0,0,...) — phải là màu chromatic theo theme, không phải đen thuần");
});

test("V3: .hero-copy chi rong bang doan van ban — inset feather nho (khong con bam theo be rong ca PageHero)", () => {
  const than = codeOnly(rule(".hero-copy::before"));
  const m = than.match(/inset:\s*(-?\d+)px\s+(-?\d+)px\s+(-?\d+)px\s+(-?\d+)px;/);
  assert.notEqual(m, null, ".hero-copy::before thiếu khai báo inset 4 giá trị");
  const [, top, right, bottom, left] = m.map(Number);
  for (const v of [top, right, bottom, left]) {
    assert.ok(Math.abs(v) <= 45, `.hero-copy::before inset ${v}px vượt quá phạm vi "content width + 60-120px feather" cho phép (tối đa ~45px mỗi cạnh, phần còn lại do mask-image lo)`);
  }
});

test("V3: .page-head-actions (nut hanh dong) khong co ::before/::after rieng — khong can khi quyen doc nhu chu", () => {
  const css_ = codeOnly(css());
  assert.ok(!css_.includes(".page-head-actions::before {"));
  assert.ok(!css_.includes(".page-head-actions::after {"));
});

test("V3: ca ba noi (PageHeader/Home/Auth) deu gan class hero-copy dung cho", () => {
  const ui = codeOnly(read("../src/components/ui.tsx"));
  assert.match(ui, /className="stack-2 page-head-body hero-copy"/, "PageHeader thiếu class hero-copy trên .page-head-body");

  const home = codeOnly(read("../src/app/page.tsx"));
  assert.match(home, /<div className="hero-copy">/, "Hero() ở trang chủ thiếu <div className=\"hero-copy\">");
  // pill + tieu de + mo ta nam TRONG hero-copy, CTA/guest-hint nam NGOAI (khong can khi quyen doc).
  const atCopy = home.indexOf('<div className="hero-copy">');
  const atCta = home.indexOf('className="row hero-v2-cta"');
  assert.ok(atCopy < home.indexOf("hero-v2-title") && home.indexOf("hero-v2-title") < atCta,
    "tiêu đề phải nằm trong hero-copy, trước CTA");

  const login = codeOnly(read("../src/app/login/page.tsx"));
  assert.match(login, /<div className="hero-copy">/, "/login thiếu <div className=\"hero-copy\">");
  const atLogoLogin = login.indexOf("<LogoMark");
  const atCopyLogin = login.indexOf('<div className="hero-copy">');
  assert.ok(atLogoLogin < atCopyLogin, "logo phải đứng TRƯỚC hero-copy (không bọc logo trong vùng khí quyển đọc)");
});

test("V3: hero-copy ke thua dung flex/gap cua tung noi chu (khong doi khoang cach thi giac)", () => {
  const heroV2 = codeOnly(rule(".hero-v2 > .hero-copy"));
  assert.match(heroV2, /display:\s*flex/);
  assert.match(heroV2, /gap:\s*var\(--s3\)/);
  const authHead = codeOnly(rule(".auth-head > .hero-copy"));
  assert.match(authHead, /display:\s*flex/);
  assert.match(authHead, /gap:\s*var\(--s2\)/);
});

/* =============================================== hoa tiet SVG rieng tung theme */

test("PageHeader nhan prop motif tuy chon, ve lop rieng .page-head-motif (mo, sau chu)", () => {
  const src = codeOnly(read("../src/components/ui.tsx"));
  const at = src.indexOf("export function PageHeader");
  const than = src.slice(at, src.indexOf("export function Loading"));
  assert.match(than, /motif\?:\s*React\.ReactNode/);
  assert.match(than, /className="page-head-motif"/);
  assert.match(than, /aria-hidden="true"/);
  const motifRule = codeOnly(rule(".page-head-motif"));
  assert.match(motifRule, /color:\s*var\(--hero-motif-color/);
  assert.match(motifRule, /opacity:\s*var\(--hero-motif-opacity/);
  assert.match(motifRule, /pointer-events:\s*none/);
});

test("moi trang truyen mot motif KHAC NHAU cho PageHeader — khong dung chung 1 hinh cho ca 8", () => {
  const map = {
    "../src/app/fanfic/page.tsx": "MotifCompassArc",
    "../src/app/animation/page.tsx": "MotifNebulaOrbit",
    "../src/app/community/page.tsx": "MotifConstellation",
    "../src/app/library/page.tsx": "MotifCelestialDial",
    "../src/app/studio/page.tsx": "MotifResonanceRings",
    "../src/app/image-studio/page.tsx": "MotifInkBloom",
    "../src/app/write/page.tsx": "MotifInkFlourish",
  };
  for (const [file, motif] of Object.entries(map)) {
    const src = codeOnly(read(file));
    assert.match(src, new RegExp(`motif=\\{<${motif} `), `${file} thiếu motif={<${motif} .../>}`);
  }
});

test("V2: Animation/Studio KHONG con dung MotifFilmFrame/MotifWaveform lam motif CUA PageHero (co the van dung MotifFilmFrame cho art= cua EmptyState — usage khac, khong phai hero)", () => {
  const animation = codeOnly(read("../src/app/animation/page.tsx"));
  assert.ok(!/motif=\{<MotifFilmFrame/.test(animation), "animation/page.tsx vẫn dùng MotifFilmFrame (khung hình điện ảnh) làm motif của PageHero — spec cấm literal film equipment ở đây");
  const studio = codeOnly(read("../src/app/studio/page.tsx"));
  assert.ok(!/motif=\{<MotifWaveform/.test(studio), "studio/page.tsx vẫn dùng MotifWaveform (cột EQ) làm motif của PageHero — spec cấm literal EQ bars ở đây");
});

test("V2: /login va /account co hoa tiet rieng (khong qua prop motif cua PageHeader — hai trang nay khong dung PageHeader)", () => {
  const login = codeOnly(read("../src/app/login/page.tsx"));
  assert.match(login, /<MotifPortalHalo\s*\/>/, "login/page.tsx thiếu <MotifPortalHalo />");
  assert.match(login, /className="auth-portal-halo"/, "login/page.tsx thiếu lớp .auth-portal-halo bọc quanh hoạ tiết");
  const account = codeOnly(read("../src/app/account/page.tsx"));
  assert.match(account, /<MotifSigil\s*\/>/, "account/page.tsx thiếu <MotifSigil />");
  assert.match(account, /className="account-hero-motif"/, "account/page.tsx thiếu lớp .account-hero-motif bọc quanh hoạ tiết");
});

test("Home (hero-v2) co hoa tiet rieng MotifWaveArcs qua lop .hero-v2-motif", () => {
  const src = codeOnly(read("../src/app/page.tsx"));
  assert.match(src, /<MotifWaveArcs className="hero-v2-motif"/, "Hero() thiếu <MotifWaveArcs className=\"hero-v2-motif\" />");
});

test("cac hoa tiet la SVG trau tuong, dung currentColor, khong tu dat ma mau", () => {
  const src = codeOnly(read("../src/components/Ornaments.tsx"));
  const fns = [
    "MotifCompassArc", "MotifConstellation", "MotifCelestialDial", "MotifInkBloom",
    "MotifWaveArcs", "MotifNebulaOrbit", "MotifResonanceRings", "MotifInkFlourish",
    "MotifSigil", "MotifPortalHalo",
  ];
  for (const fn of fns) {
    const at = src.indexOf(`export function ${fn}`);
    assert.notEqual(at, -1, `không tìm thấy ${fn}`);
    const than = src.slice(at, src.indexOf("\n}", at) + 2);
    assert.ok(/stroke="currentColor"|fill="currentColor"/.test(than), `${fn} phải dùng currentColor`);
    assert.ok(!/#[0-9a-fA-F]{3,8}\b/.test(than), `${fn} tự đặt mã màu — phải để component cha quyết định qua CSS color`);
  }
});

/* ===================================================== CTA + eyebrow theo theme */

test("eyebrow CUA DAU TRANG (khong phai toan cuc) nhan mau accent theo theme", () => {
  const than = codeOnly(rule(".page-head .eyebrow"));
  assert.match(than, /var\(--hero-accent, var\(--brand\)\)/);
  // `.eyebrow` toan cuc (dung o nhieu noi khac ngoai PageHero) KHONG duoc doi.
  const global_ = codeOnly(rule(".eyebrow"));
  assert.match(global_, /color:\s*var\(--brand\);/);
});

test("nut chinh trong dau trang ke thua mau theme — KHONG doi .btn-primary toan cuc", () => {
  const than = codeOnly(rule(".page-head-actions .btn-primary"));
  assert.match(than, /var\(--hero-accent, var\(--brand\)\)/);
  assert.match(than, /var\(--hero-accent-secondary, var\(--brand-deep\)\)/);
  const globalBtn = codeOnly(rule(".btn-primary"));
  assert.match(globalBtn, /var\(--lift-brand\)/, ".btn-primary gốc (dùng ở Khám phá, Bắt đầu viết...) không được đổi");
});

/* =============================================== khong dam vao he thong khac */

test("Nav-login/nav-right KHONG doi mau theo route — dieu huong van dung chung toan site", () => {
  const navLogin = codeOnly(rule(".nav-login"));
  assert.ok(!/var\(--hero-accent/.test(navLogin), "nav-login không được đổi màu theo PageHero — phải nhất quán toàn site");
});

test("Player V2 (YouTubePlayerControls/YouTubeFacadePlayer) van con nguyen, khong bi PageHero cham vao", () => {
  for (const f of [
    "../src/components/YouTubePlayerControls.tsx",
    "../src/components/YouTubeFacadePlayer.tsx",
    "../src/lib/youtubeIframeApi.ts",
  ]) {
    const src = read(f);
    assert.ok(src.length > 100, `${f} phải tồn tại và có nội dung thật`);
    assert.ok(!/data-hero-theme/.test(src), `${f} không nên biết gì về PageHero`);
  }
});

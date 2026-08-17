/*
 * Themed Page Hero V1 (2026-08) — moi khu vuc chinh co mot ban sac rieng
 * (mau suong/motif/accent) thay vi dung CHUNG mot lop mau navy-den cho MOI
 * trang. Kien truc: cau truc dung chung (`PageHeader`), mau/hoa tiet den tu
 * bien CSS theo `[data-hero-theme]` — khong hardcode mau rieng cho tung
 * trang o noi khac.
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
  "image-studio", "creator",
];
const REQUIRED_TOKENS = [
  "--hero-accent", "--hero-accent-secondary", "--hero-mist-1", "--hero-mist-2",
  "--hero-highlight", "--hero-motif-color", "--hero-motif-opacity", "--hero-copy-width",
];

/* =========================================== ban do theme day du 8 khu vuc */

test("ca 8 theme deu duoc khai bao voi DU 8 bien bat buoc", () => {
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
  };
  for (const [file, theme] of Object.entries(map)) {
    const src = codeOnly(read(file));
    assert.match(src, new RegExp(`data-hero-theme="${theme}"`), `${file} thiếu data-hero-theme="${theme}"`);
  }
});

/* ============================== khong con MOT lop mau navy-den chung cho MOI trang */

test(".page-head/.hero-v2 KHONG co background rieng — CHI ::before lo mau, va no doc mau tu theme", () => {
  for (const sel of [".page-head", ".hero-v2"]) {
    const than = codeOnly(rule(sel));
    assert.ok(!/background:/.test(than), `${sel} không được có background riêng (kiến trúc "generic black slab" cũ)`);
  }
  for (const sel of [".page-head::before", ".hero-v2::before"]) {
    const than = codeOnly(rule(sel));
    assert.match(than, /var\(--hero-mist-1/, `${sel} phải đọc màu từ --hero-mist-1 theo theme`);
    assert.match(than, /var\(--hero-mist-2/, `${sel} phải đọc màu từ --hero-mist-2 theo theme`);
    assert.match(than, /transparent/, `${sel} phải tan biến hoàn toàn, không phải một khối đặc`);
  }
});

test("cac theme KHAC NHAU thi mau THAT SU khac nhau — khong phai bia 8 cai ten cho CUNG mot mau", () => {
  const mists = THEMES.map((t) => {
    const than = codeOnly(rule(`[data-hero-theme="${t}"]`));
    return than.match(/--hero-mist-1:\s*([^;]+);/)?.[1]?.trim();
  });
  const uniq = new Set(mists);
  assert.ok(uniq.size >= 6, `chỉ có ${uniq.size} màu --hero-mist-1 khác nhau trong ${THEMES.length} theme — không đủ đa dạng`);
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
    "../src/app/animation/page.tsx": "MotifFilmFrame",
    "../src/app/community/page.tsx": "MotifConstellation",
    "../src/app/library/page.tsx": "MotifCelestialDial",
    "../src/app/studio/page.tsx": "MotifWaveform",
    "../src/app/image-studio/page.tsx": "MotifInkBloom",
  };
  for (const [file, motif] of Object.entries(map)) {
    const src = codeOnly(read(file));
    assert.match(src, new RegExp(`motif=\\{<${motif} `), `${file} thiếu motif={<${motif} .../>}`);
  }
});

test("cac hoa tiet moi (Compass/Constellation/CelestialDial/InkBloom) la SVG trau tuong, dung currentColor", () => {
  const src = codeOnly(read("../src/components/Ornaments.tsx"));
  for (const fn of ["MotifCompassArc", "MotifConstellation", "MotifCelestialDial", "MotifInkBloom"]) {
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

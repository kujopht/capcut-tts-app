/*
 * Fanfic World Visual Renaissance — Phase 3.5 "Cinematic Homepage Polish"
 * (2026-08).
 *
 * BOI CANH: Hero doc kho tren nen artwork sang (khong co lop nao giua chu va
 * tranh), va cong Truyen/Animation/CTA sang tac phu thuoc qua nhieu vao mot
 * chu nhat den phang (`linear-gradient` dac + hoa tiet SVG mo 12-16%). SUA:
 * (1) mot quang mo/suong xanh-navy feathered sau khoi chu Hero (KHONG dung
 * text-shadow nang); (2) anh minh hoa that (sinh qua Pollinations, khoa theo
 * `docs/design/fanfic-world-modern-anime-fantasy-aesthetic.md`) cho cong
 * Truyen/Animation va dai CTA sang tac cuoi trang, voi lop phu (`overlay`)
 * rieng de chu van doc duoc; (3) bo glow tim toa tron cu tren CTA sang tac.
 *
 * Chuan hoa CRLF -> LF (xem bai hoc o `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const home = () => read("../src/app/page.tsx");
const path = (p) => fileURLToPath(new URL(p, import.meta.url));

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

/* ============================================== Hero: quang mo, khong shadow nang */

test("Hero co lop quang mo (::before, radial-gradient) sau khoi chu, KHONG bia text-shadow nang", () => {
  const than = rule(".hero-v2::before");
  assert.match(than, /radial-gradient\(/);
  assert.match(than, /position:\s*absolute/);
  assert.match(than, /z-index:\s*-1/, "phải nằm SAU chữ (z-index âm), không đè lên");

  const titleSrc = codeOnly(css()).slice(
    css().indexOf(".hero-v2-title {"),
    css().indexOf(".hero-v2-title {") + 400,
  );
  assert.ok(!/text-shadow/.test(titleSrc),
    "không được thêm text-shadow nặng cho .hero-v2-title — spec cấm rõ");
});

test("Hero .hero-v2 la position:relative de quang mo (::before) neo dung vi tri", () => {
  const than = rule(".hero-v2");
  assert.match(than, /position:\s*relative/);
});

/* ==================================== Portal Truyen/Animation: anh that ==== */

test("Portal Truyện và Animation render next/image voi anh minh hoa that, alt rong (trang tri)", () => {
  const src = codeOnly(home());
  assert.match(src, /src="\/images\/portals\/truyen-manuscript\.webp"/);
  assert.match(src, /src="\/images\/portals\/animation-projector\.webp"/);
  // Ca hai deu la anh trang tri (chu that da co trong .portal-body kem no) —
  // alt phai rong, khong doc lap lai ten cong cho trinh doc man hinh.
  const truyenBlock = src.slice(
    src.indexOf('href={DIEM_DEN_CHINH[0].href}'),
    src.indexOf('href={DIEM_DEN_CHINH[0].href}') + 400,
  );
  assert.match(truyenBlock, /alt=""/);
});

test("anh Truyen/Animation KHONG lazy-load (o gan dau trang, tranh nhap nhay 'hop den' luc tai lan dau)", () => {
  // Bug that da gap tren staging: next/image mac dinh loading="lazy" khi
  // khong khai bao — voi anh GAN DAU TRANG dieu do gay mot khoanh khac
  // "hop den" truoc khi anh vao vung tai. `priority`/`loading="eager"` sua
  // dung tai goc, khong phai vi lam dep code.
  const src = codeOnly(home());
  const truyenBlock = src.slice(
    src.indexOf('src="/images/portals/truyen-manuscript.webp"') - 200,
    src.indexOf('src="/images/portals/truyen-manuscript.webp"') + 300,
  );
  assert.match(truyenBlock, /priority/, "ảnh Truyện (cổng lớn nhất) phải có priority");
  const animBlock = src.slice(
    src.indexOf('src="/images/portals/animation-projector.webp"') - 200,
    src.indexOf('src="/images/portals/animation-projector.webp"') + 300,
  );
  assert.match(animBlock, /loading="eager"/, "ảnh Animation phải tải eager, không lazy");
});

test("CA HAI anh Truyện/Animation deu co file that tren dia, dung .webp (khong PNG nang)", () => {
  for (const f of ["truyen-manuscript.webp", "animation-projector.webp", "creator-worldbuilding.webp"]) {
    const p = path(`../public/images/portals/${f}`);
    assert.ok(existsSync(p), `thiếu file ${f}`);
    const kb = statSync(p).size / 1024;
    assert.ok(kb < 300, `${f} nặng ${kb.toFixed(0)}KB — vượt ngân sách ảnh cho một portal (300KB)`);
  }
});

test("`.portal-art` la LOP DUOI CUNG (z-index 0), `.portal-overlay` phu TOI o TREN no (z-index 1)", () => {
  const art = rule(".portal-art");
  assert.match(art, /z-index:\s*0/);
  const overlay = rule(".portal-overlay");
  assert.match(overlay, /position:\s*absolute/);
  assert.match(overlay, /z-index:\s*1/);
});

test("hoa tiet SVG cu (.portal-motif) bi AN cho Truyện/Animation — tranh chong hai lop chat lieu", () => {
  const than = codeOnly(css());
  assert.match(than, /\.portal-truyen \.portal-motif,\s*\n\.portal-animation \.portal-motif \{\s*\n\s*display: none;/);
});

test("portal-rune va portal-body nam TREN lop overlay (z-index 2 > 1)", () => {
  assert.match(rule(".portal-rune"), /z-index:\s*2/);
  assert.match(rule(".portal-body"), /z-index:\s*2/);
});

/* ============================================ CTA sang tac: bo glow, them anh */

test("CTA sang tac (.cta-band) KHONG con glow tim toa tron cu (radial-gradient #8b6cff29)", () => {
  const than = rule(".cta-band");
  assert.ok(!/#8b6cff29/.test(than), "vẫn còn glow tím tỏa tròn cũ trên .cta-band");
  assert.match(than, /position:\s*relative/);
  assert.match(than, /overflow:\s*hidden/);
});

test("CTA sang tac co anh minh hoa that, lazy-load (duoi fold)", () => {
  const src = codeOnly(home());
  const block = src.slice(src.indexOf('<section className="cta-band"'), src.indexOf('<section className="cta-band"') + 500);
  assert.match(block, /src="\/images\/portals\/creator-worldbuilding\.webp"/);
  assert.match(block, /loading="lazy"/);
  assert.match(block, /alt=""/);
});

test("CTA sang tac dung cau chu tu nhien 'dung nen the gioi', khong con cau hoi cu", () => {
  const src = home();
  assert.match(src, /Dựng nên thế giới của riêng bạn/);
});

/* ============================================== aesthetic doc (art direction) */

test("Tai lieu aesthetic fanfic-world-modern-anime-fantasy ton tai, co Base Prompt Prefix khoa", () => {
  const p = path("../../docs/design/fanfic-world-modern-anime-fantasy-aesthetic.md");
  assert.ok(existsSync(p), "thiếu tài liệu aesthetic");
  const doc = readFileSync(p, "utf8").replace(/\r\n/g, "\n");
  assert.match(doc, /## Base Prompt Prefix/);
  for (const cum of [
    "modern anime fantasy",
    "cinematic environmental",
    "midnight",
    "arcane violet",
    "sakura",
    "lantern",
    "No text",
    "No.*franchise",
    "No.*copyrighted characters",
  ]) {
    assert.match(doc, new RegExp(cum, "i"), `Base Prompt Prefix thiếu cụm bắt buộc: ${cum}`);
  }
});

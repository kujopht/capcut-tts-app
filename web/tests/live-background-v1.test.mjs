/*
 * Live Wallpaper V1 — kien truc `LiveBackground` (2026-08).
 *
 * Component nay CHUA duoc gan vao trang nao dem nay (khong co tai san video
 * — xem bao cao overnight). Bo test o day xac nhan KIEN TRUC dung nhu dac
 * ta, theo dung quy uoc cua repo: quet MA NGUON (khong dung jsdom/render
 * component that — repo nay khong thiet lap React Testing Library o bat ky
 * dau, moi test hien co deu la phan tich tinh).
 *
 * Chuan hoa CRLF -> LF (xem bai hoc o `admin-trusted-sources.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const src = () => read("../src/components/LiveBackground.tsx");
const codeOnly = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================== poster la lop DAU TIEN ==== */

test("poster (<img>) LUON render, khong dieu kien nao bao quanh no", () => {
  const s = codeOnly(src());
  const at = s.indexOf("<img");
  assert.notEqual(at, -1, "thiếu <img> poster");
  const truoc200 = s.slice(Math.max(0, at - 200), at);
  assert.ok(!/hienVideo \?/.test(truoc200), "poster không được nằm trong nhánh điều kiện của video");
});

test("video CHI render khi hienVideo true — khong bao gio render truoc khi kiem tra dieu kien", () => {
  const s = codeOnly(src());
  assert.match(s, /const hienVideo = choPhep && coNguon && !loi;/);
  assert.match(s, /\{hienVideo \? \(\s*<video/);
});

/* ==================================== fallback khi loi / khong co nguon === */

test("loi tai video (onError) -> thu tai lai DUNG MOT LAN truoc khi loi=true vinh vien", () => {
  /*
   * V3: khong con coi MOI loi la vinh vien ngay lap tuc — mot loi GPU context
   * loss thoang qua (keo cua so qua man hinh khac) se duoc thu lai mot lan
   * (`el.load()` + `el.play()`) truoc khi ket luan hong that su. Xem chu
   * thich V3 o dau `LiveBackground.tsx`.
   */
  const s = codeOnly(src());
  assert.match(s, /onError=\{xuLyLoiVideo\}/);
  assert.match(s, /const xuLyLoiVideo = \(\) => \{/);
  assert.match(s, /daThuLaiRef\.current = true;/);
  assert.match(s, /el\.load\(\);/);
  assert.match(s, /setLoi\(true\);/, "vẫn phải có một lối ra vĩnh viễn cho lỗi thật");
  // `hienVideo` phu thuoc `!loi` — da xac nhan o test tren.
});

test("khong truyen `video` (chua co tai san) -> coNguon=false -> khong bao gio thu render video", () => {
  const s = codeOnly(src());
  assert.match(s, /const coNguon = Boolean\(video && \(video\.webm \|\| video\.mp4\)\);/);
});

/* ===================================== khong tu phat am thanh, dung <video> chuan */

test("the <video> muted+loop+playsInline+autoPlay, KHONG co <audio>, KHONG co controls", () => {
  const s = codeOnly(src());
  const at = s.indexOf("<video");
  const than = s.slice(at, s.indexOf("</video>"));
  assert.match(than, /\bmuted\b/, "phải muted — không tự phát âm thanh");
  assert.match(than, /\bloop\b/);
  assert.match(than, /\bplaysInline\b/);
  assert.match(than, /\bautoPlay\b/);
  assert.ok(!/\bcontrols\b/.test(than), "không được có controls — đây là trang trí nền");
  assert.ok(!/<audio/.test(s), "không được có thẻ <audio> nào");
});

test("ca hai dinh dang webm/mp4 deu duoc khai bao qua <source>, khong hardcode mot dinh dang", () => {
  const s = codeOnly(src());
  assert.match(s, /video\?\.webm.*<source src=\{video\.webm\} type="video\/webm"/);
  assert.match(s, /video\?\.mp4.*<source src=\{video\.mp4\} type="video\/mp4"/);
});

/* ================================ prefers-reduced-motion + Save-Data + tab an */

test("prefers-reduced-motion: reduce -> choPhep=false -> video khong bao gio phat", () => {
  const s = codeOnly(src());
  assert.match(s, /prefers-reduced-motion: reduce/);
  assert.match(s, /!qGiamChuyenDong\.matches && !tietKiemDuLieu/);
});

test("navigator.connection.saveData -> uu tien nen tinh, doc AN TOAN (Safari khong co API nay)", () => {
  const s = codeOnly(src());
  assert.match(s, /conn\?\.saveData === true/);
});

test("man hinh <=640px mac dinh KHONG phat video tru khi mobileVideo=true (Phan 20 dac ta)", () => {
  const s = codeOnly(src());
  assert.match(s, /mobileVideo = false/);
  assert.match(s, /\(!qManHinhNho\.matches \|\| mobileVideo\)/);
});

test("tab an (document.hidden) -> pause(); tab hien lai -> play() lai NEU da san sang va khong loi", () => {
  const s = codeOnly(src());
  assert.match(s, /visibilitychange/);
  assert.match(s, /if \(document\.hidden\) el\.pause\(\);/);
  assert.match(s, /else if \(sanSang && !loi\) el\.play\(\)/);
});

/* ========================================== khong Canvas/WebGL/rAF trang tri */

test("khong dung Canvas, WebGL, hay requestAnimationFrame trang tri", () => {
  const s = codeOnly(src());
  assert.ok(!/canvas|WebGL|getContext/i.test(s));
  assert.ok(!/requestAnimationFrame/.test(s));
});

/* ======================================= khong chan LCP, khong nhay hinh === */

test("video preload='none' — khong tai video truoc khi can, khong canh tranh bang thong voi poster", () => {
  const s = codeOnly(src());
  assert.match(s, /preload="none"/);
});

test("video crossfade bang opacity CSS (transition), khong bang JS animation loop", () => {
  const s = codeOnly(src());
  assert.match(s, /opacity: sanSang \? 1 : 0/);
  assert.match(s, /transition: "opacity 600ms ease"/);
});

/* ============================================ V2: videoMask (hybrid cinemagraph) */

test("videoMask la TUY CHON — bo trong thi video van phu toan khung nhu V1", () => {
  const s = codeOnly(src());
  assert.match(s, /videoMask\?: string/);
});

test("videoMask ap dung qua CSS mask-image, khong phai Canvas/clip-path JS", () => {
  const s = codeOnly(src());
  assert.match(s, /WebkitMaskImage: `url\(\$\{videoMask\}\)`/);
  assert.match(s, /maskImage: `url\(\$\{videoMask\}\)`/);
  assert.match(s, /maskSize: "cover"/);
});

test("videoMask KHONG tu dat mask-position — de tung trang tu dong bo qua CSS class rieng", () => {
  const s = codeOnly(src());
  assert.ok(!/maskPosition:/.test(s),
    "đặt sẵn mask-position trong component sẽ không thể bị CSS ngoài ghi đè (inline style luôn thắng)");
});

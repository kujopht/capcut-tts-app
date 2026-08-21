/*
 * LiveBackground V3 — sua loi "keo cua so qua man hinh khac lam mat video
 * vinh vien" (bao cao thu cong: doi man hinh vat ly -> live wallpaper roi
 * ve poster tinh mai mai).
 *
 * Goc loi: `onError` coi MOI loi la vinh vien, va hai truy van `matchMedia`
 * (`prefers-reduced-motion`, `max-width: 640px`) chi doc MOT LAN luc mount.
 * Keo cua so giua hai man hinh khac GPU/ty le DPI co the khien Chromium
 * reset ngu canh giai ma cung va phat mot `error` THOANG QUA — hoan toan
 * khong lien quan video/URL that su hong.
 *
 * Bo test o day quet MA NGUON (quy uoc cua repo — khong co jsdom) cho tung
 * kich ban trong bao cao loi (A-I), dam bao cau truc code THAT SU tach bach
 * "du dieu kien" (choPhep) khoi "trang thai phat" (sanSang/loi), va khong
 * bao gio dung `blur`/`focus`/`devicePixelRatio`/`screen.*` lam dieu kien.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const src = () => read("../src/components/LiveBackground.tsx");
const pageBg = () => read("../src/components/PageBackground.tsx");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ===== A: desktop eligible -> blur -> focus => van du dieu kien ===== */

test("A: KHONG BAO GIO dung window.blur/focus lam dieu kien du dieu kien hay phat", () => {
  const s = codeOnly(src());
  assert.ok(!/addEventListener\(\s*"blur"/.test(s), "vẫn còn lắng nghe window blur");
  assert.ok(!/addEventListener\(\s*"focus"/.test(s), "vẫn còn lắng nghe window focus");
  assert.ok(!/onblur|onfocus/i.test(s), "vẫn còn dùng blur/focus dưới dạng khác");
});

/* ===== B: playing -> visibility hidden => tam dung, VAN du dieu kien/con mount ===== */

test("B: tab an CHI goi pause() — khong dung toi choPhep/loi (khong tat du dieu kien)", () => {
  const s = codeOnly(src());
  const at = s.indexOf("const onDoiHien = () => {");
  assert.notEqual(at, -1, "thiếu handler visibilitychange");
  const than = s.slice(at, s.indexOf("};", at));
  assert.match(than, /if \(document\.hidden\) el\.pause\(\);/);
  assert.ok(!/setChoPhep/.test(than), "handler ẩn/hiện tab không được đổi eligibility");
  assert.ok(!/setLoi/.test(than), "handler ẩn/hiện tab không được đổi trạng thái lỗi");
});

/* ===== C: hidden -> visible => phat tiep ===== */

test("C: tab hien lai -> play() tiep NEU da san sang va khong loi", () => {
  const s = codeOnly(src());
  assert.match(s, /else if \(sanSang && !loi\) el\.play\(\)\.catch/);
});

test("bfcache: co lang nghe pageshow phong hờ ben canh visibilitychange", () => {
  const s = codeOnly(src());
  assert.match(s, /addEventListener\("pageshow", onDoiHien\)/,
    "thiếu lắng nghe pageshow — trang phục hồi từ bfcache có thể không phát lại visibilitychange");
});

/* ===== D/E: resize/DPR/screen KHONG duoc la dieu kien ===== */

test("D+E: KHONG dung devicePixelRatio/screen.width/screen.height lam dieu kien du/khong du", () => {
  const s = codeOnly(src());
  assert.ok(!/devicePixelRatio/.test(s), "dùng devicePixelRatio — đổi màn hình vật lý sẽ đổi giá trị này dù không phải điều đáng quan tâm");
  assert.ok(!/screen\.(width|height|availWidth|availHeight)/.test(s), "dùng screen.width/height — sai khái niệm 'màn hình bé', đây là màn hình vật lý");
});

test("D: KHONG co listener \"resize\" tho tinh lai du dieu kien lien tuc", () => {
  const s = codeOnly(src());
  assert.ok(!/addEventListener\(\s*"resize"/.test(s),
    "nghe resize thô — nên dùng matchMedia breakpoint, không phải đo lại mỗi khung hình resize");
});

/* ===== F/G: matchMedia(max-width) phai REACTIVE ca hai chieu ===== */

test("F+G: ca hai truy van matchMedia deu co addEventListener(\"change\") — khong chi doc mot lan", () => {
  const s = codeOnly(src());
  assert.match(s, /const qGiamChuyenDong = window\.matchMedia\("\(prefers-reduced-motion: reduce\)"\);/);
  assert.match(s, /const qManHinhNho = window\.matchMedia\("\(max-width: 640px\)"\);/);
  assert.match(s, /qGiamChuyenDong\.addEventListener\("change", tinhLai\)/,
    "prefers-reduced-motion không lắng nghe change — đổi lúc runtime sẽ không cập nhật");
  assert.match(s, /qManHinhNho\.addEventListener\("change", tinhLai\)/,
    "max-width không lắng nghe change — thu nhỏ/phóng to qua ngưỡng 640px sẽ không cập nhật");
  // Va don dep dung cach khi unmount/deps doi.
  assert.match(s, /qGiamChuyenDong\.removeEventListener\("change", tinhLai\)/);
  assert.match(s, /qManHinhNho\.removeEventListener\("change", tinhLai\)/);
});

test("chuyen tu DU sang KHONG DU dieu kien: don sach sanSang/loi/daThuLaiRef cho lan mount sau", () => {
  const s = codeOnly(src());
  const at = s.indexOf("if (truoc && !moi) {");
  assert.notEqual(at, -1, "thiếu nhánh dọn sạch khi mất điều kiện đủ");
  const than = s.slice(at, s.indexOf("}", at) + 1);
  assert.match(than, /setSanSang\(false\)/);
  assert.match(than, /setLoi\(false\)/);
  assert.match(than, /daThuLaiRef\.current = false/);
});

/* ===== I: loi video thuc su => van co loi thoat vinh vien ===== */

test("I: loi that (lan hai sau khi da thu lai) van dan toi poster vinh vien", () => {
  const s = codeOnly(src());
  const at = s.indexOf("const xuLyLoiVideo = () => {");
  assert.notEqual(at, -1);
  const than = s.slice(at, s.indexOf("};", at) + 2);
  assert.match(than, /if \(el && !daThuLaiRef\.current\) \{/);
  assert.match(than, /daThuLaiRef\.current = true;/);
  assert.match(than, /el\.load\(\);/);
  assert.match(than, /return;/);
  assert.match(than, /setLoi\(true\);/);
});

/* ===== H: roi Home -> quay lai Home => hoat dong lai binh thuong ===== */

test("H: khong co key nao dua tren width/DPR co the lam <video>/lop nen remount sai luc", () => {
  const s1 = codeOnly(src());
  const s2 = codeOnly(pageBg());
  for (const s of [s1, s2]) {
    assert.ok(!/key=\{[^}]*(width|innerWidth|devicePixelRatio|dpr)[^}]*\}/i.test(s),
      "key phụ thuộc kích thước/DPR — sẽ remount video một cách không cần thiết");
  }
  // V4: khoa la the-he `the` cua kho chuyen canh (routeTransitionStore),
  // tang moi khi MOT LAN REVEAL MOI that su bat dau (khong phai width/DPR)
  // — xem `route-transition-veil.test.mjs`. Van on dinh qua resize/doi man
  // hinh: chi tang khi dieu huong that su bat dau mot chu ky moi.
  assert.match(s2, /key=\{the\}/);
});

test("V3 khong dua vao focus/blur: khong them prop/co moi lien quan window focus vao LiveBackground", () => {
  const s = codeOnly(src());
  assert.ok(!/tamNgungPhat|windowFocused|isWindowFocused/.test(s),
    "đã thêm một khái niệm 'tạm ngưng theo focus cửa sổ' — đúng điều đặc tả cấm");
});

/*
 * Live Wallpaper V2 — hybrid cinemagraph tich hop vao trang chu (2026-08).
 *
 * V1 (video toan khung) bi tu choi o QA thu cong — xem lich su git cho
 * `HOME_LIVE_BAT = false` tam thoi truoc khi on dinh camera + mask duoc xay.
 * V2: video DA ON DINH CAMERA chi hien qua mot mask (may/nuoc/la), anh tinh
 * goc luon la lop duoi cung. Bo test o day xac nhan RIENG phan NOI DAY:
 * PageBackground.tsx goi dung LiveBackground CHI cho "home", dung nguon
 * video + mask that, va khong lam vo cac bat bien da co cua PageBackground
 * (xem `page-background.test.mjs`).
 *
 * Quet MA NGUON, khong render — dung quy uoc cua repo (khong co jsdom).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const comp = () => read("../src/components/PageBackground.tsx");
const css = () => read("../src/app/globals.css");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const THU_MUC = new URL("../public/artwork/fantasy-backgrounds/", import.meta.url);

test("PageBackground import LiveBackground", () => {
  assert.match(comp(), /import \{ LiveBackground \} from "@\/components\/LiveBackground";/);
});

test("LiveBackground CHI duoc goi cho \"home\", khong cho trang nao khac", () => {
  const s = codeOnly(comp());
  assert.match(s, /ten === "home" \? \(\s*<LiveBackground/);
});

test("nguon video Home tro dung hai tep that tren dia", () => {
  const s = comp();
  const webm = s.match(/webm: "(\/artwork\/fantasy-backgrounds\/[^"]+\.webm)"/)?.[1];
  const mp4 = s.match(/mp4: "(\/artwork\/fantasy-backgrounds\/[^"]+\.mp4)"/)?.[1];
  assert.ok(webm, "thiếu nguồn webm");
  assert.ok(mp4, "thiếu nguồn mp4");
  assert.ok(existsSync(new URL(webm.split("/").pop(), THU_MUC)), `không tồn tại: ${webm}`);
  assert.ok(existsSync(new URL(mp4.split("/").pop(), THU_MUC)), `không tồn tại: ${mp4}`);
});

test("LiveBackground dung poster tu chinh anhNen(ten), khong hardcode duong dan khac", () => {
  const s = codeOnly(comp());
  assert.match(s, /poster=\{anhNen\(ten\)\}/);
});

test("video Home la ban DA ON DINH CAMERA (\"-motion\"), khong phai ban V1 bi tu choi (\"-live\")", () => {
  const s = comp();
  assert.match(s, /01-home-sunny-harbor-motion\.webm/, "chưa chuyển sang video đã ổn định camera");
  assert.match(s, /01-home-sunny-harbor-motion\.mp4/);
});

test("HOME_LIVE_BAT dang BAT (V2 hybrid da qua QA, khong con la V1 bi tu choi)", () => {
  const s = codeOnly(comp());
  assert.match(s, /const HOME_LIVE_BAT = true;/);
});

test("co videoMask tro dung mot tep that — video KHONG con phu toan khung", () => {
  const s = comp();
  const mask = s.match(/const HOME_VIDEO_MASK = "(\/artwork\/fantasy-backgrounds\/[^"]+\.webp)";/)?.[1];
  assert.ok(mask, "thiếu HOME_VIDEO_MASK");
  assert.ok(existsSync(new URL(mask.split("/").pop(), THU_MUC)), `không tồn tại: ${mask}`);

  const codeS = codeOnly(s);
  assert.match(codeS, /videoMask=\{HOME_LIVE_BAT \? HOME_VIDEO_MASK : undefined\}/,
    "videoMask không được truyền cho LiveBackground — video sẽ phủ toàn khung như V1 đã bị từ chối");
});

test("mask-position dong bo voi object-position (center 42%) — vung chuyen dong khong troi khoi cho", () => {
  const cssText = css();
  const lopVideo = cssText.slice(cssText.indexOf(".home-live-lop"));
  assert.match(lopVideo, /mask-position: center 42%/);
});

test("lop video Home dung CUNG object-position voi --diem cua CSS (center 42%)", () => {
  const cssText = css();
  const dongDiem = cssText.match(/\.page-bg-lop\[data-bg="home"\]\s*\{[^}]*--diem: ([^;]+);/);
  assert.ok(dongDiem, "không tìm thấy --diem của home");
  assert.equal(dongDiem[1].trim(), "center 42%", "CSS home đổi --diem mà chưa đồng bộ");

  const lopVideo = cssText.slice(cssText.indexOf(".home-live-lop"));
  assert.match(lopVideo, /object-position: center 42%/,
    "lớp video Home lệch object-position với --diem — sẽ nhảy hình khi crossfade");
});

test("khong dua video vao lop tam CU (data-ra) dang mo di", () => {
  const s = codeOnly(comp());
  // Lop `data-ra` la mot the TU DONG (khong con), ket thuc bang `/>` truoc
  // `) : null}` — neu no tung co con thi day khong con la mot the tu dong.
  const m = s.match(/\{tenCu \? \(\s*<div className="page-bg-lop" data-bg=\{tenCu\}[^]*?\) : null\}/);
  assert.ok(m, "không tìm thấy khối lớp CŨ (data-ra)");
  assert.match(m[0], /\/>\s*\) : null\}/, "lớp CŨ không còn là thẻ tự đóng — có thể đã thêm con");
  assert.ok(!m[0].includes("LiveBackground"), "video không được render ở lớp đang mờ đi");
});

test("bat bien cu cua PageBackground van dung: khong <img>/style inline TRUC TIEP trong tep nay", () => {
  // LiveBackground.tsx (tep khac) duoc phep co <img>/style rieng cua no —
  // bai test nay chi bao ve PageBackground.tsx, giong het ky vong cua
  // `page-background.test.mjs`.
  const s = codeOnly(comp());
  assert.ok(!/<img/.test(s));
  assert.ok(!/style=\{\{/.test(s));
});

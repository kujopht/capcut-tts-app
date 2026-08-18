/*
 * Live Wallpaper V1 — tich hop LiveBackground vao trang chu (2026-08).
 *
 * Component kien truc da co tu truoc (`live-background-v1.test.mjs`,
 * `live-background-preference-stub.test.mjs`) — bo test o day xac nhan RIENG
 * phan NOI DAY: PageBackground.tsx goi dung LiveBackground CHI cho "home",
 * dung nguon video that, va khong lam vo cac bat bien da co cua PageBackground
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

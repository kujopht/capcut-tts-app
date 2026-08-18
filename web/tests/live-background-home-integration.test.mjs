/*
 * Live Wallpaper — Gemini V2 tich hop vao trang chu (2026-08).
 *
 * Lich su: Nova Reel V1 (video toan khung) va V2 (hybrid + mask) DEU bi tu
 * choi o QA thu cong — xem lich su git. Gemini V1 (video dau tien nguoi dung
 * tu tao) da thu o staging; nguoi dung tu danh gia va thay bang Gemini V2
 * (chat luong cao hon) — day la ban DANG DUNG, khong chong ban Gemini V1.
 *
 * Bo test o day xac nhan RIENG phan NOI DAY: PageBackground.tsx goi dung
 * LiveBackground CHI cho "home", dung nguon video that, khong mask, va khong
 * lam vo cac bat bien da co cua PageBackground (xem `page-background.test.mjs`).
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

test("nguon video Home la ban Gemini V2 (chua khong con dung V1 da bi thay), tro dung mot tep that tren dia", () => {
  const s = comp();
  const mp4 = s.match(/mp4: "(\/artwork\/fantasy-backgrounds\/[^"]+\.mp4)"/)?.[1];
  assert.ok(mp4, "thiếu nguồn mp4");
  assert.match(mp4, /home-live-gemini-v2\.mp4$/,
    "chưa dùng đúng bản Gemini V2 — có thể còn trỏ tới Nova Reel hoặc Gemini V1 đã bị thay");
  assert.ok(existsSync(new URL(mp4.split("/").pop(), THU_MUC)), `không tồn tại: ${mp4}`);
});

test("KHONG con nhac toi tai san Nova Reel bi tu choi (live/motion) hay Gemini V1 da bi thay", () => {
  const s = comp();
  assert.ok(!/01-home-sunny-harbor-live/.test(s), "vẫn còn trỏ tới bản Nova Reel V1 bị từ chối");
  assert.ok(!/01-home-sunny-harbor-motion/.test(s), "vẫn còn trỏ tới bản Nova Reel V2 (hybrid) bị từ chối");
  assert.ok(!/home-live-gemini-v1\.mp4/.test(s), "vẫn còn trỏ tới bản Gemini V1 đã bị thay bằng V2");
});

test("KHONG mask/on dinh hoa — danh gia video Gemini nguyen ban nhu nguoi dung duyet thu cong", () => {
  const s = codeOnly(comp());
  assert.ok(!/videoMask=/.test(s),
    "đang truyền videoMask — yêu cầu lần thử đầu là KHÔNG mask, đánh giá video Gemini nguyên bản");
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

test("V1 Cloud Veil: CHI MOT lop nen duy nhat, khong con lop CU/data-ra", () => {
  /*
    Chuyen canh route gio la viec cua `.route-veil` (xem
    `route-transition-veil.test.mjs`) — `PageBackground.tsx` khong con tu
    quan ly mot "lop cu dang mo di" nao nua, nen khong con `tenCu`/`data-ra`
    de kiem tra video co lot vao do hay khong (cau hoi khong con y nghia:
    chi co DUNG MOT `.page-bg-lop`).
  */
  const s = codeOnly(comp());
  assert.ok(!/tenCu|data-ra=/.test(s), "vẫn còn dấu vết lớp CŨ (tenCu/data-ra) của cơ chế cũ");
  assert.equal((s.match(/className="page-bg-lop"/g) ?? []).length, 1,
    "phải đúng MỘT lớp nền — cơ chế cũ (hai lớp cũ/mới) đã bị thay bằng man mây");
});

test("bat bien cu cua PageBackground van dung: khong <img>/style inline TRUC TIEP trong tep nay", () => {
  const s = codeOnly(comp());
  assert.ok(!/<img/.test(s));
  assert.ok(!/style=\{\{/.test(s));
});

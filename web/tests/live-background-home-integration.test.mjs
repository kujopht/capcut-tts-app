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

test("LiveBackground dung poster tu chinh anhNen(lop.ten), khong hardcode duong dan khac", () => {
  const s = codeOnly(comp());
  assert.match(s, /poster=\{anhNen\(lop\.ten\)\}/);
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

test("V3 crossfade: mot NGUON JSX duy nhat cho .page-bg-lop (render qua map, khong hardcode 2 khoi lap lai)", () => {
  /*
    V2: `.route-veil` day dac che kin man hinh dung luc doi anh, nen
    `PageBackground.tsx` chi can DUNG MOT `.page-bg-lop` voi `key={ten}` —
    remount cung, an duoc sau man may. V3 (dac ta muc 10) doi anh phai TAN
    SAC that (may V3 mong hon, khong con che duoc mot cu nhay), nen co THE
    co HAI lop `.page-bg-lop` CUNG LUC trong DOM khi dang crossfade (`cacLop`
    o `PageBackground.tsx`, khoa rieng, `data-fade`) — day la thay doi CO Y,
    khong phai tan du cua co che "tenCu/data-ra" cu (da bi go hoan toan o
    V1). Bai test nay xac nhan JSX chi khai bao MOT lan `className="page-
    bg-lop"` (qua `.map()`, khong copy-paste hai khoi tuong tu cho "cu"/
    "moi") va khong con dung lai bien `tenCu`/`data-ra` cua co che truoc do.
  */
  const s = codeOnly(comp());
  assert.ok(!/tenCu|data-ra=/.test(s), "vẫn còn dấu vết lớp CŨ (tenCu/data-ra) của cơ chế cũ");
  assert.equal((s.match(/className="page-bg-lop"/g) ?? []).length, 1,
    "chỉ nên có MỘT nguồn JSX cho .page-bg-lop (qua map), không copy hai khối lặp lại");
  assert.match(s, /cacLop\.map\(/, "V3 phải render .page-bg-lop qua danh sách lớp (hỗ trợ crossfade 2 lớp cùng lúc)");
});

test("bat bien cu cua PageBackground van dung: khong <img>/style inline TRUC TIEP trong tep nay", () => {
  const s = codeOnly(comp());
  assert.ok(!/<img/.test(s));
  assert.ok(!/style=\{\{/.test(s));
});

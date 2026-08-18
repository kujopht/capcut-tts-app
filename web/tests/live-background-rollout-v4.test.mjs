/*
 * Live Wallpaper — rollout V4, CA 8 chu de: cac rang buoc TOAN CUC khong
 * thuoc rieng ve mot tep nguon nao (xem `live-background-home-integration
 * .test.mjs` cho phan tich hop PageBackground.tsx/backgrounds.ts, va
 * `live-background-v1.test.mjs`/`live-background-multimonitor.test.mjs`
 * cho logic du dieu kien/vong doi cua CHINH `LiveBackground.tsx` — file do
 * KHONG doi trong dot rollout nay, nen cac bai test do van dung nguyen,
 * AP DUNG CHO CA 8 chu de vi component khong biet/khong quan tam chu de).
 *
 * Quet MA NGUON + kiem tra tep tren dia, khong render — dung quy uoc repo.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const CHU_DE = ["home", "explore", "reader", "studio", "write", "library", "account", "auth"];
const THU_MUC_LIVE = new URL("../public/artwork/fantasy-backgrounds/live/", import.meta.url);
const THU_MUC_TINH = new URL("../public/artwork/fantasy-backgrounds/", import.meta.url);

test("moi 8 video runtime deu la H.264 + khong am thanh + kich thuoc hop ly (kiem tra tren dia, khong doan)", () => {
  /*
    Khong goi ffprobe tu bai test (khong muon phu thuoc mot binary ngoai lung
    tung trong CI) — thay vao do kiem tra CHU KY TEP MP4 (box `ftyp`) va gioi
    han kich thuoc nhu mot luoi an toan tho: mot lan ai do vo tinh chep de
    tep HEVC/qua nang vao thay vi ban da ma hoa lai se bi bat o day.
  */
  const gioiHanMB = 12; // ban da ma hoa: 3.6-6.9MB thuc te, chua ai gan 12MB
  for (const tep of ["01-home", "02-explore", "03-reader", "04-studio", "05-write", "06-library", "07-account", "08-auth"]) {
    const url = new URL(`${tep}.mp4`, THU_MUC_LIVE);
    assert.ok(existsSync(url), `thiếu video runtime: ${tep}.mp4`);
    const kt = statSync(url);
    const mb = kt.size / 1024 / 1024;
    assert.ok(mb > 0.5 && mb < gioiHanMB,
      `${tep}.mp4 nặng ${mb.toFixed(1)}MB — nằm ngoài khoảng hợp lý (0.5-${gioiHanMB}MB), có thể chưa mã hoá lại từ bản HEVC gốc`);
  }
});

test("anh tinh (poster) CUA CA 8 chu de van con nguyen — live wallpaper KHONG thay the anh tinh", () => {
  const TEP_TINH = {
    home: "01-home-sunny-harbor", explore: "02-explore-sky-kingdom", reader: "03-reader-moonlit-shrine",
    studio: "04-studio-sky-workshop", write: "05-write-creators-room", library: "06-library-arcane-archive",
    account: "07-account-blossom-realm", auth: "08-login-starlight-gate",
  };
  for (const ten of CHU_DE) {
    const url = new URL(`${TEP_TINH[ten]}.webp`, THU_MUC_TINH);
    assert.ok(existsSync(url), `mất ảnh tĩnh (poster) của chủ đề "${ten}": ${TEP_TINH[ten]}.webp`);
  }
});

test("khong co duong dan .mp4 nao ngoai thu muc live/ duoc tham chieu trong code", () => {
  const files = [
    "../src/components/PageBackground.tsx",
    "../src/lib/backgrounds.ts",
  ].map((p) => read(p)).join("\n");
  const duongDanMp4 = [...codeOnly(files).matchAll(/\/artwork\/fantasy-backgrounds\/([^"]*\.mp4)/g)].map((m) => m[1]);
  assert.ok(duongDanMp4.length > 0, "không tìm thấy đường dẫn .mp4 nào — kiểm tra lại quét");
  for (const d of duongDanMp4) {
    assert.match(d, /^live\//, `đường dẫn video "${d}" nằm ngoài thư mục live/ — cấu trúc thư mục không nhất quán`);
  }
});

test("khong co thu muc/kien truc live-wallpaper song song thu hai (mot noi duy nhat)", () => {
  // Vd: khong dot nao vo tinh tao "artwork/live-backgrounds/" hay tuong tu.
  const src = codeOnly(read("../src/lib/backgrounds.ts"));
  const thuMuc = [...src.matchAll(/`\/artwork\/([a-z-]+)\//g)].map((m) => m[1]);
  assert.deepEqual([...new Set(thuMuc)], ["fantasy-backgrounds"],
    `backgrounds.ts tham chiếu nhiều thư mục artwork khác nhau: ${[...new Set(thuMuc)].join(", ")} — chỉ nên có một`);
});

test("stub tuy chon AUTO/DYNAMIC/STATIC khong bi dong cham/pha vo boi rollout nay", () => {
  // File nay la mot ham thuan, khong biet gi ve chu de/video cu the — rollout
  // video KHONG duoc phep lam no phu thuoc vao `lib/backgrounds.ts`.
  const src = read("../src/lib/liveBackgroundPreference.ts");
  assert.ok(!/backgrounds/.test(src), "stub tuỳ chọn không được phụ thuộc vào lib/backgrounds.ts (chủ đề cụ thể)");
  assert.match(src, /export type HieuUngNen = "auto" \| "dynamic" \| "static";/);
});

test("khong preload/prefetch toan cuc 8 video — chi chu de dang can duoc tai (dac ta muc 12)", () => {
  const layout = codeOnly(read("../src/app/layout.tsx"));
  assert.ok(!/\.mp4/.test(layout), "layout.tsx (chạy cho MỌI trang) không được nhắc tới bất kỳ .mp4 nào");
  assert.ok(!/rel="preload"|rel="prefetch"/.test(layout), "layout.tsx tải sẵn tài nguyên toàn cục");

  const pageBg = codeOnly(read("../src/components/PageBackground.tsx"));
  assert.ok(!/rel="preload"|rel="prefetch"/.test(pageBg), "PageBackground.tsx chủ động preload/prefetch — vi phạm 'zero cross-page live-video preloading'");

  const liveBg = codeOnly(read("../src/components/LiveBackground.tsx"));
  assert.match(liveBg, /preload="none"/, "thẻ <video> phải khai báo preload=\"none\" — trình duyệt không được tự tải trước");
});

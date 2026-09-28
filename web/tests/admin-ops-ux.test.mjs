/*
 * Admin Ops UX — /admin/community, /admin/games, /admin/features.
 *
 * Cung phong cach voi cac bai kiem admin khac: doc THANG source va khang
 * dinh cac dac diem quan trong bang regex, khong dung DOM gia lap.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const games = () => read("../src/app/admin/games/page.tsx");
const features = () => read("../src/app/admin/features/page.tsx");
const community = () => read("../src/app/admin/community/page.tsx");
const api = () => read("../src/lib/api.ts");

/** Bo chu thich truoc khi quet — xem `admin.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

// ---------------------------------------------------------------- Features

test("Features: KHONG co nut/dieu khien bat-tat cho san xuat", () => {
  const src = codeOnly(features());
  // Khong duoc co bat ky POST/PATCH nao toi mot API cho phep — trang nay CHI
  // DOC. Khong duoc co onClick goi mot ham "toggle"/"bat"/"tat" nao.
  assert.ok(!/method:\s*["']POST["']/.test(src), "features có gọi ghi (POST)");
  assert.ok(!/method:\s*["']PATCH["']/.test(src), "features có gọi ghi (PATCH)");
  assert.ok(!/<input[^>]*type=["']checkbox["']/.test(src),
    "features có checkbox bật/tắt");
  assert.ok(!/toggle|Toggle|bậ?t\/tắt/i.test(src) ||
    /không có khả năng bật\/tắt/.test(src),
    "features có vẻ có điều khiển bật/tắt thật");
});

test("Features: dùng đúng vocab 'không xác định' khi cờ chưa tồn tại", () => {
  const src = features();
  assert.match(src, /Không xác định — mã API đang chạy chưa có cờ này/);
});

test("Features: doc capabilities tu /api/limits va games tu gamesConfig(), khong hardcode ten co", () => {
  const src = codeOnly(features());
  assert.match(src, /social\.limits\(\)/);
  assert.match(src, /gamesConfig\(\)/);
  assert.match(src, /MUSIC_ENABLED/);
});

// ------------------------------------------------------------------ Games

test("Games: canh bao MULTIPLAYER PRODUCTION BLOCKED LUON hien, kem nhan tieng Viet", () => {
  const src = games();
  assert.match(src, /MULTIPLAYER PRODUCTION BLOCKED/);
  // Phai co mot nhan tieng Viet di kem, khong chi mot minh cum tieng Anh.
  assert.match(src, /CHẶN Ở PRODUCTION/);
});

test("Games: canh bao khong nam trong nhanh dieu kien phu thuoc ket qua API", () => {
  const src = codeOnly(games());
  const canhBaoAt = src.indexOf("MULTIPLAYER PRODUCTION BLOCKED");
  assert.ok(canhBaoAt > 0, "không tìm thấy khối cảnh báo");
  // Truoc canh bao, trong pham vi gan, khong duoc co dieu kien `missing ?`/
  // `error ?` bao quanh no — banner phai o ngoai cung, khong long trong
  // nhanh thanh cong/that bai cua mot loi goi API.
  const truocDo = src.slice(0, canhBaoAt);
  const doanCuoi = truocDo.slice(-300);
  assert.ok(!/\{(missing|error|loiBxh|loiGames)\s*\?/.test(doanCuoi),
    "cảnh báo có vẻ bị lồng trong nhánh điều kiện của một lời gọi API");
});

test("Games: 404 tu gamesConfig() duoc xu ly nhu trang thai TRUNG TINH, khong phai loi", () => {
  const src = codeOnly(games());
  assert.match(src, /missing/, "không đọc trường `missing` của useAsyncData");
  assert.match(src, /Chưa có API/);
  assert.match(src, /404/);
});

test("Games: khong bia so lieu phong choi\\/XP settlement khi chua co API", () => {
  const src = games();
  assert.match(src, /Phòng chơi.*settlement/s);
  assert.match(src, /Chưa có API/);
});

test("Games: dung lai api\\.getLeaderboard cong khai, khong tu goi fetch rieng", () => {
  const src = codeOnly(games());
  assert.match(src, /api\.getLeaderboard\(/);
});

// -------------------------------------------------------------- Community

test("Community: khong co nut go\\/phuc hoi rieng — chi lien ket sang trang goc", () => {
  const src = codeOnly(community());
  assert.ok(!/removePost|removeComment|resolveReport|restorePost|restoreComment/.test(src),
    "community tự gọi API ghi kiểm duyệt — logic đó chỉ nên ở /admin/posts, /admin/reports, /admin/comments");
  assert.match(src, /href="\/admin\/reports"/);
  assert.match(src, /href="\/admin\/posts"/);
  assert.match(src, /href="\/admin\/comments"/);
});

test("Community: dung lai adminSocial (khong tu goi fetch/request rieng)", () => {
  const src = codeOnly(community());
  assert.match(src, /adminSocial\.overview\(\)/);
  assert.match(src, /adminSocial\.reports\(/);
  assert.match(src, /adminSocial\.posts\(/);
  assert.ok(!/\bfetch\(/.test(src), "community tự gọi fetch() thay vì đi qua lib/api.ts");
});

// --------------------------------------------------------------- Khong lo bi mat

test("Khong trang moi nao lo email/token/id nha cung cap — CHI /admin/users duoc phep co email", () => {
  for (const [ten, src] of [
    ["games", games()],
    ["features", features()],
    ["community", community()],
  ]) {
    const s = codeOnly(src);
    assert.ok(!/\bu\.email\b|\.password|access_token|refresh_token|provider_id/i.test(s),
      `${ten} có vẻ hiển thị dữ liệu bí mật`);
  }
});

// ---------------------------------------------------------------- api.ts

test("gamesConfig() KHONG nam trong adminApi (khong phai route /api/admin/*)", () => {
  const src = api();
  const at = src.indexOf("export const adminApi");
  assert.notEqual(at, -1, "thiếu adminApi");
  const sau = src.indexOf("\nexport ", at + 1);
  const than = sau === -1 ? src.slice(at) : src.slice(at, sau);
  assert.ok(!than.includes("/api/games/config"),
    "gamesConfig lọt vào adminApi — sẽ làm sai bài kiểm 'mọi hàm adminApi nằm dưới /api/admin/'");
  assert.match(src, /export const gamesConfig = \(\)/);
});

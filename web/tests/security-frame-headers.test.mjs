/*
 * Chong clickjacking: moi response do Next tra ve mang `frame-ancestors 'self'`
 * + `X-Frame-Options: SAMEORIGIN`. Truoc day production khong gui header nao —
 * mot site bat ky nhung duoc ca `/admin`.
 *
 * Doc thang `next.config.mjs` (cung cach voi bai test redirect), khong render.
 */
import test from "node:test";
import assert from "node:assert/strict";
import nextConfig from "../next.config.mjs";

const layHeader = async () => {
  const ds = await nextConfig.headers();
  const toanSite = ds.find((m) => m.source === "/(.*)");
  return { ds, toanSite, theoKhoa: Object.fromEntries((toanSite?.headers ?? []).map((h) => [h.key, h.value])) };
};

test("header chong nhung khung ap cho MOI duong dan", async () => {
  const { toanSite } = await layHeader();
  assert.ok(toanSite, "thiếu mục headers() với source '/(.*)'");
  // `/(.*)` khop ca `/` (nhom rong) — dung mau cua tai lieu Next.
  assert.ok(new RegExp(`^${toanSite.source}$`).test("/"), "source phải khớp cả trang chủ /");
  assert.ok(new RegExp(`^${toanSite.source}$`).test("/admin/assets"));
});

test("CSP CHI co frame-ancestors 'self' — khong chan script/anh/font/API nao", async () => {
  const { theoKhoa } = await layHeader();
  assert.equal(theoKhoa["Content-Security-Policy"], "frame-ancestors 'self'");
  // Mot chi thi khac (default-src, script-src...) se bat dau chan tai nguyen that cua trang.
  const chiThi = theoKhoa["Content-Security-Policy"].split(";").map((s) => s.trim()).filter(Boolean);
  assert.deepEqual(chiThi.map((c) => c.split(/\s+/)[0]), ["frame-ancestors"]);
  assert.ok(!/'none'/.test(theoKhoa["Content-Security-Policy"]), "'none' sẽ chặn cả iframe cùng origin (/entertainment nhúng /games/...)");
});

test("X-Frame-Options SAMEORIGIN (du phong trinh duyet cu), khong DENY", async () => {
  const { theoKhoa } = await layHeader();
  assert.equal(theoKhoa["X-Frame-Options"], "SAMEORIGIN", "DENY sẽ chặn cả iframe cùng origin");
});

test("header /audio cu van nguyen (CORS cho tep audio)", async () => {
  const { ds } = await layHeader();
  const audio = ds.find((m) => m.source === "/audio/:path*");
  assert.ok(audio, "mất mục /audio/:path*");
  assert.deepEqual(audio.headers, [
    { key: "Access-Control-Allow-Origin", value: "*" },
    { key: "Access-Control-Allow-Methods", value: "GET, HEAD, OPTIONS" },
  ]);
});

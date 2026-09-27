/*
 * Studio /studio/audio — danh sach giong (do tren production 2026-09-26):
 *   * `/api/voices` bi goi HAI lan moi lan tai trang vi nam chung hieu ung voi `profile`;
 *   * loi mang bi nuot thanh danh sach rong: o chon giong trong, nut Tao bi khoa,
 *     khong mot loi giai thich nao cho nguoi dung.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/app/studio/audio/page.tsx", import.meta.url), "utf8");

test("giong tai trong hieu ung RIENG, khong phu thuoc phien", () => {
  const i = src.indexOf("await api.voices()");
  assert.ok(i >= 0, "phai goi api.voices() trong hieu ung rieng");
  const het = src.indexOf("}, [", i);
  const deps = src.slice(het, src.indexOf("]);", het) + 3);
  assert.equal(deps, "}, [draft, lanTaiGiong]);");
  assert.ok(!deps.includes("profile"));
});

test("loi tai giong KHONG bi nuot thanh danh sach rong", () => {
  assert.ok(!/api\.voices\(\)\.catch\(\(\) => \(\{ voices: \[\]/.test(src));
  assert.match(src, /catch \{\s*if \(mounted\) setLoiGiong\(true\);/);
});

test("co thong bao loi + nut thu lai tai lai danh sach giong", () => {
  assert.match(src, /role="alert"[\s\S]{0,80}Không tải được danh sách giọng đọc/);
  assert.match(src, /onClick=\{\(\) => setLanTaiGiong\(\(n\) => n \+ 1\)\}/);
});

test("job/track cua nguoi dung van chi tai khi da dang nhap", () => {
  assert.match(src, /if \(!profile\) return;[\s\S]{0,200}await refresh\(\);[\s\S]{0,200}khoiPhuc\(j\.jobs\);/);
  assert.match(src, /\}, \[profile, khoiPhuc\]\);/);
});

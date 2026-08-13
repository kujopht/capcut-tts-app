/**
 * V4 Phase 5 — tai/doi/xoa anh bia truyen o /write.
 *
 * Cung phong cach voi cac bai kiem khac trong thu muc nay: doc THANG source
 * va khang dinh cac dac diem quan trong bang regex, khong dung DOM gia lap
 * (repo khong co jsdom/testing-library — xem package.json).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const write = () => read("../src/app/write/page.tsx");
const api = () => read("../src/lib/api.ts");
const limits = () => read("../src/lib/limits.ts");

test("/write dung MAX_COVER_EDGE tu lib/limits, khong tu bia con so", () => {
  const src = write();
  assert.match(src, /import\s*\{[^}]*MAX_COVER_EDGE[^}]*\}\s*from\s*"@\/lib\/limits"/);
  assert.match(src, /xuLyAnh\(tep,\s*MAX_COVER_EDGE\)/);
});

test("MAX_COVER_EDGE la mot hang so duoc dan, khong phai gia tri tinh", () => {
  assert.match(limits(), /export const MAX_COVER_EDGE\s*=\s*\d+/);
});

test("/write goi api.setNovelCover va api.removeNovelCover", () => {
  const src = write();
  assert.match(src, /api\.setNovelCover\(/);
  assert.match(src, /api\.removeNovelCover\(/);
});

test("lib/api.ts: duong REST dung cho tai/xoa bia", () => {
  const src = api();
  assert.match(src, /setNovelCover:[\s\S]{0,220}\/api\/novels\/\$\{novelId\}\/cover/);
  assert.match(src, /setNovelCover:[\s\S]{0,260}method:\s*"PUT"/);
  assert.match(src, /removeNovelCover:[\s\S]{0,180}\/api\/novels\/\$\{novelId\}\/cover/);
  assert.match(src, /removeNovelCover:[\s\S]{0,180}method:\s*"DELETE"/);
});

test("URL xem truoc tam thoi cua anh bia duoc thu hoi sau khi tai len xong", () => {
  // Khac PostComposer (giu URL de HIEN thi cho toi khi dong): o day anh that
  // tra ve NGAY tu may chu (`result.novel.cover_url`), nen URL blob tam chi
  // song trong luc cho, va phai duoc thu hoi ngay khi khong con can nua.
  assert.match(write(), /URL\.revokeObjectURL\(anh\.xemTruoc\)/);
});

test("nut Go anh bia chi hien khi DA co bia, va khoa duoc trong luc dang luu", () => {
  const src = write();
  const at = src.indexOf("Gỡ ảnh bìa");
  assert.ok(at > 0, "không tìm thấy nút Gỡ ảnh bìa");
  const truoc = src.slice(Math.max(0, at - 600), at);
  assert.match(truoc, /selected\.cover_url\s*\?/, "nút Gỡ phải có điều kiện cover_url");
  assert.match(truoc, /disabled=\{savingCover\}/);
});

test("o chon tep bia bi khoa trong luc dang luu, chi nhan anh", () => {
  const src = write();
  const at = src.indexOf('type="file"');
  const doan = src.slice(at, at + 200);
  assert.match(doan, /accept="image\/\*"/);
  assert.match(doan, /disabled=\{savingCover\}/);
});

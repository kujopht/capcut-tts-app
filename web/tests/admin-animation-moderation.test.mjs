/**
 * Admin Control Center V2, Phase 4 — kiem duyet Animation (series/tap).
 *
 * Cung phong cach voi cac bai kiem khac: doc THANG source va khang dinh cac
 * dac diem quan trong bang regex, khong dung DOM gia lap.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const api = () => read("../src/lib/api.ts");
const shell = () => read("../src/components/AdminShell.tsx");
const landing = () => read("../src/app/admin/animation/page.tsx");
const list = () => read("../src/app/admin/animation/series/page.tsx");
const detail = () => read("../src/app/admin/animation/series/[id]/page.tsx");

// -- lop api --------------------------------------------------------------

test("adminApi: sau ham Animation deu goi dung duong /api/admin/animation/*", () => {
  const src = api();
  const at = src.indexOf("animationSeries: (");
  assert.ok(at > 0, "thiếu animationSeries");
  const doan = src.slice(at, at + 2200);
  assert.match(doan, /\/api\/admin\/animation\/series\?/);
  assert.match(doan, /animationSeriesDetail:[\s\S]{0,150}\/api\/admin\/animation\/series\/\$\{encodeURIComponent\(seriesId\)\}`/);
  assert.match(doan, /unpublishAnimationSeries:[\s\S]{0,150}\/unpublish`/);
  assert.match(doan, /restoreAnimationSeries:[\s\S]{0,150}\/restore`/);
  assert.match(doan, /unpublishAnimationEpisode:[\s\S]{0,200}\/api\/admin\/animation\/episodes\/\$\{encodeURIComponent\(episodeId\)\}\/unpublish`/);
  assert.match(doan, /restoreAnimationEpisode:[\s\S]{0,200}\/api\/admin\/animation\/episodes\/\$\{encodeURIComponent\(episodeId\)\}\/restore`/);
});

test("AnimationSeries/AnimationEpisode: co truong moderation_state TACH BACH voi state", () => {
  const src = api();
  const seriesAt = src.indexOf("export interface AnimationSeries");
  const seriesDoan = src.slice(seriesAt, src.indexOf("export type AnimationSource"));
  assert.match(seriesDoan, /moderation_state: "visible" \| "removed"/);
  assert.match(seriesDoan, /removed_by: string/);

  const epAt = src.indexOf("export interface AnimationEpisode");
  const epDoan = src.slice(epAt, epAt + 900);
  assert.match(epDoan, /moderation_state: "visible" \| "removed"/);
});

// -- dieu huong -----------------------------------------------------------

test("AdminShell: muc Series tro thang toi /admin/animation/series", () => {
  const src = shell();
  assert.match(src, /href: "\/admin\/animation\/series", nhan: "Series"/);
});

// -- trang landing ----------------------------------------------------------

test("Trang landing Animation: chi co lien ket, KHONG goi adminApi", () => {
  const src = landing();
  assert.ok(!src.includes("adminApi."), "trang landing gọi adminApi nhưng không vẽ trạng thái tải");
  assert.match(src, /href="\/admin\/animation\/series"/);
});

// -- danh sach --------------------------------------------------------------

test("Danh sach series: co tim kiem, loc trang thai VA sap xep, deu goi server", () => {
  const src = list();
  assert.match(src, /adminApi\.animationSeries\(/);
  assert.match(src, /q: tu, state: tt, sort: sap/);
  assert.match(src, /"newest" \| "oldest"/);
});

test("Danh sach series: ve CA hai truc trang thai (xuat ban VA kiem duyet) tren cung mot hang", () => {
  const src = list();
  assert.match(src, /s\.state === "published"/);
  assert.match(src, /s\.moderation_state === "removed"/);
});

test("Danh sach series: co phan trang server (Trang truoc\\/Trang sau)", () => {
  const src = list();
  assert.match(src, /Trang trước/);
  assert.match(src, /Trang sau/);
  assert.match(src, /offset: trangThai \* TRANG/);
});

// -- chi tiet -----------------------------------------------------------

test("Chi tiet series: ve HAI the trang thai rieng biet (xuat ban cua chu vs kiem duyet)", () => {
  const src = detail();
  assert.match(src, /\(chủ sở hữu\)/);
  assert.match(src, /\(kiểm duyệt\)/);
});

test("Chi tiet series: chu so huu KHONG the tu phuc hoi — chi nut quan tri goi restore", () => {
  const src = detail();
  assert.match(src, /adminApi\.restoreAnimationSeries/);
  assert.match(src, /không thể tự xuất bản lại để hoàn tác/i);
});

test("Chi tiet series: go series VA go tap deu qua ConfirmDialog, deu doi ghi chu", () => {
  const src = detail();
  const soLanConfirm = (src.match(/<ConfirmDialog/g) ?? []).length;
  assert.equal(soLanConfirm, 2, "phải có đúng 2 hộp xác nhận (gỡ series + gỡ tập)");
  assert.match(src, /if \(!ghiChu\.trim\(\)\) return;[\s\S]{0,80}setDangGui\(true\);[\s\S]{0,200}unpublishAnimationSeries/);
});

test("Chi tiet series: tap go RIENG, khong dong toi series cha", () => {
  const src = detail();
  assert.match(src, /unpublishAnimationEpisode/);
  assert.match(src, /Chỉ tập này bị gỡ/);
});

test("Chi tiet series: dung DanhSachTrangThai, khong tu ve cong chan rieng", () => {
  const src = detail();
  assert.match(src, /DanhSachTrangThai/);
  assert.ok(!src.includes("<AdminShell"), "trang tự bọc cổng chặn thay vì dùng layout");
});

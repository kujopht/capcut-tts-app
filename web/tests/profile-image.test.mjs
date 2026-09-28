/*
 * SOCIAL & PLAY V1 — toan cat/phong anh ho so: luon phu kin khung, phong quanh
 * tam, keo bi kep bien, vung nguon dung ty le khung.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { PHONG_TOI_DA, doiPhong, keo, kepViTri, khungDau, tiLePhu, vungNguon } from "../src/lib/profileImage.ts";

const gan = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} ~ ${b}`);

test("khung dau: phu kin, can giua, vung nguon dung ty le khung", () => {
  const k = khungDau(2000, 1000, 240, 240); // anh ngang, khung vuong
  gan(tiLePhu(k), 0.24);
  gan(k.y, 0);
  gan(k.x, (240 - 2000 * 0.24) / 2);
  const v = vungNguon(k);
  gan(v.sw, 1000);
  gan(v.sh, 1000);
  gan(v.sx, 500);
  gan(v.sy, 0);
});

test("anh bia 3:1 tu anh doc: cat giua theo chieu doc", () => {
  const k = khungDau(1200, 1600, 600, 200);
  const v = vungNguon(k);
  gan(v.sw / v.sh, 3);
  gan(v.sw, 1200);
  gan(v.sy, (1600 - 400) / 2);
});

test("keo bi kep: khong bao gio lo nen trong", () => {
  const k = khungDau(1000, 1000, 200, 200);
  const trai = keo(k, 5000, 5000);
  gan(trai.x, 0);
  gan(trai.y, 0);
  const phong = doiPhong(k, 2);
  const phai = keo(phong, -5000, -5000);
  gan(phai.x, 200 - 1000 * 0.2 * 2);
  gan(phai.y, 200 - 1000 * 0.2 * 2);
});

test("phong quanh tam va bi kep [1, toi da]", () => {
  const k = khungDau(1000, 1000, 200, 200);
  const p = doiPhong(k, 2);
  // tam anh van o tam khung
  const s = tiLePhu(p) * p.phong;
  gan((100 - p.x) / s, 500);
  gan((100 - p.y) / s, 500);
  assert.equal(doiPhong(k, 99).phong, PHONG_TOI_DA);
  assert.equal(doiPhong(k, 0.1).phong, 1);
  assert.equal(kepViTri({ ...k, phong: Number.NaN }).phong, 1);
});

/*
 * Live Wallpaper V1, Phan 21 — stub "Hiệu ứng nền" (AUTO/DYNAMIC/STATIC).
 * KHONG phai mot tinh nang cai dat day du (chua co UI, chua co luu tru) —
 * chi mot ham thuan tuy dinh nghia Y NGHIA cho lan mo rong sau nay.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { apDungHieuUngNen } from "../src/lib/liveBackgroundPreference.ts";

test("giamChuyenDong LUON thang, bat ke lua chon nao (tro nang khong phai tham my)", () => {
  for (const luaChon of ["auto", "dynamic", "static"]) {
    assert.equal(
      apDungHieuUngNen(luaChon, { giamChuyenDong: true, tietKiemDuLieu: false, laManHinhNho: false }),
      false,
      `${luaChon} phải tôn trọng prefers-reduced-motion`,
    );
  }
});

test("static: khong bao gio phat video, ke ca khi moi truong thuan loi", () => {
  assert.equal(
    apDungHieuUngNen("static", { giamChuyenDong: false, tietKiemDuLieu: false, laManHinhNho: false }),
    false,
  );
});

test("dynamic: uu tien video, bo qua saveData/man hinh nho (nhung KHONG bo qua reduced-motion)", () => {
  assert.equal(
    apDungHieuUngNen("dynamic", { giamChuyenDong: false, tietKiemDuLieu: true, laManHinhNho: true }),
    true,
  );
});

test("auto: giu dung logic mac dinh hien tai cua LiveBackground (tiet kiem du lieu/man hinh nho -> tinh)", () => {
  assert.equal(
    apDungHieuUngNen("auto", { giamChuyenDong: false, tietKiemDuLieu: true, laManHinhNho: false }),
    false,
  );
  assert.equal(
    apDungHieuUngNen("auto", { giamChuyenDong: false, tietKiemDuLieu: false, laManHinhNho: true }),
    false,
  );
  assert.equal(
    apDungHieuUngNen("auto", { giamChuyenDong: false, tietKiemDuLieu: false, laManHinhNho: false }),
    true,
  );
});

/*
 * DIEU PHOI TIENG: giong doc chuong > nhac nen. Chay CHINH `src/lib/audioFocus.ts`.
 * Sprint nay khong lam san pham nhac — chi khoa lai cai khop noi de lam sau.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { CHINH_SACH, DieuPhoiAm, UU_TIEN } from "../src/lib/audioFocus.ts";

function kenhGhiLai() {
  const log = [];
  return {
    log,
    dk: (uuTien) => ({
      uuTien,
      khiBiCat: (kieu) => log.push(`cat:${kieu}`),
      khiDuocTraLai: () => log.push("tra"),
    }),
  };
}

test("giong doc > nhac nen, va chinh sach hom nay la 'pause' (giu hanh vi cu)", () => {
  assert.ok(UU_TIEN.narration > UU_TIEN.ambient);
  assert.equal(CHINH_SACH.narration, "pause");
});

test("giong doc bat dau -> nhac nen bi cat; nhac bat dau -> KHONG cat giong doc", () => {
  const dp = new DieuPhoiAm();
  const nhac = kenhGhiLai();
  const doc = kenhGhiLai();
  dp.dangKy("ambient", nhac.dk(UU_TIEN.ambient));
  dp.dangKy("narration", doc.dk(UU_TIEN.narration));
  dp.yeuCau("narration");
  assert.deepEqual(nhac.log, ["cat:pause"]);
  assert.equal(dp.kenhDangGiu(), "narration");
  dp.yeuCau("ambient");
  assert.deepEqual(doc.log, [], "kenh thap khong bao gio cat kenh cao");
  assert.equal(dp.kenhDangGiu(), "narration");
});

test("tra quyen sau 'pause': nhac KHONG tu phat lai (bat ngo cho nguoi dung)", () => {
  const dp = new DieuPhoiAm();
  const nhac = kenhGhiLai();
  dp.dangKy("ambient", nhac.dk(UU_TIEN.ambient));
  dp.yeuCau("narration");
  dp.traLai("narration");
  assert.deepEqual(nhac.log, ["cat:pause"]);
  assert.equal(dp.kenhDangGiu(), null);
  // Tra lai hai lan la khong-lam-gi.
  dp.traLai("narration");
  assert.deepEqual(nhac.log, ["cat:pause"]);
});

test("nhanh 'duck' da noi san: ha am luong khi giong doc giu, tra lai khi dung", () => {
  CHINH_SACH.narration = "duck";
  try {
    const dp = new DieuPhoiAm();
    const nhac = kenhGhiLai();
    dp.dangKy("ambient", nhac.dk(UU_TIEN.ambient));
    dp.yeuCau("narration");
    dp.traLai("narration");
    assert.deepEqual(nhac.log, ["cat:duck", "tra"]);
  } finally {
    CHINH_SACH.narration = "pause";
  }
});

test("mot kenh hong khong duoc chan giong doc; huy dang ky don sach", () => {
  const dp = new DieuPhoiAm();
  const huy = dp.dangKy("ambient", {
    uuTien: UU_TIEN.ambient,
    khiBiCat: () => {
      throw new Error("hong");
    },
  });
  assert.doesNotThrow(() => dp.yeuCau("narration"));
  huy();
  dp.traLai("narration");
  assert.equal(dp.kenhDangGiu(), null);
});

/*
 * "THEO GIONG DOC": tu cuon theo doan dang doc, TAM DUNG khi nguoi dung tu
 * cuon, va "Tới đoạn đang đọc" de quay lai. Chay CHINH `src/lib/followScroll.ts`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  cheDoBanDau,
  congTacDangBat,
  khiBamCongTac,
  khiNguoiDungCuon,
  khiToiDoanDangDoc,
  kieuCuon,
  laCuonTay,
  nutToiDoan,
  trongVungDoc,
  viTriCuonDich,
} from "../src/lib/followScroll.ts";

const K = { cao: 900, tren: 80, duoi: 140 };

test("ban dau: theo mac dinh; giam chuyen dong -> KHONG tu cuon; lua chon da luu thang", () => {
  assert.equal(cheDoBanDau(false), "theo");
  assert.equal(cheDoBanDau(true), "tat", "prefers-reduced-motion: khong tu cuon");
  assert.equal(cheDoBanDau(true, true), "theo", "nguoi dung da chu dong bat thi ton trong");
  assert.equal(cheDoBanDau(false, false), "tat");
  assert.equal(cheDoBanDau(false, null), "theo");
});

test("nguoi dung tu cuon -> TAM DUNG (chi tu 'theo'); da tat thi van tat", () => {
  assert.equal(khiNguoiDungCuon("theo"), "tam-dung");
  assert.equal(khiNguoiDungCuon("tam-dung"), "tam-dung");
  assert.equal(khiNguoiDungCuon("tat"), "tat", "cuon tay khong duoc bat lai cai nguoi dung da tat");
});

test("Tới đoạn đang đọc -> bat lai theo doi tu MOI trang thai", () => {
  assert.equal(khiToiDoanDangDoc(), "theo");
});

test("cong tac 'Theo giọng đọc': tam dung van hien la BAT; bam thi tat; bam lai thi theo", () => {
  assert.equal(congTacDangBat("theo"), true);
  assert.equal(congTacDangBat("tam-dung"), true);
  assert.equal(congTacDangBat("tat"), false);
  assert.equal(khiBamCongTac("theo"), "tat");
  assert.equal(khiBamCongTac("tam-dung"), "tat");
  assert.equal(khiBamCongTac("tat"), "theo");
});

test("nhan dien cuon tay bang Y DINH, khong bang su kien scroll", () => {
  assert.equal(laCuonTay({ type: "wheel" }), true);
  assert.equal(laCuonTay({ type: "touchmove" }), true);
  // Lenh scrollTo cua chinh ta chi ban `scroll` — khong bao gio la cuon tay.
  assert.equal(laCuonTay({ type: "scroll" }), false);
  // Bam thanh cuon cua trang (dich = <html>) la cuon tay; bam vao chu thi khong.
  assert.equal(laCuonTay({ type: "pointerdown", laGocTaiLieu: true }), true);
  assert.equal(laCuonTay({ type: "pointerdown", laGocTaiLieu: false }), false);
  for (const key of ["PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End", " "]) {
    assert.equal(laCuonTay({ type: "keydown", key, tagName: "BODY" }), true, `phim ${key}`);
  }
  // Phim cuon TRONG o nhap lieu khong cuon trang.
  assert.equal(laCuonTay({ type: "keydown", key: "ArrowDown", tagName: "INPUT" }), false);
  assert.equal(laCuonTay({ type: "keydown", key: " ", tagName: "TEXTAREA" }), false);
  assert.equal(laCuonTay({ type: "keydown", key: "ArrowDown", tagName: "DIV", isContentEditable: true }), false);
  // Space tren nut = bam nut.
  assert.equal(laCuonTay({ type: "keydown", key: " ", tagName: "BUTTON" }), false);
  // Phim tat trinh duyet.
  assert.equal(laCuonTay({ type: "keydown", key: "End", ctrlKey: true, tagName: "BODY" }), false);
  // Phim khac (vd J/K/L cua trinh phat).
  assert.equal(laCuonTay({ type: "keydown", key: "k", tagName: "BODY" }), false);
});

test("vung doc thoai mai: doan con thay thi KHONG cuon (khong giang trang moi vai giay)", () => {
  assert.equal(trongVungDoc({ top: 300, bottom: 420 }, K), true);
  // Sat duoi (sap chui vao trinh phat noi) -> ra khoi vung.
  assert.equal(trongVungDoc({ top: 700, bottom: 820 }, K), false);
  // Da troi len duoi header -> ra khoi vung.
  assert.equal(trongVungDoc({ top: 40, bottom: 200 }, K), false);
  // Doan cao hon ca man hinh: dau doan con trong vung la doc duoc.
  assert.equal(trongVungDoc({ top: 120, bottom: 2400 }, K), true);
});

test("vi tri cuon dich: dua doan ve ~28% vung thay duoc, khong phai giua; khong am", () => {
  const dich = viTriCuonDich({ top: 1500 }, 2000, K);
  const vung = K.cao - K.tren - K.duoi;
  assert.equal(dich, Math.round(2000 + 1500 - (K.tren + vung * 0.28)));
  assert.equal(viTriCuonDich({ top: -99999 }, 10, K), 0);
});

test("giam chuyen dong -> nhay tuc thi, khong truot", () => {
  assert.equal(kieuCuon(true), "auto");
  assert.equal(kieuCuon(false), "smooth");
});

test("nut noi 'Tới đoạn đang đọc': chi khi dang nghe, chu hien, doan KHUAT va KHONG dang theo", () => {
  const base = { dangNghe: true, hienChu: true, doan: 12, k: K };
  // Doan nam duoi -> mui ten xuong.
  assert.equal(nutToiDoan("tam-dung", { ...base, hop: { top: 1200, bottom: 1300 } }), "xuong");
  // Doan nam tren -> mui ten len.
  assert.equal(nutToiDoan("tat", { ...base, hop: { top: -600, bottom: -500 } }), "len");
  // Doan dang thay -> khong can nut.
  assert.equal(nutToiDoan("tam-dung", { ...base, hop: { top: 300, bottom: 400 } }), null);
  // Dang theo -> ta tu cuon, khong can nut.
  assert.equal(nutToiDoan("theo", { ...base, hop: { top: 1200, bottom: 1300 } }), null);
  // An chu / khong nghe / chua co doan -> khong nut.
  assert.equal(nutToiDoan("tam-dung", { ...base, hienChu: false, hop: { top: 1200, bottom: 1300 } }), null);
  assert.equal(nutToiDoan("tam-dung", { ...base, dangNghe: false, hop: { top: 1200, bottom: 1300 } }), null);
  assert.equal(nutToiDoan("tam-dung", { ...base, doan: -1, hop: null }), null);
});

test("trang chuong noi day du: y dinh -> tam dung, khong tu cuon khi da tam dung, nut toi doan bat lai", () => {
  const src = readFileSync(new URL("../src/components/reader/ChapterExperience.tsx", import.meta.url), "utf8");
  for (const ev of ["wheel", "touchmove", "keydown", "pointerdown"]) {
    assert.match(src, new RegExp(`window\\.addEventListener\\("${ev}", khiNhap`), `thieu nghe ${ev}`);
  }
  assert.ok(!/addEventListener\("scroll", khiNhap/.test(src), "khong duoc coi su kien scroll la cuon tay");
  // Tu cuon CHI khi dang "theo" va doan ra khoi vung doc.
  assert.match(src, /if \(doanDoc < 0 \|\| theo !== "theo" \|\| !hienChuDay\) return;/);
  assert.match(src, /if \(trongVungDoc\(hop, k\)\) return;/);
  assert.match(src, /setTheoTay\(khiToiDoanDangDoc\(\)\)/);
  // Nut noi va trinh phat khong tinh la "cuon trang".
  assert.match(src, /closest\?\.\("\[data-khong-tinh-cuon\]"\)/);
});

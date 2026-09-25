/*
 * DONG BO DOC <-> NGHE: tu thoi diem audio ra DOAN dang doc, va nguoc lai.
 * Chay CHINH `src/lib/chapterSync.ts` (Node 24 nap thang `.ts`), khong doc
 * chuoi ma nguon.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  doanDangDoc,
  giayBatDauDoan,
  lapBanDoPhuDe,
  lapMoHinh,
  lapMocUocLuong,
  tachDoanVan,
  timDoanPhuDe,
} from "../src/lib/chapterSync.ts";

test("tachDoanVan: mot dinh nghia cho ca may chu lan bo dong bo", () => {
  assert.deepEqual(tachDoanVan(""), []);
  assert.deepEqual(tachDoanVan(null), []);
  assert.deepEqual(tachDoanVan("Một.\n\nHai.\n\n\n\nBa."), ["Một.", "Hai.", "Ba."]);
  // CRLF va dong trang co dau cach giua hai doan (du lieu nhap tu Windows).
  assert.deepEqual(tachDoanVan("A\r\n\r\nB\n  \nC"), ["A", "B", "C"]);
  // Xuong dong DON trong mot doan (tho, hoi thoai) KHONG tach doan.
  assert.deepEqual(tachDoanVan("Dòng một\nDòng hai\n\nĐoạn sau"), ["Dòng một\nDòng hai", "Đoạn sau"]);
  // Doan rong o dau/cuoi bi bo — khong sinh <p> trong.
  assert.deepEqual(tachDoanVan("\n\nX\n\n"), ["X"]);
});

test("timDoanPhuDe: tim nhi phan doan co start_ms <= ms", () => {
  const seg = [0, 1000, 2500, 4000].map((s) => ({ text: "x", start_ms: s, end_ms: s + 900 }));
  assert.equal(timDoanPhuDe(seg, -5), -1);
  assert.equal(timDoanPhuDe(seg, 0), 0);
  assert.equal(timDoanPhuDe(seg, 999), 0);
  assert.equal(timDoanPhuDe(seg, 1000), 1);
  assert.equal(timDoanPhuDe(seg, 3999), 2);
  assert.equal(timDoanPhuDe(seg, 99999), 3);
  assert.equal(timDoanPhuDe([], 10), -1);
});

const DOAN = [
  "Đó là một buổi sáng sớm ấm áp. Tôi thức dậy từ lâu.",
  "“Con dậy rồi à?” mẹ hỏi, giọng khàn khàn!",
  "Ngoài sân, tiếng gỗ gõ đều. Một, hai, ba.",
];

test("lapBanDoPhuDe: moi cau phu de nam trong dung doan (khop bo qua dau cau/khoang trang)", () => {
  const phuDe = [
    { text: "Đó là một buổi sáng sớm ấm áp.", start_ms: 0, end_ms: 2000 },
    { text: "Tôi thức dậy từ lâu.", start_ms: 2000, end_ms: 3500 },
    // Ngoac kep "thong minh" + khoang trang khac — van khop.
    { text: "\"Con dậy rồi à?\"   mẹ hỏi, giọng khàn khàn!", start_ms: 3500, end_ms: 6000 },
    { text: "Ngoài sân, tiếng gỗ gõ đều.", start_ms: 6000, end_ms: 8000 },
    { text: "Một, hai, ba.", start_ms: 8000, end_ms: 9000 },
  ];
  assert.deepEqual(lapBanDoPhuDe(DOAN, phuDe), [0, 0, 1, 2, 2]);
});

test("lapBanDoPhuDe: cau KHONG tim thay (chuong da sua) duoc noi suy, van khong giam", () => {
  const phuDe = [
    { text: "Đó là một buổi sáng sớm ấm áp.", start_ms: 0, end_ms: 2000 },
    { text: "Câu này đã bị tác giả xoá khỏi bản chữ.", start_ms: 2000, end_ms: 4000 },
    { text: "Ngoài sân, tiếng gỗ gõ đều.", start_ms: 4000, end_ms: 6000 },
  ];
  const bd = lapBanDoPhuDe(DOAN, phuDe);
  assert.equal(bd[0], 0);
  assert.equal(bd[2], 2);
  assert.ok(bd[1] >= 0 && bd[1] <= 2, "khong duoc de -1 lot ra");
  for (let i = 1; i < bd.length; i++) assert.ok(bd[i] >= bd[i - 1], "ban do phai khong giam");
});

test("lapBanDoPhuDe: cau lap lai o nhieu doan -> con tro chi tien, khong nhay ve doan dau", () => {
  const doan = ["Ha ha.", "Hắn đi.", "Ha ha.", "Hết."];
  const phuDe = ["Ha ha.", "Hắn đi.", "Ha ha.", "Hết."].map((t, i) => ({ text: t, start_ms: i * 1000, end_ms: i * 1000 + 900 }));
  assert.deepEqual(lapBanDoPhuDe(doan, phuDe), [0, 1, 2, 3]);
});

test("uoc luong theo DO DAI (chuong khong co phu de): doan dai chiem nhieu thoi gian hon", () => {
  const doan = ["Ngắn.", "x".repeat(900), "Ngắn."];
  const moc = lapMocUocLuong(doan);
  assert.equal(moc[0], 0);
  assert.ok(moc[1] < 0.05, "doan ngan dau chi chiem mot phan nho");
  assert.ok(moc[2] > 0.9, "doan dai giua chiem gan het");
  const m = lapMoHinh(doan, null);
  assert.equal(m.coPhuDe, false);
  // 600s: o giay 300 dang doc DOAN DAI — ban chia theo SO DOAN (WIP cu) se noi doan 1/3 = doan 1 thi dung
  // tinh co, nhung o giay 40 ban cu noi "doan 0" con uoc luong theo do dai noi doan 1.
  assert.equal(doanDangDoc(m, 300, 600), 1);
  assert.equal(doanDangDoc(m, 40, 600), 1);
  assert.equal(doanDangDoc(m, 599, 600), 2);
  assert.equal(doanDangDoc(m, 0.1, 600), 0);
});

test("doanDangDoc: chua biet thoi luong / chuong rong / giay vo nghia -> -1", () => {
  const m = lapMoHinh(DOAN, null);
  assert.equal(doanDangDoc(m, 10, 0), -1);
  assert.equal(doanDangDoc(m, NaN, 600), -1);
  assert.equal(doanDangDoc(m, -1, 600), -1);
  assert.equal(doanDangDoc(lapMoHinh([], null), 10, 600), -1);
  // Qua cuoi: van la doan cuoi, khong tran mang.
  assert.equal(doanDangDoc(m, 10_000, 600), DOAN.length - 1);
});

test("co phu de: doanDangDoc dung phu de, khong dung uoc luong", () => {
  const phuDe = [
    { text: "Đó là một buổi sáng sớm ấm áp.", start_ms: 0, end_ms: 1000 },
    { text: "Tôi thức dậy từ lâu.", start_ms: 1000, end_ms: 2000 },
    { text: "“Con dậy rồi à?” mẹ hỏi, giọng khàn khàn!", start_ms: 2000, end_ms: 50_000 },
    { text: "Ngoài sân, tiếng gỗ gõ đều.", start_ms: 50_000, end_ms: 55_000 },
    { text: "Một, hai, ba.", start_ms: 55_000, end_ms: 60_000 },
  ];
  const m = lapMoHinh(DOAN, phuDe);
  assert.equal(m.coPhuDe, true);
  assert.equal(doanDangDoc(m, 1.5, 60), 0);
  // Giay 30: theo phu de van la doan 1 (cau dai 48s), uoc luong do dai se noi doan 1 hoac 2.
  assert.equal(doanDangDoc(m, 30, 60), 1);
  assert.equal(doanDangDoc(m, 51, 60), 2);
  // Truoc cau dau (ms am do lam tron) -> doan 0, khong -1.
  assert.equal(doanDangDoc(m, 0, 60), 0);
});

test("KHU HOI: bam doan i -> tua toi giayBatDauDoan -> vach sang DUNG doan i (ca hai mo hinh)", () => {
  const doan = Array.from({ length: 40 }, (_, i) => (i % 5 === 0 ? "Dài ".repeat(120) : "Ngắn gọn thôi.") + ` #${i}`);
  const thoiLuong = 1234;
  const m = lapMoHinh(doan, null);
  for (let i = 0; i < doan.length; i++) {
    const g = giayBatDauDoan(m, i, thoiLuong);
    assert.notEqual(g, null);
    assert.equal(doanDangDoc(m, g, thoiLuong), i, `doan ${i} khong khu hoi (uoc luong)`);
  }
  const phuDe = doan.map((t, i) => ({ text: t, start_ms: i * 10_000, end_ms: i * 10_000 + 9_000 }));
  const m2 = lapMoHinh(doan, phuDe);
  for (let i = 0; i < doan.length; i++) {
    const g = giayBatDauDoan(m2, i, thoiLuong);
    assert.equal(doanDangDoc(m2, g, thoiLuong), i, `doan ${i} khong khu hoi (phu de)`);
  }
});

test("giayBatDauDoan: chi so ngoai pham vi / chua biet thoi luong -> null", () => {
  const m = lapMoHinh(DOAN, null);
  assert.equal(giayBatDauDoan(m, -1, 100), null);
  assert.equal(giayBatDauDoan(m, 99, 100), null);
  assert.equal(giayBatDauDoan(m, 1, 0), null);
});

test("chuong 329 doan (co that — Cold Between Wars ch.1): mot lan tra cuu la tim nhi phan, khong quet", () => {
  const doan = Array.from({ length: 329 }, (_, i) => `Đoạn thứ ${i}. `.repeat(1 + (i % 7)));
  const m = lapMoHinh(doan, null);
  const t0 = performance.now();
  let tong = 0;
  for (let s = 0; s < 3600; s += 0.25) tong += doanDangDoc(m, s, 3600);
  const ms = performance.now() - t0;
  assert.ok(tong > 0);
  assert.ok(ms < 200, `14.400 lan tra cuu mat ${ms.toFixed(1)}ms — qua cham cho timeupdate`);
});

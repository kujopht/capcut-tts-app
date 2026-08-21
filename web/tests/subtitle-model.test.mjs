// Subtitle Studio — mo hinh phu de thuan (overnight Phase 4, Phan 4D/4G).
import { test } from "node:test";
import assert from "node:assert/strict";

const {
  taoPhanDoan,
  sapXep,
  tachPhanDoan,
  gopVoiPhanDoanSau,
  xoaPhanDoan,
  suaVanBan,
  suaThoiGian,
  giayThanhSrt,
  giayThanhVtt,
  xuatSrt,
  xuatVtt,
  nhapSrtHoacVtt,
} = await import("../src/lib/subtitles/model.ts");

test("giayThanhSrt dung dau phay, du 3 chu so mili giay", () => {
  assert.equal(giayThanhSrt(0), "00:00:00,000");
  assert.equal(giayThanhSrt(1.5), "00:00:01,500");
  assert.equal(giayThanhSrt(65), "00:01:05,000");
  assert.equal(giayThanhSrt(3661.25), "01:01:01,250");
});

test("giayThanhVtt dung dau cham", () => {
  assert.equal(giayThanhVtt(1.5), "00:00:01.500");
});

test("sapXep sap theo start, khong doi mang goc", () => {
  const a = taoPhanDoan(5, 6, "b");
  const b = taoPhanDoan(1, 2, "a");
  const goc = [a, b];
  const ra = sapXep(goc);
  assert.equal(ra[0].text, "a");
  assert.equal(ra[1].text, "b");
  assert.equal(goc[0].text, "b"); // mang goc KHONG doi
});

test("tachPhanDoan chia dung diem, giu van ban o phan dau", () => {
  const s = taoPhanDoan(0, 10, "xin chào thế giới");
  const ra = tachPhanDoan([s], s.id, 4);
  assert.equal(ra.length, 2);
  assert.equal(ra[0].start, 0);
  assert.equal(ra[0].end, 4);
  assert.equal(ra[0].text, "xin chào thế giới");
  assert.equal(ra[1].start, 4);
  assert.equal(ra[1].end, 10);
  assert.equal(ra[1].text, "");
});

test("tachPhanDoan tai mep khong lam gi (tranh doan rong)", () => {
  const s = taoPhanDoan(0, 10, "x");
  const raODau = tachPhanDoan([s], s.id, 0);
  const raOCuoi = tachPhanDoan([s], s.id, 10);
  assert.equal(raODau.length, 1);
  assert.equal(raOCuoi.length, 1);
});

test("gopVoiPhanDoanSau noi van ban bang mot dau cach", () => {
  const a = taoPhanDoan(0, 2, "Xin chào");
  const b = taoPhanDoan(2, 4, "thế giới");
  const ra = gopVoiPhanDoanSau([a, b], a.id);
  assert.equal(ra.length, 1);
  assert.equal(ra[0].start, 0);
  assert.equal(ra[0].end, 4);
  assert.equal(ra[0].text, "Xin chào thế giới");
});

test("gopVoiPhanDoanSau o phan doan cuoi khong lam gi", () => {
  const a = taoPhanDoan(0, 2, "a");
  const ra = gopVoiPhanDoanSau([a], a.id);
  assert.equal(ra.length, 1);
});

test("xoaPhanDoan bo dung mot phan tu", () => {
  const a = taoPhanDoan(0, 1, "a");
  const b = taoPhanDoan(1, 2, "b");
  const ra = xoaPhanDoan([a, b], a.id);
  assert.equal(ra.length, 1);
  assert.equal(ra[0].id, b.id);
});

test("suaVanBan/suaThoiGian khong bien dang phan doan khac", () => {
  const a = taoPhanDoan(0, 1, "a");
  const b = taoPhanDoan(1, 2, "b");
  const ra1 = suaVanBan([a, b], a.id, "A moi");
  assert.equal(ra1[0].text, "A moi");
  assert.equal(ra1[1].text, "b");
  const ra2 = suaThoiGian([a, b], b.id, "end", 5);
  assert.equal(ra2[1].end, 5);
  assert.equal(ra2[0].end, 1);
});

test("xuatSrt dung dinh dang chuan, bo qua doan rong", () => {
  const a = taoPhanDoan(0, 1.5, "Xin chào");
  const rong = taoPhanDoan(1.5, 2, "   ");
  const b = taoPhanDoan(2, 3, "Thế giới");
  const srt = xuatSrt([a, rong, b]);
  assert.equal(
    srt,
    "1\n00:00:00,000 --> 00:00:01,500\nXin chào\n\n" +
    "2\n00:00:02,000 --> 00:00:03,000\nThế giới\n",
  );
});

test("xuatVtt bat dau bang WEBVTT", () => {
  const a = taoPhanDoan(0, 1, "x");
  const vtt = xuatVtt([a]);
  assert.match(vtt, /^WEBVTT\n\n/);
  assert.match(vtt, /00:00:00\.000 --> 00:00:01\.000/);
});

test("nhap lai chinh SRT vua xuat ra dung du lieu (round-trip)", () => {
  const a = taoPhanDoan(0, 1.5, "Xin chào");
  const b = taoPhanDoan(2, 3, "Thế giới");
  const srt = xuatSrt([a, b]);
  const lai = nhapSrtHoacVtt(srt);
  assert.equal(lai.length, 2);
  assert.equal(lai[0].text, "Xin chào");
  assert.equal(lai[0].start, 0);
  assert.equal(lai[0].end, 1.5);
  assert.equal(lai[1].text, "Thế giới");
});

test("nhap lai chinh VTT vua xuat ra dung du lieu (round-trip)", () => {
  const a = taoPhanDoan(0, 1.5, "Xin chào");
  const vtt = xuatVtt([a]);
  const lai = nhapSrtHoacVtt(vtt);
  assert.equal(lai.length, 1);
  assert.equal(lai[0].text, "Xin chào");
});

test("nhap chuoi rong tra mang rong, khong nem loi", () => {
  assert.deepEqual(nhapSrtHoacVtt(""), []);
  assert.deepEqual(nhapSrtHoacVtt("   \n\n  "), []);
});

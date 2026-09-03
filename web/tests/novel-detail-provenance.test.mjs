/*
 * Trang chi tiet truyen (`/novels/[id]`) — GHI CONG NGUON va TIEN DO TAC PHAM.
 *
 * Kho nay chua fanfic NHAP tu noi khac (Wattpad, Fandom wiki, docln...), va
 * backend luon tra ve `external_author_name` / `external_source_url` /
 * `language` / `external_chapter_count` / `status`. Trang nay truoc day KHONG
 * ve mot truong nao trong so do — nguoi doc khong thay ai la tac gia goc, khong
 * co duong ve nguon, va khong biet truyen dang ra hay da hoan thanh.
 *
 * Voi mot san pham dung noi dung cua nguoi khac, ghi cong nguon khong phai
 * "metadata cho dep". Test nay khoa lai de no khong bien mat trong mot lan don
 * dep giao dien.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(
  new URL("../src/app/novels/[id]/page.tsx", import.meta.url),
  "utf8",
);
const codeOnly = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const code = codeOnly(src);

test("hien ten tac gia goc va duong ve nguon", () => {
  assert.match(code, /novel\.external_author_name/,
    "khong ve ten tac gia goc");
  assert.match(code, /novel\.external_source_url/,
    "khong ve duong ve nguon");
  assert.match(code, /Tác giả gốc/, "thieu nhan 'Tác giả gốc'");
});

test("lien ket ra ngoai phai an toan: noopener + noreferrer + nofollow", () => {
  const the = code.match(/<a\s+[\s\S]*?href=\{novel\.external_source_url\}[\s\S]*?\/?>/);
  assert.ok(the, "khong tim thay the <a> cho external_source_url");
  for (const canCo of ["noopener", "noreferrer", "nofollow"]) {
    assert.match(the[0], new RegExp(canCo),
      `lien ket ngoai thieu rel=${canCo}`);
  }
  assert.match(the[0], /target="_blank"/,
    "lien ket ngoai nen mo tab moi de khong day nguoi doc ra khoi truyen");
});

test("tien do tac pham (`status`) TACH khoi trang thai xuat ban (`state`)", () => {
  // Hai khai niem khac nhau: mot truyen da HOAN THANH van co the la BAN NHAP.
  assert.match(code, /novel\.status/, "khong ve tien do tac pham");
  assert.match(code, /nhanTienDo/, "thieu ham doi `status` sang nhan tieng Viet");
  // Badge cu ve state phai con nguyen.
  assert.match(code, /novel\.state === "published"/,
    "mat badge trang thai xuat ban ban dau");
});

test("`status` la lạ thi hien NGUYEN VAN, khong bi nuot", () => {
  // Backend co the them trang thai moi truoc frontend; giau di thi te hon la
  // hien dung chu cua backend.
  assert.match(code, /NHAN_TIEN_DO\[status\]\s*\?\?\s*status/,
    "gia tri khong co trong bang phai duoc tra ve nguyen van");
});

test("so chuong nguon KHAC so chuong dang co thi phai noi ro", () => {
  assert.match(code, /novel\.external_chapter_count\s*>\s*0/,
    "phai bo qua khi nguon khong cong bo so chuong");
  assert.match(
    code,
    /novel\.external_chapter_count\s*!==\s*chapters\.length/,
    "chi hien khi hai con so THUC SU lech nhau",
  );
});

test("tong hop trang thai audio khong ton them request", () => {
  assert.match(code, /chapters\.filter\(\(c\)\s*=>\s*c\.has_audio\)/,
    "phai dem tu `has_audio` da co san trong danh sach chuong");
  // Mot request duy nhat cho ca trang — giu nguyen bat bien cu cua tep nay.
  const soLanGoi = (code.match(/api\.get/g) || []).length;
  assert.equal(soLanGoi, 1,
    "trang chi tiet truyen chi duoc goi API MOT lan (xem ghi chu o fetchNovel)");
});

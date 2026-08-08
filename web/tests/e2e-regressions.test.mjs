// Regression cho cac loi do luot E2E day du phat hien ra.
//
// Moi test o day deu bat nguon tu mot hien tuong quan sat duoc tren trinh duyet
// that, khong phai tu suy doan. Comment ghi lai buoc tai hien de nguoi doc sau
// nay hieu vi sao rang buoc nay ton tai.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const studio = readFileSync(
  new URL("../src/app/studio/page.tsx", import.meta.url), "utf8");

/*
 * LOI 1 — /studio ket o "Dang xu ly" sau khi tai lai trang giua luc job chay.
 *
 * Tai hien: tao audio o /studio, refresh trang khi job con `running`, roi cho.
 * Job hoan tat tren backend nhung the trong "Lich su audio" van hien "Dang xu
 * ly" mai — do bang chung: sau refresh trinh duyet chi goi `/api/jobs` DUNG MOT
 * LAN roi thoi.
 *
 * Nguyen nhan: `activeJob` chi duoc dat trong ham submit, nen sau khi tai lai
 * trang no la `null`; effect poll bat dau bang `if (!activeJob) ... return` nen
 * thoat ngay va khong bao gio hoi lai backend.
 */
test("job dang chay tu phien truoc duoc nap lai de vong poll tiep tuc", () => {
  const i = studio.indexOf("setJobs(jobList.jobs)");
  assert.ok(i > 0, "khong tim thay cho nap danh sach job luc khoi tao");

  // Doan ngay sau khi nap danh sach phai tim job chua ket thuc va dat lam
  // `activeJob`. Chi xet 900 ky tu ke tiep de rang buoc that su noi ve CHO NAY.
  const sau = studio.slice(i, i + 900);
  assert.match(sau, /jobList\.jobs\.find\(/,
    "phai do trong danh sach vua nap xem con job nao chua ket thuc");
  assert.match(sau, /"pending"/, "job dang xep hang cung phai duoc theo doi tiep");
  assert.match(sau, /"running"/, "job dang chay phai duoc theo doi tiep");
  assert.match(sau, /setActiveJob\(/,
    "phai dat lai `activeJob`, neu khong vong poll khong bao gio chay");
});

test("nap lai khong duoc de len job nguoi dung dang theo doi", () => {
  const i = studio.indexOf("jobList.jobs.find(");
  const sau = studio.slice(i, i + 400);
  // `current ?? dangChay` — giu nguyen job hien tai neu da co. Neu ghi de vo
  // dieu kien, mot lan `load()` xen vao se keo nguoi dung ve job khac.
  assert.match(sau, /setActiveJob\(\(current\) => current \?\? /,
    "chi dat khi chua theo doi job nao");
});

test("vong poll van dung o trang thai ket thuc", () => {
  // Khong duoc "sua" bang cach poll mai mai. Dieu kien dung phai con nguyen.
  assert.match(studio,
    /if \(!activeJob \|\| activeJob\.status === "completed" \|\| activeJob\.status === "failed"\)/,
    "job da ket thuc thi phai ngung poll");
});


/*
 * LOI 3 — "Dang xuat" khong ket thuc phien o phia may chu.
 *
 * Tai hien tren staging that: dang nhap, bam Dang xuat, roi dung lai chinh
 * token do goi `GET /api/auth/me` — van tra 200.
 *
 * Nguyen nhan: `signOut` chi goi `setToken(null)` (xoa localStorage). Backend
 * khong co route logout nao, va session secret cua Appwrite van song nguyen.
 *
 * Hau qua: tren may dung chung, "dang xuat" khong bao ve duoc gi.
 */
const session = readFileSync(
  new URL("../src/lib/session.tsx", import.meta.url), "utf8");
const apiSrc = readFileSync(
  new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("lop api co ham logout goi dung endpoint", () => {
  assert.match(apiSrc, /logout:/, "phai co api.logout");
  assert.match(apiSrc, /"\/api\/auth\/logout"/, "phai goi dung duong");
  const i = apiSrc.indexOf("/api/auth/logout");
  assert.match(apiSrc.slice(Math.max(0, i - 200), i + 120), /method:\s*"POST"/,
    "logout phai la POST");
});

test("signOut goi may chu chu khong chi xoa token cuc bo", () => {
  const i = session.indexOf("const signOut");
  assert.ok(i > 0, "khong tim thay signOut");
  const than = session.slice(i, i + 800);
  assert.match(than, /api\.logout\(\)/,
    "signOut phai bao may chu huy phien, khong chi setToken(null)");
  assert.match(than, /setToken\(null\)/, "van phai xoa token cuc bo");
});

test("loi mang khong giu nguoi dung o trang thai da dang nhap", () => {
  const i = session.indexOf("const signOut");
  const than = session.slice(i, i + 800);
  // `finally` la diem mau chot: goi may chu that bai thi van phai dang xuat o
  // client, neu khong nut Dang xuat se im lang khong lam gi.
  assert.match(than, /finally\s*\{/,
    "phai don phia client trong finally");
  const viTriFinally = than.indexOf("finally");
  const viTriSetToken = than.indexOf("setToken(null)");
  assert.ok(viTriSetToken > viTriFinally,
    "setToken(null) phai nam trong finally");
});

test("signOut duoc khai bao la bat dong bo trong kieu", () => {
  assert.match(session, /signOut:\s*\(\)\s*=>\s*Promise<void>/,
    "kieu phai phan anh viec no goi mang");
});

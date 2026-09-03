/*
 * Trang doc chuong (`/chapters/[id]`) — DIEU HUONG CHUONG TRUOC / CHUONG SAU.
 *
 * Ban truoc CO Y khong co hai cai nut nay; ghi chu trong tep con noi ro ly do
 * ("trang Nghe da co roi, trang doc chi can dan ve trang truyen"). Do la mot
 * quyet dinh sai voi nguoi DOC: doc xong mot chuong roi phai quay ve muc luc,
 * do lai xem vua doc chuong nao, rồi bam chuong ke tiep — ba thao tac cho mot
 * viec dang le la mot cai bam, va tren dien thoai con phai cuon muc luc.
 *
 * Test nay khoa lai CA BA dieu de lan sau khong ai lang le thao ra:
 *   1. co lien ket chuong truoc + chuong sau, tro tung dung `/chapters/{id}`;
 *   2. hai dau truyen KHONG hien nut chet (chuong dau khong co "truoc",
 *      chuong cuoi khong co "sau");
 *   3. danh sach chuong lay theo kieu khong lam hong viec doc — `getNovel`
 *      that bai thi mat nut, KHONG phai mat ca chuong.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(
  new URL("../src/app/chapters/[id]/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("../src/app/globals.css", import.meta.url),
  "utf8",
);

const codeOnly = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const code = codeOnly(src);

test("co lien ket chuong TRUOC va chuong SAU, ca hai tro toi /chapters/{id}", () => {
  for (const bien of ["chuongTruoc", "chuongSau"]) {
    assert.match(code, new RegExp(`${bien}\\s*\\?`),
      `thieu nhanh dieu kien cho ${bien}`);
    assert.match(
      code,
      new RegExp(`href=\\{\`/chapters/\\$\\{${bien}\\.chapter_id\\}\`\\}`),
      `${bien} phai dan toi /chapters/{chapter_id}`,
    );
  }
  // `rel` prev/next: khong phai trang tri — trinh duyet va cong cu doc man
  // hinh dung no de hieu day la mot chuoi trang co thu tu.
  assert.match(code, /rel="prev"/, "thieu rel=prev");
  assert.match(code, /rel="next"/, "thieu rel=next");
});

test("chuong dau/cuoi khong sinh ra nut chet", () => {
  // Chi so -1 (khong tim thay) cung phai coi nhu khong co chuong truoc/sau.
  assert.match(code, /chuongTruoc:\s*i\s*>\s*0\s*\?/,
    "chuong truoc phai yeu cau i > 0 (chuong dau khong co truoc)");
  assert.match(code, /chuongSau:\s*i\s*>=\s*0\s*&&\s*i\s*<\s*ds\.length\s*-\s*1\s*\?/,
    "chuong sau phai yeu cau i >= 0 VA i < length-1 (chuong cuoi khong co sau)");
  // Het truyen thi noi ro, khong de mot cho trong khong giai thich.
  assert.match(code, /Hết chương hiện có/,
    "thieu trang thai 'het chuong' o cuoi truyen");
});

test("danh sach chuong KHONG duoc phep lam hong viec doc", () => {
  // `getNovel` that bai -> mang rong -> mat hai cai nut, chu van hien.
  assert.match(
    code,
    /api\s*\n?\s*\.getNovel\([\s\S]{0,200}?\.catch\(\(\)\s*=>\s*\[\]/,
    "getNovel phai co .catch tra ve mang rong, khong duoc de loi noi len",
  );
});

test("van giu duong ve trang truyen (khong thay the, chi them)", () => {
  assert.match(code, /href=\{`\/novels\/\$\{novel\.novel_id\}`\}/,
    "mat duong ve danh sach chuong cua truyen");
  assert.match(code, /Danh sách chương/, "mat nhan 'Danh sách chương'");
});

test("khong goi API mot lan moi chuong de dung dieu huong", () => {
  // DUNG hai request bat ke truyen bao nhieu chuong: getChapter + getNovel.
  const soLanGetNovel = (code.match(/api\s*\n?\s*\.getNovel\(/g) || []).length;
  assert.equal(soLanGetNovel, 1,
    "chi duoc goi getNovel MOT lan; goi trong vong lap la N+1");
  assert.doesNotMatch(code, /chapters\.map\([\s\S]{0,120}api\./,
    "khong duoc goi API ben trong vong lap chuong");
});

test("tren dien thoai: TRUOC va SAU phai dung CHUNG hang dau", () => {
  /*
    Loi that, do duoc o 390px truoc khi sua: chi dat `grid-column: 1 / -1` cho
    muc luc thi luoi hai cot xep thanh BA hang — "Chương trước" mot minh mot
    hang, muc luc mot hang, "Chương sau" mot hang nua — vi muc luc nam GIUA
    trong DOM va cat ngang giua hai nut.

    Cach sua la `order`, khong phai doi thu tu DOM: o desktop muc luc nam giua
    la dung ca ve thi giac lan ve ban phim/trinh doc man hinh.
  */
  const mobile = css.match(/@media \(max-width: 640px\)([\s\S]*?)\n\}/);
  assert.ok(mobile, "khong tim thay khoi @media 640px");
  const block = mobile[1];
  assert.match(block, /\.reader-nav-prev\s*\{\s*order:\s*1/,
    "chuong truoc phai co order 1");
  assert.match(block, /\.reader-nav-next\s*\{\s*order:\s*2/,
    "chuong sau phai co order 2 — cung hang voi chuong truoc");
  assert.match(block, /\.reader-nav-up\s*\{[\s\S]*?order:\s*3/,
    "muc luc phai bi day xuong hang duoi (order 3)");
  // Trang thai "het truyen" thay cho o cua nut SAU, nen phai cung order.
  assert.match(block, /\.reader-nav-end\s*\{\s*order:\s*2/,
    "'het chuong' phai chiem dung o cua chuong sau (order 2)");
});

test("tren dien thoai: hai nut dat nguong bam va ten chuong khong chen cho", () => {
  // Muc luc xuong hang rieng, hai nut chia doi hang tren.
  assert.match(css, /\.reader-nav\s*\{[\s\S]*?grid-template-columns/,
    "reader-nav phai la grid de hai nut giu be rong bang nhau");
  assert.match(css, /\.reader-nav-title\s*\{\s*display:\s*none/,
    "o be man hinh hep, ten chuong phai an de tra cho cho nhan");
  assert.match(css, /min-height:\s*44px/,
    "nut dieu huong tren dien thoai phai dat nguong bam 44px");
  assert.match(css, /\.reader-nav-up\s*\{[\s\S]*?grid-column:\s*1\s*\/\s*-1/,
    "muc luc phai chiem ca be rong o hang rieng tren dien thoai");
});

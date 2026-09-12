/*
 * Khu KIEM DUYET TRUYEN — danh sach + trang doc/duyet.
 *
 * Cac bai o day quet MA NGUON, cung kieu voi phan con lai cua `web/tests/`.
 * Chung khong chung minh duoc giao dien dep, nhung chung chung minh duoc
 * nhung dieu co the sai mot cach IM LANG — va ba trong so do da sai that:
 *
 *   1. danh sach lien ket toi `/novels/{id}`, ma duong do tra 404 cho MOI ban
 *      nhap — tuc la cho dung nhung dong nguoi quan tri can mo nhat;
 *   2. bang dem ca kho chua Audio Studio nhu truyen cho duyet (43 thay vi 11);
 *   3. khong co duong nao doc duoc noi dung truoc khi bam xuat ban.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const danhSach = () => read("../src/app/admin/stories/page.tsx");
const chiTiet = () => read("../src/app/admin/stories/[id]/page.tsx");
const api = () => read("../src/lib/api.ts");

/* ===================================================== route co that */

test("route trang duyet MOT tac pham ton tai", () => {
  assert.ok(existsSync(new URL("../src/app/admin/stories/[id]/page.tsx",
                               import.meta.url)));
});

/* ========================================================== danh sach */

test("danh sach tro toi trang DUYET, khong tro toi duong cong khai", () => {
  const src = danhSach();
  assert.match(src, /href=\{`\/admin\/stories\/\$\{n\.novel_id\}`\}/,
    "tên truyện không dẫn tới trang duyệt");
  assert.ok(!/href=\{`\/novels\/\$\{n\.novel_id\}`\}/.test(src),
    "vẫn dẫn tới /novels/{id} — trả 404 với mọi bản nháp");
});

test("mac dinh CHI hien tac pham, khong hien ha tang", () => {
  const src = danhSach();
  assert.match(src, /useState\(true\)/, "mặc định không phải 'chỉ tác phẩm'");
  assert.match(src, /chiTacPham \? "story" : ""/,
    "không truyền kind xuống API");
  // Van xem duoc ha tang khi can — bo loc, khong phai an vinh vien.
  assert.match(src, /Tất cả bản ghi/);
});

test("loai ban ghi do BACKEND quyet dinh, giao dien khong tu doan tu tags", () => {
  const src = danhSach();
  assert.ok(!/tags\.includes\(["']audio-studio["']\)/.test(src),
    "giao diện tự phân loại lại — sẽ lệch với server/novel_kind.py");
  assert.match(src, /n\.kind/, "không dùng trường `kind` của backend");
});

/* =========================================================== chi tiet */

test("trang duyet DOC duoc noi dung chuong", () => {
  const src = chiTiet();
  assert.match(src, /adminApi\.novel\(novelId\)/);
  assert.match(src, /c\.content/, "không hiển thị nội dung chương");
  assert.match(src, /Đọc toàn văn/, "không có đường đọc hết");
});

test("trang duyet hien du sieu du lieu de RA QUYET DINH", () => {
  const src = chiTiet();
  for (const truong of [
    "external_author_name",   // tác giả nguồn
    "external_source_url",    // xuất xứ
    "cover_url",              // ảnh bìa
    "total_chars",            // tổng độ dài
    "tags",
    "owner",
    "updated_at",
  ]) {
    assert.ok(src.includes(truong), `thiếu ${truong}`);
  }
});

test("co ca XUAT BAN lan GO XUONG, va deu hoi xac nhan", () => {
  const src = chiTiet();
  assert.match(src, /adminApi\.publishNovel\(novelId\)/);
  assert.match(src, /adminApi\.unpublishNovel\(novelId\)/);
  // Hai hop thoai xac nhan — khong bam nham mot phat ra cong chung.
  assert.ok((src.match(/<ConfirmDialog/g) ?? []).length >= 2,
    "thiếu hộp thoại xác nhận");
});

test("KHONG cho xuat ban mot trang trong", () => {
  const src = chiTiet();
  // `chapters.length` chua du: 13 truyen dang song deu co dung mot chuong VA
  // `char_count === 0`. Phai dem chuong CO CHU.
  assert.match(src, /c\.content\.trim\(\)\.length > 0/,
    "không đếm chương có chữ");
  assert.match(src, /disabled=\{dangChay \|\| soChuongCoChu === 0\}/,
    "nút Xuất bản không bị khoá khi không có nội dung");
});

test("co trang thai tai / loi / rong", () => {
  const src = chiTiet();
  assert.match(src, /dangTai=\{loading\}/);
  assert.match(src, /loi=\{error\}/);
  assert.match(src, /rong=\{!data\}/);
  assert.match(src, /onThuLai=\{reload\}/);
});

test("loi tu may chu duoc hien ra, khong nuot", () => {
  const src = chiTiet();
  assert.match(src, /toast\.error\(errorMessage\(cause\)\)/);
});

/* ============================================================== client */

test("adminApi co du bon thao tac kiem duyet", () => {
  const src = api();
  for (const ten of ["novel:", "publishNovel:", "unpublishNovel:",
                     "updateNovelMeta:"]) {
    assert.ok(src.includes(ten), `adminApi thiếu ${ten}`);
  }
  // `kind` phai di xuong API, neu khong bo loc chi la trang tri.
  assert.match(src, /kind = ""/);
  assert.match(src, /&kind=\$\{kind\}/);
});

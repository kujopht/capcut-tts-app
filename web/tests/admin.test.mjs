/*
 * KHU QUAN TRI o phia giao dien.
 *
 * Dieu quan trong nhat ma bo test nay giu: GIAO DIEN KHONG BAO GIO LA NOI QUYET
 * DINH. Khong mot bien `isAdmin` nao trong trang thai React duoc phep quyet dinh
 * ai thay gi — cong chan hoi MAY CHU, va may chu tra 401/403/200.
 *
 * Mot cach lam sai rat de viet va rat kho phat hien: doc `profile.is_admin` roi
 * `if (!isAdmin) return <TuChoi/>`. Cach do "hoat dong" tren man hinh, nhung du
 * lieu VAN da ve trinh duyet truoc do — chi la khong ve ra. Cac bai duoi day
 * chan chinh hinh dang do.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");
const shell = () => read("../src/components/AdminShell.tsx");
const api = () => read("../src/lib/api.ts");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** Moi trang duoi `/admin`. */
function trangAdmin() {
  const goc = new URL("../src/app/admin/", import.meta.url);
  return readdirSync(goc, { recursive: true })
    .filter((f) => typeof f === "string" && f.endsWith("page.tsx"))
    .map((f) => `../src/app/admin/${f.split("\\").join("/")}`);
}

/* ==================================================== cong chan */

test("cong chan hoi MAY CHU, khong doc mot co trong trang thai", () => {
  const src = codeOnly(shell());
  assert.match(src, /adminApi\.overview\(\)/,
    "cổng chặn không gọi máy chủ");
  // Khong duoc co mot co `is_admin` / `isAdmin` nao ca — ke ca doc tu ho so.
  assert.ok(!/is_?[Aa]dmin/.test(src),
    "giao diện tự quyết định ai là quản trị");
});

test("MOI trang admin nam duoi mot layout co cong chan", () => {
  /*
    Dat cong o layout chu khong o tung trang: mot trang moi duoc them ma quen goi
    cong se la mot trang khong duoc bao ve, va do la loai loi khong ai phat hien
    cho toi khi da muon.
  */
  const layout = read("../src/app/admin/layout.tsx");
  assert.match(layout, /<AdminShell>/);

  const trang = trangAdmin();
  assert.ok(trang.length >= 5, `chỉ tìm thấy ${trang.length} trang admin`);
  for (const t of trang) {
    // Khong trang nao duoc tu ve mot cong rieng — chung phai dua vao layout.
    assert.ok(!read(t).includes("<AdminShell"),
      `${t} tự bọc cổng chặn thay vì dùng layout`);
  }
});

test("man tu choi PHAN BIET chua dang nhap voi khong co quyen", () => {
  // Mot nguoi quan tri that go nham tai khoan can hieu vi sao khong vao duoc.
  const src = shell();
  assert.match(src, /cần đăng nhập/i);
  assert.match(src, /không có quyền quản trị/i);
});

test("moi ham API quan tri deu nam duoi /api/admin/", () => {
  const src = api();
  const at = src.indexOf("export const adminApi");
  assert.notEqual(at, -1, "thiếu adminApi");
  const than = src.slice(at);
  const duong = [...than.matchAll(/request<[^>]*>\(\s*`?"?(\/api\/[^`"?]+)/g)]
    .map((m) => m[1]);
  assert.ok(duong.length >= 8, `chỉ thấy ${duong.length} đường`);
  for (const d of duong) {
    assert.ok(d.startsWith("/api/admin/"), `${d} không nằm trong khu quản trị`);
  }
});

/* ==================================================== trang thai danh sach */

test("MOI trang admin deu ve du ba trang thai tai/loi/rong", () => {
  /*
    Ba trang thai nay duoc gom vao MOT component co y: moi trang tu viet ba
    nhanh thi se co mot trang quen mot nhanh, va cai bi quen luon la "loi".
  */
  for (const t of trangAdmin()) {
    const src = read(t);
    if (t.endsWith("admin/page.tsx")) {
      // Bang tong quan cung dung chung component do.
      assert.match(src, /DanhSachTrangThai/, t);
      continue;
    }
    assert.match(src, /DanhSachTrangThai/, `${t} không vẽ đủ ba trạng thái`);
  }

  const src = shell();
  assert.match(src, /if \(dangTai\) return <Loading/);
  assert.match(src, /role="alert"/, "trạng thái lỗi không được báo cho trình đọc");
  assert.match(src, /role="status"/, "trạng thái rỗng không được báo");
});

/* ==================================================== hanh dong han che */

test("hai thao tac HAN CHE deu phai xac nhan", () => {
  const donSrc = read("../src/app/admin/authors/applications/page.tsx");
  const tgSrc = read("../src/app/admin/authors/page.tsx");
  assert.match(donSrc, /<ConfirmDialog/, "từ chối đơn không hỏi xác nhận");
  assert.match(tgSrc, /<ConfirmDialog/, "tạm dừng tác giả không hỏi xác nhận");

  // Duyet thi KHONG can xac nhan: no mo mot canh cua, khong dong cai nao.
  const at = donSrc.indexOf("async function duyet");
  const than = donSrc.slice(at, donSrc.indexOf("async function tuChoi"));
  assert.ok(!than.includes("setHoi"), "duyệt cũng bắt xác nhận — thừa");
});

test("tu choi KHONG gui duoc khi chua co ghi chu", () => {
  // Mot lan tu choi khong ly do la mot cai cua dong im lang. Backend cung chan,
  // day chi la lop thu hai de nguoi duyet biet truoc khi bam.
  const src = read("../src/app/admin/authors/applications/page.tsx");
  assert.match(src, /disabled=\{dangGui \|\| !ghiChu\.trim\(\)\}/);
});

test("giao dien noi RO treo KHONG xoa gi", () => {
  /*
    Day la thu de bi hieu nham nhat trong ca khu quan tri, va hau qua cua viec
    hieu nham la khong sua duoc. No phai duoc viet ra o CA hai cho: bang danh
    sach, va hop xac nhan.
  */
  const src = read("../src/app/admin/authors/page.tsx");
  assert.match(src, /Truyện đã xuất bản vẫn\s*\n?\s*công khai/);
  assert.match(src, /không bị\s*\n?\s*xoá/);
  const at = src.indexOf("<ConfirmDialog");
  assert.match(src.slice(at), /bản nháp và audio không bị xoá/);
});

test("KHONG co nut xoa truyen o khu quan tri", () => {
  // Backend chua co luong takedown an toan; mot cai nut o day se di truoc thiet ke.
  const src = codeOnly(read("../src/app/admin/stories/page.tsx"));
  assert.ok(!/xo[áa]|delete|remove|takedown/i.test(src),
    "khu duyệt truyện có thao tác phá huỷ");
  assert.ok(!api().includes("/api/admin/novels/"),
    "API quản trị có đường ghi lên truyện");
});

/* ==================================================== rieng tu */

test("email CHI xuat hien o khu quan tri", () => {
  /*
    Doi chieu hai duong canh nhau — day la cho de lech nhat. `PublicProfile`
    khong duoc co truong `email`, con `AdminUser` thi phai co.
  */
  const src = api();
  const congKhai = src.slice(src.indexOf("export interface PublicProfile"),
                             src.indexOf("}", src.indexOf("export interface PublicProfile")));
  assert.ok(!congKhai.includes("email"), "hồ sơ công khai có email");

  const quanTri = src.slice(src.indexOf("export interface AdminUser"),
                            src.indexOf("}", src.indexOf("export interface AdminUser")));
  assert.match(quanTri, /email: string/);
});

test("nhat ky kiem duyet KHONG co duong ghi tu giao dien", () => {
  // Chi THEM, va chi o phia may chu. Mot nhat ky sua duoc la mot nhat ky khong
  // dung de lam gi.
  const src = api();
  const at = src.indexOf("  events:");
  const than = src.slice(at, at + 260);
  assert.ok(!/method: "POST"|method: "PUT"|method: "DELETE"/.test(than));
});

/* ==================================================== hinh thuc */

test("nhan trang thai kiem duyet co mau co dinh va KHAC hang tac gia", () => {
  /*
    Hang la uy tin, trang thai la quyen. Ve chung giong nhau la moi nguoi doc
    bang nham hai thu — va nham o mot bang quan tri la nham mot quyet dinh.
  */
  const text = css();
  for (const lop of ["tt-cho", "tt-duyet", "tt-tuchoi", "tt-treo"]) {
    assert.ok(text.includes(`.${lop}`), `thiếu nhãn ${lop}`);
  }
  // Nhan trang thai KHONG duoc dung lop cua huy hieu hang.
  const at = text.indexOf(".tt-cho");
  const khoi = text.slice(at, at + 600);
  assert.ok(!khoi.includes("hh-hang"), "hai hệ nhãn dùng chung lớp");
});

test("khu quan tri KHONG co hat sang hay hoa van goc", () => {
  // Day la mot be mat lam viec. Xem ghi chu o dau khoi CSS.
  const text = css();
  const at = text.indexOf(".admin-page");
  const khoi = text.slice(at);
  assert.ok(!/canh-troi|\.hat\b/.test(khoi.slice(0, 4000)),
    "khu quản trị có hiệu ứng nền");

  // Va `/admin` khong nam tren truc chuyen canh — no khong phai mot khu vuc cua
  // the gioi truyen.
  const sections = read("../src/lib/sections.ts");
  assert.ok(!sections.includes('"/admin'), "/admin bị đưa vào trục chuyển cảnh");
});

test("bang cuon trong khung RIENG, khong day ca trang rong ra", () => {
  // Mot bang sau cot khong ep vua 390px duoc. De no day trang rong ra thi moi
  // trang khac cung tran theo — da do duoc loi do o cac ban truoc.
  const text = css();
  const at = text.indexOf(".admin-bang-boc {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /overflow-x: auto/);
});

test("dieu huong quan tri gap lai o mobile", () => {
  const text = css();
  const than = text.slice(text.indexOf("@media (max-width: 900px)"));
  assert.match(than, /\.admin-khung \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(than, /\.admin-doi \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});

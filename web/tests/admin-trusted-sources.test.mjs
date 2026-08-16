/**
 * Admin Control Center V2, Phase 5 — Trusted Video Sources + Import Queue.
 *
 * Cung phong cach voi `admin-animation-moderation.test.mjs`: doc THANG
 * source va khang dinh cac dac diem quan trong bang regex, khong dung DOM
 * gia lap.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  // Chuan hoa CRLF -> LF: checkout that tren Windows (core.autocrlf=true)
  // co the ghi CRLF cho file nguon, lam mot vai khang dinh so khop chuoi
  // con CHINH XAC (bao gom \n nhung) that bai du JSX khong doi gi ca — day
  // la do khac biet dong ket thuc dong, khong phai loi noi dung.
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8")
    .replace(/\r\n/g, "\n");
}

const api = () => read("../src/lib/api.ts");
const shell = () => read("../src/components/AdminShell.tsx");
const list = () => read("../src/app/admin/animation/sources/page.tsx");
const themMoi = () => read("../src/app/admin/animation/sources/new/page.tsx");
const chiTiet = () => read("../src/app/admin/animation/sources/[id]/page.tsx");
const hangDoi = () => read("../src/app/admin/animation/import-queue/page.tsx");

// -- lop api ------------------------------------------------------------

test("adminApi: cac ham Trusted Sources goi dung duong /api/admin/animation/sources*", () => {
  const src = api();
  assert.match(src, /previewTrustedSourceUrl:[\s\S]{0,600}"\/api\/admin\/animation\/sources\/preview"/);
  assert.match(src, /trustedSources:[\s\S]{0,600}\/api\/admin\/animation\/sources\?/);
  assert.match(src, /createTrustedSource:[\s\S]{0,600}"\/api\/admin\/animation\/sources"/);
  assert.match(src, /trustedSourceDetail:[\s\S]{0,600}\/api\/admin\/animation\/sources\/\$\{encodeURIComponent\(sourceId\)\}`/);
  assert.match(src, /updateTrustedSource:[\s\S]{0,600}method: "PATCH"/);
  assert.match(src, /setTrustedSourceEnabled:[\s\S]{0,600}\/enabled`/);
  assert.match(src, /removeTrustedSource:[\s\S]{0,600}method: "DELETE"/);
  assert.match(src, /scanTrustedSource:[\s\S]{0,600}\/scan`/);
});

test("adminApi: mapping va import queue goi dung duong /api/admin/animation/mappings|imports", () => {
  const src = api();
  assert.match(src, /createSeriesMapping:[\s\S]{0,600}\/mappings`/);
  assert.match(src, /updateSeriesMapping:[\s\S]{0,600}\/api\/admin\/animation\/mappings\//);
  assert.match(src, /removeSeriesMapping:[\s\S]{0,600}method: "DELETE"/);
  assert.match(src, /videoImports:[\s\S]{0,600}\/api\/admin\/animation\/imports\?/);
  assert.match(src, /setImportSeries:[\s\S]{0,600}\/series`/);
  assert.match(src, /importVideo:[\s\S]{0,600}\/import`/);
  assert.match(src, /rejectVideoImport:[\s\S]{0,600}\/reject`/);
  assert.match(src, /ignoreVideoImport:[\s\S]{0,600}\/ignore`/);
});

test("Kieu TrustedSource/VideoImport khong bao gio nhac toi API key", () => {
  const seriesAt = api().indexOf("export interface TrustedSource {");
  const doan = api().slice(seriesAt, seriesAt + 900);
  assert.ok(!/api_key|apiKey|youtube_api_key/i.test(doan),
    "kiểu TrustedSource lộ trường liên quan tới API key");
});

// -- dieu huong -----------------------------------------------------------

test("AdminShell: muc Trusted Sources va Import Queue van tro dung duong", () => {
  const src = shell();
  assert.match(src, /href: "\/admin\/animation\/sources", nhan: "Trusted Sources"/);
  assert.match(src, /href: "\/admin\/animation\/import-queue", nhan: "Import Queue"/);
});

// -- danh sach nguon --------------------------------------------------------

test("Danh sach nguon: khong con la placeholder AdminSapXayDung", () => {
  const src = list();
  assert.ok(!src.includes("AdminSapXayDung"), "trang danh sách vẫn là placeholder");
  assert.match(src, /adminApi\.trustedSources\(/);
  assert.match(src, /href="\/admin\/animation\/sources\/new"/);
});

test("Danh sach nguon: mot video tac gia thuong KHONG the tu bien kenh thanh tin cay (chi thich)", () => {
  const src = list();
  assert.match(src, /KHÔNG BAO GIỜ tự biến/);
});

// -- them nguon moi -----------------------------------------------------

test("Them nguon: BAT BUOC xem truoc truoc khi co nut xac nhan tao", () => {
  const src = themMoi();
  assert.match(src, /adminApi\.previewTrustedSourceUrl/);
  assert.match(src, /adminApi\.createTrustedSource/);
  // Nut "Them lam nguon tin cay" CHI xuat hien BEN TRONG nhanh JSX `{xem ?
  // (...)}` — khong co duong tao thang tu URL ma bo qua buoc xem truoc.
  const batDau = src.indexOf("{xem ? (");
  const ketThuc = src.indexOf(") : null}\n          </DanhSachTrangThai>");
  assert.ok(batDau > 0 && ketThuc > batDau, "không tìm thấy nhánh JSX {xem ? (...)}");
  const nhanhXem = src.slice(batDau, ketThuc);
  assert.match(nhanhXem, /onClick={xacNhanThem}/);
  assert.match(nhanhXem, /Thêm làm nguồn tin cậy/);
});

test("Them nguon: 503 (chua cau hinh key) hien ChuaCauHinh, khong phai loi chung", () => {
  const src = themMoi();
  assert.match(src, /cause\.status === 503/);
  assert.match(src, /<ChuaCauHinh/);
});

// -- chi tiet nguon -------------------------------------------------------

test("Chi tiet nguon: KHONG dung useEffect de dong bo state form tu du lieu nap (tranh set-state-in-effect)", () => {
  const src = chiTiet();
  // Mau dieu chinh luc render: so sanh sourceIdDaNap trong than component,
  // KHONG phai trong callback cua useEffect (se bi eslint
  // react-hooks/set-state-in-effect chan, xem lich su sua loi).
  assert.match(src, /if \(s && s\.source_id !== sourceIdDaNap\)/);
  assert.ok(!/useEffect\(\(\) => \{\s*if \(!s\) return;/.test(src),
    "vẫn còn effect đồng bộ state form từ dữ liệu nạp — sẽ bị eslint set-state-in-effect chặn");
});

test("Chi tiet nguon: quet video co goi scanTrustedSource va hien dem ket qua", () => {
  const src = chiTiet();
  assert.match(src, /adminApi\.scanTrustedSource/);
  assert.match(src, /Phát hiện: \{ketQuaQuet\.detected\}/);
  assert.match(src, /KHÔNG tự xuất bản toàn bộ kênh/);
});

test("Chi tiet nguon: xoa nguon va xoa anh xa deu qua ConfirmDialog", () => {
  const src = chiTiet();
  const soLanConfirm = (src.match(/<ConfirmDialog/g) ?? []).length;
  assert.equal(soLanConfirm, 2, "phải có đúng 2 hộp xác nhận (bỏ tin cậy nguồn + xoá ánh xạ)");
});

test("Chi tiet nguon: dung useRouter().push, KHONG dung window.location.href", () => {
  const src = chiTiet();
  assert.match(src, /useRouter/);
  assert.match(src, /router\.push\("\/admin\/animation\/sources"\)/);
  assert.ok(!src.includes("window.location.href"),
    "vẫn dùng window.location.href thay vì router.push — bị eslint cảnh báo");
});

// -- hang doi nhap --------------------------------------------------------

test("Hang doi nhap: loc theo trang thai va theo nguon (query param source)", () => {
  const src = hangDoi();
  assert.match(src, /useSearchParams/);
  assert.match(src, /params\.get\("source"\)/);
  assert.match(src, /adminApi\.videoImports\(/);
});

test("Hang doi nhap: bon hanh dong Nhap/Nhap+Xuat ban/Tu choi/Bo qua deu co", () => {
  const src = hangDoi();
  assert.match(src, /adminApi\.importVideo\(im\.import_id, publish\)/);
  assert.match(src, /onClick={\(\) => nhap\(im, false\)}/);
  assert.match(src, /onClick={\(\) => nhap\(im, true\)}/);
  assert.match(src, /adminApi\.rejectVideoImport/);
  assert.match(src, /adminApi\.ignoreVideoImport/);
});

test("Hang doi nhap: tu choi di qua ConfirmDialog (khong xoa am tham)", () => {
  const src = hangDoi();
  assert.match(src, /<ConfirmDialog/);
  assert.match(src, /hoiTuChoi/);
});

test("Hang doi nhap: useSearchParams duoc boc trong Suspense (yeu cau Next.js)", () => {
  const src = hangDoi();
  const capNgoai = src.slice(0, src.indexOf("function ImportQueue()"));
  assert.match(capNgoai, /<Suspense/);
});

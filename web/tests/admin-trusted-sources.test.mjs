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
const countUp = () => read("../src/components/CountUp.tsx");

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

test("Danh sach nguon: hien anh dai dien kenh THAT (thumbnail_url), co du phong chu cai khi thieu", () => {
  const src = list();
  assert.match(src, /s\.thumbnail_url\s*\?/, "phải kiểm tra thumbnail_url thật trước khi vẽ ảnh");
  assert.match(src, /<img src=\{s\.thumbnail_url\}/);
  assert.match(src, /className="admin-avt admin-avt-img"/);
  // Du phong: KHONG chi ve trong khi khong co anh — van phai co mot span chu cai.
  assert.match(src, /className="admin-avt" aria-hidden="true"/);
});

test("Danh sach nguon: hien cot 'Đã nhập'/'Đã xuất bản' tu du lieu that (imported_count/published_count)", () => {
  const src = list();
  assert.match(src, /Đã nhập/);
  assert.match(src, /Đã xuất bản/);
  assert.match(src, /\{s\.imported_count\}/);
  assert.match(src, /\{s\.published_count\}/);
});

test("Danh sach nguon: cot WebSub dung LAI nhan/mau cua trang chi tiet (khong bia lai)", () => {
  const src = list();
  assert.match(src, /NHAN_DANG_KY\[s\.subscription_status\]/);
});

test("Danh sach nguon: hanh dong Tam dung/Tiep tuc TUONG MINH (khong con nhan Bat/Tat)", () => {
  const src = list();
  assert.match(src, /"Tạm dừng"/);
  assert.match(src, /"Tiếp tục"/);
  assert.match(src, /adminApi\.setTrustedSourceEnabled\(sourceId/);
  assert.match(src, /onClick=\{\(\) => datBatTat\(s\.source_id, !s\.enabled\)\}/);
});

test("adminApi.trustedSources: kieu AdminTrustedSourceRow co imported_count/published_count", () => {
  const src = api();
  const at = src.indexOf("export interface AdminTrustedSourceRow");
  const than = src.slice(at, src.indexOf("}", at));
  assert.match(than, /imported_count:\s*number;/);
  assert.match(than, /published_count:\s*number;/);
});

test("Chi tiet nguon: nhan Tam dung/Tiep tuc dong bo voi danh sach (khong con Bat/Tat)", () => {
  const src = chiTiet();
  assert.match(src, /"Đã tạm dừng"/);
  assert.match(src, /"Tạm dừng nguồn"/);
  assert.match(src, /"Tiếp tục nguồn"/);
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

test("adminApi: discoverSeriesFromSeed goi dung duong /discover (Auto-Ingestion Phase 1)", () => {
  const src = api();
  assert.match(src, /discoverSeriesFromSeed:[\s\S]{0,400}\/discover`/);
  assert.match(src, /export interface SeriesDiscoveryResult \{[\s\S]{0,100}seed_video_id: string;/);
});

test("Chi tiet nguon: kham pha series tu seed goi discoverSeriesFromSeed va tai su dung parseYoutubeVideoId", () => {
  const src = chiTiet();
  assert.match(src, /import \{ parseYoutubeVideoId \} from "@\/lib\/youtubeUrl";/);
  assert.match(src, /adminApi\.discoverSeriesFromSeed\(sourceId, videoId\)/);
  assert.match(src, /Khám phá series từ video này/);
  assert.match(src, /ketQuaKhamPha\.created_new_series/);
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

// -- nhap hang loat (bulk import) -----------------------------------------

test("Hang doi nhap: adminApi.trustedSources co ham bulkImportVideos, khong tu ghep URL rieng", () => {
  const src = api();
  assert.match(src, /bulkImportVideos:\s*\(/);
  assert.match(src, /\/api\/admin\/animation\/imports\/bulk-import/);
});

test("Hang doi nhap: checkbox tung dong CHI cho phep chon video DA CO series+tap", () => {
  const src = hangDoi();
  assert.match(src, /coTheChon\s*=\s*useCallback\(/);
  assert.match(src, /Boolean\(im\.detected_series_id\)\s*&&\s*im\.detected_episode_number\s*!==\s*null/);
  assert.match(src, /disabled={!coTheChon\(im\)}/);
});

test("Hang doi nhap: lua chon TU DONG don sach khi doi trang/loc (dieu chinh state trong than component, KHONG dung useEffect)", () => {
  const src = hangDoi();
  assert.match(src, /const khoaLoc = `\$\{tt\}\|\$\{nguonLoc\}\|\$\{trangThai\}`;/);
  assert.match(src, /if \(khoaLoc !== khoaLocDaThay\) \{[\s\S]{0,120}setDaChon\(new Set\(\)\);/);
  // KHONG dung useEffect cho viec nay — trung dung loi lint set-state-in-effect
  // da tung vap phai o sources/[id]/page.tsx (xem docstring dau ham).
});

test("Hang doi nhap: thanh hanh dong hang loat CHI hien khi co video da chon, kem nut Bo chon", () => {
  const src = hangDoi();
  assert.match(src, /daChon\.size > 0\s*\?/);
  assert.match(src, /Đã chọn \{daChon\.size\} video/);
  assert.match(src, /onClick={\(\) => setDaChon\(new Set\(\)\)}/);
});

test("Hang doi nhap: nhap hang loat BAT BUOC xem truoc qua ConfirmDialog truoc khi goi API", () => {
  const src = hangDoi();
  // Nut mo hop thoai (dat `hoiNhapHangLoat`), KHONG goi adminApi truc tiep.
  assert.match(src, /onClick={\(\) => setHoiNhapHangLoat\(false\)}/);
  assert.match(src, /onClick={\(\) => setHoiNhapHangLoat\(true\)}/);
  // Chi ConfirmDialog (onConfirm) moi thuc su goi API nhap hang loat.
  const atDialog = src.indexOf("hoiNhapHangLoat !== null");
  const thanDialog = src.slice(atDialog, src.indexOf("/>", atDialog));
  assert.match(thanDialog, /onConfirm={\(\) => nhapHangLoat\(Boolean\(hoiNhapHangLoat\)\)}/);
  assert.match(thanDialog, /dsDaChon\.map/, "phải liệt kê ĐÚNG các video sẽ bị tác động trước khi xác nhận");
});

test("Hang doi nhap: nhapHangLoat dung adminApi.bulkImportVideos (mot request), khong lap goi importVideo tung video", () => {
  const src = hangDoi();
  const at = src.indexOf("async function nhapHangLoat");
  const than = src.slice(at, src.indexOf("\n  }", at));
  assert.match(than, /adminApi\.bulkImportVideos\(/);
  assert.ok(!than.includes("adminApi.importVideo("),
    "nhapHangLoat không được lặp gọi importVideo từng video — phải dùng route bulk-import dùng chung");
});

test("Hang doi nhap: ket qua nhap hang loat bao ro so thanh cong/loi, khong bao 'thanh cong' gia khi co video loi", () => {
  const src = hangDoi();
  const at = src.indexOf("async function nhapHangLoat");
  const than = src.slice(at, src.indexOf("\n  }", at));
  assert.match(than, /results\.filter\(\(r\) => r\.ok\)\.length/);
  assert.match(than, /thatBai === 0/);
});

test("CountUp: khong dung framer-motion hay dependency runtime nao, tu ve bang requestAnimationFrame", () => {
  const src = countUp();
  assert.ok(!/from "framer-motion"/.test(src), "phải là component tự viết, không kéo runtime nặng");
  assert.match(src, /requestAnimationFrame/);
});

test("CountUp: tat hoat hinh khi prefers-reduced-motion, hien luon gia tri cuoi", () => {
  const src = countUp();
  assert.match(src, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)/);
  assert.match(src, /setHien\(den\)/);
});

test("Anh xa series: payload va bang reload deu giu tu khoa mong doi", () => {
  const src = chiTiet();
  assert.match(src, /include_keywords:\s*tachDay\(tuKhoaBaoGom\)/);
  assert.match(src, /<th scope="col">Từ khoá mong đợi<\/th>/);
  assert.match(src, /m\.include_keywords\.join\(", "\) \|\| "—"/);
});

test("CountUp: render dau la 0 o ca server/client, sau mount moi chay toi gia tri that", () => {
  const src = countUp();
  assert.match(src, /useState\(0\)/,
    "giá trị đầu phải cố định ở 0 để vừa có hiệu ứng first-mount vừa không hydration mismatch");
  assert.match(src, /useRef\(0\)/,
    "mốc nội suy đầu tiên phải là 0, không phải giá trị cuối");
});

test("CountUp: chi chay khi gia tri thay doi va huy frame khi unmount/doi gia tri", () => {
  const src = countUp();
  assert.match(src, /if \(tu === den\) return;/);
  assert.match(src, /cancelAnimationFrame\(frameId\)/);
  assert.match(src, /if \(tiLe < 1\) frameId = requestAnimationFrame\(buoc\)/,
    "vòng animation phải tự dừng khi đạt giá trị cuối");
});

test("Trang danh sach nguon: cot Da nhap/Da xuat ban dung CountUp thay vi in so tinh", () => {
  const src = list();
  assert.match(src, /import \{ CountUp \} from "@\/components\/CountUp";/);
  assert.match(src, /<CountUp value=\{s\.imported_count\} \/>/);
  assert.match(src, /<CountUp value=\{s\.published_count\} \/>/);
});

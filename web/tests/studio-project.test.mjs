/*
 * Studio Project — rang buoc cua GIAO DIEN.
 *
 * Kiem tren ma nguon, cung khuon voi moi bo kiem web o day. No khong thay
 * duoc browser QA; no chot lai nhung quyet dinh de bi lam hong ve sau.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const tongQuan = () => read("../src/app/studio/page.tsx");
const khongGian = () => read("../src/app/studio/projects/[id]/page.tsx");
const boChon = () => read("../src/components/StudioAssetPicker.tsx");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");

const chiMa = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/* ================================================== tien do KHONG BIA === */

test("tien do KHONG bao gio bia mot ty le", () => {
  /*
    "8/10 chuong co audio" dem duoc; "80% hoan thanh" thi khong. Backend tra
    `total: null` khi khong co mau so THAT, va giao dien phai ton trong dieu
    do thay vi chia bua.
  */
  const a = api();
  assert.match(a, /total: number \| null;/,
    "kiểu tiến độ phải cho phép `null`");

  for (const [ten, src] of [["tổng quan", tongQuan()], ["không gian", khongGian()]]) {
    assert.match(src, /total === null/, `${ten} không xử lý "không có mẫu số"`);
    // Khong duoc co phep chia nao de ra phan tram.
    assert.ok(!/\.count\s*\/\s*\w*\.total/.test(chiMa(src)),
      `${ten} đang tự tính tỷ lệ từ count/total`);
    assert.ok(!/%/.test(chiMa(src).match(/function TienDo[\s\S]{0,600}/)?.[0] ?? ""),
      `${ten} hiển thị phần trăm`);
  }
});

/* ==================================================== sau chang dung ===== */

test("sau chang dung THU TU quy trinh", () => {
  const a = api();
  assert.match(
    a,
    /STUDIO_STAGES: StudioStage\[\] = \[\s*"noi_dung",\s*"dich",\s*"hinh_anh",\s*"audio",\s*"phu_de",\s*"video",?\s*\]/,
  );
});

test("khong gian lam viec ve du SAU chang", () => {
  const src = khongGian();
  assert.match(src, /STUDIO_STAGES\.map/);
  for (const c of ["noi_dung", "dich", "hinh_anh", "audio", "phu_de", "video"]) {
    assert.ok(src.includes(`${c}:`), `thiếu công cụ cho chặng ${c}`);
  }
});

test("trang du an KHONG tu lam viec cua cong cu nao", () => {
  /*
    Gop chuc nang cua sau cong cu vao mot trang la dung lai chinh cai mo
    hinh ma du an sinh ra de thay the. No NOI, khong LAM.
  */
  const src = chiMa(khongGian());
  for (const cam of ["<video", "<audio", "ffmpeg", "synthesize", "generateImage"]) {
    assert.ok(!src.includes(cam), `trang dự án đang tự làm việc: ${cam}`);
  }
});

/* ================================================== bo chon tai san ===== */

test("MOT bo chon tai san dung chung, khong moi cong cu mot ban", () => {
  const b = boChon();
  assert.match(b, /studio\.assets\(stage, projectId\)/);
  // Giao dien KHONG bao gio tu loc theo chu so huu — mot phep loc o trinh
  // duyet la mot phep loc bo qua duoc.
  assert.ok(!/owner_id|owner_user_id/.test(chiMa(b)),
    "bộ chọn đang tự lọc theo chủ sở hữu ở trình duyệt");
});

test("muc DA o trong du an thi khong gan lai duoc", () => {
  const b = boChon();
  assert.match(b, /if \(a\.in_project\) return;/);
  assert.match(b, /disabled=\{a\.in_project/);
});

test("CA SAU chang chon duoc, ke ca Noi dung", () => {
  /*
    Ban dau Nội dung khong co duong nao o giao dien: `novel_id` chi dat duoc
    bang PATCH, ma khong man hinh nao goi no. Hau qua khong dung o mot o
    trong — mau so cua Audio va Phu de la SO CHUONG cua truyen da gan, nen
    mot du an khong gan duoc truyen thi vinh vien khong hien duoc "2/4 chương
    có audio", dung thu tien do that ma ca trang nay dung len de noi.
  */
  const src = khongGian();
  assert.match(src, /const CHON_DUOC: StudioStage\[\] = \[\.\.\.STUDIO_STAGES\]/,
    "không phải cả sáu chặng đều chọn được");
  assert.match(src, /CHON_DUOC\.includes\(chang\)/);
});

test("Noi dung THAY THE, nam chang kia THEM", () => {
  /*
    Mot du an co MOT truyen. Gop hai nghia do sau mot ham `attach()` duy nhat
    se khien "gắn" am tham mang nghia "ghi đè" o dung mot chang.
  */
  const src = chiMa(khongGian());
  assert.match(src, /if \(chang === "noi_dung"\) await studio\.patchProject\(id, \{ novel_id: refId \}\);/);
  assert.match(src, /if \(chang === "noi_dung"\) await studio\.patchProject\(id, \{ novel_id: "" \}\);/);
});

test("muc da gan hien TEN, khong hien ma", () => {
  /*
    Ban truoc in thang `trk_9f2a…` len man hinh chinh cua du an — dung thu
    may can va dung thu nguoi khong doc duoc. Nhan den tu DUNG nguon ma bo
    chon dung (`refs` o backend), khong phai mot bang thu hai o trinh duyet.
  */
  const src = khongGian();
  assert.match(src, /const daGan = refs\?\.\[chang\] \?\? \[\];/);
  assert.match(src, /\{x\.label \|\| x\.id\}/);
  // Tai san da bi xoa o cho khac van phai HIEN RA de nguoi dung go duoc.
  assert.match(src, /if \(x\.missing\)/);
  assert.match(api(), /missing: boolean;/);
});

test("danh sach du an KHONG keo theo nhan", () => {
  /*
    Nhan phai quet ca sau kho. Bat no o duong danh sach se lam trang Tong
    quan tra gia theo SO DU AN nhan SAU.
  */
  assert.match(api(), /refs\?: Record<StudioStage, StudioRef\[\]>;/,
    "`refs` phải là tuỳ chọn — danh sách dự án không có nó");
});

/* ================================================== tai thang len ======= */

test("tai len KHONG con di qua base64", () => {
  /*
    #202 gui base64 trong than JSON — moi byte thanh ~1.37 byte VA ca tep di
    qua tien trinh web.
  */
  const a = api();
  const i = a.indexOf("upload: async (");
  assert.ok(i > 0, "thiếu hàm upload mới");
  const than = a.slice(i, i + 1600);
  assert.ok(!/base64/i.test(than), "đường tải lên mới vẫn dùng base64");
  assert.match(than, /method: "PUT"/);
  assert.match(than, /body: file/);
  // Ba buoc: xin phien -> PUT -> chot.
  assert.match(than, /\/api\/studio\/uploads/);
  assert.match(than, /finalize/);
});

test("kho R2 thi PUT THANG, khong di qua API", () => {
  const a = api();
  const than = a.slice(a.indexOf("upload: async ("), a.indexOf("upload: async (") + 1600);
  assert.match(than, /if \(ticket\.put_url\)/);
  assert.match(than, /fetch\(ticket\.put_url/);
});

/* ================================================ Video <-> du an ======= */

test("video tao tu du an duoc GAN NGUOC vao du an do", () => {
  const src = read("../src/app/studio/media/page.tsx");
  assert.match(src, /params\.get\("studio"\)/);
  assert.match(src, /studio\s*\n?\s*\.attach\(studioId, "video", r\.project\.project_id\)/);
  // Gan nguoc hong thi KHONG duoc chan viec dung Composer.
  assert.match(src, /\.catch\(\(\) => undefined\)/);
});

test("khong gian lam viec truyen `?studio=` khi mo Video", () => {
  assert.match(khongGian(), /\$\{cc\.href\}\?studio=\$\{encodeURIComponent\(project\.project_id\)\}/);
});

test("tham so tao-moi chi DUNG MOT LAN", () => {
  /*
    `?audio=`/`?studio=` la mot MENH LENH ("tạo một bản video mới"), con URL
    thi o lai tren thanh dia chi. Khong xoa di thi mot lan bam F5 la them mot
    du an video rong nua — va tu `?studio=` thi moi lan nhu the con gan them
    mot muc vao du an Studio.
  */
  const src = read("../src/app/studio/media/page.tsx");
  assert.match(src, /window\.history\.replaceState\(/,
    "tham số tạo-mới không được dọn khỏi URL sau khi dùng");
  assert.match(src, /\?project=\$\{encodeURIComponent\(r\.project\.project_id\)\}/);
  // `replaceState` chu khong phai push: Back khong duoc quay ve dung lenh do.
  assert.ok(!/router\.push\(`?\$\{window\.location\.pathname\}/.test(src));
});

/* ======================================================== trang chu ===== */

test("trang Tong quan KHONG BAO GIO chan cho mang", () => {
  /*
    Ghi chu cu o `/studio` noi rang mot man hinh xoay vong o day lam ca bo
    cong cu co cam giac cham du tung cong cu deu nhanh. Danh sach du an la
    mot khu vuc RIENG co trang thai tai cua no; luoi cong cu ve ngay.
  */
  const src = tongQuan();
  const i = src.indexOf("export default function StudioOverview");
  const than = src.slice(i, src.indexOf("function DuAnCuaToi"));
  assert.ok(!/useAsyncData|await |loading/.test(than),
    "thân trang chính đang chờ mạng");
  assert.match(than, /<DuAnCuaToi \/>/);
  assert.match(than, /THE\.map/);
});

test("khach vang lai KHONG thay mot khu vuc rong voi nut bi khoa", () => {
  assert.match(tongQuan(), /if \(!dangNapPhien && !profile\)/);
});

/* ============================================================== CSS ===== */

test("Studio Project KHONG dung vang", () => {
  const sach = chiMa(css());
  const i = sach.indexOf(".sp {");
  assert.ok(i > 0, "thiếu khối CSS của Studio Project");
  assert.ok(!/--vang|#d8b56a|#e4c982/.test(sach.slice(i)),
    "Studio Project dùng vàng");
});

test("khu Du an dung tren mot BE MAT, khong tran tren tranh nen", () => {
  /*
    Khu nay nam o dau `/studio` — dung cho sang nhat cua tranh nen. Truoc khi
    co no, trang bat dau bang luoi the, va moi the tu mang nen dac.

    Cach sai la noi rong lop phu `--toi` cua ca trang: do la ngan sach do chu
    kho dat, va lam ca site toi di de cuu mot doan chu la doi sai thu. Cach
    sai thu hai la dinh nghia mot mat kinh gan giong `card` — hai be mat gan
    giong nhau la hai cho co the lech.
  */
  assert.match(tongQuan(), /<section className="stack-3 card"/);
  assert.ok(!/\.sp-khu\b/.test(chiMa(css())),
    "đang định nghĩa một mặt kính gần giống `card` thay vì dùng lại nó");
});

test("thang stack-* co DU bac dang duoc dung", () => {
  /*
    `.stack-1` va `.stack-3` duoc goi o muoi hai cho nhung chua bao gio duoc
    dinh nghia. Mot lop khong ton tai khong bao loi — tren `<div>` ket qua
    gan giong du dinh, con tren `<span>` thi cac con nam ngang va dinh vao
    nhau ("Chương 1" + "10s" -> "Chương 110s").
  */
  const sach = chiMa(css());
  const dung = new Set(
    [...[tongQuan(), khongGian()].join("\n").matchAll(/stack-(\d)/g)]
      .map((m) => m[1]),
  );
  assert.ok(dung.size > 0, "không tìm thấy lớp stack-* nào");
  for (const b of dung) {
    assert.match(sach, new RegExp(`\\.stack-${b} \\{[^}]*flex-direction: column`),
      `.stack-${b} đang được dùng nhưng không được định nghĩa`);
  }
});

test("chang da xong chi doi VIEN, khong doi nen", () => {
  /*
    Mot the sang ruc giua danh sach keo mat ve phia thu DA LAM XONG, trong
    khi thu can chu y la thu chua xong.
  */
  const sach = chiMa(css());
  const r = sach.match(/\.sp-chang-xong \{[^}]*\}/)?.[0] ?? "";
  assert.match(r, /border-color/);
  assert.ok(!/background/.test(r), "chặng xong đang đổi cả nền");
});

test("mobile: hang dau cua mot chang xuong nhieu dong", () => {
  const sach = chiMa(css());
  const mobile = sach.slice(sach.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.sp-chang-nut \{ width: 100%; \}/);
  assert.match(mobile, /\.sp-the-luoi \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});

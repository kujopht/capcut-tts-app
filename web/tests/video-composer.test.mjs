/*
 * Video Composer V1 — rang buoc cua GIAO DIEN.
 *
 * Kho nay khong co jsdom/testing-library, nen day la kiem TREN MA NGUON,
 * cung khuon voi moi bo kiem web khac o day. No khong thay duoc browser QA;
 * no chot lai nhung quyet dinh de bi lam hong trong mot lan sua sau.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const trang = () => read("../src/app/studio/video/page.tsx");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");

/*
 * Bo chu thich truoc khi quet MOT LENH CAM.
 *
 * Ca hai cho o duoi cam mot chuoi xuat hien (`ffmpeg.wasm`, `--vang`) — va
 * chinh ma nguon thi NHAC den chung de giai thich vi sao no khong dung. Mot
 * bai kiem cam nhac lich su la mot bai kiem cam viet chu thich; cung nguyen
 * tac da ghi o `fanfic-first-shell.test.mjs`.
 */
const chiMa = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/* ===================================================== Audio -> Video === */

test("Thu vien audio co loi sang Video cho CA hai loai ban ghi", () => {
  /*
    Khong co nut nay thi duong duy nhat de ghep mot ban doc vao video la TAI
    VE roi TAI LEN lai chinh tep minh vua tao.
  */
  const lib = read("../src/app/studio/library/page.tsx");
  assert.match(lib, /function DungTrongVideo/);
  assert.match(lib, /\/studio\/video\?chapter=\$\{encodeURIComponent\(chapterId\)\}/);
  // Ca ban Audio Studio LAN ban fanfic deu phai co loi ra.
  assert.equal((lib.match(/<DungTrongVideo /g) ?? []).length, 2);
});

test("no la LIEN KET chu khong phai mot nut goi API", () => {
  // Bam nham phai quay lai duoc bang nut Back.
  const lib = read("../src/app/studio/library/page.tsx");
  const i = lib.indexOf("function DungTrongVideo");
  const than = lib.slice(i, i + 500);
  assert.match(than, /<Link/);
  assert.ok(!/onClick/.test(than), "không được là nút gọi API");
});

test("Composer nhan CA `?audio=` lan `?chapter=`", () => {
  const t = trang();
  assert.match(t, /params\.get\("audio"\)/);
  assert.match(t, /params\.get\("chapter"\)/);
  // `?chapter=` duoc giai o client tu danh sach da nap — khong mo them mot
  // tham so cho API.
  assert.match(t, /t\.tracks\.find\(\(x\) => x\.chapter_id === tuChuong\)/);
});

/* ======================================================== xem truoc === */

test("xem truoc dung the video/audio THAT, KHONG dung ffmpeg.wasm", () => {
  /*
    ffmpeg.wasm dung ra mot lan ma hoa that — sai cong cu cho mot ban xem
    truoc phai phan hoi tuc thi khi keo con truot. Ban XUAT moi di qua
    FFmpeg o may chu.
  */
  const t = trang();
  assert.match(t, /<video/);
  assert.match(t, /<audio/);
  assert.ok(!/ffmpeg\.wasm|@ffmpeg\//.test(chiMa(t)),
    "không được nhúng ffmpeg.wasm");
});

test("dong bo hai the nam o DUNG MOT cho", () => {
  // Rai phep dong bo ra nhieu cho la cach chac chan nhat de hai duong lech nhau.
  const t = trang();
  assert.match(t, /const dongBo = useCallback/);
  for (const bien_co of ["timeupdate", "seeked", "pause", "ended"]) {
    assert.ok(t.includes(bien_co), `thiếu xử lý ${bien_co}`);
  }
});

test("loi doc chua toi luot thi TAM DUNG, khong tua ve so am", () => {
  const t = trang();
  assert.match(t, /const muc = t - duAn\.audio_offset;/);
  assert.match(t, /if \(muc < 0\)/);
});

/* ======================================================== timeline === */

test("duong thoi gian co du ba lan + thuoc do + dau phat", () => {
  const t = trang();
  for (const lan of ["Video", "Lời đọc", "Phụ đề"]) {
    assert.ok(t.includes(`ten="${lan}"`), `thiếu làn ${lan}`);
  }
  assert.match(t, /vc-thuoc/);
  assert.match(t, /vc-dau-phat/);
});

test("keo lan loi doc doi duoc offset — va ban phim cung lam duoc", () => {
  /*
    Can lai loi doc cho khop hinh la thao tac hay dung nhat cua ca man hinh.
    Chuot khong phai thiet bi duy nhat.
  */
  const t = trang();
  assert.match(t, /onPointerDown/);
  assert.match(t, /role="slider"/);
  assert.match(t, /aria-valuenow/);
  assert.match(t, /e\.key === "ArrowLeft"/);
  assert.match(t, /e\.key === "ArrowRight"/);
});

/* ========================================================== luu === */

test("chi gui truong THAT SU doi, khong gui ca doi tuong", () => {
  // Backend dung `exclude_unset`; gui ca doi tuong se ghi de nhung truong
  // nguoi dung khong he cham toi.
  assert.match(api(), /patchProject: \(id: string, patch: VideoProjectPatch\)/);
  assert.match(api(), /VideoProjectPatch = Partial</);
});

test("khoa doi tuong KHONG nam trong kieu cua giao dien", () => {
  /*
    `output_object_key` la chi tiet kho luu tru. Giao dien xin URL co han qua
    duong rieng (`output`), giong het `audioLink` cua chuong.
  */
  const a = api();
  const i = a.indexOf("export interface VideoProject {");
  const khoi = a.slice(i, a.indexOf("}", i));
  assert.ok(!/output_object_key/.test(khoi));
  assert.match(khoi, /has_output: boolean/);
});

test("hoi trang thai render CHI khi con dang chay", () => {
  // Mot vong hoi mai mai la mot vong hoi se bi quen mat.
  const t = trang();
  assert.match(t, /render_state === "queued" \|\| duAn\.render_state === "rendering"/);
  assert.match(t, /clearInterval/);
});

/* ====================================================== Studio + CSS === */

test("Video la mot muc cua Studio, dung CUOI quy trinh", () => {
  const shell = read("../src/components/StudioShell.tsx");
  const thu_tu = [...shell.matchAll(/href: "(\/studio[^"]*)"/g)].map((m) => m[1]);
  assert.deepEqual(thu_tu.slice(0, 7), [
    "/studio",
    "/studio/write",
    "/studio/translate",
    "/studio/audio",
    "/studio/image",
    "/studio/subtitle",
    "/studio/video",
  ]);
});

test("Video dung icon RIENG, khong trung voi Phu de", () => {
  // Hai module dung canh nhau trong thanh ben; trung hinh thi cai dang mo
  // khong con nhan ra duoc.
  const shell = read("../src/components/StudioShell.tsx");
  assert.match(shell, /icon: IconClapper/);
  assert.match(read("../src/components/Icons.tsx"), /export function IconClapper/);
});

test("khung soan thao KHONG dung vang — ngan sach vang la rao cung", () => {
  /*
    Ban dac ta yeu cau "champagne-gold primary actions", nhung kho nay chot
    vang la mau CHI TIET 10-15% bang `fantasy-identity.test.mjs`. Nang tran
    do cho mot module moi la doi mot rang buoc my thuat cua ca san pham de
    lay mot mau nut.
  */
  /*
    BO CHU THICH TRUOC roi moi cat.

    Cat truoc thi diem neo (`indexOf`) roi vao GIUA khoi chu thich mo dau,
    nen `/*` nam ngoai lat cat va phep bo chu thich khong con bat duoc gi —
    ca doan giai thich "vi sao khong dung vang" se bi tinh la dung vang.
  */
  const sach = chiMa(css());
  const i = sach.indexOf(".vc {");
  assert.ok(i > 0, "thiếu khối CSS của Video Composer");
  const khoi = sach.slice(i);
  assert.ok(!/--vang|#d8b56a|#e4c982/.test(khoi), "Video Composer dùng vàng");
});

test("dau phat la CHI TIET DUY NHAT co quang trong khung soan thao", () => {
  const sach = chiMa(css());
  const khoi = sach.slice(sach.indexOf(".vc {"));
  const quang = [...khoi.matchAll(/box-shadow:\s*([^;]+);/g)]
    .map((m) => m[1].trim())
    .filter((v) => v !== "none");
  assert.equal(quang.length, 1, `số chỗ có quầng: ${quang.length}`);
  assert.ok(khoi.indexOf("box-shadow") > khoi.indexOf(".vc-dau-phat"));
});

test("duong thoi gian tu cuon ngang — ca TRANG thi khong", () => {
  const c = css();
  const khoi = c.slice(c.indexOf(".vc-timeline {"));
  assert.match(khoi.slice(0, 400), /overflow-x: auto/);
});

test("mobile KHONG bop ca khung soan thao xuong 390px", () => {
  const c = css();
  const mobile = c.slice(c.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.vc-cap \{ grid-template-columns: 1fr; \}/);
  assert.match(mobile, /\.vc-dau-nut \{ width: 100%; \}/);
});

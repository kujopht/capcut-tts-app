/*
 * Media Studio — rang buoc cua GIAO DIEN cho phan Video/Audio/Phu de.
 *
 * TRUOC KHI CO MEDIA STUDIO, day la bai kiem cho `/studio/video/page.tsx`
 * (Video Composer V1, PR #202) — mot trang RIENG chi ghep MOT video + MOT loi
 * doc + (tuy chon) MOT phu de. Sau khi gop Audio/Phu de/Video thanh mot trinh
 * soan duong thoi gian duy nhat (`feat/studio-media-workspace`, xem §4-§14
 * cua nhiem vu), logic do chuyen sang:
 *
 *   - `src/app/studio/media/page.tsx`     — nap du an, xu ly tham so URL
 *   - `src/components/media/Timeline.tsx` — ba lan + thuoc do + dau phat
 *   - `src/components/media/Preview.tsx`  — xem truoc dong bo mot dong ho
 *
 * Kho nay khong co jsdom/testing-library, nen day la kiem TREN MA NGUON,
 * cung khuon voi moi bo kiem web khac o day. No khong thay duoc browser QA;
 * no chot lai nhung quyet dinh de bi lam hong trong mot lan sua sau.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const trangMedia = () => read("../src/app/studio/media/page.tsx");
const preview = () => read("../src/components/media/Preview.tsx");
const timeline = () => read("../src/components/media/Timeline.tsx");
const dongHo = () => read("../src/components/media/useDongHo.ts");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");

/*
 * Bo chu thich truoc khi quet MOT LENH CAM.
 *
 * Cho o duoi cam mot chuoi xuat hien (`ffmpeg.wasm`) — va chinh ma nguon thi
 * NHAC den chuoi do de giai thich vi sao no khong dung. Mot bai kiem cam nhac
 * lich su la mot bai kiem cam viet chu thich; cung nguyen tac da ghi o
 * `fanfic-first-shell.test.mjs`.
 */
const chiMa = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/* ===================================================== Audio -> Video === */

test("Thu vien audio co loi sang Media cho CA hai loai ban ghi", () => {
  /*
    Khong co nut nay thi duong duy nhat de ghep mot ban doc vao video la TAI
    VE roi TAI LEN lai chinh tep minh vua tao.
  */
  const lib = read("../src/app/studio/library/page.tsx");
  assert.match(lib, /function DungTrongVideo/);
  assert.match(lib, /\/studio\/media\?chapter=\$\{encodeURIComponent\(chapterId\)\}/);
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

test("Media Studio nhan CA `?audio=` lan `?chapter=`", () => {
  const t = trangMedia();
  assert.match(t, /params\.get\("audio"\)/);
  assert.match(t, /params\.get\("chapter"\)/);
  // `?chapter=` duoc giai o client tu danh sach da nap — khong mo them mot
  // tham so cho API.
  assert.match(t, /al\.tracks\.find\(\(x\) => x\.chapter_id === tuChuong\)/);
});

/* ======================================================== xem truoc === */

test("xem truoc dung the video/audio THAT, KHONG dung ffmpeg.wasm", () => {
  /*
    ffmpeg.wasm dung ra mot lan ma hoa that — sai cong cu cho mot ban xem
    truoc phai phan hoi tuc thi khi keo con truot. Ban XUAT moi di qua
    FFmpeg o may chu.
  */
  const p = preview();
  assert.match(p, /<video/);
  assert.match(p, /<audio/);
  assert.ok(!/ffmpeg\.wasm|@ffmpeg\//.test(chiMa(p)),
    "không được nhúng ffmpeg.wasm");
});

test("dong bo video/audio/duong thoi gian dung MOT dong ho, khong rai poll", () => {
  /*
    Rai phep dong bo ra nhieu cho la cach chac chan nhat de cac phan lech
    nhau. `useDongHo` la nguon `giay` DUY NHAT; Preview va Timeline deu chi
    DOC bien do, khong ai tu tinh thoi gian rieng bang cach doc `currentTime`
    qua su kien trinh duyet (`timeupdate`) — ca hai phan tu cap nhat theo
    dong ho khi no doi, chu khong nguoc lai.
  */
  const h = dongHo();
  assert.match(h, /requestAnimationFrame/);
  assert.match(h, /export function useDongHo/);

  const p = chiMa(preview());
  assert.ok(!/addEventListener\(.timeupdate./.test(p),
    "Preview tự nghe timeupdate thay vì dùng chung đồng hồ");

  const t = trangMedia();
  assert.match(t, /const dongHo = useDongHo\(tong\);/);
  assert.match(t, /giay={dongHo\.giay}/);
});

test("loi doc chua toi luot thi TAM DUNG, khong tua ve so am", () => {
  const p = preview();
  const at = p.indexOf("const dich = giayTrongNguon(audio, giay);");
  assert.notEqual(at, -1);
  const khoi = p.slice(at, at + 450);
  assert.match(khoi, /if \(dich === null\) \{/);
  assert.match(khoi, /if \(!el\.paused\) el\.pause\(\);/);
});

/* ======================================================== timeline === */

test("duong thoi gian co du ba lan + thuoc do + dau phat", () => {
  const t = timeline();
  for (const lan of ["Video", "Lời đọc", "Phụ đề"]) {
    assert.ok(t.includes(`nhan="${lan}"`), `thiếu làn ${lan}`);
  }
  assert.match(t, /tl-thuoc/);
  assert.match(t, /tl-dau-phat/);
});

test("keo clip loi doc doi duoc thoi diem bat dau — va ban phim cung lam duoc", () => {
  /*
    Can lai loi doc cho khop hinh la thao tac hay dung nhat cua ca man hinh.
    Chuot khong phai thiet bi duy nhat.
  */
  const t = timeline();
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
  /*
    Media Studio thay `setInterval`/`clearInterval` bang mot vong lap
    `for` + `await` lien tiep: vong lap DUNG NGAY khi gap trang thai ket
    thuc (`ready`/`failed`) bang `return`/`throw`, nen no khong bao gio hoi
    mai mai sau khi da xong — cung bat bien voi ban truoc, khac co che.
  */
  const t = trangMedia();
  const at = t.indexOf("const xuat = useCallback");
  assert.notEqual(at, -1);
  const than = t.slice(at, t.indexOf("}, [duAn, toast]);", at));
  assert.match(than, /render_state === "ready"/);
  assert.match(than, /render_state === "failed"/);
  assert.match(than, /throw new Error/, "vòng lặp phải DỪNG khi thất bại, không lặp mãi");
});

/* ====================================================== Studio + CSS === */

test("Studio con BON diem den chinh, Media dung sau Noi dung", () => {
  /*
    Truoc day Studio co TAM muc — Tổng quan, Viết truyện, Dịch tiểu thuyết,
    Audio, Hình ảnh, Phụ đề, Video, Tác phẩm của tôi — la ban do cua NGUOI
    CAI DAT. Sau khi gop lai (§1 cua nhiem vu), chi con Dự án, Nội dung,
    Media, Hình ảnh.
  */
  const shell = read("../src/components/StudioShell.tsx");
  const thu_tu = [...shell.matchAll(/href: "(\/studio[^"]*)"/g)].map((m) => m[1]);
  assert.deepEqual(thu_tu, [
    "/studio",
    "/studio/content",
    "/studio/media",
    "/studio/image",
  ]);
});

test("moi muc Studio dung icon rieng — khong hai muc nao trung", () => {
  // Bon muc nam canh nhau trong thanh ben; trung hinh thi cai dang mo khong
  // con nhan ra duoc.
  const shell = read("../src/components/StudioShell.tsx");
  const icons = [...shell.matchAll(/icon: (Icon\w+),/g)].map((m) => m[1]);
  assert.equal(icons.length, 4, "phải có đúng bốn mục Studio");
  assert.equal(new Set(icons).size, icons.length, "hai mục Studio dùng trùng icon");
  assert.match(read("../src/components/Icons.tsx"), /export function IconClapper/);
});

/**
 * Diem neo THAT cua khu CSS Media Studio.
 *
 * KHONG dung `indexOf(".ms {")` truc tiep: `.ms` con xuat hien SOM HON, o
 * mot khoi `@media (max-width: 640px)` dung chung (ghi de mobile cho nhieu
 * module, khong rieng gi Media Studio) — khop nham do se keo theo CA MOT
 * doan CSS cua nhung module khac nam giua hai diem, roi bao nham chung dung
 * vang/co quang. Neo vao dong tieu de chu thich (chi xuat hien DUNG mot lan)
 * TRUOC KHI bo chu thich, roi moi cat va bo chu thich phan con lai.
 */
function khuMediaStudio() {
  const tho = css();
  const i = tho.indexOf("Media Studio ======");
  assert.ok(i > 0, "thiếu khối CSS của Media Studio");
  return chiMa(tho.slice(i));
}

test("khung soan thao KHONG dung vang — ngan sach vang la rao cung", () => {
  /*
    Ban dac ta yeu cau "champagne-gold primary actions", nhung kho nay chot
    vang la mau CHI TIET 10-15% bang `fantasy-identity.test.mjs`. Nang tran
    do cho mot module moi la doi mot rang buoc my thuat cua ca san pham de
    lay mot mau nut.
  */
  const khoi = khuMediaStudio();
  assert.ok(!/--vang|#d8b56a|#e4c982/.test(khoi), "Media Studio dùng vàng");
});

test("quang sang CHI cho clip dang chon va dau phat — khong noi rong hon", () => {
  /*
    §15 cua nhiem vu ("Modern = thao tac") cho phep quang o CA clip dang chon
    LAN dau phat — rong hon rao cu cua Video Composer (chi dau phat). Bai
    nay giu dung ranh gioi MOI: moi box-shadow trong khu Media Studio phai
    thuoc ve mot trong hai muc do, khong co quang trang tri nao khac.
  */
  const khoi = khuMediaStudio();
  const quang = [...khoi.matchAll(/^\.([a-z0-9-]+)[^{]*\{[^}]*box-shadow:\s*([^;]+);/gm)]
    .filter(([, , v]) => v.trim() !== "none");
  assert.ok(quang.length > 0, "không tìm thấy quầng sáng nào để kiểm");
  for (const [, selector] of quang) {
    assert.ok(
      selector === "tl-chon" || selector.startsWith("tl-dau-phat"),
      `.${selector} có quầng sáng ngoài clip đang chọn/đầu phát`,
    );
  }
});

test("duong thoi gian tu cuon ngang — ca TRANG thi khong", () => {
  const c = css();
  const khoi = c.slice(c.indexOf(".tl-cuon {"));
  assert.match(khoi.slice(0, 200), /overflow-x: auto/);
});

test("mobile KHONG bop ca trinh soan Media xuong 390px", () => {
  const c = css();
  const mobile = c.slice(c.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.ms-tren \{ grid-template-columns: minmax\(0, 1fr\); gap: var\(--s2\); \}/);
  assert.match(mobile, /\.ms-giua \{ order: 1; \}/);
});

test("ghi de responsive cua Media Studio nam SAU ban khong dieu kien — khong bi de len", () => {
  /*
    LOI THAT DA XAY RA (bat duoc qua QA trinh duyet, khong phai qua bai test
    chuoi): ban va mobile/may tinh bang tung nam trong hai khoi 640px/1100px
    CHINH TAC o DAU tep, trong khi `.tl`/`.ms`/`.insp` khong dieu kien nam O
    CUOI tep. CSS xu hai luat CUNG do dac hieu bang THU TU trong tep — luat
    KHONG dieu kien den SAU luon de len luat co dieu kien den TRUOC, BAT KE
    be rong man hinh. Ket qua: `.tl-lane-nhan` ket o 62px/12px tren dien
    thoai (nhan lane vo boi ky tu), va `.insp` giu nguyen 3 cot day tran
    ngang — ca hai deu VO HINH voi moi bai test quet CHUOI CHU, vi chuoi do
    van "co mat" trong tep, chi khong con hieu luc.

    Bai nay khoa lai THU TU, khong phai su hien dien: vi tri cua tung ban
    ghi de (`indexOf`) phai lon hon vi tri cua RA (`.tl {`, `.ms {`), tuc
    nam SAU no trong tep.
  */
  const c = css();
  const raTl = c.indexOf("\n.tl {");
  const raMs = c.indexOf("\n.ms {");
  const raInsp = c.indexOf("\n.insp {");
  for (const ra of [raTl, raMs, raInsp]) assert.ok(ra > 0, "thiếu bản RA để so vị trí");

  const ghiDe640 = c.indexOf(".tl-lane-nhan { flex-basis: 48px; font-size: 11px; }");
  const ghiDe1100 = c.indexOf(".ms-tren { grid-template-columns: 240px minmax(0, 1fr); }");
  assert.ok(ghiDe640 > raTl, ".tl-lane-nhan (mobile) phải nằm SAU `.tl {` — nếu không, bản RA đè lên nó bất kể bề rộng màn hình");
  assert.ok(ghiDe1100 > raMs, ".ms-tren (tablet) phải nằm SAU `.ms {`");
  assert.ok(ghiDe1100 > raInsp, ".ms-tren (tablet) phải nằm SAU `.insp {` — nó cùng khối với ghi đè .insp");
});

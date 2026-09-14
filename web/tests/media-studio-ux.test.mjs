/*
 * §20 cua nhiem vu "Media Studio" — bo kiem cho danh sach bat bien duoc yeu
 * cau tuong minh: tuong thich duong dan cu, quy trinh CHI AM THANH, loi doc
 * moi hien NGAY trong media bin, clip audio keo duoc va offset ton tai,
 * phan doan phu de keo/co-gian/sua chu duoc.
 *
 * Cung phong cach voi moi bo kiem web khac o day: doc THANG source, khong
 * jsdom/testing-library.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const shell = () => read("../src/components/StudioShell.tsx");
const trangMedia = () => read("../src/app/studio/media/page.tsx");
const timeline = () => read("../src/components/media/Timeline.tsx");
const inspector = () => read("../src/components/media/Inspector.tsx");
const libTimeline = () => read("../src/lib/media/timeline.ts");
const css = () => read("../src/app/globals.css");

const chiMa = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/* ============================================================ dieu huong = */

test("Studio primary nav is audio-first; Media, Video and Subtitle stay contextual", () => {
  const s = shell();
  const order = [...s.matchAll(/href: "([^"]+)",\s*\n\s*nhan: "([^"]+)"/g)]
    .map((m) => m[1]);
  assert.deepEqual(order, ["/studio", "/studio/content", "/studio/audio", "/studio/image"]);
  for (const cu of ["/studio/media", "/studio/subtitle", "/studio/video",
                    "/studio/write", "/studio/translate", "/studio/library"]) {
    assert.ok(!order.includes(cu), `${cu} vẫn còn là điểm đến cấp cao`);
  }
});

/* ================================================ tuong thich duong dan == */

test("only Video and Subtitle compatibility routes redirect to Media", () => {
  const s = shell();
  const map = {};
  for (const m of s.matchAll(/"(\/studio\/[a-z]+)": "([^"]+)"/g)) map[m[1]] = m[2];

  const kyVong = {
    "/studio/subtitle": "/studio/media?panel=subtitle",
    "/studio/video": "/studio/media",
    "/studio/write": "/studio/content?tab=write",
    "/studio/translate": "/studio/content?tab=translate",
  };
  for (const [cu, moi] of Object.entries(kyVong)) {
    assert.equal(map[cu], moi, `${cu} không trỏ đúng "${moi}"`);
  }
});

test("Audio is a real page; compatibility pages use ChuyenHuong", () => {
  const kyVong = {
    "../src/app/studio/subtitle/page.tsx": "/studio/media?panel=subtitle",
    "../src/app/studio/video/page.tsx": "/studio/media",
    "../src/app/studio/write/page.tsx": "/studio/content?tab=write",
    "../src/app/studio/translate/page.tsx": "/studio/content?tab=translate",
  };
  for (const [p, dich] of Object.entries(kyVong)) {
    const src = read(p);
    assert.match(src, /import \{ ChuyenHuong \} from "@\/components\/studio\/ChuyenHuong";/,
      `${p} không dùng ChuyenHuong`);
    assert.match(src, new RegExp(`<ChuyenHuong den="${dich.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}" />`),
      `${p} không trỏ tới "${dich}"`);
  }
  const audio = read("../src/app/studio/audio/page.tsx");
  assert.match(audio, /Audio Studio/);
  assert.ok(!audio.includes("ChuyenHuong"));
  assert.match(audio, /Chỉnh với video/);
  assert.match(audio, /AudioPlayer/);
  assert.match(audio, /\/studio\/media\?audio=\$\{encodeURIComponent\(a\.track_id\)\}/,
    "Chỉnh với video phải mang đúng audio hiện có vào Media");
  assert.match(read("../src/components/AudioPlayer.tsx"), /aria-label=\{`Tải xuống audio MP3:/,
    "Audio gần đây phải có hành động tải xuống rõ ràng, dùng URL audio chuẩn");
});

test("ChuyenHuong giu nguyen tham so nguoi dung mang theo, dung replace khong dung push", () => {
  const src = read("../src/components/studio/ChuyenHuong.tsx");
  assert.match(src, /router\.replace\(/, "phải dùng replace, không phải push");
  assert.ok(!/router\.push\(/.test(chiMa(src)), "không được push — Back sẽ quay lại đúng lệnh chuyển hướng");
  assert.match(src, /params\.forEach\(\(v, k\) => q\.set\(k, v\)\)/,
    "tham số người dùng mang theo phải thắng mặc định của đích");
});

/* ============================================== quy trinh CHI AM THANH === */

test("che do chi-audio KHONG doi hoi video — nut Tao loi doc khong phu thuoc video", () => {
  const panel = read("../src/components/media/TtsPanel.tsx");
  // `guiDuoc` (nut co bam duoc khong) chi phu thuoc van ban/giong/dang tao —
  // KHONG co dieu kien nao ve video trong ca tep.
  assert.match(panel, /const guiDuoc = soKyTu > 0 && !vuotTran && Boolean\(giong\) && !dangTao;/);
  assert.ok(!chiMa(panel).includes("video"), "TtsPanel không được biết gì về video");
});

test("Media Editor chi mo form Tao audio khi nguoi dung yeu cau", () => {
  const trang = trangMedia();
  assert.match(trang, /moTaoAudio/);
  assert.match(trang, /role="dialog"/);
  assert.match(trang, /\+ Tạo audio mới/);
  assert.match(trang, /datMoTaoAudio\(true\)/);
});

test("ban tin chi-audio dua tren TRANG THAI THAT (!video), khong phai tham so URL da mat", () => {
  /*
    Loi that tu QA trinh duyet: ban tin chi con dieu kien `cheDoAudio &&
    !video`, va `cheDoAudio` doc tu `?mode=audio`. Tham so do bi TIEU THU VA
    XOA khoi URL ngay sau khi du an duoc tao (doi sang `?project=<id>` —
    xem hieu ung khoi dong), nen ban tin BIEN MAT sau lan render dau tien du
    trang thai THAT (chua co video) khong doi — dung luc nguoi dung can loi
    trac an nay nhat. Dieu kien phai la `!video` mot minh.
  */
  const trang = trangMedia();
  assert.ok(!chiMa(trang).includes("cheDoAudio"),
    "vẫn còn biến cheDoAudio đọc từ tham số URL đã bị tiêu thụ");
  assert.match(trang, /\{!video \? \(\s*<p className="hint ms-bang-tin">/);
});

test("xem truoc CHI-AUDIO khong bat buoc video — Preview ve duoc khi chi co audio", () => {
  const p = read("../src/components/media/Preview.tsx");
  assert.match(p, /const chiAudio = !video \|\| !urlVideo;/);
  // Thong diep khi chi co audio phai noi ro KHONG can video.
  const at = p.indexOf("Chế độ chỉ âm thanh");
  assert.notEqual(at, -1, "thiếu thông điệp chế độ chỉ âm thanh trong Preview");
});

test("tai xuong duoc loi doc MA KHONG can video — nut Tai xuong o Inspector khong dieu kien video", () => {
  const insp = inspector();
  const at = insp.indexOf("function AudioInsp");
  assert.notEqual(at, -1);
  const than = insp.slice(at, insp.indexOf("function SubInsp"));
  assert.match(than, /href=\{urlAudio\} download/, "thiếu nút tải xuống độc lập với video");
});

test("kho chua TTS o che do khong gan du an KHONG doi hoi truyen fanfic co san", () => {
  // `ensureStudioNovel()` LAY-HOAC-TAO, khong bao gio nem loi "chua co truyen".
  const trang = trangMedia();
  assert.match(trang, /const kho = await ensureStudioNovel\(\);/);
  assert.ok(
    !chiMa(trang).includes('throw new Error("Bạn cần một truyện'),
    "không được chặn tạo lời đọc chỉ vì chưa có truyện fanfic",
  );
});

/* ================================================== media bin cap nhat == */

test("loi doc vua tao hien NGAY trong media bin, khong doi F5", () => {
  const trang = trangMedia();
  const at = trang.indexOf("const ganTrackMoi = useCallback");
  assert.notEqual(at, -1);
  const than = trang.slice(at, trang.indexOf("[napKho, toast, veKho]", at));
  assert.match(than, /const kho = await napKho\(\);/,
    "phải nạp lại kho ngay sau khi job xong");
  assert.match(than, /datKhoAudio\(veKho\(kho\.a,/,
    "phải cập nhật danh sách hiển thị của Media Bin ngay, không đợi F5");
});

test("tai video/audio tho cung cap nhat media bin ngay", () => {
  const trang = trangMedia();
  const at = trang.indexOf("const taiLen = useCallback");
  assert.notEqual(at, -1);
  const than = trang.slice(at, trang.indexOf("[duAn, ghiPhuDe, napKho, toast, veKho]", at));
  assert.match(than, /const kho = await napKho\(\);/);
  assert.match(than, /datKhoVideo\(veKho\(kho\.v,/);
});

/* ==================================================== clip audio keo ===== */

test("keo clip audio doi duoc thoi diem bat dau, va gia tri do TON TAI qua PATCH", () => {
  const t = timeline();
  // Lane audio: pointer-down bat dau mot phep keo "audio-di".
  assert.match(t, /batDauKeo\(e, \{ loai: "audio-di", batDau0: audio\.batDau \}\)/);
  // Khi keo, gia tri moi di qua `onAudio`.
  const at = t.indexOf('k.loai === "audio-di"');
  assert.notEqual(at, -1);
  const than = t.slice(at, at + 200);
  assert.match(than, /onAudio\(\{ \.\.\.audio, batDau: hut\(g, moc, nguong\) \}\)/);
});

test("doi audio (keo/mep/tat) luon ghi PATCH len backend — offset TON TAI qua reload", () => {
  const trang = trangMedia();
  const at = trang.indexOf("const doiAudio = useCallback");
  assert.notEqual(at, -1);
  const than = trang.slice(at, trang.indexOf("[ghi]", at));
  assert.match(than, /audio_offset: c\.batDau,/, "phải ghi audio_offset lên backend");
  assert.match(than, /audio_trim_end: c\.catCuoi,/);
  assert.match(trang, /const ghi = useCallback/, "phải ghi qua đường PATCH dùng chung");
});

test("keo clip audio la Pointer Events, khong phai keo-tha HTML5 (dnd)", () => {
  const t = timeline();
  assert.match(t, /onPointerDown/);
  assert.ok(!/draggable=\{?true\}?/.test(t), "không được dùng thuộc tính draggable của HTML5");
  assert.ok(!chiMa(t).includes("ondragstart"), "không được dùng sự kiện kéo-thả HTML5");
});

/* ================================================== phu de tren timeline = */

test("keo phan doan phu de doi duoc vi tri, GIU NGUYEN do dai", () => {
  const lib = libTimeline();
  const at = lib.indexOf("export function doiPhanDoan");
  assert.notEqual(at, -1);
  const than = lib.slice(at, at + 400);
  assert.match(than, /const dai = s\.end - s\.start;/);
  assert.match(than, /return \{ \.\.\.s, start, end: start \+ dai \};/);

  const t = timeline();
  assert.match(t, /onSub\(doiPhanDoan\(s, hut\(g, moc, nguong\)\)\)/,
    "Timeline phải gọi doiPhanDoan khi kéo phần thân phân đoạn");
});

test("keo MEP phan doan co-gian duoc thoi luong (resize)", () => {
  const lib = libTimeline();
  assert.match(lib, /export function keoMep\(/);
  assert.match(lib, /TOI_THIEU = 0\.2/, "phải có sàn tối thiểu, không cho co về 0");

  const t = timeline();
  assert.match(t, /onSub\(keoMep\(s, k\.mep, hut\(g, moc, nguong\)\)\)/,
    "Timeline phải gọi keoMep khi kéo tay cầm ở mép");
  // Ca hai mep deu bam duoc rieng.
  assert.match(t, /tl-tay-trai/);
  assert.match(t, /tl-tay-phai/);
});

test("sua chu phu de qua Inspector, cap nhat NGAY khong doi bam Luu", () => {
  const insp = inspector();
  const at = insp.indexOf("function SubInsp");
  assert.notEqual(at, -1);
  const than = insp.slice(at, insp.indexOf("function TongQuan", at));
  assert.match(than, /onChange=\{\(e\) => onDoi\(\{ \.\.\.s, text: e\.target\.value \}\)\}/,
    "sửa chữ phải cập nhật ngay trong onChange, không cần một nút Lưu riêng");
});

test("phu de sua xong duoc GHI len backend (thanh mot MediaAsset SRT moi)", () => {
  const trang = trangMedia();
  assert.match(trang, /const ghiPhuDe = useCallback/);
  const at = trang.indexOf("const ghiPhuDe = useCallback");
  const than = trang.slice(at, trang.indexOf("[duAn?.project_id, toast]", at));
  assert.match(than, /const srt = xuatSrt\(ds\);/);
  assert.match(than, /await studio\.upload\(f, "subtitles"\)/);
  assert.match(than, /subtitle_asset_id: r\.asset\.asset_id,/);
});

/* ================================================ h1 + nav o che do ranh = */

test("che do RANH cua Media Studio VAN giu <h1> VA nut mo menu mobile", () => {
  /*
    Loi that tu QA trinh duyet: ban dau che do ranh an CA header, keo theo
    mat luon <h1> (trang khong con tieu de nao cho trinh doc man hinh) VA
    mat nut "Menu Studio" — duoi 900px `.studio-nav` chi hien khi
    `.studio-nav-mo` duoc bat bang dung nut do, nen mat no la khoa nguoi
    dung mobile khoi MOI dieu huong Studio khac, khong loi ra duoc khoi
    Media Studio. Chi duoc phep bo dong eyebrow trang tri.
  */
  const src = shell();
  const at = src.indexOf("<header");
  assert.notEqual(at, -1);
  const than = src.slice(at, src.indexOf("</header>", at));
  assert.match(than, /<h1 className="page-title studio-tieu-de">\{tieuDe\}<\/h1>/,
    "phải luôn render đúng một <h1>, bất kể chế độ ranh");
  assert.ok(
    !/\{cheDoRanh \? null : \(\s*<button/.test(than),
    "nút mở menu mobile không được ẩn ở chế độ ranh",
  );
  assert.match(than, /\{cheDoRanh \? null : \(\s*<span className="eyebrow/,
    "chỉ được phép ẩn dòng eyebrow trang trí ở chế độ ranh");
});

/* ========================================= khung ranh sup tren mobile === */

test("khung 52px cua che do RANH CHI ap dung tu 901px — khong sup tren mobile", () => {
  /*
    Loi that tu QA trinh duyet, sau MOT lop sua khac (thu tu cascade) van
    con: `.studio-ranh .studio-khung { grid-template-columns: 52px minmax(0,
    1fr); }` co do dac hieu CAO HON ban mobile mot-cot da co san
    (`.studio-khung { grid-template-columns: minmax(0, 1fr); }`, mot lop) —
    hai lop luon thang du dung SAU trong tep, BAT KE be rong man hinh.

    Duoi 900px, `.studio-nav` la `display: none` (chi hien khi bam mo menu),
    nen `.studio-khung` chi con MOT o luoi con (`.studio-than`). Grid tu dat
    no vao track DAU TIEN (52px) va de trong track thu hai (rong) — `.ms`
    (va moi thu ben trong: Media Bin, Preview, Timeline, Inspector) bi ep
    con dung 52px. Domino do la ly do `.tl`/`.insp` do duoc ~34px o QA that,
    hoan toan vo hinh voi bat ky bai test chi quet SU HIEN DIEN chuoi chu.

    Sua bang cach bat khung rail CHI tu 901px — duoi do, chi con ban mobile
    mot-cot.
  */
  // Bo chu thich TRUOC khi tim — chinh chu thich giai thich loi nay co chua
  // nguyen van chuoi selector de doi chieu.
  const sach = chiMa(css());
  const at = sach.indexOf(".studio-ranh .studio-khung");
  assert.notEqual(at, -1, "thiếu luật khung rail của chế độ ranh");
  const truoc = sach.slice(Math.max(0, at - 200), at);
  assert.match(truoc, /@media \(min-width: 901px\) \{/,
    "khung 52px của chế độ ranh phải nằm trong @media (min-width: 901px) — không được áp dụng vô điều kiện");
});

/* ============================================== nguon media bin dung ==== */

test("Media Bin lay VIDEO tu MediaAsset THO, khong tu VideoProject cua Studio", () => {
  /*
    Loi that tu QA trinh duyet: `studio.assets("video", studioId)` (chang
    "video" cua Studio Project, #203) tra ve `VideoProject` — CA MOT du an
    Composer — khong phai tep MP4 tho. `video_asset_id` cua VideoProject can
    mot `MediaAsset.asset_id`; nhet mot `VideoProject.project_id` vao do se
    bi backend tu choi (khong tim thay tham chieu). Media Bin phai lay video
    tu `videoStudio.listAssets()` (`/api/video/assets`) va loc theo
    `media_type === "video"`.
  */
  const trang = trangMedia();
  const at = trang.indexOf("const napKho = useCallback");
  assert.notEqual(at, -1);
  // Bo chu thich TRUOC khi quet — chinh chu thich giai thich vi sao ban cu
  // sai co chua nguyen van chuoi `studio.assets("video"` de doi chieu.
  const than = chiMa(trang.slice(at, trang.indexOf("[studioId]", at)));
  assert.ok(!/studio\.assets\("video"/.test(than),
    "Media Bin vẫn lấy video từ chặng Studio Project — sai đối tượng");
  assert.match(than, /videoStudio\.listAssets\(\)/);
  assert.match(than, /x\.media_type === "video"/);
  assert.match(than, /id: x\.asset_id,/, "phải dùng asset_id của MediaAsset");
});

/* ======================================================== du an + reload = */

test("nap lai trang (F5) tren MOT du an co san KHONG tao du an moi", () => {
  const trang = trangMedia();
  const at = trang.indexOf("const moId = params.get");
  assert.notEqual(at, -1);
  const than = trang.slice(at, at + 700);
  assert.match(than, /if \(moId\) \{\s*\n\s*hienTai = await moDuAn\(moId\);/,
    "có ?project= thì chỉ MỞ, không tạo mới");
});

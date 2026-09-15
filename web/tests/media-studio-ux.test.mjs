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

test("Audio co loi vao Media tuy chon ca khi chua chon audio", () => {
  const audio = read("../src/app/studio/audio/page.tsx");
  assert.match(audio, /\+ Thêm video để chỉnh/);
  assert.match(audio, /href="\/studio\/media"/,
    "CTA không được đòi audio_id mới vào được Media");
  assert.match(audio, /\/studio\/media\?audio=\$\{encodeURIComponent\(a\.track_id\)\}/,
    "thẻ audio có sẵn vẫn phải mang đúng track_id sang Media");
});

test("Studio dung page flow tu nhien, khong khoa chieu cao hay ep scroll noi bo", () => {
  const s = css();
  const sach = chiMa(s);
  assert.match(sach, /\.studio-page \{[\s\S]*max-width: 1440px;[\s\S]*margin-inline: auto;/);
  assert.ok(!sach.includes("studio-app-active"));
  assert.ok(!sach.includes("--studio-shell-height"));
  assert.ok(!/\.studio-than\s*\{[^}]*overflow:\s*auto/.test(sach));
  assert.match(sach, /\.audio-recent\s*\{[^}]*max-height:min\(680px, calc\(100dvh - 170px\)\); overflow-y:auto;/,
    "Audio gần đây là danh sách dài duy nhất được cuộn nội bộ trên desktop");
  assert.match(sach, /@media \(max-width: 640px\) \{[\s\S]*\.audio-recent \{ max-height:none; overflow:visible; padding:0; \}/,
    "mobile trở lại page scroll tự nhiên");
});

test("Media giu bo cuc chuyen dung nhung khong dung rail hay viewport shell", () => {
  const s = css();
  const sach = chiMa(s);
  assert.ok(!sach.includes("studio-ranh"));
  assert.match(sach, /\.ms-tren\s*\{[\s\S]*grid-template-columns: 260px minmax\(0, 1fr\) 280px;/);
  assert.match(sach, /\.tl-cuon\s*\{ overflow-x: auto; overflow-y: hidden; \}/,
    "timeline van duoc phep cuon ngang mot cach co chu dich");
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

test("Media chỉ mở editor sau khi có video; trước đó hiển thị onboarding", () => {
  const trang = trangMedia();
  assert.match(trang, /function KhoiDongMedia\(/);
  assert.match(trang, /if \(!video\) \{\s*return \(\s*<KhoiDongMedia/);
  assert.match(trang, /onTaiVideo=\{\(file\) => void taiLen\(file, "video"\)\}/,
    "onboarding phải dùng đúng luồng upload video hiện có");
  assert.match(trang, /accept="video\/mp4,video\/quicktime,video\/webm,video\/x-matroska"/);
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

/* ======================================================== h1 + nav ===== */

test("Studio giữ h1 và nút mở menu mobile trong page flow thường", () => {
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
  assert.match(than, /<span className="eyebrow eyebrow-icon">/,
    "dòng nhận diện Studio luôn hiện trong bố cục trang bình thường");
});

/* =========================================================== mobile ===== */

test("Studio mobile đổi sang một cột, không có desktop rail ẩn nhãn", () => {
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
  assert.ok(!sach.includes("studio-ranh"));
  assert.match(sach, /@media \(max-width: 900px\) \{[\s\S]*\.studio-khung \{ grid-template-columns: minmax\(0, 1fr\); \}/);
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

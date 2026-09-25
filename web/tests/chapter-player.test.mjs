/*
 * Trinh phat cua trang chuong.
 *
 * RANG BUOC QUAN TRONG NHAT: MOT the `<audio>` duy nhat. Trinh phat lon (che
 * do Nghe), trinh phat noi o day man hinh (Doc + Nghe) va thanh nho toan
 * tuyen deu doc cung mot trang thai va goi cung mot bo dieu khien. Tao the
 * thu hai la loi de mac nhat o cho nay — hai the cung phat mot tep thi nguoi
 * dung nghe thanh tieng vong, va bam dung o thanh nay khong dung thanh kia.
 *
 * The `<audio>` VAN la dong co phat. Cai duoc thay chi la lop VE.
 *
 * Sprint doc/nghe 2026-09-24: `/listen/[id]` + `MiniPlayer` (thanh theo cuon
 * cua trang Nghe) duoc thay boi CHE DO NGHE cua trang chuong
 * (`reader/ChapterExperience`) + trinh phat noi (`reader/ChapterAudioDock`).
 * Cac bat bien duoi day duoc CHUYEN sang hai tep do, khong bi bo.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const engine = () => read("../src/components/AudioEngine.tsx");
const hero = () => read("../src/components/ChapterPlayer.tsx");
/** Trinh phat noi cua trang chuong — thay cho `MiniPlayer` cu. */
const dock = () => read("../src/components/reader/ChapterAudioDock.tsx");
const globalMini = () => read("../src/components/GlobalMiniPlayer.tsx");
/** Trai nghiem doc/nghe cua trang chuong — noi goi `phat()` gio. */
const trang = () => read("../src/components/reader/ChapterExperience.tsx");
const trangMayChu = () => read("../src/app/chapters/[id]/page.tsx");
const layout = () => read("../src/app/layout.tsx");
const css = () => read("../src/app/globals.css");
const config = () => read("../next.config.mjs");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================ MOT the audio, khong phai hai */

test("chi DONG CO moi tao the <audio>", () => {
  assert.match(codeOnly(engine()), /<audio\b/, "động cơ không có thẻ <audio>");
  for (const [ten, src] of [
    ["ChapterPlayer", codeOnly(hero())],
    ["ChapterAudioDock", codeOnly(dock())],
    ["ChapterExperience", codeOnly(trang())],
    ["GlobalMiniPlayer", codeOnly(globalMini())],
  ]) {
    assert.ok(
      !/<audio\b/.test(src) && !/new Audio\(/.test(src),
      `${ten} tự tạo thẻ <audio> thứ hai — hai thẻ cùng phát một tệp là tiếng vọng`,
    );
  }
});

test("the <audio> LUON duoc mount — doi chuong chi doi src tren CUNG phan tu", () => {
  // iOS chi cho play() khong-qua-cu-chi tren phan tu da tung phat bang cu chi;
  // mount lai phan tu o moi chuong lam "Chương sau" (dang nghe) bi chan.
  const src = codeOnly(engine());
  assert.ok(!/\{tep \? \(\s*<audio/.test(src), "thẻ <audio> lại bị mount có điều kiện theo tep");
  assert.match(src, /<audio\s+ref=\{el\}\s+preload="metadata"\s+src=\{tep\?\.playUrl\}/);
  // Doi chuong: dung ngay tieng cu, go src, nap lai.
  assert.match(src, /a\.pause\(\);\s*a\.removeAttribute\("src"\);\s*a\.load\(\);/);
});

test("moi trinh phat doc CUNG mot ngu canh, cung dong co toan cuc", () => {
  for (const [ten, src] of [["ChapterPlayer", hero()], ["ChapterAudioDock", dock()],
                            ["ChapterExperience", trang()]]) {
    assert.match(src, /useAudioEngine\(\)/, `${ten} không dùng ngữ cảnh chung`);
  }
  // Dong co la TOAN CUC, mount mot lan trong layout — bao TRUM ca header/
  // main/footer va thanh phat nho toan tuyen. Dieu huong khong huy dong co.
  const l = layout();
  const mo = l.indexOf("<AudioEngineProvider");
  const dong = l.indexOf("</AudioEngineProvider>");
  assert.ok(mo !== -1 && dong > mo, "layout không có <AudioEngineProvider>");
  const trong = l.slice(mo, dong);
  assert.match(trong, /\{children\}/, "children nằm ngoài ngữ cảnh audio");
  assert.match(trong, /<GlobalMiniPlayer/, "thanh phát toàn tuyến nằm ngoài ngữ cảnh");
  // Trang chuong KHONG tu mo mot provider rieng — chi goi `phat()`.
  const t = trang();
  assert.ok(!/<AudioEngineProvider/.test(t), "trang chương tự mở provider riêng");
  assert.match(t, /d\.phat\(chapterId, chapterTitle/, "trang chương không gọi phat()");
  // Phan may chu khong cham dong co (no la Server Component).
  assert.ok(!/useAudioEngine/.test(trangMayChu()));
});

test("trang Nghe rieng chi con la CHUYEN HUONG ve trang chuong", () => {
  assert.ok(!existsSync(new URL("../src/app/listen/[id]/page.tsx", import.meta.url)));
  assert.match(
    config(),
    /\{ source: "\/listen\/:id", destination: "\/chapters\/:id\?mode=listen", permanent: false \}/,
  );
});

test("nut phat o MOI cho deu di vao cung dong co", () => {
  assert.match(hero(), /onClick=\{d\.batTat\}/, "ChapterPlayer không gọi batTat chung");
  // Trinh phat noi goi nut Phat CUA TRANG: chuong da nap -> batTat; chua -> nap + phat.
  assert.match(dock(), /onClick=\{p\.onPhat\}/);
  const t = trang();
  assert.match(t, /if \(laBaiNay && t\.tep\) \{\s*d\.batTat\(\);/);
  assert.match(t, /d\.phat\(chapterId, chapterTitle, \{ \.\.\.thongTin, tuPhat: true \}\)/);
});

/* ==================================== the <audio> van la dong co, khong bi thay */

test("phat/dung/tua deu goi thang vao the <audio>", () => {
  const src = engine();
  assert.match(src, /a\.play\(\)/, "không gọi play() của thẻ audio");
  assert.match(src, /a\.pause\(\)/);
  assert.match(src, /a\.currentTime = /);
  assert.match(src, /a\.volume = /);
  assert.match(src, /a\.playbackRate = v/);
  // KHONG tu dung Web Audio API — the <audio> la du.
  assert.ok(!/AudioContext|createMediaElementSource/.test(src));
});

test("duong lay URL KHONG doi", () => {
  // Van la `lib/audio.ts::resolveAudio`, ke ca duong R2 ky san lan duong
  // stream qua backend. Doi cho nay la pha ca hai che do kho.
  assert.match(engine(), /resolveAudio\(track\.chapterId\)/);
  assert.match(engine(), /thuHoi\.current\?\.\(\)/, "không thu hồi blob URL");
});

test("phat() la khong-lam-gi voi CUNG chapterId — vi tri phat khong bi dat lai", () => {
  // Day la ly do dieu huong ve DUNG trang chuong dang nghe khong lam audio
  // nhay ve dau: `setTrack` tra ve chinh doi tuong cu khi chapterId khop, nen
  // effect lay URL (khoa boi `track`) khong chay lai.
  const src = engine();
  assert.match(
    src,
    /hienTai\?\.chapterId === chapterId \? hienTai : \{ chapterId, title \}/,
    "phat() không idempotent theo chapterId",
  );
  assert.match(src, /\}, \[track\]\);/, "effect lấy URL không khóa theo track");
  // Cung chuong: y dinh (tua/phat) ap ngay, KHONG nap lai.
  assert.match(src, /if \(trackRef\.current\?\.chapterId === chapterId\) \{[\s\S]{0,1000}?return;/);
});

test("GlobalMiniPlayer an o dung trang chuong dang phat, hien o moi noi khac", () => {
  // Trang chuong cua bai dang phat da co trinh phat rieng (noi / lon). Trang
  // cua MOT CHUONG KHAC van can thanh toan cuc.
  const src = globalMini();
  assert.match(src, /usePathname\(/, "không đọc tuyến hiện tại");
  assert.match(src, /pathname === `\/chapters\/\$\{t\.chapterId\}`/,
    "không so sánh với trang chương đang phát");
  assert.match(src, /t\.daBatDau && !t\.loi && !oTrangNgheChuongNay/);
  // Bam ten -> ve duong dan chinh tac, khong ve trang Nghe cu.
  assert.match(src, /href=\{`\/chapters\/\$\{t\.chapterId\}`\}/);
  assert.ok(!/href=\{`\/listen\//.test(src));
});

test("tai MP3 van con, va dung URL tai rieng", () => {
  assert.match(hero(), /href=\{t\.tep\.downloadUrl\}/);
  assert.match(hero(), /download=\{t\.tenTep\}/);
});

test("KHONG tu dong phat khi mo trang", () => {
  // Trinh duyet chan tu dong phat khi chua co tuong tac, va tu phat mot chuong
  // truyen khi nguoi ta vua mo trang la mot hanh vi tho lo.
  const src = codeOnly(engine());
  assert.ok(!/autoPlay|autoplay/.test(src));
  assert.ok(!/useEffect\([^)]*\)\s*=>\s*\{[^}]*\.play\(\)/.test(src));
  // Trang chuong: luc mo chi NAP (khong `tuPhat`) — tru khi URL xin tuong minh.
  const t = codeOnly(trang());
  const moTrang = t.slice(t.indexOf("const daKhoiDong = useRef(false);"));
  const than = moTrang.slice(0, moTrang.indexOf("}, []);"));
  assert.match(than, /if \(urlRequestsPlay && !banChuongKhac\) \{\s*d\.phat\(chapterId, chapterTitle, \{ \.\.\.thongTin, tuPhat: true \}\);/);
  assert.match(than, /d\.phat\(chapterId, chapterTitle, thongTin\);/, "nap san khong duoc kem tuPhat");
  assert.equal((than.match(/tuPhat: true/g) ?? []).length, 1, "chi nhanh ?autoplay=1 duoc xin phat");
});

/* ============================================ trinh phat noi: khi nao noi len */

test("trinh phat noi o che do Nghe chi hien khi DA nghe VA trinh phat lon da khuat", () => {
  assert.match(trang(), /mode === "listen" && heroKhuat && dangNghe/);
});

test("biet trinh phat lon con thay khong bang IntersectionObserver", () => {
  // Khong dung `scrollY`: chieu cao dau trang doi theo do dai ten chuong, nen
  // mot con so pixel co dinh se sai o dung nhung chuong co ten dai.
  const src = trang();
  assert.match(src, /new IntersectionObserver\(/);
  assert.match(src, /theoDoi\.disconnect\(\)/, "không ngắt observer khi rời trang");
  assert.ok(!/scrollY/.test(codeOnly(dock())), "trinh phat noi tu doc scrollY");
});

test("trinh phat noi + thanh nho chua cho o cuoi trang de khong che chan trang", () => {
  // Trinh phat noi: dem = chieu cao THAT (ResizeObserver), khong so doan.
  const t = trang();
  assert.match(t, /body\.classList\.add\("co-dock"\)/);
  assert.match(t, /body\.classList\.remove\("co-dock"\)/, "không dọn lớp khi rời trang");
  assert.match(t, /new ResizeObserver\(/);
  assert.match(css(), /body\.co-dock \{ padding-bottom: var\(--dock-cao, \d+px\); \}/);
  // Thanh toan tuyen giu co che cu.
  assert.match(globalMini(), /classList\.toggle\("co-mini", hien\)/);
  assert.match(globalMini(), /classList\.remove\("co-mini"\)/);
  assert.match(css(), /body\.co-mini \{ padding-bottom: \d+px; \}/);
});

/* ======================================================= tiep can */

test("moi dieu khien deu la nut/thanh truot THAT", () => {
  // `codeOnly`: chu thich co trich `<div onClick>` de noi vi sao KHONG dung no.
  for (const [ten, src] of [["ChapterPlayer", codeOnly(hero())],
                            ["ChapterAudioDock", codeOnly(dock())]]) {
    assert.match(src, /<button\s+[\s\S]*?type="button"/, `${ten} thiếu <button>`);
    assert.ok(!/<div[^>]*onClick/.test(src), `${ten} dùng <div onClick>`);
  }
  // Tua bang `<input type=range>`: mui ten tua duoc, Home/End nhay dau/cuoi,
  // trinh doc man hinh doc ra dung la mot thanh truot.
  assert.match(hero(), /className="seek"[\s\S]*?type="range"/);
  assert.match(dock(), /className="seek dock-seek-range"[\s\S]*?type="range"/);
});

test("moi dieu khien co ten doc duoc", () => {
  assert.match(hero(), /aria-label=\{t\.dangPhat \? "Tạm dừng" : "Phát"\}/);
  assert.match(dock(), /aria-label=\{dangPhat \? "Tạm dừng" : "Phát"\}/);
  for (const [ten, src] of [["ChapterPlayer", hero()], ["ChapterAudioDock", dock()]]) {
    assert.match(src, /aria-label="Vị trí phát"/, `${ten} thanh tua thiếu tên`);
    assert.match(src, /aria-valuetext=/, `${ten} thanh tua không đọc ra được giờ`);
    for (const nhan of ["Lùi 10 giây", "Tới 10 giây", "Chương trước", "Chương sau", "Tốc độ phát"]) {
      assert.ok(src.includes(`aria-label="${nhan}"`), `${ten} thiếu nút "${nhan}"`);
    }
  }
  assert.match(hero(), /aria-label="Âm lượng"/);
  assert.match(dock(), /aria-label="Thu nhỏ trình phát"/);
  assert.match(dock(), /aria-label="Mở rộng trình phát"/);
  // Phim tat duoc khai bao cho trinh doc man hinh.
  assert.match(dock(), /aria-keyshortcuts="k"/);
});

test("trang thai KHONG chi dua vao mau", () => {
  // Mot dong chu noi dang o trang thai nao — trinh doc man hinh doc ra duoc,
  // va nguoi khong phan biet duoc mau van hieu.
  const src = hero();
  assert.match(src, /role="status"/);
  for (const chu of ["Đang phát", "Đang tạm dừng", "Sẵn sàng phát",
                     "Đã nghe hết chương", "Đang chuẩn bị"]) {
    assert.ok(src.includes(chu), `thiếu trạng thái: ${chu}`);
  }
  assert.match(dock(), /role="status"/);
  // Gio hien duoi dang CHU o ca hai trinh phat.
  assert.match(src, /dongHo\(t\.thoiDiem\)/);
  assert.match(dock(), /dongHo\(thoiDiem\)/);
});

test("vung doc to cua trinh phat noi KHONG doi moi giay", () => {
  // `role="status"` doc to MOI lan doi chu; kem gio vao do la trinh doc man
  // hinh noi lien tuc suot chuong.
  const src = codeOnly(dock());
  const khoi = src.slice(src.indexOf("const trangThaiChu"), src.indexOf("const nutPhat"));
  assert.ok(!/dongHo\(/.test(khoi), "dòng trạng thái đọc to lại kèm giờ");
});

test("nut bi khoa khi chua the phat", () => {
  assert.match(hero(), /const chua_the_bam = t\.dangTai \|\| !t\.tep;/);
  assert.match(hero(), /disabled=\{chua_the_bam\}/);
});

/* ================================================= dong ho */

test("dongHo doi giay thanh chu doc duoc", async () => {
  // Nam o `lib/time.ts`, mot tep KHONG import gi ca: Node khong nap duoc
  // `.tsx`, va `lib/audio.ts` thi keo theo `./api` khong co duoi tep.
  const { dongHo } = await import("../src/lib/time.ts");
  assert.equal(dongHo(0), "0:00");
  assert.equal(dongHo(9), "0:09");
  assert.equal(dongHo(83), "1:23");
  assert.equal(dongHo(600), "10:00");
  assert.equal(dongHo(3661), "1:01:01");
  // Chua biet thoi luong thi noi ro la chua biet, khong hien "0:00".
  assert.equal(dongHo(NaN), "--:--");
  assert.equal(dongHo(Infinity), "--:--");
  assert.equal(dongHo(-1), "--:--");
});

/* ================================================= bo cuc trang doc */

test("khu nghe rong hon cot chu", () => {
  // Cot chu hep de doc de; khu nghe la mot cai the, va mot cai the hep bang
  // cot chu trong nhu bi ep.
  const text = css();
  const nghe = Number(text.match(/\.listen-col \{ max-width: (\d+)px; \}/)?.[1] ?? 0);
  const chu = Number(text.match(/\.reader \{[\s\S]{0,120}?max-width: (\d+)px/)?.[1] ?? 0);
  assert.ok(nghe > chu, `khu nghe ${nghe}px không rộng hơn cột chữ ${chu}px`);
});

test("nut phat lon hon nut thuong, va du vung bam", () => {
  const src = css();
  const at = src.indexOf(".play-btn {");
  const than = src.slice(at, src.indexOf("}", at));
  const w = Number(than.match(/width: (\d+)px/)?.[1] ?? 0);
  assert.ok(w >= 56, `nút phát ${w}px — phải là điều khiển mạnh nhất`);
});

test("trinh phat noi tren dien thoai: moi nut >= 44px, nut phat >= 52px", () => {
  const src = css();
  const at = src.indexOf("TRANG CHUONG THONG NHAT — doc & nghe");
  const khoi = src.slice(at);
  const mobile = khoi.slice(khoi.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.dock-icon-btn \{ width: 44px; height: 44px; \}/);
  assert.match(mobile, /\.dock-play \{ width: 52px; height: 52px; \}/);
  // Chua vung an toan duoi (thanh home cua iPhone).
  assert.match(khoi, /env\(safe-area-inset-bottom\)/);
});

/*
 * Trinh phat cua trang doc chuong.
 *
 * RANG BUOC QUAN TRONG NHAT: MOT the `<audio>` duy nhat. Trinh phat lon o dau
 * trang va thanh nho dinh o duoi deu doc cung mot trang thai va goi cung mot
 * bo dieu khien. Tao the thu hai la loi de mac nhat o cho nay — hai the cung
 * phat mot tep thi nguoi dung nghe thanh tieng vong, va bam dung o thanh nay
 * khong dung thanh kia.
 *
 * The `<audio>` VAN la dong co phat. Cai duoc thay chi la lop VE.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const engine = () => read("../src/components/AudioEngine.tsx");
const hero = () => read("../src/components/ChapterPlayer.tsx");
const mini = () => read("../src/components/MiniPlayer.tsx");
const globalMini = () => read("../src/components/GlobalMiniPlayer.tsx");
/** Trang Nghe rieng (overnight Phase 2, Phan 2A) — day la trang goi
    `phat()`/`useAudioEngine()` gio, tach khoi trang doc `/chapters/[id]`. */
const trang = () => read("../src/app/listen/[id]/page.tsx");
const trangDoc = () => read("../src/app/chapters/[id]/page.tsx");
const layout = () => read("../src/app/layout.tsx");
const css = () => read("../src/app/globals.css");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================ MOT the audio, khong phai hai */

test("chi DONG CO moi tao the <audio>", () => {
  assert.match(codeOnly(engine()), /<audio\b/, "động cơ không có thẻ <audio>");
  // `codeOnly`: chu thich cua ca ba tep co trich `<audio controls>` de giai
  // thich vi sao chung KHONG tu tao the — quet ca tep se bat trung loi giai.
  for (const [ten, src] of [
    ["ChapterPlayer", codeOnly(hero())],
    ["MiniPlayer", codeOnly(mini())],
    ["GlobalMiniPlayer", codeOnly(globalMini())],
  ]) {
    assert.ok(
      !/<audio\b/.test(src),
      `${ten} tự tạo thẻ <audio> thứ hai — hai thẻ cùng phát một tệp là tiếng vọng`,
    );
  }
});

test("ca hai trinh phat doc CUNG mot ngu canh, cung dong co toan cuc", () => {
  for (const [ten, src] of [["ChapterPlayer", hero()], ["MiniPlayer", mini()]]) {
    assert.match(src, /useAudioEngine\(\)/, `${ten} không dùng ngữ cảnh chung`);
  }
  // Dong co gio la TOAN CUC, mount mot lan trong layout — bao TRUM ca thanh
  // header/main/footer va thanh phat nho toan tuyen (GlobalMiniPlayer), khong
  // phai chi rieng trang doc chuong. Dieu huong sang trang khac vi vay khong
  // huy dong co: chi `{children}` doi.
  const l = layout();
  const mo = l.indexOf("<AudioEngineProvider");
  const dong = l.indexOf("</AudioEngineProvider>");
  assert.ok(mo !== -1 && dong > mo, "layout không có <AudioEngineProvider>");
  const trong = l.slice(mo, dong);
  assert.match(trong, /\{children\}/, "children nằm ngoài ngữ cảnh audio");
  assert.match(trong, /<GlobalMiniPlayer/, "thanh phát toàn tuyến nằm ngoài ngữ cảnh");
  // Trang Nghe KHONG tu mo mot provider rieng — chi goi `phat()` de bien
  // chuong cua no thanh bai dang phat toan cuc.
  const t = trang();
  assert.ok(!/<AudioEngineProvider/.test(t), "trang Nghe tự mở provider riêng");
  assert.match(t, /useAudioEngine\(\)/, "trang Nghe không lấy điều khiển từ ngữ cảnh chung");
  assert.match(t, /\.phat\(chapter\.chapter_id, chapter\.title\)/, "trang Nghe không gọi phat()");

  // Trang doc (`/chapters/[id]`) gio KHONG con cham toi audio nua — day la
  // rang buoc MOI cua overnight Phase 2 (Phan 2A/2E: doc va nghe la HAI
  // trai nghiem tach biet).
  const d = trangDoc();
  assert.ok(!/useAudioEngine\(\)/.test(d), "trang đọc không được dùng AudioEngine nữa");
  assert.ok(!/\.phat\(/.test(d), "trang đọc không được tự nạp audio nữa");
});

test("nut phat o CA HAI cho deu goi cung mot ham", () => {
  for (const [ten, src] of [["ChapterPlayer", hero()], ["MiniPlayer", mini()]]) {
    assert.match(src, /onClick=\{d\.batTat\}/, `${ten} không gọi batTat chung`);
  }
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
});

test("GlobalMiniPlayer an o dung trang Nghe dang phat, hien o moi noi khac", () => {
  // Ke ca trang doc `/chapters/[id]` (overnight Phase 2: khong con trinh
  // phat rieng nua) — chi trang Nghe `/listen/[id]` moi co ChapterPlayer to.
  const src = globalMini();
  assert.match(src, /usePathname\(/, "không đọc tuyến hiện tại");
  assert.match(
    src,
    /pathname === `\/listen\/\$\{t\.chapterId\}`/,
    "không so sánh với trang Nghe đang phát",
  );
  assert.match(src, /t\.daBatDau && !t\.loi && !oTrangNgheChuongNay/);
});

test("tai MP3 van con, va dung URL tai rieng", () => {
  assert.match(hero(), /href=\{t\.tep\.downloadUrl\}/);
  assert.match(hero(), /download=\{t\.tenTep\}/);
});

test("KHONG tu dong phat", () => {
  // Trinh duyet chan tu dong phat khi chua co tuong tac, va tu phat mot chuong
  // truyen khi nguoi ta vua mo trang la mot hanh vi tho lo.
  const src = codeOnly(engine());
  assert.ok(!/autoPlay|autoplay/.test(src));
  assert.ok(!/useEffect\([^)]*\)\s*=>\s*\{[^}]*\.play\(\)/.test(src));
});

/* ================================================= thanh nho: khi nao noi len */

test("thanh nho chi hien khi DA bam phat VA trinh phat lon da khuat", () => {
  const src = mini();
  assert.match(src, /t\.daBatDau && khuat && !t\.loi/);
});

test("biet trinh phat lon con thay khong bang IntersectionObserver", () => {
  // Khong dung `scrollY`: chieu cao dau trang doi theo do dai ten chuong, nen
  // mot con so pixel co dinh se sai o dung nhung chuong co ten dai.
  const src = mini();
  assert.match(src, /new IntersectionObserver\(/);
  assert.match(src, /theo_doi\.disconnect\(\)/, "không ngắt observer khi rời trang");
  assert.ok(!/scrollY/.test(codeOnly(src)), "dùng scrollY thay vì observer");
});

test("thanh nho chua cho o cuoi trang de khong che chan trang", () => {
  assert.match(mini(), /classList\.toggle\("co-mini", hien\)/);
  assert.match(mini(), /classList\.remove\("co-mini"\)/, "không dọn lớp khi rời trang");
  assert.match(css(), /body\.co-mini \{ padding-bottom: \d+px; \}/);
});

/* ======================================================= tiep can */

test("moi dieu khien deu la nut/thanh truot THAT", () => {
  // `codeOnly`: chu thich co trich `<div onClick>` de noi vi sao KHONG dung no.
  for (const [ten, src] of [["ChapterPlayer", codeOnly(hero())],
                            ["MiniPlayer", codeOnly(mini())]]) {
    assert.match(src, /<button\s+[\s\S]*?type="button"/, `${ten} thiếu <button>`);
    assert.ok(!/<div[^>]*onClick/.test(src), `${ten} dùng <div onClick>`);
  }
  // Tua bang `<input type=range>`: mui ten tua duoc, Home/End nhay dau/cuoi,
  // trinh doc man hinh doc ra dung la mot thanh truot.
  assert.match(hero(), /className="seek"[\s\S]*?type="range"/);
  assert.match(mini(), /className="seek mini-seek"[\s\S]*?type="range"/);
});

test("moi dieu khien co ten doc duoc", () => {
  for (const [ten, src] of [["ChapterPlayer", hero()], ["MiniPlayer", mini()]]) {
    assert.match(src, /aria-label=\{t\.dangPhat \? "Tạm dừng" : "Phát"\}/,
      `${ten} nút phát không có tên đọc được`);
    assert.match(src, /aria-label="Vị trí phát"/, `${ten} thanh tua thiếu tên`);
    assert.match(src, /aria-valuetext=/, `${ten} thanh tua không đọc ra được giờ`);
  }
  assert.match(hero(), /aria-label="Âm lượng"/);
  assert.match(hero(), /aria-label="Tốc độ phát"/);
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
  // Va gio hien duoi dang CHU o ca hai trinh phat.
  assert.match(src, /dongHo\(t\.thoiDiem\)/);
  assert.match(mini(), /dongHo\(t\.thoiDiem\)/);
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

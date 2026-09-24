/*
 * SPRINT UX DOC/NGHE (2026-09-24) — cac bat bien cua trang chuong thong nhat
 * ma logic thuan (chapterSync / followScroll / readerSession / audioFocus,
 * co bai kiem rieng) khong tu chung minh duoc: day la noi ghep chung vao
 * giao dien.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const exp = () => read("../src/components/reader/ChapterExperience.tsx");
const dock = () => read("../src/components/reader/ChapterAudioDock.tsx");
const navLink = () => read("../src/components/reader/ChapterNavLink.tsx");
const readerText = () => read("../src/components/reader/ReaderText.tsx");
const css = () => read("../src/app/globals.css");

function tatCaTep(thuMuc) {
  const ra = [];
  for (const ten of readdirSync(thuMuc)) {
    const p = join(thuMuc, ten);
    if (statSync(p).isDirectory()) ra.push(...tatCaTep(p));
    else if (/\.(tsx?|jsx?)$/.test(ten)) ra.push(p);
  }
  return ra;
}

/** Khoi than cua mot `const ten = useCallback(` toi `}, [` ket thuc no. */
function thanHam(src, ten) {
  const a = src.indexOf(`const ${ten} = useCallback(`);
  assert.notEqual(a, -1, `khong thay ${ten}`);
  return src.slice(a, src.indexOf("\n    [", a) > 0 ? src.indexOf("\n    [", a) : a + 1500);
}

test("MOT the <audio> truyen cho CA ung dung — quet MOI tep trong src/", () => {
  const goc = fileURLToPath(new URL("../src/", import.meta.url));
  const coAudioJsx = [];
  const coNewAudio = [];
  for (const tep of tatCaTep(goc)) {
    const src = codeOnly(readFileSync(tep, "utf8"));
    if (/<audio\b/.test(src)) coAudioJsx.push(tep.slice(goc.length).replace(/\\/g, "/"));
    if (/new Audio\(/.test(src)) coNewAudio.push(tep.slice(goc.length).replace(/\\/g, "/"));
  }
  /*
    Ngoai le DUY NHAT: xem truoc cua Media Studio (`/studio/media`) — cong cu
    DUNG video cua nguoi sang tac, dong bo `<video>` + `<audio>` loi doc tren
    mot duong thoi gian (`video-composer.test.mjs`). No khong phat chuong
    truyen cho nguoi doc va khong song tren trang doc/nghe nao.
  */
  assert.deepEqual(coAudioJsx, ["components/AudioEngine.tsx", "components/media/Preview.tsx"],
    "chi AudioEngine duoc ve the <audio> truyen — them the thu hai la tieng vong");
  assert.ok(
    !/useAudioEngine|reader\//.test(read("../src/components/media/Preview.tsx")),
    "xem truoc Media Studio khong duoc dinh vao dong co truyen",
  );
  // Nhac nen (kenh "ambient" cua bo dieu phoi) la am thanh RIENG cua site,
  // khong phai chuong truyen; no nhuong tieng cho giong doc qua `audioFocus`.
  assert.deepEqual(coNewAudio, ["lib/musicStore.ts"]);
});

test("an/hien truyen chu, thu nho trinh phat, doi Nghe <-> Doc+Nghe: KHONG BAO GIO dung audio", () => {
  const src = codeOnly(exp());
  for (const ten of ["doiKhungChu", "doiHienChu", "doiThuNho", "doiTheo"]) {
    const than = thanHam(src, ten);
    assert.ok(!/tamDung|batTat|\.pause\(/.test(than), `${ten} cham vao audio`);
  }
  // Chi chon "Đọc" (chi doc) moi tam dung — va chi chuong NAY, khi dang phat.
  const doiCheDo = thanHam(src, "doiCheDo");
  assert.match(doiCheDo, /if \(m === "read" && laBaiNay && t\.dangPhat\) d\.tamDung\(\);/);
});

test("dieu khien bat buoc co mat, bang tieng Viet", () => {
  const e = exp();
  const d = dock();
  for (const nhan of ["Theo giọng đọc", "Ẩn truyện chữ", "Hiện truyện chữ"]) {
    assert.ok(d.includes(nhan) || e.includes(nhan), `thieu "${nhan}"`);
  }
  assert.match(e, /Tới đoạn đang đọc/);
  assert.match(e, /aria-label="Lên đầu trang"/);
  // Ba che do + ba trang thai khung chu.
  for (const nhan of ['read: "Đọc"', 'read_listen: "Đọc + Nghe"', 'listen: "Nghe"']) {
    assert.ok(e.includes(nhan), `thieu nhan che do ${nhan}`);
  }
  for (const nhan of ['["open", "Mở"]', '["collapsed", "Thu gọn"]', '["closed", "Đóng"]']) {
    assert.ok(e.includes(nhan), `thieu nut khung chu ${nhan}`);
  }
  // Nut nhom co ten + trang thai doc duoc (aria-pressed), khong chi mau.
  assert.match(e, /role="group" aria-label="Chế độ đọc và nghe"/);
  assert.match(e, /role="group" aria-label="Hiển thị truyện chữ"/);
  assert.match(e, /aria-pressed=\{mode === m\}/);
  assert.match(d, /aria-pressed=\{p\.theoBat\}/);
});

test("khung chu dong/thu gon chi AN bang `hidden`, van trong DOM — mo lai tuc thi, SEO van thay", () => {
  const e = exp();
  assert.match(e, /hidden=\{coChu && !hienChuDay\}/);
  assert.match(e, /const hienChuDay = coChu && \(mode !== "listen" \|\| prefs\.khungChu === "open"\);/);
  // Lua chon khung chu duoc NHO (cookie) — mo trang sau van nhu cu.
  assert.match(thanHam(codeOnly(e), "luuPrefs"), /document\.cookie = chuoiGhiCookie\(moi/);
});

test("chuyen chuong CO CHU DICH giu ngu nghia phat", () => {
  const src = codeOnly(exp());
  const giao = thanHam(src, "giaoAudio");
  // Dang phat chuong nay (hoac bam "Nghe tiếp chương sau") + chuong dich co audio -> phat tiep.
  assert.match(giao, /const dangPhatBaiNay = laBaiNay && t\.dangPhat;/);
  assert.match(giao, /if \(\(dangPhatBaiNay \|\| epNghe\) && dich\.has_audio !== false\)/);
  assert.match(giao, /tuPhat: true/);
  // Lien ket may chu ve (dau/cuoi trang) cung giao audio — tru mo tab moi.
  const nl = codeOnly(navLink());
  assert.match(nl, /if \(e\.metaKey \|\| e\.ctrlKey \|\| e\.shiftKey \|\| e\.altKey \|\| e\.button !== 0\) return;/);
  assert.match(nl, /ctx\?\.giaoAudio\(target\)/);
  // Van la lien ket that (next/link), rel prev/next giu nguyen o trang may chu.
  assert.match(nl, /<Link/);
  const page = read("../src/app/chapters/[id]/page.tsx");
  assert.match(page, /rel="prev"/);
  assert.match(page, /rel="next"/);
  // Cuoi chuong: CTA manh "Chương tiếp theo" + "Nghe tiếp chương sau".
  assert.match(exp(), /Chương tiếp theo/);
  assert.match(exp(), /Nghe tiếp chương sau/);
});

test("phim tat: K (va Space o che do Nghe) phat/dung, J/L tua 10s — khong an phim trong o nhap", () => {
  const src = codeOnly(exp());
  const khoi = src.slice(src.indexOf("const khiPhim = (e: KeyboardEvent) =>"));
  const than = khoi.slice(0, khoi.indexOf('window.addEventListener("keydown", khiPhim)'));
  assert.match(than, /tag === "INPUT" \|\| tag === "TEXTAREA" \|\| tag === "SELECT" \|\| dich\?\.isContentEditable/);
  assert.match(than, /k === "k" \|\| k === "K" \|\| \(k === " " && mode === "listen"/);
  assert.match(than, /d\.tuaTuongDoi\(-10\)/);
  assert.match(than, /d\.tuaTuongDoi\(10\)/);
  // Dang phat chuong KHAC: phim tat dieu khien cai dang phat, khong tu y doi chuong.
  assert.match(than, /if \(banChuongKhac\) d\.batTat\(\);/);
});

test("giam chuyen dong: vach sang khong chuyen tiep/nhip; tu cuon mac dinh tat", () => {
  const c = css();
  const khoi = c.slice(c.indexOf("TRANG CHUONG THONG NHAT — doc & nghe"));
  const rm = khoi.slice(khoi.indexOf("@media (prefers-reduced-motion: reduce)"));
  assert.match(rm.slice(0, 300), /\.reader-para,[\s\S]*?transition: none/);
  // Khong con nhip vo han kieu ban WIP (`para-pulse ... infinite`).
  assert.ok(!/reader-para[^{]*\{[^}]*animation:[^}]*infinite/.test(khoi), "vach sang nhap nhay vo han");
  assert.match(exp(), /cheDoBanDau\(giamChuyenDong, initialPrefs\.theoGiong\)/);
});

test("cham doan KHONG tua ngay — chon doan roi nut 'Nghe từ đoạn này'; boi den chu thi khong chon", () => {
  const r = readerText();
  assert.match(r, /Nghe từ đoạn này/);
  assert.match(r, /sel\.toString\(\)\.trim\(\)\.length > 0\) return;/);
  assert.match(r, /onClick=\{canSeek \? \(\) => onSelect\(i\) : undefined\}/);
  // Doan memo: vach sang doi chi ve lai hai doan.
  assert.match(r, /const Doan = memo\(/);
});

test("trinh phat noi: DAC (khong qua trong), vua ngon cai, co cho cho iPhone", () => {
  const c = css();
  const khoi = c.slice(c.indexOf("TRANG CHUONG THONG NHAT — doc & nghe"));
  const dockRule = khoi.slice(khoi.indexOf("\n.dock {"), khoi.indexOf("}", khoi.indexOf("\n.dock {")));
  const nen = dockRule.match(/background: #([0-9a-f]{6})([0-9a-f]{2})/);
  assert.ok(nen, "trinh phat noi phai co nen mau dac co alpha ro rang");
  assert.ok(parseInt(nen[2], 16) >= 0xe6, `nen trinh phat qua trong (alpha ${nen[2]})`);
  // Cot chu cung giu nen gan dac nhu truoc (>= 0xe0).
  assert.match(c, /\.reader \{[\s\S]{0,200}?background: linear-gradient\(180deg, #070912e0, #070912f2/);
});

test("trinh phat noi + nut noi di qua PORTAL vao <body> — to tien co transform khong bat duoc chung", () => {
  // Do that tren trinh duyet: `.page` giu `transform` sau hoat anh vao trang,
  // va `position: fixed` ben trong no nam o CUOI trang thay vi day man hinh.
  const src = codeOnly(exp());
  assert.match(src, /import \{ createPortal \} from "react-dom";/);
  assert.match(src, /daMount && coTrinhPhatNoi \? createPortal\(\s*<ChapterAudioDock/);
  assert.match(src, /daMount && \(huongNut \|\| xaDau\) \? createPortal\(\s*<div className="reader-chips"/);
  assert.equal((src.match(/document\.body,/g) ?? []).length, 2);
});

test("tai nghe / man hinh khoa: chuong truoc/sau + tua, qua Media Session", () => {
  const e = exp();
  assert.match(e, /dat\("previoustrack", prev \? \(\) => sangChuong\(prev, true\) : null\)/);
  assert.match(e, /dat\("nexttrack", next \? \(\) => sangChuong\(next, true\) : null\)/);
  const eng = read("../src/components/AudioEngine.tsx");
  for (const h of ["play", "pause", "seekbackward", "seekforward", "seekto"]) {
    assert.ok(eng.includes(`dat("${h}"`), `engine thieu hanh dong ${h}`);
  }
  assert.match(eng, /navigator\.mediaSession\.metadata = new MediaMetadata\(/);
});

test("bao cao nghe CHI cho chuong dang phat — khong tinh nham audio cua chuong khac", () => {
  // Dang doc chuong 7 trong khi nghe chuong 5: ListenReporter(chuong 7) khong
  // duoc dem giay cua chuong 5.
  assert.match(exp(), /\{laBaiNay && hasAudio \? \(\s*<>\s*<ListenReporter chapterId=\{chapterId\} \/>/);
});

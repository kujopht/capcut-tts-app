/*
 * SOCIAL & PLAY V1 — PR B: an nhac bang MOT co, hub Giai tri noi that, Audio
 * Studio chong tao trung va dung thu tu thao tac.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { GAMES, nhanCheDo } from "../src/lib/games.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
/** Bo chu thich truoc khi khang dinh mot thu KHONG co mat (chu thich hay nhac chinh no). */
const chiMa = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");

test("co nhac: MOT diem cau hinh, mac dinh TAT", () => {
  const f = read("../src/lib/features.ts");
  assert.match(f, /export const MUSIC_ENABLED = process\.env\.NEXT_PUBLIC_MUSIC_ENABLED === "1";/);
});

test("musicStore: nhac tat thi khong phat, khong dang ky kenh ambient, khong lo ra window", () => {
  const s = read("../src/lib/musicStore.ts");
  assert.match(s, /private startTrack\(resume = false\) \{[\s\S]{0,300}if \(!MUSIC_ENABLED\) return;\s*this\.initAudio\(\);/);
  assert.match(s, /public togglePlay = \(\) => \{[\s\S]{0,200}if \(!MUSIC_ENABLED\) return;/);
  assert.match(s, /public play = \(\) => \{\s*if \(!MUSIC_ENABLED\) return;/);
  // dang ky kenh + window CHI trong nhanh bat
  const khoi = s.slice(s.indexOf("if (MUSIC_ENABLED) {"));
  assert.match(khoi, /^if \(MUSIC_ENABLED\) \{\s*audioFocus\.dangKy\("ambient"/);
  assert.match(khoi, /\(window as any\)\.musicStore = musicStore;/);
  assert.equal((s.match(/audioFocus\.dangKy\(/g) ?? []).length, 1);
});

test("khong gan widget nhac khi tat: ticker loi bai hat, khung song header, song mini nav", () => {
  assert.match(read("../src/app/layout.tsx"), /\{MUSIC_ENABLED \? <LiveLyricTicker \/> : null\}/);
  const h = read("../src/components/SiteHeader.tsx");
  assert.match(h, /\{MUSIC_ENABLED \? <DockSoundwaveFrame \/> : null\}/);
  assert.match(h, /if \(MUSIC_ENABLED && typeof window !== "undefined"\) \{\s*\(window as unknown as \{ __musicStore: unknown \}\)\.__musicStore = musicStore;/);
  assert.match(read("../src/components/NavAuth.tsx"), /\{MUSIC_ENABLED && link\.href === "\/entertainment" \? <SoundwaveMini \/> : null\}/);
});

test("trang Giai tri: trinh phat nhac CHI khi bat; the trang chu khong hua kho nhac", () => {
  const p = read("../src/app/entertainment/page.tsx");
  assert.match(p, /\{MUSIC_ENABLED \? \(\s*<MusicSection \/>\s*\) : \(\s*<p className="hint gt-nhac-sau">Âm nhạc — sẽ quay lại sau\.<\/p>/);
  assert.ok(!chiMa(p).includes("musicStore"), "trang hub không được đụng musicStore trực tiếp");
  // Tai luoi: khong import tinh MusicSection (no se vao goi JS ban dau du khong render).
  assert.ok(!/^import \{ MusicSection \}/m.test(p));
  assert.match(p, /const MusicSection = dynamic\(\s*\(\) => import\("@\/components\/entertainment\/MusicSection"\)/);
  assert.ok(!/đang online|online/i.test(chiMa(p)), "không có số 'đang online' nào không đọc từ trạng thái sống");
  const home = read("../src/app/page.tsx");
  assert.match(home, /\{MUSIC_ENABLED \? "Âm Nhạc" : "Giải trí"\}/);
  // Icon tai nghe goi am nhac — khi nhac tat, the dung tay cam game.
  assert.match(home, /\{MUSIC_ENABLED \? <IconHeadphones size=\{20\} \/> : <IconGamepad size=\{20\} \/>\}/);
  // Ma trinh phat cu van con (khong xoa), tach nguyen van ra MusicSection.
  const ms = read("../src/components/entertainment/MusicSection.tsx");
  assert.match(ms, /export function MusicSection\(\)/);
  assert.match(ms, /aria-label="Trình phát nhạc Fantasy"/);
});

test("the game noi that: che do, so nguoi, thoi luong, XP", () => {
  assert.ok(GAMES.length >= 2);
  for (const g of GAMES) {
    assert.ok(["solo", "phong", "may-va-phong"].includes(g.cheDo), g.id);
    assert.ok(g.nguoiChoi && g.thoiLuong, g.id);
    assert.ok(g.xp === null || typeof g.xp === "string", g.id);
    assert.ok(g.iframe || g.href, g.id);
  }
  // Hai game 3D tinh khong noi chuyen voi may chu -> KHONG tinh XP.
  assert.ok(GAMES.filter((g) => g.iframe).every((g) => g.xp === null));
  assert.equal(nhanCheDo("solo"), "Chơi đơn");
  const p = read("../src/app/entertainment/page.tsx");
  // Goi C: dong "Phan thuong" doc tu cau hinh SONG cua may chu (nhanXp), game tinh van "Không tính XP".
  assert.match(p, /<dd>\{nhanXp\(g, mayChuBat\)\}<\/dd>/);
  // iframe CHI gan khi mo; mo game thi tam dung loi doc dang phat.
  assert.match(p, /\{dangChoi \? \(\s*<KhungGame/);
  assert.match(p, /if \(engine\?\.trangThai\.dangPhat\) engine\.dieuKhien\.tamDung\(\);/);
  // MOI loi mo game deu tam dung loi doc: nut trong trang, "Toan man hinh" (tab moi), lien ket.
  assert.equal((p.match(/Toàn màn hình ↗/g) ?? []).length, 2);
  assert.equal((p.match(/target="_blank" rel="noopener noreferrer" className="btn [^"]+" onClick=\{onRoiTrang\}/g) ?? []).length, 2);
  assert.match(p, /<Link href=\{g\.href\} className="btn btn-primary btn-sm" prefetch=\{false\} onClick=\{onRoiTrang\}>/);
  assert.match(p, /const moGame = useCallback\(\s*\(g: GameInfo\) => \{\s*tamDungLoiDoc\(\);/);
});

test("Audio Studio: khoa bam dup trong cung nhip + dung lai chuong khi thu lai", () => {
  const a = read("../src/app/studio/audio/page.tsx");
  assert.match(a, /if \(dangGui\.current\) return;\s*dangGui\.current = true;/);
  assert.match(a, /let chapterId = lanTruoc\.current\?\.khoa === khoa \? lanTruoc\.current\.chapterId : "";/);
  // Doi giong/toc do voi cung van ban -> chuong MOI (the gan day phat theo chapter_id).
  assert.match(a, /const khoa = \[tieuDeThat, vanBan, giong, tocDo\]\.join\("␟"\);/);
  assert.match(a, /if \(!chapterId\) \{[\s\S]*?api\.createChapter\([\s\S]*?lanTruoc\.current = \{ khoa, chapterId \};/);
});

test("tieu de tu sinh: cat o ranh gioi tu, co dau …, khong cat giua chu", async () => {
  const { tieuDeTuVanBan, TRAN_TIEU_DE } = await import("../src/lib/tieuDe.ts");
  assert.equal(tieuDeTuVanBan("  Ngắn  gọn \n thôi "), "Ngắn gọn thôi");
  const dai = "Dữ liệu thử cục bộ. Gió đêm thổi qua rặng tre, ánh trăng rơi trên mặt hồ yên ắng.";
  const t = tieuDeTuVanBan(dai);
  assert.ok(t.endsWith("…") && t.length <= TRAN_TIEU_DE + 1, t);
  assert.ok(dai.startsWith(t.slice(0, -1)), "tiền tố nguyên văn");
  assert.match(dai.slice(t.length - 1), /^[\s,.;:!?]/, "cắt đúng ranh giới từ");
  assert.equal(tieuDeTuVanBan("a".repeat(100)).length, TRAN_TIEU_DE + 1);
  assert.match(read("../src/app/studio/audio/page.tsx"), /const tieuDeThat = tieuDe \|\| tieuDeTuVanBan\(vanBan\);/);
});

test("TtsPanel: van ban la o chinh, dung TRUOC giong; tieu de nam trong 'Tuy chon them'", () => {
  const t = read("../src/components/media/TtsPanel.tsx");
  const iVanBan = t.indexOf('className="input tts-van-ban"');
  const iGiong = t.indexOf("<optgroup");
  const iThem = t.indexOf('<details className="tts-them">');
  const iTieuDe = t.indexOf("Tiêu đề (không bắt buộc)");
  assert.ok(iVanBan > 0 && iVanBan < iGiong, "văn bản trước giọng");
  assert.ok(iThem > iGiong && iTieuDe > iThem, "tiêu đề trong mục thu gọn");
  // Van giu luat cu: khong tu doi giong khi that bai, tran ky tu.
  assert.match(t, /Hệ thống không tự đổi sang giọng khác/);
  assert.match(t, /const MAX_CHARS = 20_000;/);
});

/**
 * Animation Player V2 — Custom Fanfic Controls.
 *
 * Cung phong cach voi cac bai kiem khac trong thu muc nay: doc THANG source
 * va khang dinh cac dac diem quan trong bang regex, khong dung DOM gia lap
 * (repo khong co jsdom/testing-library, khong co loader TypeScript cho
 * `node --test` — xem package.json).
 *
 * DA BO so voi ban goc tren `feature/animation-player-v2-custom-controls`:
 * bai kiem CSP trong `next.config.mjs` va bai kiem khung trang tri
 * `.yt-cinema`. Ca hai thuoc ve nhung phan CHUA CO tren nhanh chinh (nhanh
 * chinh khong cau hinh header CSP, va trang xem giu bo cuc rieng cua no chu
 * khong dung khung "rap chieu"), nen giu lai chi tao ra bai kiem noi doi.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const facadePlayer = () => read("../src/components/YouTubeFacadePlayer.tsx");
const playerControls = () => read("../src/components/YouTubePlayerControls.tsx");
const youtubeIframeApi = () => read("../src/lib/youtubeIframeApi.ts");
const watchPage = () => read("../src/app/animation/watch/[id]/page.tsx");
const globalsCss = () => read("../src/app/globals.css");

// -- Play / Pause -----------------------------------------------------------

test("YouTubeFacadePlayer: togglePlay goi dung playVideo/pauseVideo THAT, khong gia trang thai", () => {
  const src = facadePlayer();
  assert.match(src, /if \(trangThai === "dang-phat"\) p\.pauseVideo\(\);/);
  assert.match(src, /else p\.playVideo\(\);/);
});

test("YouTubeFacadePlayer: video ket thuc thi Phat lai = seekTo(0) + playVideo (khong tu ve nut khac)", () => {
  const src = facadePlayer();
  assert.match(src, /if \(trangThai === "ket-thuc"\) \{\s*p\.seekTo\(0, true\);\s*p\.playVideo\(\);/);
});

test("YouTubePlayerControls: nhan Play/Pause/Phat lai dung trangThai, co aria-label ro rang", () => {
  const src = playerControls();
  assert.match(src, /aria-label=\{\s*trangThai === "ket-thuc"\s*\?\s*"Phát lại"/);
  assert.match(src, /"dang-phat"\s*\?\s*"Tạm dừng"\s*:\s*"Phát"/);
  assert.match(src, /disabled=\{dangTai\}/);
});

// -- Seek ---------------------------------------------------------------

test("YouTubePlayerControls: thanh tien do la input range, seekTo CHI goi luc tha/nha phim (khong spam moi buoc keo)", () => {
  const src = playerControls();
  assert.match(src, /className="yt-controls-seek"/);
  assert.match(src, /onChange=\{\(e\) => \{[\s\S]{0,120}onSeekPreview\(giay\);/);
  assert.match(src, /onMouseUp=\{\(e\) => \{[\s\S]{0,200}onSeekCommit\(giay\)/);
  assert.match(src, /onTouchEnd=\{\(e\) => \{[\s\S]{0,200}onSeekCommit\(giay\)/);
  // Ban phim (mui ten/Home/End/PageUp/PageDown) cung phai "tha" nhu keo chuot.
  assert.match(src, /onKeyUp=\{\(e\) => \{/);
  assert.match(src, /"ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"/);
});

test("YouTubeFacadePlayer: seekPreview CHI cap nhat hien thi cuc bo, seekCommit moi goi player.seekTo", () => {
  const src = facadePlayer();
  assert.match(src, /const seekPreview = useCallback\(\(giay: number\) => setHienTai\(giay\), \[\]\);/);
  assert.match(src, /const seekCommit = useCallback\(\(giay: number\) => \{\s*player\.current\?\.seekTo\(giay, true\);/);
});

// -- Volume ---------------------------------------------------------------

test("YouTubeFacadePlayer: mute/unMute doc THAT tu isMuted(), khong doan tu volume === 0", () => {
  const src = facadePlayer();
  assert.match(src, /if \(p\.isMuted\(\)\) \{\s*p\.unMute\(\);/);
  assert.match(src, /\}\s*else\s*\{\s*p\.mute\(\);/);
});

test("YouTubeFacadePlayer: keo am luong ve 0 tu dong mute, keo len tu unmute (setVolume THAT)", () => {
  const src = facadePlayer();
  assert.match(src, /p\.setVolume\(v\);/);
  assert.match(src, /if \(v === 0\) \{\s*p\.mute\(\);/);
  assert.match(src, /\} else if \(daTat\) \{\s*p\.unMute\(\);/);
});

test("YouTubePlayerControls: input am luong ve 0 khi da tat tieng (khong hien so sai)", () => {
  const src = playerControls();
  assert.match(src, /value=\{daTat \? 0 : amLuong\}/);
  assert.match(src, /aria-label="Âm lượng"/);
});

// -- State sync -------------------------------------------------------------

test("lib/youtubeIframeApi.ts: YT_PLAYER_STATE la hang so THAT tu tai lieu, khong phai so ma thuc rai rac", () => {
  const src = youtubeIframeApi();
  assert.match(src, /UNSTARTED:\s*-1/);
  assert.match(src, /ENDED:\s*0/);
  assert.match(src, /PLAYING:\s*1/);
  assert.match(src, /PAUSED:\s*2/);
  assert.match(src, /BUFFERING:\s*3/);
  assert.match(src, /CUED:\s*5/);
});

test("YouTubeFacadePlayer: onStateChange dung YT_PLAYER_STATE, khong so ma thuc, moi trang thai deu duoc anh xa", () => {
  const src = facadePlayer();
  assert.match(src, /case YT_PLAYER_STATE\.PLAYING:\s*\n\s*setTrangThai\("dang-phat"\)/);
  assert.match(src, /case YT_PLAYER_STATE\.PAUSED:\s*\n\s*setTrangThai\("tam-dung"\)/);
  assert.match(src, /case YT_PLAYER_STATE\.BUFFERING:\s*\n\s*setTrangThai\("dang-tai"\)/);
  assert.match(src, /case YT_PLAYER_STATE\.ENDED:\s*\n\s*setTrangThai\("ket-thuc"\)/);
});

test("YouTubeFacadePlayer: onReady doc getPlayerState()/getDuration()/getVolume()/isMuted() THAT, khong khoi tao gia trinh sai", () => {
  const src = facadePlayer();
  assert.match(src, /setDoDai\(e\.target\.getDuration\(\) \|\| 0\);/);
  assert.match(src, /setAmLuong\(e\.target\.getVolume\(\)\);/);
  assert.match(src, /setDaTat\(e\.target\.isMuted\(\)\);/);
  assert.match(src, /e\.target\.getPlayerState\(\) === YT_PLAYER_STATE\.PLAYING/);
});

test("YouTubeFacadePlayer: thanh tien do cuc bo cap nhat qua interval RIENG, khong lien quan throttle bao cao backend", () => {
  const src = facadePlayer();
  assert.match(src, /const KHOANG_BAO_CAO_GIAY = 10;/);
  assert.match(src, /const KHOANG_CAP_NHAT_CUC_BO_MS = 250;/);
  assert.notEqual(
    src.match(/KHOANG_BAO_CAO_GIAY/g)?.length ?? 0,
    0,
  );
});

// -- Error state --------------------------------------------------------

test("YouTubeFacadePlayer: video loi (onError THAT) go iframe, hien thong bao — khong doan them chi tiet", () => {
  const src = facadePlayer();
  assert.match(src, /onError:\s*\(e\)\s*=>\s*\{/);
  assert.match(src, /const thongDiep = thongBaoLoiVideo\(e\.data\);/);
  assert.match(src, /setGiaiDoan\("loi-video"\);/);
  assert.match(src, /if \(giaiDoan === "loi-video"\)/);
});

test("YouTubeFacadePlayer: API IFrame khong tai duoc thi FALLBACK ve controls goc YouTube, khong bo lai video cau cam", () => {
  const src = facadePlayer();
  assert.match(src, /catch \{[\s\S]{0,400}setGiaiDoan\("loi-api"\);/);
  assert.match(src, /controls:\s*giaiDoan === "san-sang" \? "0" : "1"/);
  assert.match(src, /Bộ điều khiển tuỳ chỉnh không tải được/);
});

test("YouTubeFacadePlayer: 5 giai doan hop le, khong co trang thai gia/lai gia dinh nao khac", () => {
  const src = facadePlayer();
  assert.match(
    src,
    /type GiaiDoan = "facade" \| "khoi-tao" \| "san-sang" \| "loi-api" \| "loi-video";/,
  );
});

// -- Vong doi: DUY NHAT mot noi tao YT.Player -------------------------------

/** Moi tep nguon duoi `src/` (de dem noi `new YT.Player` xuat hien). */
function moiTepNguon(thuMuc) {
  const ra = [];
  for (const ten of readdirSync(thuMuc)) {
    const duong = path.join(thuMuc, ten);
    if (statSync(duong).isDirectory()) ra.push(...moiTepNguon(duong));
    else if (/\.(ts|tsx)$/.test(ten)) ra.push(duong);
  }
  return ra;
}

/** Bo chu thich de chi dem MA THAT (docstring cua chinh trinh phat co nhac
    lai `new YT.Player(...)` khi giai thich kien truc — do khong phai mot noi
    dung trinh phat). */
function boChuThich(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

test("toan bo src/: DUY NHAT mot noi `new YT.Player(...)` — khong co trinh phat thu hai o dau", () => {
  const goc = fileURLToPath(new URL("../src", import.meta.url));
  const noiTao = [];
  for (const tep of moiTepNguon(goc)) {
    const src = boChuThich(readFileSync(tep, "utf8"));
    const so = (src.match(/new YT\.Player\(/g) ?? []).length;
    // `path.sep` la `\` tren Windows — chuan hoa de bai kiem khong phu thuoc
    // he dieu hanh chay CI/may dev.
    const duong = path.relative(goc, tep).split(path.sep).join("/");
    if (so > 0) noiTao.push(`${duong} (${so})`);
  }
  assert.deepEqual(
    noiTao,
    ["components/YouTubeFacadePlayer.tsx (1)"],
    `chi YouTubeFacadePlayer duoc tao YT.Player; tim thay: ${noiTao.join(", ")}`,
  );
});

test("YouTubeFacadePlayer: doi tap/thao trang thi HUY sach — cancelAnimationFrame + clearInterval + destroy", () => {
  const src = facadePlayer();
  // Cleanup dat co `daHuy` TRUOC, de mot `loadYouTubeIframeApi()` dang bay ve
  // khong tao ra mot YT.Player mo coi sau khi component da thao.
  assert.match(src, /daHuy\.current = true;/);
  assert.match(src, /cancelAnimationFrame\(khungCho\.current\)/);
  assert.match(src, /if \(baoTienDo\.current\) clearInterval\(baoTienDo\.current\);/);
  assert.match(src, /if \(capNhatCucBo\.current\) clearInterval\(capNhatCucBo\.current\);/);
  assert.match(src, /player\.current\?\.destroy\?\.\(\);/);
  // Chan o CA hai diem bat dong bo: sau `await`, va trong khung `rAF`.
  assert.match(src, /if \(daHuy\.current\) return;\s*\n\s*setGiaiDoan\("san-sang"\);/);
  assert.match(src, /khungCho\.current = null;\s*\n\s*if \(daHuy\.current\) return;/);
  // StrictMode (dev) chay mount -> cleanup -> mount: phai dat lai `false`,
  // neu khong trinh phat khong bao gio khoi tao duoc trong dev.
  assert.match(src, /daHuy\.current = false;/);
});

test("YouTubeFacadePlayer: callback cua cha di qua ref, khong dong bang closure cu trong interval 10s", () => {
  const src = facadePlayer();
  assert.match(src, /goiLai\.current\.onProgress\?\.\(vt, dd \|\| 0\);/);
  assert.match(src, /goiLai\.current = \{ onPlay, onProgress, onError, onEnded \};/);
});

// -- Bo cuc dap ung (responsive) ---------------------------------------------

test("globals.css: control bar an bot am luong tren man hinh nho, khong vo bo cuc mobile", () => {
  const css = globalsCss();
  assert.match(css, /@media \(max-width: 480px\) \{\s*\.yt-controls-volume \{ display: none; \}/);
});

test("globals.css: khung fullscreen KHONG dat overflow len iframe", () => {
  const css = globalsCss();
  const at = css.indexOf(".yt-cinema-fsframe:fullscreen {");
  assert.ok(at > 0, "không tìm thấy .yt-cinema-fsframe:fullscreen");
  const khoi = css.slice(at, css.indexOf("}", at));
  assert.doesNotMatch(khoi, /overflow:/);
});

// -- Nguon nhung an toan (safe iframe origin) --------------------------------

test("YouTubeFacadePlayer: CHI DUNG MOT iframe THAT SU render cho moi video, khong long iframe trong iframe khac", () => {
  const src = facadePlayer();
  // Dem the JSX THAT (co thuoc tinh id={iframeId}) — bo qua cac lan nhac
  // `<iframe>` trong docstring/comment giai thich kien truc.
  const soLanIframeThat = (src.match(/<iframe\s*\n\s*id=\{iframeId\}/g) ?? []).length;
  assert.equal(soLanIframeThat, 1, "phải có đúng một <iframe id={iframeId}> render thật");
});

test("YouTubeFacadePlayer: chi dung tham so player CHINH THUC (controls/enablejsapi/playsinline/origin/autoplay/rel)", () => {
  const src = facadePlayer();
  const khoiParams = src.slice(src.indexOf("const params = new URLSearchParams"));
  for (const thamSo of ["autoplay", "rel", "playsinline", "enablejsapi", "controls", "origin"]) {
    assert.match(khoiParams, new RegExp(`\\b${thamSo}\\b`), `thiếu tham số ${thamSo}`);
  }
});

test("YouTubeFacadePlayer: allow list co fullscreen (Fullscreen API cua trinh duyet, khong phai API cua YouTube)", () => {
  assert.match(facadePlayer(), /allow="[^"]*\bfullscreen\b[^"]*"/);
});

test("YouTubeFacadePlayer: thanh dieu khien Fanfic KHONG BAO GIO dat position de len tren iframe (docstring xac nhan)", () => {
  const src = facadePlayer();
  assert.match(src, /KHONG BAO GIO dat phan tu nao \(bao gom `\.yt-controls`\) DE LEN TREN iframe/);
});

test("animation/watch/[id]/page.tsx: trang xem khong con giu ref/interval YT.Player nao (chuyen het vao component)", () => {
  const src = watchPage();
  assert.doesNotMatch(src, /loadYouTubeIframeApi/);
  assert.doesNotMatch(src, /YTPlayerInstance/);
  assert.doesNotMatch(src, /IFRAME_ID/);
  assert.match(src, /onProgress=\{onProgress\}/);
  // Doi tap = doi CA trinh phat, khong doi `src` cua mot iframe dang song.
  assert.match(src, /key=\{`\$\{episode\.episode_id\}:\$\{episode\.external_id\}`\}/);
});

test("animation/watch/[id]/page.tsx: chi nguoi da dang nhap moi ghi tien do xem (giu dung hanh vi V1)", () => {
  const src = watchPage();
  assert.match(src, /if \(!profile \|\| !data\) return;/);
  assert.match(src, /api\s*\n?\s*\.reportWatchProgress\(/);
});

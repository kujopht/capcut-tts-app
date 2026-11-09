/*
 * INK SCOUT — KIỂM TĨNH: cờ build mặc định TẮT, không rò sang production, tải lười, không có thứ nguy hiểm trong mã game, lõi tất định, phân lớp,
 * `<Link>` không prefetch, tiền tố CSS, nút chạm đủ lớn, không dùng tên/tài sản của game khác.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = fileURLToPath(new URL("../", import.meta.url));
const read = (p) => readFileSync(join(WEB, p), "utf8").replace(/\r\n/g, "\n");
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const GAME_DIR = join(WEB, "src/game/inkscout");
const gameFiles = walk(GAME_DIR);
const code = gameFiles.filter((f) => /\.(ts|tsx)$/.test(f));

test("cờ build GAME_INK_SCOUT_ENABLED: một điểm cấu hình, mặc định TẮT", () => {
  assert.match(read("src/lib/features.ts"), /export const GAME_INK_SCOUT_ENABLED = process\.env\.NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED === "1";/);
});

test("cờ KHÔNG được bật ở bất kỳ cấu hình triển khai nào (workflow, wrangler, next.config)", () => {
  const roots = [join(WEB, "..", ".github", "workflows")];
  const files = [];
  for (const r of roots) if (existsSync(r)) for (const f of readdirSync(r)) files.push(join(r, f));
  for (const f of readdirSync(WEB)) if (/^wrangler.*\.jsonc?$/.test(f) || /^next\.config\./.test(f) || /^open-next\.config\./.test(f)) files.push(join(WEB, f));
  assert.ok(files.length > 0);
  for (const f of files) assert.ok(!/GAME_INK_SCOUT/.test(readFileSync(f, "utf8")), `${relative(WEB, f)} nhắc tới cờ game — không được bật production`);
});

test("route: cờ tắt ⇒ chỉ một thông báo tĩnh, không tải mã game; noindex", () => {
  const p = read("src/app/entertainment/ink-scout/page.tsx");
  assert.match(p, /if \(!GAME_INK_SCOUT_ENABLED\) \{[\s\S]*?Game này chưa mở[\s\S]*?\}\s*return <InkScoutLoader \/>;/);
  assert.match(p, /robots: \{ index: false, follow: false \}/);
  assert.ok(!/^import .*InkScoutShell/m.test(p), "route không import vỏ trực tiếp");
});

test("Giải trí: thẻ Ink Scout chỉ nối vào danh sách khi cờ bật; games.ts không import giá trị (an toàn cho test Node)", () => {
  const hub = read("src/app/entertainment/page.tsx");
  assert.match(hub, /const DANH_SACH: readonly GameInfo\[\] = GAME_INK_SCOUT_ENABLED \? \[\.\.\.GAMES, INK_SCOUT_GAME\] : GAMES;/);
  assert.match(hub, /\{DANH_SACH\.map\(\(g\) => \(/);
  const games = read("src/lib/games.ts");
  assert.ok(!/^import /m.test(stripComments(games)), "games.ts chỉ chứa dữ liệu");
  assert.match(games, /href: "\/entertainment\/ink-scout"/);
  assert.match(games, /xp: null,\s*\n\s*href: "\/entertainment\/ink-scout"/);
});

test("tải lười: vỏ chỉ import() runtime khi bấm Chơi; không import tĩnh lõi nặng/render/âm thanh; chỉ route game import vỏ", () => {
  const shell = stripComments(read("src/game/inkscout/ui/InkScoutShell.tsx"));
  assert.match(shell, /await import\("\.\.\/platform\/runtime"\)/);
  for (const bad of ["../platform/runtime", "../render/", "../core/game", "../core/boss", "../core/rooms", "../core/enemies", "../core/player", "../platform/audio"]) {
    const re = new RegExp(`^import (?!type)[^\\n]*from "${bad.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "m");
    assert.ok(!re.test(shell), `vỏ không được import tĩnh ${bad}`);
  }
  assert.match(read("src/game/inkscout/ui/InkScoutLoader.tsx"), /dynamic\(\(\) => import\("\.\/InkScoutShell"\), \{\s*ssr: false/);
  // Không nơi nào khác trong src (ngoài src/game và route game) kéo mã game vào gói.
  const offenders = walk(join(WEB, "src"))
    .filter((f) => /\.(ts|tsx)$/.test(f) && !f.startsWith(GAME_DIR))
    .filter((f) => /(?:from|import\()\s*["'][^"']*game\/inkscout/.test(readFileSync(f, "utf8")) && !f.endsWith(join("entertainment", "ink-scout", "page.tsx")))
    .map((f) => relative(WEB, f));
  assert.deepEqual(offenders, []);
});

test("bảo mật: không eval/Function/HTML động/mạng/khoá/Appwrite trong mã game; localStorage chỉ ở platform/storage", () => {
  const banned = [
    [/\beval\s*\(/, "eval"],
    [/new Function\s*\(/, "new Function"],
    [/dangerouslySetInnerHTML/, "dangerouslySetInnerHTML"],
    [/\.innerHTML\b/, "innerHTML"],
    [/\.outerHTML\b/, "outerHTML"],
    [/document\.write/, "document.write"],
    [/\bfetch\s*\(/, "fetch"],
    [/XMLHttpRequest/, "XMLHttpRequest"],
    [/\bWebSocket\b/, "WebSocket"],
    [/\bEventSource\b/, "EventSource"],
    [/sendBeacon/, "sendBeacon"],
    [/appwrite/i, "appwrite"],
    [/@\/lib\/api|\/lib\/auth|getToken/, "API/auth của site"],
    [/process\.env/, "process.env"],
    [/importScripts|new Worker\s*\(|SharedWorker/, "worker"],
    [/\bsetInterval\s*\(/, "setInterval"],
  ];
  for (const f of code) {
    const src = stripComments(readFileSync(f, "utf8"));
    for (const [re, what] of banned) assert.ok(!re.test(src), `${relative(WEB, f)} chứa ${what}`);
    if (/localStorage/.test(src)) assert.ok(f.endsWith(join("platform", "storage.ts")), `${relative(WEB, f)} dùng localStorage ngoài storage.ts`);
  }
});

test("lõi tất định và đứng một mình: không Math.random/Date/hẹn giờ/DOM; không import render/platform/ui", () => {
  const core = code.filter((f) => f.startsWith(join(GAME_DIR, "core")));
  assert.ok(core.length >= 12);
  for (const f of core) {
    const src = stripComments(readFileSync(f, "utf8"));
    for (const re of [/Math\.random/, /Date\.now|new Date\(/, /performance\.now/, /setTimeout|setInterval|requestAnimationFrame/, /\bdocument\b|\bwindow\b|\bnavigator\b|localStorage/]) {
      assert.ok(!re.test(src), `${relative(WEB, f)} vi phạm tính tất định/độc lập: ${re}`);
    }
    assert.ok(!/from "\.\.\/(render|platform|ui)\//.test(src), `${relative(WEB, f)} import lớp ngoài`);
  }
});

test("<Link> trong game có prefetch={false} (không prefetch tuyến tĩnh)", () => {
  for (const f of code.filter((x) => x.endsWith(".tsx"))) {
    const src = readFileSync(f, "utf8");
    for (const m of src.matchAll(/<Link\b[^>]*>/g)) assert.match(m[0], /prefetch=\{false\}/, `${relative(WEB, f)}: ${m[0]}`);
  }
  assert.match(read("src/app/entertainment/ink-scout/page.tsx"), /<Link href="\/entertainment" prefetch=\{false\}/);
});

test("CSS: mọi selector có tiền tố isc-; nút chạm chính ≥ 56 px, nút tạm dừng ≥ 44 px; vùng an toàn + không cuộn", () => {
  const css = read("src/game/inkscout/ui/inkscout.css");
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const selectors = [...bare.matchAll(/(?:^|\})\s*([^{}@]+)\{/gm)].map((m) => m[1].trim()).filter(Boolean);
  for (const sel of selectors) {
    for (const part of sel.split(",")) {
      const p = part.trim();
      if (!p) continue;
      assert.ok(/\.isc-/.test(p) || /^(html|body)\b/.test(p) && /isc-lock/.test(p) || /^(from|to|\d+%)$/.test(p), `selector ngoài tiền tố: ${p}`);
    }
  }
  for (const cls of ["jump", "attack", "pulse", "dash"]) {
    const m = css.match(new RegExp(`\\.isc-tb-${cls} \\{[^}]*?width: (\\d+)px;[^}]*?height: (\\d+)px;`));
    assert.ok(m && Number(m[1]) >= 56 && Number(m[2]) >= 56, `nút ${cls} phải ≥ 56 px`);
  }
  assert.match(css, /\.isc-tb-pause \{[^}]*width: 48px;[^}]*height: 48px;/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
  assert.match(css, /touch-action: none;/);
  assert.match(css, /overscroll-behavior: none;/);
  const touch = read("src/game/inkscout/ui/TouchControls.tsx");
  assert.match(touch, /onPointerDown/);
  assert.match(touch, /onLostPointerCapture/);
  assert.match(touch, /setPointerCapture/);
});

test("trợ năng: canvas có nhãn, hộp thoại có role/aria-modal, nút tạm dừng có nhãn, có lựa chọn giảm rung", () => {
  const shell = read("src/game/inkscout/ui/InkScoutShell.tsx");
  assert.match(shell, /<canvas[^>]*aria-label=/);
  assert.match(shell, /aria-label="Tạm dừng \(Esc\)"/);
  const overlay = read("src/game/inkscout/ui/StageOverlay.tsx");
  assert.ok((overlay.match(/role="dialog" aria-modal="true"/g) ?? []).length >= 5);
  assert.match(overlay, /Rung màn hình/);
  assert.match(overlay, /\{ v: 0, label: "Tắt" \}/);
});

test("nguyên bản: không dùng tên/nhân vật/tài sản của game tham chiếu", () => {
  const banned = /hollow\s*knight|silksong|hornet|team\s*cherry|hallownest|pharloom|zote|the knight\b/i;
  for (const f of gameFiles) {
    if (!/\.(ts|tsx|css|mjs)$/.test(f)) continue;
    assert.ok(!banned.test(readFileSync(f, "utf8")), `${relative(WEB, f)} nhắc tên game tham chiếu`);
  }
  // Mọi tài sản ảnh trong game lấy từ kho có sẵn (linh vật Ink Scout) — không thêm tệp nhị phân mới.
  assert.ok(gameFiles.every((f) => !/\.(png|jpe?g|gif|webp|mp3|ogg|wav|woff2?)$/i.test(f)), "không có tệp nhị phân trong src/game");
});

test("save: chỉ cục bộ, một khoá có phiên bản, có sanitize khi đọc", () => {
  const storage = read("src/game/inkscout/platform/storage.ts");
  assert.match(storage, /window\.localStorage\.getItem\(this\.key\)/);
  assert.match(storage, /sanitizeSave\(JSON\.parse\(raw\)\)/);
  assert.match(read("src/game/inkscout/core/save.ts"), /export const SAVE_KEY = "fanfic\.inkscout\.lostchapter\.v1";/);
  // Không chạm schema Appwrite / không có bảng mới.
  assert.ok(!existsSync(join(WEB, "..", "server", "appwrite_ink_scout")), "không có schema Appwrite riêng");
});

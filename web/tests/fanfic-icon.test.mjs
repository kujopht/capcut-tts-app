// Kiem tra tinh (khong render) bo bieu tuong FanficIcon (Icons8 Line Awesome
// vendor hoa) va cac mat migrate uu tien.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, "..", "src");
const PKG_JSON = path.join(__dirname, "..", "package.json");
const GENERATED = path.join(SRC, "components", "icons", "lineAwesome.generated.ts");
const LICENSE = path.join(SRC, "components", "icons", "LINE_AWESOME_LICENSE.md");

function timTepTsx(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) timTepTsx(p, out);
    else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) out.push(p);
  }
  return out;
}

const CAC_TEP_TSX = timTepTsx(SRC);
const noiDungTep = new Map(CAC_TEP_TSX.map((f) => [f, readFileSync(f, "utf8")]));

const NHUNG_MAT_CAN_CO = [
  "home", "community", "library", "studio", "search", "notification",
  "message", "profile", "settings", "admin", "audio", "book", "image",
  "upload", "download", "play", "pause", "like", "comment", "share",
  "report", "block", "mute", "game", "trophy", "leaderboard", "level",
  "ai", "support", "sticker", "emoji", "close", "send", "stop", "refresh",
  "history", "plus", "menu", "chevron-down", "chevron-left",
  "external-link", "trash",
];

test("moi ten icon trong bang loi ket duong dan (viewBox + path)", () => {
  const noiDung = readFileSync(GENERATED, "utf8");
  const banGhi = {};
  for (const m of noiDung.matchAll(/"([a-z0-9-]+)":\s*\{\s*viewBox:\s*"([^"]+)",\s*path:\s*"([^"]+)"\s*\}/g)) {
    banGhi[m[1]] = { viewBox: m[2], path: m[3] };
  }
  for (const ten of NHUNG_MAT_CAN_CO) {
    assert.ok(banGhi[ten], `thieu icon "${ten}" trong lineAwesome.generated.ts`);
    assert.ok(banGhi[ten].viewBox.length > 0, `icon "${ten}" thieu viewBox`);
    assert.ok(banGhi[ten].path.length > 0, `icon "${ten}" thieu path`);
  }
});

test("co tep giay phep Line Awesome canh module sinh ra", () => {
  const noiDung = readFileSync(LICENSE, "utf8");
  assert.match(noiDung, /Good Boy License|MIT/i);
});

test("khong tai icon qua CDN Icons8 (chi vendor tinh)", () => {
  for (const [f, noiDung] of noiDungTep) {
    assert.ok(
      !/icons8\.com|img\.icons8\.com/i.test(noiDung),
      `${path.relative(SRC, f)} tham chieu toi CDN icons8 — phai vendor tinh, khong tai qua mang`,
    );
  }
});

test("khong them line-awesome vao package.json (chi vendor du lieu path)", () => {
  const pkg = JSON.parse(readFileSync(PKG_JSON, "utf8"));
  const moiPhuThuoc = { ...pkg.dependencies, ...pkg.devDependencies };
  assert.ok(!("line-awesome" in moiPhuThuoc), "line-awesome khong duoc la mot dependency runtime/dev");
});

const BE_MAT_UU_TIEN = [
  "components/NavAuth.tsx",
  "components/SiteSearch.tsx",
  "components/NotificationBell.tsx",
  "components/PostCard.tsx",
  "components/ChapterComments.tsx",
  "components/EpisodeComments.tsx",
  path.join("app", "u", "[username]", "page.tsx"),
  "components/StudioShell.tsx",
  "components/chat/ChatLauncher.tsx",
  "components/chat/ChatDock.tsx",
  "components/chat/ChatWindow.tsx",
  "components/chat/ConversationList.tsx",
  "components/chat/ChatThreadMenu.tsx",
  "components/chat/ChatComposer.tsx",
];

test("cac be mat da migrate deu import FanficIcon", () => {
  for (const rel of BE_MAT_UU_TIEN) {
    const f = path.join(SRC, rel);
    const noiDung = readFileSync(f, "utf8");
    assert.match(
      noiDung,
      /from "@\/components\/icons\/FanficIcon"/,
      `${rel} phai import FanficIcon`,
    );
  }
});

test("Chat V1: cac aria-label/title goc van con nguyen (icon swap thuan tuy)", () => {
  const doc = (rel) => readFileSync(path.join(SRC, rel), "utf8");

  assert.match(doc("components/chat/ChatLauncher.tsx"), /aria-label=\{unreadTotal > 0 \? `Tin nhắn/);
  assert.match(doc("components/chat/ChatDock.tsx"), /aria-label=\{`Đóng cuộc trò chuyện với \$\{ten\}`\}/);
  assert.match(doc("components/chat/ChatWindow.tsx"), /aria-label=\{`Đóng cuộc trò chuyện với \$\{ten\}`\}/);
  assert.match(doc("components/chat/ConversationList.tsx"), /title="Đã tắt thông báo"/);
  assert.match(doc("components/chat/ChatThreadMenu.tsx"), /Xem hồ sơ/);
  assert.match(doc("components/chat/ChatThreadMenu.tsx"), /Bật thông báo/);
  assert.match(doc("components/chat/ChatThreadMenu.tsx"), /Tắt thông báo/);
  assert.match(doc("components/chat/ChatComposer.tsx"), /aria-label=\{guiDuoc \? "Gửi tin nhắn"/);
});

test("cac be mat da migrate KHONG con emoji cu (💬 🔔 🔕 👤 ✕ ➤)", () => {
  const kiemTraKhongCon = (rel, glyphs) => {
    const noiDung = readFileSync(path.join(SRC, rel), "utf8");
    for (const g of glyphs) {
      assert.ok(!noiDung.includes(g), `${rel} van con glyph cu "${g}"`);
    }
  };
  kiemTraKhongCon("components/chat/ChatLauncher.tsx", ["💬"]);
  kiemTraKhongCon("components/chat/ChatDock.tsx", ["✕"]);
  kiemTraKhongCon("components/chat/ChatWindow.tsx", ["✕"]);
  kiemTraKhongCon("components/chat/ConversationList.tsx", ["🔕"]);
  kiemTraKhongCon("components/chat/ChatThreadMenu.tsx", ["👤"]);
  kiemTraKhongCon("components/chat/ChatComposer.tsx", ["➤"]);
  kiemTraKhongCon("components/NotificationBell.tsx", ["🔔"]);
});

/*
 * Tests for Studio guest UX polish (P1-01, P1-02, P1-03, P1-04):
 * - P1-01: Audio Studio guest experience (creation UI interactive, draft persistence, auth gate on action)
 * - P1-02: /studio/media route identity (title = "Media", back link to Audio, Media not in primary nav)
 * - P1-03: Mobile "Menu Studio" button clipping prevention (flex-shrink: 0, white-space: nowrap)
 * - P1-04: Content guest state (explicit login EmptyState, no auto-redirect or indefinite loading)
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const shell = () => read("../src/components/StudioShell.tsx");
const audio = () => read("../src/app/studio/audio/page.tsx");
const media = () => read("../src/app/studio/media/page.tsx");
const ttsPanel = () => read("../src/components/media/TtsPanel.tsx");
const vietTruyen = () => read("../src/components/studio/VietTruyen.tsx");
const css = () => read("../src/app/globals.css");

const chiMa = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/* ==================================================== P1-01: Audio Guest UX */

test("P1-01: Audio Studio does not block guest users behind a full-page login EmptyState", () => {
  const src = audio();
  // Should NOT early-return an EmptyState when !profile
  assert.ok(!src.includes('if (!profile) return <EmptyState'),
    "Audio Studio must not replace the whole creation workspace with EmptyState");
  // Should render TtsPanel and audio-studio layout unconditionally
  assert.match(src, /<TtsPanel\b/);
  assert.match(src, /className="audio-studio"/);
  assert.match(src, /className="audio-create-pane"/);
});

test("P1-01: Audio Studio loads public voices for guests but gates server jobs behind auth", () => {
  const src = audio();
  // Public voices are fetched unconditionally
  assert.match(src, /api\.voices\(\)/);
  // Draft persistence in sessionStorage on unauthenticated create
  assert.match(src, /sessionStorage\.setItem\("fanfic_audio_draft"/);
  assert.match(src, /loginHref\("\/studio\/audio"\)/);
  // Restores draft on mount
  assert.match(src, /sessionStorage\.getItem\("fanfic_audio_draft"\)/);
});

test("P1-01: TtsPanel accepts initialDraft and restores form fields", () => {
  const src = ttsPanel();
  assert.match(src, /initialDraft\?:/);
  assert.match(src, /initialDraft\?\.tieuDe/);
  assert.match(src, /initialDraft\?\.vanBan/);
  assert.match(src, /initialDraft\?\.tocDo/);
});

test("P1-01: Recent audio section provides guest login prompt card", () => {
  const src = audio();
  assert.match(src, /!profile \?/);
  assert.match(src, /Đăng nhập để xem và quản lý danh sách audio/);
});

/* =============================================== P1-02: Media Route Identity */

test("P1-02: Media is NOT added as a 5th primary destination in StudioShell", () => {
  const s = shell();
  const order = [...s.matchAll(/href: "([^"]+)",\s*\n\s*nhan: "([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ["/studio", "/studio/content", "/studio/audio", "/studio/image"]);
  assert.ok(!order.includes("/studio/media"), "Media must not be in primary navigation");
});

test("P1-02: StudioShell recognizes /studio/media with title 'Media' and back link to Audio", () => {
  const s = shell();
  assert.match(s, /pathname\.startsWith\("\/studio\/media"\)/);
  assert.match(s, /tieuDe = isMedia\s*\?\s*"Media"/);
  assert.match(s, /href="\/studio\/audio"/);
  assert.match(s, /Quay lại Audio Studio/);
});

test("P1-02: Media Studio unauthenticated state includes back link to Audio Studio", () => {
  const m = media();
  assert.match(m, /title="Đăng nhập để mở Media Studio"/);
  assert.match(m, /Quay lại Audio Studio/);
});

/* =============================================== P1-03: Mobile Menu Studio */

test("P1-03: .studio-nut-mobile has flex-shrink: 0 and white-space: nowrap", () => {
  const s = chiMa(css());
  assert.match(s, /\.studio-nut-mobile\s*\{[^}]*flex-shrink:\s*0;/);
  assert.match(s, /\.studio-nut-mobile\s*\{[^}]*white-space:\s*nowrap;/);
});

test("P1-03: .studio-dau layout prevents title overflow and protects menu button", () => {
  const s = chiMa(css());
  assert.match(s, /\.studio-dau\s*\{[^}]*gap:\s*var\(--s3\);/);
  assert.match(s, /\.studio-dau > :first-child\s*\{[^}]*min-width:\s*0;/);
});

/* ============================================== P1-04: Content Guest State */

test("P1-04: VietTruyen does not auto-redirect unauthenticated users with router.replace", () => {
  const src = vietTruyen();
  assert.ok(!src.includes('router.replace(loginHref("/studio/content"))'),
    "VietTruyen must not auto-redirect unauthenticated users");
  assert.ok(!src.includes('label="Đang chuyển tới trang đăng nhập…"'),
    "VietTruyen must not show indefinite redirect loading spinner");
});

test("P1-04: VietTruyen renders explicit EmptyState login prompt for unauthenticated users", () => {
  const src = vietTruyen();
  assert.match(src, /<EmptyState[\s\S]*?icon="✍️"[\s\S]*?title="Đăng nhập để bắt đầu viết truyện"/);
  assert.match(src, /loginHref\("\/studio\/content"\)/);
});

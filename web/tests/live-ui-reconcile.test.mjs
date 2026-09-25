/*
 * DOI SOAT PRODUCTION <-> MAIN (2026-09-25).
 *
 * Production (Cloudflare version 5b855690…) duoc dung tu checkpoint WIP
 * 83b3a3e, KHONG phai tu `main`. Cac tinh nang giao dien dang chay that o do
 * duoc mang ve `main` (nhanh feat/reconcile-live-ui) de lan trien khai `main`
 * tiep theo khong xoa mat chung. Bai nay khoa lai ca hai chieu:
 *   - tinh nang dang chay that phai CON;
 *   - dock doc/nghe WIP (thay the boi Sprint 1) KHONG duoc quay lai.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { isLegacyAudioOnly, novelHeroUrl, novelPortraitUrl } from "../src/lib/catalog.ts";
import { cheDoKhiMo } from "../src/lib/readerSession.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const has = (p) => existsSync(new URL(p, import.meta.url));

test("catalog: nhan dien truyen audio-only cu (13 tac pham nhap tu audio dai tap)", () => {
  assert.equal(isLegacyAudioOnly({ content_mode: "audio_only" }), true);
  assert.equal(isLegacyAudioOnly({ tags: ["long_form_audio"] }), true);
  assert.equal(isLegacyAudioOnly({ tags: ["work:CAT-12"] }), true);
  assert.equal(isLegacyAudioOnly({ tags: ["work:OP-3"] }), true);
  assert.equal(isLegacyAudioOnly({ content_mode: "readable", tags: ["fandom:Naruto"] }), false);
  assert.equal(isLegacyAudioOnly({}), false);
});

test("catalog: anh hero 16:9 roi dan ve bia doc roi ve bia cu; bia doc roi ve bia cu", () => {
  assert.equal(novelHeroUrl({ hero_background_url: "h", cover_portrait_url: "p", cover_url: "c" }), "h");
  assert.equal(novelHeroUrl({ cover_portrait_url: "p", cover_url: "c" }), "p");
  assert.equal(novelHeroUrl({ cover_url: "c" }), "c");
  assert.equal(novelHeroUrl({}), null);
  assert.equal(novelPortraitUrl({ cover_portrait_url: "p", cover_url: "c" }), "p");
  assert.equal(novelPortraitUrl({ cover_url: "c" }), "c");
  assert.equal(novelPortraitUrl({}), null);
});

test("/admin/assets (Bia & Hero 16:9) ton tai va co trong dieu huong quan tri", () => {
  assert.ok(has("../src/app/admin/assets/page.tsx"), "mat trang /admin/assets dang chay tren production");
  assert.match(read("../src/components/AdminShell.tsx"), /\{ href: "\/admin\/assets", nhan: "Bìa & Hero 16:9"/);
  assert.match(read("../src/app/admin/page.tsx"), /href: "\/admin\/assets"/);
  const stories = read("../src/app/admin/stories/page.tsx");
  assert.match(stories, /Tài nguyên/);
  assert.match(stories, /isLegacyAudioOnly\(n\)/);
  assert.match(stories, /Xem công khai ↗/);
});

test("thu vien: bo loc Doc & Nghe, Kho Audio cu (audio_only), sap xep Moi xuat ban, the co hero", async () => {
  /*
    Product UX Sprint 2: logic bo loc chuyen vao `lib/libraryQuery.ts` (thuan)
    nen kiem bang HANH VI thay vi chuoi nguon. Hai sua that so voi ban
    production 5b855690:
      - "Mới xuất bản" gui `sort=newest` (do that: `latest` = y het `updated`);
      - "Có audio" mo ca kho audio cu (`content_mode=all`), "Đọc & nghe" chi
        kho doc duoc CO audio — ban truoc hai lua chon tra ve giong nhau.
  */
  const { thamSoDuyet, MAC_DINH_THU_VIEN, NHAN_SAP_XEP } = await import("../src/lib/libraryQuery.ts");
  const ts = (phan) => thamSoDuyet({ ...MAC_DINH_THU_VIEN, ...phan }, 12);
  assert.equal(ts({}).content_mode, "readable", "mặc định KHÔNG hiện kho audio cũ");
  assert.equal(ts({ audio: "legacy" }).content_mode, "audio_only");
  assert.deepEqual([ts({ audio: "read_audio" }).content_mode, ts({ audio: "read_audio" }).audio], ["readable", true]);
  assert.deepEqual([ts({ audio: "audio" }).content_mode, ts({ audio: "audio" }).audio], ["all", true]);
  assert.equal(ts({ audio: "text" }).audio, false);
  assert.equal(NHAN_SAP_XEP.latest, "Mới xuất bản");
  assert.equal(ts({ sort: "latest" }).sort, "newest");
  const lib = read("../src/app/library/page.tsx");
  assert.match(lib, /nhan: "Đọc & nghe"/);
  assert.match(lib, /nhan: "Kho audio cũ"/);
  assert.match(lib, /heroUrl=\{novelHeroUrl\(n\)\}/);
});

test("trang truyen: nen hero + nut theo che do dung dung tham so ma trang chuong Sprint 1 hieu", () => {
  const page = read("../src/app/novels/[id]/page.tsx");
  assert.match(page, /className="novel-head-backdrop"/);
  assert.match(page, /coverUrl=\{novelPortraitUrl\(novel\)\}/);
  for (const q of ["mode=listen&autoplay=1", "mode=read_listen&autoplay=1", "mode=read"]) {
    assert.ok(page.includes(`?${q}`), `thieu nut ?${q}`);
  }
  // Trang chuong phai hieu dung ba gia tri `mode` do.
  for (const m of ["read", "read_listen", "listen"]) {
    assert.equal(cheDoKhiMo({ tuUrl: m, coAudio: true, coChu: true }), m);
  }
  const chapter = read("../src/app/chapters/[id]/page.tsx");
  assert.match(chapter, /const urlRequestsPlay = sp\.autoplay === "1" \|\| sp\.autoplay === "true";/);
  const css = read("../src/app/globals.css");
  assert.match(css, /\.novel-head-backdrop \{/);
  assert.match(css, /\.novel-head-overlay \{/);
});

test("NovelCover: truyen co hero ma chua co bia van hien anh (loi da ghi o checkpoint 83b3a3e)", () => {
  const src = read("../src/components/NovelCover.tsx");
  assert.match(src, /const anh = isLandscape \? heroUrl \|\| coverUrl : coverUrl;/);
  assert.match(src, /\{anh \? \(/);
  assert.ok(!/\{coverUrl \? \(/.test(src), "anh con bi chan boi coverUrl");
});

test("dock doc/nghe WIP (thay the boi Sprint 1) KHONG quay lai", () => {
  assert.ok(!has("../src/components/ChapterAudioSyncDock.tsx"));
  assert.ok(!has("../src/components/UnifiedChapterExperience.tsx"));
  const css = read("../src/app/globals.css");
  assert.ok(!/\.reader-mode-tabs \{/.test(css), "CSS dock WIP quay lai");
  assert.ok(!/para-pulse/.test(css), "nhip nhay vo han cua WIP quay lai");
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const robotsSrc = readFileSync(new URL("../src/app/robots.ts", import.meta.url), "utf8");
const sitemapSrc = readFileSync(new URL("../src/app/sitemap.ts", import.meta.url), "utf8");
const novelSrc = readFileSync(new URL("../src/app/novels/[id]/page.tsx", import.meta.url), "utf8");
const chapterSrc = readFileSync(new URL("../src/app/chapters/[id]/page.tsx", import.meta.url), "utf8");
const novelActionsSrc = readFileSync(new URL("../src/components/NovelInteractiveActions.tsx", import.meta.url), "utf8");
const chapterReaderSrc = readFileSync(new URL("../src/components/ChapterInteractiveReader.tsx", import.meta.url), "utf8");

test("robots.ts: quy tắc robots chuẩn xác cho tìm kiếm công khai và bảo vệ khu vực quản trị/riêng tư", () => {
  assert.ok(existsSync(new URL("../src/app/robots.ts", import.meta.url)));
  assert.match(robotsSrc, /export default function robots/);
  // Cho phép các trang nội dung
  assert.match(robotsSrc, /"\/library"/);
  assert.match(robotsSrc, /"\/novels\/"/);
  assert.match(robotsSrc, /"\/chapters\/"/);
  assert.match(robotsSrc, /"\/community"/);
  // Chặn khu vực quản trị và studio
  assert.match(robotsSrc, /"\/admin\/"/);
  assert.match(robotsSrc, /"\/studio\/"/);
  assert.match(robotsSrc, /"\/api\/"/);
  assert.match(robotsSrc, /sitemap: "https:\/\/fanfic\.world\/sitemap\.xml"/);
});

test("sitemap.ts: sitemap động cho phép index trang tĩnh và danh mục truyện", () => {
  assert.ok(existsSync(new URL("../src/app/sitemap.ts", import.meta.url)));
  assert.match(sitemapSrc, /export default async function sitemap/);
  assert.match(sitemapSrc, /https:\/\/fanfic\.world/);
  assert.match(sitemapSrc, /\/api\/novels\?limit=/);
  assert.match(sitemapSrc, /`\$\{BASE_URL\}\/novels\/\$\{novel\.novel_id\}`/);
});

test("Trang chi tiết truyện /novels/[id] là Server Component với generateMetadata chuẩn OpenGraph type book", () => {
  // Không có directive 'use client' ở root trang
  assert.ok(!novelSrc.startsWith('"use client"') && !novelSrc.startsWith("'use client'"), "Trang truyện phải là Server Component");
  // Có generateMetadata
  assert.match(novelSrc, /export async function generateMetadata/);
  assert.match(novelSrc, /type:\s*"book"/);
  assert.match(novelSrc, /card:\s*"summary_large_image"/);
  assert.match(novelSrc, /canonical/);
  // SSR layout và markup
  assert.match(novelSrc, /<NovelCover/);
  assert.match(novelSrc, /<h1 className="page-title">/);
  assert.match(novelSrc, /className="list list-gon"/);
  // Client island được nhúng
  assert.match(novelSrc, /<NovelOwnerActions/);
  assert.ok(novelActionsSrc.startsWith('"use client"') || novelActionsSrc.startsWith("'use client'"), "NovelInteractiveActions phải là Client Component");
});

test("Trang đọc chương /chapters/[id] là Server Component với generateMetadata chuẩn OpenGraph type article", () => {
  // Không có directive 'use client' ở root trang
  assert.ok(!chapterSrc.startsWith('"use client"') && !chapterSrc.startsWith("'use client'"), "Trang chương phải là Server Component");
  // Có generateMetadata
  assert.match(chapterSrc, /export async function generateMetadata/);
  assert.match(chapterSrc, /type:\s*"article"/);
  assert.match(chapterSrc, /canonical/);
  // SSR readable prose paragraphs
  assert.match(chapterSrc, /<div className="prose">/);
  assert.match(chapterSrc, /chapter\.content\.split\(/);
  assert.match(chapterSrc, /<p key=\{idx\}/);
  // Client island được nhúng
  assert.match(chapterSrc, /<ChapterInteractiveReader/);
  assert.ok(chapterReaderSrc.startsWith('"use client"') || chapterReaderSrc.startsWith("'use client'"), "ChapterInteractiveReader phải là Client Component");
});

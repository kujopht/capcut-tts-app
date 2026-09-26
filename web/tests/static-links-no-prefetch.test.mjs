/**
 * Moi <Link> tro toi trang dang nhap PHAI co prefetch={false}.
 *
 * Su co do tren fanfic.world (2026-09-27, khach): o /community va
 * /novels/[id], router cua Next xin lai prefetch segment `/_tree` cua
 * `/login?next=...` khoang 22-24 lan MOI GIAY, mai mai, chung nao tab con mo.
 * Phan hoi tu cache cua OpenNext (`x-opennext-cache: HIT`) thieu header
 * `x-nextjs-postponed` ma ban `next start` co, nen client khong bao gio coi
 * prefetch la xong. Moi lan xin lai la mot lan goi Cloudflare Worker. Ba link
 * gay ra no (nut Thich cua khach o PostCard, "Dang nhap de binh luan" o
 * CommentThread, nut Theo doi cua khach o FollowButton) la ba link DUY NHAT
 * toi /login con de prefetch mac dinh — moi link dang nhap khac trong kho da
 * `prefetch={false}` tu truoc. Prefetch trang dang nhap cung khong dem lai
 * gi: khong ai can no hien tuc thi.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

function tepTsx(thuMuc) {
  const ra = [];
  for (const ten of readdirSync(thuMuc)) {
    const p = join(thuMuc, ten);
    if (statSync(p).isDirectory()) ra.push(...tepTsx(p));
    else if (p.endsWith(".tsx")) ra.push(p);
  }
  return ra;
}

/** Cac the mo `<Link ...>` (ca khi xuong dong, co `{}` long nhau) trong mot tep. */
function theLink(src) {
  const ra = [];
  let i = src.indexOf("<Link");
  while (i >= 0) {
    let sau = 0;
    let j = i + 5;
    for (; j < src.length; j++) {
      const c = src[j];
      if (c === "{") sau++;
      else if (c === "}") sau--;
      else if (c === ">" && sau === 0) break;
    }
    ra.push(src.slice(i, j + 1));
    i = src.indexOf("<Link", j);
  }
  return ra;
}

/*
  Route TINH (prerender, "○" trong `next build`). Cung co che voi su co
  2026-08-26 o thanh dieu huong (xem chu thich `prefetch={false}` trong
  NavAuth.tsx): prefetch segment toi mot trang tinh phuc vu qua tang
  cache-interception cua OpenNext bi xin lai lien tuc. Link toi route DONG
  (`/novels/${id}`, `/posts/${id}`) khong nam trong luat nay — do tren
  production chung chi xin 2 lan roi dung.
*/
const ROUTE_TINH = new Set([
  "/", "/account", "/animation", "/animation/new", "/authors", "/community", "/creator/apply", "/entertainment",
  "/fanfic", "/import", "/leaderboard", "/library", "/login", "/notifications", "/studio", "/studio/audio",
  "/studio/content", "/studio/image", "/studio/library", "/studio/media", "/studio/subtitle", "/studio/translate",
  "/studio/video", "/studio/write", "/studio/write/import",
]);

test("moi Link co href TINH toi route tinh deu prefetch={false}", () => {
  const vi = [];
  let dem = 0;
  for (const tep of tepTsx(SRC)) {
    const src = readFileSync(tep, "utf8");
    for (const the of theLink(src)) {
      if (/prefetch=\{false\}/.test(the)) continue;
      const m = the.match(/href="([^"]+)"/) || the.match(/href=\{"([^"]+)"\}/) || the.match(/href=\{`([^`]+)`\}/);
      if (!m) continue;
      const duong = m[1].split(/[?#]/)[0];
      if (duong.includes("${")) continue; // bien nam trong DUONG DAN -> route dong
      dem++;
      if (ROUTE_TINH.has(duong.replace(/\/$/, "") || "/")) vi.push(`${tep.slice(SRC.length)}: ${m[1]}`);
    }
  }
  assert.ok(dem >= 20, `chỉ quét được ${dem} link có href tĩnh — bộ quét có thể đã hỏng`);
  assert.deepEqual(vi, [], `Link tới route tĩnh còn prefetch mặc định:\n${vi.join("\n")}`);
});

test("moi Link toi /login deu prefetch={false} (chan vong prefetch vo han tren OpenNext)", () => {
  const vi = [];
  let dem = 0;
  for (const tep of tepTsx(SRC)) {
    const src = readFileSync(tep, "utf8");
    for (const the of theLink(src)) {
      if (!/href=(\{loginHref\(|"\/login|\{`\/login)/.test(the)) continue;
      dem++;
      if (!/prefetch=\{false\}/.test(the)) vi.push(`${tep.slice(SRC.length)}: ${the.replace(/\s+/g, " ").slice(0, 120)}`);
    }
  }
  assert.ok(dem >= 10, `chỉ tìm thấy ${dem} link tới /login — bộ quét có thể đã hỏng`);
  assert.deepEqual(vi, [], `Link tới /login thiếu prefetch={false}:\n${vi.join("\n")}`);
});

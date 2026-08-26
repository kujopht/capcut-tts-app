/*
 * Khoa lai bao mot vong: MOI <Link> tro toi mot trong cac trang TINH da
 * prerender (`/`, `/fanfic`, `/animation`, `/community`, `/library`,
 * `/write`, `/login`, `/studio`, `/image-studio`, `/leaderboard`,
 * `/account`) phai co `prefetch={false}`.
 *
 * BOI CANH: do that tren production, prefetch tu dong (Next.js quan sat
 * moi <Link> trong/gan khung nhin qua IntersectionObserver) gay ra mot
 * luong request lap lai lien tuc (~40ms/lan) toi CUNG mot segment, du yeu
 * cau truoc do da tra ve 200 kem `x-nextjs-stale-time: 300`. Vi day la
 * hanh vi THEO TUNG <Link> (khong rieng component/trang nao), sua rieng
 * header (PR #63) roi rieng trang chu (PR #64) deu chi lam "bao doi cho" —
 * no chuyen sang <Link> TINH ke tiep con lai chua sua, khong bien mat.
 *
 * Test nay quet TOAN BO `web/src` mot lan, giong het cach da dung de tim
 * va sua tat ca cac vi tri — bat ky <Link> TINH moi nao sau nay quen
 * `prefetch={false}` se lam hong test nay ngay, thay vi phai doi den luc
 * do lai tren production moi phat hien.
 *
 * NGOAI LE duy nhat: <Link> nam TRONG mot menu tha xuong chi mount khi
 * `open` (vd `.menu-item` trong `NavAuth.tsx`) — nhung the do KHONG thuong
 * truc trong DOM, IntersectionObserver khong co co hoi quan sat lien tuc,
 * nen khong can (va phan hoi review truoc xac nhan: sua rieng nhung Link
 * nay la thua, khong sai nhung khong can thiet).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, "..", "src");

const STATIC_HREFS = [
  "/fanfic", "/animation", "/community", "/library", "/write",
  "/login", "/studio", "/image-studio", "/leaderboard", "/account",
];

// `<Link>` chi mount khi mot menu tha xuong dang mo — an toan, khong can prefetch={false}.
const NGOAI_LE = [
  'href="/studio" className="menu-item"',
  'href="/image-studio" className="menu-item"',
  'href="/account" className="menu-item"',
  'href="/leaderboard" className="menu-item"',
];

function timTepTsx(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) timTepTsx(p, out);
    else if (entry.name.endsWith(".tsx")) out.push(p);
  }
  return out;
}

const hrefPattern = new RegExp(
  `href="(${STATIC_HREFS.map((h) => h.replace("/", "\\/")).join("|")})"`,
);

test("moi <Link> toi trang tinh (khong nam trong menu tha xuong) co prefetch={false}", () => {
  const viPham = [];
  for (const file of timTepTsx(SRC)) {
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      if (!line.includes("<Link")) return;
      if (!hrefPattern.test(line)) return;
      if (line.includes("prefetch={")) return;
      if (NGOAI_LE.some((s) => line.includes(s))) return;
      viPham.push(`${path.relative(SRC, file)}:${i + 1}  ${line.trim()}`);
    });
  }
  assert.deepEqual(
    viPham,
    [],
    `Cac <Link> sau tro toi trang tinh nhung thieu prefetch={false}:\n${viPham.join("\n")}`,
  );
});

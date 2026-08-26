/*
 * Khoa lai bao mot vong: MOI <Link> tro toi mot trong cac trang TINH da
 * prerender (`/`, `/fanfic`, `/animation`, `/community`, `/library`,
 * `/write`, `/login`, `/studio`, `/image-studio`, `/leaderboard`,
 * `/account`, `/notifications`, `/creator/apply`, `/animation/new`) phai
 * co `prefetch={false}` — KE CA khi href co query string
 * (`href="/login?next=..."`) hoac la mot bieu thuc dieu kien
 * (`href={profile ? "/write" : "/login"}`).
 *
 * BOI CANH: do that tren production, prefetch tu dong (Next.js quan sat
 * moi <Link> trong/gan khung nhin qua IntersectionObserver) gay ra mot
 * luong request lap lai lien tuc (~40ms/lan) toi CUNG mot segment, du yeu
 * cau truoc do da tra ve 200 kem `x-nextjs-stale-time: 300`. Vi day la
 * hanh vi THEO TUNG <Link> (khong rieng component/trang nao), sua rieng
 * header (PR #63) roi rieng trang chu (PR #64) deu chi lam "bao doi cho" —
 * no chuyen sang <Link> TINH ke tiep con lai chua sua, khong bien mat.
 *
 * Lan quet DAU TIEN (PR #64) dung mot regex chi khop `href="/duong-dan"`
 * NGUYEN VAN — bo sot CA HAI dang o tren, va do THAT tren mot build cuc bo
 * tuong duong production (`wrangler dev` tren Worker OpenNext that) van
 * thay bao ~3500 request/30s idle, 100% do vao `/` — CHINH XAC tu logo/
 * brand-link o `app/layout.tsx` (mot `href="/"` don gian, khong query,
 * khong dieu kien, nhung van bi bo sot vi regex dau tien chua bao gio liet
 * `/` vao danh sach TINH). Test nay quet rong hon de khong lap lai kieu
 * bo sot do.
 *
 * NGOAI LE:
 *   1. <Link> nam TRONG mot menu tha xuong chi mount khi `open` (vd
 *      `.menu-item` trong `NavAuth.tsx`) — the do KHONG thuong truc trong
 *      DOM, IntersectionObserver khong co co hoi quan sat lien tuc.
 *   2. Lien ket dieu huong NOI BO trong khu quan tri (`/admin/**` sang
 *      `/admin/**` khac, vd breadcrumb "← Về danh sách") — luu luong admin
 *      RAT thap (chi vai tai khoan quan tri, khong phai khach cong khai),
 *      va day la dieu huong MOT-DICH-DUY-NHAT that su co ich cho nguoi
 *      dang lam viec trong khu do — giu prefetch o day co gia tri UX that,
 *      khong phai "prefetch thua". Rieng thanh dieu huong THUONG TRUC cua
 *      khu quan tri (`AdminShell.tsx`, tuong duong header cong khai) VAN
 *      phai co `prefetch={false}` — no khong nam trong ngoai le nay.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, "..", "src");

const STATIC_HREFS = [
  "/", "/fanfic", "/animation", "/animation/new", "/community", "/library",
  "/write", "/login", "/studio", "/image-studio", "/leaderboard", "/account",
  "/notifications", "/creator/apply",
];

// `<Link>` chi mount khi mot menu tha xuong dang mo — an toan, khong can prefetch={false}.
const NGOAI_LE_MENU = [
  'href="/studio" className="menu-item"',
  'href="/image-studio" className="menu-item"',
  'href="/account" className="menu-item"',
  'href="/leaderboard" className="menu-item"',
  'href="/admin" className="menu-item"',
];

function timTepTsx(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) timTepTsx(p, out);
    else if (entry.name.endsWith(".tsx")) out.push(p);
  }
  return out;
}

/** `href="/fanfic"`, `href="/fanfic?x=1"`, hoac ("/fanfic" ben trong mot
 * bieu thuc `href={...}`) — nhung KHONG khop `href="/fanfic-xyz"` hay
 * `href="/fanficabc"` (bien gioi tu `"` hoac `?` hoac dau ngoac dong `}`). */
function coHrefTinh(dong) {
  return STATIC_HREFS.some((duong) => {
    const escaped = duong.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`href=(\\{[^}]*)?"${escaped}(\\?[^"]*)?"`);
    return re.test(dong);
  });
}

test("moi <Link> toi trang tinh (khong nam trong ngoai le) co prefetch={false}", () => {
  const viPham = [];
  for (const file of timTepTsx(SRC)) {
    // Bo qua khu quan tri: chi thanh dieu huong thuong truc (AdminShell) can
    // sua, cac lien ket mot-dich noi bo trong tung trang admin thi giu
    // nguyen (xem NGOAI LE 2 o dau tep).
    const laFileAdminShell = file.endsWith("AdminShell.tsx");
    const laTrongThuMucAdmin = file.includes(`${path.sep}app${path.sep}admin${path.sep}`);
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      if (!line.includes("<Link")) return;
      if (!coHrefTinh(line)) return;
      if (line.includes("prefetch={")) return;
      if (NGOAI_LE_MENU.some((s) => line.includes(s))) return;
      if (laTrongThuMucAdmin && !laFileAdminShell) return;
      viPham.push(`${path.relative(SRC, file)}:${i + 1}  ${line.trim()}`);
    });
  }
  assert.deepEqual(
    viPham,
    [],
    `Cac <Link> sau tro toi trang tinh nhung thieu prefetch={false}:\n${viPham.join("\n")}`,
  );
});

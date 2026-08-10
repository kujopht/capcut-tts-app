/*
 * Chuyen canh tranh nen khi doi route, va bia du phong khong con chu cai.
 *
 * VAN DE DA CO: doi route la anh nen doi tuc thi — doc ra nhu doi hinh nen may
 * tinh chu khong phai nhu di qua mot the gioi lien mach.
 *
 * Bo test nay giu bon rang buoc de nhat bi pha:
 *
 *   1. DUNG HAI lop, khong bao gio tich lai;
 *   2. NAP TRUOC anh moi — khong nap truoc thi co mot nhay den giua hai tam;
 *   3. do mo chi ap cho LOP ANH, khong cho ca ung dung;
 *   4. tab cuc bo (Thu vien) khong lam nen nhap nhay.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");
const comp = () => read("../src/components/PageBackground.tsx");
const anhXa = () => read("../src/lib/backgrounds.ts");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ==================================================== hai lop, khong tich lai */

test("dung HAI lop, khong bao gio nhieu hon", () => {
  /*
    Mot lop dang mo ra, mot lop dang hien vao. Neu de lop cu tich lai thi sau
    vai lan dieu huong se co chuc lop `fixed` chong nhau — vua ton GPU vua lam
    mau cong don sai.
  */
  const src = comp();
  assert.match(src, /tenCu \? <div className="page-bg-lop"/,
    "lớp cũ không được vẽ có điều kiện");
  assert.match(src, /setTenCu\(null\)/, "không dọn lớp cũ sau khi chuyển cảnh");
  assert.match(src, /clearTimeout\(hen\.current\)/,
    "không huỷ hẹn cũ — hai lần điều hướng nhanh sẽ chồng nhau");
});

test("NAP TRUOC anh moi truoc khi chuyen canh", () => {
  // Doi ngay thi trinh duyet ve mot khung trong trong luc tai, va nguoi dung
  // thay mot nhay den giua hai tam.
  const src = comp();
  assert.match(src, /new Image\(\)/, "không nạp trước ảnh mới");
  assert.match(src, /img\.decode/, "không dùng decode() cho ảnh đã trong cache");
  assert.match(src, /anhNen\(ten\)/);
});

test("KHONG tai ca tam anh luc khoi dong", () => {
  // Chi tam hien hanh duoc dat vao CSS; cac tam khac chi tai khi dieu huong toi.
  const src = codeOnly(comp());
  assert.ok(!/rel="preload"|rel="prefetch"/.test(src), "tải sẵn toàn bộ bộ ảnh");
  const layout = read("../src/app/layout.tsx");
  assert.ok(!layout.includes("fantasy-backgrounds"),
    "layout tải sẵn tranh nền — 8 tấm cho một lần mở trang");
});

test("bang ten tep o lib KHOP voi cac url trong CSS", () => {
  // Hai cho phai noi cung mot dieu: `anhNen()` dung de NAP TRUOC, con CSS dung
  // de VE. Lech nhau thi nap truoc mot tam roi ve mot tam khac.
  const lib = anhXa();
  const text = css();
  const tep = [...lib.matchAll(/^ {2}\w+: "([^"]+)",$/gm)].map((m) => m[1]);
  assert.ok(tep.length >= 8, `chỉ tìm thấy ${tep.length} tên tệp trong lib`);
  for (const t of tep) {
    assert.ok(text.includes(`${t}.webp`), `CSS không dùng tấm ${t} mà lib khai báo`);
  }
});

/* ============================================================== do mo */

test("do mo chi ap cho LOP ANH, khong cho ca ung dung", () => {
  const text = css();
  const at = text.indexOf(".page-bg-lop::before {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /filter: blur\(var\(--mo, 0px\)\)/);
  // Phong to di kem do mo: lam mo keo mau o bien vao va lo ra mot vien nhat.
  assert.match(than, /transform: scale\(var\(--phong, 1\)\)/);

  // Va KHONG co `filter: blur` nao dat tren `body`, `main` hay `.page`.
  for (const sel of ["\nbody {", "\nmain {", "\n.page {"]) {
    const a = text.indexOf(sel);
    if (a === -1) continue;
    const t = text.slice(a, text.indexOf("}", a));
    assert.ok(!/filter: blur/.test(t), `${sel.trim()} bị làm mờ toàn phần`);
  }
});

test("do mo tung trang dung nhu da dat", () => {
  const text = css();
  const mo = {};
  for (const m of text.matchAll(
    /\.page-bg-lop\[data-bg="([^"]+)"\][^\n]*--mo: ([\d.]+)px;/g,
  )) {
    mo[m[1]] = Number(m[2]);
  }
  assert.equal(Object.keys(mo).length, 8, "có tấm chưa đặt độ mờ");

  // Mat tien phai SAC: tranh la thu tao ban sac.
  for (const ten of ["home", "explore", "auth", "reader"]) {
    assert.equal(mo[ten], 0, `${ten} bị làm mờ — phải sắc`);
  }
  // Trang lam viec: tranh lui ve sau de form la thu chinh.
  for (const ten of ["studio", "write"]) {
    assert.ok(mo[ten] >= 5 && mo[ten] <= 8, `${ten} mờ ${mo[ten]}px, cần 5–8`);
  }
  // Hai trang con lai chi lam mem, giu chi tiet.
  for (const ten of ["library", "account"]) {
    assert.ok(mo[ten] > 0 && mo[ten] <= 4, `${ten} mờ ${mo[ten]}px, cần 0–4`);
  }
});

test("moi tam co lam mo thi PHAI phong to theo", () => {
  // Lam mo keo mau o bien anh vao trong va lo ra mot vien nhat quanh khung.
  const text = css();
  for (const m of text.matchAll(
    /\.page-bg-lop\[data-bg="([^"]+)"\][^\n]*--mo: ([\d.]+)px; --phong: ([\d.]+);/g,
  )) {
    const [, ten, mo, phong] = m;
    if (Number(mo) > 0) {
      assert.ok(Number(phong) > 1,
        `${ten} mờ ${mo}px nhưng không phóng to — sẽ lộ viền`);
    }
  }
});

/* ============================================================ giam chuyen dong */

test("giam chuyen dong: bo phong to, giu doi anh rat ngan", () => {
  const text = css();
  const than = text.slice(text.indexOf("@media (prefers-reduced-motion: reduce)"));
  assert.match(than, /--dur-nen: \d+ms/, "không rút ngắn chuyển cảnh");
  assert.match(than, /\.page-bg-lop\[data-vao\]::before \{ animation: none; \}/,
    "vẫn còn phóng to khi người dùng chọn giảm chuyển động");
});

test("thoi luong o CSS khop voi thoi luong o component", () => {
  // Lech nhau thi lop cu bi bo TRUOC khi mo het (thay mot nhay) hoac o lai SAU
  // khi da mo het (mot lop `fixed` thua nam do).
  const ms = Number(css().match(/--dur-nen: (\d+)ms/)?.[1]);
  const js = Number(comp().match(/const THOI_LUONG = (\d+);/)?.[1]);
  assert.equal(ms, js, `CSS ${ms}ms nhưng component ${js}ms`);
  assert.ok(ms >= 350 && ms <= 500, `${ms}ms — cần 350–500`);
});

/* ============================================================== tab cuc bo */

test("tab cuc bo KHONG doi nen toan trang", () => {
  // `Tất cả / Audio Studio / Fanfic` la trang thai trong mot trang; `pathname`
  // khong doi nen nen phai dung yen.
  const src = comp();
  assert.match(src, /location\.pathname/);
  assert.ok(!src.includes("searchParams"), "nền phản ứng theo query string");

  const lib = read("../src/app/library/page.tsx");
  assert.match(lib, /setSource\(value\)/);
  assert.ok(!lib.includes("router.push"),
    "đổi tab bằng điều hướng — nền sẽ nhấp nháy");
});

/* ================================================== bia du phong: KHONG chu cai */

test("bia du phong KHONG con chu cai dau", () => {
  /*
    LOI CUA BAN TRUOC: phase K boc chu cai vao mot khung huy hieu nhung VAN GIU
    chu cai o trong. Bao cao luc do viet "thay chu cai bang mot huy hieu", doc
    ra la da bo chu — thuc te chi la boc lai. Anh chup van hien V / N / Z.

    Bay gio khong con chu cai nao: mot dau an hinh hoc thay cho no.
  */
  const cover = read("../src/components/NovelCover.tsx");
  assert.ok(!cover.includes("coverInitial"), "vẫn dùng chữ cái đầu làm bìa");
  assert.match(cover, /<StoryCoverFallback seed=/);
  assert.ok(!css().includes(".cover-initial"), "CSS còn quy tắc cho chữ cái");
});

test("dau an on dinh theo truyen, va KHONG di kem mau", async () => {
  const { sigilFor, paletteFor, COVER_SIGILS } =
    await import("../src/lib/cover.ts");
  assert.equal(sigilFor("nov_abc"), sigilFor("nov_abc"));
  assert.ok(COVER_SIGILS.includes(sigilFor("nov_abc")));

  /*
    Hai truyen cung mau van phai khac dau an duoc. Neu dau an dung y nguyen ham
    bam nhu mau thi hai thu luon di cap, va bo bia mat mot nua so bien the.
  */
  const cap = new Set();
  for (let i = 0; i < 80; i += 1) {
    cap.add(`${paletteFor("s" + i)[0]}|${sigilFor("s" + i)}`);
  }
  assert.ok(cap.size > COVER_SIGILS.length,
    `chỉ ${cap.size} tổ hợp màu+dấu ấn — dấu ấn đi kèm màu`);
});

test("dau an ve bang SVG noi tuyen, khong tep anh va khong goi phu thuoc", () => {
  const src = read("../src/components/StoryCoverFallback.tsx");
  assert.match(src, /<svg/);
  assert.ok(!/\.png|\.webp/.test(src), "dấu ấn tải tệp ảnh");
  assert.ok(!src.includes("artwork/"), "dùng tranh nền làm bìa truyện");

  // Va KHONG them goi icon nao — repo nay ve SVG noi tuyen, xem `ProviderIcons`.
  const pkg = JSON.parse(read("../package.json"));
  const tat_ca = { ...pkg.dependencies, ...pkg.devDependencies };
  for (const goi of ["lucide-react", "@heroicons/react", "react-icons",
                     "@phosphor-icons/react", "@tabler/icons-react"]) {
    assert.ok(!(goi in tat_ca), `đã thêm gói icon ${goi}`);
  }
});

test("moi dau an dung currentColor de dung duoc tren moi cap mau nen", () => {
  const src = read("../src/components/StoryCoverFallback.tsx");
  assert.match(src, /fill="currentColor"/);
  const rule = css().match(/\.cover-sigil \{[^}]*\}/)?.[0] ?? "";
  assert.match(rule, /color:/, "dấu ấn không được cấp màu");
});

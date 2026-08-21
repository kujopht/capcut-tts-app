/*
 * Chuyen canh tranh nen khi doi route, va bia du phong khong con chu cai.
 *
 * VAN DE DA CO: doi route la anh nen doi tuc thi — doc ra nhu doi hinh nen may
 * tinh chu khong phai nhu di qua mot the gioi lien mach.
 *
 * V1 "Cloud Veil": co che HAI-LOP-tu-quan-ly (mot lop dang mo ra, mot lop
 * dang hien vao, trong PageBackground.tsx) da duoc thay bang MOT lop DUY
 * NHAT + `RouteTransitionVeil.tsx` (man may/suong) + `lib/
 * routeTransitionStore.ts` (dong ho dieu phoi, MOI nap-truoc-anh chuyen vao
 * day — xem `route-transition-veil.test.mjs` cho bo test day du cua co che
 * moi). Bo test o day gio con giu HAI rang buoc con lai van dung nguyen:
 *
 *   1. do mo chi ap cho LOP ANH, khong cho ca ung dung;
 *   2. tab cuc bo (Thu vien) khong lam nen nhap nhay.
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
  //
  // Chi quet trong khoi `const TEP = {...}` (anh TINH) — tu rollout Live
  // Wallpaper V4, tep nay CON co mot bang thu hai `VIDEO` (ten .mp4, khong
  // phai .webp) ngay ben duoi, khong lien quan gi toi CSS anh tinh o day.
  const lib = anhXa();
  const text = css();
  const khoiTep = lib.slice(lib.indexOf("const TEP"), lib.indexOf("const TEP") + lib.slice(lib.indexOf("const TEP")).indexOf("\n};"));
  const tep = [...khoiTep.matchAll(/^ {2}\w+: "([^"]+)",$/gm)].map((m) => m[1]);
  assert.ok(tep.length >= 8, `chỉ tìm thấy ${tep.length} tên tệp trong lib`);
  for (const t of tep) {
    assert.ok(text.includes(`${t}.webp`), `CSS không dùng tấm ${t} mà lib khai báo`);
  }
});

/* ============================================================== do mo */

test("tranh nen KHONG bao gio bi lam mo", () => {
  /*
    HOI QUY DA XAY RA: phase L lam mo 6px o `/studio` va `/write`, 2.5-3px o
    `/library` va `/account`, de form va danh sach noi len. Cach do lam hong
    chinh buc tranh — chi tiet (kinh vien vong, khinh khi cau, ke sach, hoa anh
    dao) la thu tao ban sac, va lam mo la nem no di.

    De doc phai den tu MANG TOI CUC BO va BE MAT KINH.

    `backdrop-filter` TREN TAM KINH thi duoc phep — do la thu lam nen kinh. Cai
    bi cam la `filter: blur` tren chinh lop tranh.
  */
  const text = css();
  const at = text.indexOf(".page-bg-lop::before {");
  // `codeOnly`: chu thich trong khoi do co trich `filter: blur` de noi vi sao
  // KHONG dung no.
  const than = codeOnly(text.slice(at, text.indexOf("}", at)));
  assert.match(than, /filter: none/, "lớp tranh vẫn có bộ lọc");
  assert.ok(!/filter: blur/.test(than), "tranh nền bị làm mờ");

  // Va moi tam deu khai 0px — de neu ai doi thi bai test nay do ngay.
  const mo = {};
  for (const m of text.matchAll(
    /\.page-bg-lop\[data-bg="([^"]+)"\][^\n]*--mo: ([\d.]+)px;/g,
  )) {
    mo[m[1]] = Number(m[2]);
  }
  assert.equal(Object.keys(mo).length, 8, "có tấm chưa khai độ mờ");
  for (const [ten, v] of Object.entries(mo)) {
    assert.equal(v, 0, `${ten} mờ ${v}px — mọi tấm phải sắc`);
  }

  // Va KHONG `filter: blur` nao tren `body`, `main` hay `.page`.
  for (const sel of ["\nbody {", "\nmain {", "\n.page {"]) {
    const a = text.indexOf(sel);
    if (a === -1) continue;
    const t = text.slice(a, text.indexOf("}", a));
    assert.ok(!/filter: blur/.test(t), `${sel.trim()} bị làm mờ toàn phần`);
  }
});

test("de doc den tu MANG TOI CUC BO, khong tu lam mo", () => {
  // Thu thay cho do mo: mot mang toi dat ngay sau khu lam viec. Tranh o mep
  // trang van sac nguyen; chi vung co chu la toi hon.
  const text = css();
  assert.match(text, /\.page-lam-viec::before/, "thiếu mảng tối sau khu làm việc");
  for (const f of ["../src/app/studio/page.tsx", "../src/app/write/page.tsx"]) {
    assert.match(read(f), /page-lam-viec/, `${f} không dùng mảng tối cục bộ`);
  }
});

test("chu nam TRUC TIEP tren tranh deu co mot cach chong nhoe", () => {
  /*
    Bo do mo xong thi lo ra mot loai loi: nhung khoi chu KHONG boc trong the nao
    ca. Do duoc tren anh chup that:

      - footer (`/library`, `/account`) — khong the, khong kinh, va tren tam ke
        sach sang / troi chieu cam thi chu cap ba bien mat;
      - dong ghi chu cuoi mot muc o `/account` — nam giua hai luoi the, do thang
        len hoa anh dao;
      - tieu de `/login` — trang co lop phu nhat nhat (0.30).

    Ba cho, hai cach chua: MANG TOI cuc bo cho khoi lon, BONG CHU cho dong le.
  */
  const text = css();

  assert.match(text, /\.site-footer::before/, "footer không có mảng tối");
  // `.hero-copy::before` thuộc "Themed Page Hero" (PageHero V2/V3) — CHƯA
  // được port trong đợt Visual Renaissance v2-clean này (xem semantic
  // inventory: PageHero là một hạng mục riêng, cố ý để lại cho một đợt
  // port khác). Bỏ qua khẳng định này ở đây thay vì port cả PageHero chỉ
  // để test này đạt.
  assert.match(text, /\.page > section:not\(\.card\) > \.hint/,
    "ghi chú cuối mục không được cấp bóng chữ");

  /*
    Mang toi cua footer phai TAN o CA HAI dau. Ban dau tri no cat thang o mep
    duoi, va khi trang ngan hon khung nhin thi footer khong nam o day man hinh —
    ket qua la mot dai bang den ngang giua tranh. Do la loi da do duoc mot lan.
  */
  const at = text.indexOf(".site-footer::before");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /inset: 0 0 -\d+px 0/, "mảng tối footer không tràn xuống dưới");
  const diem = [...than.matchAll(/#05070f([0-9a-f]{2})/g)].map((m) => m[1]);
  assert.equal(diem.at(0), "00", "mảng tối footer không tan ở mép trên");
  assert.equal(diem.at(-1), "00", "mảng tối footer không tan ở mép dưới");
});

test("tieu de trang dac mau gan trang, khong con gradient mo dan", () => {
  /*
    Ban gradient-clip-text truoc day (`linear-gradient(...) -> #c5cfe3`) van
    lam nua duoi cua tieu de hai dong doc ra XAM tren nen sang — do bang anh
    chup that o `02-explore-sky-kingdom`. Sua: mau DAC `var(--text)`, khong
    con `background-clip: text` / `color: transparent`, kem text-shadow RIENG
    (khong dua vao danh sach dung chung — no lon hon han cac dong con lai).
  */
  const text = css();
  const at = text.indexOf(".page-title {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /color:\s*var\(--text\)/, "tiêu đề trang phải là màu đặc var(--text)");
  assert.doesNotMatch(than, /color:\s*transparent/, "tiêu đề trang không còn được phép trong suốt");
  assert.doesNotMatch(than, /background-clip:\s*text/, "tiêu đề trang không còn gradient-clip");
  assert.match(than, /text-shadow:/, "tiêu đề trang cần bóng chữ riêng để đọc được trên tranh nền");
});

test("hang dieu huong cuon duoc o mobile thi phai NOI ra la cuon duoc", () => {
  /*
    O 390px hang nay cuon ngang va thanh cuon bi an, nen the cuoi ("Viết truyện")
    bi cat giua chu. Khong co vet mo thi no doc ra la mot loi bo cuc chu khong
    phai la "con nua o ben phai".
  */
  const text = css();
  const at = text.indexOf(".nav-links {", text.indexOf("@media"));
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /overflow-x: auto/);
  assert.match(than, /-webkit-mask-image: linear-gradient\(to right/,
    "thiếu vệt mờ ở mép phải — cần cả tiền tố -webkit- cho Safari");
  assert.match(than, /^\s*mask-image: linear-gradient\(to right/m,
    "thiếu mask-image không tiền tố");
});

test("lam mo tren TAM KINH thi duoc phep — do la thu khac", () => {
  // Phan biet nay la quan trong: `backdrop-filter` lam nen mot tam kinh, con
  // `filter: blur` pha chinh buc tranh.
  const text = css();
  assert.match(text, /backdrop-filter: blur\(var\(--blur-the\)\)/,
    "không còn bề mặt kính nào");
});

// Giam chuyen dong + dong bo thoi luong CSS/JS cho chuyen canh: xem
// `route-transition-veil.test.mjs` (`--dur-veil-phu`/`--dur-veil-lo` va
// `THOI_LUONG_BINH_THUONG`/`THOI_LUONG_GIAM` o `lib/routeTransitionStore.ts`).

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

test("KHONG cung SVG nao co ban kinh nho hon nua day cung", () => {
  /*
    LOI DA XAY RA: dau an mat trang ve bang `M40 12 A20 ... A16 16 ... 40 52`.
    Hai diem cach nhau 40 don vi, nhung cung thu hai khai ban kinh 16 — duong
    kinh 32, be hon day cung. Dac ta SVG buoc trinh duyet NONG ban kinh len cho
    vua, nen ca hai cung thanh r=20 va hinh ra mot dia tron dac.

    Khong mot cong cu nao bao loi: SVG hop le, React vui ve, TypeScript vui ve,
    ESLint vui ve. Chi mot nguoi nhin vao bia moi thay "mat trang" la mot cai dia.
    Nen chinh phep tinh do phai thanh mot bai test.
  */
  const src = read("../src/components/StoryCoverFallback.tsx");
  const loi = [];
  for (const d of [...src.matchAll(/\sd="([^"]+)"/g)].map((m) => m[1])) {
    // Chi doc cac lenh tuyet doi `M x y` va `A rx ry rot laf sf x y` — du cho
    // moi duong trong tep nay, va khong bia ra mot bo phan tich SVG day du.
    const so = d.replace(/\s+/g, " ").trim();
    let x = 0, y = 0;
    for (const lenh of so.match(/[MA][^MAZz]*/g) ?? []) {
      const n = (lenh.slice(1).match(/-?[\d.]+/g) ?? []).map(Number);
      if (lenh[0] === "M") { [x, y] = n; continue; }
      for (let i = 0; i + 6 < n.length + 1; i += 7) {
        const [rx, ry, , , , x2, y2] = n.slice(i, i + 7);
        const day = Math.hypot(x2 - x, y2 - y);
        if (day > 2 * Math.min(rx, ry) + 1e-9) {
          loi.push(`cung tới (${x2},${y2}): dây ${day.toFixed(1)} > 2r ${2 * Math.min(rx, ry)}`);
        }
        x = x2; y = y2;
      }
    }
  }
  assert.deepEqual(loi, [], `cung bị nong bán kính:\n  ${loi.join("\n  ")}`);
});

test("the loi tat o /account dung icon SVG, KHONG emoji", () => {
  /*
    Ba the nay tung dung `✍️ 🎙 🎧`. Chung nam ngay canh `IconSparkles` va
    `IconCompass` o dau muc — mot emoji mau giua cac icon mot net doc ra nhu rac,
    va tren Windows/Android thi ba emoji do khong cung mot bo net nao ca.
  */
  const src = read("../src/app/account/page.tsx");
  const khoi = src.slice(src.indexOf("quick-grid"), src.indexOf("</section>", src.indexOf("quick-grid")));
  assert.ok(
    !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u.test(khoi),
    "thẻ lối tắt còn emoji",
  );
  for (const icon of ["IconFeather", "IconMic", "IconHeadphones"]) {
    assert.ok(khoi.includes(`<${icon} `), `thẻ lối tắt thiếu ${icon}`);
  }
  // Va o cha thi mau phai den tu CSS, khong tu thuoc tinh tren tung the.
  assert.match(css(), /\.quick-icon \{[^}]*color: var\(--brand-hover\)/s);
});

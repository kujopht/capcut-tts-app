// L2 (phan trang + tim kiem phia server), L3 (badge lich su Studio),
// L4 (mau hardcode) va vung bam breadcrumb.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

/**
 * Khop mot loi goi `api.xxx(` KE CA khi viet `api` xuong dong roi `.xxx(`.
 *
 * Da mac ba lan: `assert.match(src, /api\.novelTags\(\)/)` truot vi nguon viet
 * `api\n  .novelTags()`. Dung ham nay thay vi tu ghep regex.
 */
const callsApi = (src, method) =>
  new RegExp(`api\\s*\\.\\s*${method}\\s*\\(`).test(src);

const fanfic = () => read("../src/app/fanfic/page.tsx");
const studio = () => read("../src/app/studio/page.tsx");
const home = () => read("../src/app/page.tsx");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");
const novel = () => read("../src/app/novels/[id]/page.tsx");
const chapter = () => read("../src/app/chapters/[id]/page.tsx");

function rule(selector) {
  const text = css();
  const at = text.indexOf(selector + " {");
  assert.notEqual(at, -1, `thieu ${selector}`);
  return text.slice(at, text.indexOf("}", at) + 1);
}

/* =====================================================================
   L2 — tim kiem, loc va phan trang phia server
   ===================================================================== */

test("L2: trang kham pha khong con TIM KIEM/LOC trong trinh duyet", () => {
  const src = fanfic();
  // Ban cu: `novels.filter(...)` voi `toLowerCase().includes(needle)`
  assert.ok(!/novels\.filter\(/.test(src), "khong duoc loc danh sach o frontend");
  assert.ok(!/toLowerCase\(\)\.includes/.test(src),
    "khong duoc so khop chuoi o frontend");
  assert.ok(!/novel\.tags\.includes\(tag\)/.test(src),
    "khong duoc loc the o frontend");
  // `fanficOnly` KHONG tinh: no la lop phong ve chong kho chua cua Audio Studio,
  // khong phai bo loc tim kiem. Xem chu thich trong `fetchPage`.
  assert.match(src, /fanficOnly\(r\.novels\)/,
    "phai giu lop phong ve chong kho Studio");
});

test("L2: goi backend voi q, tag, limit va offset", () => {
  const src = fanfic();
  assert.match(src, /api\.browseNovels\(\{/);
  for (const key of ["query", "tag", "limit", "offset"]) {
    assert.match(src, new RegExp(`${key}[:,]`), `thieu tham so ${key}`);
  }
  const a = api();
  assert.match(a, /browseNovels:/);
  assert.match(a, /params\.set\("q"/);
  assert.match(a, /params\.set\("tag"/);
  assert.match(a, /params\.set\("limit"/);
  assert.match(a, /params\.set\("offset"/);
});

test("L2: danh sach the lay tu backend, khong suy ra tu trang dang xem", () => {
  const src = fanfic();
  assert.ok(callsApi(src, "novelTags"), "phai goi api.novelTags()");
  // Ban cu gom the bang cach quet toan bo `novels`
  assert.ok(!/novels\.forEach\(/.test(src),
    "khong duoc suy danh sach the tu du lieu da tai");
  assert.match(api(), /novelTags:/);
});

test("L2: co dieu huong trang, va nut bi vo hieu o hai dau", () => {
  const src = fanfic();
  assert.match(src, /className="pager"/);
  assert.match(src, /disabled=\{page === 0\}/);
  assert.match(src, /disabled=\{!hasMore\}/);
  assert.match(src, /aria-label="Phân trang"/);
});

test("L2: doi bo loc thi ve trang dau", () => {
  const src = fanfic();
  // Trang 5 cua ket qua cu thuong khong ton tai trong ket qua moi
  for (const fn of ["changeQuery", "changeTag", "clearFilters"]) {
    const at = src.indexOf(`const ${fn} =`);
    assert.notEqual(at, -1, `thieu ${fn}`);
    assert.match(src.slice(at, at + 220), /setPage\(0\)/, `${fn} phai ve trang dau`);
  }
});

test("L2: go chu khong ban mot request moi ky tu", () => {
  const src = fanfic();
  assert.match(src, /DEBOUNCE_MS/);
  assert.match(src, /setTimeout\(fetchPage, DEBOUNCE_MS\)/);
  assert.match(src, /clearTimeout/);
});

test("L2: phan hoi den muon cua request cu bi bo qua", () => {
  const src = fanfic();
  // Khong co cho nay thi ket qua cua tu khoa cu co the ghi de ket qua moi
  assert.match(src, /const latest = useRef\(0\)/);
  assert.match(src, /if \(latest\.current !== ticket\) return;/);
});

test("L2: trang rong phan biet 'chua co truyen' voi 'khong khop bo loc'", () => {
  const src = fanfic();
  assert.match(src, /Chưa có truyện nào được xuất bản/);
  assert.match(src, /Không tìm thấy truyện phù hợp/);
  assert.match(src, /const filtering = Boolean\(query\.trim\(\) \|\| tag\)/);
});

test("L2: kieu tra ve khai bao total va has_more", () => {
  const a = api();
  assert.match(a, /export interface NovelPage/);
  for (const field of ["total", "has_more", "limit", "offset"]) {
    assert.match(a, new RegExp(`${field}[?]?:`), `NovelPage thieu ${field}`);
  }
});

test("L2: listNovels cu khong bi doi — tuong thich nguoc", () => {
  const a = api();
  assert.match(a, /listNovels: \(mine = false\) =>/);
  // Khong duoc tu them limit vao duong cu
  const at = a.indexOf("listNovels: (mine = false)");
  assert.ok(!/limit/.test(a.slice(at, at + 200)),
    "listNovels khong duoc tu phan trang");
});

/* =====================================================================
   L3 — badge lich su Studio
   ===================================================================== */

test("L3: lich su duoc dong bo o MOI vong poll", () => {
  const src = studio();
  const at = src.indexOf("api\n        .getJob(");
  const body = src.slice(at > 0 ? at : src.indexOf(".getJob("), src.indexOf(".catch(", src.indexOf(".getJob(")));
  assert.match(body, /setJobs\(\(current\) => \[/);
  // Truoc day `setJobs` nam TRONG dieu kien "da ket thuc"
  assert.ok(
    !/if \(r\.job\.status === "completed" \|\| r\.job\.status === "failed"\) \{\s*\n\s*setJobs/.test(body),
    "setJobs khong duoc nam trong dieu kien ket thuc",
  );
});

test("L3: toast van chi keu o trang thai ket thuc", () => {
  const src = studio();
  const at = src.indexOf(".getJob(");
  const body = src.slice(at, src.indexOf(".catch(", at));
  // Ca hai toast phai di kem dieu kien trang thai — neu khong se keu moi vong
  // poll (2 giay mot lan) trong suot luc job dang chay.
  assert.match(body, /if \(r\.job\.status === "completed"\) toast\.ok/);
  assert.match(body, /else if \(r\.job\.status === "failed"\)/);
  const toastLines = body.split("\n").filter((l) => /toast\.(ok|error|push)\(/.test(l));
  assert.equal(toastLines.length, 2, `chi duoc 2 loi goi toast: ${toastLines}`);
  for (const line of toastLines) {
    assert.match(line, /r\.job\.status ===|toast\.error\("Tạo audio thất bại/,
      `toast khong co dieu kien: ${line.trim()}`);
  }
});

/* =====================================================================
   L4 — khong con mau hardcode
   ===================================================================== */

test("L4: trang chu khong con hex va khong con style inline", () => {
  const src = home();
  assert.ok(!/#7c8cff3d|#4dd6c133/.test(src), "van con hex trong JSX");
  assert.ok(!/"--glow"/.test(src), "khong duoc dat bien CSS bang style inline");
  // Hai the tinh nang cu da bien mat cung ban thiet ke lai huong fanfic-first.
  // Quy tac o day KHONG doi: trang chu van khong duoc chua mot style inline
  // nao ca — media query khong voi toi chung duoc.
  assert.ok(!/style=\{\{/.test(src), "trang chu con style inline");
});

test("L4: mau quang nam trong khoi token", () => {
  const text = css();
  assert.match(text, /--brand-glow: #7c8cff3d;/);
  assert.match(text, /--accent-glow: #4dd6c133;/);
  assert.match(rule(".feature-studio"), /var\(--brand-glow\)/);
  assert.match(rule(".feature-fanfic"), /var\(--accent-glow\)/);
});

test("L4: khong con gia tri du phong hardcode trong .feature::after", () => {
  const text = css();
  const at = text.indexOf(".feature::after");
  const body = text.slice(at, text.indexOf("}", at));
  assert.match(body, /var\(--glow\)/);
  assert.ok(!/#7c8cff33/.test(body), "van con mau du phong hardcode");
});

test("L4: khong con hex mau nao trong cac trang tsx", () => {
  // `opengraph-image.tsx` va `apple-icon.tsx` buoc phai hardcode: Satori khong
  // doc duoc CSS variable. Cac trang khac thi khong duoc.
  for (const f of ["../src/app/page.tsx", "../src/app/fanfic/page.tsx",
                   "../src/app/studio/page.tsx", "../src/app/write/page.tsx",
                   "../src/app/novels/[id]/page.tsx",
                   "../src/app/chapters/[id]/page.tsx"]) {
    const hex = read(f).match(/#[0-9a-fA-F]{6,8}\b/g) || [];
    assert.deepEqual(hex, [], `${f} con mau hardcode: ${hex.join(" ")}`);
  }
});

/* =====================================================================
   Breadcrumb — de bam ma khong lam hang cao them
   ===================================================================== */

test("breadcrumb dung lop .crumb o ca hai trang", () => {
  assert.match(novel(), /className="hint crumb"/);
  assert.match(chapter(), /className="hint crumb"/);
});

test("breadcrumb mo rong vung bam bang ::after, khong bang padding", () => {
  const r = rule(".crumb::after");
  assert.match(r, /position:\s*absolute/);
  assert.match(r, /height:\s*44px/);
  // `padding` se lam CHIEU CAO CUA HANG to len theo — dung yeu cau
  assert.ok(!/padding/.test(rule(".crumb")), "khong duoc dung padding");
  assert.match(rule(".crumb"), /position:\s*relative/);
  assert.match(rule(".crumb"), /min-width:\s*44px/);
});

/* =====================================================================
   Khong pha thu da co
   ===================================================================== */

test("khong pha M1: khoi mobile van nang vung bam len 44px", () => {
  const text = css();
  const start = text.indexOf("@media (max-width: 640px)");
  const open = text.indexOf("{", start);
  let depth = 0, block = "";
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) { block = text.slice(open + 1, i); break; }
    }
  }
  const r = block.match(/([^{}]*)\{[^{}]*min-height:\s*44px[^{}]*\}/);
  assert.ok(r, "mat quy tac 44px");
  const selectors = r[1].replace(/\/\*[\s\S]*?\*\//g, "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  for (const cls of [".btn", ".btn-sm", ".chip", ".seg-item", ".nav-link",
                     ".account-link", ".brand"]) {
    assert.ok(selectors.includes(cls), `mat ${cls}`);
  }
});

test("khong pha M2/M3/M4: cac tinh nang van con", () => {
  assert.match(novel(), /<AudioPlayer/);              // M2 nghe tai cho
  assert.match(read("../src/app/write/page.tsx"), /api\.reorderChapters\(/);  // M3
  assert.match(novel(), /chapter\.audio_outdated \?/);                        // M4
  assert.match(chapter(), /audioOutdated/);
});

test("cac ho endpoint khong doi, chi them duong duoi novels", () => {
  const found = new Set([...api().matchAll(/\/api\/([a-z]+)/g)].map((m) => m[1]));
  assert.deepEqual(
    [...found].sort(),
    ["audio", "auth", "chapters", "health", "jobs", "novels", "voices"],
    "khong duoc them ho tai nguyen moi",
  );
  assert.match(api(), /\/api\/novels\/tags/);
});

test("publish, unpublish, xoa, doi thu tu va tai MP3 van con", () => {
  const a = api();
  for (const fn of ["publishNovel:", "unpublishNovel:", "deleteNovel:",
                    "deleteChapter:", "updateChapter:", "reorderChapters:",
                    "audioLink:", "listNovels:", "browseNovels:"]) {
    assert.ok(a.includes(fn), `mat ${fn}`);
  }
  assert.match(read("../src/components/AudioPlayer.tsx"), /Tải MP3/);
});

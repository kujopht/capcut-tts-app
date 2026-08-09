// M3 — sap xep lai thu tu chuong. M4 — canh bao audio khong con khop.
//
// File rieng vi `ui.test.mjs` da dai; `package.json` chay `tests/*.test.mjs`
// nen file nay tu duoc nhan.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

const write = () => read("../src/app/write/page.tsx");
const novel = () => read("../src/app/novels/[id]/page.tsx");
const chapter = () => read("../src/app/chapters/[id]/page.tsx");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");

/** Cat khoi lenh dau tien cua mot selector. */
function rule(selector) {
  const text = css();
  const at = text.indexOf(selector + " {");
  assert.notEqual(at, -1, `thieu ${selector}`);
  return text.slice(at, text.indexOf("}", at) + 1);
}

/** Khoi `@media (max-width: 640px)`. */
function mobileBlock() {
  const text = css();
  const start = text.indexOf("@media (max-width: 640px)");
  assert.ok(start >= 0, "khong tim thay khoi mobile");
  const open = text.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(open + 1, i);
    }
  }
  throw new Error("khoi mobile khong dong ngoac");
}

/* =====================================================================
   M3 — thu tu chuong
   ===================================================================== */

test("M3: co nut di chuyen len va xuong, co nhan cho doc man hinh", () => {
  const src = write();
  assert.match(src, /aria-label=\{`Di chuyển \$\{chapter\.title\} lên trên`\}/);
  assert.match(src, /aria-label=\{`Di chuyển \$\{chapter\.title\} xuống dưới`\}/);
  // Mui nhon chi la trang tri, khong duoc la thong tin duy nhat
  assert.match(src, /<span aria-hidden="true">↑<\/span>/);
  assert.match(src, /<span aria-hidden="true">↓<\/span>/);
});

test("M3: nut dau va cuoi danh sach bi vo hieu", () => {
  const src = write();
  assert.match(src, /disabled=\{index === 0 \|\| savingOrder\}/);
  assert.match(src, /disabled=\{index === chapters\.length - 1 \|\| savingOrder\}/);
});

test("M3: thu tu duoc luu len backend, khong chi doi tam tren frontend", () => {
  assert.match(write(), /api\.reorderChapters\(/);
  assert.match(api(), /reorderChapters:/);
  assert.match(api(), /\/api\/novels\/\$\{novelId\}\/chapters\/order/);
  assert.match(api(), /method: "POST"/);
});

test("M3: doi thu tu la MOT request, khong phai mot request moi chuong", () => {
  const src = write();
  // Gui ca danh sach id mot lan
  assert.match(src, /next\.map\(\(c\) => c\.chapter_id\)/);
  // Va KHONG goi updateChapter trong vong lap de doi order_index
  assert.ok(
    !/order_index/.test(src.slice(src.indexOf("const moveChapter"),
                                  src.indexOf("const makeAudio"))),
    "khong duoc doi order_index tung chuong mot",
  );
});

test("M3: backend tu choi thi tra lai thu tu cu", () => {
  const src = write();
  const body = src.slice(src.indexOf("const moveChapter"),
                         src.indexOf("const makeAudio"));
  assert.match(body, /const before = chapters;/);
  assert.match(body, /setChapters\(before\);/, "loi thi phai hoan tac");
  assert.match(body, /toast\.error\(/);
});

test("M3: chan bam lien tuc trong khi dang luu", () => {
  const src = write();
  assert.match(src, /const \[savingOrder, setSavingOrder\] = useState\(false\)/);
  assert.match(src, /if \(savingOrder \|\| target < 0/);
});

test("M3: dung nut len\\/xuong chu khong phai keo-tha HTML5", () => {
  const src = write();
  // Keo-tha HTML5 khong chay tren man hinh cam ung ma khong co polyfill
  for (const attr of ["draggable", "onDragStart", "onDragOver", "onDrop"]) {
    assert.ok(!src.includes(attr), `${attr} khong hoat dong tren mobile`);
  }
});

test("M3: nut di chuyen tach khoi nhom hanh dong noi dung", () => {
  const src = write();
  assert.match(src, /className="list-move"/);
  // `.list-move` phai nam TRUOC `.list-index` trong hang
  assert.ok(
    src.indexOf('className="list-move"') < src.indexOf('className="list-index"'),
    "dieu khien vi tri phai o dau hang, canh so thu tu",
  );
});

test("M3: nut di chuyen nam tren lop phu nen bam duoc", () => {
  const r = rule(".list-move");
  assert.match(r, /position:\s*relative/);
  assert.match(r, /z-index:\s*1/);
});

test("M3: o mobile hai nut nam ngang, moi nut du 44x44", () => {
  const block = mobileBlock();
  // Xep doc thi hai nut 44px chong len nhau thanh cot 88px -> hang qua cao
  assert.match(block, /\.list-move \{[^}]*flex-direction:\s*row/);
  const icon = block.match(/\.btn-icon \{[^}]*\}/);
  assert.ok(icon, "thieu ghi de .btn-icon o mobile");
  assert.match(icon[0], /width:\s*44px/);
  assert.match(icon[0], /height:\s*44px/);
});

test("M3: trang cong khai va trang quan ly doc cung mot nguon thu tu", () => {
  // Ca hai deu doc `chapters` tu `getNovel`, backend sap theo `order_index`.
  // `\s*` vi ban trong `/write` viet `api` xuong dong roi `.getNovel(`.
  assert.match(novel(), /api\s*\.?\s*getNovel\(/);
  assert.match(write(), /api\s*\n?\s*\.getNovel\(/);
  // Khong trang nao tu sap lai danh sach chuong
  for (const [name, src] of [["novels", novel()], ["write", write()]]) {
    assert.ok(!/chapters[\w.]*\.sort\(/.test(src),
      `${name} khong duoc tu sap lai thu tu chuong`);
  }
});

/* =====================================================================
   M4 — canh bao audio khong con khop
   ===================================================================== */

test("M4: lop api khai bao truong moi la tuy chon", () => {
  assert.match(api(), /audio_outdated\?: boolean;/);
});

test("M4: trang quan ly hien badge canh bao va nut tao lai", () => {
  const src = write();
  assert.match(src, /staleByChapter\[chapter\.chapter_id\]/);
  assert.match(src, /Audio cũ/);
  assert.match(src, /Tạo lại audio/);
  // Badge canh bao dung mau canh bao, khong phai mau "on"
  assert.match(src, /badge badge-warn/);
});

test("M4: badge canh bao co CHU, khong chi dua vao mau", () => {
  const src = write();
  const at = src.indexOf("Audio cũ");
  assert.notEqual(at, -1);
  assert.match(src.slice(at - 400, at), /title="Chương đã sửa sau khi tạo audio"/);
});

test("M4: luu noi dung xong thi canh bao bat len ngay", () => {
  const src = write();
  assert.match(src, /if \(audioByChapter\[editingChapterId\]\) \{/);
  assert.match(src, /setStaleByChapter\(\(current\) => \(\{ \.\.\.current, \[editingChapterId\]: true \}\)\)/);
});

test("M4: tao lai audio xong thi canh bao tat", () => {
  const src = write();
  // Bam Y NGHIA chu khong bam ten bien: vong poll da doi tu mot job toan cuc
  // sang `Record<chapter_id, TtsJob>`, nen bien trong callback doi ten. Hanh vi
  // can giu la: job hoan tat -> tat canh bao "Audio cũ" cho DUNG chuong do.
  // Nhanh nay gio la callback `onCompleted` cua `useJobTracker` — vong poll
  // dung chung voi `/studio`. Hanh vi khong doi, chi doi cho.
  const at = src.indexOf("onCompleted:");
  assert.notEqual(at, -1, "khong tim thay nhanh xu ly job hoan tat");
  const khoi = src.slice(at, at + 600);
  assert.match(
    khoi,
    /setStaleByChapter\(\(current\) => \(\{ \.\.\.current, \[\w+\.chapter_id\]: false \}\)\)/,
    "job hoàn tất phải tắt cảnh báo audio cũ cho đúng chương",
  );
});

test("M4: cho nguoi dung CHON giu audio hay tao lai", () => {
  const src = write();
  const at = src.indexOf("Chương này đã có audio");
  assert.notEqual(at, -1, "thieu canh bao trong form sua");
  const alert = src.slice(at, at + 500);
  assert.match(alert, /không bị xoá/, "phai noi ro audio khong bi xoa");
  assert.match(alert, /giữ\s*\n?\s*audio đang có/, "phai neu lua chon giu audio");
  assert.match(alert, /Tạo lại audio/, "phai neu lua chon tao lai");
});

test("M4: trang doc chuong canh bao ngay tren trinh phat", () => {
  const src = chapter();
  assert.match(src, /audioOutdated/);
  assert.match(src, /alert alert-warn/);
  assert.match(src, /audio có thể không còn khớp/);
  assert.match(src, /vẫn nghe và tải được/, "phai noi ro audio van dung duoc");
  // Canh bao phai o TRUOC trinh phat trong DOM
  assert.ok(
    src.indexOf("alert alert-warn") < src.indexOf("<AudioPlayer"),
    "canh bao phai nam tren trinh phat",
  );
});

test("M4: chu so huu duoc chi duong tao lai bang NUT, khong phai link trong cau", () => {
  const src = chapter();
  const at = src.indexOf("Tạo lại audio trong khu vực tác giả");
  assert.notEqual(at, -1);
  // Lien ket trong cau chi cao ~17px o mobile — phai la nut that
  assert.match(src.slice(at - 200, at), /className="btn btn-sm"/);
  assert.match(src, /isOwner \? \(/);
});

test("M4: danh sach chuong cong khai cung hien canh bao", () => {
  const src = novel();
  assert.match(src, /chapter\.audio_outdated \?/);
  assert.match(src, /Audio cũ/);
});

test("M4: canh bao KHONG bao gio dan den xoa audio", () => {
  for (const [name, src] of [["write", write()], ["novels", novel()],
                             ["chapters", chapter()]]) {
    const stale = src.split("\n").filter((line) =>
      /outdated|stale/i.test(line) && /delete|Xoá|xoa/i.test(line));
    assert.deepEqual(stale, [],
      `${name}: khong duoc gan canh bao audio cu voi hanh dong xoa`);
  }
});

test("M4: audio cu van phat va tai duoc nhu thuong", () => {
  const src = novel();
  // Nut Nghe khong bi vo hieu vi audio cu
  const at = src.indexOf("chapter.has_audio ?");
  const block = src.slice(at, at + 1200);
  assert.match(block, /Nghe/);
  assert.ok(
    !/disabled=\{[^}]*outdated/.test(block),
    "khong duoc chan phat chi vi audio cu",
  );
});

/* =====================================================================
   Khong pha thu da co
   ===================================================================== */

test("M3\\/M4 khong pha M2: van chi mot lan goi getNovel", () => {
  const src = novel();
  assert.equal((src.match(/api\.get\w+\(/g) || []).length, 1);
  assert.ok(!/\.getChapter\(/.test(src));
});

test("M3\\/M4 khong pha M1: khoi mobile van nang vung bam len 44px", () => {
  const block = mobileBlock();
  const r = block.match(/([^{}]*)\{[^{}]*min-height:\s*44px[^{}]*\}/);
  assert.ok(r, "mat quy tac 44px");
  const selectors = r[1].replace(/\/\*[\s\S]*?\*\//g, "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  for (const cls of [".btn", ".btn-sm", ".chip", ".seg-item", ".nav-link",
                     ".account-link", ".brand"]) {
    assert.ok(selectors.includes(cls), `mat ${cls} khoi quy tac 44px`);
  }
});

test("cac endpoint cu con nguyen, chi them dung mot cai", () => {
  const found = new Set([...api().matchAll(/\/api\/([a-z]+)/g)].map((m) => m[1]));
  assert.deepEqual(
    [...found].sort(),
    ["audio", "auth", "chapters", "health", "jobs", "novels", "voices"],
    "khong duoc them ho tai nguyen moi",
  );
  // Duong doi thu tu nam duoi `novels`, khong phai mot ho moi
  assert.match(api(), /novels\/\$\{novelId\}\/chapters\/order/);
});

test("publish, unpublish, xoa va tai MP3 van con", () => {
  const a = api();
  for (const fn of ["publishNovel:", "unpublishNovel:", "deleteNovel:",
                    "deleteChapter:", "updateChapter:", "audioLink:"]) {
    assert.match(a, new RegExp(fn.replace(":", "\\:")), `mat ${fn}`);
  }
  assert.match(read("../src/components/AudioPlayer.tsx"), /Tải MP3/);
});

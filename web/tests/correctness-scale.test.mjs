// N+1 o thu vien audio, va cac khai bao kem theo cua ba ban sua lan nay.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

const library = () => read("../src/app/library/page.tsx");
const studio = () => read("../src/app/studio/page.tsx");
const api = () => read("../src/lib/api.ts");

/** Khop `api.xxx(` ke ca khi viet `api` xuong dong roi `.xxx(`. */
const callsApi = (src, method) =>
  new RegExp(String.raw`api\s*\.\s*${method}\s*\(`).test(src);

/* ================================================================
   N+1 o thu vien audio
   ================================================================ */

test("thu vien khong con goi getNovel cho tung truyen", () => {
  const src = library();
  assert.ok(
    !/\.getNovel\(/.test(src),
    "khong duoc goi getNovel — dung /api/chapters?mine=true",
  );
  assert.ok(
    !/novels\.map\(\s*\(novel\)\s*=>/.test(src),
    "khong duoc lap qua danh sach truyen de goi API",
  );
});

test("thu vien lay chuong bang MOT request", () => {
  const src = library();
  assert.ok(callsApi(src, "myChapters"), "phai goi api.myChapters()");
  assert.match(api(), /myChapters:/);
  assert.match(api(), /\/api\/chapters\?mine=true/);
});

test("ba request song song, khong phai hai vong tuan tu", () => {
  const src = library();
  const at = src.indexOf("const gather");
  const body = src.slice(at, src.indexOf("}, []);", at));
  assert.match(body, /Promise\.all\(\[/);
  // Ban cu co HAI cho await: mot cho danh sach, mot cho vong getNovel
  assert.equal((body.match(/await Promise\.all/g) ?? []).length, 1,
    "chi duoc mot lan cho song song");
  for (const fn of ["listNovels", "listJobs", "myChapters"]) {
    assert.ok(callsApi(body, fn), `thieu ${fn} trong lan goi song song`);
  }
});

test("so request khong phu thuoc so truyen", () => {
  const src = library();
  const at = src.indexOf("const gather");
  const body = src.slice(at, src.indexOf("}, []);", at));
  // Khong duoc co loi goi api nao ben trong mot vong lap.
  //
  // KHONG ghep regex qua ca callback: `[^)]*` khong khop duoc dang
  // `.map((novel) =>` vi co hai dau ngoac, va assertion se dat tren ca code con
  // loi. Cat theo tung `.map(` roi soi mot doan ngan phia sau thi chac chan hon.
  for (const kind of [".map(", ".forEach(", ".flatMap("]) {
    let from = 0;
    for (;;) {
      const found = body.indexOf(kind, from);
      if (found === -1) break;
      const sau = body.slice(found, found + 220);
      assert.ok(
        !/\bapi\s*[.\n]/.test(sau),
        `co loi goi API ngay sau ${kind}: ${sau.slice(0, 90).replace(/\s+/g, " ")}`,
      );
      from = found + kind.length;
    }
  }
});

test("bang tra duoc dung tu chuong, khong tu tung truyen", () => {
  const src = library();
  assert.match(src, /new Map\(novelList\.novels\.map/);
  assert.match(src, /chapterList\.chapters\.forEach/);
  // Chuong khong tra ra truyen thi bo qua, khong hien hang thieu ten
  assert.match(src, /if \(novel\) index\.set/);
});

test("Audio Studio von da la hang so — khong duoc lam no thanh N+1", () => {
  const src = studio();
  // Chi MOT getNovel, cho dung kho chua cua Studio
  assert.equal((src.match(/api\.getNovel\(/g) ?? []).length, 1);
  assert.match(src, /ensureStudioNovel\(\)/);
  assert.ok(
    !/novels\.map\(\s*\(novel\)\s*=>[\s\S]{0,60}api\./.test(src),
    "khong duoc goi API cho tung truyen",
  );
});

test("endpoint chuong cua toi khong kem noi dung, khong kem URL audio", () => {
  const a = api();
  const at = a.indexOf("myChapters:");
  const block = a.slice(at, at + 260);
  // Kieu tra ve la Chapter[] — `content` la truong tuy chon, backend khong gui
  assert.match(block, /chapters: Chapter\[\]/);
  assert.ok(!/audio_url|object_key/.test(block));
});

/* ================================================================
   Khai bao kem theo
   ================================================================ */

test("khong them ho tai nguyen moi", () => {
  const found = new Set([...api().matchAll(/\/api\/([a-z]+)/g)].map((m) => m[1]));
  /*
    Bon ho MOI cua V2 — `creator`, `users`, `search`, `listens`. Bai test nay
    van la mot cai chot: no khong cam them ho, no bat MOI lan them phai di qua
    day. Mot ho tai nguyen moi la mot be mat API moi, va no phai duoc ai do co y
    viet vao danh sach nay chu khong tu xuat hien.
  */
  assert.deepEqual(
    [...found].sort(),
    ["admin", "audio", "auth", "chapters", "creator", "health", "jobs",
     "listens", "novels", "search", "users", "voices"],
    "chi duoc dung lai cac ho da co",
  );
});

test("cac ham api cu con nguyen", () => {
  const a = api();
  for (const fn of ["listNovels:", "browseNovels:", "novelTags:", "getNovel:",
                    "publishNovel:", "unpublishNovel:", "deleteNovel:",
                    "updateChapter:", "deleteChapter:", "reorderChapters:",
                    "getChapter:", "audioLink:", "listJobs:", "myChapters:"]) {
    assert.ok(a.includes(fn), `mat ${fn}`);
  }
});

test("khong pha L2: trang kham pha van phan trang phia server", () => {
  const fanfic = read("../src/app/fanfic/page.tsx");
  assert.ok(callsApi(fanfic, "browseNovels"));
  assert.ok(!/novels\.filter\(/.test(fanfic));
  assert.match(fanfic, /className="pager"/);
});

test("khong pha M2/M3/M4", () => {
  assert.match(read("../src/app/novels/[id]/page.tsx"), /<AudioPlayer/);
  assert.match(read("../src/app/write/page.tsx"), /api\.reorderChapters\(/);
  assert.match(read("../src/app/novels/[id]/page.tsx"), /chapter\.audio_outdated \?/);
  assert.match(read("../src/app/chapters/[id]/page.tsx"), /audioOutdated/);
});

test("tai MP3 va trinh phat van con", () => {
  const player = read("../src/components/AudioPlayer.tsx");
  assert.match(player, /Tải MP3/);
  assert.match(player, /resolveAudio/);
  assert.match(library(), /<AudioPlayer/);
});

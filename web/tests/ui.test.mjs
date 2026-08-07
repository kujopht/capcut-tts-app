// Regression cho hai lo hong giao dien da phat hien va sua o lan nay.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const has = (p) => existsSync(new URL(p, import.meta.url));

/* ------------------------------------------------------------------ route */

test("du cac route cua hai khu vuc san pham", () => {
  for (const route of [
    "../src/app/page.tsx",           // trang chu
    "../src/app/studio/page.tsx",    // Audio Studio
    "../src/app/fanfic/page.tsx",    // kham pha fanfic
    "../src/app/write/page.tsx",     // khu vuc tac gia
    "../src/app/library/page.tsx",   // thu vien audio chung
    "../src/app/account/page.tsx",   // tai khoan
    "../src/app/login/page.tsx",
    "../src/app/novels/[id]/page.tsx",
    "../src/app/chapters/[id]/page.tsx",
  ]) {
    assert.ok(has(route), `thieu route ${route}`);
  }
});

test("header co du bon muc dieu huong", () => {
  const nav = read("../src/components/NavAuth.tsx");
  for (const target of ["/studio", "/fanfic", "/library"]) {
    assert.ok(nav.includes(target), `header thieu link ${target}`);
  }
  assert.match(nav, /\/account/, "header thieu khu vuc tai khoan");
});

test("trang chu dung hai feature card, khong chia doi 50/50", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /href="\/studio"/);
  assert.match(home, /href="\/fanfic"/);
  assert.equal((home.match(/className="feature"/g) ?? []).length, 2);

  const css = read("../src/app/globals.css");
  assert.ok(
    !/grid-template-columns:\s*1fr\s+1fr/.test(css),
    "khong duoc chia doi man hinh co dinh 50/50",
  );
});

/* -------------------------------------------- LOI 1: khong co nut xuat ban */

test("khu vuc tac gia goi publishNovel", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /api\.publishNovel\(/, "phai goi api.publishNovel");
  assert.match(write, /Xuất bản/, "phai co nut Xuat ban");
});

test("xuat ban co hop thoai xac nhan", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /ConfirmDialog/);
  assert.match(write, /confirmPublish/);
});

/* ------------------------------- LOI 2: the <audio> khong gui duoc token */

test("trinh phat khong gan thang /api/audio vao src", () => {
  const player = read("../src/components/AudioPlayer.tsx");
  assert.ok(
    !player.includes("api.audioUrl("),
    "audioUrl tra URL khong kem xac thuc — the <audio> se nhan 401",
  );
  assert.match(player, /resolveAudio/, "phai lay URL qua resolveAudio");
});

test("resolveAudio hoi backend URL thay vi tu ghep", () => {
  const audio = read("../src/lib/audio.ts");
  assert.match(audio, /api\.audioLink\(/);
  // Che do R2 dung URL ky; che do cuc bo stream kem token roi doi thanh blob
  assert.match(audio, /createObjectURL/);
  assert.match(audio, /Authorization/);
});

test("lop api co ham xin URL audio", () => {
  const api = read("../src/lib/api.ts");
  assert.match(api, /audioLink:/);
  assert.match(api, /\/url\$\{download \? "\?download=true" : ""\}/);
});

test("co nut tai MP3", () => {
  const player = read("../src/components/AudioPlayer.tsx");
  assert.match(player, /download=\{audioFileName/);
  assert.match(player, /Tải MP3/);
});

/* ------------------------------------------------------ tach hai khu vuc */

test("audio tu Studio khong tro thanh chuong fanfic", () => {
  const workspace = read("../src/lib/workspace.ts");
  assert.match(workspace, /STUDIO_TAG = "audio-studio"/);
  assert.match(workspace, /export function fanficOnly/);

  // Ca hai noi liet ke truyen fanfic deu phai loc kho chua cua Studio
  for (const page of ["../src/app/fanfic/page.tsx", "../src/app/write/page.tsx"]) {
    assert.match(read(page), /fanficOnly\(/, `${page} phai loc kho Studio`);
  }
});

test("thu vien chung phan biet nguon audio", () => {
  const library = read("../src/app/library/page.tsx");
  assert.match(library, /isStudioNovel\(/);
  assert.match(library, /fromStudio/);
});

/* --------------------------------------------------- Audio Studio day du */

test("Audio Studio co du cac dieu khien bat buoc", () => {
  const studio = read("../src/app/studio/page.tsx");
  assert.match(studio, /textarea/, "phai co o dan van ban tu do");
  assert.match(studio, /MAX_CHARS/, "phai hien gioi han ky tu");
  assert.match(studio, /ký tự/, "phai hien so ky tu");
  assert.match(studio, /RATES/, "phai chon duoc toc do");
  assert.match(studio, /api\.createJob\(\s*\n?\s*created\.chapter\.chapter_id,\s*\n?\s*voiceId,\s*\n?\s*rate,?\s*\n?\s*\)/s,
    "phai gui rate len backend");
  assert.match(studio, /Thử lại/, "job that bai phai co nut thu lai");
  assert.match(studio, /Lịch sử audio/, "phai co lich su");
});

test("bon trang thai job deu duoc xu ly", () => {
  const ui = read("../src/components/ui.tsx");
  for (const status of ["pending", "running", "completed", "failed"]) {
    assert.ok(ui.includes(status), `thieu trang thai ${status}`);
  }
  // Trang thai phai co CHU, khong chi dua vao mau
  assert.match(ui, /Đang xếp hàng/);
  assert.match(ui, /Đang xử lý/);
  assert.match(ui, /Hoàn tất/);
  assert.match(ui, /Thất bại/);
});

/* --------------------------------------------------------- design system */

test("design system co du token va thanh phan", () => {
  const css = read("../src/app/globals.css");
  for (const token of ["--bg:", "--text:", "--brand:", "--s4:", "--r2:", "--t-base:"]) {
    assert.ok(css.includes(token), `thieu token ${token}`);
  }
  for (const part of [".btn", ".card", ".badge", ".input", ".modal", ".toast", ".sk", ".progress"]) {
    assert.ok(css.includes(part), `thieu thanh phan ${part}`);
  }
});

test("ho tro desktop, tablet va mobile", () => {
  const css = read("../src/app/globals.css");
  assert.match(css, /@media \(max-width: 900px\)/, "thieu breakpoint tablet");
  assert.match(css, /@media \(max-width: 640px\)/, "thieu breakpoint mobile");
});

test("widget audio duoc ep ve dark theme", () => {
  const css = read("../src/app/globals.css");
  assert.match(css, /color-scheme: dark/);
  assert.match(css, /\.player audio/);
});

test("link phan biet duoc voi van ban thuong", () => {
  const css = read("../src/app/globals.css");
  assert.ok(
    !/^a \{[^}]*color: inherit/ms.test(css),
    "link khong duoc lay mau chu xung quanh",
  );
  assert.match(css, /a \{\s*color: var\(--brand\)/);
});

test("ton trong prefers-reduced-motion", () => {
  assert.match(read("../src/app/globals.css"), /prefers-reduced-motion/);
});

/* -------------------------------------------------------- kha nang tiep can */

test("layout co skip-link, lang va viewport", () => {
  const layout = read("../src/app/layout.tsx");
  assert.match(layout, /lang="vi"/);
  assert.match(layout, /skip-link/);
  assert.match(layout, /id="main"/);
  assert.match(layout, /export const viewport/, "thieu khai bao viewport");
});

test("trang thai dong deu duoc thong bao cho doc man hinh", () => {
  const ui = read("../src/components/ui.tsx");
  assert.match(ui, /role="status"/);
  assert.match(ui, /role="alert"/);
  assert.match(ui, /role="progressbar"/);
  assert.match(read("../src/lib/toast.tsx"), /aria-live="polite"/);
});

test("hop thoai xac nhan bay focus va dong bang Escape", () => {
  const ui = read("../src/components/ui.tsx");
  assert.match(ui, /role="dialog"/);
  assert.match(ui, /aria-modal="true"/);
  assert.match(ui, /"Escape"/);
  assert.match(ui, /event\.key !== "Tab"/, "phai bay focus trong hop thoai");
});

test("khong dung eslint-disable de lam ngo canh bao", () => {
  for (const file of [
    "../src/components/AudioPlayer.tsx",
    "../src/components/ui.tsx",
    "../src/app/studio/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/library/page.tsx",
    "../src/lib/useAsyncData.ts",
  ]) {
    assert.ok(!read(file).includes("eslint-disable"), `${file} co eslint-disable`);
  }
});

/* ------------------------------- giong mac dinh (loi tim thay khi chay that) */

test("giong mac dinh khop TOAN BO id, khong phai chuoi con", async () => {
  const { defaultVoiceId, VERIFIED_VOICE_ID } = await import(
    "../src/lib/voices.ts"
  );
  const v = (voice_id, installed = true) => ({ voice_id, installed });

  // Bay da tung sap: mot giong CapCut cung ten "HoaiMy" bi chon nham,
  // CapCut tra ve TTSInvalidSpeaker ngay lan tao dau tien.
  assert.equal(
    defaultVoiceId([v("capcut:BV074_HoaiMy"), v(VERIFIED_VOICE_ID)]),
    VERIFIED_VOICE_ID,
  );
  // Khong co giong da kiem chung -> uu tien Edge tieng Viet
  assert.equal(
    defaultVoiceId([v("capcut:BV074_HoaiMy"), v("edge:vi-VN-NamMinhNeural")]),
    "edge:vi-VN-NamMinhNeural",
  );
  // Bo qua giong chua cai
  assert.equal(
    defaultVoiceId([v(VERIFIED_VOICE_ID, false), v("capcut:x")]),
    "capcut:x",
  );
  assert.equal(defaultVoiceId([]), "");
});

test("hai trang dung chung bo chon giong", () => {
  for (const page of ["../src/app/studio/page.tsx", "../src/app/write/page.tsx"]) {
    const src = read(page);
    assert.match(src, /defaultVoiceId\(/, `${page} phai dung defaultVoiceId`);
    assert.ok(
      !src.includes('includes("HoaiMy")'),
      `${page} khong duoc so khop chuoi con ten giong`,
    );
  }
});

/* ------------------------------------------------------- CRUD fanfic */

test("lop api co du CRUD truyen va chuong", () => {
  const api = read("../src/lib/api.ts");
  for (const fn of [
    "updateNovel:", "deleteNovel:", "unpublishNovel:",
    "updateChapter:", "deleteChapter:",
  ]) {
    assert.ok(api.includes(fn), `lop api thieu ${fn}`);
  }
  assert.match(api, /method: "PATCH"/);
  assert.match(api, /method: "DELETE"/);
});

test("khu vuc tac gia noi day du CRUD", () => {
  const write = read("../src/app/write/page.tsx");
  for (const call of [
    "api.updateNovel(", "api.deleteNovel(", "api.publishNovel(",
    "api.unpublishNovel(", "api.updateChapter(", "api.deleteChapter(",
  ]) {
    assert.ok(write.includes(call), `khu vuc tac gia chua goi ${call}`);
  }
});

test("moi thao tac xoa deu phai qua modal xac nhan", () => {
  const write = read("../src/app/write/page.tsx");
  // Khong duoc goi thang api.delete* tu onClick
  assert.ok(
    !/onClick=\{\(\)\s*=>\s*api\.delete/.test(write),
    "khong duoc xoa ngay khi bam, phai qua xac nhan",
  );
  assert.match(write, /setPendingDelete\(\{\s*\n?\s*kind: "novel"/s);
  assert.match(write, /setPendingDelete\(\{\s*\n?\s*kind: "chapter"/s);
  assert.match(write, /confirmLabel="Xoá vĩnh viễn"/);
  assert.match(write, /danger/, "hop thoai xoa phai o dang canh bao");
});

test("xac nhan xoa noi ro se mat nhung gi", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /toàn bộ \{chapters\.length\} chương/);
  assert.match(write, /không hoàn tác được/);
  assert.match(write, /file audio/);
});

test("nut xuat ban va go xuat ban deu co xac nhan rieng", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /setConfirmPublish\("publish"\)/);
  assert.match(write, /setConfirmPublish\("unpublish"\)/);
  assert.match(write, /Gỡ xuất bản truyện này\?/);
  assert.match(write, /Xuất bản truyện này\?/);
});

test("moi thao tac ghi deu co trang thai dang chay va toast", () => {
  const write = read("../src/app/write/page.tsx");
  for (const busy of [
    "creatingNovel", "savingNovel", "creatingChapter", "savingChapter",
    "togglingPublish", "deleting",
  ]) {
    assert.ok(write.includes(busy), `thieu trang thai dang chay: ${busy}`);
  }
  assert.match(write, /toast\.ok\(/);
  assert.match(write, /toast\.error\(errorMessage\(cause\)\)/);
});

test("giao dien cap nhat ngay sau khi xoa, khong doi tai lai trang", () => {
  const write = read("../src/app/write/page.tsx");
  // Xoa truyen: bo khoi danh sach va chon lai truyen khac ngay trong bo nho
  assert.match(write, /novels\.filter\(\(n\) => n\.novel_id !== target\.id\)/);
  assert.match(write, /setSelectedId\(left\[0\]\?\.novel_id \?\? ""\)/);
  // Xoa chuong: bo khoi danh sach chuong
  assert.match(write, /current\.filter\(\(c\) => c\.chapter_id !== target\.id\)/);
  // Khong duoc tai lai ca trang
  assert.ok(!write.includes("location.reload"), "khong duoc tai lai trang");
});

test("sua truyen khong gui truong do server quyet dinh", () => {
  const api = read("../src/lib/api.ts");
  const block = api.slice(api.indexOf("updateNovel:"), api.indexOf("deleteNovel:"));
  for (const field of ["state", "owner_id", "novel_id"]) {
    assert.ok(!block.includes(`${field}?:`), `updateNovel khong duoc nhan ${field}`);
  }
});

test("khong goi setState long trong ham cap nhat cua setState", () => {
  // Bay da tung sap: setSelectedId nam trong updater cua setNovels khien React
  // chan lai, backend xoa xong ma giao dien khong doi va khong co toast.
  const write = read("../src/app/write/page.tsx");
  const nested = /set[A-Z]\w*\(\((?:current|prev)\)\s*=>\s*\{[^}]*\bset[A-Z]\w*\(/s;
  assert.ok(!nested.test(write), "hàm cập nhật của setState phải thuần khiết");
});

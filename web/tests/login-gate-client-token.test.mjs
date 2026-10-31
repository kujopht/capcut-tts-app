// Fix login-gate: muc luc + trang chuong phan anh dung viewer da dang nhap.
//
// Root cause: trang may chu fetch khong token (token chi o localStorage)
// nen backend tra khoa theo khach — user DA dang nhap van thay "Can dang
// nhap" o muc luc va 403 o trang chuong. Fix: refetch co token o client.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
/** Xoa whitespace de assert bat chap xuong dong khi chain promise. */
const flat = (s) => s.replace(/\s+/g, "");

const chapterList = () => read("../src/components/novel/ChapterList.tsx");
const novelPage = () => read("../src/app/novels/[id]/page.tsx");
const chapterPage = () => read("../src/app/chapters/[id]/page.tsx");
const retry = () => read("../src/components/reader/ChapterGateRetry.tsx");

test("muc luc: server chapters lam khoi diem, co token thi fetch lai bang token", () => {
  const src = chapterList();
  // Khoi diem tu props server (khach + SEO giu nguyen).
  assert.ok(src.includes("useState(chapters)"), "ChapterList phai khoi tao state tu chapters cua server");
  // Chi fetch lai khi co token — khach khong them request.
  assert.ok(src.includes("getToken()"), "ChapterList phai kiem tra token truoc khi fetch lai");
  assert.ok(
    flat(src).includes("api.getNovel(novelId)"),
    "ChapterList phai fetch lai getNovel bang token",
  );
  // Cap nhat co khoa tu ket qua fetch.
  assert.ok(src.includes("locked: c.locked"), "ChapterList phai cap nhat locked tu ban fetch lai");
  assert.ok(
    src.includes("premium_locked: c.premium_locked"),
    "ChapterList phai cap nhat premium_locked tu ban fetch lai",
  );
  // Fetch hong thi giu ban server (khong vo muc luc).
  assert.ok(src.includes(".catch("), "ChapterList phai co catch giu ban server khi fetch lai hong");
});

test("trang truyen: van truyen chapters cua server xuong ChapterList (fallback)", () => {
  const src = novelPage();
  assert.ok(src.includes("<ChapterList"), "trang truyen phai render ChapterList");
  assert.ok(
    src.includes("chapters={chapters.map"),
    "trang truyen phai truyen chapters cua server xuong",
  );
});

test("trang chuong: nhanh 403 dung ChapterGateRetry thay vi EmptyState kho", () => {
  const src = chapterPage();
  assert.ok(src.includes("ChapterGateRetry"), "trang chuong phai dung ChapterGateRetry o nhanh 403");
  assert.ok(src.includes('gateKind="login"'), "nhanh login phai truyen gateKind login");
  assert.ok(src.includes('gateKind="premium"'), "nhanh premium phai truyen gateKind premium");
  // Duong thanh cong khong doi: van ve ChapterExperience tu server.
  assert.ok(
    src.includes("<ChapterExperience"),
    "duong thanh cong van ve ChapterExperience tu server",
  );
});

test("ChapterGateRetry: khach khong token thi khong request, hien dung EmptyState", () => {
  const src = retry();
  // Khoi tao = EmptyState cua server (khong flash loading cho khach).
  assert.ok(
    src.includes("useState<TrangThai>(() => biKhoa(gateKind))"),
    "khoi tao phai la EmptyState theo gateKind",
  );
  // Kiem tra token truoc khi fetch — khong token thi return som, khong request.
  assert.ok(src.includes("if (!getToken()) return;"), "phai return som khi khong co token");
  // Fetch bang api co san (Bearer tu localStorage), khong ghep token vao URL.
  assert.ok(flat(src).includes("api.getChapter(chapterId)"), "phai fetch lai bang api.getChapter");
  assert.ok(!src.includes("token="), "khong duoc dua token len URL");
  // Khong import module chi chay o server.
  assert.ok(!src.includes("next/headers"), "component client khong duoc import next/headers");
  // 403 tiep thi ve EmptyState theo loai gate (tach bang "Premium" nhu server).
  assert.ok(
    src.includes('err.message.includes("Premium")'),
    "403 tiep thi tach loai gate bang detail Premium",
  );
  // Thanh cong thi ve dung noi dung (ChapterExperience).
  assert.ok(src.includes("<ChapterExperience"), "fetch thanh cong phai ve ChapterExperience");
});

test("ChapterGateRetry: doi chuong thi xoa noi dung cu ngay", () => {
  const src = retry();
  assert.ok(
    src.includes("setTrangThai(biKhoa(gateKind));"),
    "effect phai reset ve khoa khi doi chuong",
  );
});

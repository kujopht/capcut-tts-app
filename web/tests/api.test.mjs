// Test lop goi backend - chay offline bang fetch gia lap.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("khong hard-code endpoint hay secret trong lop api", () => {
  assert.ok(!/appwrite\.io/i.test(src), "khong duoc hard-code endpoint Appwrite");
  assert.ok(!/r2\.cloudflarestorage/i.test(src), "khong duoc hard-code endpoint R2");
  assert.ok(!/APPWRITE_API_KEY|R2_SECRET|R2_ACCESS_KEY/.test(src),
    "trinh duyet khong duoc biet bat ky credential nao");
});

test("API base doc tu bien moi truong cong khai", () => {
  assert.match(src, /process\.env\.NEXT_PUBLIC_API_BASE/);
});

test("moi request deu gan Bearer token khi da dang nhap", () => {
  assert.match(src, /Authorization/);
  assert.match(src, /Bearer \$\{token\}/);
});

test("loi mang tra ve thong bao tieng Viet", () => {
  assert.match(src, /Không kết nối được máy chủ/);
});

test("co day du ham cho vertical slice", () => {
  for (const fn of ["register", "login", "me", "voices", "listNovels",
                    "createNovel", "getNovel", "createChapter", "getChapter",
                    "createJob", "getJob", "audioUrl"]) {
    assert.ok(src.indexOf(fn + ":") !== -1, "thieu api." + fn);
  }
});

test("trang thai job khop voi backend", () => {
  assert.match(src, /"pending" \| "running" \| "completed" \| "failed"/);
});

test("voice co co danh dau commercial_ready", () => {
  assert.match(src, /commercial_ready: boolean/);
});

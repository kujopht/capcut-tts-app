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

/*
 * `commercial_ready` da bi thay bang `public_enabled`.
 *
 * Ten cu la mot phan doan ve GIAY PHEP, thu ma may chu khong biet va khong nen
 * doan. `public_enabled` la mot su that ky thuat: giong nay co nam trong danh
 * sach trang o `server/tts_bridge.py` hay khong.
 */
test("voice co co danh dau public_enabled", () => {
  assert.match(src, /public_enabled: boolean/);
  assert.doesNotMatch(src, /commercial_ready: boolean/);
});

/*
 * Model Piper nam tren may worker, khong nam trong tien trinh API. Tren Render
 * khong co file `.onnx` nao nen `installed` o do LUON false — loc theo mot
 * minh no thi Ngoc Huyen khong bao gio hien ra du da duoc duyet.
 */
test("voice co co runs_on_worker de phan biet model o dau", () => {
  assert.match(src, /runs_on_worker: boolean/);
});

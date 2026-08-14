/**
 * V5 — /translate. Cung phong cach voi cac bai test khac trong thu muc nay:
 * doc THANG source, khang dinh dac diem quan trong bang regex.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const page = () => read("../src/app/translate/page.tsx");
const api = () => read("../src/lib/api.ts");
const navAuth = () => read("../src/components/NavAuth.tsx");

test("menu Cong cu co loi vao Dich tieu thuyet", () => {
  assert.match(navAuth(), /href="\/translate"/);
});

test("/translate doi dang nhap, dung loginHref chu khong tu ve mot form", () => {
  const src = page();
  assert.match(src, /loginHref\("\/translate"\)/);
});

test("/translate goi du bon thao tac chinh cua V5", () => {
  const src = page();
  assert.match(src, /translate\.createProject\(/);
  assert.match(src, /translate\.uploadProject\(/);
  assert.match(src, /translate\.createJob\(/);
  assert.match(src, /translate\.importToDraft\(/);
});

test("upload tep dung base64 (khong dung multipart/UploadFile)", () => {
  const src = page();
  assert.match(src, /docTepThanhBase64/);
  assert.doesNotMatch(src, /FormData/);
});

test("glossary: co the khoa/mo khoa mot thuat ngu", () => {
  const src = page();
  assert.match(src, /updateGlossaryEntry\(projectId, entry\.term_id, \{\s*locked:/);
});

test("khong tao AudioEngine/the <audio> thu hai trong trang dich", () => {
  const src = page();
  assert.doesNotMatch(src, /<audio\b/);
  assert.doesNotMatch(src, /AudioEngineProvider/);
});

test("lib/api.ts: duong REST /api/translate/* dung hinh dang", () => {
  const src = api();
  assert.match(src, /createProject:[\s\S]{0,260}\/api\/translate\/projects"/);
  assert.match(src, /uploadProject:[\s\S]{0,260}\/api\/translate\/projects\/upload"/);
  assert.match(src, /createJob:[\s\S]{0,200}\/api\/translate\/projects\/\$\{[\s\S]{0,80}\/jobs`/);
  assert.match(src, /importToDraft:[\s\S]{0,260}\/import`/);
});

test("uploadProject gui base64 CHINH LA noi dung tep, khong phai van ban da giai ma", () => {
  const src = api();
  const at = src.indexOf("uploadProject:");
  const than = src.slice(at, at + 500);
  assert.match(than, /base64: fields\.base64/);
});

test("V5 tach bach voi Audio Studio: khong dung chung tts_jobs", () => {
  // Kiem gian tiep qua backend: khong co tham chieu tts_jobs trong tang
  // service V5 — xac nhan da doc dung source, khong doan.
  const svc = read("../../server/translation_service.py");
  assert.doesNotMatch(svc, /tts_jobs/);
});

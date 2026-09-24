/*
 * Trang chuong (`/chapters/[id]`) — trang thai chuong CHI CO AUDIO.
 *
 * 13 tac pham Fanfic nhap tu audio dai tap (xem docs/reports/) khong co van
 * ban goc: `chapter.content` rong nhung `audio` ton tai. Truoc day trang hien
 * "Chương này chưa có nội dung." — doc nhu mot loi/thieu du lieu, trong khi
 * day la trang thai BINH THUONG cua nhom tac pham nay.
 *
 * Tu sprint doc/nghe 2026-09-24 doc va nghe la MOT trang: chuong khong co chu
 * mo thang che do NGHE (trinh phat lon o dau trang), va khung chu noi ro
 * "chỉ có bản audio" — khong con nut dan sang trang `/listen` rieng nua.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cheDoKhiMo } from "../src/lib/readerSession.ts";

const src = readFileSync(
  new URL("../src/components/reader/ChapterExperience.tsx", import.meta.url),
  "utf8",
);

const codeOnly = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

test("chuong khong noi dung NHUNG co audio -> mo thang che do Nghe", () => {
  // Du URL hay cookie xin "read"/"read_listen": khong co chu thi chi co nghe.
  for (const tuUrl of [undefined, "read", "read_listen", "listen"]) {
    assert.equal(cheDoKhiMo({ tuUrl, daLuu: "read", coAudio: true, coChu: false }), "listen");
  }
  // Nguoc lai: khong co audio thi luon doc, ke ca khi URL xin nghe.
  assert.equal(cheDoKhiMo({ tuUrl: "listen", daLuu: "listen", coAudio: false, coChu: true }), "read");
});

test("chuong khong noi dung NHUNG co audio -> trang thai audio-only, khong phai canh bao chung", () => {
  const code = codeOnly(src);
  const audioBranch = code.match(/coChu \?\s*\(?\s*noiDungChu\s*\)?\s*:\s*hasAudio\s*\?([\s\S]*?):\s*\(/);
  assert.ok(audioBranch, "khong tim thay nhanh rieng cho truong hop co audio nhung khong co content");
  const branchBody = audioBranch[1];
  assert.match(branchBody, /Chương này chỉ có bản audio/, "thieu thong bao audio-only ro rang");
  assert.ok(!/\/listen\//.test(branchBody), "khong con dan sang trang Nghe rieng");
});

test("chuong khong noi dung VA khong co audio -> van giu thong bao chung (khong xoa nhanh that-su-trong)", () => {
  assert.match(
    codeOnly(src),
    /Chương này chưa có nội dung\./,
    "truong hop chuong that su trong (khong audio) van can mot thong bao — khong duoc xoa nham",
  );
});

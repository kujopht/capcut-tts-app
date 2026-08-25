/*
 * Trang doc chuong (`/chapters/[id]`) — trang thai chuong CHI CO AUDIO.
 *
 * 13 tac pham Fanfic nhap tu audio dai tap (xem docs/reports/) khong co van
 * ban goc: `chapter.content` rong nhung `audio` ton tai. Truoc day trang hien
 * "Chương này chưa có nội dung." — doc nhu mot loi/thieu du lieu, trong khi
 * day la trang thai BINH THUONG cua nhom tac pham nay. Test nay khoa lai:
 * co audio thi phai dan ro rang toi trai nghiem nghe, khong phai mot dong
 * canh bao mo ho.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(
  new URL("../src/app/chapters/[id]/page.tsx", import.meta.url),
  "utf8",
);

const codeOnly = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

test("chuong khong noi dung NHUNG co audio -> trang thai audio-only, khong phai canh bao chung", () => {
  const code = codeOnly(src);
  // Nhanh audio phai duoc kiem TRUOC nhanh "chua co noi dung" chung, va phai
  // dua vao chinh bien `audio` da fetch san (khong goi lai API).
  const audioBranch = code.match(/chapter\.content\s*\?[\s\S]*?:\s*audio\s*\?([\s\S]*?):\s*\(/);
  assert.ok(audioBranch, "khong tim thay nhanh rieng cho truong hop co audio nhung khong co content");

  const branchBody = audioBranch[1];
  assert.match(branchBody, /Nghe tập này/, "thieu nut hanh dong ro rang toi trai nghiem nghe");
  assert.match(
    branchBody,
    /href=\{`\/listen\/\$\{chapter\.chapter_id\}`\}/,
    "nut hanh dong phai dan toi /listen/[chapter_id], khong phai noi khac",
  );
});

test("chuong khong noi dung VA khong co audio -> van giu thong bao chung (khong xoa nhanh that-su-trong)", () => {
  assert.match(
    codeOnly(src),
    /Chương này chưa có nội dung\./,
    "truong hop chuong that su trong (khong audio) van can mot thong bao — khong duoc xoa nham",
  );
});

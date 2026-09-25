/*
 * KHONG mat khau / dang nhap gan cung trong ma web.
 *
 * Do 2026-09-25: nut "Đăng nhập nhanh (Test)" o /library goi `signIn(email,
 * mat khau)` voi chuoi that va KHONG co dieu kien moi truong, nen mat khau nam
 * trong bundle production cong khai. Bai nay quet MOI tep trong src/.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

function tatCaTep(thuMuc) {
  const ra = [];
  for (const ten of readdirSync(thuMuc)) {
    const p = join(thuMuc, ten);
    if (statSync(p).isDirectory()) ra.push(...tatCaTep(p));
    else if (/\.(tsx?|jsx?|mjs)$/.test(ten)) ra.push(p);
  }
  return ra;
}

test("khong goi signIn voi chuoi email/mat khau viet cung", () => {
  const goc = fileURLToPath(new URL("../src/", import.meta.url));
  const vi = [];
  for (const tep of tatCaTep(goc)) {
    const src = readFileSync(tep, "utf8");
    if (/signIn\(\s*["'`][^"'`]+@[^"'`]+["'`]\s*,\s*["'`]/.test(src)) vi.push(tep.slice(goc.length));
    if (/Password1\d\d!/.test(src)) vi.push(tep.slice(goc.length) + " (chuoi mat khau)");
  }
  assert.deepEqual(vi, [], "tim thay dang nhap gan cung");
});

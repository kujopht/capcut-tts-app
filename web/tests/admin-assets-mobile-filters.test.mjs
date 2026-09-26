/*
 * /admin/assets tren dien thoai: hang loc 5 nut khong con bi ep trong mot vien
 * thuoc (do that 2026-09-26 o 390px: moi nut ~65px, chu gay 4 dong, cao 93px).
 * O <= 640px la luoi 2 cot, "Tất cả" chiem hang dau, chu mot dong, vung cham 44px.
 * Chi trang nay doi — cac `.seg admin-loc` khac giu nguyen.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("chi hang loc cua /admin/assets dung luoi mobile", () => {
  assert.match(read("../src/app/admin/assets/page.tsx"), /className="seg admin-loc admin-loc-luoi" role="group" aria-label="Bộ lọc tác vụ"/);
  for (const f of ["../src/app/admin/stories/page.tsx", "../src/app/admin/authors/applications/page.tsx"]) {
    assert.ok(!read(f).includes("admin-loc-luoi"), `${f} không được đổi`);
  }
});

test("luoi chi ap o <= 640px: 2 cot, nut dau chiem ca hang, chu mot dong", () => {
  // Chuan hoa xuong dong: checkout tren Windows co the la CRLF.
  const css = read("../src/app/globals.css").replace(/\r\n/g, "\n");
  const at = css.indexOf("@media (max-width: 640px) {\n  .admin-loc-luoi {");
  assert.ok(at > 0, "thiếu khối mobile của .admin-loc-luoi");
  const khoi = css.slice(at, css.indexOf("\n}\n", at));
  assert.match(khoi, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(khoi, /\.admin-loc-luoi \.seg-item:first-child \{\s*grid-column: 1 \/ -1;/);
  assert.match(khoi, /white-space: nowrap;/);
  // Khong dat lai chieu cao nut: quy tac chung 44px cua khoi mobile van ap.
  assert.ok(!/\.admin-loc-luoi \.seg-item \{[^}]*height:/.test(khoi));
  // Nam TRUOC khu Media Studio (cac bai kiem Media Studio cat tu banner do toi het tep).
  assert.ok(at < css.indexOf("Media Studio ======"));
});

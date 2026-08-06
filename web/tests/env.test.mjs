// Bao ve: khong bao gio commit secret trong file mau cua web.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const example = readFileSync(new URL("../.env.example", import.meta.url), "utf8");

test(".env.example chi chua bien cong khai", () => {
  assert.match(example, /NEXT_PUBLIC_API_BASE/);
  for (const forbidden of ["APPWRITE_API_KEY", "R2_SECRET_ACCESS_KEY", "R2_ACCESS_KEY_ID"]) {
    assert.ok(!example.includes(forbidden),
      `${forbidden} khong duoc xuat hien o phia web`);
  }
});

test("khong co gia tri that nao bi dien san", () => {
  const filled = example
    .split("\n")
    .filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .filter((l) => {
      const [k, v] = l.split("=");
      return v && v.trim() && !k.includes("NEXT_PUBLIC_API_BASE");
    });
  assert.deepEqual(filled, [], "file mau khong duoc chua gia tri that");
});

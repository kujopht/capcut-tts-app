// Bao ve: khong bao gio commit secret trong file mau cua web.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const example = readFileSync(new URL("../.env.example", import.meta.url), "utf8");

/** Ten cac bien duoc KHAI BAO (bo qua dong chu thich). */
function declaredNames(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => !line.trim().startsWith("#") && line.includes("="))
    .map((line) => line.split("=")[0].trim());
}

test(".env.example chi khai bao bien cong khai", () => {
  assert.match(example, /NEXT_PUBLIC_API_BASE/);

  const declared = declaredNames(example);

  // Nhac ten trong chu thich canh bao thi duoc; KHAI BAO thi khong.
  for (const forbidden of [
    "APPWRITE_API_KEY",
    "R2_SECRET_ACCESS_KEY",
    "R2_ACCESS_KEY_ID",
  ]) {
    assert.ok(
      !declared.includes(forbidden),
      `${forbidden} khong duoc khai bao o phia web`,
    );
  }

  // Moi bien phia web deu phai co tien to NEXT_PUBLIC_ (tuc la co y cong khai).
  for (const name of declared) {
    assert.ok(
      name.startsWith("NEXT_PUBLIC_"),
      `${name} thieu tien to NEXT_PUBLIC_ nen khong nen nam o phia web`,
    );
  }
});

test("khong co gia tri that nao bi dien san", () => {
  const filled = example
    .split(/\r?\n/)
    .filter((line) => line.includes("=") && !line.trim().startsWith("#"))
    .filter((line) => {
      const [key, value] = line.split("=");
      return value && value.trim() && !key.includes("NEXT_PUBLIC_API_BASE");
    });
  assert.deepEqual(filled, [], "file mau khong duoc chua gia tri that");
});

test("file mau canh bao ro ve secret", () => {
  assert.match(example, /TUYET DOI khong dat/);
});

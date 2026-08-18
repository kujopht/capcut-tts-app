/*
 * Live Wallpaper — trang chu DA QUAY VE anh tinh (2026-08).
 *
 * V1 (video toan khung) va V2 (hybrid cinemagraph, video da on dinh + mask)
 * DEU bi tu choi o QA thu cong — xem lich su git. `LiveBackground.tsx` va
 * `liveBackgroundPreference.ts` la KIEN TRUC CHUNG, van con nguyen (xem
 * `live-background-v1.test.mjs`, `live-background-preference-stub.test.mjs`)
 * cho lan tich hop sau voi mot video thu cong chat luong cao hon — nhung
 * PageBackground.tsx (trang chu) KHONG con goi no.
 *
 * Bo test o day la RAO CHAN: dam bao khong ai vo tinh noi lai video vao trang
 * chu ma khong qua mot quyet dinh ro rang — trang chu khong duoc phat sinh
 * bat ky yeu cau video/mask nao.
 *
 * Quet MA NGUON, khong render — dung quy uoc cua repo (khong co jsdom).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const comp = () => read("../src/components/PageBackground.tsx");
const css = () => read("../src/app/globals.css");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

test("PageBackground KHONG import LiveBackground — trang chu la anh tinh", () => {
  const s = codeOnly(comp());
  assert.ok(!/LiveBackground/.test(s),
    "PageBackground vẫn còn nhắc tới LiveBackground — trang chủ sẽ lại phát video");
});

test("lop tam HIEN HANH (data-vao) la mot the TU DONG — khong con phan tu con nao", () => {
  const s = codeOnly(comp());
  assert.match(s,
    /<div className="page-bg-lop" data-bg=\{ten\} key=\{ten\} data-vao=""\s*data-huong=\{huongText\} \/>/,
    "lớp data-vao không còn là thẻ tự đóng — có thể đã thêm lại một lớp video/con nào đó",
  );
});

test("khong con class .home-live-lop trong CSS (dead code sau khi go video)", () => {
  assert.ok(!css().includes("home-live-lop"),
    "CSS vẫn còn .home-live-lop — lớp này chỉ có ý nghĩa khi PageBackground render LiveBackground");
});

test("home van dung dung anh tinh goc qua CSS ::before, khong doi", () => {
  const text = css();
  const dongHome = text.match(/\.page-bg-lop\[data-bg="home"\]\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(dongHome, /01-home-sunny-harbor\.webp/);
  assert.match(dongHome, /01-home-sunny-harbor-sm\.webp/);
});

test("bat bien cu cua PageBackground van dung: khong <img>/style inline", () => {
  const s = codeOnly(comp());
  assert.ok(!/<img/.test(s));
  assert.ok(!/style=\{\{/.test(s));
});

/*
 * `lib/routeTransitionInstance.ts` — ban lap ghep THAT (khong the kiem qua
 * phu thuoc gia) noi `taoRouteTransitionStore` (logic thuan, da kiem day du
 * o `route-transition-veil.test.mjs` qua dong ho gia) voi cac API trinh
 * duyet that: `Image`, `matchMedia`, `setTimeout`.
 *
 * Phat hien khi review PR #24 (2026-08-21): bai test cu cho ham nap-anh that
 * ("NAP TRUOC anh moi truoc khi chuyen canh", von nam trong
 * `route-crossfade.test.mjs` khi ham nay con nam inline trong
 * `PageBackground.tsx`) bi XOA khi ham duoc tach ra tep nay, khong co ban
 * thay the — moi test con lai chi kiem `taoRouteTransitionStore` voi mot ham
 * `napAnh` GIA duoc tiem vao, khong bao gio cham toi `napAnhThat` that. Tep
 * nay lap lai dung quy uoc cua repo (quet MA NGUON tinh, khong dung jsdom —
 * xem `live-background-v1.test.mjs`) nhung tro vao DUNG vi tri moi.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const src = () => read("../src/lib/routeTransitionInstance.ts");

test("napAnhThat dung Image that de nap truoc, khong doi mang", () => {
  const s = src();
  assert.match(s, /new Image\(\)/, "không nạp trước bằng Image() thật");
  assert.match(s, /img\.src = anhNen\(ten\)/,
    "phải dùng CHÍNH ham anhNen() mà CSS dùng để vẽ — lệch nhau thì nạp trước một tấm, vẽ tấm khác");
});

test("uu tien decode() cho anh da trong cache, luon co fallback onload/onerror", () => {
  const s = src();
  assert.match(s, /if \(img\.decode\)/, "thiếu nhánh decode() cho ảnh đã cache");
  assert.match(s, /img\.decode\(\)\.then\(xong, xong\)/,
    "decode() phải giải quyết CẢ HAI trường hợp thành công/lỗi — một ảnh lỗi không được treo chuyển cảnh mãi mãi");
  assert.match(s, /img\.onload = xong/);
  assert.match(s, /img\.onerror = xong/,
    "thiếu fallback onerror — trình duyệt không decode() được thì ảnh lỗi sẽ treo chuyển cảnh vĩnh viễn");
});

test("napAnhThat duoc noi THAT vao taoRouteTransitionStore qua napAnh, khong bi bo sot", () => {
  const s = src();
  assert.match(s, /napAnh:\s*napAnhThat,/,
    "napAnhThat định nghĩa ra nhưng không được nối vào store thật — chuyển cảnh sẽ chạy mà không nạp trước ảnh");
});

test("dangGiamChuyenDong doc THAT tu window.matchMedia, khong doc mot lan roi cache sai", () => {
  const s = src();
  // Phai la MOT HAM (goi lai moi lan can), khong phai mot gia tri boolean tinh
  // duoc doc mot lan luc module nap — nguoi dung co the doi che do giam
  // chuyen dong trong luc dang dung trang, khong reload lai.
  assert.match(s, /dangGiamChuyenDong:\s*\(\)\s*=>/,
    "phải là một hàm được gọi lại mỗi lần, không phải giá trị đọc một lần lúc module nạp");
  assert.match(s, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)\.matches/);
});

/**
 * Trang chu: nguoi da dang nhap KHONG nap lai nam nguon cong khai.
 *
 * Truoc day mot bo nap duy nhat phu thuoc `daDangNhap`; phien chi khoi phuc
 * xong sau lan ve dau nen bo nap chay HAI lan (profile null -> co profile) va
 * moi request cong khai di hai lan (do tren ban production: 17 thay vi 12).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const home = read("../src/app/page.tsx");

function than(ten) {
  const dau = home.indexOf(`const ${ten} = useCallback(`);
  assert.ok(dau >= 0, `thiếu ${ten}`);
  const moc = "\n  }, [";
  const cuoi = home.indexOf(moc, dau);
  const dauDeps = cuoi + moc.length;
  return { body: home.slice(dau, cuoi), deps: home.slice(dauDeps, home.indexOf("]", dauDeps)) };
}

test("nguon cong khai nap MOT lan: bo nap khong phu thuoc phien", () => {
  const { body, deps } = than("loadChung");
  assert.equal(deps, "", "loadChung phải có deps rỗng — đổi phiên không được nạp lại nguồn công khai");
  for (const goi of ["api.browseNovels(", "api.novelTags(", "api.listAnimationSeries(", "social.feed(", "api.getLeaderboard("]) {
    assert.ok(body.includes(goi), `loadChung thiếu ${goi}`);
  }
  for (const rieng of ["getContinueProgress", "getProgress", "getAchievements", "daDangNhap", "profile"]) {
    assert.ok(!body.includes(rieng), `loadChung không được chạm ${rieng}`);
  }
});

test("nguon rieng chi nap khi da biet nguoi dung, theo user_id", () => {
  const { body, deps } = than("loadRieng");
  assert.equal(deps, "nguoiDung");
  for (const goi of ["api.getContinueProgress(", "api.getProgress(", "api.getAchievements("]) {
    assert.ok(body.includes(goi), `loadRieng thiếu ${goi}`);
  }
  assert.match(home, /useAsyncData\(loadRieng, \{ enabled: daDangNhap \}\)/);
  assert.match(home, /useAsyncData\(loadChung\)/);
  assert.ok(!/\}, \[daDangNhap\]\);/.test(home), "không còn bộ nạp nào phụ thuộc daDangNhap");
});

test("dang xuat thi bo du lieu rieng cu ngay", () => {
  assert.match(home, /\(daDangNhap && rieng\) \|\| RIENG_RONG/);
});

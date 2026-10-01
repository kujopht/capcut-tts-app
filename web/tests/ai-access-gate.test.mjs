/**
 * Cổng HIỂN THỊ của Trợ lý AI (`GET /api/ai/access` → `{eligible}`), xem
 * `src/lib/ai/quyenTruyCap.ts`. Lối vào (nút nổi, menu tài khoản, trang truyện,
 * linh vật nổi) chỉ được vẽ khi máy chủ xác nhận — chưa biết = KHÔNG vẽ.
 *
 * Hai lớp: hành vi thuần (gọi thẳng `quyenTruyCap.ts` cho từng vai) + bất biến tĩnh
 * (mỗi lối vào đọc đúng bit đó; client không biết danh sách/ID/lý do).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const { nenHoiQuyen, docQuyen, quyenHienTai, hienLoiVao } = await import("../src/lib/ai/quyenTruyCap.ts");

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

/** Mô phỏng đúng đường đi của AiProvider: hỏi máy chủ (nếu nên hỏi) → đọc bit → quyết vẽ. */
function veLoiVao({ coBat, userId, phanHoi }) {
  if (!nenHoiQuyen(coBat, userId)) return { hoi: false, ve: hienLoiVao(coBat, userId, null) };
  const ketQua = { userId, eligible: docQuyen(phanHoi) };
  return { hoi: true, ve: hienLoiVao(coBat, userId, quyenHienTai(ketQua, userId)) };
}

test("vai: Owner / tester beta được máy chủ xác nhận → vẽ lối vào", () => {
  for (const userId of ["6a88165cc7a586625966", "tester_01"]) {
    assert.deepEqual(veLoiVao({ coBat: true, userId, phanHoi: { eligible: true } }), { hoi: true, ve: true });
  }
});

test("vai: người đã đăng nhập ngoài nhóm beta → máy chủ trả false → KHÔNG vẽ", () => {
  assert.deepEqual(veLoiVao({ coBat: true, userId: "user_stranger", phanHoi: { eligible: false } }),
    { hoi: true, ve: false });
});

test("vai: khách chưa đăng nhập → không hỏi máy chủ, không vẽ", () => {
  for (const userId of [null, undefined, ""]) {
    assert.deepEqual(veLoiVao({ coBat: true, userId, phanHoi: { eligible: true } }), { hoi: false, ve: false });
  }
});

test("cờ build tắt → 0 request, không vẽ, kể cả Owner", () => {
  assert.deepEqual(veLoiVao({ coBat: false, userId: "6a88165cc7a586625966", phanHoi: { eligible: true } }),
    { hoi: false, ve: false });
});

test("công tắc khẩn cấp: máy chủ trả eligible:false cho cả Owner → ẩn lối vào", () => {
  assert.equal(veLoiVao({ coBat: true, userId: "6a88165cc7a586625966", phanHoi: { eligible: false } }).ve, false);
});

test("chỉ đúng `{eligible: true}` mới mở — lỗi mạng/401/5xx/JSON lạ đều ĐÓNG", () => {
  assert.equal(docQuyen({ eligible: true }), true);
  for (const body of [null, undefined, {}, { eligible: "true" }, { eligible: 1 }, [true], "true", true,
    { enabled: true }, { eligible: false }]) {
    assert.equal(docQuyen(body), false, JSON.stringify(body));
  }
});

test("chưa biết (đang hỏi) = không vẽ; đổi tài khoản thì bit cũ không còn giá trị", () => {
  assert.equal(hienLoiVao(true, "u1", null), false);
  assert.equal(quyenHienTai({ userId: "u1", eligible: true }, "u2"), null);
  assert.equal(quyenHienTai({ userId: "u1", eligible: true }, "u1"), true);
  assert.equal(quyenHienTai(null, "u1"), null);
  assert.equal(quyenHienTai({ userId: "u1", eligible: true }, null), null);
});

test("mọi lối vào đọc đúng bit máy chủ", () => {
  const launcher = codeOnly(read("components/ai/AiLauncher.tsx"));
  assert.match(launcher, /if \(!eligible\) return null;/);
  const menu = codeOnly(read("components/NavAuth.tsx"));
  assert.match(menu, /\{AI_ASSISTANT_ENABLED && ai\?\.eligible \? \(\s*<Link href="\/assistant"/);
  const story = codeOnly(read("components/ai/AskAiAssistantStoryEntry.tsx"));
  assert.match(story, /if \(!enabled \|\| !eligible\) return null;/);
  const companion = codeOnly(read("components/ai/companion/AiCompanionGate.tsx"));
  assert.match(companion, /variant === "inline" \|\|\s*\(ai\.eligible &&/);
  const panel = codeOnly(read("components/ai/AiPanel.tsx"));
  assert.match(panel, /if \(access === false\) return null;/);
});

test("AiProvider: hỏi máy chủ MỘT lần mỗi người, chỉ khi nên hỏi; setState chỉ trong callback", () => {
  const p = codeOnly(read("components/ai/AiProvider.tsx"));
  const hieuUng = p.match(/useEffect\(\(\) => \{[\s\S]*?\n {2}\}, \[[^\]]*\]\);/g) ?? [];
  const goiMang = hieuUng.filter((h) => /aiApi\./.test(h));
  assert.equal(goiMang.length, 1, "chỉ một useEffect được gọi mạng lúc mount");
  const [h] = goiMang;
  assert.match(h, /if \(!nenHoiQuyen\(AI_ASSISTANT_ENABLED, uid\) \|\| !uid\) return;/);
  assert.match(h, /aiApi\.access\(\)\.then\(\(ok\) => \{\s*if \(alive\) setQuyen\(\{ userId: uid, eligible: ok \}\);/);
  assert.match(h, /\}, \[profile\?\.user_id\]\);$/);
  assert.ok(!/aiApi\.(availability|listConversations|getConversation)/.test(h));
  assert.match(p, /const eligible = hienLoiVao\(AI_ASSISTANT_ENABLED, profile\?\.user_id, access\);/);
});

test("client: `access()` chỉ đọc bit qua docQuyen, lỗi = false", () => {
  const c = codeOnly(read("lib/ai/client.ts"));
  const than = c.split("async access(): Promise<boolean> {")[1].split("\n  },")[0];
  assert.match(than, /\/api\/ai\/access/);
  assert.match(than, /if \(!res\.ok\) return false;/);
  assert.match(than, /return docQuyen\(await res\.json\(\)\);/);
  assert.match(than, /catch \{\s*return false;/);
});

test("client KHÔNG biết danh sách tester, khán giả hay luật phân quyền", () => {
  const tep = [];
  const duyet = (dir) => {
    for (const ten of readdirSync(dir)) {
      const p = `${dir}${dir.endsWith("/") ? "" : "/"}${ten}`;
      if (statSync(p).isDirectory()) duyet(`${p}/`);
      else if (/\.(tsx?|mjs|js)$/.test(ten)) tep.push(p);
    }
  };
  duyet(SRC);
  const cam = /FAS_AI_BETA_USERS|FAS_AI_CANARY_USERS|FAS_AI_AUDIENCE|FAS_OWNER_USER_IDS|beta_users|canary_users|audience_users|not_in_audience/;
  const viPham = tep.filter((p) => cam.test(codeOnly(readFileSync(p, "utf8"))))
    .map((p) => p.slice(SRC.length).replace(/\\/g, "/"));
  assert.deepEqual(viPham, []);
});

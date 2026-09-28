/**
 * Sentry web (`lib/observability/*`, `components/SentryGate.tsx`) — bất biến:
 *   * TẮT mặc định (không DSN = không trình nghe, không import, không gửi);
 *   * môi trường KHÔNG tự suy ra production;
 *   * SDK chỉ nạp qua MỘT điểm `import()`, không import tĩnh `@sentry/*` ở đâu khác;
 *   * không tích hợp tự thu (GlobalHandlers/Breadcrumbs/BrowserSession), không tracing, không PII;
 *   * làm sạch THẬT (chạy `scrub.ts`): query URL, header, token/JWT/khoá Appwrite/UserSig/email.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { lamSachBreadcrumb, lamSachSuKien, locUrl } from "../src/lib/observability/scrub.ts";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

function moiTep(dir) {
  const ra = [];
  for (const ten of readdirSync(dir)) {
    const p = join(dir, ten);
    if (statSync(p).isDirectory()) ra.push(...moiTep(p));
    else if (/\.(tsx?|mjs)$/.test(ten)) ra.push(p);
  }
  return ra;
}

// Gia tri GIA, ghep luc chay — khong phai bi mat that.
const KHOA_APPWRITE = "standard_" + "ab12".repeat(20);
const JWT = ["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxIn0", "c2lnMTIzNDU2"].join(".");
const USERSIG = "eJw" + "1jcEOgjAQRH9lwjXGUqmoFYz3Rz0g";
const URL_KY = "https://r2.example.com/a.mp3?X-Amz-Credential=AKIA" + "X".repeat(16) + "&X-Amz-Signature=" + "f".repeat(64);
const EMAIL = "nguoi.dung@vidu.vn";

test("tat mac dinh va moi truong khong tu thanh production", () => {
  const cfg = codeOnly(read("lib/observability/config.ts"));
  assert.match(cfg, /export const SENTRY_DSN = process\.env\.NEXT_PUBLIC_SENTRY_DSN \|\| "";/);
  assert.match(cfg, /export const SENTRY_ENV = process\.env\.NEXT_PUBLIC_SENTRY_ENV \|\| "development";/);
  assert.ok(!/"production"/.test(cfg), "config không được mặc định production");
  const cong = codeOnly(read("components/SentryGate.tsx"));
  assert.match(cong, /useEffect\(\(\) => \{\s*if \(!SENTRY_DSN\) return;/);
  assert.match(cong, /if \(!SENTRY_DSN \|\| soDaGui >= TRAN_SU_KIEN_MOI_TRANG\) return;/);
  assert.match(codeOnly(read("lib/observability/config.ts")), /TRAN_SU_KIEN_MOI_TRANG = 10;/);
  assert.match(codeOnly(read("app/layout.tsx")), /<SentryGate \/>/);
});

test("frontend CHI biet DSN va moi truong — khong bao gio mot token Sentry", () => {
  // Token read-only cua AI Support (FAS_SUPPORT_SENTRY_TOKEN) va moi token Sentry khac CHI o backend.
  // Mot NEXT_PUBLIC_* bi nhung vao bundle cong khai, nen moi ten bien Sentry o web phai nam trong
  // danh sach cho phep, va khong duoc nhac toi bat ky bien token nao.
  const choPhep = new Set(["NEXT_PUBLIC_SENTRY_DSN", "NEXT_PUBLIC_SENTRY_ENV"]);
  const tep = [...moiTep(SRC), fileURLToPath(new URL("../next.config.mjs", import.meta.url))];
  for (const p of tep) {
    const rel = p.replace(/\\/g, "/").split("/web/")[1];
    const c = readFileSync(p, "utf8");
    for (const m of c.matchAll(/\b[A-Z][A-Z0-9_]*SENTRY[A-Z0-9_]*\b/g)) {
      if (m[0].startsWith("NEXT_PUBLIC_")) assert.ok(choPhep.has(m[0]), `${rel}: biến ${m[0]} ngoài danh sách cho phép`);
    }
    assert.ok(!/SENTRY[A-Z0-9_]*TOKEN|SUPPORT_SENTRY|SENTRY_AUTH/.test(c), `${rel} nhắc tới một biến token Sentry`);
  }
});

test("SDK chi nap qua MOT diem import(), khong import tinh @sentry o dau khac", () => {
  const diem = [];
  for (const p of moiTep(SRC)) {
    const rel = p.replace(/\\/g, "/").split("/src/")[1];
    const c = codeOnly(readFileSync(p, "utf8"));
    if (!rel.startsWith("lib/observability/")) {
      assert.ok(!/from\s+["']@sentry\//.test(c), `${rel} import tĩnh @sentry`);
      assert.ok(!/^import[^;]*from\s+["'][^"']*observability\/sentry-lazy["']/m.test(c), `${rel} import tĩnh sentry-lazy`);
    }
    for (const m of c.matchAll(/(?<!typeof )import\(\s*["']([^"']*sentry-lazy)["']/g)) diem.push(`${rel}:${m[1]}`);
  }
  assert.deepEqual(diem, ["components/SentryGate.tsx:@/lib/observability/sentry-lazy"]);
});

test("it on va khong PII: bo tich hop tu thu, khong tracing, gui qua bo loc", () => {
  const l = codeOnly(read("lib/observability/sentry-lazy.ts"));
  assert.match(l, /TICH_HOP_BO = \["GlobalHandlers", "Breadcrumbs", "BrowserSession", "BrowserApiErrors"\]/);
  assert.match(l, /tracesSampleRate: 0,/);
  // Sentry JS 11: `dataCollection` (mac dinh THOANG) — tung muc phai o muc chat nhat.
  for (const muc of ["userInfo: false", "cookies: false", "httpBodies: []", "urlQueryParams: false",
    "stackFrameVariables: false", "databaseQueryData: false", "response: false"]) {
    assert.ok(l.includes(muc), `dataCollection thiếu ${muc}`);
  }
  assert.match(l, /request: \{ allow: \["user-agent", "accept-language", "content-type"\] \}/);
  assert.match(l, /beforeSend: \(ev\) => lamSachSuKien\(ev\),/);
  assert.match(l, /beforeBreadcrumb: \(b\) => lamSachBreadcrumb\(b\),/);
  assert.ok(!/replay|Replay|browserTracing/i.test(l));
});

test("PR nay KHONG sua duong deploy production; khong token Sentry nao trong workflow", () => {
  // Bat Sentry production la viec cua chu du an (docs/observability/SENTRY.md): them
  // NEXT_PUBLIC_SENTRY_DSN (tu bien repo) + NEXT_PUBLIC_SENTRY_ENV=production vao buoc build web.
  const wf = readFileSync(new URL("../../.github/workflows/production-deploy.yml", import.meta.url), "utf8");
  assert.ok(!/SENTRY_AUTH_TOKEN|secrets\.SENTRY/.test(wf), "không token Sentry nào trong deploy web");
});

test("lam sach THAT: su kien trinh duyet mang du loai bi mat", () => {
  const ev = {
    message: `loi ${KHOA_APPWRITE} ${EMAIL}`,
    request: {
      url: "https://fanfic.world/auth/callback?code=MA_OAUTH_BI_MAT&state=x#frag",
      headers: { "User-Agent": "Mozilla/5.0", Referer: URL_KY, Cookie: "a=b" },
      cookies: { a: "b" },
    },
    user: { id: "usr_1", email: EMAIL, ip_address: "10.0.0.1" },
    exception: { values: [{ type: "Error", value: `usersig=${USERSIG} Bearer ${JWT} ${URL_KY}`,
      stacktrace: { frames: [{ filename: "https://fanfic.world/_next/static/chunks/a.js?v=tok123", vars: { api_key: "x" } }] } }] },
    breadcrumbs: [{ category: "fetch", data: { url: URL_KY, headers: { authorization: `Bearer ${JWT}` } }, message: `GET ${URL_KY}` }],
    extra: { token: "phien-bi-mat", ghi_chu: `api_key=${KHOA_APPWRITE}` },
    tags: { email: EMAIL },
  };
  const ra = lamSachSuKien(ev);
  const than = JSON.stringify(ra);
  for (const cam of [KHOA_APPWRITE, JWT, USERSIG, "X-Amz-Signature", "X-Amz-Credential", EMAIL, "MA_OAUTH_BI_MAT",
    "phien-bi-mat", "tok123", "10.0.0.1"]) {
    assert.ok(!than.includes(cam), `còn lộ ${cam}: ${than}`);
  }
  assert.equal(ra.request.url, "https://fanfic.world/auth/callback");
  assert.deepEqual(Object.keys(ra.request.headers), ["User-Agent"]);
  assert.deepEqual(ra.user, {});
  assert.equal(ra.exception.values[0].stacktrace.frames[0].filename, "https://fanfic.world/_next/static/chunks/a.js");
  assert.equal(ra.exception.values[0].stacktrace.frames[0].vars, undefined);
});

test("lam sach hong thi bo su kien, khong gui ban tho", () => {
  const xau = { get request() { throw new Error("hong"); } };
  assert.equal(lamSachSuKien(xau), null);
  assert.equal(lamSachBreadcrumb(null), null);
  assert.equal(locUrl("https://u:p@a.example/x?y=1#z"), "https://a.example/x");
});

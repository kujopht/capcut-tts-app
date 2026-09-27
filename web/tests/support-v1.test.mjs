/**
 * Fanfic AI Support V1 (web) — các bất biến KHÔNG được hỏng lặng lẽ.
 *
 * 1. TẮT CỜ = KHÔNG ĐỔI GÌ: không lối vào, `/support` 404, không trình nghe
 *    lỗi, không request, không CSS Support trên trang thường.
 * 2. KHÔNG THĂM DÒ: không `setInterval` nào; bộ thu lỗi chỉ chạy theo sự kiện,
 *    có giới hạn cứng, lọc trùng.
 * 3. KHÔNG RÒ RỈ: làm sạch phía client (chạy THẬT `sanitize.ts` — Node ≥ 23.6
 *    tự bỏ kiểu TS), ngữ cảnh chỉ có trường liệt kê sẵn.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { duongDanAnToan, maLoi, sachChuoi } from "../src/lib/support/sanitize.ts";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

function moiTep(dir) {
  const ra = [];
  for (const ten of readdirSync(dir)) {
    const p = join(dir, ten);
    if (statSync(p).isDirectory()) ra.push(...moiTep(p));
    else if (/\.(tsx?|css)$/.test(ten)) ra.push(p);
  }
  return ra;
}
const tepHoTro = () => [...moiTep(join(SRC, "components", "support")), ...moiTep(join(SRC, "lib", "support")), ...moiTep(join(SRC, "app", "support"))];

test("co TAT mac dinh, doc tu MOT cho", () => {
  assert.match(read("lib/features.ts"), /export const SUPPORT_ENABLED = process\.env\.NEXT_PUBLIC_SUPPORT_ENABLED === "1";/);
});

test("tat co: layout khong gan bo thu loi / ranh gioi loi; loi vao deu co dieu kien; /support 404", () => {
  const layout = codeOnly(read("app/layout.tsx"));
  assert.match(layout, /\{SUPPORT_ENABLED \? <SupportBoundaryGate>\{children\}<\/SupportBoundaryGate> : children\}/);
  assert.match(layout, /\{SUPPORT_ENABLED \? <SupportCollectorGate \/> : null\}/);
  // Cong: hai cho nap (goi y + bo thu loi) deu dung lai ngay khi tat co.
  const cong = codeOnly(read("components/SupportGate.tsx"));
  assert.equal((cong.match(/if \(!SUPPORT_ENABLED\) return;/g) ?? []).length, 2);
  assert.match(layout, /\{SUPPORT_ENABLED \? \(\s*<Link href="\/support"/);
  assert.match(codeOnly(read("components/NavAuth.tsx")), /\{SUPPORT_ENABLED \? \(\s*<Link href="\/support"/);
  assert.match(codeOnly(read("app/support/page.tsx")), /if \(!SUPPORT_ENABLED\) notFound\(\);/);
  assert.match(codeOnly(read("components/support/SupportHint.tsx")), /if \(!SUPPORT_ENABLED\) return null;/);
  const bo = codeOnly(read("lib/support/collector.ts"));
  assert.match(bo, /if \(!SUPPORT_ENABLED \|\| typeof window === "undefined"\) return;/, "ghiLoi phai khong lam gi khi tat");
  assert.match(bo, /if \(!SUPPORT_ENABLED \|\| daCai \|\| typeof window === "undefined"\) return;/, "khong gan trinh nghe khi tat");
});

test("tat co = 0 byte tren trang thuong: ngoai thu muc Support, KHONG import tinh ma Support", () => {
  // Ba dieu DO THAT tren ban build (so voi main @ 4318e38, cung env):
  //  1. import tinh (ke ca trong nhanh `SUPPORT_ENABLED ? … : null`) keo ma tro vao
  //     MOI trang — trinh rut gon khong gap hang so qua ranh gioi module;
  //  2. `dynamic()` trong SERVER component (layout) van thanh client entry -> tai o
  //     MOI trang (~3.6 KB o `/` khi tat);
  //  3. `next/dynamic` tu no keo runtime ~6 KB tho vao MOI trang.
  // Nen: ngoai thu muc Support chi co MOT diem `import()` — o `components/SupportGate.tsx`
  // (client component) — va moc `window.__fanficSupport`.
  const ngoai = moiTep(SRC).filter((p) => !/[\\/](support)[\\/]/.test(p) && /\.tsx?$/.test(p));
  const diemNap = [];
  for (const p of ngoai) {
    const c = codeOnly(readFileSync(p, "utf8"));
    assert.ok(!/^import[^;]*from\s+["'][^"']*\/support\/[^"']*["']/m.test(c), `${p} import tinh ma Support`);
    // `typeof import("…")` chi la KIEU (bi xoa khi bien dich) — khong phai diem nap.
    for (const m of c.matchAll(/(?<!typeof )import\(\s*["']([^"']*\/support\/[^"']*)["']/g)) diemNap.push(`${p.replace(/\\/g, "/").split("/src/")[1]}:${m[1]}`);
  }
  assert.deepEqual(diemNap, ["components/SupportGate.tsx:./support/lazy"], "chi MOT diem nap luoi Support");
  const cong = readFileSync(join(SRC, "components", "SupportGate.tsx"), "utf8");
  assert.match(cong, /^"use client";/, "diem nap phai la client component");
  for (const f of ["app/layout.tsx", "components/SupportGate.tsx", "components/ui.tsx", "components/ChapterPlayer.tsx"]) {
    assert.ok(!/next\/dynamic/.test(codeOnly(read(f))), `${f} dung next/dynamic (runtime ~6 KB vao moi trang)`);
  }
  assert.match(codeOnly(read("app/layout.tsx")), /import \{ SupportBoundaryGate, SupportCollectorGate \} from "@\/components\/SupportGate";/);
  for (const f of ["components/ui.tsx", "components/ChapterPlayer.tsx"]) {
    assert.match(codeOnly(read(f)), /import \{ SupportHintGate \} from "[^"]*SupportGate";/, f);
  }
  // API Support khong nam trong `lib/api.ts` (module dung chung cua MOI trang).
  assert.ok(!/api\/support\//.test(codeOnly(read("lib/api.ts"))), "lib/api.ts chua duong dan /api/support/");
  assert.match(read("lib/support/api.ts"), /export const supportApi = \{/);
  // Loi render/audio di qua moc toan cuc, khong import bo thu loi.
  assert.match(codeOnly(read("components/AudioEngine.tsx")), /window\.__fanficSupport\?\.ghiLoi\(e\)/);
  assert.match(codeOnly(cong), /window\.__fanficSupport\?\.ghiLoi\(\{/);
  assert.match(codeOnly(read("lib/support/collector.ts")), /window\.__fanficSupport = \{ ghiLoi \};/);
});

test("CSS Support chi nap o trang /support (khong qua ui.tsx cua moi trang)", () => {
  const nap = tepHoTro().filter((p) => /import "\.\/support\.css";/.test(readFileSync(p, "utf8")));
  assert.deepEqual(nap.map((p) => p.replace(/\\/g, "/").split("/src/")[1]), ["components/support/SupportPanel.tsx"]);
  assert.ok(!/support\.css/.test(read("app/layout.tsx")) && !/support\.css/.test(read("components/ui.tsx")));
});

test("khong tham do: khong setInterval; bo thu loi co gioi han cung va loc trung", () => {
  for (const p of [...tepHoTro(), join(SRC, "components", "SupportGate.tsx")]) {
    assert.ok(!/setInterval\s*\(/.test(codeOnly(readFileSync(p, "utf8"))), `${p} dung setInterval`);
  }
  const bo = codeOnly(read("lib/support/collector.ts"));
  assert.match(bo, /GIOI_HAN = \{ hangDoi: 20, moiLo: 10, soLo: 3, byte: 8000, henMs: 4000 \}/);
  assert.match(bo, /if \(daGui\.has\(chuKy\) \|\| hangDoi\.has\(chuKy\) \|\| hangDoi\.size >= GIOI_HAN\.hangDoi \|\| soLoDaGui >= GIOI_HAN\.soLo\) return;/);
  // Gui bang fetch THANG — loi khi bao loi khong tu ghi lai thanh loi moi.
  assert.match(bo, /await fetch\(`\$\{API_BASE\}\/api\/support\/client-errors`/);
  assert.ok(!/\brequest\s*</.test(bo));
  // Chi loi CUA TRANG; bo nhieu ResizeObserver.
  assert.match(bo, /if \(nguon && !nguon\.startsWith\(location\.origin\)\) return;/);
});

test("bo nghe loi API: chi mang hong / 5xx; bo qua chinh /api/support/*", () => {
  const api = codeOnly(read("lib/api.ts"));
  assert.match(api, /khiApiHong\?\.\(path, 0\);/);
  assert.match(api, /if \(response\.status >= 500\) khiApiHong\?\.\(path, response\.status, code\);/);
  assert.match(codeOnly(read("components/support/lazy.ts")), /if \(path\.startsWith\("\/api\/support\/"\)\) return;/);
});

test("lam sach phia client (chay that): token, URL ky, JWT, email, query", () => {
  const s = sachChuoi(
    "fetch https://r2.example/a.mp3?X-Amz-Signature=abc&X-Amz-Credential=AKIA1234 failed Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig12345678 " +
      "token=s3cr3tValue me@example.com usersig: eJwtjEFrw",
    500,
  );
  for (const lo of ["X-Amz-Signature", "abc&", "eyJhbGci", "s3cr3tValue", "me@example.com", "eJwtjEFrw"]) {
    assert.ok(!s.includes(lo), `con lo ${lo}: ${s}`);
  }
  assert.ok(s.includes("https://r2.example/a.mp3"));
  assert.equal(duongDanAnToan("/messages?c=fw_usr_abc#x"), "/messages");
  assert.equal(duongDanAnToan("https://evil.example/x"), "/");
  assert.equal(maLoi("Audio_Media"), "audio_media");
  assert.equal(maLoi("<script>"), "");
});

test("ngu canh chi co truong liet ke — khong token/cookie/email/header", () => {
  const ctx = codeOnly(read("lib/support/context.ts"));
  const kieu = ctx.slice(ctx.indexOf("export type SupportContext"), ctx.indexOf("};", ctx.indexOf("export type SupportContext")));
  const truong = [...kieu.matchAll(/^\s+([a-z_]+)\??:/gm)].map((m) => m[1]);
  assert.deepEqual(truong, ["route", "build", "novel_id", "chapter_id", "reader_mode", "browser", "device", "viewport", "last_error_code"]);
  for (const p of tepHoTro()) {
    const c = codeOnly(readFileSync(p, "utf8"));
    assert.ok(!/document\.cookie/.test(c), `${p} doc cookie`);
    assert.ok(!/dangerouslySetInnerHTML/.test(c), `${p} chen HTML tho`);
  }
});

test("hoi thoai: status goi MOT lan, IME tieng Viet khong gui nua chu, khong tu bat popup", () => {
  const p = codeOnly(read("components/support/SupportPanel.tsx"));
  assert.equal((p.match(/supportApi\.status\(\)/g) ?? []).length, 1);
  assert.match(p, /if \(e\.nativeEvent\.isComposing \|\| e\.keyCode === 229\) return;/);
  assert.match(p, /diagnostic_id: res\?\.diagnostic_id/, "bao cao gan dung ket qua chan doan cua may chu");
  assert.ok(!/window\.open|alert\(|confirm\(/.test(p));
});

test("diem vao dung cho: trang loi chung, trinh phat audio, loi render", () => {
  assert.match(codeOnly(read("components/ui.tsx")), /<SupportHintGate code="load_error" \/>/);
  assert.match(codeOnly(read("components/ChapterPlayer.tsx")), /<SupportHintGate code="audio_media" mode="listen" compact \/>/);
  const cong = codeOnly(read("components/SupportGate.tsx"));
  assert.match(cong, /<SupportHintGate code="render_error" \/>/);
  // Phan du phong loi render dung duoc NGAY ca khi chunk Support khong tai duoc.
  assert.match(cong, /<strong>Trang này gặp lỗi khi hiển thị<\/strong>/);
  assert.match(cong, /onClick=\{\(\) => this\.setState\(\{ loi: false, duong: "" \}\)\}/);
  const am = codeOnly(read("components/AudioEngine.tsx"));
  for (const ma of ["audio_url", "audio_media", "audio_expired"]) assert.ok(am.includes(`code: "${ma}"`), ma);
});

test("ma build web lay tu next.config (khong phai bi mat)", () => {
  const cfg = readFileSync(new URL("../next.config.mjs", import.meta.url), "utf8");
  assert.match(cfg, /NEXT_PUBLIC_BUILD_SHA: maBuild\(\),/);
  assert.match(read("lib/support/context.ts"), /export const BUILD_SHA = process\.env\.NEXT_PUBLIC_BUILD_SHA \|\| "unknown";/);
});

/*
 * /admin/ai — AI Control Plane (docs/ai/AI_ADMIN_CONTROL_PLANE.md).
 *
 * Cung phong cach voi cac bai kiem admin khac: doc THANG source va khang dinh
 * cac dac diem quan trong bang regex. Server moi la noi quyet quyen va giu bi
 * mat (xem server/tests/test_ai_admin_api.py); o day khoa phia giao dien:
 * khong o nhap khoa, ghi chi cho OWNER, tat AI phai xac nhan, 390px khong tran.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const page = () => read("../src/app/admin/ai/page.tsx");
const client = () => read("../src/lib/admin/aiControl.ts");
const shell = () => read("../src/components/AdminShell.tsx");
const css = () => read("../src/app/globals.css");
const COMP_DIR = new URL("../src/components/admin/ai/", import.meta.url);
const components = () =>
  readdirSync(fileURLToPath(COMP_DIR))
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => [f, readFileSync(fileURLToPath(new URL(f, COMP_DIR)), "utf8")]);
const allUi = () => [["page.tsx", page()], ["aiControl.ts", client()], ...components()];

// ------------------------------------------------------------------ bi mat

test("khong co o nao nhan API key: khong input password, khong truong api_key/apiKey", () => {
  for (const [f, src] of allUi()) {
    const code = codeOnly(src);
    assert.ok(!/type=["']password["']/.test(code), `${f}: có ô password`);
    assert.ok(!/\b(api_key|apiKey|secret_value|secretValue|raw_key)\b/.test(code), `${f}: có trường khoá thô`);
  }
});

test("client chi gui secret_ref (ten), khong co kieu nao mang gia tri khoa", () => {
  const src = codeOnly(client());
  assert.match(src, /secret_ref\?: string/);
  assert.match(src, /fingerprint: string/);
  assert.ok(!/\bkey\??:\s*string/.test(src), "có trường `key: string`");
});

test("khong co chuoi giong khoa that trong ma giao dien (AIza…, sk-…, gsk_…)", () => {
  for (const [f, src] of allUi()) {
    assert.ok(!/AIza[0-9A-Za-z_-]{20,}|\bsk-[A-Za-z0-9]{16,}|\bgsk_[A-Za-z0-9]{16,}/.test(src), `${f}: chuỗi giống khoá`);
  }
});

test("khong dangerouslySetInnerHTML trong cac component AI admin", () => {
  for (const [f, src] of allUi()) assert.ok(!/dangerouslySetInnerHTML/.test(src), f);
});

// ------------------------------------------------------------------ API + quyen

test("client goi dung cac route /api/admin/ai/* kem Bearer token", () => {
  const src = client();
  for (const r of ["/api/admin/ai/overview", "/api/admin/ai/config", "/api/admin/ai/audit",
    "/api/admin/ai/global", "/api/admin/ai/provider-types/", "/api/admin/ai/slots",
    "/reset-cooldown", "/api/admin/ai/profiles/"]) {
    assert.ok(src.includes(r), `thiếu ${r}`);
  }
  assert.match(src, /Authorization", `Bearer \$\{token\}`/);
  assert.match(src, /encodeURIComponent\(slotId\)/);
});

test("loi 422 giu danh sach loi theo truong de hien canh o nhap", () => {
  const src = client();
  assert.match(src, /class AiAdminApiError extends ApiError/);
  assert.match(src, /body\.detail\.errors/);
  assert.match(page(), /e\.status === 422/);
  assert.match(page(), /e\.status === 409/);
});

test("ghi chi cho OWNER: giao dien lay vai tro tu phien, ADMIN thay che do chi doc", () => {
  const src = codeOnly(page());
  assert.match(src, /laOwner = profile\?\.admin_role === "owner"/);
  assert.match(src, /Chế độ chỉ đọc/);
  // AiSlotForm chi duoc AiSlotList ve khi `laOwner` (khoa ngay ben duoi).
  for (const [f, s] of components()) {
    if (/onClick|onSubmit/.test(s) && !/AiAuditTable|AiQuotaBar|AiOverviewCards|AiSlotForm/.test(f)) {
      assert.ok(/laOwner/.test(s), `${f}: có thao tác ghi nhưng không xét laOwner`);
    }
  }
  const list = codeOnly(read("../src/components/admin/ai/AiSlotList.tsx"));
  assert.ok(/laOwner && !dangTao \?/.test(list), "nút Thêm slot không khoá theo laOwner");
  assert.ok(/\{laOwner \? \(\s*xacNhanXoa/.test(list), "nút Sửa/Xoá slot không khoá theo laOwner");
});

test("co trang thai trung thuc khi co tat (503 ai_admin_not_enabled) va khi 403", () => {
  const src = page();
  assert.match(src, /ai_admin_not_enabled/);
  assert.match(src, /FAS_AI_ADMIN_V1/);
  assert.match(src, /status === 403/);
});

test("dieu huong: muc /admin/ai cho vai admin tro len, khop theo DOAN duong dan", () => {
  const src = shell();
  assert.match(src, /href: "\/admin\/ai", nhan: "AI Control Plane", icon: IconBulb, vaiToiThieu: "admin"/);
  assert.match(src, /pathname\.startsWith\(`\$\{href\}\/`\)/);
  assert.ok(!/pathname\.startsWith\(m\.href\)/.test(src), "còn khớp tiền tố chuỗi (/admin/ai sáng ở /admin/ai-credits)");
});

// ------------------------------------------------------------------ xac nhan

test("tat toan bo AI phai qua buoc xac nhan trong trang (khong window.confirm)", () => {
  const src = read("../src/components/admin/ai/AiKillSwitch.tsx");
  assert.match(src, /role="alertdialog"/);
  assert.match(src, /Xác nhận tắt AI/);
  for (const [f, s] of allUi()) assert.ok(!/window\.confirm|\bconfirm\(/.test(codeOnly(s)), `${f}: dùng confirm()`);
});

test("luu ho so dinh tuyen, luu han muc, xoa slot deu co buoc xac nhan", () => {
  assert.match(read("../src/components/admin/ai/AiRoutingProfiles.tsx"), /Xác nhận lưu/);
  assert.match(read("../src/components/admin/ai/AiGlobalCaps.tsx"), /Xác nhận lưu/);
  assert.match(read("../src/components/admin/ai/AiSlotList.tsx"), /Xác nhận xoá/);
});

test("han muc gui expected_version (409 thay vi ghi de nguoi khac)", () => {
  assert.match(read("../src/components/admin/ai/AiGlobalCaps.tsx"), /expected_version: controls\.version/);
  assert.match(page(), /expected_version: c\.version/);
});

test("ho so dinh tuyen: sap xep bang nut Len/Xuong co aria-label, gioi han 12 buoc", () => {
  const src = read("../src/components/admin/ai/AiRoutingProfiles.tsx");
  assert.match(src, /const MAX_BUOC = 12/);
  assert.match(src, /aria-label=\{`Đưa \$\{st\} lên`\}/);
  assert.match(src, /aria-label=\{`Đưa \$\{st\} xuống`\}/);
});

test("slot hien secret_ref + ten bien moi truong + van tay, khong gi hon", () => {
  const src = read("../src/components/admin/ai/AiSlotList.tsx");
  assert.match(src, /h\.secret\.ref/);
  assert.match(src, /h\.secret\.env_name/);
  assert.match(src, /h\.secret\.fingerprint/);
  assert.match(src, /COOLDOWN · 429×/);
});

// ------------------------------------------------------------------ mobile

test("390px: bang audit thanh the, luoi slot/ho so co min(100%, …)", () => {
  const s = css();
  assert.match(s, /\.ai-admin-audit td::before \{\s*content: attr\(data-nhan\)/);
  assert.match(s, /minmax\(min\(100%, 340px\), 1fr\)/);
  assert.match(s, /minmax\(min\(100%, 360px\), 1fr\)/);
  assert.match(s, /\.ai-quota-bar-fill \{ transition: none; \}/);
  assert.match(read("../src/components/admin/ai/AiAuditTable.tsx"), /data-nhan="Cũ → Mới"/);
});

test("CSS moi khong dung token vang (ngan sach vang cua he nhan dang)", () => {
  const s = css();
  const khoi = s.slice(s.indexOf("/* -- /admin/ai — AI Control Plane"));
  assert.ok(khoi.length > 100, "không tìm thấy khối CSS /admin/ai");
  assert.ok(!/--vang|#d8b56a|#e4c982/.test(khoi), "khối CSS /admin/ai dùng vàng");
});

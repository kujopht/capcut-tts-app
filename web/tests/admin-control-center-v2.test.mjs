/**
 * Admin Control Center V2, Phase 2 — shell/dashboard/audit-log/AI-credits.
 *
 * Cung phong cach voi cac bai kiem khac: doc THANG source va khang dinh cac
 * dac diem quan trong bang regex, khong dung DOM gia lap.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

function read(rel) {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

const shell = () => read("../src/components/AdminShell.tsx");
const dashboard = () => read("../src/app/admin/page.tsx");
const auditLog = () => read("../src/app/admin/audit-log/page.tsx");
const aiCredits = () => read("../src/app/admin/ai-credits/page.tsx");
const api = () => read("../src/lib/api.ts");
const css = () => read("../src/app/globals.css");

// -- Dieu huong ---------------------------------------------------------

test("AdminShell: co du cac nhom dieu huong theo dung ke hoach", () => {
  const src = shell();
  // "Content"/"Animation"/"Moderation" la nhan NHOM (`nhom: "..."`), con lai
  // la nhan MUC LA (`nhan: "..."`) — hai truong khac nhau trong cung mang.
  for (const nhom of ["Content", "Animation", "Moderation"]) {
    assert.match(src, new RegExp(`nhom: "${nhom}"`), nhom);
  }
  for (const nhan of [
    "Dashboard", "Users", "Analytics", "AI / Credits", "System", "Audit Log",
  ]) {
    assert.match(src, new RegExp(`nhan: "${nhan.replace(/[/]/g, "\\/")}"`), nhan);
  }
});

test("AdminShell: nhom Animation co du ba muc con Series/Trusted Sources/Import Queue", () => {
  const src = shell();
  const at = src.indexOf('nhom: "Animation"');
  assert.ok(at > 0, "không tìm thấy nhóm Animation");
  const doan = src.slice(at, at + 500);
  assert.match(doan, /href: "\/admin\/animation\/series", nhan: "Series"/);
  assert.match(doan, /href: "\/admin\/animation\/sources"/);
  assert.match(doan, /href: "\/admin\/animation\/import-queue"/);
});

test("AdminShell: nut mobile gap\\/mo co aria-expanded + aria-controls, GAN voi id thanh dieu huong", () => {
  const src = shell();
  assert.match(src, /aria-expanded=\{moDieuHuongMobile\}/);
  assert.match(src, /aria-controls="admin-dieu-huong"/);
  assert.match(src, /id="admin-dieu-huong"/);
});

test("globals.css: .admin-nav AN mac dinh duoi 900px, CHI hien khi co class admin-nav-mo", () => {
  const c = css();
  // Neo vao chinh dong co y nghia (khong phai tieu de @media, vi co NHIEU
  // khoi @media (max-width: 900px) khong lien quan trong tep).
  const at = c.indexOf(".admin-nut-mobile { display: inline-flex; }");
  assert.ok(at > 0, "không tìm thấy .admin-nut-mobile { display: inline-flex; }");
  const doan = c.slice(at, at + 400);
  assert.match(doan, /\.admin-nav \{[\s\S]{0,80}display: none;/);
  assert.match(doan, /\.admin-nav\.admin-nav-mo \{ display: flex; \}/);
});

test("AdminShell: an\\/hien theo vai tro CHI la goi y hien thi, khong phai kiem quyen that", () => {
  const src = shell();
  assert.match(src, /function duVaiTro/);
  // Route /api/admin/* van la nguon su that — shell KHONG tu chan render
  // children dua vao vai tro, chi loc MUC trong sidebar.
  assert.match(src, /adminApi\.overview\(\)/);
});

// -- Dashboard ------------------------------------------------------------

test("Dashboard: co du sau nhom the (Users/Content/Product/Trusted Sources/Traffic/System)", () => {
  const src = dashboard();
  assert.match(src, /data\.users\.total/);
  assert.match(src, /data\.content\.novels_total/);
  assert.match(src, /data\.product\.translation_projects_total/);
  assert.match(src, /data\.trusted_sources\.configured/);
  assert.match(src, /data\.traffic\.configured/);
  assert.match(src, /data\.system\.appwrite_healthy/);
});

test("Dashboard: Trusted Sources/Traffic deu co nhanh ChuaCauHinh khi configured=false", () => {
  const src = dashboard();
  assert.match(src, /data\.trusted_sources\.configured \? \(/);
  assert.match(src, /data\.traffic\.configured \? \(/);
  const soLanChuaCauHinh = (src.match(/<ChuaCauHinh/g) ?? []).length;
  assert.equal(soLanChuaCauHinh, 2, "phải có đúng 2 khối ChưaCấuHình (Trusted Sources + Traffic)");
});

test("AdminShell: OSo hien '—' cho gia tri null, KHONG bao gio hien 0 sai su that", () => {
  const src = shell();
  const at = src.indexOf("export function OSo");
  const doan = src.slice(at, at + 700);
  assert.match(doan, /so === null \? "—"/);
  assert.doesNotMatch(doan, /so === null \? "0"/);
});

// -- Audit Log --------------------------------------------------------------

test("Audit Log: co bo loc hanh dong/loai doi tuong/user_id + phan trang", () => {
  const src = auditLog();
  assert.match(src, /locHanhDong/);
  assert.match(src, /locLoaiDoiTuong/);
  assert.match(src, /locNguoiDung/);
  assert.match(src, /Trang trước/);
  assert.match(src, /Trang sau/);
});

test("adminApi.events: truyen duoc target_type/action/target_user_id qua query string", () => {
  const src = api();
  // `events: (` (co dau mo ngoac) — khop DUNG dinh nghia ham trong `adminApi`,
  // khong khop truong `events: ModerationEvent[]` cua mot interface khac
  // dung tinh cau "  events:" (vi du `AdminAnimationSeriesDetail`, Phase 4).
  const at = src.indexOf("  events: (");
  assert.ok(at > 0, "không tìm thấy hàm adminApi.events");
  const doan = src.slice(at, at + 700);
  assert.match(doan, /target_user_id/);
  assert.match(doan, /target_type/);
  assert.match(doan, /"action"/);
});

// -- AI / Credits -------------------------------------------------------

test("AI/Credits: nut cong tac khan cap tu vo hieu hoa khi KHONG PHAI owner", () => {
  const src = aiCredits();
  assert.match(src, /laOwner = profile\?\.admin_role === "owner"/);
  assert.match(src, /disabled=\{!laOwner \|\| dangGui \|\| data\.kill_switch_engaged\}/);
  assert.match(src, /disabled=\{!laOwner \|\| dangGui \|\| !data\.kill_switch_engaged\}/);
});

test("adminApi: kill-switch va spending goi dung duong /api/admin/image-studio/*", () => {
  const src = api();
  assert.match(src, /imageStudioSpending:[\s\S]{0,80}\/api\/admin\/image-studio\/spending/);
  assert.match(src, /imageStudioKillSwitch:[\s\S]{0,150}\/api\/admin\/image-studio\/kill-switch/);
  assert.match(src, /imageStudioKillSwitch:[\s\S]{0,200}method:\s*"POST"/);
});

// -- Khong bia du lieu --------------------------------------------------

test("AdminSapXayDung: trang placeholder KHONG goi adminApi (chua co logic nghiep vu that)", () => {
  const src = read("../src/components/AdminSapXayDung.tsx");
  assert.doesNotMatch(src, /adminApi\./);
  assert.match(src, /Sắp xây dựng/);
});

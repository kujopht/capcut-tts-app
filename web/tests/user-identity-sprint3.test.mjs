/**
 * Sprint 3 — danh tinh nguoi dung NHAT QUAN: avatar + khung qua MOT component (`UserAvatar`),
 * cap tai khoan qua MOT component (`CapDoTaiKhoan`, "Lv. N"), khong lan voi HANG TAC GIA ("Hạng").
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");

function tep(thuMuc) {
  const ra = [];
  for (const ten of readdirSync(thuMuc)) {
    const p = join(thuMuc, ten);
    if (statSync(p).isDirectory()) ra.push(...tep(p));
    else if (p.endsWith(".tsx")) ra.push(p);
  }
  return ra;
}

test("khong con <Avatar> tran ngoai UserAvatar — moi noi hien mot nguoi deu mang khung dang deo", () => {
  const vi = tep(SRC)
    .filter((f) => !f.endsWith("UserAvatar.tsx") && !f.endsWith(`components${"\\"}Avatar.tsx`) && !f.endsWith("components/Avatar.tsx"))
    .filter((f) => /<Avatar\b/.test(readFileSync(f, "utf8")))
    .map((f) => f.slice(SRC.length));
  assert.deepEqual(vi, [], `còn <Avatar> trần (thiếu khung): ${vi.join(", ")}`);
});

test("bam Dang/Gui lien tiep trong mot nhip chi gui MOT request (co ref, khong chi state)", () => {
  // Do that (Sprint 3): 3 cu bam 'Dang' -> 3 POST; may chu khu trung con 1 bai nhung moi POST mang ca anh base64.
  for (const f of ["../src/components/PostComposer.tsx", "../src/components/CommentThread.tsx"]) {
    const s = read(f);
    assert.match(s, /const dangGuiRef = useRef\(false\);/, f);
    assert.match(s, /dangGuiRef\.current\) return;/, f);
    assert.match(s, /dangGuiRef\.current = true;\s*\n\s*setDangGui\(true\);/, f);
    assert.match(s, /finally \{\s*\n\s*dangGuiRef\.current = false;/, f);
  }
});

test("trang chu, tai khoan, ho so deu hien cap qua CapDoTaiKhoan", () => {
  for (const f of ["../src/app/page.tsx", "../src/components/GamificationPanel.tsx", "../src/app/u/[username]/page.tsx"]) {
    assert.match(read(f), /<CapDoTaiKhoan\b/, f);
  }
  assert.match(read("../src/app/page.tsx"), /<UserAvatar user=\{it\} className="avatar avatar-sm" \/>/, "bảng vàng tuần dùng UserAvatar");
});

test("khong tu viet 'Bậc {level}' / 'Lv. {…}' ngoai component (tranh lan voi hang tac gia)", () => {
  const vi = [];
  for (const f of tep(SRC)) {
    if (f.endsWith("CapDoTaiKhoan.tsx")) continue;
    const s = readFileSync(f, "utf8");
    if (/Bậc \{[a-zA-Z_.?]*level\}|Lv\. \{/.test(s)) vi.push(f.slice(SRC.length));
  }
  assert.deepEqual(vi, [], `hiển thị cấp tự viết: ${vi.join(", ")}`);
  const c = read("../src/components/CapDoTaiKhoan.tsx");
  assert.match(c, /Lv\. \{level\}/);
  assert.ok(!/xp \+|xp\+|\+= ?xp/.test(c), "component chỉ vẽ số của máy chủ, không tự cộng XP");
});

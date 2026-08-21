/*
 * Live Wallpaper — rollout V4, CA 8 chu de (2026-08).
 *
 * Lich su rieng cua home: Nova Reel V1 (video toan khung) va V2 (hybrid +
 * mask) DEU bi tu choi o QA thu cong; Gemini V1/V2 (nguoi dung tu tao) thay
 * the sau do — xem lich su git. Dot rollout nay THAY THE hoan toan Gemini V2
 * bang MOT BO 8 video nguoi dung tu lam thu cong (mot cho moi chu de nen,
 * khong con rieng home) — xem bao cao rollout cho kiem tra vong lap/chat
 * luong day du cua ca 8 tep.
 *
 * Bo test o day xac nhan RIENG phan NOI DAY: PageBackground.tsx goi
 * LiveBackground cho MOI chu de (khong con dieu kien `=== "home"`), doc
 * video qua `videoNen()` (mot nguon su that duy nhat, khong hard-code duong
 * dan trong component), va khong lam vo cac bat bien da co (xem
 * `page-background.test.mjs`).
 *
 * Quet MA NGUON, khong render — dung quy uoc cua repo (khong co jsdom).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const comp = () => read("../src/components/PageBackground.tsx");
const css = () => read("../src/app/globals.css");
const backgrounds = () => read("../src/lib/backgrounds.ts");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const THU_MUC_LIVE = new URL("../public/artwork/fantasy-backgrounds/live/", import.meta.url);
const CHU_DE = ["home", "explore", "reader", "studio", "write", "library", "account", "auth"];

test("PageBackground import LiveBackground va videoNen (khong tu ghep duong dan)", () => {
  const s = comp();
  assert.match(s, /import \{ LiveBackground \} from "@\/components\/LiveBackground";/);
  assert.match(s, /import \{ anhNen, videoNen \} from "@\/lib\/backgrounds";/);
});

test("LiveBackground duoc goi cho MOI chu de (khong con dieu kien rieng \"home\")", () => {
  const s = codeOnly(comp());
  assert.ok(!/ten === "home"|tenMoi === "home"/.test(s),
    "vẫn còn rẽ nhánh riêng cho home — rollout V4 phải áp dụng LiveBackground cho MỌI chủ đề như nhau");
  // Ca hai lop (duoi/tren) deu goi LiveBackground KHONG DIEU KIEN, video lay tu videoNen(...).
  assert.match(s, /<LiveBackground\s+key=\{ten\}\s+poster=\{anhNen\(ten\)\}\s+video=\{videoNen\(ten\)\}/);
  assert.match(s, /<LiveBackground\s+poster=\{anhNen\(tenMoi\)\}\s+video=\{videoNen\(tenMoi\)\}/);
});

test("videoNen la NGUON DUY NHAT — component KHONG hard-code duong dan .mp4 nao", () => {
  const s = codeOnly(comp());
  assert.ok(!/\.mp4/.test(s), "PageBackground.tsx tự ghép chuỗi đường dẫn .mp4 — phải đi qua videoNen() ở backgrounds.ts");
});

test("videoNen: du CA 8 chu de, moi chu de mot tep .mp4 THAT ton tai tren dia, khong trung duong dan", () => {
  const src = backgrounds();
  const khoiVideo = src.slice(src.indexOf("const VIDEO"), src.indexOf("const VIDEO") + src.slice(src.indexOf("const VIDEO")).indexOf("\n};"));
  const duongDan = new Set();
  for (const ten of CHU_DE) {
    const re = new RegExp(`${ten}: "([^"]+)"`);
    const m = khoiVideo.match(re);
    assert.ok(m, `videoNen thiếu ánh xạ cho chủ đề "${ten}"`);
    const tep = m[1];
    assert.ok(!duongDan.has(tep), `hai chủ đề dùng trùng file "${tep}" — mỗi chủ đề phải có video riêng`);
    duongDan.add(tep);
    const fileUrl = new URL(`${tep}.mp4`, THU_MUC_LIVE);
    assert.ok(existsSync(fileUrl), `không tồn tại: public/artwork/fantasy-backgrounds/live/${tep}.mp4`);
  }
  assert.equal(duongDan.size, 8, "phải có đúng 8 video, một cho mỗi chủ đề");
});

test("KHONG con nhac toi tai san cu bi thay (Nova Reel, Gemini V1/V2)", () => {
  const s = comp() + backgrounds();
  assert.ok(!/01-home-sunny-harbor-live/.test(s), "vẫn còn trỏ tới bản Nova Reel V1 bị từ chối");
  assert.ok(!/01-home-sunny-harbor-motion/.test(s), "vẫn còn trỏ tới bản Nova Reel V2 (hybrid) bị từ chối");
  assert.ok(!/home-live-gemini-v1\.mp4|home-live-gemini-v2\.mp4/.test(s),
    "vẫn còn trỏ tới bản Gemini V1/V2 đã bị thay bằng bộ 8 video rollout V4");
});

test("cac tep Gemini/Nova Reel cu KHONG con nam trong repo (da don sach)", () => {
  const thuMucGoc = new URL("../public/artwork/fantasy-backgrounds/", import.meta.url);
  for (const tep of ["home-live-gemini-v1.mp4", "home-live-gemini-v2.mp4", "01-home-sunny-harbor-live.mp4", "01-home-sunny-harbor-motion.mp4"]) {
    assert.ok(!existsSync(new URL(tep, thuMucGoc)), `tệp cũ vẫn còn trên đĩa: ${tep} — phải xoá (đã thay bằng bộ 8 video mới, lịch sử git giữ lại nếu cần)`);
  }
});

test("lop DUOI dung key={ten} — bat buoc de <video> THAT SU doi nguon khi doi chu de (loi phat hien qua QA that)", () => {
  /*
    Loi THAT phat hien qua dieu huong that trong trinh duyet (khong phai
    doan): truoc rollout V4 CHI home co video, nen doi chu de LUON keo theo
    mount/unmount `<video>` (mot ben co, mot ben khong) — khong bao gio can
    React "cap nhat lai" mot `<video>` dang ton tai. Tu khi CA 8 chu de deu
    co video, doi tu chu de CO video nay sang chu de CO video KHAC ma khong
    co `key` khien React chi cap nhat thuoc tinh `src` tren `<source>` co
    san — trinh duyet KHONG tu doc lai (can `.load()`), nen video CU van
    tiep tuc phat DU DOM da hien dung poster/data-bg moi. `key={ten}` ep
    React mount lai toan bo moi lan chu de LOP DUOI doi.
  */
  const s = codeOnly(comp());
  assert.match(s, /<LiveBackground\s+key=\{ten\}/,
    "lớp DƯỚI thiếu key={ten} — video sẽ kẹt lại nguồn CŨ khi đổi giữa hai chủ đề đều có video");
});

test("KHONG mask/on dinh hoa cho bo video rollout — danh gia nguyen ban nhu nguoi dung duyet thu cong", () => {
  const s = codeOnly(comp());
  assert.ok(!/videoMask=/.test(s),
    "đang truyền videoMask — bộ 8 video rollout V4 phải được đánh giá NGUYÊN BẢN, không mask");
});

test("LiveBackground dung poster tu chinh anhNen(ten/tenMoi), khong hardcode duong dan khac", () => {
  const s = codeOnly(comp());
  assert.match(s, /poster=\{anhNen\(ten\)\}/, "lớp DƯỚI (ten) thiếu poster đúng theo chủ đề");
  assert.match(s, /poster=\{anhNen\(tenMoi\)\}/, "lớp TRÊN (tenMoi, đang reveal) thiếu poster đúng theo chủ đề");
});

test("lop video dung CHUNG mot class generic, object-position thua ke --diem cua TUNG chu de", () => {
  const s = codeOnly(comp());
  assert.ok(!/home-live-lop/.test(s), "vẫn còn class riêng cho home (\"home-live-lop\") — phải dùng class chung cho mọi chủ đề");
  assert.match(s, /className="live-wallpaper-lop"/g);
  assert.equal((s.match(/className="live-wallpaper-lop"/g) ?? []).length, 2, "cả hai lớp (dưới/trên) đều phải dùng class chung này");

  const cssText = css();
  assert.match(cssText, /\.live-wallpaper-lop \.live-bg-poster,\s*\n\.live-wallpaper-lop \.live-bg-video \{ object-position: var\(--diem, center\); \}/,
    "lớp video phải object-position: var(--diem, center) — kế thừa điểm neo riêng của MỖI chủ đề, không hard-code một giá trị");

  // Xac nhan CA 8 chu de deu co --diem rieng (khong chi home) — da co tu
  // truoc rollout nay, chi xac nhan lai chua bi xoa nham.
  for (const ten of CHU_DE) {
    assert.match(cssText, new RegExp(`\\.page-bg-lop\\[data-bg="${ten}"\\][^\\n]*--diem: [^;]+;`),
      `chủ đề "${ten}" thiếu --diem — lớp video sẽ lệch điểm neo với ảnh tĩnh`);
  }
});

test("V4: HAI lop tuong minh (duoi on dinh + tren dang reveal), khong con co che mang lop tu quan ly", () => {
  const s = codeOnly(comp());
  assert.ok(!/tenCu|data-ra=|cacLop/.test(s), "vẫn còn dấu vết cơ chế mảng lớp cũ (cacLop/tenCu/data-ra)");
  assert.equal((s.match(/className="page-bg-lop"/g) ?? []).length, 1,
    "lớp DƯỚI dùng className=\"page-bg-lop\" (không kèm page-bg-reveal)");
  assert.match(s, /className="page-bg-lop page-bg-reveal"/, "lớp TRÊN (đang reveal) thiếu class page-bg-reveal");
  assert.match(s, /key=\{the\}/, "lớp TRÊN thiếu key={the} — cần remount mỗi lần một reveal MỚI thật sự bắt đầu");
});

test("bat bien cu cua PageBackground van dung: khong <img>/style inline TRUC TIEP trong tep nay", () => {
  const s = codeOnly(comp());
  assert.ok(!/<img/.test(s));
  assert.ok(!/style=\{\{/.test(s));
});

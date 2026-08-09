/*
 * Tai lai trang KHONG duoc lam mat mot job dang chay.
 *
 * LOI DA XAY RA TREN PRODUCTION: `/write` giu job trong state cua React. Tai
 * lai trang la mat `job_id`, du job that van dang chay tren worker. Nguoi dung
 * tuong da dung, bam "Tạo audio" lai — va cuoi cung mot chuong co NAM job hoan
 * tat, hien thanh nam dong trong thu vien.
 *
 * Ba tang cung gop phan, va bo test nay giu ca ba:
 *   1. backend khong con cho hai request cung tao mot job (test o Python);
 *   2. `/write` tim lai job tu KHO sau khi tai lai trang;
 *   3. `/library` chi hien mot ban hien hanh cho moi chuong.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const write = () => read("../src/app/write/page.tsx");

/**
 * Bo chu thich truoc khi quet.
 *
 * Cac test duoi tim chuoi KHONG DUOC PHEP xuat hien (`localStorage`), nhung
 * chinh chu thich giai thich VI SAO chung bi cam lai chua nguyen van chuoi do.
 * Da do that o lan chay dau.
 */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ==================================================== khoi phuc sau reload */

test("/write hoi KHO khi nap trang, khong doi nguoi dung bam lai", () => {
  const src = write();
  assert.match(src, /api\.listJobs\(\)/, "không hỏi kho về job đang chạy");
  assert.match(src, /setJobs\(moiNhatTheoChuong\(jobList\.jobs\)\)/);
});

test("khoi phuc dung MOT request, khong N+1", () => {
  // `/api/chapters/{id}/jobs/latest` co ton tai va huu ich khi chi can hoi ve
  // dung mot chuong. Goi no trong vong lap la N+1 —
  // `tests/correctness-scale.test.mjs` khoa lai chinh cho do.
  const src = write();
  assert.ok(!src.includes("latestJobForChapter"),
    "/write gọi endpoint từng chương — N+1");
  const so_lan = (src.match(/api\.listJobs\(/g) ?? []).length;
  assert.equal(so_lan, 1, `gọi listJobs ${so_lan} lần, phải đúng 1`);
});

test("KHONG doc job_id tu localStorage — kho moi la nguon su that", () => {
  // Trinh duyet co the bi xoa du lieu, mo o may khac, hoac giu mot `job_id` da
  // bi worker khac thay the sau khi lease chet.
  const src = codeOnly(write());
  for (const cam of ["localStorage", "sessionStorage"]) {
    assert.ok(!src.includes(cam), `/write dùng ${cam} để nhớ job`);
  }
});

test("moiNhatTheoChuong uu tien job DANG CHAY hon ban hoan tat moi hon", async () => {
  const { moiNhatTheoChuong } = await import("../src/lib/jobs.ts");
  const ra = moiNhatTheoChuong([
    { job_id: "j-xong", chapter_id: "c1", status: "completed",
      created_at: "2026-08-09T10:00:00Z" },
    { job_id: "j-chay", chapter_id: "c1", status: "running",
      created_at: "2026-08-09T09:00:00Z" },
  ]);
  // Sau khi tai lai trang, cai nguoi dung can thay la thanh tien trinh, khong
  // phai mot ket qua cu.
  assert.equal(ra.c1.job_id, "j-chay");
});

test("moiNhatTheoChuong: cung trang thai thi lay cai moi hon", async () => {
  const { moiNhatTheoChuong } = await import("../src/lib/jobs.ts");
  const ra = moiNhatTheoChuong([
    { job_id: "cu", chapter_id: "c1", status: "completed",
      created_at: "2026-08-09T08:00:00Z" },
    { job_id: "moi", chapter_id: "c1", status: "completed",
      created_at: "2026-08-09T11:00:00Z" },
  ]);
  assert.equal(ra.c1.job_id, "moi");
});

test("moiNhatTheoChuong khong tron job cua hai chuong", async () => {
  const { moiNhatTheoChuong } = await import("../src/lib/jobs.ts");
  const ra = moiNhatTheoChuong([
    { job_id: "a", chapter_id: "c1", status: "running", created_at: "2026-08-09T08:00:00Z" },
    { job_id: "b", chapter_id: "c2", status: "pending", created_at: "2026-08-09T08:00:00Z" },
  ]);
  assert.deepEqual(Object.keys(ra).sort(), ["c1", "c2"]);
});

/* ============================================== job theo tung chuong */

test("job duoc giu theo chuong, khong phai MOT job toan cuc", () => {
  const src = write();
  assert.match(src, /useState<Record<string, TtsJob>>\(\{\}\)/,
    "vẫn giữ một job toàn cục — hai chương cùng xếp hàng sẽ đè nhau");
  assert.ok(!/const \[job, setJob\] = useState<TtsJob \| null>/.test(src));
});

test("poll MOI job dang chay, khong chi cai dang duoc nhin", () => {
  const src = write();
  assert.match(src, /Object\.values\(jobs\)\.filter\(/);
  assert.match(src, /Promise\.all\(ids\.map\(/);
});

/* ================================================== tien do that, khong bia */

test("tien do hien PHAN TRAM va SO PHAN khi da biet tong", () => {
  const src = write();
  assert.match(src, /\{job\.progress\}%/);
  assert.match(src, /\{job\.done_parts\} \/ \{job\.total_parts\} phần/);
});

test("KHONG bia ty le khi chua biet total_parts", () => {
  // Ban cu dat `percent={job.progress || 6}` — mot con so 6% khong den tu dau
  // ca, chi de thanh tien trinh trong "co dong tinh".
  const src = write();
  assert.ok(!/job\.progress \|\| 6/.test(src), "vẫn bịa 6%");
  assert.match(src, /percent=\{job\.total_parts \? job\.progress : 0\}/);
  assert.match(src, /indeterminate=\{!job\.total_parts\}/);
});

test("truoc khi biet tong thi noi ro dang lam gi", () => {
  const src = write();
  assert.match(src, /Đang chia chương thành các phần/);
});

/* ========================================== thu vien: mot dong moi chuong */

test("/library chi hien ban HIEN HANH cua moi chuong", () => {
  const src = read("../src/app/library/page.tsx");
  assert.match(src, /moi_nhat/, "vẫn vẽ một dòng cho mỗi job hoàn tất");
  assert.match(src, /job\.created_at > dang_co\.created_at/);
});

test("/library van doc job hoan tat, khong doi sang nguon khac", () => {
  // Sua trung lap KHONG duoc lam mat audio: van la job `completed`, chi la
  // gom theo chuong.
  const src = read("../src/app/library/page.tsx");
  assert.match(src, /job\.status !== "completed"/);
});

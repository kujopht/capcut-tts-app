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
 *
 * Phan vong theo doi da chuyen sang `lib/useJobTracker.ts` de `/studio` dung
 * chung — cac bai lien quan toi no nam o `job-progress-shared.test.mjs`. Cho
 * nay chi con giu duong DAU DAY cua `/write`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const write = () => read("../src/app/write/page.tsx");
const tracker = () => read("../src/lib/useJobTracker.ts");

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
  assert.match(src, /khoiPhucJob\(jobList\.jobs\)/);
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
  const src = tracker();
  assert.match(src, /useState<Record<string, TtsJob>>\(\{\}\)/,
    "vẫn giữ một job toàn cục — hai chương cùng xếp hàng sẽ đè nhau");
  assert.ok(!/const \[job, setJob\] = useState<TtsJob \| null>/.test(write()));
});

test("poll MOI job dang chay, khong chi cai dang duoc nhin", () => {
  const src = tracker();
  assert.match(src, /Object\.values\(jobs\)\.filter\(dangChayJob\)/);
  assert.match(src, /Promise\.all\(ids\.map\(/);
});

/* ============================================ vong poll phai THUC SU lap */

test("vong poll co nhip dem trong dependency, khong chi chay mot lan", () => {
  /*
    LOI DA LEN PRODUCTION: effect chi phu thuoc `[dangChayKey, toast]`. Sau
    moi lan poll, `setJobs()` tao object moi nhung `dangChayKey` van la CUNG
    MOT CHUOI (van dung mot `job_id` do), nen dependency khong doi va effect
    khong chay lai — khong co `setTimeout` nao duoc dat tiep.

    Ket qua: poll dung MOT nhip, bat duoc `pending -> running` roi dung han.
    Job xong sau 7 giay ma giao dien ket o "Đang xử lý" mai mai.
  */
  const src = tracker();
  const at = src.indexOf("const id = window.setTimeout(");
  assert.notEqual(at, -1, "khong tim thay vong poll");
  const sau = src.slice(at, at + 1800);

  assert.match(sau, /setTick\(\(t\) => t \+ 1\)/,
    "không có nhịp đếm — vòng poll sẽ chết sau một nhịp");
  assert.match(src, /\}, \[dangChayKey, tick, pollMs\]\)/,
    "nhịp đếm phải nằm trong dependency của effect");
});

test("nhip dem duoc dat NGOAI vong lap ket qua va khong dieu kien", () => {
  // Mot lan mang chap (moi request deu `catch` thanh null) van phai dat duoc
  // nhip ke tiep, neu khong mot loi thoang qua se giet vong poll y het loi cu.
  const src = codeOnly(tracker());
  const mo = src.indexOf("(ket_qua) => {");
  const at = src.indexOf("setTick((t) => t + 1)");
  assert.ok(mo !== -1 && at > mo, "khong tim thay than cua `.then`");

  const than = src.slice(mo, at);
  assert.ok(!/\bfor \(/.test(than), "setTick nằm trong vòng lặp kết quả");
  assert.ok(!/\bif \(/.test(than), "setTick bị đặt sau điều kiện");
});

test("job ket thuc thi vong poll TU DUNG", () => {
  // `khoaTheoDoi` chi giu `pending`/`running`; het job dang chay thi khoa rong
  // va effect thoat ngay o dong dau.
  const src = tracker();
  assert.match(src, /if \(!dangChayKey\) return;/);
  assert.match(read("../src/lib/jobs.ts"),
    /const CHUA_XONG: JobStatus\[\] = \["pending", "running"\];/);
});

test("completed thi cap nhat audio va tat canh bao ngay trong nhip do", () => {
  const src = write();
  const at = src.indexOf("onCompleted:");
  assert.notEqual(at, -1);
  const khoi = src.slice(at, at + 500);
  assert.match(khoi, /setAudioByChapter/);
  assert.match(khoi, /setStaleByChapter/);
});

test("failed thi bao loi cho nguoi dung", () => {
  const src = write();
  assert.match(src, /onFailed: \(\) => toast\.error\("Tạo audio thất bại\."\)/);
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

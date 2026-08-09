/*
 * `/studio` phai co CUNG hanh vi job voi `/write`.
 *
 * TRANG NAY DA O LAI PHIA SAU. Ba PR lien tiep sua tien do va khoi phuc sau
 * reload cho `/write`; `/studio` khong duoc huong gi ca, vi khong co gi dung
 * chung de sua mot lan. Nguoi dung o `/studio` thay:
 *   - mot thanh chay vo dinh voi 6% hoac 8% bia ra;
 *   - "Đã xong 5/7 đoạn" nhung khong bao gio thay phan tram;
 *   - chi MOT job duoc theo doi, du backend cho chay nhieu job.
 *
 * Phan logic dung chung duoc kiem that o `job-progress-shared.test.mjs`. Cho
 * nay kiem viec DAU DAY: `/studio` co that su cam vao logic do khong.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const studio = () => read("../src/app/studio/page.tsx");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================================ theo doi job */

test("/studio theo doi job qua hook chung, khong tu poll", () => {
  const src = studio();
  assert.match(src, /useJobTracker\(\{/);
  assert.ok(
    !codeOnly(src).includes("window.setTimeout"),
    "/studio vẫn tự đặt vòng poll",
  );
});

test("/studio theo doi MOI job dang chay, khong chi mot cai", () => {
  /*
    Ban cu giu dung mot `activeJob` trong state va poll dung `activeJob.job_id`.
    Bay gio job nam trong ban do theo chuong cua hook, va hook poll TAT CA cai
    nao chua xong.
  */
  const src = codeOnly(studio());
  assert.ok(
    !/const \[activeJob, setActiveJob\]/.test(src),
    "/studio vẫn giữ một job toàn cục",
  );
  assert.match(src, /const activeJob = activeChapterId \? \(jobs\[activeChapterId\] \?\? null\) : null;/);
});

/* ===================================================== khoi phuc sau reload */

test("F5 tren /studio: hoi KHO, khong doi nguoi dung bam lai", () => {
  const src = studio();
  assert.match(src, /api\.listJobs\(\)/, "không hỏi kho về job đang chạy");
  assert.match(src, /khoiPhucJob\(jobList\.jobs\)/, "không nạp job vào vòng theo dõi");
});

test("khoi phuc dung MOT request, khong N+1", () => {
  const src = studio();
  assert.ok(
    !src.includes("latestJobForChapter"),
    "/studio gọi endpoint từng chương — N+1",
  );
  const so_lan = (src.match(/api\.listJobs\(/g) ?? []).length;
  assert.equal(so_lan, 1, `gọi listJobs ${so_lan} lần, phải đúng 1`);
});

test("roi trang roi quay lai: van tim duoc job dang chay tu backend", () => {
  // `load()` chay lai moi lan trang duoc gan, va no luon hoi `listJobs()`.
  // Khong co nhanh nao doc lai state React cu hay `job_id` da luu san.
  const src = codeOnly(studio());
  assert.match(src, /setActiveChapterId\(\(current\) => current \|\| som_nhat\.chapter_id\)/);
  for (const cam of ["localStorage", "sessionStorage"]) {
    assert.ok(!src.includes(cam), `/studio dùng ${cam} để nhớ job`);
  }
});

/* ==================================================== hien thi tien do that */

test("/studio ve bang khung chung, khong tu ve thanh", () => {
  const src = studio();
  assert.match(src, /<JobProgress\b/);
  assert.ok(!codeOnly(src).includes("<ProgressBar"), "/studio vẫn tự vẽ thanh");
});

test("/studio khong con con so 6% hay 8% bia ra", () => {
  const src = codeOnly(studio());
  assert.ok(!/percent=\{6\}/.test(src), "vẫn bịa 6%");
  assert.ok(!/progress \|\| 8/.test(src), "vẫn bịa 8%");
});

test("/studio khong con dong 'Đã xong x/y đoạn' rieng", () => {
  // Chu nam o `tienDoJob` va la "5 / 7 phần" — dung mot cach noi voi `/write`.
  const src = codeOnly(studio());
  assert.ok(!src.includes("Đã xong"), "/studio vẫn tự viết chữ tiến độ riêng");
  assert.ok(
    !/\{activeJob\.done_parts\}|done_parts\}\/\$\{|đoạn`/.test(src),
    "/studio còn tự ghép chuỗi số phần — /write gọi là 'phần', không phải 'đoạn'",
  );
});

/* ================================================ hoan tat: tu cap nhat ngay */

test("lich su lay tu vong theo doi nen tu doi khi job xong", () => {
  /*
    Ban cu giu mot mang `jobs` rieng va phai tu dong bo o moi nhip poll. Bay
    gio lich su duoc suy ra tu ban do cua hook, nen khung "Tiến trình" va the
    trong "Lịch sử audio" khong the noi hai dieu khac nhau ve cung mot job.
  */
  const src = studio();
  assert.match(src, /Object\.values\(jobs\)/, "lịch sử không lấy từ vòng theo dõi");
  assert.ok(
    !/const \[jobs, setJobs\] = useState<TtsJob\[\]>/.test(codeOnly(src)),
    "/studio vẫn giữ mảng job riêng",
  );
});

test("hoan tat thi phat trinh nghe ngay, khong doi F5", () => {
  const src = studio();
  const at = src.indexOf('activeJob.status === "completed"');
  assert.notEqual(at, -1);
  assert.match(src.slice(at, at + 400), /<AudioPlayer/);
});

test("that bai thi noi ro nguyen nhan va cho thu lai", () => {
  const src = studio();
  const at = src.indexOf('activeJob.status === "failed"');
  assert.notEqual(at, -1);
  const khoi = src.slice(at, at + 1600);
  assert.match(khoi, /activeJob\.error_message \|\| "Không rõ nguyên nhân\."/);
  assert.match(khoi, /retry\(activeJob\)/);
  // Va van giu loi hua: khong tu doi sang giong khac.
  assert.match(khoi, /không tự đổi sang giọng khác/);
});

/* ======================================================== chong tao trung */

test("bam lai voi CUNG noi dung thi dung lai chuong cu", () => {
  /*
    Moi lan bam la Studio tao mot CHUONG moi, nen khoa van tay o backend
    (`owner + chapter + content_hash`) khong the nhan ra hai lan bam la mot:
    chuong khac nhau thi van tay khac nhau. Nho lai chuong da tao cho dung noi
    dung nay la thu cho phep khoa do lam viec.
  */
  const src = studio();
  assert.match(src, /let chapterId = khongDoi \? daGui\.chapterId : "";/);
  assert.match(src, /if \(!chapterId\) \{/, "vẫn tạo chương mới vô điều kiện");
  assert.match(
    src,
    /const khongDoi =\s*daGui !== null && daGui\.title === title\.trim\(\) && daGui\.text === text;/,
  );
});

test("doi noi dung thi VAN tao chuong moi", () => {
  // Audio khac thi ban ghi khac — khong duoc de lan sua de len ban cu.
  const src = studio();
  assert.match(src, /setDaGui\(\{ title: ten, text, chapterId \}\)/);
});

test("nut bi khoa trong khi job cho CHINH noi dung nay dang chay", () => {
  const src = studio();
  assert.match(
    src,
    /const dangChoJobNay = Boolean\(activeJob && dangChayJob\(activeJob\) && khongDoi\)/,
  );
  assert.match(src, /!dangChoJobNay/, "nút không bị khoá khi job đang chạy");
  assert.match(src, /dangChoJobNay \? "Đang tạo audio…" : "Tạo audio"/);
});

test("backend van la trong tai — frontend khong tu quyet dinh dung lai", () => {
  // `reused` den TU BACKEND. Frontend chi noi lai, khong tu suy ra.
  const src = studio();
  assert.match(src, /result\.reused \? "Dùng lại audio đã tạo\." : "Đã đưa vào hàng đợi\."/);
});

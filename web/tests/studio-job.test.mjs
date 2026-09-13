/*
 * Media Studio phai co CUNG hanh vi job voi `/studio/content` (Viet truyen).
 *
 * Truoc doi kien truc (`feat/studio-media-workspace`), day la bai kiem cho
 * `/studio/audio/page.tsx` — mot trang TTS rieng voi mo hinh "mot job hoat
 * dong tren moi chuong". Trang do khong con: tao loi doc nay la MOT bang
 * trong Media Studio (`/studio/media`), va no chi giu MOT o soan + MOT job
 * dang cho — khong phai mot danh sach chuong nhu Viet truyen.
 *
 * Nhung ba dieu ĐÃ TRẢ GIÁ THẬT o ban cu van la bat bien phai giu:
 *   - theo doi job qua `useJobTracker` dung chung, khong tu dat `setTimeout`;
 *   - khoi phuc sau F5 di qua `listJobs()` MOT lan, khong qua localStorage;
 *   - tien do ve bang `<JobProgress>` dung chung, khong tu ve thanh rieng.
 * Va mot dieu moi duoc bao ton tu Audio Studio: bam lai CUNG mot doan van
 * thi dung lai chuong cu, de khoa van tay o backend (owner+chapter+hash)
 * con tac dung — tao chuong moi moi lan bam se pha khoa do.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const trangMedia = () => read("../src/app/studio/media/page.tsx");
const ttsPanel = () => read("../src/components/media/TtsPanel.tsx");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================================ theo doi job */

test("Media Studio theo doi job qua hook chung, khong tu poll", () => {
  const src = trangMedia();
  assert.match(src, /useJobTracker\(\{/);
  assert.ok(
    !codeOnly(src).includes("window.setTimeout"),
    "Media Studio vẫn tự đặt vòng poll",
  );
});

/* ===================================================== khoi phuc sau reload */

test("F5 tren Media Studio: hoi KHO, khong doi nguoi dung bam lai", () => {
  const src = trangMedia();
  assert.match(src, /api\.listJobs\(\)/, "không hỏi kho về job đang chạy");
  assert.match(src, /khoiPhuc\(js\.jobs\)/, "không nạp job vào vòng theo dõi");
});

test("khoi phuc dung MOT request, khong N+1", () => {
  const src = trangMedia();
  assert.ok(
    !src.includes("latestJobForChapter"),
    "Media Studio gọi endpoint từng chương — N+1",
  );
  const so_lan = (src.match(/api\.listJobs\(/g) ?? []).length;
  assert.equal(so_lan, 1, `gọi listJobs ${so_lan} lần, phải đúng 1`);
});

test("roi trang roi quay lai: khong dung localStorage/sessionStorage de nho job", () => {
  const src = codeOnly(trangMedia());
  for (const cam of ["localStorage", "sessionStorage"]) {
    assert.ok(!src.includes(cam), `Media Studio dùng ${cam} để nhớ job`);
  }
});

/* ==================================================== hien thi tien do that */

test("tien do ve bang khung chung, khong tu ve thanh", () => {
  const src = ttsPanel();
  assert.match(src, /<JobProgress\b/);
  assert.ok(!codeOnly(src).includes("<ProgressBar"), "TtsPanel vẫn tự vẽ thanh");
});

test("khong bia phan tram — JobProgress nhan NGUYEN job, khong tu tinh so", () => {
  const src = codeOnly(ttsPanel());
  assert.ok(!/percent=\{6\}/.test(src), "vẫn bịa 6%");
  assert.ok(!/progress \|\| 8/.test(src), "vẫn bịa 8%");
  // `job` di THANG vao `<JobProgress job={...}>` — khong co phep tinh phan
  // tram nao rieng o day, tat ca nam trong `tienDoJob` dung chung.
  assert.match(src, /<JobProgress job=\{job\}/);
});

/* ================================================ hoan tat: tu cap nhat ngay */

test("job xong thi track moi len NGAY duong thoi gian, khong doi F5", () => {
  const src = trangMedia();
  const at = src.indexOf("onCompleted:");
  assert.notEqual(at, -1, "không thấy callback onCompleted");
  const khoi = src.slice(at, at + 400);
  assert.match(khoi, /ganTrackMoi/);
  // Ham do phai gan track vao du an VA len lane audio ngay, khong cho nguoi
  // dung tu vao kho bam chon.
  const ganAt = src.indexOf("const ganTrackMoi");
  const thanGan = src.slice(ganAt, ganAt + 900);
  assert.match(thanGan, /audio_track_id: moi\.id/);
  assert.match(thanGan, /datChon\(\{ loai: "audio" \}\)/);
});

test("that bai thi noi ro nguyen nhan, khong lam nguoi dung ket ket qua tao", () => {
  const src = trangMedia();
  const at = src.indexOf("onFailed:");
  assert.notEqual(at, -1);
  const khoi = src.slice(at, at + 300);
  assert.match(khoi, /error_message \|\| "Tạo lời đọc thất bại\."/);
  // Nut phai mo lai (`dangTaoTts(false)`) de nguoi dung bam lai duoc ngay —
  // do la duong "thu lai" thuc su o day, khong phai mot nut Retry rieng.
  assert.match(khoi, /datDangTaoTts\(false\)/);
});

/* ======================================================== chong tao trung */

test("bam lai voi CUNG tieu de + van ban thi dung lai chuong cu", () => {
  /*
    Moi lan tao chuong moi la lam khoa van tay o backend (owner + chapter +
    content_hash) mat tac dung: chuong khac nhau thi van tay khac nhau. Nho
    lai chuong da tao cho DUNG noi dung nay la thu cho phep khoa do lam viec.
  */
  const src = codeOnly(trangMedia());
  assert.match(src, /const daGuiTts = useRef</);
  assert.match(
    src,
    /const khongDoi =\s*truoc !== null && truoc\.tieuDe === y\.tieuDe && truoc\.vanBan === y\.vanBan;/,
  );
  assert.match(src, /let chapterId = khongDoi \? truoc\.chapterId : "";/);
  assert.match(src, /if \(!chapterId\) \{/, "vẫn tạo chương mới vô điều kiện");
});

test("gui xong thi nho lai LAN NAY de lan sau so sanh", () => {
  const src = codeOnly(trangMedia());
  assert.match(
    src,
    /daGuiTts\.current = \{ tieuDe: y\.tieuDe, vanBan: y\.vanBan, chapterId \};/,
  );
});

test("backend van la trong tai — frontend khong tu quyet dinh 'da dung'", () => {
  // `reused` den TU BACKEND. Frontend chi noi lai, khong tu suy ra.
  const src = trangMedia();
  assert.match(src, /jr\.reused \? "Dùng lại audio đã tạo\." : "Đã đưa vào hàng đợi\."/);
});

/*
 * MOT ban logic job cho ca `/write` va `/studio`.
 *
 * LOI DA XAY RA: hai trang tu viet vong poll va khung tien do rieng. Cac ban
 * va cua PR #11/#12/#13 chi duoc ap vao ban cua `/write`. `/studio` o lai phia
 * sau: theo doi dung MOT job, va ve tien do bang `progress || 8` — mot con so
 * 8% khong den tu dau ca. Nguoi dung o `/studio` khong bao gio thay phan tram
 * that, du backend da bao du `done_parts` va `total_parts`.
 *
 * Bo test nay giu HAI thu:
 *   1. logic that — `tienDoJob`, `gopNhipPoll`, `khoaTheoDoi` chay that voi
 *      du lieu that, nhieu nhip lien tiep;
 *   2. rang buoc CHONG LECH — khong trang nao duoc tu viet lai vong poll hay
 *      khung tien do cua rieng no nua.
 *
 * Diem thu hai moi la thu ngan lan sau. Neu `/studio` lai co `setTimeout` cua
 * chinh no thi bai test do lai, ke ca khi luc do no dang chay dung.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  dangChayJob,
  daKetThuc,
  gopNhipPoll,
  khoaTheoDoi,
  tienDoJob,
} from "../src/lib/jobs.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const write = () => read("../src/app/write/page.tsx");
const studio = () => read("../src/app/studio/page.tsx");
const tracker = () => read("../src/lib/useJobTracker.ts");
const khung = () => read("../src/components/JobProgress.tsx");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

let dem = 0;
const job = (p = {}) => ({
  job_id: `j${(dem += 1)}`,
  chapter_id: "c1",
  status: "running",
  progress: 0,
  total_parts: 0,
  done_parts: 0,
  created_at: "2026-08-09T10:00:00Z",
  voice_id: "piper:v",
  error_message: "",
  ...p,
});

/* ============================================== tien do: chua biet tong phan */

test("chua biet total_parts thi KHONG bia ty le", () => {
  // Hai con so bia da tung nam trong ma nguon that: `progress || 6` o `/write`
  // va `progress || 8` o `/studio`.
  const t = tienDoJob(job({ status: "running", total_parts: 0, progress: 0 }));
  assert.equal(t.percent, 0, "vẫn bịa một tỷ lệ khi chưa biết tổng");
  assert.equal(t.biet_tong, false, "phải để thanh chạy vô định");
  assert.equal(t.nhan, "Đang chuẩn bị…");
  assert.equal(t.chi_tiet, "", "chưa biết tổng thì không có dòng x/y phần");
});

test("job dang xep hang cung la 'Đang chuẩn bị…', khong phai mot % nao", () => {
  const t = tienDoJob(job({ status: "pending" }));
  assert.equal(t.percent, 0);
  assert.equal(t.biet_tong, false);
  assert.equal(t.nhan, "Đang chuẩn bị…");
});

/* ================================================ tien do: da biet tong phan */

test("da biet tong thi hien % that va so phan", () => {
  const t = tienDoJob(
    job({ status: "running", total_parts: 7, done_parts: 5, progress: 71 }),
  );
  assert.equal(t.biet_tong, true);
  assert.equal(t.percent, 71);
  assert.equal(t.nhan, "Đang xử lý · 71%");
  assert.equal(t.chi_tiet, "5 / 7 phần");
});

test("0/7 van la DA BIET TONG — day chinh la lot bao dau tien cua worker", () => {
  /*
    Backend goi `on_progress(0, len(chunks))` truoc khi tong hop phan dau tien
    (PR #13). Neu cho nay coi 0% la "chua biet" thi ban va do vo nghia: nguoi
    dung van thay thanh vo dinh trong suot phan dau.
  */
  const t = tienDoJob(
    job({ status: "running", total_parts: 7, done_parts: 0, progress: 0 }),
  );
  assert.equal(t.biet_tong, true, "0/7 là biết tổng, không phải chưa biết");
  assert.equal(t.chi_tiet, "0 / 7 phần");
  assert.equal(t.nhan, "Đang xử lý · 0%");
});

test("hoan tat LUON la 100% va noi 'Hoàn tất'", () => {
  const t = tienDoJob(
    job({ status: "completed", total_parts: 7, done_parts: 7, progress: 100 }),
  );
  assert.equal(t.percent, 100);
  assert.equal(t.nhan, "Hoàn tất");
  assert.equal(t.biet_tong, true, "hoàn tất thì không được để thanh vô định");
});

test("job cu khong con so phan van hien 100% khi hoan tat", () => {
  // Job tao truoc PR #13 khong co `total_parts`. Van phai day thanh len het.
  const t = tienDoJob(job({ status: "completed", total_parts: 0, progress: 0 }));
  assert.equal(t.percent, 100);
  assert.equal(t.biet_tong, true);
  assert.equal(t.chi_tiet, "", "không bịa ra số phần mà job không có");
});

test("that bai thi khong ve thanh tien trinh gia", () => {
  const t = tienDoJob(job({ status: "failed", total_parts: 0, progress: 0 }));
  assert.equal(t.nhan, "Thất bại");
  assert.equal(t.percent, 0);
});

/* ================================================== nhieu nhip poll lien tiep */

test("nhieu nhip: tien do di len dan va khong bao gio giat lui", () => {
  /*
    Day la thu bo test cu KHONG cham toi duoc: vong poll nam trong than effect
    cua tung trang. Tach `gopNhipPoll` thanh ham thuan la de chay that duoc
    mot chuoi nhip.
  */
  let ban_do = {};
  const nhip = [
    { status: "pending", total_parts: 0, done_parts: 0, progress: 0 },
    { status: "running", total_parts: 7, done_parts: 0, progress: 0 },
    { status: "running", total_parts: 7, done_parts: 3, progress: 42 },
    { status: "running", total_parts: 7, done_parts: 5, progress: 71 },
    { status: "completed", total_parts: 7, done_parts: 7, progress: 100 },
  ];
  const thay = [];
  for (const b of nhip) {
    const r = gopNhipPoll(ban_do, [job({ job_id: "j-co-dinh", ...b })]);
    ban_do = r.jobs;
    thay.push(tienDoJob(ban_do.c1));
  }

  assert.deepEqual(
    thay.map((t) => t.percent),
    [0, 0, 42, 71, 100],
  );
  assert.deepEqual(
    thay.map((t) => t.biet_tong),
    [false, true, true, true, true],
    "nhịp 2 đã có tổng thì phải thôi chạy vô định ngay từ đó",
  );
  assert.equal(thay[3].chi_tiet, "5 / 7 phần");
  assert.equal(thay[4].nhan, "Hoàn tất");
});

test("bao HOAN TAT dung mot lan, khong keu lai o moi nhip sau", () => {
  const xong_roi = job({ job_id: "j-co-dinh", status: "completed", progress: 100 });
  const lan_1 = gopNhipPoll({}, [xong_roi]);
  assert.equal(lan_1.xong.length, 1, "lần đầu phải báo");

  const lan_2 = gopNhipPoll(lan_1.jobs, [xong_roi]);
  assert.equal(lan_2.xong.length, 0, "job đã xong từ trước không được báo lại");
});

test("that bai cung chi bao mot lan", () => {
  const hong = job({ job_id: "j-co-dinh", status: "failed" });
  const lan_1 = gopNhipPoll({}, [hong]);
  assert.equal(lan_1.hong.length, 1);
  assert.equal(gopNhipPoll(lan_1.jobs, [hong]).hong.length, 0);
});

test("thu lai cung chuong thi VAN bao, vi la job KHAC", () => {
  // Bam "Thử lại" tao job moi cho cung chuong. Job cu that bai khong duoc lam
  // job moi im lang.
  const cu = job({ job_id: "j-cu", status: "failed" });
  const sau = gopNhipPoll({}, [cu]);
  const moi = job({ job_id: "j-moi", status: "completed", progress: 100 });
  assert.equal(gopNhipPoll(sau.jobs, [moi]).xong.length, 1);
});

test("mang chap mot nhip KHONG lam mat job dang chay", () => {
  // Moi request `catch` thanh null. Ban do phai giu nguyen.
  const dang_chay = job({ job_id: "j-co-dinh", total_parts: 7, done_parts: 2 });
  const truoc = gopNhipPoll({}, [dang_chay]).jobs;
  const sau = gopNhipPoll(truoc, [null, null]);
  assert.deepEqual(sau.jobs, truoc, "một lần mạng chập đã xoá job khỏi bản đồ");
  assert.equal(sau.xong.length + sau.hong.length, 0);
});

test("nhieu job cung luc: moi chuong mot dong, khong de len nhau", () => {
  const r = gopNhipPoll({}, [
    job({ job_id: "a", chapter_id: "c1", done_parts: 1, total_parts: 4 }),
    job({ job_id: "b", chapter_id: "c2", done_parts: 3, total_parts: 4 }),
  ]);
  assert.deepEqual(Object.keys(r.jobs).sort(), ["c1", "c2"]);
  assert.equal(tienDoJob(r.jobs.c2).chi_tiet, "3 / 4 phần");
});

/* ========================================================= khoa vong theo doi */

test("khoa chi gom job CHUA XONG, va vong dung khi het viec", () => {
  const ban_do = {
    c1: job({ job_id: "a", chapter_id: "c1", status: "running" }),
    c2: job({ job_id: "b", chapter_id: "c2", status: "completed" }),
    c3: job({ job_id: "c", chapter_id: "c3", status: "pending" }),
    c4: job({ job_id: "d", chapter_id: "c4", status: "failed" }),
  };
  assert.equal(khoaTheoDoi(ban_do), "a,c");
  // Het job chua xong -> khoa rong -> effect thoat ngay o dong dau.
  assert.equal(khoaTheoDoi({ c2: ban_do.c2, c4: ban_do.c4 }), "");
});

test("khoa on dinh du thu tu duyet doi", () => {
  // Khoa doi la effect tuong co job moi va dat lai `setTimeout` vo ich.
  const a = job({ job_id: "z", chapter_id: "c1" });
  const b = job({ job_id: "a", chapter_id: "c2" });
  assert.equal(khoaTheoDoi({ c1: a, c2: b }), khoaTheoDoi({ c2: b, c1: a }));
});

test("dangChayJob / daKetThuc phu kin bon trang thai", () => {
  for (const s of ["pending", "running"]) {
    assert.equal(dangChayJob(job({ status: s })), true, s);
    assert.equal(daKetThuc(job({ status: s })), false, s);
  }
  for (const s of ["completed", "failed"]) {
    assert.equal(dangChayJob(job({ status: s })), false, s);
    assert.equal(daKetThuc(job({ status: s })), true, s);
  }
});

/* ================================================== CHONG LECH: mot ban duy nhat */

test("KHONG trang nao con vong poll cua rieng no", () => {
  /*
    Day la bai giu cho lan sau. Hai trang tung co hai vong `setTimeout` rieng,
    va sua mot ben thi ben kia o lai phia sau — do la ly do `/studio` khong
    duoc huong bat ky ban va nao cua `/write`.
  */
  for (const [ten, src] of [["/write", write()], ["/studio", studio()]]) {
    const ma = codeOnly(src);
    assert.ok(
      !ma.includes("window.setTimeout"),
      `${ten} tự đặt setTimeout — vòng poll thứ hai sẽ lại lệch`,
    );
    assert.ok(
      !ma.includes("api.getJob("),
      `${ten} tự gọi getJob — phải đi qua useJobTracker`,
    );
  }
});

test("ca hai trang deu dung useJobTracker", () => {
  for (const [ten, src] of [["/write", write()], ["/studio", studio()]]) {
    assert.match(src, /useJobTracker\(/, `${ten} không dùng hook chung`);
  }
});

test("ca hai trang deu ve bang JobProgress, khong tu ve", () => {
  for (const [ten, src] of [["/write", write()], ["/studio", studio()]]) {
    assert.match(src, /<JobProgress\b/, `${ten} không dùng khung chung`);
    assert.ok(
      !codeOnly(src).includes("<ProgressBar"),
      `${ten} tự vẽ thanh tiến độ — đúng chỗ đã lệch lần trước`,
    );
  }
});

test("KHONG trang nao tu dinh nghia lai chu cua tien do", () => {
  /*
    Chu nam o `tienDoJob`. Chep lai vao trang la mo duong cho lech tiep — dung
    kieu lech da xay ra: `/write` noi "5 / 7 phần" con `/studio` noi
    "Đã xong 5/7 đoạn" ve cung mot thu.

    Chi cam DUNG cac cau cua khung tien do. Chu "phần" o cho khac (vi du loi
    khuyen cat bot van ban) khong lien quan.
  */
  for (const [ten, src] of [["/write", write()], ["/studio", studio()]]) {
    const ma = codeOnly(src);
    for (const chu of [
      "Đang chuẩn bị…",
      "Đang xử lý ·",
      "Đang chia chương thành các phần",
      "Đã xong",
    ]) {
      assert.ok(!ma.includes(chu), `${ten} vẫn tự viết chữ tiến độ: ${chu}`);
    }
    assert.ok(
      !/\{job\.done_parts\}|\{activeJob\.done_parts\}/.test(ma),
      `${ten} vẫn tự ghép dòng số phần`,
    );
  }
});

test("khong con con so ty le bia dau trong ma nguon", () => {
  for (const [ten, src] of [
    ["/write", write()],
    ["/studio", studio()],
    ["JobProgress", khung()],
  ]) {
    const ma = codeOnly(src);
    assert.ok(!/progress \|\| \d/.test(ma), `${ten} vẫn bịa tỷ lệ`);
    assert.ok(!/percent=\{\d+\}/.test(ma), `${ten} vẫn đặt percent bằng hằng số`);
  }
});

test("KHO la nguon su that — khong trang nao doc job tu localStorage", () => {
  for (const [ten, src] of [
    ["/write", write()],
    ["/studio", studio()],
    ["useJobTracker", tracker()],
  ]) {
    const ma = codeOnly(src);
    for (const cam of ["localStorage", "sessionStorage"]) {
      assert.ok(!ma.includes(cam), `${ten} dùng ${cam} để nhớ job`);
    }
  }
});

/* ============================================== vong poll o hook: van phai lap */

test("hook giu nhip dem trong dependency — vong poll khong chet sau mot nhip", () => {
  /*
    LOI DA LEN PRODUCTION (PR #12): effect chi phu thuoc `[dangChayKey]`. Sau
    moi lan poll, ban do job la object moi nhung khoa van la CUNG MOT CHUOI,
    nen dependency khong doi va khong co `setTimeout` nao duoc dat tiep.
  */
  const src = tracker();
  assert.match(src, /setTick\(\(t\) => t \+ 1\)/, "không có nhịp đếm");
  assert.match(
    src,
    /\}, \[dangChayKey, tick, pollMs\]\)/,
    "nhịp đếm phải nằm trong dependency của effect",
  );
});

test("nhip dem duoc dat khong dieu kien, ngoai moi nhanh re", () => {
  /*
    Mot lan mang chap — moi request deu `catch` thanh null — van phai dat duoc
    nhip ke tiep. Neu `setTick` nam trong mot `if` hay mot vong lap thi mot loi
    mang thoang qua se giet vong poll y het loi cu.
  */
  const src = codeOnly(tracker());
  const mo = src.indexOf("(ket_qua) => {");
  const at = src.indexOf("setTick((t) => t + 1)");
  assert.ok(mo !== -1 && at > mo, "khong tim thay than cua `.then`");

  const than = src.slice(mo, at);
  assert.ok(!/\bif \(/.test(than), "setTick nằm sau một nhánh rẽ");
  assert.ok(!/\bfor \(/.test(than), "setTick nằm trong vòng lặp kết quả");
});

test("vong poll thoat ngay khi khong con job chay", () => {
  assert.match(tracker(), /if \(!dangChayKey\) return;/);
});

test("callback di qua ref, KHONG qua dependency cua effect", () => {
  /*
    Trang truyen ham inline nen moi lan render la mot ham moi. De no trong
    dependency thi effect huy va dat lai `setTimeout` o moi lan render — vong
    poll bi lui vo han va khong bao gio chay.
  */
  const src = tracker();
  assert.match(src, /goiLai\.current\.onCompleted/);
  assert.ok(
    !/\[dangChayKey, tick, pollMs, onCompleted/.test(src),
    "callback lọt vào dependency của vòng poll",
  );
});

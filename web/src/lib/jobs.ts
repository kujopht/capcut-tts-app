/**
 * Gom job cua nguoi dung thanh trang thai ma giao dien can.
 *
 * Tach khoi `app/write/page.tsx` vi hai ly do, va ly do thu hai moi la
 * chinh: (1) day la logic THUAN, khong lien quan gi toi React; (2) Node
 * khong import duoc `.tsx`, nen logic nam trong trang thi khong co bo test
 * don vi nao cham toi duoc — chi con cach quet ma nguon bang regex, va do
 * la mot cach kiem rat yeu cho thu co nhieu nhanh nhu the nay.
 *
 * DAY LA NOI DUY NHAT dinh nghia y nghia cua mot job cho giao dien. `/write`
 * va `/studio` deu doc tu day, qua `useJobTracker` va `<JobProgress>`. Truoc
 * do moi trang tu viet lay: sua mot ben thi ben kia o lai phia sau, va do
 * chinh la thu da xay ra voi tien do that.
 */

import type { JobStatus, TtsJob } from "./api";

/**
 * Gom danh sach job thanh MOT job dang ke nhat cho moi chuong.
 *
 * Cung thu tu uu tien voi `_UU_TIEN_JOB` o `server/main.py`: job dang chay
 * thang moi thu khac, ke ca mot job hoan tat moi hon — sau khi tai lai trang,
 * cai nguoi dung can thay la thanh tien trinh, khong phai ket qua cu.
 */
const UU_TIEN: Record<string, number> = {
  running: 0,
  pending: 1,
  completed: 2,
  failed: 3,
};

export function moiNhatTheoChuong(danh_sach: TtsJob[]): Record<string, TtsJob> {
  const ra: Record<string, TtsJob> = {};
  for (const j of danh_sach) {
    const dang_co = ra[j.chapter_id];
    if (!dang_co) {
      ra[j.chapter_id] = j;
      continue;
    }
    const a = UU_TIEN[j.status] ?? 9;
    const b = UU_TIEN[dang_co.status] ?? 9;
    // Cung uu tien thi lay cai TAO SAU.
    if (a < b || (a === b && j.created_at > dang_co.created_at)) {
      ra[j.chapter_id] = j;
    }
  }
  return ra;
}

/** Chuong cua job dang chay dau tien, de khung tien trinh co cho de tro toi. */
export function dangChayDauTien(danh_sach: TtsJob[]): string {
  const chay = danh_sach.filter(
    (j) => j.status === "running" || j.status === "pending",
  );
  if (chay.length === 0) return "";
  // Cai chay lau nhat truoc: no gan xong nhat.
  return chay.reduce((a, b) => (a.created_at <= b.created_at ? a : b)).chapter_id;
}

/* ==================================================== trang thai cua mot job */

const CHUA_XONG: JobStatus[] = ["pending", "running"];

export function dangChayJob(job: TtsJob): boolean {
  return CHUA_XONG.includes(job.status);
}

export function daKetThuc(job: TtsJob): boolean {
  return job.status === "completed" || job.status === "failed";
}

/* ============================================================= vong theo doi */

/**
 * Khoa on dinh cho effect poll: danh sach `job_id` con dang chay, da sap xep.
 *
 * Phai la CHUOI chu khong phai mang: mang moi moi lan render se lam effect
 * chay lai vo tan. Va phai sap xep, neu khong thu tu duyet object thay doi la
 * effect tuong co job moi.
 */
export function khoaTheoDoi(jobs: Record<string, TtsJob>): string {
  return Object.values(jobs)
    .filter(dangChayJob)
    .map((j) => j.job_id)
    .sort()
    .join(",");
}

export interface NhipPoll {
  jobs: Record<string, TtsJob>;
  /** Job VUA chuyen sang hoan tat trong nhip nay. */
  xong: TtsJob[];
  /** Job VUA that bai trong nhip nay. */
  hong: TtsJob[];
}

/**
 * Gop ket qua mot nhip poll vao ban do job.
 *
 * Tach thanh ham THUAN de bo test chay duoc that su nhieu nhip lien tiep —
 * `useJobTracker` chi con la cai vo dat `setTimeout`. Truoc day toan bo cho
 * nay nam trong than effect cua `/write` va khong bai test nao cham toi duoc.
 *
 * `null` trong `ket_qua` la mot request hong (mang chap): giu nguyen ban cu,
 * KHONG xoa job khoi ban do — mot loi mang thoang qua khong duoc lam giao
 * dien quen mat job dang chay.
 */
export function gopNhipPoll(
  hien_tai: Record<string, TtsJob>,
  ket_qua: readonly (TtsJob | null)[],
): NhipPoll {
  const jobs = { ...hien_tai };
  const xong: TtsJob[] = [];
  const hong: TtsJob[] = [];

  for (const moi of ket_qua) {
    if (!moi) continue;
    const cu = jobs[moi.chapter_id];
    jobs[moi.chapter_id] = moi;
    // Chi bao khi VUA doi trang thai. Neu khong, mot job da xong tu truoc se
    // keu toast lai o moi nhip poll cua cac job khac.
    if (cu && cu.job_id === moi.job_id && daKetThuc(cu)) continue;
    if (moi.status === "completed") xong.push(moi);
    else if (moi.status === "failed") hong.push(moi);
  }

  return { jobs, xong, hong };
}

/* ================================================================== tien do */

export interface TienDo {
  /** Worker da bao tong so phan chua. Chua biet thi thanh phai chay vo dinh. */
  biet_tong: boolean;
  percent: number;
  done: number;
  total: number;
  /** Chu tren thanh tien trinh. */
  nhan: string;
  /** "5 / 7 phần", hoac rong khi chua biet tong. */
  chi_tiet: string;
}

/**
 * Trang thai job -> nhung gi ve len man hinh.
 *
 * KHONG BIA TY LE. Truoc khi worker bao `total_parts` thi khong ai biet chuong
 * se ra bao nhieu phan, nen thanh chay vo dinh moi la su that; dat dai mot con
 * so "6%" hay "8%" cho do trong la noi doi voi nguoi dung. Ca hai con so do
 * deu da tung nam trong ma nguon that.
 *
 * "Đang chuẩn bị…" chu khong phai "Đang chia chương thành các phần…": chia
 * chuong la thao tac trong bo nho, xong trong mot phan nghin giay. Thu that su
 * dien ra o day la CHO — cho worker nhan job, hoac cho `_PIPER_LOCK` khi mot
 * job khac dang chay.
 */
export function tienDoJob(job: TtsJob): TienDo {
  const total = job.total_parts || 0;
  const done = job.done_parts || 0;
  const biet_tong = total > 0;

  if (job.status === "completed") {
    // Hoan tat LUON la 100%, ke ca khi job cu trong kho khong con so phan.
    return {
      biet_tong: true,
      percent: 100,
      done: total,
      total,
      nhan: "Hoàn tất",
      chi_tiet: biet_tong ? `${total} / ${total} phần` : "",
    };
  }

  if (job.status === "failed") {
    return {
      biet_tong,
      percent: biet_tong ? job.progress : 0,
      done,
      total,
      nhan: "Thất bại",
      chi_tiet: "",
    };
  }

  if (!biet_tong) {
    return {
      biet_tong: false,
      percent: 0,
      done,
      total,
      nhan: "Đang chuẩn bị…",
      chi_tiet: "",
    };
  }

  return {
    biet_tong: true,
    percent: job.progress,
    done,
    total,
    nhan: `Đang xử lý · ${job.progress}%`,
    chi_tiet: `${done} / ${total} phần`,
  };
}

/**
 * Gom job cua nguoi dung thanh trang thai ma giao dien can.
 *
 * Tach khoi `app/write/page.tsx` vi hai ly do, va ly do thu hai moi la
 * chinh: (1) day la logic THUAN, khong lien quan gi toi React; (2) Node
 * khong import duoc `.tsx`, nen logic nam trong trang thi khong co bo test
 * don vi nao cham toi duoc — chi con cach quet ma nguon bang regex, va do
 * la mot cach kiem rat yeu cho thu co nhieu nhanh nhu the nay.
 */

import type { TtsJob } from "./api";

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

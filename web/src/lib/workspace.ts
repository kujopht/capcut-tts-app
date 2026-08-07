/**
 * Khu vuc lam viec rieng cua Audio Studio.
 *
 * Backend chi biet khai niem "chuong thuoc mot tieu thuyet" — `POST /api/jobs`
 * nhan `chapter_id`. Nhung Audio Studio thi cho nguoi dung DAN VAN BAN BAT KY.
 *
 * Cach lam: moi nguoi dung co MOT tieu thuyet an lam kho chua, danh dau bang
 * tag `audio-studio`. Moi lan tao audio la mot chuong trong do.
 *
 * Nho vay:
 *   - khong phai sua backend;
 *   - audio tu Studio KHONG tu bien thanh chuong fanfic — kho nay bi loc ra
 *     khoi moi danh sach cua khu vuc Fanfic;
 *   - no luon o trang thai ban nhap nen khong bao gio lot vao trang kham pha.
 */

import { api, type Novel } from "./api";

export const STUDIO_TAG = "audio-studio";
export const STUDIO_TITLE = "Audio Studio";

/** Kho chua cua Audio Studio, khong phai truyen fanfic. */
export function isStudioNovel(novel: Novel): boolean {
  return novel.tags.includes(STUDIO_TAG);
}

/** Chi giu lai truyen fanfic that su. */
export function fanficOnly(novels: Novel[]): Novel[] {
  return novels.filter((novel) => !isStudioNovel(novel));
}

/**
 * Lay kho chua cua Audio Studio, tao moi neu chua co.
 *
 * Goi lai nhieu lan an toan: luon tim truoc khi tao.
 */
export async function ensureStudioNovel(): Promise<Novel> {
  const { novels } = await api.listNovels(true);
  const existing = novels.find(isStudioNovel);
  if (existing) return existing;

  const created = await api.createNovel(
    STUDIO_TITLE,
    "Kho chứa audio tạo nhanh từ Audio Studio. Không phải truyện fanfic.",
    [STUDIO_TAG],
  );
  return created.novel;
}

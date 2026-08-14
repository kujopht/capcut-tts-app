/**
 * Dich "Quality AI" (Phan 4E) — gui CHI VAN BAN sang backend Fanfic
 * Translation qua `POST /api/tools/subtitles/translate`. Video KHONG BAO
 * GIO roi khoi may nguoi dung o duong nay.
 *
 * Chia LO o day (khop `SUBTITLE_TRANSLATE_MAX_LINES` phia backend) — phu de
 * dai hang tram dong khong duoc don thanh MOT request khong lo, treo timeout.
 */

import { api } from "@/lib/api";

const KICH_THUOC_LO = 50;

export class SubtitleTranslateError extends Error {}

/** Dich MOT DANH SACH dong theo LO, tuan tu (khong song song — tranh dua
    het han muc pool mien phi trong vai giay). Nem `SubtitleTranslateError`
    voi thong diep tieng Viet neu MOT lo that bai — cac lo da xong TRUOC do
    van giu nguyen ket qua (nguoi goi co the giu lai phan da dich). */
export async function dichDongPhuDe(
  texts: string[],
  onTienDo?: (daXong: number, tongSo: number) => void,
): Promise<string[]> {
  const ra: string[] = [];
  for (let i = 0; i < texts.length; i += KICH_THUOC_LO) {
    const lo = texts.slice(i, i + KICH_THUOC_LO);
    try {
      const { translated } = await api.translateSubtitleLines(lo);
      ra.push(...translated);
    } catch (cause) {
      throw new SubtitleTranslateError(
        cause instanceof Error ? cause.message : "Không dịch được lô này.");
    }
    onTienDo?.(ra.length, texts.length);
  }
  return ra;
}

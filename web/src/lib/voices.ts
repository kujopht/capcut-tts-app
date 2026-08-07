/**
 * Chon giong doc mac dinh.
 *
 * VI SAO CAN FILE RIENG: ban dau moi trang tu chon bang cach tim chuoi
 * "HoaiMy" trong `voice_id`. Chay that tren trinh duyet thi no bat trung mot
 * giong CapCut cung ten, va CapCut tra ve `TTSInvalidSpeaker` — nguoi dung mo
 * trang len, bam tao, va that bai ngay lan dau.
 *
 * Nay uu tien theo dung thu tu do tin cay, va dat o mot cho de hai trang
 * khong lech nhau.
 */

import type { Voice } from "./api";

/** Giong da duoc kiem chung end-to-end tren Appwrite + R2. */
export const VERIFIED_VOICE_ID = "edge:vi-VN-HoaiMyNeural";

export function usableVoices(voices: Voice[]): Voice[] {
  return voices.filter((voice) => voice.installed);
}

export function defaultVoiceId(voices: Voice[]): string {
  const usable = usableVoices(voices);
  if (usable.length === 0) return "";

  // 1. Dung giong da kiem chung, so khop TOAN BO id chu khong phai chuoi con.
  const verified = usable.find((voice) => voice.voice_id === VERIFIED_VOICE_ID);
  if (verified) return verified.voice_id;

  // 2. Bat ky giong Edge tieng Viet nao.
  const edgeVi = usable.find(
    (voice) =>
      voice.voice_id.startsWith("edge:") && voice.voice_id.includes("vi-VN"),
  );
  if (edgeVi) return edgeVi.voice_id;

  // 3. Bat ky giong Edge nao.
  const edge = usable.find((voice) => voice.voice_id.startsWith("edge:"));
  if (edge) return edge.voice_id;

  // 4. Het cach: lay giong dau tien dung duoc.
  return usable[0].voice_id;
}

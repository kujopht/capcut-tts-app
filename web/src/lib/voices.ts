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

/**
 * Giong nguoi dung chon duoc.
 *
 * `installed` mot minh la KHONG DU. No tra loi cau hoi "tien trinh API co file
 * model khong" — dung cho giong CapCut/Edge, sai hoan toan cho giong cuc bo:
 * model Piper nam tren laptop worker, con API chay tren Render, nen `installed`
 * o do luon false. Loc theo mot minh no thi Ngoc Huyen khong bao gio hien ra.
 *
 * `runs_on_worker` la cau tra loi cho dung cau hoi: may chu da duyet giong nay,
 * va noi kiem tra model la worker.
 */
export function usableVoices(voices: Voice[]): Voice[] {
  return voices.filter((voice) => voice.installed || voice.runs_on_worker);
}

/** Nhan cua hai muc trong bo chon giong. Mot cho khai bao duy nhat. */
export const RECOMMENDED_LABEL = "Giọng đề xuất";
export const ALL_VOICES_LABEL = "Tất cả giọng tiếng Việt";

/**
 * Chia giong thanh hai muc de hien thi.
 *
 * KHONG nhan ban `Voice` nao: day chi la HAI CACH TRINH BAY cung mot bo ban
 * ghi. Bay giong de xuat co mat o ca hai muc, va vi ca hai muc cung nam trong
 * MOT `<select>`, viec chon o muc nay tu dong dong bo voi muc kia — khong co
 * trang thai thu hai nao de lech.
 *
 * Thu tu muc de xuat do MAY CHU quyet dinh (`recommended_order`, lay tu
 * `desktop_app/providers/recommended.py`). Frontend khong duoc tu sap xep lai:
 * thu tu do la lua chon cua chu du an trong app desktop cu.
 */
export function voiceSections(voices: Voice[]): {
  recommended: Voice[];
  all: Voice[];
} {
  const usable = usableVoices(voices);
  const recommended = usable
    .filter((v) => v.recommended && v.recommended_order !== null)
    .sort((a, b) => (a.recommended_order ?? 0) - (b.recommended_order ?? 0));
  return { recommended, all: usable };
}

/**
 * Nhan mot dong trong bo chon giong.
 *
 * Voi giong chay tren may worker, PHAI noi ra dieu do. May chu khong biet
 * laptop worker dang bat hay tat — no chi biet giong nay khong chay tren no.
 * Noi "máy riêng" la su that va du de nguoi dung hieu vi sao job co the nam
 * cho; hua "đang trực tuyến" thi khong phai su that.
 */
export function voiceOptionLabel(voice: Voice): string {
  const phan = [voice.display_name, voice.provider_label];
  if (voice.runs_on_worker) phan.push("máy riêng");
  // Chi hien trang thai khi no NOI LEN MOT VAN DE.
  //
  // "unknown" (nhan: "Chưa kiểm tra") la mac dinh cua MOI giong cho toi khi co
  // probe that — no khong phai van de, chi la chua ai hoi. Do bang trinh duyet
  // that: dua "khac available" vao dieu kien lam ca 27 dong deu duoi thanh
  // "· Chưa kiểm tra", tuc la mot dong nhieu lap lai 27 lan ma khong phan biet
  // duoc giong nao that su hong.
  const CO_VAN_DE = ["unavailable", "not_installed", "degraded"];
  if (voice.status_label && CO_VAN_DE.includes(voice.status)) {
    phan.push(voice.status_label);
  }
  return phan.join(" · ");
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

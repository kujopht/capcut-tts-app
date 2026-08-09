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
 * model khong" — dung cho giong CapCut/Edge, sai hoan toan cho giong NghiTTS:
 * model nam tren may chu tong hop (GCE), con API chay tren Render, nen
 * `installed` o do luon false. Loc theo mot minh no thi khong giong NghiTTS
 * nao hien ra.
 *
 * `runs_on_worker` la cau tra loi cho dung cau hoi: may chu da duyet giong nay,
 * va noi co model la may chu tong hop.
 */
export function usableVoices(voices: Voice[]): Voice[] {
  return voices.filter((voice) => voice.installed || voice.runs_on_worker);
}

/**
 * `provider` cua bo NghiTTS, cung la tien to cua `voice_id` (`piper:<model>`).
 *
 * Day la khoa ben vung: no da nam trong job va track da tao, va gop phan sinh
 * `output_key` tren R2. Doi nhan hien thi khong duoc dong toi no.
 */
export const NGHITTS_PROVIDER = "piper";

/**
 * Giong nay co thuoc bo NghiTTS khong.
 *
 * Nhan dien theo `provider`, KHONG theo `runs_on_worker`. Hai co nay hom nay
 * trung nhau nhung tra loi hai cau hoi khac han: `provider` la DANH TINH cua
 * bo giong, con `runs_on_worker` la NOI chay. Them mot provider chay tren
 * worker sau nay se lam cach nhan dien theo `runs_on_worker` gan nham nhan
 * NghiTTS cho no.
 */
export function isNghiTtsVoice(voice: Voice): boolean {
  return voice.provider === NGHITTS_PROVIDER;
}

/** Nhan cua ba muc trong bo chon giong. Mot cho khai bao duy nhat. */
export const RECOMMENDED_LABEL = "Giọng đề xuất";
export const NGHITTS_LABEL = "NghiTTS";
export const ALL_VOICES_LABEL = "Tất cả giọng tiếng Việt";

/**
 * Chia giong thanh ba muc de hien thi.
 *
 * KHONG nhan ban `Voice` nao: day chi la BA CACH TRINH BAY cung mot bo ban
 * ghi. Mot giong NghiTTS duoc de xuat co mat o ca ba muc, va vi ca ba muc cung
 * nam trong MOT `<select>`, viec chon o muc nay tu dong dong bo voi muc kia —
 * khong co trang thai thu hai nao de lech.
 *
 * Thu tu muc de xuat do MAY CHU quyet dinh (`recommended_order`, lay tu
 * `desktop_app/providers/recommended.py`). Frontend khong duoc tu sap xep lai:
 * thu tu do la lua chon cua chu du an trong app desktop cu.
 *
 * Muc NghiTTS giu THU TU MAY CHU TRA VE, khong sap xep lai. May chu sinh danh
 * sach tu `builtin_catalog.PIPER_BUILTIN`, va thu tu do co y nghia: ba giong
 * co (da co ten hien thi that) dung truoc, phan con lai theo bang chu cai.
 */
export function voiceSections(voices: Voice[]): {
  recommended: Voice[];
  nghitts: Voice[];
  all: Voice[];
} {
  const usable = usableVoices(voices);
  const recommended = usable
    .filter((v) => v.recommended && v.recommended_order !== null)
    .sort((a, b) => (a.recommended_order ?? 0) - (b.recommended_order ?? 0));
  return { recommended, nghitts: usable.filter(isNghiTtsVoice), all: usable };
}

/**
 * Nhan mot dong trong bo chon giong.
 *
 * KHONG con phu chu "máy riêng". Cau do co tu thoi worker chay tren laptop cua
 * chu du an, khi "may co the dang tat" la mot su that nguoi dung can biet.
 * Production chay worker 24/7 tren Google Compute Engine, nen no khong con
 * dung — va no goi y sai rang nguoi dung phai co may cua rieng ho.
 *
 * `provider_label` cua giong NghiTTS do MAY CHU dat (xem
 * `LOCAL_PROVIDER_PUBLIC_LABEL`), khong phai frontend suy ra. Mot cho quyet
 * dinh duy nhat.
 */
export function voiceOptionLabel(voice: Voice): string {
  const phan = [voice.display_name, voice.provider_label];
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

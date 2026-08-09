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
 * Provider mà nhãn hiển thị CHỈ là tên giọng, không hậu tố.
 *
 * Nhận diện theo `provider`, KHÔNG theo `runs_on_worker`. Hai cờ này hôm nay
 * trùng nhau với NghiTTS nhưng trả lời hai câu hỏi khác hẳn: `provider` là
 * DANH TÍNH của bộ giọng, còn `runs_on_worker` là NƠI chạy.
 *
 * CapCut cố ý KHÔNG nằm trong danh sách này, và không phải vì bỏ sót. Trong
 * bộ 51 giọng có hai cặp trùng `display_name` bắc qua provider:
 *
 *     "Ban Mai"   — NghiTTS  vs  CapCut
 *     "Nam Minh"  — Edge     vs  CapCut
 *
 * Hậu tố "· CapCut" là thứ DUY NHẤT còn phân biệt hai dòng đó. Bỏ nốt nó thì
 * danh sách có hai cặp dòng trông y hệt nhau, và người dùng không có cách nào
 * biết mình đang chọn giọng nào.
 */
const PROVIDER_KHONG_HAU_TO = new Set([NGHITTS_PROVIDER, "edge"]);

function chiHienTen(voice: Voice): boolean {
  return PROVIDER_KHONG_HAU_TO.has(voice.provider);
}

/** Nhan cua hai muc trong bo chon giong. Mot cho khai bao duy nhat. */
export const RECOMMENDED_LABEL = "Giọng đề xuất";
export const ALL_VOICES_LABEL = "Tất cả giọng tiếng Việt";

/**
 * Chia giong thanh hai muc de hien thi.
 *
 * KHONG nhan ban `Voice` nao: day chi la HAI CACH TRINH BAY cung mot bo ban
 * ghi. Giong duoc de xuat co mat o ca hai muc, va vi ca hai muc cung nam trong
 * MOT `<select>`, viec chon o muc nay tu dong dong bo voi muc kia — khong co
 * trang thai thu hai nao de lech.
 *
 * KHONG co muc rieng cho NghiTTS. Da tung co mot muc nhu vay; bo di theo yeu
 * cau san pham. Giong NghiTTS nam trong "Tất cả giọng tiếng Việt" nhu moi
 * provider khac, va neu duoc de xuat thi cung xuat hien o muc de xuat nhu moi
 * provider khac. Day thuan tuy la thay doi TRINH BAY: `provider`,
 * `provider_label` va duong di cua job khong doi.
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
 * Giong NghiTTS va Edge chi hien TEN, khong hau to gi. Ca hai deu da co ten
 * tieng Viet dat dung ("Ngọc Huyền (Mới)", "Hoài My"), nen ten tu no da du ro;
 * dan them ten bo giong hay trang thai vao chi lam dong dai ra ma khong noi
 * them dieu gi nguoi dung can. Phu chu "máy riêng" cung da bo tu truoc: no co
 * tu thoi worker chay tren laptop chu du an, con production chay 24/7 tren
 * Google Compute Engine.
 *
 * CapCut VAN giu hau to — xem `PROVIDER_KHONG_HAU_TO` de biet vi sao: no la
 * thu duy nhat con phan biet hai cap giong trung ten.
 *
 * `provider_label` van co trong API (`/api/voices`) cho ai can no; day chi la
 * quyet dinh KHONG dua no vao ten hien thi.
 */
export function voiceOptionLabel(voice: Voice): string {
  if (chiHienTen(voice)) return voice.display_name;

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

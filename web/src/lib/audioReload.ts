/**
 * Y DINH PHAT cho the `<audio>` DUY NHAT — ap SAU khi nguon moi da nap.
 *
 * Hai luc can den:
 *   - URL ky R2 het han (nghe mot chuong dai, hoac tam dung lau roi bam phat
 *     tiep): lay URL moi, nhung nguoi nghe phai o NGUYEN cho cu va, neu dang
 *     phat, phat tiep;
 *   - nguoi dung bam "Tiếp tục nghe" / "Chương sau" luc dang nghe: nap chuong,
 *     tua toi giay da luu, phat.
 *
 * Ca hai di CUNG mot duong: `AudioEngine` ghi mot y dinh, doi `src` (qua
 * React), roi ap y dinh o hai moc cua chinh the: `loadedmetadata` (tua) va
 * `canplay` (phat). KHONG gan `currentTime` ngay sau khi doi nguon: luc do
 * the con o `HAVE_NOTHING`, va gia tri do bi bo qua o mot so trinh duyet —
 * audio chay lai tu 0:00.
 *
 * Tep thuan (khong DOM) — bai kiem Node chay CHINH cac ham nay voi mot the
 * gia (`tests/audio-url-refresh-resilience.test.mjs`).
 */

export interface YDinhPhat {
  batDauTu?: number;
  tuPhat?: boolean;
}

export interface TheCoViTri {
  currentTime: number;
  readonly duration: number;
}

/** Gan vi tri, kep trong [0, thoi luong - 0.25s] khi da biet thoi luong. */
export function datViTriAnToan(a: TheCoViTri, giay: number): void {
  if (!Number.isFinite(giay) || giay < 0) return;
  const d = a.duration;
  const dich = Number.isFinite(d) && d > 0 ? Math.min(giay, Math.max(0, d - 0.25)) : giay;
  try {
    a.currentTime = dich;
  } catch {
    /* Mot so trinh duyet nem khi chua co metadata. */
  }
}

/** Y dinh khi phai lay URL moi giua chung: giu vi tri, giu trang thai phat. */
export function yDinhKhiLamMoi(viTri: number, dangPhat: boolean): YDinhPhat {
  return { batDauTu: Number.isFinite(viTri) && viTri > 0 ? viTri : undefined, tuPhat: dangPhat };
}

/** Moc `loadedmetadata`: tua neu co y dinh. Tra ve phan y dinh CON LAI. */
export function apKhiCoMetadata(a: TheCoViTri, y: YDinhPhat | null): YDinhPhat | null {
  if (!y) return null;
  if (y.batDauTu !== undefined) datViTriAnToan(a, y.batDauTu);
  return y.tuPhat ? { tuPhat: true } : null;
}

/** Moc `canplay`: co phai phat khong, va y dinh sau do (luon het). */
export function apKhiSanSang(y: YDinhPhat | null): { phat: boolean; conLai: null } {
  return { phat: !!y?.tuPhat, conLai: null };
}

/** So lan toi da tu lam moi URL cho MOT loi lien tiep, truoc khi bao loi. */
export const TOI_DA_LAM_MOI = 2;

/** Gap loi phat: thu lam moi nua hay dung han. */
export function quyetDinhKhiLoi(soLanDaThu: number): { thuLai: boolean; soLanMoi: number } {
  if (soLanDaThu >= TOI_DA_LAM_MOI) return { thuLai: false, soLanMoi: soLanDaThu };
  return { thuLai: true, soLanMoi: soLanDaThu + 1 };
}

/**
 * Loi `play()` nao la LOI THAT can bao cho nguoi dung.
 *
 * - `AbortError`: lenh phat bi cat vi nguon vua doi (doi chuong, lam moi
 *   URL). Khong phai loi — lenh moi se phat.
 * - `NotAllowedError`: trinh duyet chan phat khi chua co cu chi cua nguoi
 *   dung (vd `?autoplay=1` luc vua mo tab). Khong phai loi cua tep — nut Phat
 *   van o do; hien "Trình duyệt không cho phát audio này" la noi sai.
 */
export function laLoiPhatThat(e: unknown): boolean {
  const ten = (e as { name?: string } | null)?.name;
  return ten !== "AbortError" && ten !== "NotAllowedError";
}

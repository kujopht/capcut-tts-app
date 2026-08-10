/**
 * Doi giay thanh chu doc duoc.
 *
 * MOT TEP RIENG, va khong import gi ca — do la ca ly do no ton tai o day.
 *
 * De trong `components/AudioEngine.tsx` thi khong test don vi duoc: Node
 * khong nap duoc `.tsx`. De trong `lib/audio.ts` cung khong, vi tep do import
 * GIA TRI tu `./api` (khong phai chi kieu), ma duong dan do khong co duoi tep
 * nen Node ESM tu choi. Tach ra day thi ham nay chay duoc trong `node --test`
 * ma khong keo theo thu gi.
 */

/** `83` -> `1:23`. Tra `--:--` khi chua biet thoi luong. */
export function dongHo(giay: number): string {
  // `Infinity` la gia tri THAT ma `<audio>.duration` tra ve khi chua doc xong
  // metadata, hoac voi luong khong biet do dai. Hien "0:00" o do la noi doi;
  // "--:--" noi dung rang chua biet.
  if (!Number.isFinite(giay) || giay < 0) return "--:--";
  const tong = Math.floor(giay);
  const gio = Math.floor(tong / 3600);
  const phut = Math.floor((tong % 3600) / 60);
  const gy = tong % 60;
  const hai = (n: number) => String(n).padStart(2, "0");
  return gio > 0 ? `${gio}:${hai(phut)}:${hai(gy)}` : `${phut}:${hai(gy)}`;
}

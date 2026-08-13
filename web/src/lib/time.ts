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

/**
 * `2026-08-11T09:00:00+00:00` -> `2 giờ trước`.
 *
 * NHẬN `now` LÀM THAM SỐ, mặc định là bây giờ. Không có nó thì hàm này không
 * kiểm thử được: mọi bài test sẽ phải dựng một mốc rồi mong nó không đổi giữa
 * hai dòng lệnh.
 *
 * Quá 7 ngày thì trả về NGÀY THẬT, không phải "12 tuần trước". Với một bài đăng
 * cũ, ngày cụ thể mới là thứ có ích; "37 tuần trước" bắt người đọc tự làm phép
 * trừ trong đầu.
 *
 * Mốc không đọc được trả về chuỗi rỗng, KHÔNG phải `Invalid Date` — một chuỗi
 * rỗng biến mất khỏi giao diện, còn `Invalid Date` thì hiện ra như một lỗi.
 */
export function khiNao(iso: string, now: Date = new Date()): string {
  const luc = new Date(iso);
  if (Number.isNaN(luc.getTime())) return "";
  const giay = Math.floor((now.getTime() - luc.getTime()) / 1000);
  // Lệch âm (đồng hồ máy khách chạy chậm hơn máy chủ) đọc ra là "vừa xong", chứ
  // không phải "trong 3 giây nữa" — thứ đó nghe như một lỗi.
  if (giay < 60) return "vừa xong";
  const phut = Math.floor(giay / 60);
  if (phut < 60) return `${phut} phút trước`;
  const gio = Math.floor(phut / 60);
  if (gio < 24) return `${gio} giờ trước`;
  const ngay = Math.floor(gio / 24);
  if (ngay <= 7) return `${ngay} ngày trước`;
  return luc.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

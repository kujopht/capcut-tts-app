/**
 * Live Wallpaper V1, Phan 21 — CHI mot khai niem NHO, chua phai mot tinh
 * nang cai dat day du. Du an CHUA co he thong preferences nguoi dung nao
 * (da kiem tra: khong co localStorage/settings page rieng cho tuy chon
 * hien thi) — nen dem nay KHONG dung mot trang "Cai dat" moi, chi dat TEN
 * va Y NGHIA cho ba lua chon tuong lai de `LiveBackground`/mot trang cai
 * dat sau nay co the dung LAI dung mot khai niem, khong tu dat ten khac.
 *
 * Chua duoc doc/ghi o dau ca — la mot STUB co y.
 */

/** "Hiệu ứng nền" — ba lua chon nguoi dung co the chon trong tuong lai. */
export type HieuUngNen = "auto" | "dynamic" | "static";

/**
 * AUTO: de he thong tu quyet dinh theo kha nang may/mang (giong hanh vi
 *       MAC DINH hien tai cua `LiveBackground` — `prefers-reduced-motion`,
 *       `saveData`, kich thuoc man hinh).
 * DYNAMIC: uu tien video khi co the, bo qua uu tien "tiet kiem" mem (nhung
 *       KHONG bao gio bo qua `prefers-reduced-motion` — do la yeu cau
 *       trợ năng, khong phai mot tuy chon tham my).
 * STATIC: luon dung poster, khong bao gio phat video.
 */
export function apDungHieuUngNen(
  luaChon: HieuUngNen,
  moiTruong: { giamChuyenDong: boolean; tietKiemDuLieu: boolean; laManHinhNho: boolean },
): boolean {
  if (moiTruong.giamChuyenDong) return false; // trợ năng luôn thắng, ở cả 3 lựa chọn
  if (luaChon === "static") return false;
  if (luaChon === "dynamic") return true;
  // "auto": logic mac dinh hien tai cua LiveBackground.
  return !moiTruong.tietKiemDuLieu && !moiTruong.laManHinhNho;
}

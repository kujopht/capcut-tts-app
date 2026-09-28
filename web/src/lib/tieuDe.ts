/**
 * Tieu de tu sinh cho mot ban audio khi nguoi dung khong dat tieu de.
 *
 * Truoc day la `vanBan.slice(0, 40)` — cat giua chu ("Gió đê"), nhin nhu loi.
 * Nay: gop khoang trang, cat o RANH GIOI TU gan nhat trong tran, them "…" khi
 * co cat. Chuoi khong co khoang trang (mot tu rat dai) thi cat cung o tran.
 */
export const TRAN_TIEU_DE = 48;

export function tieuDeTuVanBan(vanBan: string, tran = TRAN_TIEU_DE): string {
  const gon = vanBan.replace(/\s+/g, " ").trim();
  if (gon.length <= tran) return gon;
  const cat = gon.slice(0, tran);
  const khoang = cat.lastIndexOf(" ");
  const phan = khoang >= tran / 2 ? cat.slice(0, khoang) : cat;
  return `${phan.replace(/[\s,.;:!?—–-]+$/u, "")}…`;
}

/**
 * Cac ham dinh dang dung chung (chay duoc ca o Server Component lan Client).
 */

export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(value: number): string {
  return value.toLocaleString("vi-VN");
}

/**
 * Gio chinh xac theo mui gio Asia/Saigon (kieu `14:32:05, 23/11/2026`).
 * Khac `formatDate` o cho: khoa chac mui gio thay vi lay mui gio may
 * nguoi xem — trang quan tri can mot moc goc chung cho moi admin.
 */
export function formatDateTimeSG(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Thoi gian tuong doi tieng Viet ("vua xong", "2 phut truoc"...).
 * `bayGio` chi de test — mac dinh la thoi diem goi ham.
 */
export function formatRelative(iso: string | null, bayGio = Date.now()): string {
  if (!iso) return "Chưa từng online";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const giay = Math.floor((bayGio - date.getTime()) / 1000);
  if (giay < 0) return "Vừa xong";
  if (giay < 60) return "Vừa xong";
  const phut = Math.floor(giay / 60);
  if (phut < 60) return `${phut} phút trước`;
  const gio = Math.floor(phut / 60);
  if (gio < 24) return `${gio} giờ trước`;
  const ngay = Math.floor(gio / 24);
  if (ngay < 30) return `${ngay} ngày trước`;
  const thang = Math.floor(ngay / 30);
  if (thang < 12) return `${thang} tháng trước`;
  return `${Math.floor(thang / 12)} năm trước`;
}

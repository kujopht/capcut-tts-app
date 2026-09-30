/**
 * Cờ phiên (sessionStorage) của trợ lý AI NỔI — chính sách "ai được mở panel".
 *
 * Luật: CHỈ một hành động mở TƯỜNG MINH của người dùng trên panel nổi (bấm nút
 * nổi, lối vào Story trên desktop) mới được ghi cờ mở. Trang toàn màn hình
 * `/assistant` KHÔNG phải panel nổi: vào đó thì panel nổi ĐÓNG và cờ bị xoá,
 * nên quay lại một trang thường (Back, nút X, link) panel vẫn đóng cho tới khi
 * người dùng tự mở. Lỗi cũ: `/assistant` gọi `openAssistant()` → ghi cờ "1" →
 * mọi trang sau đó (và cả lần tải lại) tự bật panel.
 *
 * Hội thoại đang mở (`CO_HOI_THOAI`), lịch sử và bản nháp KHÔNG bị chạm bởi
 * bất kỳ hành động nào ở đây — chỉ trạng thái hiển thị của panel nổi.
 *
 * Tách khỏi `AiProvider.tsx` thành hàm thuần để test chạy được chuỗi thao tác
 * thật (`web/tests/ai-assistant-v1.test.mjs`), không chỉ soi mã nguồn.
 */

export const CO_MO = "fas.ai.open";
export const CO_HOI_THOAI = "fas.ai.conv";

/** Tập con của `Storage` mà ta dùng — test truyền một bản giả dựa trên `Map`. */
export interface KhoPhien {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** `window.sessionStorage`, hoặc `null` khi không có (SSR, chế độ riêng tư chặn truy cập). */
export function khoPhien(): KhoPhien | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function docPhien(key: string, kho: KhoPhien | null = khoPhien()): string | null {
  if (!kho) return null;
  try {
    return kho.getItem(key);
  } catch {
    return null;
  }
}

export function ghiPhien(key: string, value: string | null, kho: KhoPhien | null = khoPhien()): void {
  if (!kho) return;
  try {
    if (value === null) kho.removeItem(key);
    else kho.setItem(key, value);
  } catch {
    // Chế độ riêng tư/hết hạn mức — bỏ qua, không phải lỗi nghiêm trọng.
  }
}

export type HanhDongMo =
  /** Người dùng bấm mở panel nổi (nút nổi, lối vào Story trên desktop). */
  | "mo_noi"
  /** Người dùng bấm X của panel nổi. */
  | "dong_noi"
  /** Trang `/assistant` được mount — toàn màn hình thay chỗ panel nổi. */
  | "vao_toan_man";

/** Áp một hành động: ghi/xoá cờ mở và trả về giá trị `open` MỚI của panel nổi. */
export function apDungHanhDongMo(hanhDong: HanhDongMo, kho: KhoPhien | null = khoPhien()): boolean {
  if (hanhDong === "mo_noi") {
    ghiPhien(CO_MO, "1", kho);
    return true;
  }
  ghiPhien(CO_MO, null, kho);
  return false;
}

/** Trạng thái khôi phục khi tải lại trang/đăng nhập lại trong CÙNG tab. */
export function khoiPhucMo(kho: KhoPhien | null = khoPhien()): { open: boolean; conversationId: string | null } {
  return { open: docPhien(CO_MO, kho) === "1", conversationId: docPhien(CO_HOI_THOAI, kho) };
}

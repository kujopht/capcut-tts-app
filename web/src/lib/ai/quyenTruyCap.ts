/**
 * Cổng HIỂN THỊ của Trợ lý AI: nút nổi, mục "Trợ lý AI" trong menu tài khoản, lối vào
 * ở trang truyện. Máy chủ quyết (`GET /api/ai/access` → `{eligible}`), cùng luật với
 * các route `/api/ai/*` thật: khán giả (canary/beta/all), cờ backend, công tắc khẩn cấp.
 *
 * Frontend KHÔNG biết danh sách tester, ID, lý do hay provider — chỉ một bit. Đây không
 * phải rào chặn: sửa bit này trong trình duyệt chỉ hiện ra một nút mà máy chủ vẫn từ chối
 * (403 `ai_not_enabled`).
 *
 * Thuần (không React, không mạng) để `node --test` gọi thẳng được.
 */

/** `null` = chưa hỏi máy chủ / đang hỏi. `true`/`false` = máy chủ đã trả lời cho ĐÚNG người này. */
export type AiAccess = boolean | null;

/** Kết quả gắn với người đã hỏi — đổi tài khoản thì kết quả cũ không còn giá trị. */
export interface AiAccessKetQua {
  userId: string;
  eligible: boolean;
}

/** Chỉ HỎI máy chủ khi bản build bật cờ VÀ đã đăng nhập. Khách / cờ tắt: 0 request. */
export function nenHoiQuyen(coBat: boolean, userId: string | null | undefined): boolean {
  return coBat && typeof userId === "string" && userId.length > 0;
}

/** Đọc phản hồi `/api/ai/access`. Chỉ `{eligible: true}` mới mở; mọi thứ khác ĐÓNG. */
export function docQuyen(body: unknown): boolean {
  return typeof body === "object" && body !== null && (body as { eligible?: unknown }).eligible === true;
}

/** Bit của người ĐANG đăng nhập: kết quả của người khác (vừa đổi tài khoản) = chưa biết. */
export function quyenHienTai(ketQua: AiAccessKetQua | null, userId: string | null | undefined): AiAccess {
  if (!ketQua || !userId || ketQua.userId !== userId) return null;
  return ketQua.eligible;
}

/** Vẽ lối vào không: cờ bật, đã đăng nhập, và máy chủ ĐÃ xác nhận. Chưa biết = KHÔNG vẽ. */
export function hienLoiVao(coBat: boolean, userId: string | null | undefined, access: AiAccess): boolean {
  return nenHoiQuyen(coBat, userId) && access === true;
}

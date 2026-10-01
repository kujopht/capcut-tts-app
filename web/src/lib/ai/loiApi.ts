/**
 * Đọc thân lỗi HTTP của `/api/ai/*` — hàm THUẦN (không import gì) để test
 * chạy thẳng được (`web/tests/ai-assistant-v1.test.mjs`).
 *
 * FastAPI bọc `HTTPException(detail={...})` thành `{"detail": {code, message,
 * reset_at}}` (và `{"detail": "chuỗi"}` cho 401...). Bản cũ đọc `code` ở TẦNG
 * NGOÀI CÙNG nên không bao giờ thấy mã: mọi 429 (hết ngân sách ngày, quá
 * nhanh) và 503 `ai_busy` đều hiện thành "đang tạm gián đoạn" — phát hiện ở
 * QA release gate trên Lightning (2026-09-30).
 */
export interface LoiApiDoc {
  message: string;
  status: number;
  code?: string;
  resetAt: string | null;
  /** Chỉ có ở `ai_budget_exhausted`: điều gì đã hết ("user" | "global" | "qa"). Thiếu/lạ = `undefined`. */
  scope?: "user" | "global" | "qa";
}

export function docLoiApi(body: unknown, status: number, macDinh: string): LoiApiDoc {
  const ngoai = body && typeof body === "object" ? (body as Record<string, unknown>) : null;
  const d = ngoai && "detail" in ngoai ? ngoai.detail : ngoai;
  if (typeof d === "string") return { message: d || macDinh, status, resetAt: null };
  const obj = d && typeof d === "object" ? (d as Record<string, unknown>) : null;
  const doc: LoiApiDoc = {
    message: (obj && typeof obj.message === "string" && obj.message) || macDinh,
    status,
    code: obj && typeof obj.code === "string" ? obj.code : undefined,
    resetAt: obj && typeof obj.reset_at === "string" ? obj.reset_at : null,
  };
  // Chỉ gắn khi có: hình dạng cũ của kết quả (không có khoá `scope`) giữ nguyên cho mọi lỗi khác.
  const scope = obj ? obj.scope : undefined;
  if (scope === "user" || scope === "global" || scope === "qa") doc.scope = scope;
  return doc;
}

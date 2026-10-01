/**
 * Hạn mức RIÊNG của người dùng + trạng thái "chưa gửi" — logic THUẦN (không React, không mạng, không import
 * runtime) để `node --test` gọi thẳng được (`web/tests/ai-quota-ux.test.mjs`).
 *
 * Quy tắc bất di bất dịch của giao diện người dùng:
 *   1. Chỉ hiện hạn mức CỦA CHÍNH người đó (số lượt còn lại + giờ làm mới). Mức dùng toàn site, công suất nhà
 *      cung cấp, phần trăm "đã dùng" kiểu cũ: KHÔNG BAO GIỜ — chúng thuộc `/admin/ai`. Trước đây nhãn hiện
 *      "Đã dùng 51% hạn mức hôm nay" (ngân sách token cũ) ngay cạnh "đã dùng hết lượt hỏi" (trần 5 lượt thật):
 *      hai thước đo khác nhau, người dùng chỉ thấy mâu thuẫn.
 *   2. Hết lượt của bạn / hết công suất chung của site / hết hạn mức QA là BA câu khác nhau; câu về công suất
 *      chung nói rõ "không phải do bạn" và không kèm con số nào.
 *   3. Một tin bị máy chủ từ chối trước khi nhận phải hiện là "chưa gửi", không phải đã gửi.
 */
import type { AiAllowance, AiAvailability, AiBudgetScope, AiMessage } from "./types";

const soNguyen = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.floor(v) : null;

/**
 * Đọc `limits` (availability) hoặc `allowance` (sự kiện `usage`). Hình dạng cũ — chỉ có token `used_today` /
 * `limit_today` — cho `null`: giao diện không bịa ra "x/y lượt" từ số token.
 */
export function docHanMuc(raw: unknown): AiAllowance | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const used = soNguyen(r.requests_used);
  if (used === null || typeof r.exhausted !== "boolean") return null;
  const limit = soNguyen(r.requests_limit);
  const remaining = limit === null ? null : (soNguyen(r.requests_remaining) ?? Math.max(0, limit - used));
  return {
    requests_used: used,
    requests_limit: limit,
    requests_remaining: remaining,
    exhausted: r.exhausted,
    reset_at: typeof r.reset_at === "string" ? r.reset_at : null,
  };
}

/** Chuỗi phạm vi từ máy chủ → kiểu hẹp; giá trị lạ / thiếu (máy chủ cũ) → `undefined` (coi như "user"). */
export function docPhamVi(raw: unknown): AiBudgetScope | undefined {
  return raw === "user" || raw === "global" || raw === "qa" ? raw : undefined;
}

/** ISO → "HH:MM" giờ địa phương của người dùng (nửa đêm UTC = 07:00 ở Việt Nam). "" nếu không đọc được. */
export function dinhDangGio(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  try {
    return t.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Đã hết lượt thật sự chưa? Quá giờ làm mới rồi thì KHÔNG khoá cứng ô soạn nữa (bảng điều khiển có thể mở qua
 * nửa đêm UTC) — để máy chủ quyết ở lần gửi kế tiếp.
 */
export function daHetLuot(h: AiAllowance | null | undefined, now: number = Date.now()): boolean {
  if (!h || !h.exhausted) return false;
  const t = h.reset_at ? Date.parse(h.reset_at) : NaN;
  return !(Number.isFinite(t) && now >= t);
}

/** Dòng hạn mức dưới tiêu đề panel. `gio` đã định dạng (`dinhDangGio`). "" = không có gì để nói. */
export function nhanHanMuc(h: AiAllowance | null | undefined, gio: string, now: number = Date.now()): string {
  if (!h) return "";
  const lamMoi = gio ? `Làm mới lúc ${gio}.` : "";
  if (daHetLuot(h, now)) {
    const dem = h.requests_limit === null ? "" : ` (0/${h.requests_limit})`;
    return `Bạn đã hết lượt hỏi hôm nay${dem}. ${lamMoi}`.trim();
  }
  // Đã qua giờ làm mới: con số cũ không còn đúng, và chưa biết con số mới -> không nói gì cho tới lần gửi sau.
  if (h.exhausted) return "";
  if (h.requests_limit === null || h.requests_remaining === null) return "";
  return `Hôm nay còn ${h.requests_remaining}/${h.requests_limit} lượt hỏi${gio ? ` · làm mới lúc ${gio}` : ""}`;
}

/** Câu thông báo khi máy chủ báo `ai_budget_exhausted`, theo ĐÚNG phạm vi (xem quy tắc 2 ở đầu tệp). */
export function thongDiepHetLuot(scope: AiBudgetScope | undefined, gio: string): string {
  const lamMoi = gio ? ` Làm mới lúc ${gio}.` : "";
  switch (scope) {
    case "global":
      return `Trợ lý AI đã đạt giới hạn sử dụng của hôm nay — không phải do bạn.${gio ? ` Thử lại sau ${gio}.` : " Thử lại sau."}`;
    case "qa":
      return `Đã hết hạn mức QA của hôm nay.${lamMoi}`;
    default:
      return `Bạn đã hết lượt hỏi hôm nay.${lamMoi}`;
  }
}

/**
 * Đánh dấu tin người dùng vừa gửi là CHƯA GỬI (máy chủ từ chối trước khi nhận, nên nó không có trong hội thoại
 * thật). Chỉ đổi đúng tin của người dùng có `messageId`; mọi thứ khác nguyên vẹn. Không đổi mảng gốc.
 */
export function danhDauChuaGui(messages: AiMessage[], messageId: string): AiMessage[] {
  return messages.map((m) =>
    m.message_id === messageId && m.role === "user" ? { ...m, status: "not_sent" as const } : m,
  );
}

/**
 * "Tạo lại" chỉ bỏ câu trả lời cũ khi máy chủ ĐÃ NHẬN lượt mới (sự kiện `meta`), không phải ngay lúc bấm: nếu lượt
 * tạo lại bị từ chối (hết hạn mức…), câu trả lời cũ còn nguyên thay vì biến mất khỏi màn hình.
 */
export function boTinTraLoiCu(messages: AiMessage[], regenerateOf: string | undefined): AiMessage[] {
  return regenerateOf ? messages.filter((m) => m.message_id !== regenerateOf) : messages;
}

/**
 * Khi máy chủ từ chối vì hết lượt CỦA BẠN, ghi nhận ngay vào availability để ô soạn khoá lại mà không cần hỏi
 * lại máy chủ. Phạm vi "global"/"qa" KHÔNG đổi hạn mức riêng của người dùng nên giữ nguyên.
 */
export function apDungHetLuot(
  av: AiAvailability | null | false,
  scope: AiBudgetScope | undefined,
  resetAt: string | null | undefined,
): AiAvailability | null | false {
  if (!av || scope === "global" || scope === "qa") return av;
  const cu = av.limits;
  return {
    ...av,
    limits: {
      requests_used: cu?.requests_used ?? 0,
      requests_limit: cu?.requests_limit ?? null,
      requests_remaining: cu?.requests_limit == null ? null : 0,
      exhausted: true,
      reset_at: resetAt ?? cu?.reset_at ?? null,
    },
  };
}

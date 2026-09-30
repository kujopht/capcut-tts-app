/**
 * Ánh xạ TRẠNG THÁI THẬT của Trợ lý AI (`AiProvider`) sang trạng thái linh vật
 * Ink Scout. Hàm THUẦN — không React, không DOM, không hẹn giờ — để test được
 * bằng `node --test` và để mọi quyết định "linh vật đang làm gì" nằm ở MỘT chỗ.
 *
 * Nguồn tín hiệu (không mô phỏng bằng timer khi đã có trạng thái thật):
 *   * `availability === false` / `!availability.enabled` / mất mạng → offline
 *   * `streaming` + `streamingText` rỗng  → TRƯỚC token đầu (thinking / searching)
 *   * `streaming` + có chữ               → đang stream (answering / writing)
 *   * `error` của lượt vừa rồi            → error (hoặc offline nếu là lỗi "không có AI")
 *   * `flash === "success"`               → lượt vừa xong trọn vẹn (sự kiện, do component đặt)
 *   * `open`                              → listening
 *
 * "searching": frontend V1 KHÔNG gửi `use_web_search`, nên không có tín hiệu
 * tìm web thật. Tín hiệu thật gần nhất là chế độ Truyện ở pha trước token đầu —
 * máy chủ đang truy chương/thư viện để dựng ngữ cảnh (`build_context`). Khi có
 * cờ tìm web ở frontend, truyền `webSearch: true`.
 */

export type CompanionState =
  | "idle"
  | "hover"
  | "listening"
  | "thinking"
  | "searching"
  | "writing"
  | "answering"
  | "success"
  | "error"
  | "offline";

export const COMPANION_STATES: readonly CompanionState[] = [
  "idle", "hover", "listening", "thinking", "searching", "writing", "answering", "success", "error", "offline",
];

export type CompanionMode = "general" | "story" | "writer" | "support";

export interface CompanionInput {
  /** `availability` của trợ lý: `null` = chưa biết, `false`/`{enabled:false}` = không có AI. */
  available: boolean | null;
  /** `navigator.onLine === false`. */
  networkOffline: boolean;
  /** Panel/`/assistant` đang mở (người dùng đang ở trong trợ lý). */
  open: boolean;
  streaming: boolean;
  /** Đã có ít nhất một token của lượt đang stream. */
  hasStreamText: boolean;
  mode: CompanionMode | string;
  /** Mã lỗi của lượt vừa rồi (`AiProvider.error.code`), `null` nếu không lỗi. */
  errorCode: string | null;
  /** Con trỏ đang ở trên linh vật (chỉ ở vị trí "nhà"). */
  hovering: boolean;
  /** Đặt bởi component khi một lượt vừa XONG trọn vẹn (`done` + `status:"complete"`). */
  flash: "success" | null;
  /** Lượt đang chạy có tìm web (chưa có trong V1 — để sẵn chỗ nối). */
  webSearch?: boolean;
}

/** Lỗi nghĩa là "không có AI để hỏi" → linh vật nghỉ (offline), không phải "bối rối" (error). */
const OFFLINE_CODES = new Set(["network_error", "ai_not_enabled", "disabled_by_admin", "ai_no_provider"]);

export function isOfflineError(code: string | null | undefined): boolean {
  return !!code && OFFLINE_CODES.has(code);
}

/**
 * Trạng thái linh vật cho MỘT ảnh chụp trạng thái trợ lý. Thứ tự ưu tiên:
 * không có AI → đang stream → lỗi → vừa xong → hover → mở → nghỉ.
 */
export function mapCompanionState(i: CompanionInput): CompanionState {
  if (i.available === false || i.networkOffline) return "offline";
  if (i.streaming) {
    if (!i.hasStreamText) return i.webSearch || i.mode === "story" ? "searching" : "thinking";
    return i.mode === "writer" ? "writing" : "answering";
  }
  if (i.open && i.errorCode) return isOfflineError(i.errorCode) ? "offline" : "error";
  if (i.flash === "success") return "success";
  if (i.hovering && !i.open) return "hover";
  if (i.open) return "listening";
  return "idle";
}

/** Trạng thái phát MỘT lần rồi trở về trạng thái nền (runtime tự chuyển theo `after`). */
export function isOnceState(s: CompanionState): boolean {
  return s === "success" || s === "hover";
}

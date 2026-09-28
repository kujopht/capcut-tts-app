/**
 * Cấu hình Sentry phía web (project Sentry `fanfic-web`) — đọc lúc BUILD, TẮT mặc định.
 *
 * `NEXT_PUBLIC_SENTRY_DSN` rỗng (mặc định) = không gắn trình nghe nào, không tải SDK, không gửi
 * gì. DSN là toạ độ CÔNG KHAI của Sentry (được thiết kế để nằm trong trình duyệt) — không phải
 * token; token Sentry không bao giờ tới web.
 *
 * Môi trường KHÔNG BAO GIỜ tự suy ra `production`: thiếu `NEXT_PUBLIC_SENTRY_ENV` thì là
 * `development`. Chỉ bước build production đặt `production` — việc bật do chủ dự án làm, xem
 * `docs/observability/SENTRY.md`.
 */
export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || "";
export const SENTRY_ENV = process.env.NEXT_PUBLIC_SENTRY_ENV || "development";
export const BUILD_SHA = process.env.NEXT_PUBLIC_BUILD_SHA || "unknown";

/** Ít ồn: tối đa ngần này sự kiện MỖI lần tải trang, mỗi chữ ký lỗi gửi một lần. */
export const TRAN_SU_KIEN_MOI_TRANG = 10;

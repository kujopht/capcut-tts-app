/**
 * Ngữ cảnh AN TOÀN gửi kèm câu hỏi hỗ trợ — chỉ đủ để máy chủ biết kiểm tra gì.
 *
 * GỬI: đường dẫn (không query), bản build web, mã truyện/chương nếu có, chế độ
 * đọc, họ trình duyệt, loại thiết bị, cỡ khung nhìn, mã lỗi cuối đã làm sạch.
 * KHÔNG GỬI: token/cookie, UserSig chat, email, header, stack thô, URL ký.
 */
import { duongDanAnToan, maLoi } from "./sanitize";

export type SupportContext = {
  route: string;
  build: string;
  novel_id?: string;
  chapter_id?: string;
  reader_mode?: string;
  browser: string;
  device: string;
  viewport: string;
  last_error_code?: string;
};

export const BUILD_SHA = process.env.NEXT_PUBLIC_BUILD_SHA || "unknown";

export function hoTrinhDuyet(ua = typeof navigator === "undefined" ? "" : navigator.userAgent): string {
  const u = ua.toLowerCase();
  if (u.includes("coc_coc") || u.includes("coccoc")) return "coc_coc";
  if (u.includes("samsungbrowser")) return "samsung";
  if (u.includes("edg/")) return "edge";
  if (u.includes("opr/") || u.includes("opera")) return "opera";
  if (u.includes("firefox/")) return "firefox";
  if (u.includes("chrome/") || u.includes("crios/")) return "chrome";
  if (u.includes("safari/")) return "safari";
  return "other";
}

export function loaiThietBi(): string {
  if (typeof window === "undefined") return "other";
  const w = window.innerWidth;
  return w <= 640 ? "mobile" : w <= 1024 ? "tablet" : "desktop";
}

const ID = /^[A-Za-z0-9_-]{1,64}$/;

export function layBoiCanh(them: Partial<SupportContext> = {}): SupportContext {
  const route = duongDanAnToan(them.route ?? (typeof location === "undefined" ? "/" : location.pathname));
  const kq: SupportContext = {
    route,
    build: BUILD_SHA,
    browser: hoTrinhDuyet(),
    device: loaiThietBi(),
    viewport: typeof window === "undefined" ? "" : `${window.innerWidth}x${window.innerHeight}`,
  };
  const nid = them.novel_id ?? route.match(/^\/novels\/([^/]+)/)?.[1];
  const cid = them.chapter_id ?? route.match(/^\/chapters\/([^/]+)/)?.[1];
  if (nid && ID.test(nid)) kq.novel_id = nid;
  if (cid && ID.test(cid)) kq.chapter_id = cid;
  if (them.reader_mode && ["read", "listen", "read_listen"].includes(them.reader_mode)) kq.reader_mode = them.reader_mode;
  const ma = maLoi(them.last_error_code);
  if (ma) kq.last_error_code = ma;
  return kq;
}

/** Mã phiên NGẪU NHIÊN của tab (khách dùng để xem lại báo cáo của chính mình). */
export function phienHoTro(): string {
  const KHOA = "fanfic.support.sid";
  try {
    const cu = sessionStorage.getItem(KHOA);
    if (cu && /^[A-Za-z0-9_-]{16,64}$/.test(cu)) return cu;
    const b = new Uint8Array(12);
    crypto.getRandomValues(b);
    const moi = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem(KHOA, moi);
    return moi;
  } catch {
    return "khongluuduoc" + Math.random().toString(36).slice(2, 14).padEnd(12, "0");
  }
}

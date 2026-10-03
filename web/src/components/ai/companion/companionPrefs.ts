/**
 * Tuỳ chọn linh vật của NGƯỜI DÙNG trên trình duyệt này: ẩn hẳn / giảm chuyển
 * động. Lưu localStorage (mọi truy cập bọc try/catch — trình duyệt chặn lưu trữ
 * thì coi như mặc định), phát sự kiện `fas:ai-companion-prefs` để mọi linh vật
 * đang mở (panel nổi + `/assistant`) đổi ngay mà không cần tải lại trang.
 *
 * `prefers-reduced-motion` của hệ điều hành LUÔN thắng: tắt "giảm chuyển động"
 * ở đây không bật lại hoạt ảnh cho người đã yêu cầu giảm ở cấp hệ thống.
 */
import { useEffect, useState } from "react";

export interface CompanionPrefs {
  hidden: boolean;
  reducedMotion: boolean;
  /**
   * Chỗ đứng NGƯỜI DÙNG đã đặt cho linh vật nổi (desktop): độ dịch ngang, tính bằng px, so với vị trí nhà mặc định cạnh nút mở
   * trợ lý (luôn ≤ 0: sang trái; linh vật không bao giờ đứng đè nút mở). `null` = mặc định. Chỉ là SỞ THÍCH — mỗi lần dùng đều được
   * kẹp lại theo bố cục hiện tại, nên một giá trị cũ/hỏng không bao giờ đưa linh vật ra ngoài màn hình hay vào vùng cấm.
   */
  homeX: number | null;
}

const KEY = "fas.aiCompanion.v1";
const EVENT = "fas:ai-companion-prefs";
const DEFAULTS: CompanionPrefs = { hidden: false, reducedMotion: false, homeX: null };
/** Cận cứng của `homeX` đọc từ lưu trữ: rộng hơn mọi màn hình thật, đủ để loại giá trị rác (NaN, ±Infinity, 1e9). */
export const HOME_X_MIN = -8000;

/** `homeX` hợp lệ (số hữu hạn, ≤ 0, làm tròn) hoặc `null`. */
export function sanitizeHomeX(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const x = Math.round(value);
  if (x > 0 || x < HOME_X_MIN) return null;
  return x === 0 ? null : x;
}

export function readCompanionPrefs(): CompanionPrefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const v = JSON.parse(raw) as Partial<CompanionPrefs>;
    return { hidden: v.hidden === true, reducedMotion: v.reducedMotion === true, homeX: sanitizeHomeX(v.homeX) };
  } catch {
    return DEFAULTS;
  }
}

export function writeCompanionPrefs(patch: Partial<CompanionPrefs>): CompanionPrefs {
  const next = { ...readCompanionPrefs(), ...patch };
  next.homeX = sanitizeHomeX(next.homeX);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* không lưu được — vẫn áp cho phiên này qua sự kiện */
  }
  try {
    window.dispatchEvent(new CustomEvent<CompanionPrefs>(EVENT, { detail: next }));
  } catch {
    /* môi trường không có window (SSR) */
  }
  return next;
}

export function useCompanionPrefs(): [CompanionPrefs, (patch: Partial<CompanionPrefs>) => void] {
  const [prefs, setPrefs] = useState<CompanionPrefs>(DEFAULTS);
  useEffect(() => {
    const sync = () => setPrefs(readCompanionPrefs());
    sync();
    const onEvent = (e: Event) => setPrefs((e as CustomEvent<CompanionPrefs>).detail ?? readCompanionPrefs());
    window.addEventListener(EVENT, onEvent);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVENT, onEvent);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return [prefs, (patch) => setPrefs(writeCompanionPrefs(patch))];
}

/** `prefers-reduced-motion: reduce` của hệ điều hành, cập nhật khi đổi. */
export function useSystemReducedMotion(): boolean {
  const [v, setV] = useState(false);
  useEffect(() => {
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    } catch {
      return;
    }
    const on = () => setV(!!mq?.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq?.removeEventListener("change", on);
  }, []);
  return v;
}

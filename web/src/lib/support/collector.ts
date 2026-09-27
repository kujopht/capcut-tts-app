/**
 * Bộ thu lỗi client của Fanfic AI Support — NHẸ, CHỈ THEO SỰ KIỆN.
 *
 * Không `setInterval`, không thăm dò: trang không lỗi thì KHÔNG có request nào.
 * Có lỗi thì gom lại (hẹn 4 giây), lọc trùng theo chữ ký, rồi gửi một lô.
 *
 * Giới hạn cứng (đổi ở đây là đổi hành vi — có test canh):
 *   * mỗi chữ ký lỗi gửi TỐI ĐA MỘT LẦN mỗi lần tải trang;
 *   * hàng đợi tối đa 20 mục, mỗi lô tối đa 10 sự kiện, payload ≤ 8 KB;
 *   * tối đa 3 lô mỗi lần tải trang — sau đó chỉ nhớ mã lỗi cuối cho ngữ cảnh.
 *
 * Tắt (`SUPPORT_ENABLED` false) thì `caiBoThuLoi()` không gắn gì và `ghiLoi()`
 * không làm gì.
 */
import { API_BASE, getToken } from "@/lib/api";
import { SUPPORT_ENABLED } from "@/lib/features";
import { BUILD_SHA, hoTrinhDuyet, loaiThietBi, phienHoTro } from "./context";
import { duongDanAnToan, maLoi, sachChuoi } from "./sanitize";

export type LoaiLoi = "js_error" | "unhandled_rejection" | "api_error" | "media_error" | "render_error";

type SuKien = { kind: LoaiLoi; code: string; message: string; route: string; build: string; browser: string; device: string };

export const GIOI_HAN = { hangDoi: 20, moiLo: 10, soLo: 3, byte: 8000, henMs: 4000 } as const;

const daGui = new Set<string>();
const hangDoi = new Map<string, SuKien>();
let hen: ReturnType<typeof setTimeout> | null = null;
let soLoDaGui = 0;
let maCuoi = "";
let daCai = false;

export function maLoiCuoi(): string {
  return maCuoi;
}

export function ghiLoi(e: { kind: LoaiLoi; code: string; message?: string; route?: string }): void {
  if (!SUPPORT_ENABLED || typeof window === "undefined") return;
  const code = maLoi(e.code) || e.kind;
  maCuoi = code;
  const ev: SuKien = {
    kind: e.kind,
    code,
    message: sachChuoi(e.message ?? code, 300),
    route: duongDanAnToan(e.route ?? location.pathname),
    build: BUILD_SHA,
    browser: hoTrinhDuyet(),
    device: loaiThietBi(),
  };
  // Chu ky THO (so/id da bi may chu chuan hoa) — du de khong gui lai cung mot loi.
  const chuKy = `${ev.kind}|${ev.code}|${ev.route}|${ev.message.replace(/\d+/g, "#").slice(0, 80)}`;
  if (daGui.has(chuKy) || hangDoi.has(chuKy) || hangDoi.size >= GIOI_HAN.hangDoi || soLoDaGui >= GIOI_HAN.soLo) return;
  hangDoi.set(chuKy, ev);
  if (!hen) hen = setTimeout(() => void guiLo(), GIOI_HAN.henMs);
}

async function guiLo(): Promise<void> {
  hen = null;
  if (!hangDoi.size || soLoDaGui >= GIOI_HAN.soLo) return;
  const lo: SuKien[] = [];
  for (const [k, v] of hangDoi) {
    if (lo.length >= GIOI_HAN.moiLo) break;
    lo.push(v);
    daGui.add(k);
    hangDoi.delete(k);
  }
  let than = JSON.stringify({ session_id: phienHoTro(), events: lo });
  while (than.length > GIOI_HAN.byte && lo.length > 1) {
    lo.pop();
    than = JSON.stringify({ session_id: phienHoTro(), events: lo });
  }
  soLoDaGui += 1;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  try {
    // `fetch` thang, KHONG qua `request()` cua api.ts: loi khi gui bao cao loi
    // khong duoc tu ghi lai thanh mot loi moi (vong lap).
    await fetch(`${API_BASE}/api/support/client-errors`, { method: "POST", headers, body: than, keepalive: true });
  } catch {
    /* im lang — bo thu loi khong bao gio duoc lam phien nguoi dung */
  }
  if (hangDoi.size && soLoDaGui < GIOI_HAN.soLo) hen = setTimeout(() => void guiLo(), GIOI_HAN.henMs);
}

/** Gắn trình nghe `error`/`unhandledrejection` MỘT lần. Tắt cờ thì không gắn gì. */
export function caiBoThuLoi(): void {
  if (!SUPPORT_ENABLED || daCai || typeof window === "undefined") return;
  daCai = true;
  window.addEventListener("error", (e) => {
    // Chi loi CUA TRANG: bo loi tu tien ich trinh duyet va tep khac nguon.
    const nguon = (e as ErrorEvent).filename || "";
    if (nguon && !nguon.startsWith(location.origin)) return;
    const msg = (e as ErrorEvent).message || "";
    if (/ResizeObserver loop/i.test(msg)) return;
    ghiLoi({ kind: "js_error", code: "js_error", message: msg });
  });
  window.addEventListener("unhandledrejection", (e) => {
    const r = (e as PromiseRejectionEvent).reason;
    ghiLoi({ kind: "unhandled_rejection", code: "unhandled_rejection", message: r instanceof Error ? r.message : String(r ?? "") });
  });
}

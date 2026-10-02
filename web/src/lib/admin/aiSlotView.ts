/**
 * `/admin/ai` — định dạng hiển thị của MỘT slot (độ trễ, hạn mức miễn phí, endpoint). Hàm THUẦN, không DOM, không mạng:
 * test thẳng bằng `node --test` (xem `web/tests/admin-ai-alibaba.test.mjs`). Không tên provider nào viết cứng ở đây — nhãn,
 * tên biến môi trường và quy tắc đều đến từ `meta`/`health` của server.
 */
import type { AiFreeQuotaState, AiLatencyStat, AiSlotLatency, AiSlotQuota } from "./aiControl";

export function dinhDangMs(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? `${n.toLocaleString("vi-VN")} ms` : "—";
}

function mucDoTre(nhan: string, s: AiLatencyStat): string {
  if (s.p50 === null && s.p95 === null) return `${nhan} —`;
  return `${nhan} p50 ${dinhDangMs(s.p50)} · p95 ${dinhDangMs(s.p95)} · gần nhất ${dinhDangMs(s.last)}`;
}

/** Một dòng tóm tắt độ trễ: TTFT (tới token chữ đầu) và tổng, cùng số mẫu; `chưa có số liệu` khi chưa có lượt nào. */
export function moTaDoTre(l: AiSlotLatency | undefined): string {
  if (!l || l.samples === 0) return "chưa có số liệu (đo ở các lượt thật và lần Kiểm tra, giữ trong tiến trình)";
  const thongKe = `${l.samples} mẫu, ${l.ok} thành công${l.probe_samples ? `, ${l.probe_samples} lần Kiểm tra` : ""}`;
  return `${mucDoTre("TTFT", l.ttft_ms)} · ${mucDoTre("tổng", l.total_ms)} (${thongKe})`;
}

const NHAN_HAN_MUC: Record<AiFreeQuotaState, { nhan: string; lop: string }> = {
  none: { nhan: "Chưa nhập", lop: "tt-trong" },
  active: { nhan: "Còn hạn mức", lop: "tt-duyet" },
  expiring: { nhan: "Sắp hết hạn", lop: "tt-cho" },
  expired: { nhan: "Đã hết hạn", lop: "tt-tuchoi" },
  exhausted: { nhan: "Hết hạn mức", lop: "tt-tuchoi" },
};

export function nhanHanMuc(q: AiSlotQuota | undefined): { nhan: string; lop: string } {
  return NHAN_HAN_MUC[q?.state ?? "none"] ?? NHAN_HAN_MUC.none;
}

/** Có gì để hiện ở dòng "Hạn mức miễn phí" không (siêu dữ liệu, khoá chỉ-miễn-phí, hoặc nhà cung cấp báo hết hôm nay). */
export function coThongTinHanMuc(q: AiSlotQuota | undefined): boolean {
  return !!q && (q.state !== "none" || q.only || q.provider_exhausted_today);
}

/** `max-age` thuần: "3 ngày còn lại" / "đã quá 2 ngày"; `null` khi không có hạn. */
export function moTaHanDung(q: AiSlotQuota | undefined): string | null {
  if (!q || q.days_left === null || q.expires_at === null) return null;
  const ngay = Math.abs(q.days_left);
  return q.days_left < 0 ? `đã quá ${ngay} ngày` : `còn ${ngay} ngày`;
}

const LY_DO_KHOA: Record<string, string> = {
  expired: "hạn mức miễn phí đã quá hạn",
  stale: "số liệu quá cũ hoặc thiếu dấu thời gian — nhập lại số dư từ trang nhà cung cấp",
  unverifiable: "không đọc được lượng đã dùng từ sổ sử dụng",
  exhausted: "hết số dư ước tính (đã trừ dự phòng 5%)",
};

/** Lý do khoá "chỉ dùng hạn mức miễn phí" đang chặn slot; `null` khi không chặn. */
export function moTaKhoaChan(q: AiSlotQuota | undefined): string | null {
  if (!q || !q.lock_block) return null;
  return LY_DO_KHOA[q.lock_block] ?? q.lock_block;
}

/** "Ước còn X token (đã trừ Y token slot đã phục vụ từ lúc nhập)"; `null` khi không ước tính được. */
export function moTaUocTinh(q: AiSlotQuota | undefined): string | null {
  if (!q || q.estimated_remaining === null || q.consumed_since_snapshot === null) return null;
  return `ước còn ${q.estimated_remaining.toLocaleString("vi-VN")} token (đã trừ ${q.consumed_since_snapshot.toLocaleString("vi-VN")} token slot đã phục vụ từ lúc nhập)`;
}

/** Máy chủ (không đường dẫn) của endpoint — cho Owner thấy slot đang trỏ vùng nào mà không in cả URL. */
export function hostCuaEndpoint(url: string | undefined): string {
  try {
    return url ? new URL(url).host : "—";
  } catch {
    return "—";
  }
}

const pad = (n: number): string => String(n).padStart(2, "0");

/** ISO-8601 có múi giờ → giá trị cho `<input type="datetime-local">` (GIỜ ĐỊA PHƯƠNG, đến phút). Rỗng/sai → "". */
export function isoSangDatetimeLocal(iso: string | undefined | null): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  return `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}T${pad(t.getHours())}:${pad(t.getMinutes())}`;
}

/** Giá trị `datetime-local` (giờ địa phương) → ISO-8601 UTC mà máy chủ nhận (nó đòi múi giờ tường minh). Rỗng/sai → "". */
export function datetimeLocalSangIso(local: string): string {
  if (!local) return "";
  const t = new Date(local);
  return Number.isNaN(t.getTime()) ? "" : t.toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

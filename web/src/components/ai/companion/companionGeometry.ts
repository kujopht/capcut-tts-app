/**
 * Hình học THUẦN cho linh vật nổi trên desktop: chỗ ngồi trên mép panel AI.
 *
 * Hệ toạ độ: runtime Ink Scout dịch chuyển host bằng `translate(x, y)` tính từ
 * vị trí "nhà" (host đặt `position: fixed` cạnh nút mở trợ lý). Hàm này trả về
 * độ dịch cần để host ngồi lên mép TRÊN của panel — NGOÀI panel, nên không bao
 * giờ che chữ, nút Gửi hay nút Đóng — hoặc `null` khi không có chỗ an toàn
 * (thì linh vật ẩn đi trong lúc panel mở, không đứng đè lên panel).
 */

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface SeatInput {
  /** Hộp của host ở vị trí nhà (chưa dịch). */
  home: Rect;
  /** Hộp của `.ai-panel`. */
  panel: Rect;
  /** Đáy thanh điều hướng — linh vật không bao giờ lên trên mốc này. */
  navBottom: number;
  viewportWidth: number;
  /** Cạnh linh vật (px). */
  size: number;
}

export interface Seat {
  x: number;
  y: number;
  /** "top": ngồi trên mép trên panel; "side": đứng cạnh trái panel. */
  where: "top" | "side";
}

const GAP = 8;
/**
 * Phần canvas trong suốt dưới chân nhân vật đứng — chân chạm mép panel. Nhỏ vì
 * `sit-down` của runtime tự hạ thêm 19% cỡ khi ngồi (linh vật nằm DƯỚI panel
 * theo z-index, nên phần chồng bị panel che — không đè lên chữ/nút — nhưng
 * chồng nhiều quá thì khuất mất thân, đo QA 2026-10-01).
 */
const FOOT_OVERLAP = 0.06;

export function computeSeat({ home, panel, navBottom, viewportWidth, size }: SeatInput): Seat | null {
  // 1) Mép trên panel, sát góc trái (xa nút Đóng ở góc phải).
  const topLeft = panel.left + 12;
  const topTop = panel.top - size + size * FOOT_OVERLAP;
  if (topTop >= navBottom + GAP && topLeft + size <= panel.left + panel.width) {
    return { x: topLeft - home.left, y: topTop - home.top, where: "top" };
  }
  // 2) Không đủ chỗ phía trên (màn thấp): đứng cạnh TRÁI panel, ngang đầu panel.
  const sideLeft = panel.left - size - GAP;
  const sideTop = Math.max(panel.top, navBottom + GAP);
  if (sideLeft >= GAP && sideLeft + size <= viewportWidth) {
    return { x: sideLeft - home.left, y: sideTop - home.top, where: "side" };
  }
  return null;
}

/** Biên cho `runtime.setBounds` — đủ rộng để tới chỗ ngồi, không cho ra khỏi màn hình. */
export function boundsFor(home: Rect, viewportWidth: number, navBottom: number) {
  return {
    left: -home.left + GAP,
    right: Math.max(0, viewportWidth - home.left - home.width - GAP),
    top: -(home.top - navBottom - GAP),
    bottom: 0,
  };
}

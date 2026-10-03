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

/**
 * Biên cho `runtime.setBounds` — đủ rộng để tới chỗ ngồi và để NGƯỜI DÙNG kéo thả, không cho ra khỏi màn hình.
 *
 * `right: 0`: linh vật chỉ được đi sang TRÁI vị trí nhà (nhà nằm ngay trái nút mở trợ lý). Nhờ vậy dù kéo hay thả ở đâu, nó cũng
 * không bao giờ chui xuống dưới nút mở trợ lý / Chat Dock ở góc phải (những lớp có z-index cao hơn nó). `top`: không bao giờ
 * lên trên đáy thanh điều hướng.
 */
export function boundsFor(home: Rect, _viewportWidth: number, navBottom: number) {
  return {
    left: -home.left + GAP,
    right: 0,
    top: -(home.top - navBottom - GAP),
    bottom: 0,
  };
}

/** Biên cho linh vật INLINE (`/assistant`): trong dải nội dung của chính nó — kéo ngang cả bề rộng, nhấc lên một đoạn ngắn. */
export function inlineBoundsFor(stage: Rect, size: number) {
  const slack = Math.max(0, stage.width - size);
  return { left: -slack / 2, right: slack / 2, top: -Math.round(size * 0.6), bottom: 0 };
}

/**
 * Mặt phẳng để linh vật ĐÁP LÊN (HANDOFF §5): chỉ mép TRÊN của panel khi có chỗ ngồi kiểu "top". `y` = top-left canvas khi chân
 * chạm mép panel — đúng `seat.y`, nên nhảy-lên-panel và rơi-xuống-panel cho cùng một độ cao.
 */
export function panelSurfaces(seat: Seat | null, panel: Rect | null, home: Rect): Array<{ left: number; right: number; y: number }> {
  if (!seat || !panel || seat.where !== "top") return [];
  return [{ left: panel.left - home.left, right: panel.left + panel.width - home.left, y: seat.y }];
}

/** Hộp THÂN của linh vật (trừ phần trong suốt quanh nhân vật) trong toạ độ viewport, cho vị trí runtime `(x, y)`. */
export function mascotBody(home: Rect, x: number, y: number, size: number): Rect {
  return { left: home.left + x + size * 0.2, top: home.top + y + size * 0.1, width: size * 0.6, height: size * 0.86 };
}

export function rectsIntersect(a: Rect, b: Rect, pad = 0): boolean {
  return a.left < b.left + b.width + pad && a.left + a.width > b.left - pad && a.top < b.top + b.height + pad && a.top + a.height > b.top - pad;
}

export type LandingVerdict =
  /** Đáp lên mép trên panel: hợp lệ, trở thành "chỗ ngồi". */
  | { kind: "seat" }
  /** Đứng trên sàn ở chỗ hợp lệ: được NHỚ làm vị trí nhà mới (độ dịch ngang `x`). */
  | { kind: "floor"; x: number }
  /** Rơi vào vùng cấm (panel / nút mở / Chat Dock / thanh phát): phải được đưa tới chỗ an toàn. */
  | { kind: "rescue"; to: "seat" | "home" };

export interface LandingInput {
  /** Vị trí runtime sau khi đáp (so với gốc host). */
  x: number;
  y: number;
  size: number;
  home: Rect;
  seat: Seat | null;
  /** Mọi hộp mà linh vật không được nằm đè lên (đã loại những cái không hiện). */
  protectedRects: Rect[];
}

/**
 * Phán xử nơi NGƯỜI DÙNG thả linh vật. Thứ tự: đáp đúng mép trên panel → chỗ ngồi; thân chồng lên vùng cấm → cứu (về chỗ ngồi nếu
 * panel đang mở và có chỗ, ngược lại về nhà); còn lại → sàn hợp lệ. Thuần túy — toàn bộ quyết định "không che nút Gửi/Đóng/Điều hướng"
 * nằm ở đây và được `node --test` khoá lại.
 */
export function judgeLanding({ x, y, size, home, seat, protectedRects }: LandingInput): LandingVerdict {
  if (seat && seat.where === "top" && Math.abs(y - seat.y) < 6) return { kind: "seat" };
  const body = mascotBody(home, x, y, size);
  if (protectedRects.some((r) => rectsIntersect(body, r, 2))) return { kind: "rescue", to: seat ? "seat" : "home" };
  return { kind: "floor", x: Math.round(x) };
}

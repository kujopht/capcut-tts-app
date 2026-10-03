/**
 * Hằng số cân chỉnh của Ink Scout: The Lost Chapter. TOÀN BỘ đơn vị là pixel nội bộ (384×216) và khung hình (bước cố định 60 Hz).
 * Số liệu dẫn xuất (độ cao nhảy, tầm nhảy, tầm lướt) được `ink-scout-core.test.mjs` đo lại bằng chính mô phỏng — đổi một hằng số
 * mà làm vỡ thiết kế phòng (khe hở cần Margin Step, bậc thang cần nhảy) thì test bắt ngay.
 */

export const TICK_RATE = 60;
/** Bước mô phỏng cố định, giây. */
export const TICK_DT = 1 / TICK_RATE;
export const TILE = 16;
/** Độ phân giải nội bộ: 384×216 (24×13,5 ô). Canvas vẽ ở đúng độ phân giải này rồi phóng nguyên bằng CSS (nearest-neighbor). */
export const VIEW_W = 384;
export const VIEW_H = 216;

export const PLAYER = {
  /** Hộp va chạm: gốc = giữa chân. */
  w: 8,
  h: 16,
  maxRun: 1.65,
  groundAccel: 0.24,
  groundDecel: 0.3,
  airAccel: 0.17,
  airDecel: 0.05,
  /** Quay đầu nhanh: nhân gia tốc khi nhấn ngược chiều đang chạy. */
  turnBoost: 1.6,
  gravityUp: 0.32,
  gravityDown: 0.44,
  maxFall: 5.2,
  jumpVel: 6.2,
  /** Nhả nút nhảy khi còn đang bay lên → cắt vận tốc lên còn mức này (nhảy thấp có kiểm soát). */
  jumpCut: 2.1,
  coyoteFrames: 6,
  jumpBufferFrames: 7,
  maxHp: 5,
  maxInk: 9,
  invulnFrames: 60,
  hurtFrames: 14,
  knockbackX: 2.6,
  knockbackY: -2.6,
  /** Margin Step. */
  dashSpeed: 5.4,
  dashFrames: 10,
  dashCooldown: 16,
  /** Số khung đầu của lướt là bất khả xâm phạm (né đòn boss). */
  dashInvuln: 7,
  /** Sau lướt, giữ lại một phần vận tốc ngang (mượt khi nối vào nhảy). */
  dashExitSpeed: 2.4,
} as const;

/** Glyph Blade. Mọi số là khung hình. `hit` = [khung bắt đầu, khung kết thúc] trong đó hộp đòn có hiệu lực. */
export const BLADE = {
  g1: { total: 15, hit: [3, 6] as const, damage: 1, lunge: 0.7, box: { dx: 3, dy: -15, w: 22, h: 14 } },
  g2: { total: 15, hit: [3, 6] as const, damage: 1, lunge: 0.7, box: { dx: 3, dy: -15, w: 24, h: 14 } },
  g3: { total: 24, hit: [4, 9] as const, damage: 2, lunge: 1.1, box: { dx: 2, dy: -17, w: 28, h: 18 } },
  air: { total: 16, hit: [3, 8] as const, damage: 1, lunge: 0, box: { dx: 2, dy: -16, w: 24, h: 16 } },
  dash: { total: 10, hit: [0, 10] as const, damage: 2, lunge: 0, box: { dx: -2, dy: -15, w: 30, h: 14 } },
  /** Cửa sổ nhấn thêm đòn để nối combo: [từ khung, tới khung] của đòn hiện tại. */
  comboWindow: [4, 15] as const,
  hitStop: 3,
  hitStopHeavy: 5,
  inkPerHit: 1,
} as const;

export const PULSE = {
  cost: 3,
  /** Memory III: Pulse rẻ hơn. */
  costMemory3: 2,
  windup: 6,
  expandFrames: 14,
  radius: 56,
  /** Memory II mở rộng bán kính. */
  radiusMemory2: 80,
  stunFrames: 120,
  stunFramesElite: 60,
  glyphRevealFrames: 480,
  lockFrames: 18,
} as const;

export const HITSTOP_PLAYER_HURT = 5;
/** Số khung bất tử của boss giữa các giai đoạn. */
export const FALL_DEATH_MARGIN = 40;

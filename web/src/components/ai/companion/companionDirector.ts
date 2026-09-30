/**
 * Điều phối runtime Ink Scout: TRẠNG THÁI MỚI NHẤT THẮNG, không cắt ngang di chuyển.
 *
 * Vì sao cần: `runtime.setState()` HUỶ chuyển động đang chạy (`cancelMotion`),
 * nên gọi thẳng `setState` mỗi lần React render sẽ để linh vật lơ lửng giữa
 * đường nhảy. Director giữ HAI giá trị "mong muốn" (trạng thái + chỗ đứng), chạy
 * MỘT vòng lặp tuần tự: chuyển động xong mới áp trạng thái; yêu cầu mới trong lúc
 * bận chỉ GHI ĐÈ giá trị mong muốn (không xếp hàng) → đổi trạng thái dồn dập chỉ
 * áp cái cuối cùng.
 *
 * Không DOM, không React: `RuntimeLike` là phần API của `ink-scout.js` được dùng
 * (test bằng runtime giả trong `web/tests/ai-companion.test.mjs`).
 */
import type { CompanionState } from "./companionState";

export interface RuntimeLike {
  setState(state: string): Promise<boolean>;
  transition(name: string, options?: Record<string, unknown>): Promise<{ cancelled?: boolean }>;
  setReducedMotion(value: boolean | null): Promise<unknown>;
  destroy(): void;
  applyPosition(): void;
  position: { x: number; y: number };
  readonly reducedMotion: boolean;
}

export type Place = { kind: "home" } | { kind: "seat"; x: number; y: number };

const HOME: Place = { kind: "home" };

function samePlace(a: Place, b: Place): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "home" || b.kind === "home") return true;
  return Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1;
}

export class CompanionDirector {
  private desired: CompanionState = "idle";
  private applied: CompanionState | "seated" | null = null;
  private place: Place = HOME;
  private target: Place | null = null;
  private running = false;
  private destroyed = false;
  private readonly rt: RuntimeLike;
  private readonly onError: (e: unknown) => void;

  // Không dùng "parameter property" của TS: test chạy file này trực tiếp bằng
  // chế độ strip-types của Node, vốn chỉ nhận cú pháp TS xoá-được.
  constructor(rt: RuntimeLike, onError: (e: unknown) => void = () => {}) {
    this.rt = rt;
    this.onError = onError;
  }

  get currentPlace(): Place {
    return this.place;
  }

  get busy(): boolean {
    return this.running;
  }

  /** Trạng thái mong muốn MỚI NHẤT (ghi đè; không xếp hàng). */
  setState(state: CompanionState): void {
    this.desired = state;
    void this.pump();
  }

  goHome(): void {
    this.target = HOME;
    void this.pump();
  }

  goSeat(x: number, y: number): void {
    this.target = { kind: "seat", x, y };
    void this.pump();
  }

  /**
   * Chỗ ngồi đổi vì bố cục (resize, Chat Dock mở). Đang ngồi yên → dời NGAY,
   * không phát hoạt ảnh; đang bận → coi như đích mới.
   */
  relocate(x: number, y: number): void {
    if (this.place.kind === "seat" && !this.running) {
      const dx = x - this.place.x, dy = y - this.place.y;
      this.rt.position = { x: this.rt.position.x + dx, y: this.rt.position.y + dy };
      this.rt.applyPosition();
      this.place = { kind: "seat", x, y };
    } else if (this.place.kind === "seat" || this.target?.kind === "seat") {
      this.goSeat(x, y);
    }
  }

  /** Runtime đã tự đổi trạng thái (ví dụ `success` phát xong → `after:"idle"`). */
  notifyRuntimeState(state: string): void {
    if (state !== this.applied) {
      this.applied = null;
      void this.pump();
    }
  }

  destroy(): void {
    this.destroyed = true;
    this.rt.destroy();
  }

  private async pump(): Promise<void> {
    if (this.running || this.destroyed) return;
    this.running = true;
    try {
      while (!this.destroyed) {
        const t = this.target;
        this.target = null;
        if (t && !samePlace(t, this.place)) {
          await this.move(t);
          continue;
        }
        const want = this.desired;
        // Đang ngồi trên panel và chỉ "lắng nghe" → giữ tư thế NGỒI (sit-down là
        // chuyển động có thật; setState sẽ bắt đứng dậy — runtime bỏ seatOffset).
        if (this.place.kind === "seat" && want === "listening" && !this.rt.reducedMotion) {
          if (this.applied !== "seated") {
            this.applied = "seated";
            await this.rt.transition("sit-down");
            continue;
          }
          break;
        }
        if (want !== this.applied) {
          this.applied = want;
          await this.rt.setState(want);
          continue;
        }
        break;
      }
    } catch (e) {
      this.applied = null;
      this.onError(e);
    } finally {
      this.running = false;
    }
  }

  private async move(t: Place): Promise<void> {
    const reduced = this.rt.reducedMotion;
    if (reduced) {
      // Giảm chuyển động: dời tức thì, không hoạt ảnh di chuyển (và không tải poster PNG).
      this.rt.position = t.kind === "seat" ? { x: t.x, y: t.y } : { x: 0, y: 0 };
      this.rt.applyPosition();
    } else if (t.kind === "seat") {
      await this.rt.transition("jump-onto-panel", { x: t.x, y: t.y });
    } else {
      if (this.applied === "seated") await this.rt.transition("stand-up");
      await this.rt.transition("return-home");
    }
    this.place = t;
    this.applied = null; // runtime kết thúc di chuyển ở idle/tư thế — áp lại trạng thái mong muốn
  }
}

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

/** = `companionState.isOnceState` (test khoá hai danh sách khớp nhau). Giữ bản sao ở đây vì
 *  file này chạy thẳng bằng strip-types của Node, vốn không phân giải import giá trị
 *  không đuôi `.ts` (import KIỂU thì được xoá nên không sao). */
const ONCE_STATES: ReadonlySet<string> = new Set(["success", "hover"]);

export interface RuntimeLike {
  setState(state: string): Promise<boolean>;
  transition(name: string, options?: Record<string, unknown>): Promise<{ cancelled?: boolean }>;
  setReducedMotion(value: boolean | null): Promise<unknown>;
  destroy(): void;
  applyPosition(): void;
  position: { x: number; y: number };
  /** "Nhà" của runtime (`return-home` đi tới đây). Mặc định `{0,0}`; người dùng có thể dời nó bằng kéo thả. */
  home: { x: number; y: number };
  readonly reducedMotion: boolean;
}

/** `free` = một chỗ KHÔNG xác định (người dùng vừa thả linh vật vào vùng cấm): không đích nào "đã ở đó", nên mọi đích đều di chuyển thật. */
export type Place = { kind: "home" } | { kind: "seat"; x: number; y: number } | { kind: "free" };

const HOME: Place = { kind: "home" };
const FREE: Place = { kind: "free" };

function samePlace(a: Place, b: Place): boolean {
  if (a.kind === "free" || b.kind === "free") return false;
  if (a.kind !== b.kind) return false;
  if (a.kind === "home" || b.kind === "home") return true;
  return Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1;
}

export class CompanionDirector {
  private desired: CompanionState = "idle";
  private applied: CompanionState | "seated" | null = null;
  /** Trạng thái MỘT-LẦN (success/hover) runtime đã phát xong và tự rời — không phát lại
   *  chừng nào trạng thái mong muốn còn là nó (review Codex #2: React chưa kịp đổi `desired`). */
  private consumed: CompanionState | null = null;
  private place: Place = HOME;
  private target: Place | null = null;
  private running = false;
  private destroyed = false;
  /**
   * NGƯỜI DÙNG đang cầm / thả linh vật (kéo thả). Trong lúc đó director KHÔNG ra lệnh gì cho runtime: `setState`/`transition` huỷ
   * chuyển động đang chạy, tức là giật linh vật khỏi tay người dùng. Thả xong (`hold(false)`) thì áp lại trạng thái/chỗ đứng MỚI NHẤT.
   */
  private held = false;
  /** `rehome()` được gọi lúc vòng lặp đang bận: dời nhà ngay khi nó rảnh. */
  private rehomePending = false;
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

  get isHeld(): boolean {
    return this.held;
  }

  /** Người dùng bắt đầu (`true`) / kết thúc (`false`) cầm linh vật. Kết thúc → chạy lại vòng lặp với yêu cầu mới nhất. */
  hold(value: boolean): void {
    if (this.held === value) return;
    this.held = value;
    if (!value) void this.pump();
  }

  /**
   * Chốt chỗ đứng sau khi người dùng THẢ: linh vật đã đứng yên ở đó (runtime tự kết thúc ở idle), nên director chỉ ghi nhận nơi ở
   * mới và áp lại trạng thái mong muốn. Không gọi `transition` (không có gì để di chuyển).
   */
  settle(place: Place): void {
    this.place = place;
    this.target = null;
    this.applied = null;
  }

  /**
   * "Nhà" (`rt.home`) vừa dời — vị trí người dùng đã nhớ được khôi phục lúc tải trang, cửa sổ thu nhỏ, "Đặt lại vị trí". Đang đứng nhà
   * thì dời NGAY (không hoạt ảnh), kể cả khi vòng lặp đang bận áp trạng thái: khi đó dời ngay lúc nó rảnh. (Trước đây nhánh "đang
   * bận" bỏ qua hẳn nên linh vật vẫn đứng ở nhà mặc định dù đã nhớ chỗ khác — lỗi chạy đua phụ thuộc nhịp tải, đo ở QA trình duyệt.)
   * Đang ở chỗ ngồi / bị cầm: lần về nhà kế tiếp (`return-home`) tự tới nhà mới, `settle()` chốt chỗ sau khi thả.
   */
  rehome(): void {
    if (this.destroyed) return;
    if (this.running) {
      this.rehomePending = true;
      return;
    }
    if (this.place.kind === "home" && !this.held) this.applyHome();
  }

  private applyHome(): void {
    const h = this.rt.home;
    if (this.rt.position.x === h.x && this.rt.position.y === h.y) return;
    this.rt.position = { x: h.x, y: h.y };
    this.rt.applyPosition();
  }

  /** Trạng thái mong muốn MỚI NHẤT (ghi đè; không xếp hàng). */
  setState(state: CompanionState): void {
    if (state !== this.desired) this.consumed = null;
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
    if (this.held) {
      // Người dùng đang cầm: không dời trực tiếp; ghi nhận đích mới, áp khi họ thả.
      if (this.place.kind === "seat" || this.target?.kind === "seat") this.target = { kind: "seat", x, y };
      return;
    }
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
      const prev = this.applied;
      if (prev && prev !== "seated" && ONCE_STATES.has(prev)) this.consumed = prev;
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
        if (this.held) break; // người dùng đang cầm: không giật linh vật khỏi tay họ
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
        if (want === this.consumed) break; // một-lần đã phát xong: chờ trạng thái mong muốn mới
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
      if (this.rehomePending) {
        this.rehomePending = false;
        if (!this.destroyed && !this.held && this.place.kind === "home") this.applyHome();
      }
    }
  }

  private async move(t: Place): Promise<void> {
    const reduced = this.rt.reducedMotion;
    if (reduced) {
      // Giảm chuyển động: dời tức thì, không hoạt ảnh di chuyển (và không tải poster PNG).
      this.rt.position = t.kind === "seat" ? { x: t.x, y: t.y } : { ...this.rt.home };
      this.rt.applyPosition();
    } else if (t.kind === "seat") {
      await this.rt.transition("jump-onto-panel", { x: t.x, y: t.y });
    } else {
      if (this.applied === "seated") await this.rt.transition("stand-up");
      await this.rt.transition("return-home");
    }
    // Người dùng cầm linh vật GIỮA lúc nó đang di chuyển (physics huỷ chuyển động đó): linh vật KHÔNG ở đích. Ghi nhận đích sẽ làm lần
    // `goHome`/`goSeat` kế tiếp coi như "đã ở đó" và không đi đâu; để "không xác định" tới khi người dùng thả (`settle` chốt chỗ thật).
    this.place = this.held ? FREE : t;
    this.applied = null; // runtime kết thúc di chuyển ở idle/tư thế — áp lại trạng thái mong muốn
  }
}

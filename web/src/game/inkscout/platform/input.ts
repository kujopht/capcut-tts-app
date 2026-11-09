import { NO_INPUT, type InputState } from "../core/types";

/**
 * Lớp trừu tượng đầu vào: bàn phím + nút chạm → một `InputState` mỗi bước mô phỏng. Mô phỏng chỉ biết "nút đang giữ"; cạnh lên/xuống do lõi tự tính.
 * Mọi bộ nghe sự kiện gắn ở `attach()` và gỡ hết ở `detach()` — không rò rỉ khi rời trang.
 */
export type ButtonName = "left" | "right" | "jump" | "attack" | "pulse" | "dash" | "confirm";

const KEYMAP: Readonly<Record<string, ButtonName>> = {
  ArrowLeft: "left",
  KeyA: "left",
  ArrowRight: "right",
  KeyD: "right",
  Space: "jump",
  ArrowUp: "jump",
  KeyW: "jump",
  KeyJ: "attack",
  KeyZ: "attack",
  KeyK: "pulse",
  KeyX: "pulse",
  ShiftLeft: "dash",
  ShiftRight: "dash",
  KeyL: "dash",
  Enter: "confirm",
  KeyE: "confirm",
};

/** Phím mà trình duyệt có thể dùng để cuộn trang: chặn mặc định khi game đang nhận đầu vào. */
const SWALLOW = new Set(["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);

export class InputSource {
  private readonly keys = new Set<ButtonName>();
  /** Mỗi nút chạm có thể do nhiều con trỏ giữ (chạm nhiều ngón). */
  private readonly touch = new Map<ButtonName, Set<number>>();
  private target: Window | null = null;
  private onPause: (() => void) | null = null;
  private onAnyKey: (() => void) | null = null;
  private readonly held = new Set<string>();
  /** Đặt `true` khi game đang nhận đầu vào (không phải menu). */
  active = false;
  /** Chỉ dùng cho QA/bot khi trang đặt `window.__INK_QA__ = true` trước khi tải game: thay hẳn nguồn đầu vào. */
  controller: (() => InputState) | null = null;

  attach(target: Window, hooks: { onPause: () => void; onAnyKey?: () => void }): void {
    this.detach();
    this.target = target;
    this.onPause = hooks.onPause;
    this.onAnyKey = hooks.onAnyKey ?? null;
    target.addEventListener("keydown", this.keydown);
    target.addEventListener("keyup", this.keyup);
    target.addEventListener("blur", this.releaseAll);
  }

  detach(): void {
    if (this.target) {
      this.target.removeEventListener("keydown", this.keydown);
      this.target.removeEventListener("keyup", this.keyup);
      this.target.removeEventListener("blur", this.releaseAll);
    }
    this.target = null;
    this.onPause = null;
    this.onAnyKey = null;
    this.releaseAll();
  }

  private readonly keydown = (e: KeyboardEvent): void => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // Đang gõ vào ô nhập: không bắt phím.
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    this.onAnyKey?.();
    // Enter/Space đang nằm trên một nút/liên kết/ô chọn của hộp thoại DOM thì để trình duyệt kích hoạt nó (không nuốt, không ánh xạ thành hành động game).
    if ((e.code === "Space" || e.code === "Enter") && t && (t.tagName === "BUTTON" || t.tagName === "A" || t.tagName === "SUMMARY" || (t.getAttribute?.("role") ?? "") === "radio")) return;
    if (e.code === "Escape" || e.code === "KeyP") {
      if (!e.repeat) this.onPause?.();
      e.preventDefault();
      return;
    }
    const b = KEYMAP[e.code];
    if (!b) return;
    if (this.active && SWALLOW.has(e.code)) e.preventDefault();
    if (this.active && (e.code === "Space" || e.code === "Enter")) e.preventDefault();
    this.held.add(e.code);
    this.keys.add(b);
  };

  private readonly keyup = (e: KeyboardEvent): void => {
    const b = KEYMAP[e.code];
    if (!b) return;
    this.held.delete(e.code);
    // Nút chỉ nhả khi KHÔNG còn phím nào khác cùng nút đang giữ (A + ← cùng trái).
    let still = false;
    for (const code of this.held) if (KEYMAP[code] === b) still = true;
    if (!still) this.keys.delete(b);
  };

  /** Nhả sạch mọi nút (mất tiêu điểm / mở menu / tạm dừng) — tránh "kẹt phím". */
  readonly releaseAll = (): void => {
    this.keys.clear();
    this.held.clear();
    this.touch.clear();
  };

  // ---- nút chạm
  press(button: ButtonName, pointerId: number): void {
    // Nút chạm cũng là cử chỉ người dùng: thử mở khoá âm thanh (trình duyệt di động có thể đã hết "cửa sổ cử chỉ" sau lúc tải bất đồng bộ).
    this.onAnyKey?.();
    let s = this.touch.get(button);
    if (!s) this.touch.set(button, (s = new Set()));
    s.add(pointerId);
  }

  release(button: ButtonName, pointerId: number): void {
    const s = this.touch.get(button);
    if (!s) return;
    s.delete(pointerId);
    if (s.size === 0) this.touch.delete(button);
  }

  releasePointer(pointerId: number): void {
    for (const [b, s] of this.touch) {
      s.delete(pointerId);
      if (s.size === 0) this.touch.delete(b);
    }
  }

  private down(b: ButtonName): boolean {
    return this.keys.has(b) || (this.touch.get(b)?.size ?? 0) > 0;
  }

  read(): InputState {
    if (!this.active) return NO_INPUT;
    if (this.controller) return this.controller();
    const left = this.down("left");
    const right = this.down("right");
    return {
      // Trái + phải cùng giữ thì triệt tiêu nhau (không ưu tiên bên nào).
      left: left && !right,
      right: right && !left,
      jump: this.down("jump"),
      attack: this.down("attack"),
      pulse: this.down("pulse"),
      dash: this.down("dash"),
      confirm: this.down("confirm"),
    };
  }
}

import type { GameEvent } from "../core/types";
import { C } from "./palette";

/**
 * Hạt hiệu ứng (chỉ để vẽ — không ảnh hưởng mô phỏng, nên dùng `Math.random` thoải mái). Có trần số hạt để một đợt hiệu ứng lớn không làm tụt khung hình.
 */
export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  g: number;
  life: number;
  max: number;
  color: string;
  size: number;
  /** "rect" (mặc định), "page" (mảnh giấy xoay), "ring". */
  kind: "rect" | "page" | "mote";
  rot: number;
  spin: number;
}

export interface Ghost {
  x: number;
  y: number;
  facing: 1 | -1;
  life: number;
}

const MAX_PARTICLES = 420;

function rnd(a: number, b: number): number {
  return a + Math.random() * (b - a);
}

export class FxSystem {
  readonly parts: Particle[] = [];
  /** Ảnh mờ sau khi lướt. */
  readonly ghosts: Ghost[] = [];
  flash = 0;
  flashColor = "#ffffff";
  shakeAmount = 0;
  shakeFrames = 0;
  private shakeTotal = 1;
  /** Tia cắt: một cung vẽ ngắn khi chém (do renderer đọc). */
  slashLife = 0;

  clear(): void {
    this.parts.length = 0;
    this.ghosts.length = 0;
    this.flash = 0;
    this.shakeAmount = 0;
    this.shakeFrames = 0;
    this.slashLife = 0;
  }

  shake(amount: number, frames: number): void {
    if (amount >= this.shakeAmount * (this.shakeFrames / this.shakeTotal)) {
      this.shakeAmount = amount;
      this.shakeFrames = frames;
      this.shakeTotal = Math.max(1, frames);
    }
  }

  /** Độ lệch rung hiện tại (đã nhân hệ số cài đặt). */
  shakeOffset(scale: number): { x: number; y: number } {
    if (this.shakeFrames <= 0 || scale <= 0) return { x: 0, y: 0 };
    const k = (this.shakeFrames / this.shakeTotal) * this.shakeAmount * scale;
    return { x: Math.round(rnd(-k, k)), y: Math.round(rnd(-k, k)) };
  }

  add(p: Partial<Particle> & { x: number; y: number }): void {
    if (this.parts.length >= MAX_PARTICLES) this.parts.shift();
    this.parts.push({
      vx: 0, vy: 0, g: 0, life: 30, max: 30, color: C.white, size: 1, kind: "rect", rot: 0, spin: 0, ...p,
    });
  }

  /** Chuyển một sự kiện mô phỏng thành hạt/ảnh/rung. */
  onEvent(e: GameEvent): void {
    switch (e.t) {
      case "shake":
        this.shake(e.amount, e.frames);
        break;
      case "fx":
        this.fx(e.name, e.x, e.y, e.dir ?? 0, e.n ?? 6, e.color);
        break;
      case "bossPhase":
        this.flash = 0.6;
        this.flashColor = C.crimsonLight;
        break;
      case "memory":
        this.flash = 0.45;
        this.flashColor = C.gold;
        break;
      case "ability":
        this.flash = 0.4;
        this.flashColor = C.cyanLight;
        break;
      default:
        break;
    }
  }

  private fx(name: string, x: number, y: number, dir: number, n: number, color?: string): void {
    switch (name) {
      case "spark":
        for (let i = 0; i < n; i += 1) {
          const a = rnd(-1.3, 1.3) + (dir < 0 ? Math.PI : 0);
          const s = rnd(0.8, 2.6);
          this.add({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 0.3, g: 0.08, life: rnd(8, 16), max: 16, color: color ?? (Math.random() < 0.5 ? C.white : C.cyanLight), size: 1 });
        }
        break;
      case "dust":
        for (let i = 0; i < n; i += 1) {
          this.add({ x: x + rnd(-3, 3), y: y - 1, vx: rnd(-0.5, 0.5), vy: rnd(-0.5, -0.1), g: -0.005, life: rnd(12, 22), max: 22, color: C.slate3, size: 2 });
        }
        break;
      case "inkSplash":
        for (let i = 0; i < n; i += 1) {
          const a = rnd(0, Math.PI * 2);
          const s = rnd(0.5, 2.4);
          this.add({ x, y, vx: Math.cos(a) * s + dir * 0.4, vy: Math.sin(a) * s - 0.8, g: 0.1, life: rnd(14, 28), max: 28, color: Math.random() < 0.7 ? color ?? C.violetDark : C.cyan, size: Math.random() < 0.3 ? 2 : 1 });
        }
        break;
      case "dashTrail":
        this.ghosts.push({ x, y: y + 8, facing: dir < 0 ? -1 : 1, life: 10 });
        for (let i = 0; i < 4; i += 1) this.add({ x: x - dir * rnd(2, 8), y: y + rnd(-6, 6), vx: -dir * rnd(0.3, 1.2), vy: rnd(-0.2, 0.2), life: rnd(8, 14), max: 14, color: C.cyan, size: 1 });
        break;
      case "memoryGlow":
        for (let i = 0; i < n; i += 1) {
          this.add({ x: x + rnd(-6, 6), y: y + rnd(-4, 4), vx: rnd(-0.4, 0.4), vy: rnd(-1.2, -0.3), g: -0.01, life: rnd(26, 52), max: 52, color: Math.random() < 0.6 ? C.gold : C.white, size: 1, kind: "mote" });
        }
        break;
      case "page":
      case "debris":
      case "deleteBurst":
        for (let i = 0; i < n; i += 1) {
          this.add({ x, y, vx: rnd(-1.6, 1.6), vy: rnd(-2.4, -0.4), g: 0.05, life: rnd(30, 60), max: 60, color: name === "deleteBurst" ? C.crimson : C.parch2, size: 3, kind: "page", rot: rnd(0, 6), spin: rnd(-0.2, 0.2) });
        }
        break;
      default:
        break;
    }
  }

  update(): void {
    for (let i = this.parts.length - 1; i >= 0; i -= 1) {
      const p = this.parts[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += p.g;
      p.rot += p.spin;
      p.life -= 1;
      if (p.life <= 0) this.parts.splice(i, 1);
    }
    for (let i = this.ghosts.length - 1; i >= 0; i -= 1) {
      this.ghosts[i].life -= 1;
      if (this.ghosts[i].life <= 0) this.ghosts.splice(i, 1);
    }
    if (this.flash > 0) this.flash = Math.max(0, this.flash - 0.04);
    if (this.shakeFrames > 0) this.shakeFrames -= 1;
    if (this.slashLife > 0) this.slashLife -= 1;
  }
}

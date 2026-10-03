import { TILE } from "./constants";
import { moveFoot, rectsOverlap, T, type TileMap } from "./tilemap";
import type { Facing, FootBox, GameEvent, Rect } from "./types";

export type EnemyKind = "scribble" | "tornPage" | "hound" | "broken";

/** Mọi trạng thái của bốn loại kẻ địch (mỗi loại chỉ dùng tập con của chúng). */
export type EnemyState =
  | "patrol" | "notice" | "lunge" | "recover" // Scribble
  | "hover" | "telegraph" | "dive" | "return" // Torn Page
  | "crouch" | "charge" | "skid" // Redaction Hound
  | "idle" | "chase" | "slam" // Broken Character
  | "dying";

export interface EnemyDef {
  kind: EnemyKind;
  /** Vị trí theo ô: tx = cột, ty = hàng của ô nơi kẻ địch ĐỨNG (chân ở đáy ô). Torn Page: tâm bay. */
  tx: number;
  ty: number;
  /** Phạm vi tuần tra theo ô [trái, phải] (chỉ ghi nhớ — kẻ địch tự quay đầu ở tường/mép). */
  range?: readonly [number, number];
}

interface Spec {
  w: number;
  h: number;
  hp: number;
  /** Số khung của từng pha (telegraph = báo trước). */
  telegraph: number;
  contact: number;
  flying: boolean;
}

export const ENEMY_SPEC: Record<EnemyKind, Spec> = {
  scribble: { w: 12, h: 12, hp: 3, telegraph: 24, contact: 1, flying: false },
  tornPage: { w: 12, h: 12, hp: 2, telegraph: 30, contact: 1, flying: true },
  hound: { w: 18, h: 10, hp: 4, telegraph: 22, contact: 1, flying: false },
  broken: { w: 14, h: 22, hp: 12, telegraph: 38, contact: 1, flying: false },
};

export interface EnemyCtx {
  map: TileMap;
  /** Vị trí người chơi (chân giữa) và hộp thân. */
  px: number;
  py: number;
  emit: (e: GameEvent) => void;
}

let nextId = 1;

export class Enemy {
  readonly id = nextId++;
  readonly kind: EnemyKind;
  readonly spec: Spec;
  x: number;
  y: number;
  vx = 0;
  vy = 0;
  facing: Facing = -1;
  hp: number;
  maxHp: number;
  state: EnemyState;
  t = 0;
  /** Khung còn lại bị Memory Pulse làm gián đoạn. */
  stun = 0;
  flash = 0;
  /** Khung bị đẩy lùi sau khi trúng đòn. */
  knock = 0;
  deathT = 0;
  dead = false;
  /** Điểm neo (Torn Page) / mốc sinh ra. */
  readonly ax: number;
  readonly ay: number;
  /** Mốc mục tiêu đã khoá lúc telegraph (Torn Page). */
  lockX = 0;
  lockY = 0;
  cooldown = 0;
  /** Broken Character: đã nói câu "gặp" chưa / đã vào chế độ bực dọc chưa. */
  engaged = false;
  enraged = false;
  chain = 0;
  anim = 0;

  constructor(def: EnemyDef) {
    this.kind = def.kind;
    this.spec = ENEMY_SPEC[def.kind];
    this.hp = this.maxHp = this.spec.hp;
    this.x = def.tx * TILE + TILE / 2;
    this.y = this.spec.flying ? def.ty * TILE + TILE / 2 : (def.ty + 1) * TILE;
    this.ax = this.x;
    this.ay = this.y;
    this.state = this.spec.flying ? "hover" : def.kind === "broken" ? "idle" : "patrol";
  }

  /** Hộp thân (nhận đòn). Gốc giữa-chân với kẻ đi bộ; tâm với kẻ bay. */
  get foot(): FootBox {
    return this.spec.flying
      ? { x: this.x, y: this.y + this.spec.h / 2, w: this.spec.w, h: this.spec.h }
      : { x: this.x, y: this.y, w: this.spec.w, h: this.spec.h };
  }

  get hurtbox(): Rect {
    const f = this.foot;
    return { x: f.x - f.w / 2, y: f.y - f.h, w: f.w, h: f.h };
  }

  /** Hộp chạm gây sát thương lên người chơi — hơi nhỏ hơn thân (va chạm công bằng). Rỗng khi chết/bị gián đoạn. */
  get contactBox(): Rect | null {
    if (this.dead || this.state === "dying" || this.stun > 0) return null;
    const b = this.hurtbox;
    return { x: b.x + 2, y: b.y + 2, w: b.w - 4, h: b.h - 3 };
  }

  /** Hộp đòn riêng (đòn đập của Broken Character) hoặc null. */
  get attackBox(): Rect | null {
    if (this.kind === "broken" && this.state === "slam" && this.stun === 0 && this.t >= 1 && this.t <= 8) {
      const reach = 26;
      const x = this.facing === 1 ? this.x + this.spec.w / 2 - 2 : this.x - this.spec.w / 2 - reach + 2;
      return { x, y: this.y - 22, w: reach, h: 22 };
    }
    return null;
  }

  get damage(): number {
    return this.spec.contact;
  }

  disrupt(frames: number): void {
    if (this.dead || this.state === "dying") return;
    this.stun = Math.max(this.stun, this.kind === "broken" ? Math.min(frames, 60) : frames);
  }

  /** Nhận đòn: trả `true` nếu chết. */
  hit(damage: number, dir: number, emit: (e: GameEvent) => void): boolean {
    if (this.dead || this.state === "dying") return false;
    this.hp -= damage;
    this.flash = 6;
    this.knock = this.kind === "broken" ? 4 : 8;
    this.vx = dir * (this.kind === "broken" ? 0.6 : this.kind === "hound" ? 1.2 : 1.8);
    if (this.spec.flying) this.vy = -0.6;
    // Đòn trúng cắt ngang pha telegraph/lướt của kẻ nhỏ (người chơi được thưởng vì phản ứng đúng); Broken Character không bị cắt.
    if (this.kind !== "broken") {
      if (this.state === "telegraph") {
        // Torn Page (không có pha "recover"): bị ngắt thì bay về chỗ neo.
        this.state = "return";
        this.t = 0;
        this.vx = 0;
        this.vy = 0;
      } else if (this.state === "dive") {
        this.state = "return";
        this.t = 0;
        this.vx = 0;
        this.vy = 0;
      } else if (this.state === "notice" || this.state === "crouch" || this.state === "lunge" || this.state === "charge" || this.state === "skid") {
        // Bị chém giữa chừng (kể cả lúc đang lao) ⇒ cú lao bị ngắt, kẻ địch lảo đảo rồi hồi — không tiếp tục lao với vận tốc hất lùi.
        this.setState("recover", 18);
      }
    }
    if (this.kind === "broken" && !this.enraged && this.hp <= this.maxHp / 2 && this.hp > 0) {
      this.enraged = true;
      emit({ t: "caption", id: "broken.half" });
    }
    if (this.hp <= 0) {
      this.state = "dying";
      this.deathT = 22;
      this.t = 0;
      this.vx = 0;
      emit({ t: "sfx", name: "enemyDie", x: this.x, y: this.y });
      emit({ t: "fx", name: "inkSplash", x: this.x, y: this.y - this.spec.h / 2, n: 14 });
      if (this.kind === "broken") emit({ t: "caption", id: "broken.die" });
      return true;
    }
    return false;
  }

  /** Còn tồn tại trong thế giới? (chết xong thì dọn). */
  get alive(): boolean {
    return !(this.state === "dying" && this.deathT <= 0);
  }

  private setState(s: EnemyState, t = 0): void {
    this.state = s;
    this.t = t > 0 ? this.stateLen(s) - t : 0;
  }

  /** Độ dài pha cố định (khung) — dùng cho setState có đếm lùi ngắn hơn. */
  private stateLen(s: EnemyState): number {
    switch (s) {
      case "recover": return this.kind === "hound" ? 26 : this.kind === "broken" ? 44 : 28;
      default: return 30;
    }
  }

  update(ctx: EnemyCtx): void {
    this.anim += 1;
    if (this.flash > 0) this.flash -= 1;
    if (this.cooldown > 0) this.cooldown -= 1;
    if (this.state === "dying") {
      this.deathT -= 1;
      return;
    }
    if (this.stun > 0) {
      this.stun -= 1;
      return; // bị Pulse làm gián đoạn: đứng im (không hành động, không gây sát thương chạm)
    }
    if (this.knock > 0) {
      this.knock -= 1;
      this.applyMove(ctx.map, this.vx, this.spec.flying ? this.vy : 0, false);
      this.vx *= 0.8;
      this.vy *= 0.8;
      return;
    }
    this.t += 1;
    switch (this.kind) {
      case "scribble": this.updateScribble(ctx); break;
      case "tornPage": this.updateTornPage(ctx); break;
      case "hound": this.updateHound(ctx); break;
      case "broken": this.updateBroken(ctx); break;
    }
  }

  // ---------------------------------------------------------------- tiện ích di chuyển
  private applyMove(map: TileMap, dx: number, dy: number, gravity: boolean): { hitWall: boolean; onGround: boolean } {
    let vy = dy;
    if (gravity) {
      this.vy = Math.min(5, this.vy + 0.4);
      vy = this.vy;
    }
    const res = moveFoot(map, this.foot, dx, vy);
    if (this.spec.flying) {
      this.x = res.x;
      this.y = res.y - this.spec.h / 2;
    } else {
      this.x = res.x;
      this.y = res.y;
    }
    if (res.hitFloor) this.vy = 0;
    return { hitWall: res.hitLeft || res.hitRight, onGround: res.hitFloor || (!this.spec.flying && map.groundBelow(this.foot)) };
  }

  /** Có sàn ngay trước mặt (mép hố/tường)? Dùng để quay đầu thay vì rơi. */
  private edgeAhead(map: TileMap, dir: number): boolean {
    const f = this.foot;
    const px = f.x + dir * (f.w / 2 + 2);
    const tx = Math.floor(px / TILE);
    const ty = Math.floor((f.y + 2) / TILE);
    const k = map.kind(tx, ty);
    if (map.kind(tx, Math.floor((f.y - 2) / TILE)) === T.SPIKE) return true;
    return !(map.solid(tx, ty) || k === T.ONEWAY);
  }

  private wallAhead(map: TileMap, dir: number): boolean {
    const f = this.foot;
    const px = f.x + dir * (f.w / 2 + 1);
    return map.solid(Math.floor(px / TILE), Math.floor((f.y - f.h / 2) / TILE));
  }

  private face(px: number): void {
    this.facing = px >= this.x ? 1 : -1;
  }

  private sees(ctx: EnemyCtx, range: number, dy: number): boolean {
    const dx = Math.abs(ctx.px - this.x);
    const ddy = Math.abs(ctx.py - this.y);
    return dx < range && ddy < dy && ctx.map.lineClear(this.x, this.y - this.spec.h / 2, ctx.px, ctx.py - 8);
  }

  // ---------------------------------------------------------------- Scribble: tuần tra → báo trước → lao → hồi
  private updateScribble(ctx: EnemyCtx): void {
    const { map } = ctx;
    switch (this.state) {
      case "patrol": {
        const sp = 0.5;
        if (this.wallAhead(map, this.facing) || this.edgeAhead(map, this.facing)) this.facing = (-this.facing) as Facing;
        this.applyMove(map, this.facing * sp, 0, true);
        if (this.cooldown === 0 && this.sees(ctx, 90, 28)) {
          this.face(ctx.px);
          this.state = "notice";
          this.t = 0;
          ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
        }
        break;
      }
      case "notice":
        this.applyMove(map, 0, 0, true);
        if (this.t >= this.spec.telegraph) {
          this.state = "lunge";
          this.t = 0;
        }
        break;
      case "lunge": {
        const r = this.applyMove(map, this.facing * 2.8, 0, true);
        if (this.t >= 14 || r.hitWall || this.edgeAhead(map, this.facing)) {
          this.state = "recover";
          this.t = 0;
        }
        break;
      }
      case "recover":
        this.applyMove(map, 0, 0, true);
        if (this.t >= 28) {
          this.state = "patrol";
          this.t = 0;
          this.cooldown = 30;
        }
        break;
      default:
        break;
    }
  }

  // ---------------------------------------------------------------- Torn Page: lơ lửng → báo trước → bổ nhào → trở về
  private updateTornPage(ctx: EnemyCtx): void {
    const { map } = ctx;
    switch (this.state) {
      case "hover": {
        const k = this.anim;
        const tx = this.ax + Math.sin(k * 0.03) * 10;
        const ty = this.ay + Math.sin(k * 0.05) * 6;
        this.x += (tx - this.x) * 0.1;
        this.y += (ty - this.y) * 0.1;
        this.face(ctx.px);
        if (this.cooldown === 0 && Math.abs(ctx.px - this.x) < 120 && Math.abs(ctx.py - 8 - this.y) < 100 && map.lineClear(this.x, this.y, ctx.px, ctx.py - 8)) {
          this.state = "telegraph";
          this.t = 0;
          ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
        }
        break;
      }
      case "telegraph":
        if (this.t < this.spec.telegraph - 8) {
          this.lockX = ctx.px;
          this.lockY = ctx.py - 8; // theo dõi tới 8 khung cuối rồi KHOÁ: người chơi có thời gian đổi vị trí
        }
        this.x += (Math.sin(this.t * 1.7) * 0.6);
        if (this.t >= this.spec.telegraph) {
          const dx = this.lockX - this.x;
          const dy = this.lockY - this.y;
          const d = Math.hypot(dx, dy) || 1;
          this.vx = (dx / d) * 3.4;
          this.vy = (dy / d) * 3.4;
          this.state = "dive";
          this.t = 0;
        }
        break;
      case "dive": {
        const res = moveFoot(map, this.foot, this.vx, this.vy);
        const blocked = res.hitLeft || res.hitRight || res.hitFloor || res.hitCeil;
        this.x = res.x;
        this.y = res.y - this.spec.h / 2;
        const reached = Math.hypot(this.lockX - this.x, this.lockY - this.y) < 4;
        if (blocked || reached || this.t >= 28) {
          this.state = "return";
          this.t = 0;
          this.vx = 0;
          this.vy = 0;
        }
        break;
      }
      case "return": {
        const dx = this.ax - this.x;
        const dy = this.ay - this.y;
        const d = Math.hypot(dx, dy);
        if (d < 3 || this.t >= 90) {
          this.state = "hover";
          this.t = 0;
          this.cooldown = 40;
        } else {
          const sp = Math.min(1.2, d);
          const res = moveFoot(map, this.foot, (dx / d) * sp, (dy / d) * sp);
          this.x = res.x;
          this.y = res.y - this.spec.h / 2;
        }
        break;
      }
      default:
        break;
    }
  }

  // ---------------------------------------------------------------- Redaction Hound: tuần tra nhanh → cúi (báo trước) → lao thẳng → trượt → hồi
  private updateHound(ctx: EnemyCtx): void {
    const { map } = ctx;
    switch (this.state) {
      case "patrol": {
        const sp = 0.8;
        if (this.wallAhead(map, this.facing) || this.edgeAhead(map, this.facing)) this.facing = (-this.facing) as Facing;
        this.applyMove(map, this.facing * sp, 0, true);
        if (this.cooldown === 0 && this.sees(ctx, 150, 20) && !this.wallBetween(map, ctx.px)) {
          this.face(ctx.px);
          this.state = "crouch";
          this.t = 0;
          ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
        }
        break;
      }
      case "crouch":
        this.applyMove(map, 0, 0, true);
        if (this.t >= this.spec.telegraph) {
          this.state = "charge";
          this.t = 0;
          this.vx = this.facing * 3.3;
        }
        break;
      case "charge": {
        const r = this.applyMove(map, this.vx, 0, true);
        if (r.hitWall || this.edgeAhead(map, this.facing) || this.t >= 70) {
          this.state = "skid";
          this.t = 0;
        }
        break;
      }
      case "skid":
        this.vx *= 0.82;
        this.applyMove(map, this.vx, 0, true);
        if (this.t >= 12) {
          this.state = "recover";
          this.t = 0;
          this.vx = 0;
        }
        break;
      case "recover":
        this.applyMove(map, 0, 0, true);
        if (this.t >= 26) {
          this.state = "patrol";
          this.t = 0;
          this.cooldown = 30;
        }
        break;
      default:
        break;
    }
  }

  private wallBetween(map: TileMap, px: number): boolean {
    const y = this.y - this.spec.h / 2;
    return !map.lineClear(this.x, y, px, y);
  }

  // ---------------------------------------------------------------- Broken Character: bất ổn → đuổi chậm → giơ tay (báo trước dài) → đập → hồi
  private updateBroken(ctx: EnemyCtx): void {
    const { map } = ctx;
    const tele = this.enraged ? 28 : this.spec.telegraph;
    switch (this.state) {
      case "idle":
      case "chase": {
        this.face(ctx.px);
        const near = Math.abs(ctx.px - this.x) < 170 && Math.abs(ctx.py - this.y) < 40;
        if (near && !this.engaged) {
          this.engaged = true;
          ctx.emit({ t: "caption", id: "broken.engage" });
        }
        if (near) {
          this.state = "chase";
          if (Math.abs(ctx.px - this.x) > 36 && !this.edgeAhead(map, this.facing) && !this.wallAhead(map, this.facing)) this.applyMove(map, this.facing * (this.enraged ? 0.8 : 0.6), 0, true);
          else this.applyMove(map, 0, 0, true);
          if (Math.abs(ctx.px - this.x) <= 44 && this.cooldown === 0) {
            this.state = "notice";
            this.t = 0;
            ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
          }
        } else {
          this.state = "idle";
          this.applyMove(map, 0, 0, true);
        }
        break;
      }
      case "notice":
        this.applyMove(map, 0, 0, true);
        if (this.t >= tele) {
          this.state = "slam";
          this.t = 0;
        }
        break;
      case "slam":
        this.applyMove(map, 0, 0, true);
        if (this.t === 1) ctx.emit({ t: "shake", amount: 2, frames: 8 });
        if (this.t >= 12) {
          if (this.enraged && this.chain === 0) {
            this.chain = 1;
            this.state = "notice";
            this.t = Math.floor(tele * 0.5); // đòn nối: báo trước ngắn hơn nhưng vẫn đủ đọc
          } else {
            this.chain = 0;
            this.state = "recover";
            this.t = 0;
          }
        }
        break;
      case "recover":
        this.applyMove(map, 0, 0, true);
        if (this.t >= 44) {
          this.state = "chase";
          this.t = 0;
          this.cooldown = 24;
        }
        break;
      default:
        break;
    }
  }
}

export function resetEnemyIds(): void {
  nextId = 1;
}

export function enemyOverlaps(e: Enemy, r: Rect): boolean {
  return !e.dead && e.state !== "dying" && rectsOverlap(e.hurtbox, r);
}

import { BLADE, PLAYER, PULSE } from "./constants";
import { moveFoot, type TileMap } from "./tilemap";
import type { Facing, FootBox, GameEvent, InputState, Rect } from "./types";
import { NO_INPUT } from "./types";

export type AttackKind = "none" | "g1" | "g2" | "g3" | "air";
export type PlayerAnim = "idle" | "run" | "jump" | "fall" | "dash" | "attack" | "hurt" | "pulse" | "read";

export interface PlayerAbilities {
  marginStep: boolean;
  /** Memory II mở rộng Memory Pulse. */
  pulseWide: boolean;
  /** Memory III làm Pulse rẻ hơn. */
  pulseCheap: boolean;
}

export interface PlayerCtx {
  map: TileMap;
  input: Readonly<InputState>;
  abilities: Readonly<PlayerAbilities>;
  emit: (e: GameEvent) => void;
}

/**
 * Người chơi: bộ điều khiển di chuyển + đòn đánh + Margin Step + Memory Pulse. Mọi thứ là máy trạng thái đếm khung hình, không
 * dùng thời gian thực, nên cùng chuỗi nhập luôn cho cùng kết quả (replay/test tất định).
 */
export class Player {
  x = 0;
  y = 0;
  vx = 0;
  vy = 0;
  facing: Facing = 1;
  onGround = false;
  coyote = 0;
  jumpBuffer = 0;
  hp: number = PLAYER.maxHp;
  maxHp: number = PLAYER.maxHp;
  ink = 0;
  invuln = 0;
  hurt = 0;
  /** Margin Step. */
  dashTimer = 0;
  dashDir: Facing = 1;
  dashCooldown = 0;
  dashAvailable = true;
  dashSlash = false;
  /** Glyph Blade. */
  attackKind: AttackKind = "none";
  attackT = 0;
  attackQueued = false;
  /** Số định danh các thực thể đã trúng ở nhát hiện tại (một nhát chỉ trúng mỗi kẻ một lần). */
  readonly attackHit = new Set<number>();
  /** Memory Pulse: 0 = không; >0 = số khung đã trôi từ lúc tung. */
  pulseT = 0;
  pulseRadius = 0;
  /** Vị trí an toàn gần nhất (gai/hố đưa người chơi về đây). */
  safeX = 0;
  safeY = 0;
  private safeStable = 0;
  anim: PlayerAnim = "idle";
  animT = 0;
  /** Số khung đã chạy cho nhịp bước chân. */
  runT = 0;
  private prev: InputState = { ...NO_INPUT };

  constructor(x = 0, y = 0) {
    this.place(x, y);
  }

  place(x: number, y: number): void {
    this.x = x;
    this.y = y;
    this.vx = 0;
    this.vy = 0;
    this.safeX = x;
    this.safeY = y;
    this.safeStable = 0;
    this.onGround = false;
    this.coyote = 0;
    this.jumpBuffer = 0;
    this.dashTimer = 0;
    this.attackKind = "none";
    this.attackT = 0;
    this.attackQueued = false;
    this.attackHit.clear();
    this.pulseT = 0;
    this.hurt = 0;
  }

  get foot(): FootBox {
    return { x: this.x, y: this.y, w: PLAYER.w, h: PLAYER.h };
  }

  get dashing(): boolean {
    return this.dashTimer > 0;
  }

  /** Bất khả xâm phạm (khung bất tử sau trúng đòn hoặc khung đầu của lướt). */
  get invulnerable(): boolean {
    return this.invuln > 0 || (this.dashTimer > 0 && PLAYER.dashFrames - this.dashTimer < PLAYER.dashInvuln);
  }

  /** Hộp đòn đang có hiệu lực (toạ độ thế giới, góc trên-trái) hoặc null. */
  attackBox(): { rect: Rect; damage: number; heavy: boolean } | null {
    if (this.dashing && this.dashSlash) {
      const b = BLADE.dash.box;
      return { rect: this.boxRect(b), damage: BLADE.dash.damage, heavy: true };
    }
    if (this.attackKind === "none") return null;
    const def = BLADE[this.attackKind];
    if (this.attackT < def.hit[0] || this.attackT > def.hit[1]) return null;
    return { rect: this.boxRect(def.box), damage: def.damage, heavy: this.attackKind === "g3" };
  }

  private boxRect(b: { dx: number; dy: number; w: number; h: number }): Rect {
    const x = this.facing === 1 ? this.x + b.dx : this.x - b.dx - b.w;
    return { x, y: this.y + b.dy, w: b.w, h: b.h };
  }

  /** Nhận sát thương. Trả `true` nếu thật sự trúng (không bất tử). */
  takeHit(srcX: number, damage: number, emit: (e: GameEvent) => void): boolean {
    if (this.invulnerable || this.hp <= 0) return false;
    this.hp = Math.max(0, this.hp - damage);
    this.invuln = PLAYER.invulnFrames;
    this.hurt = PLAYER.hurtFrames;
    const dir = this.x < srcX ? -1 : 1;
    this.vx = dir * PLAYER.knockbackX;
    this.vy = PLAYER.knockbackY;
    this.onGround = false;
    this.cancelActions();
    emit({ t: "sfx", name: "hurt", x: this.x, y: this.y });
    emit({ t: "shake", amount: 3, frames: 10 });
    emit({ t: "fx", name: "inkSplash", x: this.x, y: this.y - 8, dir, n: 8 });
    return true;
  }

  /** Về chỗ an toàn (gai/hố): mất 1 máu nhưng không mất phòng. */
  returnToSafe(): void {
    this.x = this.safeX;
    this.y = this.safeY;
    this.vx = 0;
    this.vy = 0;
    this.cancelActions();
    this.invuln = Math.max(this.invuln, PLAYER.invulnFrames);
  }

  private cancelActions(): void {
    this.dashTimer = 0;
    this.dashSlash = false;
    this.attackKind = "none";
    this.attackT = 0;
    this.attackQueued = false;
    this.attackHit.clear();
    this.pulseT = 0;
  }

  update(ctx: PlayerCtx): void {
    const { map, input: inp, emit } = ctx;
    const jumpPressed = inp.jump && !this.prev.jump;
    const attackPressed = inp.attack && !this.prev.attack;
    const pulsePressed = inp.pulse && !this.prev.pulse;
    const dashPressed = inp.dash && !this.prev.dash;

    if (this.invuln > 0) this.invuln -= 1;
    if (this.dashCooldown > 0) this.dashCooldown -= 1;
    if (this.jumpBuffer > 0) this.jumpBuffer -= 1;
    if (jumpPressed) this.jumpBuffer = PLAYER.jumpBufferFrames;

    const dir = (inp.right ? 1 : 0) - (inp.left ? 1 : 0);
    const stunned = this.hurt > 0;

    if (stunned) {
      this.hurt -= 1;
    } else {
      this.controlActions(ctx, { attackPressed, pulsePressed, dashPressed, dir });
    }

    // --- ngang ---
    if (this.dashing) {
      this.vx = this.dashDir * PLAYER.dashSpeed;
      this.vy = 0;
    } else if (!stunned) {
      this.horizontal(dir);
    } else {
      this.vx *= 0.9;
    }

    // --- nhảy ---
    if (!stunned && !this.dashing && this.pulseT === 0 && this.jumpBuffer > 0 && (this.onGround || this.coyote > 0) && !(this.attackKind === "g3" && this.attackT < 8)) {
      this.vy = -PLAYER.jumpVel;
      this.onGround = false;
      this.coyote = 0;
      this.jumpBuffer = 0;
      emit({ t: "sfx", name: "jump", x: this.x, y: this.y });
      emit({ t: "fx", name: "dust", x: this.x, y: this.y, n: 4 });
      if (this.attackKind !== "none" && this.attackKind !== "air") this.endAttack();
    }
    if (!inp.jump && this.vy < -PLAYER.jumpCut && !this.dashing) this.vy = -PLAYER.jumpCut;

    // --- trọng lực ---
    if (!this.dashing) {
      const g = this.vy < 0 && inp.jump ? PLAYER.gravityUp : PLAYER.gravityDown;
      this.vy = Math.min(PLAYER.maxFall, this.vy + g);
    }

    // --- di chuyển + va chạm ---
    const res = moveFoot(map, this.foot, this.vx, this.vy);
    this.x = res.x;
    this.y = res.y;
    if (res.hitLeft || res.hitRight) {
      this.vx = 0;
      if (this.dashing) this.dashTimer = 1;
    }
    if (res.hitCeil && this.vy < 0) this.vy = 0;
    const wasAir = !this.onGround;
    if (res.hitFloor) {
      if (this.vy > 0) {
        if (wasAir && this.vy > 2.2) {
          emit({ t: "sfx", name: "land", x: this.x, y: this.y });
          emit({ t: "fx", name: "dust", x: this.x, y: this.y, n: 3 });
        }
        this.vy = 0;
      }
      this.onGround = true;
    } else {
      this.onGround = this.vy >= 0 && map.groundBelow(this.foot);
    }

    if (this.onGround) {
      this.coyote = PLAYER.coyoteFrames;
      this.dashAvailable = true;
      // Ghi nhớ chỗ an toàn khi đã đứng vững một lúc (không ở mép hố/gai).
      this.safeStable += 1;
      if (this.safeStable >= 8 && !map.hitsSpike({ ...this.foot, y: this.y - 2 })) {
        this.safeX = this.x;
        this.safeY = this.y;
      }
    } else {
      this.safeStable = 0;
      if (this.coyote > 0) this.coyote -= 1;
    }

    // --- hoạt ảnh ---
    this.pickAnim();
    this.prev = { ...inp };
  }

  /** Lướt / đánh / Pulse — quyết định hành động của khung này. */
  private controlActions(ctx: PlayerCtx, a: { attackPressed: boolean; pulsePressed: boolean; dashPressed: boolean; dir: number }): void {
    const { abilities, emit } = ctx;

    // Memory Pulse
    if (this.pulseT > 0) {
      this.pulseT += 1;
      this.pulseRadius = this.pulseProgress() * (abilities.pulseWide ? PULSE.radiusMemory2 : PULSE.radius);
      if (this.pulseT > PULSE.lockFrames + PULSE.windup) {
        this.pulseT = 0;
        this.pulseRadius = 0;
      }
    } else if (a.pulsePressed && this.ink >= this.pulseCost(abilities) && !this.dashing) {
      this.ink -= this.pulseCost(abilities);
      this.pulseT = 1;
      this.pulseRadius = 0;
      this.endAttack();
      emit({ t: "sfx", name: "pulse", x: this.x, y: this.y });
    }

    // Margin Step
    if (this.dashing) {
      this.dashTimer -= 1;
      if (a.attackPressed && !this.dashSlash) {
        this.dashSlash = true;
        this.attackHit.clear();
        emit({ t: "sfx", name: "slash", x: this.x, y: this.y });
      }
      if (this.dashTimer <= 0) {
        this.dashSlash = false;
        this.vx = this.dashDir * PLAYER.dashExitSpeed;
        this.dashCooldown = PLAYER.dashCooldown;
      }
      return;
    }
    if (a.dashPressed && abilities.marginStep && this.dashCooldown === 0 && (this.onGround || this.dashAvailable) && this.pulseT === 0) {
      this.dashDir = a.dir !== 0 ? (a.dir as Facing) : this.facing;
      this.facing = this.dashDir;
      this.dashTimer = PLAYER.dashFrames;
      this.dashSlash = false;
      if (!this.onGround) this.dashAvailable = false;
      this.endAttack();
      emit({ t: "sfx", name: "dash", x: this.x, y: this.y });
      emit({ t: "fx", name: "dashTrail", x: this.x, y: this.y - 8, dir: this.dashDir, n: 1 });
      return;
    }

    // Glyph Blade
    if (this.pulseT > 0) return;
    if (this.attackKind !== "none") {
      const def = BLADE[this.attackKind];
      if (a.attackPressed && this.attackKind !== "air" && this.attackT >= BLADE.comboWindow[0]) this.attackQueued = true;
      this.attackT += 1;
      if (this.attackT >= def.total) {
        const next = this.attackQueued && this.onGround ? (this.attackKind === "g1" ? "g2" : this.attackKind === "g2" ? "g3" : "none") : "none";
        this.attackQueued = false;
        if (next !== "none") this.startAttack(next, emit);
        else this.endAttack();
      }
    } else if (a.attackPressed) {
      this.startAttack(this.onGround ? "g1" : "air", emit);
    }
  }

  private startAttack(kind: AttackKind, emit: (e: GameEvent) => void): void {
    this.attackKind = kind;
    this.attackT = 0;
    this.attackQueued = false;
    this.attackHit.clear();
    emit({ t: "sfx", name: "slash", x: this.x, y: this.y });
  }

  private endAttack(): void {
    this.attackKind = "none";
    this.attackT = 0;
    this.attackQueued = false;
    this.attackHit.clear();
  }

  pulseCost(abilities: Readonly<PlayerAbilities>): number {
    return abilities.pulseCheap ? PULSE.costMemory3 : PULSE.cost;
  }

  private pulseProgress(): number {
    const t = this.pulseT - PULSE.windup;
    if (t <= 0) return 0;
    return Math.min(1, t / PULSE.expandFrames);
  }

  /** Khung mà vòng Pulse bắt đầu có hiệu lực (sau thời gian chuẩn bị). */
  get pulseActive(): boolean {
    return this.pulseT > PULSE.windup && this.pulseT <= PULSE.windup + PULSE.expandFrames;
  }

  private horizontal(dir: number): void {
    const attacking = this.attackKind !== "none";
    const ground = this.onGround;
    let target = dir * PLAYER.maxRun;
    let accel: number = dir === 0 ? (ground ? PLAYER.groundDecel : PLAYER.airDecel) : ground ? PLAYER.groundAccel : PLAYER.airAccel;
    if (dir !== 0 && Math.sign(this.vx) === -dir) accel *= PLAYER.turnBoost;

    if (this.pulseT > 0) {
      target = 0;
      accel = ground ? PLAYER.groundDecel : PLAYER.airDecel;
    } else if (attacking && ground) {
      // Đòn trên mặt đất: bước tới nhẹ ở khung đầu rồi hãm lại; không đổi hướng giữa nhát.
      const def = BLADE[this.attackKind as "g1" | "g2" | "g3"];
      target = this.attackT < 6 ? this.facing * def.lunge : 0;
      accel = this.attackT < 6 ? 0.5 : PLAYER.groundDecel;
    } else if (dir !== 0) {
      this.facing = dir as Facing;
    }

    if (this.vx < target) this.vx = Math.min(target, this.vx + accel);
    else if (this.vx > target) this.vx = Math.max(target, this.vx - accel);
  }

  private pickAnim(): void {
    let a: PlayerAnim = "idle";
    if (this.hurt > 0) a = "hurt";
    else if (this.pulseT > 0) a = "pulse";
    else if (this.dashing) a = "dash";
    else if (this.attackKind !== "none") a = "attack";
    else if (!this.onGround) a = this.vy < 0 ? "jump" : "fall";
    else if (Math.abs(this.vx) > 0.3) a = "run";
    if (a === this.anim) this.animT += 1;
    else {
      this.anim = a;
      this.animT = 0;
    }
    this.runT = a === "run" ? this.runT + Math.abs(this.vx) : 0;
  }
}

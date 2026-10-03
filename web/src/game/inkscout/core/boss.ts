import { TILE } from "./constants";
import { Rng } from "./rng";
import type { TileMap } from "./tilemap";
import type { Facing, GameEvent, Rect } from "./types";

/**
 * THE REDACTOR — boss duy nhất của Chương 0. Máy trạng thái đếm khung hình, mọi lựa chọn đi qua `Rng` có hạt giống ⇒ cùng hạt giống + cùng
 * chuỗi nhập luôn cho cùng trận đấu. Mỗi đòn nguy hiểm có `telegraph` (báo trước) ≥ 24 khung (0,4 s) — `ink-scout-boss.test.mjs` canh số này
 * và chạy một bot phản ứng chậm 15 khung để chứng minh trận đấu thắng được.
 *
 * Giai đoạn 1 — Guardian: Revision Slash, Black Line, Margin Cut, Rewrite.
 * Giai đoạn 2 — Corrupted Editor (≤ ~56% máu): thêm Delete, Broken Sentence, Revision Rush, Memory Collapse.
 */
export type BossAttack =
  | "revisionSlash" | "blackLine" | "marginCut" | "rewrite"
  | "delete" | "brokenSentence" | "revisionRush" | "memoryCollapse";

export const BOSS_ATTACKS: Record<BossAttack, { telegraph: number; active: number; recover: number }> = {
  revisionSlash: { telegraph: 40, active: 30, recover: 34 },
  blackLine: { telegraph: 45, active: 20, recover: 30 },
  marginCut: { telegraph: 36, active: 44, recover: 30 },
  rewrite: { telegraph: 30, active: 40, recover: 26 },
  delete: { telegraph: 50, active: 90, recover: 24 },
  brokenSentence: { telegraph: 30, active: 70, recover: 36 },
  revisionRush: { telegraph: 24, active: 156, recover: 42 },
  memoryCollapse: { telegraph: 50, active: 720, recover: 0 },
};

export const PHASE1_ATTACKS: readonly BossAttack[] = ["revisionSlash", "blackLine", "marginCut", "rewrite"];
export const PHASE2_ATTACKS: readonly BossAttack[] = ["revisionSlash", "blackLine", "marginCut", "rewrite", "delete", "brokenSentence", "revisionRush"];

export const BOSS = {
  w: 24,
  h: 44,
  maxHp: 50,
  /** Vào giai đoạn 2 khi máu ≤ ngưỡng này (~56%). */
  phase2At: 28,
  /** Lần Memory Collapse thứ hai. */
  collapse2At: 12,
  fragments: 4,
  fragmentHp: 2,
  fragmentRadius: 42,
  staggerFrames: 90,
  stunAfterCollapse: 170,
  pulseStun: 50,
} as const;

export type BossPhase = 1 | 2;
export type BossState = "dormant" | "intro" | "neutral" | "telegraph" | "active" | "recover" | "stagger" | "stunned" | "collapse" | "dying" | "dead";

export interface BossHazard {
  rect: Rect;
  damage: number;
  kind: "slash" | "line" | "wave" | "projectile" | "zone" | "fragment";
}

interface LineHazard { horizontal: boolean; rect: Rect; t: number; telegraph: number; active: number }
interface DeleteZone { x: number; w: number; t: number; telegraph: number; active: number }
interface Wave { x: number; y: number; dir: Facing; life: number }
export interface GlyphShot { x: number; y: number; vx: number; vy: number; life: number; id: number }
export interface Fragment { id: number; angle: number; hp: number; cracked: boolean; flash: number; fireT: number; x: number; y: number }

export interface BossCtx {
  map: TileMap;
  px: number;
  py: number;
  /** Số Memory người chơi đã có (0–3): làm nứt từng mảnh của Memory Collapse. */
  memories: number;
  emit: (e: GameEvent) => void;
}

/** Bộ lập lịch đòn: túi xáo trộn có hạt giống, không lặp đòn liền kề, lọc theo khoảng cách. Tách riêng để test. */
export class BossScheduler {
  private bag: BossAttack[] = [];
  last: BossAttack | null = null;

  constructor(private readonly rng: Rng) {}

  next(phase: BossPhase, dist: number): BossAttack {
    const pool = phase === 1 ? PHASE1_ATTACKS : PHASE2_ATTACKS;
    if (this.bag.length === 0) this.refill(pool);
    // Lấy đòn đầu túi không trùng đòn trước; Revision Slash không dùng khi người chơi áp sát (bất công) — Margin Cut hợp hơn.
    let idx = this.bag.findIndex((a) => a !== this.last && !(a === "revisionSlash" && dist < 28));
    if (idx < 0) idx = 0;
    const pick = this.bag.splice(idx, 1)[0];
    this.last = pick;
    return pick;
  }

  /** Sang giai đoạn 2: bỏ túi cũ để đòn mới xuất hiện ngay. */
  reset(): void {
    this.bag = [];
  }

  private refill(pool: readonly BossAttack[]): void {
    const a = [...pool];
    for (let i = a.length - 1; i > 0; i -= 1) {
      const j = this.rng.int(i + 1);
      [a[i], a[j]] = [a[j], a[i]];
    }
    this.bag = a;
  }
}

let shotId = 1;
let fragId = 1;

export class Boss {
  x: number;
  y: number;
  facing: Facing = -1;
  hp: number = BOSS.maxHp;
  readonly maxHp: number = BOSS.maxHp;
  phase: BossPhase = 1;
  state: BossState = "dormant";
  t = 0;
  attack: BossAttack | null = null;
  invuln = false;
  flash = 0;
  stun = 0;
  /** Biến ẩn của đòn đang chạy. */
  lockX = 0;
  lockY = 0;
  step = 0;
  visible = true;
  collapses = 0;
  collapseT = 0;
  pulseCooldown = 0;
  dyingT = 0;
  anim = 0;
  readonly lines: LineHazard[] = [];
  readonly zones: DeleteZone[] = [];
  readonly waves: Wave[] = [];
  readonly shots: GlyphShot[] = [];
  fragments: Fragment[] = [];
  private readonly sched: BossScheduler;
  private neutralFor = 40;
  private readonly rng: Rng;

  constructor(
    readonly floorY: number,
    readonly left: number,
    readonly right: number,
    seed: number,
  ) {
    this.rng = new Rng(seed);
    this.sched = new BossScheduler(this.rng);
    this.x = right - 40;
    this.y = floorY;
  }

  get hurtbox(): Rect {
    return { x: this.x - BOSS.w / 2, y: this.y - BOSS.h, w: BOSS.w, h: BOSS.h };
  }

  /** Bắt đầu trận (người chơi đã vào đấu trường). */
  awaken(): void {
    if (this.state === "dormant") {
      this.state = "intro";
      this.t = 0;
    }
  }

  get active(): boolean {
    return this.state !== "dormant" && this.state !== "dead";
  }

  /** Có thể bị trúng đòn lúc này không? */
  get vulnerable(): boolean {
    return !this.invuln && this.visible && (this.state === "neutral" || this.state === "telegraph" || this.state === "active" || this.state === "recover" || this.state === "stunned");
  }

  /** Người chơi chém trúng boss. Trả `true` nếu nhận sát thương. */
  hit(damage: number, emit: (e: GameEvent) => void): boolean {
    if (!this.vulnerable) return false;
    const dmg = this.state === "stunned" ? Math.ceil(damage * 1.5) : damage;
    this.hp -= dmg;
    this.flash = 6;
    emit({ t: "sfx", name: "bossHit", x: this.x, y: this.y - 20 });
    if (this.hp <= 0) {
      this.die(emit);
    } else if (this.phase === 1 && this.hp <= BOSS.phase2At) {
      this.beginStagger(emit);
    }
    return true;
  }

  /** Memory Pulse trúng boss ngoài pha chắn: ngắt đòn đang báo trước, boss choáng ngắn (có hồi chiêu để không lạm dụng). */
  pulseHit(emit: (e: GameEvent) => void): void {
    if (this.state === "collapse" || this.invuln || this.pulseCooldown > 0) return;
    if (this.state === "telegraph") {
      this.state = "stunned";
      this.stun = BOSS.pulseStun;
      this.t = 0;
      this.attack = null;
      this.lines.length = 0;
      this.zones.length = 0;
      this.pulseCooldown = 600;
      this.flash = 8;
      emit({ t: "sfx", name: "bossHit", x: this.x, y: this.y - 20 });
      emit({ t: "fx", name: "memoryGlow", x: this.x, y: this.y - 22, n: 10 });
    }
  }

  /** Pulse xoá đạn glyph trong bán kính. Trả số viên bị xoá. */
  pulseShots(cx: number, cy: number, r: number, emit: (e: GameEvent) => void): number {
    let n = 0;
    for (let i = this.shots.length - 1; i >= 0; i -= 1) {
      const s = this.shots[i];
      if (Math.hypot(s.x - cx, s.y - cy) <= r) {
        this.shots.splice(i, 1);
        n += 1;
        emit({ t: "fx", name: "spark", x: s.x, y: s.y, n: 4 });
      }
    }
    return n;
  }

  /** Pulse phá mảnh Memory Collapse trong bán kính. Trả số mảnh vỡ. */
  pulseFragments(cx: number, cy: number, r: number, emit: (e: GameEvent) => void): number {
    let n = 0;
    for (const f of this.fragments) {
      if (f.hp <= 0) continue;
      if (Math.hypot(f.x - cx, f.y - cy) <= r + 6) {
        f.hp = 0;
        n += 1;
        emit({ t: "fx", name: "memoryGlow", x: f.x, y: f.y, n: 8 });
      }
    }
    if (n > 0) emit({ t: "sfx", name: "glyph", x: cx, y: cy });
    this.checkCollapseDone(emit);
    return n;
  }

  /** Lưỡi chém trúng mảnh/đạn glyph. Trả loại vật bị trúng (để cộng Ink) hoặc null. */
  slashAt(rect: Rect, damage: number, emit: (e: GameEvent) => void, seen: Set<number>): "fragment" | "shot" | null {
    for (const f of this.fragments) {
      const key = -1000 - f.id;
      if (f.hp > 0 && !seen.has(key) && overlapPoint(rect, f.x, f.y, 6)) {
        seen.add(key);
        f.hp -= f.cracked ? damage + 1 : damage;
        f.flash = 6;
        if (f.hp <= 0) {
          emit({ t: "fx", name: "memoryGlow", x: f.x, y: f.y, n: 8 });
          emit({ t: "sfx", name: "glyph", x: f.x, y: f.y });
          this.checkCollapseDone(emit);
        }
        return "fragment";
      }
    }
    for (let i = this.shots.length - 1; i >= 0; i -= 1) {
      const s = this.shots[i];
      if (overlapPoint(rect, s.x, s.y, 5)) {
        this.shots.splice(i, 1);
        emit({ t: "fx", name: "spark", x: s.x, y: s.y, n: 5 });
        return "shot";
      }
    }
    return null;
  }

  private checkCollapseDone(emit: (e: GameEvent) => void): void {
    if (this.state === "collapse" && this.fragments.every((f) => f.hp <= 0)) {
      this.fragments = [];
      this.state = "stunned";
      this.stun = BOSS.stunAfterCollapse;
      this.invuln = false;
      this.t = 0;
      emit({ t: "sfx", name: "bossPhase", x: this.x, y: this.y });
      emit({ t: "shake", amount: 3, frames: 14 });
      emit({ t: "fx", name: "memoryGlow", x: this.x, y: this.y - 22, n: 16 });
    }
  }

  private beginStagger(emit: (e: GameEvent) => void): void {
    this.phase = 2;
    this.state = "stagger";
    this.t = 0;
    this.attack = null;
    this.invuln = true;
    this.lines.length = 0;
    this.zones.length = 0;
    this.waves.length = 0;
    this.shots.length = 0;
    this.sched.reset();
    emit({ t: "bossPhase", phase: 2 });
    emit({ t: "sfx", name: "bossPhase", x: this.x, y: this.y });
    emit({ t: "shake", amount: 4, frames: 24 });
    emit({ t: "caption", id: "boss.phase2" });
  }

  private die(emit: (e: GameEvent) => void): void {
    this.state = "dying";
    this.t = 0;
    this.dyingT = 150;
    this.attack = null;
    this.invuln = true;
    this.lines.length = 0;
    this.zones.length = 0;
    this.waves.length = 0;
    this.shots.length = 0;
    this.fragments = [];
    emit({ t: "bossPhase", phase: "dying" });
    emit({ t: "sfx", name: "bossDie", x: this.x, y: this.y });
    emit({ t: "shake", amount: 5, frames: 40 });
  }

  /** Những vùng đang gây sát thương lên người chơi. */
  hazards(): BossHazard[] {
    const out: BossHazard[] = [];
    const s = this.slashBox();
    if (s) out.push({ rect: s, damage: 1, kind: "slash" });
    for (const l of this.lines) if (l.t >= l.telegraph && l.t < l.telegraph + l.active) out.push({ rect: l.rect, damage: 1, kind: "line" });
    for (const z of this.zones) {
      if (z.t >= z.telegraph && z.t < z.telegraph + z.active) out.push({ rect: { x: z.x - z.w / 2, y: this.floorY - 14 * TILE, w: z.w, h: 14 * TILE }, damage: 1, kind: "zone" });
    }
    for (const w of this.waves) out.push({ rect: { x: w.x - 7, y: w.y - 16, w: 14, h: 16 }, damage: 1, kind: "wave" });
    for (const p of this.shots) out.push({ rect: { x: p.x - 4, y: p.y - 4, w: 8, h: 8 }, damage: 1, kind: "projectile" });
    for (const f of this.fragments) if (f.hp > 0) out.push({ rect: { x: f.x - 5, y: f.y - 5, w: 10, h: 10 }, damage: 1, kind: "fragment" });
    return out;
  }

  /** Hộp lưỡi gươm đang chém (Revision Slash / Rewrite / Revision Rush). */
  private slashBox(): Rect | null {
    if (this.state !== "active") return null;
    const front = (w: number, h: number, back = 4): Rect => ({
      x: this.facing === 1 ? this.x - back : this.x - w + back,
      y: this.y - h,
      w,
      h,
    });
    if (this.attack === "revisionSlash" && this.step === 1) return front(40, 26, 6);
    if (this.attack === "revisionRush" && this.step % 2 === 1) return front(38, 22, 6);
    if (this.attack === "rewrite" && this.step === 3) return front(40, 30, 6);
    return null;
  }

  update(ctx: BossCtx): void {
    this.anim += 1;
    if (this.flash > 0) this.flash -= 1;
    if (this.pulseCooldown > 0) this.pulseCooldown -= 1;
    this.t += 1;
    this.updateHazards(ctx);

    switch (this.state) {
      case "dormant":
        return;
      case "intro":
        this.face(ctx.px);
        if (this.t === 1) ctx.emit({ t: "caption", id: "boss.intro" });
        if (this.t >= 100) this.goNeutral();
        return;
      case "neutral": {
        this.face(ctx.px);
        const d = Math.abs(ctx.px - this.x);
        if (d > 56) this.moveTo(this.x + this.facing * 0.9);
        if (this.t >= this.neutralFor) this.startAttack(ctx);
        return;
      }
      case "telegraph":
        this.updateTelegraph(ctx);
        return;
      case "active":
        this.updateActive(ctx);
        return;
      case "recover":
        if (this.t >= BOSS_ATTACKS[this.attack ?? "revisionSlash"].recover) this.goNeutral();
        return;
      case "stagger":
        if (this.t >= BOSS.staggerFrames) {
          this.invuln = false;
          this.beginCollapse(ctx);
        }
        return;
      case "stunned":
        this.stun -= 1;
        if (this.stun <= 0) this.goNeutral();
        return;
      case "collapse":
        this.updateCollapse(ctx);
        return;
      case "dying":
        this.dyingT -= 1;
        if (this.dyingT <= 0) this.state = "dead";
        return;
      default:
        return;
    }
  }

  private face(px: number): void {
    this.facing = px >= this.x ? 1 : -1;
  }

  private moveTo(x: number): void {
    this.x = Math.max(this.left + BOSS.w / 2, Math.min(this.right - BOSS.w / 2, x));
  }

  private goNeutral(): void {
    this.state = "neutral";
    this.t = 0;
    this.attack = null;
    this.step = 0;
    this.visible = true;
    this.neutralFor = this.phase === 1 ? 34 + this.rng.int(30) : 22 + this.rng.int(24);
  }

  private startAttack(ctx: BossCtx): void {
    const dist = Math.abs(ctx.px - this.x);
    // Memory Collapse thứ hai: một lần khi máu thấp.
    if (this.phase === 2 && this.collapses === 1 && this.hp <= BOSS.collapse2At) {
      this.beginCollapse(ctx);
      return;
    }
    this.attack = this.sched.next(this.phase, dist);
    this.state = "telegraph";
    this.t = 0;
    this.step = 0;
    this.lockX = ctx.px;
    this.lockY = ctx.py;
    ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
  }

  // ---------------------------------------------------------------- báo trước
  private updateTelegraph(ctx: BossCtx): void {
    const a = this.attack as BossAttack;
    const spec = BOSS_ATTACKS[a];
    this.face(ctx.px);
    // Theo dõi mục tiêu tới ~8 khung cuối rồi KHOÁ: người chơi luôn có khoảng đọc-và-phản-ứng.
    if (this.t < spec.telegraph - 8) {
      this.lockX = ctx.px;
      this.lockY = ctx.py;
    }
    if (this.t === 1) this.spawnTelegraphHazards(ctx, a);
    if (a === "rewrite" && this.t === 1) this.visible = true;
    if (this.t >= spec.telegraph) {
      this.state = "active";
      this.t = 0;
      this.step = 0;
      this.beginActive(ctx, a);
    }
  }

  private beginActive(ctx: BossCtx, a: BossAttack): void {
    switch (a) {
      case "revisionSlash":
        this.facing = this.lockX >= this.x ? 1 : -1;
        this.step = 1;
        break;
      case "blackLine":
        ctx.emit({ t: "sfx", name: "glyph", x: this.x, y: this.y });
        break;
      case "marginCut":
        ctx.emit({ t: "shake", amount: 2, frames: 10 });
        this.waves.push({ x: this.x, y: this.floorY, dir: -1, life: 120 }, { x: this.x, y: this.floorY, dir: 1, life: 120 });
        ctx.emit({ t: "sfx", name: "bossHit", x: this.x, y: this.floorY });
        break;
      case "rewrite":
        this.visible = false; // biến mất
        this.step = 1;
        break;
      case "delete":
        break;
      case "brokenSentence":
        this.fireSentence(ctx);
        break;
      case "revisionRush":
        this.facing = this.lockX >= this.x ? 1 : -1;
        this.step = 0;
        break;
      default:
        break;
    }
  }

  /** Vùng báo trước đứng yên (Black Line / Delete) xuất hiện NGAY khi bắt đầu báo trước — người chơi có đủ cả pha báo trước để rời đi. */
  private spawnTelegraphHazards(ctx: BossCtx, a: BossAttack): void {
    if (a === "blackLine") {
      const spec = BOSS_ATTACKS.blackLine;
      // Một đường mực chạy ngang tầm thấp (nhảy qua) HOẶC một cột dọc (bước ra) — chọn bằng hạt giống.
      if (this.rng.next() < 0.5) {
        const span = 12 * TILE;
        const side = ctx.px < (this.left + this.right) / 2 ? this.left : this.right - span;
        this.lines.push({ horizontal: true, rect: { x: side, y: this.floorY - 10, w: span, h: 10 }, t: 0, telegraph: spec.telegraph, active: spec.active });
      } else {
        const w = 20;
        const x = Math.max(this.left, Math.min(this.right - w, ctx.px - w / 2));
        this.lines.push({ horizontal: false, rect: { x, y: this.floorY - 12 * TILE, w, h: 12 * TILE }, t: 0, telegraph: spec.telegraph, active: spec.active });
      }
    } else if (a === "delete") {
      const w = 5 * TILE;
      this.zones.push({ x: Math.max(this.left + w / 2, Math.min(this.right - w / 2, ctx.px)), w, t: 0, telegraph: BOSS_ATTACKS.delete.telegraph, active: BOSS_ATTACKS.delete.active });
    }
  }

  // ---------------------------------------------------------------- đang thực hiện
  private updateActive(ctx: BossCtx): void {
    const a = this.attack as BossAttack;
    switch (a) {
      case "revisionSlash": {
        this.moveTo(this.x + this.facing * 4.6);
        const passed = (this.facing === 1 && this.x >= this.lockX + 36) || (this.facing === -1 && this.x <= this.lockX - 36);
        if (this.t >= 30 || passed || this.atWall()) this.endActive();
        break;
      }
      case "blackLine":
        if (this.t >= 26) this.endActive();
        break;
      case "marginCut":
        if (this.t >= 20 && this.waves.length === 0) this.endActive();
        else if (this.t >= 60) this.endActive();
        break;
      case "rewrite": {
        if (this.step === 1 && this.t >= 8) {
          // xuất hiện sau lưng người chơi
          const behind = ctx.px - this.facingOf(ctx.px) * 56;
          this.x = Math.max(this.left + BOSS.w / 2, Math.min(this.right - BOSS.w / 2, behind));
          this.visible = true;
          this.face(ctx.px);
          this.step = 2;
          this.t = 0;
          ctx.emit({ t: "fx", name: "inkSplash", x: this.x, y: this.y - 22, n: 10 });
          ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
        } else if (this.step === 2 && this.t >= 16) {
          this.step = 3; // chém nhanh sau khi hiện ra (báo trước 16 khung)
          this.t = 0;
        } else if (this.step === 3 && this.t >= 7) {
          this.endActive();
        }
        break;
      }
      case "delete":
        if (this.t >= 8) this.endActive();
        break;
      case "brokenSentence":
        if (this.t >= 20) this.endActive();
        break;
      case "revisionRush": {
        // Ba cú lao nhịp 1-2-3: mỗi cú có phần báo trước 24 khung ở đầu (đứng chuẩn bị), rồi lao 18 khung, nghỉ 10.
        const seg = this.rushSegment();
        if (seg.kind === "windup") {
          this.step = seg.idx * 2; // chẵn = không chém
          if (seg.t === 0) {
            this.lockX = ctx.px;
            this.facing = this.lockX >= this.x ? 1 : -1;
            ctx.emit({ t: "sfx", name: "telegraph", x: this.x, y: this.y });
          }
          if (seg.t < 16) {
            this.lockX = ctx.px;
            this.facing = this.lockX >= this.x ? 1 : -1;
          }
        } else if (seg.kind === "dash") {
          this.step = seg.idx * 2 + 1;
          this.moveTo(this.x + this.facing * 5.2);
          if (this.atWall()) this.facing = (-this.facing) as Facing;
        } else if (seg.kind === "pause") {
          this.step = seg.idx * 2;
        } else {
          this.endActive();
        }
        break;
      }
      default:
        break;
    }
  }

  private rushSegment(): { kind: "windup" | "dash" | "pause" | "done"; idx: number; t: number } {
    // mỗi cú: windup 24 + dash 18 + pause 10 = 52 khung; 3 cú = 156
    const per = 52;
    const idx = Math.floor(this.t / per);
    if (idx >= 3) return { kind: "done", idx, t: 0 };
    const t = this.t - idx * per;
    if (t < 24) return { kind: "windup", idx, t };
    if (t < 42) return { kind: "dash", idx, t: t - 24 };
    return { kind: "pause", idx, t: t - 42 };
  }

  private facingOf(px: number): number {
    return px >= this.x ? -1 : 1; // hướng từ người chơi về phía boss (để đứng "sau lưng")
  }

  private atWall(): boolean {
    return this.x <= this.left + BOSS.w / 2 + 0.5 || this.x >= this.right - BOSS.w / 2 - 0.5;
  }

  private endActive(): void {
    this.state = "recover";
    this.t = 0;
    this.step = 0;
  }

  // ---------------------------------------------------------------- Broken Sentence
  private fireSentence(ctx: BossCtx): void {
    const pattern = this.rng.int(3);
    const sx = this.x;
    const sy = this.y - 30;
    const add = (vx: number, vy: number): void => {
      this.shots.push({ x: sx, y: sy, vx, vy, life: 200, id: shotId++ });
    };
    if (pattern === 0) {
      // quạt 5 viên
      for (let i = -2; i <= 2; i += 1) {
        const ang = Math.atan2(ctx.py - 10 - sy, ctx.px - sx) + i * 0.28;
        add(Math.cos(ang) * 1.7, Math.sin(ang) * 1.7);
      }
    } else if (pattern === 1) {
      // hàng ngang bắn lần lượt (ba tầng cao khác nhau, giãn cách để đọc được)
      const dir = this.facing;
      for (let i = 0; i < 4; i += 1) {
        const s = { x: sx, y: this.floorY - 12 - i * 18, vx: dir * 1.6, vy: 0, life: 220, id: shotId++ };
        s.x -= dir * i * 10; // lệch pha: viên sau cách viên trước 10px theo hướng bay
        this.shots.push(s);
      }
    } else {
      // ba viên nhắm thẳng, giãn nhịp
      const base = Math.atan2(ctx.py - 10 - sy, ctx.px - sx);
      for (let i = 0; i < 3; i += 1) {
        const s = { x: sx - Math.cos(base) * i * 14, y: sy - Math.sin(base) * i * 14, vx: Math.cos(base) * 1.5, vy: Math.sin(base) * 1.5, life: 220, id: shotId++ };
        this.shots.push(s);
      }
    }
    ctx.emit({ t: "sfx", name: "glyph", x: sx, y: sy });
  }

  // ---------------------------------------------------------------- Memory Collapse
  private beginCollapse(ctx: BossCtx): void {
    this.collapses += 1;
    this.state = "collapse";
    this.t = 0;
    this.attack = "memoryCollapse";
    this.invuln = true;
    this.visible = true;
    this.lines.length = 0;
    this.zones.length = 0;
    this.waves.length = 0;
    this.shots.length = 0;
    this.x = (this.left + this.right) / 2;
    const cracked = Math.min(BOSS.fragments, ctx.memories);
    this.fragments = [];
    for (let i = 0; i < BOSS.fragments; i += 1) {
      this.fragments.push({
        id: fragId++, angle: (i / BOSS.fragments) * Math.PI * 2, hp: BOSS.fragmentHp, cracked: i < cracked, flash: 0, fireT: 80 + i * 40, x: this.x, y: this.y - 26,
      });
    }
    ctx.emit({ t: "caption", id: "boss.collapse" });
    ctx.emit({ t: "sfx", name: "bossPhase", x: this.x, y: this.y });
  }

  private updateCollapse(ctx: BossCtx): void {
    this.face(ctx.px);
    const cx = this.x;
    const cy = this.y - 26;
    for (const f of this.fragments) {
      if (f.hp <= 0) continue;
      f.angle += 0.028;
      f.x = cx + Math.cos(f.angle) * BOSS.fragmentRadius;
      f.y = cy + Math.sin(f.angle) * (BOSS.fragmentRadius * 0.6);
      if (f.flash > 0) f.flash -= 1;
      f.fireT -= 1;
      if (f.fireT <= 0) {
        f.fireT = 150;
        const ang = Math.atan2(ctx.py - 10 - f.y, ctx.px - f.x);
        this.shots.push({ x: f.x, y: f.y, vx: Math.cos(ang) * 1.2, vy: Math.sin(ang) * 1.2, life: 200, id: shotId++ });
        ctx.emit({ t: "sfx", name: "glyph", x: f.x, y: f.y });
      }
    }
    // Chống kẹt: người chơi tránh mãi thì mảnh tan sau ~12 giây và boss chuyển sang choáng ngắn (không phạt thêm).
    if (this.t >= BOSS_ATTACKS.memoryCollapse.active) {
      this.fragments = [];
      this.state = "stunned";
      this.stun = 40;
      this.invuln = false;
      this.t = 0;
    }
  }

  // ---------------------------------------------------------------- hazard chạy nền
  private updateHazards(ctx: BossCtx): void {
    for (let i = this.lines.length - 1; i >= 0; i -= 1) {
      this.lines[i].t += 1;
      if (this.lines[i].t >= this.lines[i].telegraph + this.lines[i].active) this.lines.splice(i, 1);
    }
    for (let i = this.zones.length - 1; i >= 0; i -= 1) {
      this.zones[i].t += 1;
      if (this.zones[i].t >= this.zones[i].telegraph + this.zones[i].active) this.zones.splice(i, 1);
    }
    for (let i = this.waves.length - 1; i >= 0; i -= 1) {
      const w = this.waves[i];
      w.x += w.dir * 2.2;
      w.life -= 1;
      if (w.life <= 0 || w.x < this.left || w.x > this.right) this.waves.splice(i, 1);
    }
    for (let i = this.shots.length - 1; i >= 0; i -= 1) {
      const s = this.shots[i];
      s.x += s.vx;
      s.y += s.vy;
      s.life -= 1;
      if (s.life <= 0 || ctx.map.solid(Math.floor(s.x / TILE), Math.floor(s.y / TILE)) || s.x < this.left - 8 || s.x > this.right + 8) this.shots.splice(i, 1);
    }
  }
}

function overlapPoint(r: Rect, x: number, y: number, rad: number): boolean {
  return x + rad > r.x && x - rad < r.x + r.w && y + rad > r.y && y - rad < r.y + r.h;
}

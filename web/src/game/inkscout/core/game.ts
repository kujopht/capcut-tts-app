import { Boss } from "./boss";
import { BLADE, FALL_DEATH_MARGIN, HITSTOP_PLAYER_HURT, PLAYER, PULSE, TILE } from "./constants";
import { Enemy, enemyOverlaps, resetEnemyIds } from "./enemies";
import { CAPTIONS, ENDINGS } from "./lore";
import { Player, type PlayerAbilities } from "./player";
import { room, rooms, spawnPos, type CycleHazard, type RoomDef } from "./rooms";
import { defaultSave, endingEligibility, sanitizeSave, type CheckpointId, type SaveData } from "./save";
import { footToRect, rectsOverlap, T, TileMap } from "./tilemap";
import type { EndingKind, GameEvent, InputState, MemoryId, Rect, RoomId } from "./types";
import { NO_INPUT } from "./types";

export type GameMode = "play" | "read" | "dead" | "ending" | "complete";
export type EndingStage = "choice" | "pages";

export interface GameOptions {
  save?: SaveData;
  seed?: number;
}

export interface GameResult {
  ending: EndingKind;
  memories: MemoryId[];
  /** Tổng số khung hình đã chơi (60 = 1 giây). */
  frames: number;
  deaths: number;
  bestFrames: number;
}

export interface CycleState {
  /** 0 = nghỉ, 1 = báo trước, 2 = nguy hiểm. */
  phase: 0 | 1 | 2;
  /** Số khung đã trôi trong pha hiện tại. */
  t: number;
}

const READ_MIN_FRAMES = 30;
const DEATH_FRAMES = 84;

/** Vị trí hồi sinh của một Dấu Trang (tra từ dữ liệu phòng — nguồn duy nhất). */
export function checkpointSpawn(id: CheckpointId): { room: RoomId; x: number; y: number } {
  if (id === "start") {
    const def = room("entrance");
    const s = spawnPos(def, "start");
    return { room: "entrance", x: s.x, y: s.y };
  }
  for (const def of Object.values(rooms())) {
    for (const t of def.things) {
      if (t.kind === "checkpoint" && t.id === id) return { room: def.id, x: t.tx * TILE + TILE / 2, y: (t.ty + 1) * TILE };
    }
  }
  throw new Error(`checkpoint không tồn tại: ${id}`);
}

export function cycleState(c: CycleHazard, roomT: number): CycleState {
  const p = (roomT + c.offset) % c.period;
  if (p < c.telegraph) return { phase: 1, t: p };
  if (p < c.telegraph + c.active) return { phase: 2, t: p - c.telegraph };
  return { phase: 0, t: p - c.telegraph - c.active };
}

function cycleRect(c: CycleHazard): Rect {
  return { x: c.tx * TILE, y: c.ty * TILE, w: c.tw * TILE, h: c.th * TILE };
}

/**
 * Mô phỏng toàn bộ game: bước cố định 60 Hz, KHÔNG biết đến DOM/Canvas/thời gian thực. `step(input)` tiến một khung; mọi hiệu ứng ra ngoài là
 * `GameEvent` (đọc bằng `drainEvents()`). Cùng `seed` + cùng chuỗi `InputState` ⇒ cùng kết quả — nền tảng của replay/test/QA bot.
 */
export class Game {
  readonly save: SaveData;
  readonly seed: number;
  player: Player;
  roomId: RoomId = "entrance";
  def: RoomDef;
  map: TileMap;
  enemies: Enemy[] = [];
  boss: Boss | null = null;
  mode: GameMode = "play";
  /** Số khung từ lúc vào phòng (đồng hồ của thanh Redaction). */
  roomT = 0;
  /** Số khung mô phỏng đã chạy (kể cả lúc đọc/kết thúc). */
  frame = 0;
  hitStop = 0;
  /** Khung mờ-dần-vào còn lại sau khi đổi phòng (lớp vẽ). */
  fade = 0;
  bossLocked = false;
  // đọc ký ức/khả năng
  readKind: "memory" | "ability" | null = null;
  readId: string | null = null;
  readT = 0;
  // chết
  deadT = 0;
  // kết thúc
  endingStage: EndingStage = "pages";
  endingKind: EndingKind | null = null;
  endingChoice: 0 | 1 = 0;
  endingPage = 0;
  endingT = 0;
  readonly abilities: PlayerAbilities = { marginStep: false, pulseWide: false, pulseCheap: false };

  private events: GameEvent[] = [];
  private readonly spoken = new Set<string>();
  private readonly spokenSession = new Set<string>();
  private readonly visited = new Set<RoomId>();
  private prev: InputState = { ...NO_INPUT };
  private nearCheckpoint: string | null = null;
  private readonly pulseHit = new Set<number>();
  private pulseGlyphSfx = false;
  private pulseBossHit = false;
  readonly emit = (e: GameEvent): void => this.onEvent(e);

  constructor(opts: GameOptions = {}) {
    resetEnemyIds();
    this.save = sanitizeSave(opts.save ?? defaultSave());
    this.seed = (opts.seed ?? 0x1ee7) >>> 0;
    this.player = new Player();
    this.def = room("entrance");
    this.map = new TileMap(this.def.tiles);
    this.refreshAbilities();
    this.player.hp = this.player.maxHp;
    const cp = checkpointSpawn(this.save.checkpoint);
    this.loadRoom(cp.room, { x: cp.x, y: cp.y, facing: 1 });
  }

  // ------------------------------------------------------------------ truy cập
  has(id: MemoryId): boolean {
    return this.save.memories.includes(id);
  }

  get memoryCount(): number {
    return this.save.memories.length;
  }

  drainEvents(): GameEvent[] {
    const e = this.events;
    this.events = [];
    return e;
  }

  snapshot(): SaveData {
    return { ...this.save, memories: [...this.save.memories], settings: { ...this.save.settings } };
  }

  result(): GameResult | null {
    if (this.mode !== "complete" || !this.save.ending) return null;
    return {
      ending: this.save.ending,
      memories: [...this.save.memories],
      frames: this.save.playFrames,
      deaths: this.save.deaths,
      bestFrames: this.save.bestFrames ?? this.save.playFrames,
    };
  }

  setSettings(patch: Partial<SaveData["settings"]>): void {
    Object.assign(this.save.settings, patch);
    this.save.settings = sanitizeSave({ settings: this.save.settings }).settings;
    this.emit({ t: "save" });
  }

  endingPages(): readonly string[] {
    const k = this.endingKind ?? "basic";
    const key = k === "basic" && this.memoryCount >= 2 ? "basic2" : k;
    return ENDINGS[key].pages;
  }

  private onEvent(e: GameEvent): void {
    if (e.t === "caption" && e.id.startsWith("boss.")) {
      // Lời của Redactor thay đổi theo số Memory người chơi đã nhớ (ký ức thật sự đổi cuộc đối thoại).
      const n = this.memoryCount;
      const variants = n >= 3 ? [`${e.id}.m3`, `${e.id}.m2`] : n >= 2 ? [`${e.id}.m2`] : [];
      const hit = variants.find((v) => CAPTIONS[v] !== undefined);
      if (hit) e = { ...e, id: hit };
    }
    if (this.events.length > 4000) this.events.splice(0, 2000);
    this.events.push(e);
  }

  private refreshAbilities(): void {
    this.abilities.marginStep = this.save.marginStep;
    this.abilities.pulseWide = this.has(2);
    this.abilities.pulseCheap = this.has(3);
    this.player.maxHp = PLAYER.maxHp + (this.has(1) ? 1 : 0);
    this.player.hp = Math.min(this.player.hp, this.player.maxHp);
  }

  // ------------------------------------------------------------------ phòng
  private loadRoom(id: RoomId, at: { x: number; y: number; facing: 1 | -1 }): void {
    const def = room(id);
    this.def = def;
    this.roomId = id;
    this.map = new TileMap(def.tiles);
    resetEnemyIds();
    this.enemies = def.enemies.map((d) => new Enemy(d));
    this.roomT = 0;
    this.spoken.clear();
    this.nearCheckpoint = null;
    this.boss = null;
    this.bossLocked = false;
    this.pulseHit.clear();
    if (id === "arena") {
      if (!this.save.bossDefeated) {
        const right = (def.tiles[0].length - 1) * TILE;
        const seed = (this.seed ^ Math.imul(this.save.deaths + 1, 0x9e3779b1)) >>> 0;
        this.boss = new Boss(11 * TILE, TILE, right, seed);
        this.setDoors(def, true, true);
      }
    }
    this.player.place(at.x, at.y);
    this.player.facing = at.facing;
    this.fade = 14;
    this.emit({ t: "roomEnter", room: id, first: !this.visited.has(id) });
    this.visited.add(id);
  }

  /** Khoá/mở hai cánh cửa của đấu trường (ô đặc thay cho lối ra). */
  private setDoors(def: RoomDef, left: boolean, right: boolean): void {
    const w = def.tiles[0].length;
    for (const ex of def.exits) {
      for (let ty = ex.ty; ty < ex.ty + ex.th; ty += 1) {
        for (let tx = ex.tx; tx < ex.tx + ex.tw; tx += 1) {
          if (tx === 0) this.map.setCell(tx, ty, left ? T.SOLID : T.AIR);
          else if (tx === w - 1) this.map.setCell(tx, ty, right ? T.SOLID : T.AIR);
        }
      }
    }
  }

  /** Cửa ra của đấu trường đang bị khoá? (lớp vẽ vẽ ổ khoá). */
  doorLocked(side: "left" | "right"): boolean {
    if (this.roomId !== "arena") return false;
    const w = this.def.tiles[0].length;
    return this.map.kind(side === "left" ? 0 : w - 1, 9) === T.SOLID;
  }

  private respawn(): void {
    const p = this.player;
    p.hp = p.maxHp;
    p.ink = 0;
    p.invuln = PLAYER.invulnFrames;
    p.hurt = 0;
    this.mode = "play";
    this.deadT = 0;
    const cp = checkpointSpawn(this.save.checkpoint);
    this.loadRoom(cp.room, { x: cp.x, y: cp.y, facing: 1 });
    p.invuln = PLAYER.invulnFrames;
    this.emit({ t: "sfx", name: "ui" });
  }

  // ------------------------------------------------------------------ bước mô phỏng
  step(input: Readonly<InputState>): void {
    this.frame += 1;
    const pressed = {
      confirm: input.confirm && !this.prev.confirm,
      any: (input.confirm && !this.prev.confirm) || (input.jump && !this.prev.jump) || (input.attack && !this.prev.attack),
      left: input.left && !this.prev.left,
      right: input.right && !this.prev.right,
    };
    switch (this.mode) {
      case "play":
        this.stepPlay(input);
        break;
      case "read":
        this.readT += 1;
        if (this.readT >= READ_MIN_FRAMES && pressed.any) {
          this.mode = "play";
          this.readKind = null;
          this.readId = null;
        }
        break;
      case "dead":
        this.save.playFrames += 1;
        this.deadT += 1;
        if (this.deadT >= DEATH_FRAMES) this.respawn();
        break;
      case "ending":
        this.stepEnding(pressed);
        break;
      default:
        break;
    }
    this.prev = { ...input };
  }

  private stepPlay(input: Readonly<InputState>): void {
    this.save.playFrames += 1;
    if (this.hitStop > 0) {
      this.hitStop -= 1;
      return;
    }
    this.roomT += 1;
    if (this.fade > 0) this.fade -= 1;
    this.map.tick();
    const p = this.player;
    p.update({ map: this.map, input, abilities: this.abilities, emit: this.emit });
    this.resolveBlade();
    this.applyPulse();

    const px = p.x;
    const py = p.y;
    for (const e of this.enemies) e.update({ map: this.map, px, py, emit: this.emit });
    this.enemies = this.enemies.filter((e) => e.alive);

    if (this.boss) {
      this.boss.update({ map: this.map, px, py, memories: this.memoryCount, emit: this.emit });
      if (this.boss.state === "dead") this.bossDefeated();
    }

    this.resolveDamage();
    this.resolveEnvironment();
    this.processThings();
    if (this.mode !== "play") return;
    if (this.checkExits()) return;
    if (p.hp <= 0) this.die();
  }

  // ------------------------------------------------------------------ chiến đấu
  private resolveBlade(): void {
    const p = this.player;
    const atk = p.attackBox();
    if (!atk) return;
    const hits = p.attackHit;
    let landed = 0;
    for (const e of this.enemies) {
      if (hits.has(e.id) || !enemyOverlaps(e, atk.rect)) continue;
      hits.add(e.id);
      e.hit(atk.damage, e.x >= p.x ? 1 : -1, this.emit);
      this.emit({ t: "sfx", name: "hit", x: e.x, y: e.y });
      this.emit({ t: "fx", name: "spark", x: e.x, y: e.y - e.spec.h / 2, dir: p.facing, n: 5 });
      landed += 1;
    }
    const b = this.boss;
    if (b && b.active) {
      if (!hits.has(-1) && rectsOverlap(b.hurtbox, atk.rect) && b.vulnerable) {
        hits.add(-1);
        if (b.hit(atk.damage, this.emit)) {
          this.emit({ t: "fx", name: "spark", x: b.x, y: b.y - 24, dir: p.facing, n: 6 });
          landed += 1;
        }
      }
      if (b.slashAt(atk.rect, atk.damage, this.emit, hits)) landed += 1;
    }
    if (landed > 0) {
      p.ink = Math.min(PLAYER.maxInk, p.ink + landed * BLADE.inkPerHit);
      this.hitStop = Math.max(this.hitStop, atk.heavy ? BLADE.hitStopHeavy : BLADE.hitStop);
      this.emit({ t: "shake", amount: atk.heavy ? 2.5 : 1.5, frames: 6 });
    }
  }

  /** Memory Pulse: áp dụng liên tục theo bán kính đang mở rộng; mỗi đối tượng chỉ bị tính một lần mỗi lần tung. */
  private applyPulse(): void {
    const p = this.player;
    if (p.pulseT === PULSE.windup + 1) {
      this.pulseHit.clear();
      this.pulseGlyphSfx = false;
      this.pulseBossHit = false;
      this.emit({ t: "fx", name: "pulseRing", x: p.x, y: p.y - 8, n: 1 });
    }
    if (!p.pulseActive) return;
    const r = p.pulseRadius;
    const cx = p.x;
    const cy = p.y - 8;
    if (this.map.revealGlyphs(cx, cy, r, PULSE.glyphRevealFrames) > 0 && !this.pulseGlyphSfx) {
      this.pulseGlyphSfx = true;
      this.emit({ t: "sfx", name: "glyph", x: cx, y: cy });
    }
    for (const e of this.enemies) {
      if (this.pulseHit.has(e.id) || e.state === "dying") continue;
      if (Math.hypot(e.x - cx, e.y - e.spec.h / 2 - cy) <= r + e.spec.w / 2) {
        this.pulseHit.add(e.id);
        e.disrupt(e.kind === "broken" ? PULSE.stunFramesElite : PULSE.stunFrames);
        this.emit({ t: "fx", name: "memoryGlow", x: e.x, y: e.y - e.spec.h / 2, n: 6 });
      }
    }
    for (const th of this.def.things) {
      if (th.kind !== "glyphLore" || this.spoken.has(th.id)) continue;
      if (Math.hypot(th.tx * TILE + TILE / 2 - cx, th.ty * TILE + TILE / 2 - cy) <= r + 8) {
        this.spoken.add(th.id);
        this.emit({ t: "caption", id: th.id });
      }
    }
    const b = this.boss;
    if (b && b.active) {
      if (!this.pulseBossHit && Math.hypot(b.x - cx, b.y - 22 - cy) <= r + 14) {
        this.pulseBossHit = true;
        b.pulseHit(this.emit);
      }
      b.pulseFragments(cx, cy, r, this.emit);
      b.pulseShots(cx, cy, r, this.emit);
    }
  }

  private hurt(srcX: number, dmg: number): void {
    if (this.player.takeHit(srcX, dmg, this.emit)) this.hitStop = Math.max(this.hitStop, HITSTOP_PLAYER_HURT);
  }

  private resolveDamage(): void {
    const p = this.player;
    if (p.hp <= 0) return;
    const body = footToRect(p.foot);
    for (const e of this.enemies) {
      const cb = e.contactBox;
      if (cb && rectsOverlap(cb, body)) this.hurt(e.x, e.damage);
      const ab = e.attackBox;
      if (ab && rectsOverlap(ab, body)) this.hurt(e.x, 1);
    }
    const b = this.boss;
    if (b && b.active) {
      for (const h of b.hazards()) if (rectsOverlap(h.rect, body)) this.hurt(h.rect.x + h.rect.w / 2, h.damage);
    }
    for (const c of this.def.cycles) {
      if (cycleState(c, this.roomT).phase === 2 && rectsOverlap(cycleRect(c), body)) this.hurt(c.tx * TILE + (c.tw * TILE) / 2, 1);
    }
  }

  /** Gai và rơi khỏi bản đồ: mất 1 máu (nếu không bất tử) rồi về chỗ an toàn gần nhất — không mất phòng. */
  private resolveEnvironment(): void {
    const p = this.player;
    if (p.hp <= 0) return;
    const fell = p.y > this.map.pxH + FALL_DEATH_MARGIN;
    if (this.map.hitsSpike(p.foot) || fell) {
      if (!p.invulnerable) {
        p.hp = Math.max(0, p.hp - 1);
        this.emit({ t: "sfx", name: "hurt", x: p.x, y: p.y });
        this.emit({ t: "shake", amount: 3, frames: 10 });
        this.emit({ t: "fx", name: "inkSplash", x: p.x, y: p.y - 6, n: 8 });
      }
      p.returnToSafe();
      this.hitStop = Math.max(this.hitStop, 4);
    }
  }

  // ------------------------------------------------------------------ vật thể trong phòng
  private near(tx: number, ty: number, rx = 14, ry = 26): boolean {
    const p = this.player;
    return Math.abs(p.x - (tx * TILE + TILE / 2)) <= rx && Math.abs(p.y - (ty + 1) * TILE) <= ry;
  }

  private processThings(): void {
    const p = this.player;
    const body = footToRect(p.foot);
    for (const th of this.def.things) {
      switch (th.kind) {
        case "checkpoint": {
          const n = this.near(th.tx, th.ty, 18, 26);
          if (n && this.nearCheckpoint !== th.id) {
            this.nearCheckpoint = th.id;
            const isNew = this.save.checkpoint !== th.id;
            if (isNew || p.hp < p.maxHp) {
              this.save.checkpoint = th.id as CheckpointId;
              p.hp = p.maxHp;
              this.emit({ t: "sfx", name: "checkpoint", x: p.x, y: p.y });
              this.emit({ t: "fx", name: "memoryGlow", x: th.tx * TILE + TILE / 2, y: th.ty * TILE, n: 10 });
              this.emit({ t: "checkpoint", room: this.roomId });
              if (isNew) this.emit({ t: "caption", id: "checkpoint" });
              this.emit({ t: "save" });
            }
          } else if (!n && this.nearCheckpoint === th.id) {
            this.nearCheckpoint = null;
          }
          break;
        }
        case "memory":
          if (!this.has(th.id) && this.near(th.tx, th.ty, 14, 16)) this.collectMemory(th.id, th.tx, th.ty);
          break;
        case "marginStep":
          if (!this.save.marginStep && this.near(th.tx, th.ty, 14, 16)) this.collectMarginStep(th.tx, th.ty);
          break;
        case "echo":
        case "sign": {
          const range = th.range ?? 40;
          const key = th.id;
          if (this.spoken.has(key) || (key.startsWith("tut.") && this.spokenSession.has(key))) break;
          if (Math.abs(p.x - (th.tx * TILE + TILE / 2)) <= range && Math.abs(p.y - (th.ty + 1) * TILE) <= 56) {
            this.spoken.add(key);
            if (key.startsWith("tut.")) this.spokenSession.add(key);
            this.emit({ t: "caption", id: key });
          }
          break;
        }
        case "bossTrigger": {
          const b = this.boss;
          if (b && b.state === "dormant" && rectsOverlap({ x: th.tx * TILE, y: th.ty * TILE, w: th.tw * TILE, h: th.th * TILE }, body)) {
            b.awaken();
            this.setDoors(this.def, true, true);
            this.bossLocked = true;
            this.emit({ t: "sfx", name: "door" });
            this.emit({ t: "shake", amount: 2, frames: 14 });
          }
          break;
        }
        case "endingTrigger":
          if (rectsOverlap({ x: th.tx * TILE, y: th.ty * TILE, w: th.tw * TILE, h: th.th * TILE }, body) && this.save.bossDefeated) this.beginEnding();
          break;
        default:
          break;
      }
    }
  }

  private collectMemory(id: MemoryId, tx: number, ty: number): void {
    this.save.memories = [...this.save.memories, id].sort() as MemoryId[];
    const p = this.player;
    this.refreshAbilities();
    if (id === 1) p.hp = Math.min(p.maxHp, p.hp + 1);
    this.emit({ t: "memory", id });
    this.emit({ t: "sfx", name: "memory", x: p.x, y: p.y });
    this.emit({ t: "fx", name: "memoryGlow", x: tx * TILE + TILE / 2, y: ty * TILE, n: 18 });
    this.emit({ t: "save" });
    this.mode = "read";
    this.readKind = "memory";
    this.readId = String(id);
    this.readT = 0;
  }

  private collectMarginStep(tx: number, ty: number): void {
    this.save.marginStep = true;
    this.refreshAbilities();
    const p = this.player;
    this.emit({ t: "ability", id: "marginStep" });
    this.emit({ t: "sfx", name: "pickup", x: p.x, y: p.y });
    this.emit({ t: "fx", name: "memoryGlow", x: tx * TILE + TILE / 2, y: ty * TILE, n: 16 });
    this.emit({ t: "save" });
    this.mode = "read";
    this.readKind = "ability";
    this.readId = "marginStep";
    this.readT = 0;
  }

  // ------------------------------------------------------------------ cửa
  private checkExits(): boolean {
    const body = footToRect(this.player.foot);
    for (const ex of this.def.exits) {
      if (!rectsOverlap({ x: ex.tx * TILE, y: ex.ty * TILE, w: ex.tw * TILE, h: ex.th * TILE }, body)) continue;
      // Cửa đấu trường khoá thì ô đặc đã chắn; kiểm lại để chắc chắn không lọt qua khi chuyển phòng.
      if (this.roomId === "arena" && this.boss && this.boss.active) continue;
      const target = room(ex.to);
      const s = spawnPos(target, ex.spawn);
      const hp = this.player.hp;
      const vy = this.player.vy;
      this.emit({ t: "sfx", name: "door" });
      this.loadRoom(ex.to, s);
      this.player.hp = hp;
      // Rơi qua lỗ: giữ một phần vận tốc rơi để mượt, nhưng không để rơi quá nhanh vào phòng mới.
      this.player.vy = Math.min(vy, 2);
      return true;
    }
    return false;
  }

  // ------------------------------------------------------------------ chết / boss / kết thúc
  private die(): void {
    this.mode = "dead";
    this.deadT = 0;
    this.save.deaths += 1;
    this.player.hp = 0;
    this.emit({ t: "sfx", name: "death" });
    this.emit({ t: "died" });
    this.emit({ t: "shake", amount: 3, frames: 16 });
    this.emit({ t: "save" });
  }

  private bossDefeated(): void {
    if (this.save.bossDefeated) return;
    this.save.bossDefeated = true;
    this.boss = null;
    this.setDoors(this.def, false, false);
    this.bossLocked = false;
    this.emit({ t: "caption", id: "boss.defeat" });
    this.emit({ t: "sfx", name: "door" });
    this.emit({ t: "save" });
  }

  private beginEnding(): void {
    if (this.mode !== "play") return;
    const elig = endingEligibility(this.save.memories);
    this.mode = "ending";
    this.endingT = 0;
    this.endingPage = 0;
    this.endingChoice = 0;
    if (elig.choice) {
      this.endingStage = "choice";
      this.endingKind = null;
      this.emit({ t: "ending", kind: "choice" });
    } else {
      this.endingStage = "pages";
      this.endingKind = "basic";
      this.emit({ t: "ending", kind: "basic" });
    }
  }

  private stepEnding(pressed: { confirm: boolean; any: boolean; left: boolean; right: boolean }): void {
    this.endingT += 1;
    if (this.endingStage === "choice") {
      if (pressed.left) this.endingChoice = 0;
      if (pressed.right) this.endingChoice = 1;
      if (this.endingT >= READ_MIN_FRAMES && pressed.confirm) {
        this.endingKind = this.endingChoice === 0 ? "erase" : "restore";
        this.endingStage = "pages";
        this.endingPage = 0;
        this.endingT = 0;
        this.emit({ t: "ending", kind: this.endingKind });
      }
      return;
    }
    if (this.endingT >= 20 && pressed.any) {
      this.endingPage += 1;
      this.endingT = 0;
      this.emit({ t: "sfx", name: "ui" });
      if (this.endingPage >= this.endingPages().length) this.finish();
    }
  }

  private finish(): void {
    const kind = this.endingKind ?? "basic";
    this.save.ending = kind;
    this.save.bestFrames = this.save.bestFrames === null ? this.save.playFrames : Math.min(this.save.bestFrames, this.save.playFrames);
    this.mode = "complete";
    this.emit({ t: "save" });
    this.emit({ t: "complete" });
  }

  // ------------------------------------------------------------------ móc cho test / QA (không dùng trong game thường)
  /** Dịch chuyển tới một phòng (test/QA). */
  qaGoto(id: RoomId, spawn: string): void {
    const s = spawnPos(room(id), spawn);
    this.mode = "play";
    this.loadRoom(id, s);
  }

  /** Cấp khả năng/ký ức (test/QA). */
  qaGrant(g: { marginStep?: boolean; memories?: MemoryId[]; hp?: number; ink?: number }): void {
    if (g.marginStep !== undefined) this.save.marginStep = g.marginStep;
    if (g.memories) this.save.memories = [...new Set(g.memories)].sort() as MemoryId[];
    this.refreshAbilities();
    if (g.hp !== undefined) this.player.hp = Math.min(this.player.maxHp, g.hp);
    if (g.ink !== undefined) this.player.ink = Math.min(PLAYER.maxInk, g.ink);
  }
}

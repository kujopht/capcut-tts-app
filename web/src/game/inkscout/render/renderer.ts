import { PULSE, VIEW_H, VIEW_W } from "../core/constants";
import type { Game } from "../core/game";
import { T } from "../core/tilemap";
import type { GameEvent, RoomId } from "../core/types";
import { drawBoss, drawDashGhost, drawEnemy, drawHero, drawSlashArc, r } from "./actors";
import { FxSystem } from "./fx";
import { drawHud } from "./hud";
import { C, ROOM_STYLE } from "./palette";
import { buildTerrain, drawBackground, drawBossHazards, drawBossTelegraph, drawCycles, drawExits, drawGlyphs, drawThings, makeMotes, type Mote } from "./world";

/**
 * Lớp vẽ Canvas 2D ở độ phân giải nội bộ 384×216 (CSS phóng nguyên theo nearest-neighbor). KHÔNG đọc đầu vào, KHÔNG sửa trạng thái mô phỏng — chỉ
 * đọc `Game`. `step()` gọi MỖI bước mô phỏng (camera, hạt), `render()` gọi mỗi khung hiển thị.
 */
export class Renderer {
  readonly fx = new FxSystem();
  private readonly ctx: CanvasRenderingContext2D;
  private terrain: HTMLCanvasElement | null = null;
  private roomId: RoomId | null = null;
  private mapRef: unknown = null;
  private glyphs: { tx: number; ty: number }[] = [];
  private grad: CanvasGradient | null = null;
  private vignette: HTMLCanvasElement | null = null;
  private motes: Mote[] = makeMotes(26);
  private readonly cam = { x: 0, y: 0 };
  private readonly glow = new Map<string, number>();
  private lastFacing: 1 | -1 = 1;
  private disposed = false;

  constructor(
    readonly canvas: HTMLCanvasElement,
    private portrait: HTMLImageElement | null,
  ) {
    const c = canvas.getContext("2d", { alpha: false });
    if (!c) throw new Error("Canvas 2D không khả dụng");
    this.ctx = c;
    canvas.width = VIEW_W;
    canvas.height = VIEW_H;
    c.imageSmoothingEnabled = false;
  }

  setPortrait(img: HTMLImageElement | null): void {
    this.portrait = img;
  }

  onEvents(events: readonly GameEvent[], game: Game): void {
    for (const e of events) {
      this.fx.onEvent(e);
      if (e.t === "caption") {
        for (const th of game.def.things) if (th.kind === "glyphLore" && th.id === e.id) this.glow.set(th.id, 480);
      } else if (e.t === "roomEnter") {
        this.setRoom(game);
      }
    }
  }

  private setRoom(game: Game): void {
    this.roomId = game.roomId;
    this.mapRef = game.map;
    this.terrain = buildTerrain(game.map, game.def);
    this.glyphs = [];
    for (let ty = 0; ty < game.map.h; ty += 1) for (let tx = 0; tx < game.map.w; tx += 1) if (game.map.kind(tx, ty) === T.GLYPH) this.glyphs.push({ tx, ty });
    const st = ROOM_STYLE[game.roomId];
    const g = this.ctx.createLinearGradient(0, 0, 0, VIEW_H);
    g.addColorStop(0, st.sky0);
    g.addColorStop(1, st.sky1);
    this.grad = g;
    // viền tối quanh màn hình
    const v = document.createElement("canvas");
    v.width = VIEW_W;
    v.height = VIEW_H;
    const vc = v.getContext("2d");
    if (vc) {
      const rg = vc.createRadialGradient(VIEW_W / 2, VIEW_H / 2, VIEW_H * 0.35, VIEW_W / 2, VIEW_H / 2, VIEW_W * 0.62);
      rg.addColorStop(0, "rgba(0,0,0,0)");
      rg.addColorStop(1, `rgba(3,3,10,${st.vignette})`);
      vc.fillStyle = rg;
      vc.fillRect(0, 0, VIEW_W, VIEW_H);
    }
    this.vignette = v;
    this.fx.clear();
    this.glow.clear();
    this.snapCamera(game);
  }

  private camTarget(game: Game): { x: number; y: number } {
    const p = game.player;
    const pw = game.map.pxW;
    const ph = game.map.pxH;
    const look = p.facing * 18 + (p.dashing ? p.facing * 14 : 0);
    let x = p.x + look - VIEW_W / 2;
    let y = p.y - VIEW_H * 0.6;
    x = pw <= VIEW_W ? (pw - VIEW_W) / 2 : Math.max(0, Math.min(pw - VIEW_W, x));
    y = ph <= VIEW_H ? (ph - VIEW_H) / 2 : Math.max(0, Math.min(ph - VIEW_H, y));
    return { x, y };
  }

  private snapCamera(game: Game): void {
    const t = this.camTarget(game);
    this.cam.x = t.x;
    this.cam.y = t.y;
  }

  /** Mỗi bước mô phỏng: camera, hạt, hiệu ứng nền. */
  step(game: Game): void {
    if (game.map !== this.mapRef || game.roomId !== this.roomId) this.setRoom(game);
    const t = this.camTarget(game);
    const p = game.player;
    this.cam.x += (t.x - this.cam.x) * 0.14;
    this.cam.y += (t.y - this.cam.y) * (Math.abs(t.y - this.cam.y) > 40 ? 0.2 : 0.1);
    this.fx.update();
    for (const [k, v] of this.glow) {
      if (v <= 1) this.glow.delete(k);
      else this.glow.set(k, v - 1);
    }
    this.lastFacing = p.facing;
    if (p.dashing && game.frame % 2 === 0) this.fx.onEvent({ t: "fx", name: "dashTrail", x: p.x, y: p.y - 8, dir: p.facing, n: 1 });
    // boss tan thành giấy khi chết
    const b = game.boss;
    if (b && b.state === "dying" && game.frame % 3 === 0) {
      this.fx.onEvent({ t: "fx", name: "page", x: b.x + (Math.random() - 0.5) * 24, y: b.y - Math.random() * 50, n: 2 });
    }
    // mảnh giấy rơi khi Memory Pulse
    if (p.pulseActive && game.frame % 2 === 0) this.fx.onEvent({ t: "fx", name: "memoryGlow", x: p.x + (Math.random() - 0.5) * p.pulseRadius * 1.6, y: p.y - 8 + (Math.random() - 0.5) * p.pulseRadius, n: 1 });
  }

  render(game: Game): void {
    if (this.disposed) return;
    if (game.map !== this.mapRef || game.roomId !== this.roomId) this.setRoom(game);
    const c = this.ctx;
    c.imageSmoothingEnabled = false;
    const tick = game.frame;
    const st = ROOM_STYLE[game.roomId];
    const camX = Math.round(this.cam.x);
    const camY = Math.round(this.cam.y);
    if (this.grad) drawBackground(c, this.grad, st, camX, camY, tick, this.motes);
    const sh = this.fx.shakeOffset(game.save.settings.shake);

    c.save();
    c.translate(-camX + sh.x, -camY + sh.y);
    if (this.terrain) c.drawImage(this.terrain, 0, 0);
    drawGlyphs(c, game.map, this.glyphs, tick);
    drawExits(c, game, tick);
    drawThings(c, game, tick, this.glow);
    drawCycles(c, game, tick);

    const b = game.boss;
    if (b) {
      drawBossTelegraph(c, b, tick);
      drawBoss(c, b, tick);
      drawBossHazards(c, b, tick);
    }
    for (const e of game.enemies) drawEnemy(c, e, tick);
    for (const g of this.fx.ghosts) drawDashGhost(c, g.x, g.y, g.facing, g.life);

    const p = game.player;
    const dead = game.mode === "dead";
    drawHero(c, p, tick, dead, game.deadT);
    drawSlashArc(c, p);
    this.drawPulse(c, game);

    // hạt
    for (const q of this.fx.parts) {
      const a = q.life / q.max;
      c.globalAlpha = Math.min(1, a * 1.4);
      if (q.kind === "page") {
        c.save();
        c.translate(Math.round(q.x), Math.round(q.y));
        c.rotate(q.rot);
        r(c, q.color, -q.size, -q.size + 1, q.size * 2, q.size * 2 - 2);
        c.restore();
      } else {
        r(c, q.color, Math.round(q.x), Math.round(q.y), q.size, q.size);
      }
    }
    c.globalAlpha = 1;
    c.restore();

    if (this.vignette) c.drawImage(this.vignette, 0, 0);
    // quầng đỏ khi máu thấp
    if (p.hp === 1 && game.mode === "play") {
      c.globalAlpha = 0.12 + 0.08 * Math.sin(tick * 0.15);
      r(c, C.crimson, 0, 0, VIEW_W, 3);
      r(c, C.crimson, 0, VIEW_H - 3, VIEW_W, 3);
      r(c, C.crimson, 0, 0, 3, VIEW_H);
      r(c, C.crimson, VIEW_W - 3, 0, 3, VIEW_H);
      c.globalAlpha = 1;
    }
    if (this.fx.flash > 0) {
      c.globalAlpha = this.fx.flash;
      r(c, this.fx.flashColor, 0, 0, VIEW_W, VIEW_H);
      c.globalAlpha = 1;
    }
    drawHud(c, game, this.portrait, tick);
    // mờ vào/ra
    let black = 0;
    if (game.mode === "dead") black = Math.min(1, game.deadT / 60);
    else if (game.fade > 0) black = game.fade / 14;
    if (game.mode === "ending" || game.mode === "complete") black = Math.max(black, 0.55);
    if (black > 0) {
      c.globalAlpha = black;
      r(c, C.void, 0, 0, VIEW_W, VIEW_H);
      c.globalAlpha = 1;
    }
  }

  private drawPulse(c: CanvasRenderingContext2D, game: Game): void {
    const p = game.player;
    if (p.pulseT <= 0) return;
    const cx = Math.round(p.x);
    const cy = Math.round(p.y - 8);
    if (p.pulseT <= PULSE.windup) {
      // gom lực: vòng nhỏ co lại
      const k = p.pulseT / PULSE.windup;
      const rad = Math.round(14 * (1 - k) + 3);
      c.globalAlpha = 0.5 + 0.5 * k;
      for (let i = 0; i < 16; i += 1) {
        const a = (i / 16) * Math.PI * 2;
        r(c, C.cyanLight, Math.round(cx + Math.cos(a) * rad), Math.round(cy + Math.sin(a) * rad), 1, 1);
      }
      c.globalAlpha = 1;
      return;
    }
    const rad = p.pulseRadius;
    const frac = Math.min(1, (p.pulseT - PULSE.windup) / (PULSE.expandFrames + PULSE.lockFrames));
    const g = c.createRadialGradient(cx, cy, 2, cx, cy, Math.max(4, rad));
    g.addColorStop(0, "rgba(154,240,255,0)");
    g.addColorStop(0.8, `rgba(139,108,255,${0.28 * (1 - frac)})`);
    g.addColorStop(1, `rgba(154,240,255,${0.5 * (1 - frac)})`);
    c.fillStyle = g;
    c.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
    const n = Math.max(24, Math.round(rad * 0.9));
    c.globalAlpha = Math.max(0.2, 1 - frac);
    for (let i = 0; i < n; i += 1) {
      const a = (i / n) * Math.PI * 2;
      r(c, i & 1 ? C.violetLight : C.cyanLight, Math.round(cx + Math.cos(a) * rad), Math.round(cy + Math.sin(a) * rad), 2, 2);
    }
    c.globalAlpha = 1;
  }

  dispose(): void {
    this.disposed = true;
    this.terrain = null;
    this.vignette = null;
    this.grad = null;
    this.fx.clear();
    this.glow.clear();
  }

  get facing(): 1 | -1 {
    return this.lastFacing;
  }
}

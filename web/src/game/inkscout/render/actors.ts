import { BLADE } from "../core/constants";
import type { Boss } from "../core/boss";
import { BOSS_ATTACKS } from "../core/boss";
import type { Enemy } from "../core/enemies";
import type { Player } from "../core/player";
import { C } from "./palette";

type Ctx = CanvasRenderingContext2D;

/** TẤT CẢ hình ở đây là sprite TẠM do mã vẽ (nguyên bản, không dùng nghệ thuật của game khác); có thể thay bằng sprite sheet thật mà không đổi lõi mô phỏng. */
export function r(c: Ctx, col: string, x: number, y: number, w: number, h: number): void {
  c.fillStyle = col;
  c.fillRect(x, y, w, h);
}

export function hash(a: number, b: number): number {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

const lerp = (a: number, b: number, k: number): number => a + (b - a) * k;
const clamp01 = (k: number): number => (k < 0 ? 0 : k > 1 ? 1 : k);
const ease = (k: number): number => 1 - (1 - clamp01(k)) * (1 - clamp01(k));

// ====================================================================== người chơi
/** Góc lưỡi gươm (rad, 0 = hướng mặt, dương = xuống) theo đòn đang đánh. */
export function bladeAngle(p: Player): number | null {
  if (p.dashing && p.dashSlash) return 0;
  const t = p.attackT;
  switch (p.attackKind) {
    case "g1": return lerp(-1.3, 0.6, ease(t / 9));
    case "g2": return lerp(0.7, -0.9, ease(t / 9));
    case "g3": return lerp(-2.3, 1.0, ease(t / 12));
    case "air": return lerp(-1.2, 1.5, ease(t / 11));
    default: return null;
  }
}

export function drawHero(c: Ctx, p: Player, tick: number, dead: boolean, deadT: number): void {
  const x = Math.round(p.x);
  const y = Math.round(p.y);
  c.save();
  c.translate(x, y);
  if (p.facing < 0) c.scale(-1, 1);
  const blink = p.invuln > 0 && p.hurt === 0 && ((tick >> 2) & 1) === 1;
  if (blink) c.globalAlpha = 0.45;
  if (dead) {
    // gục xuống rồi mờ dần
    c.globalAlpha = Math.max(0, 1 - deadT / 70);
    c.rotate(Math.min(1.4, deadT / 14));
  }
  const anim = p.anim;
  let bob = 0;
  let legL = 0;
  let legR = 0;
  let lean = 0;
  let arm: "idle" | "up" | "swing" | "out" | "back" = "idle";
  if (anim === "idle") bob = (Math.floor(p.animT / 22) & 1) === 1 ? 1 : 0;
  else if (anim === "run") {
    const ph = Math.floor(p.runT / 5.5) & 3;
    legL = ph === 0 ? 2 : ph === 2 ? -2 : 0;
    legR = -legL;
    bob = ph & 1 ? 1 : 0;
    arm = ph === 0 || ph === 2 ? "back" : "idle";
    lean = 1;
  } else if (anim === "jump") {
    legL = -1;
    legR = 2;
    arm = "up";
  } else if (anim === "fall") {
    legL = -2;
    legR = 2;
    arm = "up";
  } else if (anim === "dash") {
    legL = -3;
    legR = 3;
    lean = 3;
    arm = "back";
  } else if (anim === "hurt") {
    lean = -2;
    arm = "up";
  } else if (anim === "pulse") {
    arm = "out";
    bob = p.pulseT < 6 ? 1 : 0;
  } else if (anim === "attack") {
    arm = "swing";
    lean = 1;
  }
  if (lean !== 0) c.transform(1, 0, -lean * 0.06, 1, 0, 0);

  // chân + giày
  r(c, C.jacket, -3 + legL, -6, 2, 4);
  r(c, C.jacket, 1 + legR, -6, 2, 4);
  r(c, C.ink, -4 + legL, -2, 4, 2);
  r(c, C.ink, 0 + legR, -2, 4, 2);
  r(c, C.cyan, -4 + legL, -1, 4, 1);
  r(c, C.cyan, 0 + legR, -1, 4, 1);
  // thân + cổ áo tím
  r(c, C.jacket, -3, -12 + bob, 6, 6);
  r(c, C.violetDark, -4, -12 + bob, 8, 2);
  r(c, C.violet, -4, -12 + bob, 8, 1);
  r(c, C.cyan, 0, -9 + bob, 1, 1);
  // tay sau
  if (arm === "back") r(c, C.jacket, -5, -11 + bob, 2, 4);
  // đầu: tóc sau, mặt, tóc trước
  r(c, C.hair, -8, -20 + bob, 4, 7);
  r(c, C.hair, -7, -22 + bob, 13, 5);
  r(c, C.hairLight, -3, -22 + bob, 6, 1);
  r(c, C.hair, -1, -25 + bob, 2, 3);
  r(c, C.skin, -4, -17 + bob, 9, 6);
  r(c, C.skinShade, -4, -12 + bob, 9, 1);
  r(c, C.hair, 2, -19 + bob, 5, 3);
  r(c, C.cyan, 4, -19 + bob, 1, 5);
  r(c, C.eye, 1, -15 + bob, 3, 2);
  r(c, C.white, 3, -15 + bob, 1, 1);
  // tay trước
  if (arm === "idle" || arm === "back") {
    r(c, C.jacket, 1, -11 + bob, 3, 5);
    r(c, C.violetDark, 1, -7 + bob, 3, 1);
    r(c, C.ink, 1, -6 + bob, 3, 2);
  } else if (arm === "up") {
    r(c, C.jacket, 2, -17 + bob, 2, 6);
    r(c, C.ink, 2, -19 + bob, 2, 2);
  } else if (arm === "out") {
    r(c, C.jacket, 2, -12 + bob, 6, 3);
    r(c, C.ink, 8, -12 + bob, 2, 3);
  }
  // lưỡi gươm Glyph Blade
  const a = bladeAngle(p);
  if (a !== null || arm === "swing") {
    const ang = a ?? 0;
    c.save();
    c.translate(3, -11 + bob);
    c.rotate(ang);
    r(c, C.jacket, 0, -1, 4, 3);
    r(c, C.violet, 4, -3, 2, 6);
    r(c, C.white, 6, -1, 15, 2);
    r(c, C.cyanLight, 6, -2, 14, 1);
    r(c, C.violetLight, 9, -1, 1, 1);
    r(c, C.violetLight, 13, -1, 1, 1);
    r(c, C.violetLight, 17, -1, 1, 1);
    c.restore();
  } else if (anim !== "pulse") {
    // lưỡi gươm đeo sau lưng khi không đánh
    r(c, C.violetDark, -7, -14 + bob, 2, 8);
    r(c, C.white, -7, -20 + bob, 1, 6);
  }
  if (anim === "pulse") {
    c.globalAlpha = 0.55;
    r(c, C.cyanLight, -6, -24 + bob, 12, 24);
  }
  c.restore();
}

/** Cung chém (pixel) quanh vai người chơi khi có hộp đòn hiệu lực. */
export function drawSlashArc(c: Ctx, p: Player): void {
  const a = bladeAngle(p);
  if (a === null) return;
  const kind = p.attackKind;
  const dashSlash = p.dashing && p.dashSlash;
  const t = p.attackT;
  if (!dashSlash && kind === "none") return;
  const hit = BLADE[kind === "none" ? "g1" : kind].hit;
  if (!dashSlash && (t < hit[0] - 1 || t > hit[1] + 3)) return;
  const x = Math.round(p.x);
  const y = Math.round(p.y) - 11;
  const dir = p.facing;
  const spread = kind === "g3" ? 1.9 : 1.3;
  const R = kind === "g3" ? 25 : dashSlash ? 22 : 20;
  const steps = 22;
  for (let i = 0; i < steps; i += 1) {
    const k = i / (steps - 1);
    const ang = a - spread * (1 - k) * (kind === "g2" ? -1 : 1);
    const px = x + dir * (3 + Math.cos(ang) * R);
    const py = y + Math.sin(ang) * R;
    c.globalAlpha = 0.25 + 0.7 * k;
    r(c, k > 0.7 ? C.white : C.cyanLight, Math.round(px) - 1, Math.round(py) - 1, k > 0.5 ? 3 : 2, k > 0.5 ? 3 : 2);
  }
  c.globalAlpha = 1;
}

export function drawDashGhost(c: Ctx, x: number, y: number, facing: 1 | -1, life: number): void {
  c.save();
  c.globalAlpha = Math.min(0.5, life / 18);
  c.translate(Math.round(x), Math.round(y));
  if (facing < 0) c.scale(-1, 1);
  r(c, C.cyan, -5, -22, 10, 20);
  r(c, C.cyanLight, -3, -20, 6, 6);
  c.restore();
}

// ====================================================================== kẻ địch
function exclaim(c: Ctx, x: number, y: number, tick: number): void {
  if (((tick >> 2) & 1) === 0) return;
  r(c, C.crimsonLight, x - 1, y - 8, 3, 5);
  r(c, C.crimsonLight, x - 1, y - 2, 3, 2);
}

export function drawEnemy(c: Ctx, e: Enemy, tick: number): void {
  const x = Math.round(e.x);
  const y = Math.round(e.y);
  c.save();
  c.translate(x, y);
  if (e.facing < 0 && e.kind !== "tornPage") c.scale(-1, 1);
  if (e.state === "dying") c.globalAlpha = Math.max(0, e.deathT / 22);
  const flash = e.flash > 0 && ((e.flash >> 1) & 1) === 0;
  const t = e.anim;
  switch (e.kind) {
    case "scribble": drawScribble(c, e, t, flash); break;
    case "tornPage": drawTornPage(c, e, t, flash); break;
    case "hound": drawHound(c, e, t, flash); break;
    case "broken": drawBroken(c, e, t, flash, tick); break;
  }
  c.restore();
  if (e.stun > 0) {
    // sao choáng quay quanh đầu
    const top = e.kind === "tornPage" ? -14 : e.kind === "broken" ? -28 : -16;
    for (let i = 0; i < 3; i += 1) {
      const a = (tick * 0.12) + i * 2.1;
      r(c, C.gold, x + Math.round(Math.cos(a) * 6) - 1, y + top + Math.round(Math.sin(a) * 2), 2, 2);
    }
  }
  if ((e.state === "notice" || e.state === "crouch" || e.state === "telegraph") && e.kind !== "broken") exclaim(c, x, y - (e.kind === "tornPage" ? 16 : 14), tick);
  if (e.kind === "broken" && e.state === "notice") exclaim(c, x, y - 30, tick);
}

function drawScribble(c: Ctx, e: Enemy, t: number, flash: boolean): void {
  const squash = e.state === "recover" ? 0.72 : e.state === "lunge" ? 1.3 : 1;
  const w = Math.round(12 * squash);
  const h = Math.round(11 * (2 - squash));
  const body = flash ? C.white : C.ink;
  r(c, body, -(w >> 1) + 1, -h, w - 2, h);
  r(c, body, -(w >> 1), -h + 2, w, h - 4);
  // nét vẽ nguệch ngoạc
  const seed = Math.floor(t / 4);
  for (let i = 0; i < 7; i += 1) {
    const hx = Math.round((hash(i, seed) - 0.5) * (w + 6));
    const hy = -Math.round(hash(i + 9, seed) * (h + 2));
    r(c, flash ? C.white : C.slate2, hx, hy, hash(i, 3) < 0.5 ? 3 : 1, hash(i, 4) < 0.5 ? 1 : 3);
  }
  // mắt
  const alert = e.state === "notice" || e.state === "lunge";
  r(c, alert ? C.crimsonLight : C.white, 1, -h + 3, 3, 3);
  r(c, alert ? C.crimsonDark : C.ink, 3, -h + 4, 1, 2);
  r(c, alert ? C.crimsonLight : C.white, -3, -h + 3, 2, 3);
  // chân
  const ph = Math.floor(t / 6) & 1;
  r(c, C.ink, -4 + ph, -1, 2, 2);
  r(c, C.ink, 2 - ph, -1, 2, 2);
}

function drawTornPage(c: Ctx, e: Enemy, t: number, flash: boolean): void {
  const flap = Math.round(Math.sin(t * 0.3) * 2);
  const dive = e.state === "dive";
  const tele = e.state === "telegraph";
  if (dive) c.scale(0.8, 1.35);
  const page = flash ? C.white : C.parch2;
  // cánh rách
  r(c, C.parch0, -9, -4 + flap, 4, 6);
  r(c, C.parch0, 5, -4 - flap, 4, 6);
  r(c, C.parch1, -8, -3 + flap, 2, 4);
  r(c, C.parch1, 6, -3 - flap, 2, 4);
  // trang giấy với mép trên rách
  r(c, page, -5, -7, 10, 14);
  for (let i = 0; i < 5; i += 1) r(c, page, -5 + i * 2, -9 + Math.round(hash(i, 5) * 3), 2, 2 + Math.round(hash(i, 6) * 2));
  r(c, C.parch0, -5, 6, 10, 1);
  // thanh bôi đen + mắt
  r(c, C.ink, -5, -3, 10, 4);
  r(c, tele || dive ? C.crimsonLight : C.crimson, -1, -2, 3, 2);
  // dòng chữ mờ
  r(c, C.parch0, -4, 3, 6, 1);
  r(c, C.parch0, -4, 5, 4, 1);
  if (tele) {
    c.globalAlpha = 0.5;
    r(c, C.crimson, -7, -9, 14, 1);
    r(c, C.crimson, -7, 8, 14, 1);
  }
}

function drawHound(c: Ctx, e: Enemy, t: number, flash: boolean): void {
  const crouch = e.state === "crouch" ? 3 : 0;
  const charge = e.state === "charge" || e.state === "skid";
  const ph = charge ? Math.floor(t / 3) & 1 : Math.floor(t / 7) & 1;
  const body = flash ? C.white : C.ink;
  // thân gồm các thanh "bôi đen"
  r(c, body, -9, -8 + crouch, 15, 3);
  r(c, C.ink2, -9, -5 + crouch, 15, 2);
  r(c, body, -8, -3 + crouch, 13, 2);
  // đầu + mõm + tai
  r(c, body, 4, -10 + crouch, 7, 5);
  r(c, body, 9, -8 + crouch, 4, 3);
  r(c, body, 4, -12 + crouch, 2, 3);
  r(c, e.state === "crouch" || charge ? C.crimsonLight : C.crimson, 8, -9 + crouch, 2, 2);
  // răng giấy
  r(c, C.parch2, 11, -6 + crouch, 1, 1);
  // chân
  r(c, body, -8 + ph * 2, -2, 2, 2);
  r(c, body, -4 - ph * 2, -2, 2, 2);
  r(c, body, 1 + ph * 2, -2, 2, 2);
  r(c, body, 5 - ph * 2, -2, 2, 2);
  // đuôi là một dải giấy
  r(c, C.parch1, -12, -8 + crouch + (ph ? 0 : 1), 3, 1);
  if (charge) {
    c.globalAlpha = 0.35;
    r(c, C.crimson, -22, -7, 12, 1);
    r(c, C.crimson, -20, -4, 10, 1);
  }
}

function drawBroken(c: Ctx, e: Enemy, t: number, flash: boolean, tick: number): void {
  const raise = e.state === "notice" ? Math.min(1, e.t / 30) : e.state === "slam" ? 0 : 0;
  const slam = e.state === "slam";
  const tint = e.enraged ? C.crimsonLight : C.violetLight;
  // Bản thể bất ổn: các lát ngang lệch nhau theo nhịp, kèm bản sao lệch màu.
  const slices = 6;
  for (let s = 0; s < slices; s += 1) {
    const y0 = -22 + s * 4;
    const off = hash(s, Math.floor(tick / 5)) < 0.22 ? Math.round((hash(s, tick) - 0.5) * 5) : 0;
    const body = flash ? C.white : s < 2 ? C.skin : s < 5 ? C.parch1 : C.parch0;
    if (s >= 2) {
      r(c, "#7ff3ff55", -6 + off - 1, y0, 12, 4);
      r(c, "#ff7a8e55", -6 + off + 1, y0, 12, 4);
    }
    r(c, body, -5 + off, y0, 10, 4);
  }
  // tóc rối + mặt
  r(c, C.hair, -6, -25, 12, 4);
  r(c, C.hair, -7, -23, 3, 5);
  r(c, C.ink, 1, -20, 3, 2);
  r(c, tint, 1, -20, 1, 1);
  r(c, C.ink, -3, -18, 5, 1);
  // áo choàng rách
  r(c, C.slate1, -6, -14, 12, 8);
  r(c, C.slate0, -5, -6, 10, 6);
  for (let i = 0; i < 4; i += 1) r(c, C.slate0, -6 + i * 3, -2 + Math.round(hash(i, 1) * 2), 2, 3);
  // tay
  if (slam) {
    r(c, C.parch1, 4, -4, 14, 4);
    r(c, C.ink, 16, -6, 5, 8);
  } else if (e.state === "notice") {
    const up = Math.round(raise * 14);
    r(c, C.parch1, 4, -16 - up, 3, 10 + up);
    r(c, C.ink, 3, -20 - up, 5, 4);
    r(c, C.parch1, -7, -16 - up, 3, 10 + up);
    r(c, C.ink, -8, -20 - up, 5, 4);
  } else {
    r(c, C.parch1, 5, -13, 3, 8);
    r(c, C.parch1, -8, -13, 3, 8);
  }
  void t;
}

// ====================================================================== boss
export function bossBladeAngle(b: Boss, tick: number): number {
  const rest = 1.05 + Math.sin(tick * 0.04) * 0.05;
  if (b.state === "telegraph" && b.attack) {
    const k = ease(b.t / BOSS_ATTACKS[b.attack].telegraph);
    switch (b.attack) {
      case "revisionSlash": return lerp(rest, -2.7, k);
      case "marginCut": return lerp(rest, -2.0, k);
      case "blackLine": return lerp(rest, 0.05, k);
      case "rewrite": return lerp(rest, -0.7, k);
      case "delete": return lerp(rest, -1.2, k);
      case "brokenSentence": return lerp(rest, -1.7, k);
      case "revisionRush": return lerp(rest, -0.5, k);
      default: return rest;
    }
  }
  if (b.state === "active") {
    switch (b.attack) {
      case "revisionSlash": return lerp(-1.6, 0.35, ease(b.t / 8));
      case "marginCut": return lerp(-2.0, 1.55, ease(b.t / 5));
      case "rewrite": return b.step === 3 ? lerp(-1.4, 0.3, ease(b.t / 4)) : -0.7;
      case "revisionRush": return b.step % 2 === 1 ? 0.15 : -0.5;
      case "blackLine": return 0.05;
      case "brokenSentence": return -1.7;
      case "delete": return -1.2;
      default: return rest;
    }
  }
  return rest;
}

export function drawBoss(c: Ctx, b: Boss, tick: number): void {
  if (b.state === "dormant") {
    // Tượng bất động trong bóng tối: chỉ thấy đường viền mờ cho tới khi người chơi bước vào.
    c.save();
    c.globalAlpha = 0.28;
    c.translate(Math.round(b.x), Math.round(b.y));
    r(c, C.ink2, -10, -44, 20, 44);
    r(c, C.ink2, -6, -54, 12, 11);
    c.restore();
    return;
  }
  if (!b.visible) return;
  const x = Math.round(b.x);
  const y = Math.round(b.y);
  const phase2 = b.phase === 2;
  const flash = b.flash > 0 && ((b.flash >> 1) & 1) === 0;
  const dying = b.state === "dying";
  c.save();
  c.translate(x, y);
  if (b.facing < 0) c.scale(-1, 1);
  if (dying) c.globalAlpha = Math.max(0, b.dyingT / 150);
  const sway = Math.round(Math.sin(tick * 0.05) * 1.2);
  const robe = flash ? C.white : phase2 ? "#1c0d18" : C.ink2;
  const trim = flash ? C.white : C.parch1;
  const shake = b.state === "telegraph" ? Math.round(Math.sin(tick * 1.4) * 1) : 0;
  c.translate(shake, 0);

  // quầng đỏ giai đoạn 2
  if (phase2) {
    const g = c.createRadialGradient(0, -26, 4, 0, -26, 38);
    g.addColorStop(0, "rgba(217,48,76,0.35)");
    g.addColorStop(1, "rgba(217,48,76,0)");
    c.fillStyle = g;
    c.fillRect(-40, -70, 80, 90);
  }
  // áo choàng: hình thang các lớp
  for (let row = 0; row < 40; row += 2) {
    const w = 14 + Math.round((row / 40) * 16);
    r(c, row % 8 < 2 ? C.navy2 : robe, -(w >> 1) + sway * (row / 40), -44 + row, w, 2);
  }
  // dải giấy rách ở gấu
  for (let i = 0; i < 8; i += 1) {
    const len = 3 + Math.round(hash(i, 11) * 7);
    r(c, i & 1 ? robe : C.navy2, -15 + i * 4 + sway, -len, 3, len);
  }
  // đường gấp giữa + viền giấy
  r(c, trim, -1, -40, 2, 38);
  r(c, trim, -14 + sway, -6, 28, 1);
  if (phase2) {
    r(c, C.crimson, -1, -34, 2, 2);
    r(c, C.crimson, 3, -26, 1, 6);
    r(c, C.crimson, -5, -20, 1, 8);
  }
  // vai
  r(c, robe, -13, -42, 26, 6);
  r(c, trim, -13, -42, 26, 1);
  // đầu: mũ trùm + mặt nạ giấy + thanh bôi đen
  r(c, robe, -8, -57, 16, 15);
  r(c, flash ? C.white : C.parch2, -5, -55, 10, 11);
  r(c, C.ink, -5, -51, 10, 3);
  const eyeOn = b.state !== "stunned";
  r(c, eyeOn ? C.crimsonLight : C.slate1, 1, -50, 2, 1);
  r(c, C.parch1, -3, -46, 6, 1);
  // vương miện giấy
  r(c, trim, -7, -61, 2, 5);
  r(c, trim, -1, -64, 2, 8);
  r(c, trim, 5, -61, 2, 5);
  // cánh tay sau
  r(c, robe, -16, -40, 4, 14);
  r(c, trim, -16, -27, 4, 2);
  // cánh tay cầm Revision Blade
  const ang = bossBladeAngle(b, tick);
  c.save();
  c.translate(12, -34);
  r(c, robe, 0, -2, 7, 5);
  c.rotate(ang);
  r(c, trim, 0, -2, 6, 4);
  r(c, C.crimsonDark, 6, -4, 2, 8);
  r(c, flash ? C.white : C.ink, 8, -2, 38, 4);
  r(c, C.crimson, 8, -2, 38, 1);
  for (let i = 0; i < 6; i += 1) r(c, C.parch2, 12 + i * 6, 0, 3, 1);
  r(c, C.crimsonLight, 45, -2, 3, 4);
  c.restore();
  c.restore();
}

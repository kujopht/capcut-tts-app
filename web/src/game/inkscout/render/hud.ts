import { PLAYER, PULSE, VIEW_H, VIEW_W } from "../core/constants";
import { BOSS } from "../core/boss";
import type { Game } from "../core/game";
import { r } from "./actors";
import { C } from "./palette";

type Ctx = CanvasRenderingContext2D;

/** Một giọt mực (HP) 7×9. */
function drop(c: Ctx, x: number, y: number, fill: string, edge: string): void {
  r(c, edge, x + 3, y, 1, 1);
  r(c, edge, x + 2, y + 1, 3, 1);
  r(c, edge, x + 1, y + 2, 5, 2);
  r(c, edge, x, y + 4, 7, 3);
  r(c, edge, x + 1, y + 7, 5, 1);
  r(c, edge, x + 2, y + 8, 3, 1);
  if (fill !== edge) {
    r(c, fill, x + 3, y + 2, 1, 1);
    r(c, fill, x + 2, y + 3, 3, 1);
    r(c, fill, x + 1, y + 4, 5, 3);
    r(c, fill, x + 2, y + 7, 3, 1);
  }
}

export function drawHud(c: Ctx, game: Game, portrait: HTMLImageElement | null, tick: number): void {
  const p = game.player;
  // khung chân dung
  r(c, C.ink, 3, 3, 26, 26);
  r(c, C.slate2, 3, 3, 26, 1);
  r(c, C.slate2, 3, 3, 1, 26);
  r(c, C.slate0, 28, 3, 1, 26);
  r(c, C.slate0, 3, 28, 26, 1);
  r(c, C.navy2, 4, 4, 24, 24);
  if (portrait && portrait.complete && portrait.naturalWidth > 0) {
    c.imageSmoothingEnabled = true;
    // lấy phần đầu (nửa trên) của ảnh linh vật
    c.drawImage(portrait, 110, 20, 290, 290, 4, 4, 24, 24);
    c.imageSmoothingEnabled = false;
  } else {
    r(c, C.hair, 9, 8, 14, 7);
    r(c, C.skin, 10, 14, 12, 8);
    r(c, C.eye, 17, 17, 3, 2);
  }
  // HP
  const maxHp = p.maxHp;
  for (let i = 0; i < maxHp; i += 1) {
    const full = i < p.hp;
    const low = p.hp <= 1 && full && ((tick >> 3) & 1) === 1;
    drop(c, 33 + i * 9, 4, full ? (low ? C.crimsonLight : C.cyanLight) : C.slate0, full ? C.cyanDark : C.slate1);
  }
  // Ink (9 ô); các ô đủ để gọi Memory Pulse sáng hơn
  const cost = game.abilities.pulseCheap ? PULSE.costMemory3 : PULSE.cost;
  for (let i = 0; i < PLAYER.maxInk; i += 1) {
    const x = 33 + i * 6;
    const on = i < p.ink;
    const ready = p.ink >= cost;
    r(c, C.ink, x, 16, 5, 6);
    r(c, on ? (ready ? C.violetLight : C.violet) : C.slate0, x + 1, 17, 3, 4);
    if (i === cost - 1) r(c, C.gold, x + 1, 23, 3, 1);
  }
  // ký ức đã nhớ
  for (let i = 1; i <= 3; i += 1) {
    const x = 36 + (i - 1) * 9;
    const have = game.has(i as 1 | 2 | 3);
    r(c, C.ink, x, 26, 7, 7);
    r(c, have ? C.gold : C.slate0, x + 1, 27, 5, 5);
    if (have) r(c, C.white, x + 2, 28, 2, 2);
  }
  // Margin Step
  if (game.save.marginStep) {
    const ready = p.dashCooldown === 0 && (p.onGround || p.dashAvailable);
    const x = 33 + 3 * 9 + 6;
    r(c, C.ink, x, 25, 12, 9);
    const col = ready ? C.cyanLight : C.slate2;
    r(c, col, x + 2, 29, 6, 1);
    r(c, col, x + 6, 27, 1, 5);
    r(c, col, x + 7, 28, 1, 3);
    r(c, col, x + 8, 29, 1, 1);
  }
  // thanh máu boss
  const b = game.boss;
  if (b && b.active && b.state !== "dead") {
    const w = 220;
    const x = (VIEW_W - w) >> 1;
    const y = VIEW_H - 14;
    r(c, C.ink, x - 2, y - 2, w + 4, 10);
    r(c, C.crimsonDark, x, y, w, 6);
    const frac = Math.max(0, b.hp) / b.maxHp;
    r(c, b.phase === 2 ? C.crimsonLight : C.crimson, x, y, Math.round(w * frac), 6);
    r(c, "#ffffff30", x, y, Math.round(w * frac), 1);
    // vạch báo giai đoạn 2
    r(c, C.parch2, x + Math.round((BOSS.phase2At / b.maxHp) * w), y - 2, 1, 10);
    if (b.state === "collapse") {
      c.globalAlpha = 0.6 + 0.4 * Math.sin(tick * 0.2);
      r(c, C.gold, x, y + 7, w, 1);
      c.globalAlpha = 1;
    }
  }
}

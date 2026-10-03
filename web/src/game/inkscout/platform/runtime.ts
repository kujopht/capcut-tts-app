import { TICK_RATE } from "../core/constants";
import { Game, type EndingStage, type GameMode, type GameResult } from "../core/game";
import { CAPTIONS } from "../core/lore";
import { defaultSave, type SaveData, type SaveSettings, type SaveStore } from "../core/save";
import type { EndingKind, GameEvent, MemoryId } from "../core/types";
import { Renderer } from "../render/renderer";
import { AudioBus, type Mood } from "./audio";
import { InputSource } from "./input";

/**
 * Vòng chạy của Ink Scout: bước cố định 60 Hz (bộ tích luỹ thời gian), vẽ mỗi khung hiển thị, TẠM DỪNG khi tab ẩn/mất tiêu điểm, và `destroy()` gỡ
 * SẠCH mọi thứ (requestAnimationFrame, bộ nghe, âm thanh, canvas) — rời trang rồi vào lại không để lại tài nguyên mồ côi.
 * React chỉ nhận `UiSnapshot` rời rạc (đổi chế độ, lời thoại, ký ức...) — không có cập nhật React theo từng khung.
 */
export interface UiSnapshot {
  mode: GameMode;
  paused: boolean;
  caption: { id: string; who?: string; text: string; touch?: string } | null;
  read: { kind: "memory" | "ability"; id: string; readT: number } | null;
  ending: { stage: EndingStage; kind: EndingKind | null; choice: 0 | 1; page: number; pages: readonly string[] } | null;
  boss: { phase: 1 | 2; hp: number; max: number } | null;
  marginStep: boolean;
  memories: MemoryId[];
  settings: SaveSettings;
  result: GameResult | null;
  saveFailed: boolean;
}

export interface RuntimeOptions {
  canvas: HTMLCanvasElement;
  store: SaveStore & { failed?: boolean };
  onUi: (s: UiSnapshot) => void;
  newGame?: boolean;
  seed?: number;
  /** Đường dẫn ảnh chân dung HUD (tái dùng ảnh Ink Scout có sẵn). */
  portraitUrl?: string;
}

export interface RuntimeHandle {
  readonly game: Game;
  readonly input: InputSource;
  pause(): void;
  resume(): void;
  togglePause(): void;
  setShake(v: SaveSettings["shake"]): void;
  setMuted(m: boolean): void;
  unlockAudio(): void;
  snapshot(): SaveData;
  destroy(): void;
  /** Số liệu để kiểm rò rỉ (chỉ đọc). */
  stats(): { rafActive: boolean; instances: number; steps: number; frames: number; listeners: number };
}

const STEP_MS = 1000 / TICK_RATE;
const MAX_STEPS_PER_FRAME = 5;

let instances = 0;

export async function createRuntime(opts: RuntimeOptions): Promise<RuntimeHandle> {
  const { canvas, store } = opts;
  const prev = await store.load();
  let save: SaveData;
  if (opts.newGame) {
    save = defaultSave();
    if (prev) {
      save.settings = prev.settings;
      save.bestFrames = prev.bestFrames;
    }
  } else {
    save = prev ?? defaultSave();
  }

  const game = new Game({ save, seed: opts.seed ?? (Math.floor(Math.random() * 0x7fffffff) | 1) });
  let portrait: HTMLImageElement | null = null;
  if (opts.portraitUrl) {
    portrait = new Image();
    portrait.decoding = "async";
    portrait.src = opts.portraitUrl;
  }
  const renderer = new Renderer(canvas, portrait);
  const audio = new AudioBus(game.save.settings.muted);
  const input = new InputSource();
  input.active = true;

  let raf = 0;
  let last = 0;
  let acc = 0;
  let paused = false;
  let destroyed = false;
  let steps = 0;
  let frames = 0;
  let listeners = 0;
  let caption: UiSnapshot["caption"] = null;
  let captionUntil = 0;
  let lastUiKey = "";
  let mood: Mood = "explore";
  instances += 1;

  const disposers: Array<() => void> = [];
  const listen = <T extends EventTarget>(t: T, type: string, fn: EventListenerOrEventListenerObject, o?: AddEventListenerOptions): void => {
    t.addEventListener(type, fn, o);
    listeners += 1;
    disposers.push(() => {
      t.removeEventListener(type, fn, o);
      listeners -= 1;
    });
  };

  const persist = (): void => {
    void store.save(game.snapshot());
  };

  const touchUi = (): void => {
    lastUiKey = "";
  };

  const setCaption = (id: string): void => {
    const cap = CAPTIONS[id];
    if (!cap) return;
    const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
    const text = touch && cap.touch ? cap.touch : cap.text;
    caption = { id, who: cap.who, text, touch: cap.touch };
    captionUntil = performance.now() + (cap.ms ?? Math.max(3200, text.length * 62));
  };

  const handleEvents = (events: GameEvent[]): void => {
    if (events.length === 0) return;
    renderer.onEvents(events, game);
    for (const e of events) {
      switch (e.t) {
        case "sfx":
          audio.play(e.name);
          break;
        case "caption":
          setCaption(e.id);
          break;
        case "save":
        case "died":
          persist();
          break;
        case "bossPhase":
          mood = e.phase === "dying" ? "explore" : "boss";
          audio.setMood(mood);
          break;
        case "roomEnter":
          mood = "explore";
          audio.setMood(mood);
          caption = null;
          break;
        case "complete":
          mood = "none";
          audio.setMood(mood);
          break;
        default:
          break;
      }
    }
    // Boss thức dậy → nhạc căng lên.
    if (game.boss && game.boss.active && mood !== "boss") {
      mood = "boss";
      audio.setMood(mood);
    }
  };

  const stepOnce = (): void => {
    const inp = input.read();
    game.step(inp);
    steps += 1;
    handleEvents(game.drainEvents());
    renderer.step(game);
  };

  const computeUi = (): UiSnapshot => {
    const b = game.boss;
    const bossActive = !!b && b.active && b.state !== "dead";
    return {
      mode: game.mode,
      paused,
      caption,
      read: game.mode === "read" && game.readId && game.readKind ? { kind: game.readKind, id: game.readId, readT: game.readT } : null,
      ending:
        game.mode === "ending"
          ? { stage: game.endingStage, kind: game.endingKind, choice: game.endingChoice, page: game.endingPage, pages: game.endingKind ? game.endingPages() : [] }
          : null,
      boss: bossActive && b ? { phase: b.phase, hp: b.hp, max: b.maxHp } : null,
      marginStep: game.save.marginStep,
      memories: [...game.save.memories],
      settings: { ...game.save.settings },
      result: game.result(),
      saveFailed: store.failed === true,
    };
  };

  const pushUi = (force = false): void => {
    const s = computeUi();
    // Khoá so sánh gọn: bỏ máu boss chi tiết (đổi theo từng khung) — chỉ quan tâm có/không + giai đoạn.
    const key = [s.mode, s.paused ? 1 : 0, s.caption?.id ?? "", s.read ? `${s.read.kind}${s.read.id}` : "", s.ending ? `${s.ending.stage}${s.ending.kind}${s.ending.choice}${s.ending.page}` : "", s.boss ? `b${s.boss.phase}` : "", s.marginStep ? 1 : 0, s.memories.join(""), s.settings.shake, s.settings.muted ? 1 : 0, s.result ? 1 : 0, s.saveFailed ? 1 : 0].join("|");
    if (!force && key === lastUiKey) return;
    lastUiKey = key;
    opts.onUi(s);
  };

  const frame = (now: number): void => {
    if (destroyed) return;
    raf = requestAnimationFrame(frame);
    frames += 1;
    if (last === 0) last = now;
    let dt = now - last;
    last = now;
    if (dt > 100) dt = 100;
    if (!paused) {
      acc += dt;
      let n = 0;
      while (acc >= STEP_MS && n < MAX_STEPS_PER_FRAME) {
        stepOnce();
        acc -= STEP_MS;
        n += 1;
      }
      if (n === MAX_STEPS_PER_FRAME) acc = 0;
    }
    renderer.render(game);
    if (caption && performance.now() > captionUntil) caption = null;
    pushUi();
  };

  const pause = (): void => {
    if (paused || destroyed || game.mode === "complete") return;
    paused = true;
    input.releaseAll();
    audio.suspend();
    persist();
    touchUi();
    pushUi(true);
  };

  const resume = (): void => {
    if (!paused || destroyed) return;
    paused = false;
    last = 0;
    acc = 0;
    audio.resume();
    touchUi();
    pushUi(true);
  };

  input.attach(window, {
    onPause: () => (paused ? resume() : pause()),
    onAnyKey: () => audio.unlock(),
  });
  listeners += 3; // keydown, keyup, blur do InputSource gắn
  disposers.push(() => {
    input.detach();
    listeners -= 3;
  });
  listen(document, "visibilitychange", () => {
    if (document.hidden) pause();
  });
  listen(window, "blur", () => pause());
  listen(window, "pagehide", () => persist());

  // Khung đầu tiên: dựng phòng, đẩy UI ban đầu.
  handleEvents(game.drainEvents());
  renderer.step(game);
  renderer.render(game);
  pushUi(true);
  raf = requestAnimationFrame(frame);

  const handle: RuntimeHandle = {
    game,
    input,
    pause,
    resume,
    togglePause: () => (paused ? resume() : pause()),
    setShake: (v) => {
      game.setSettings({ shake: v });
      handleEvents(game.drainEvents());
      touchUi();
    },
    setMuted: (m) => {
      game.setSettings({ muted: m });
      audio.setMuted(m);
      if (!m) audio.setMood(mood);
      handleEvents(game.drainEvents());
      touchUi();
    },
    unlockAudio: () => {
      audio.unlock();
      audio.setMood(mood);
    },
    snapshot: () => game.snapshot(),
    destroy: () => {
      if (destroyed) return;
      destroyed = true;
      cancelAnimationFrame(raf);
      raf = 0;
      persist();
      for (const d of disposers.splice(0)) d();
      audio.dispose();
      renderer.dispose();
      instances -= 1;
    },
    stats: () => ({ rafActive: raf !== 0, instances, steps, frames, listeners }),
  };

  // Móc QA: CHỈ có khi trang chủ động đặt cờ trước khi tải (test/QA tự động); người chơi thường không bao giờ thấy nó. Chỉ phơi bày chính mô phỏng
  // cục bộ của game — không có API quản trị, khoá, hay dữ liệu máy chủ.
  if (typeof window !== "undefined" && (window as unknown as { __INK_QA__?: boolean }).__INK_QA__ === true) {
    const w = window as unknown as { __INK_QA_API__?: unknown };
    w.__INK_QA_API__ = { game, runtime: handle, renderer };
    disposers.push(() => {
      delete w.__INK_QA_API__;
    });
  }
  return handle;
}

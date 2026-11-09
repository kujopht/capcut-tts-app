import type { SfxName } from "../core/types";

/**
 * Âm thanh tổng hợp bằng Web Audio — không tệp âm thanh, không bản quyền ngoài. Chính sách tự phát của trình duyệt: `AudioContext` chỉ được tạo/mở
 * khi có cử chỉ người dùng (`unlock()` gọi từ nút Chơi / phím đầu tiên). Khi tắt tiếng (`muted`) thì không phát gì — game chơi hệt như bình thường.
 */
export type Mood = "none" | "explore" | "boss";

type WindowWithWebkit = Window & { webkitAudioContext?: typeof AudioContext };

export class AudioBus {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private ambientNodes: AudioScheduledSourceNode[] = [];
  private ambientGain: GainNode | null = null;
  private lfo: GainNode | null = null;
  private mood: Mood = "none";
  private readonly last = new Map<SfxName, number>();
  private noiseBuf: AudioBuffer | null = null;
  private disposed = false;

  constructor(private muted: boolean) {}

  get isMuted(): boolean {
    return this.muted;
  }

  /** Gọi trong một cử chỉ người dùng. An toàn khi gọi nhiều lần. */
  unlock(): void {
    if (this.disposed || this.muted) return;
    try {
      if (!this.ctx) {
        const AC = window.AudioContext ?? (window as WindowWithWebkit).webkitAudioContext;
        if (!AC) return;
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.gain.value = 0.45;
        const comp = this.ctx.createDynamicsCompressor();
        this.master.connect(comp);
        comp.connect(this.ctx.destination);
        this.startAmbient();
      }
      if (this.ctx.state === "suspended") void this.ctx.resume();
    } catch {
      // Không có âm thanh: game vẫn chạy.
    }
  }

  setMuted(m: boolean): void {
    this.muted = m;
    if (m) {
      this.stopAmbient();
      if (this.ctx && this.ctx.state === "running") void this.ctx.suspend();
    } else {
      this.unlock();
      if (this.ctx && !this.ambientGain) this.startAmbient();
    }
  }

  setMood(m: Mood): void {
    this.mood = m;
    if (this.ambientGain && this.ctx) {
      const g = m === "none" ? 0 : m === "boss" ? 0.1 : 0.05;
      this.ambientGain.gain.setTargetAtTime(g, this.ctx.currentTime, 0.4);
    }
    if (this.lfo && this.ctx) this.lfo.gain.setTargetAtTime(m === "boss" ? 0.05 : 0.0, this.ctx.currentTime, 0.3);
  }

  /** Tạm dừng (mở menu/ẩn tab): treo ngữ cảnh để không tốn CPU. */
  suspend(): void {
    if (this.ctx && this.ctx.state === "running") void this.ctx.suspend();
  }

  resume(): void {
    if (!this.muted && this.ctx && this.ctx.state === "suspended") void this.ctx.resume();
  }

  dispose(): void {
    this.disposed = true;
    this.stopAmbient();
    const c = this.ctx;
    this.ctx = null;
    this.master = null;
    if (c) void c.close().catch(() => undefined);
  }

  // ------------------------------------------------------------------ hiệu ứng
  play(name: SfxName): void {
    const c = this.ctx;
    if (this.muted || !c || !this.master || c.state !== "running") return;
    const now = c.currentTime;
    const prev = this.last.get(name) ?? -1;
    if (now - prev < 0.035) return;
    this.last.set(name, now);
    switch (name) {
      case "jump": this.tone(300, 520, 0.12, "square", 0.1); break;
      case "land": this.noise(0.08, 400, 0.12); break;
      case "slash": this.noise(0.1, 2600, 0.12, "bandpass"); this.tone(700, 260, 0.08, "sawtooth", 0.05); break;
      case "hit": this.noise(0.06, 1400, 0.16); this.tone(180, 90, 0.1, "square", 0.12); break;
      case "enemyDie": this.tone(420, 70, 0.28, "sawtooth", 0.11); this.noise(0.18, 900, 0.08); break;
      case "hurt": this.tone(160, 60, 0.24, "sawtooth", 0.18); this.noise(0.12, 600, 0.12); break;
      case "pulse": this.tone(260, 1040, 0.4, "sine", 0.16); this.tone(390, 1560, 0.4, "triangle", 0.07, 0.04); break;
      case "pickup": this.arp([523, 659, 784], 0.07, "triangle", 0.12); break;
      case "memory": this.arp([392, 523, 659, 784, 1047], 0.11, "sine", 0.14); break;
      case "dash": this.noise(0.14, 1800, 0.12, "bandpass"); this.tone(220, 520, 0.12, "sine", 0.06); break;
      case "checkpoint": this.arp([440, 660], 0.12, "triangle", 0.13); break;
      case "telegraph": this.tone(880, 880, 0.08, "square", 0.05); this.tone(660, 660, 0.08, "square", 0.05, 0.1); break;
      case "bossHit": this.tone(120, 50, 0.2, "square", 0.2); this.noise(0.1, 500, 0.12); break;
      case "bossPhase": this.tone(60, 200, 0.9, "sawtooth", 0.2); this.noise(0.8, 300, 0.12); break;
      case "bossDie": this.tone(220, 30, 1.6, "sawtooth", 0.22); this.noise(1.2, 400, 0.16); break;
      case "door": this.noise(0.4, 300, 0.2); this.tone(90, 60, 0.4, "square", 0.1); break;
      case "glyph": this.arp([880, 1175], 0.06, "sine", 0.07); break;
      case "death": this.tone(300, 40, 0.8, "sawtooth", 0.2); break;
      case "ui": this.tone(660, 760, 0.05, "square", 0.05); break;
      default: break;
    }
  }

  private tone(f0: number, f1: number, dur: number, type: OscillatorType, vol: number, delay = 0): void {
    const c = this.ctx;
    const m = this.master;
    if (!c || !m) return;
    const t0 = c.currentTime + delay;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f0, t0);
    o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g);
    g.connect(m);
    o.start(t0);
    o.stop(t0 + dur + 0.02);
  }

  private arp(notes: readonly number[], step: number, type: OscillatorType, vol: number): void {
    notes.forEach((f, i) => this.tone(f, f, step * 1.6, type, vol, i * step));
  }

  private getNoise(): AudioBuffer | null {
    const c = this.ctx;
    if (!c) return null;
    if (!this.noiseBuf) {
      const len = c.sampleRate;
      const b = c.createBuffer(1, len, c.sampleRate);
      const d = b.getChannelData(0);
      // Hạt giống cố định → tiếng ồn giống hệt mỗi lần (không phụ thuộc Math.random).
      let s = 0x9e3779b9;
      for (let i = 0; i < len; i += 1) {
        s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
        d[i] = ((s >>> 0) / 0xffffffff) * 2 - 1;
      }
      this.noiseBuf = b;
    }
    return this.noiseBuf;
  }

  private noise(dur: number, freq: number, vol: number, type: BiquadFilterType = "lowpass"): void {
    const c = this.ctx;
    const m = this.master;
    const buf = this.getNoise();
    if (!c || !m || !buf) return;
    const t0 = c.currentTime;
    const src = c.createBufferSource();
    src.buffer = buf;
    const f = c.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    const g = c.createGain();
    g.gain.setValueAtTime(vol, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f);
    f.connect(g);
    g.connect(m);
    src.start(t0);
    src.stop(t0 + dur + 0.02);
  }

  // ------------------------------------------------------------------ nền
  private startAmbient(): void {
    const c = this.ctx;
    const m = this.master;
    if (!c || !m || this.ambientGain) return;
    const g = c.createGain();
    g.gain.value = this.mood === "none" ? 0.0 : 0.05;
    g.connect(m);
    const lfoGain = c.createGain();
    lfoGain.gain.value = 0;
    const lfo = c.createOscillator();
    lfo.frequency.value = 2;
    lfo.connect(lfoGain);
    lfoGain.connect(g.gain);
    lfo.start();
    for (const [f, type] of [[55, "sine"], [82.6, "sine"], [110.4, "triangle"]] as const) {
      const o = c.createOscillator();
      o.type = type;
      o.frequency.value = f;
      const og = c.createGain();
      og.gain.value = type === "triangle" ? 0.25 : 0.7;
      o.connect(og);
      og.connect(g);
      o.start();
      this.ambientNodes.push(o);
    }
    this.ambientNodes.push(lfo);
    this.ambientGain = g;
    this.lfo = lfoGain;
  }

  private stopAmbient(): void {
    for (const n of this.ambientNodes) {
      try {
        n.stop();
      } catch {
        // đã dừng
      }
    }
    this.ambientNodes = [];
    this.ambientGain = null;
    this.lfo = null;
  }
}

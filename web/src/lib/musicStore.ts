/**
 * Global Fantasy Music Synthesizer & Soundwave Store.
 *
 * Cung cap am thanh ambient fantasy phat xuyen suot website bang Web Audio API,
 * dong bo trang thai phat va du lieu song am (soundwave frequency data)
 * len thanh tac vu (navbar) va trang Giai tri.
 */

export interface MiniGame {
  id: string;
  title: string;
  desc: string;
  tag: string;
  color: string;
  path: string;
  icon: string;
}

import {
  SHOTS_LYRICS,
  SHADOW_OF_THE_SUN_LYRICS,
  type LyricLine,
  type LyricWord,
} from "@/lib/lyricsData";
import { audioFocus, UU_TIEN } from "@/lib/audioFocus";
import { MUSIC_ENABLED } from "@/lib/features";

export type { LyricLine, LyricWord };

export interface MusicTrack {
  id: string;
  title: string;
  subtitle: string;
  duration: string;
  mood: string;
  bpm: number;
  notes: number[];
  color: string;
  icon: string;
  audioSrc?: string;
  lyrics?: LyricLine[];
}

export const TRACKS: MusicTrack[] = [
  {
    id: "shots-broiler-remix",
    title: "Shots (Broiler Remix)",
    subtitle: "Imagine Dragons • Broiler Remix (Lyrics + Vietsub)",
    duration: "3:11",
    mood: "Bass Drop Siêu Bốc (EDM / Trap Remix)",
    bpm: 128,
    notes: [130.81, 164.81, 196.00, 246.94, 293.66],
    color: "#06b6d4",
    icon: "⚡",
    audioSrc: "/audio/shots_broiler_remix.mp3",
    lyrics: SHOTS_LYRICS,
  },
  {
    id: "shadow-of-the-sun",
    title: "Shadow Of The Sun",
    subtitle: "Professor Green • Lyrics & Vietsub (Official Beat)",
    duration: "4:01",
    mood: "Bùng nổ & Sôi động (Hip-hop / Electronic)",
    bpm: 126,
    notes: [130.81, 164.81, 196.00, 261.63, 329.63],
    color: "#f59e0b",
    icon: "☀️",
    audioSrc: "/audio/shadow_of_the_sun.mp3",
    lyrics: SHADOW_OF_THE_SUN_LYRICS,
  },
  {
    id: "celestial-waltz",
    title: "Vũ Khúc Tinh Vân",
    subtitle: "Celestial Waltz • Ambient Synth & Strings",
    duration: "3:42",
    mood: "Huyền ảo & Tĩnh lặng",
    bpm: 72,
    notes: [261.63, 329.63, 392.00, 523.25, 659.25],
    color: "#60a5fa",
    icon: "🌌",
  },
  {
    id: "midnight-library",
    title: "Thư Viện Lúc Nửa Đêm",
    subtitle: "Midnight Archive • Lofi Chill & Piano",
    duration: "2:58",
    mood: "Thư thái & Đọc sách",
    bpm: 80,
    notes: [220.00, 261.63, 329.63, 440.00, 523.25],
    color: "#38bdf8",
    icon: "📖",
  },
  {
    id: "astral-ocean",
    title: "Tiếng Vọng Biển Sao",
    subtitle: "Astral Ocean • Ethereal Calm Waves",
    duration: "4:15",
    mood: "Mơ màng & Tĩnh tâm",
    bpm: 60,
    notes: [174.61, 220.00, 261.63, 349.23, 440.00],
    color: "#a78bfa",
    icon: "🌊",
  },
  {
    id: "dawn-odyssey",
    title: "Khúc Ca Khởi Hành",
    subtitle: "Dawn of Odyssey • Fantasy Acoustic",
    duration: "3:10",
    mood: "Khám phá & Tràn đầy hy vọng",
    bpm: 96,
    notes: [196.00, 246.94, 293.66, 392.00, 493.88],
    color: "#38bdf8",
    icon: "⚔️",
  },
];

export type SoundwaveStyle = "bottom-spectrum" | "trap-nation" | "bottom-wave";

export interface MusicSnapshot {
  isPlaying: boolean;
  currentTrackIndex: number;
  currentTrack: MusicTrack;
  volume: number;
  soundwaveStyle: SoundwaveStyle;
}

type Listener = () => void;

class MusicStore {
  private isPlaying = false;
  private currentTrackIndex = 0;
  private volume = 0.5;
  private soundwaveStyle: SoundwaveStyle = "bottom-spectrum";
  private listeners = new Set<Listener>();

  private snapshot: MusicSnapshot = {
    isPlaying: false,
    currentTrackIndex: 0,
    currentTrack: TRACKS[0],
    volume: 0.5,
    soundwaveStyle: "bottom-spectrum",
  };

  private ctx: AudioContext | null = null;
  private timerId: number | null = null;
  private masterGain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private audioElement: HTMLAudioElement | null = null;
  private audioSourceNode: MediaElementAudioSourceNode | null = null;

  private currentTime = 0;
  private timeListeners = new Set<(time: number) => void>();

  private rafTimeId: number | null = null;

  private startTimeLoop = () => {
    if (typeof window === "undefined") return;
    if (this.rafTimeId !== null) return;
    const tick = () => {
      if (this.isPlaying) {
        if (this.audioElement && !Number.isNaN(this.audioElement.currentTime)) {
          this.currentTime = this.audioElement.currentTime;
          this.notifyTime();
        }
        this.rafTimeId = window.requestAnimationFrame(tick);
      } else {
        this.rafTimeId = null;
      }
    };
    this.rafTimeId = window.requestAnimationFrame(tick);
  };

  private stopTimeLoop = () => {
    if (this.rafTimeId !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(this.rafTimeId);
      this.rafTimeId = null;
    }
  };

  public getCurrentTime = (): number => {
    if (this.audioElement && !Number.isNaN(this.audioElement.currentTime)) {
      return this.audioElement.currentTime;
    }
    return this.currentTime;
  };

  public subscribeTime = (listener: (time: number) => void) => {
    this.timeListeners.add(listener);
    return () => {
      this.timeListeners.delete(listener);
    };
  };

  private notifyTime = () => {
    const t = this.getCurrentTime();
    this.timeListeners.forEach((fn) => fn(t));
  };

  public getSnapshot = (): MusicSnapshot => {
    return this.snapshot;
  };

  public subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private updateSnapshot() {
    this.snapshot = {
      isPlaying: this.isPlaying,
      currentTrackIndex: this.currentTrackIndex,
      currentTrack: TRACKS[this.currentTrackIndex],
      volume: this.volume,
      soundwaveStyle: this.soundwaveStyle,
    };
    this.listeners.forEach((l) => l());
  }

  public setSoundwaveStyle = (style: SoundwaveStyle) => {
    this.soundwaveStyle = style;
    this.updateSnapshot();
  };

  public cycleSoundwaveStyle = () => {
    const list: SoundwaveStyle[] = ["bottom-spectrum", "trap-nation", "bottom-wave"];
    const curIdx = list.indexOf(this.soundwaveStyle);
    this.soundwaveStyle = list[(curIdx + 1) % list.length];
    this.updateSnapshot();
  };

  private initAudio() {
    if (typeof window === "undefined") return;
    if (this.ctx && this.ctx.state !== "closed") return;
    try {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      this.ctx = new AudioCtx();
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.setValueAtTime(this.volume, this.ctx.currentTime);

      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.75; // Studio-grade meter smoothing: eliminates jitter while preserving punch
      this.analyser.minDecibels = -85;
      this.analyser.maxDecibels = -15;

      this.masterGain.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);

      if (typeof Audio !== "undefined" && !this.audioElement) {
        this.audioElement = new Audio();
        // Do NOT set crossOrigin = "anonymous" on same-origin local assets
        // to prevent Chrome from zeroing out AnalyserNode frequency data
        this.audioSourceNode = this.ctx.createMediaElementSource(this.audioElement);
        this.audioSourceNode.connect(this.masterGain);
        this.audioElement.addEventListener("ended", () => {
          this.nextTrack();
        });
        this.audioElement.addEventListener("loadedmetadata", () => {
          this.notifyTime();
          this.updateSnapshot();
        });
        this.audioElement.addEventListener("durationchange", () => {
          this.notifyTime();
          this.updateSnapshot();
        });
        this.audioElement.addEventListener("timeupdate", () => {
          if (this.audioElement) {
            this.currentTime = this.audioElement.currentTime;
            this.notifyTime();
          }
        });
        this.audioElement.addEventListener("seeked", () => {
          if (this.audioElement) {
            this.currentTime = this.audioElement.currentTime;
            this.notifyTime();
          }
        });
      }
    } catch {
      // Not supported
    }
  }

  public getFrequencyData = (outArray: Uint8Array): void => {
    if (this.analyser && this.isPlaying) {
      this.analyser.getByteFrequencyData(outArray);

      // Check if browser/hardware zeroed out frequency data (e.g. crossOrigin / muted / synth track)
      let sum = 0;
      for (let i = 0; i < Math.min(16, outArray.length); i++) {
        sum += outArray[i];
      }

      if (sum === 0 && this.isPlaying) {
        // Synthesize dynamic reactive rhythmic beat based on track BPM & currentTime
        const track = TRACKS[this.currentTrackIndex];
        const bpm = track?.bpm || 128;
        const beatProgress = (this.currentTime * (bpm / 60)) % 1;
        const kickPulse = Math.max(0, 1 - beatProgress * 3.5);
        for (let i = 0; i < outArray.length; i++) {
          const wave = Math.sin(this.currentTime * 7 + i * 0.32) * 0.5 + 0.5;
          const energy = (kickPulse * 0.72 + wave * 0.28) * Math.max(0.1, 1 - i / outArray.length);
          outArray[i] = Math.floor(energy * 220);
        }
      }
    } else {
      outArray.fill(0);
    }
  };

  private startTrack(resume = false) {
    // Nhac dang TAM AN (`lib/features.ts`): khong tao AudioContext/<audio>,
    // khong tai tep nao, khong phat — du ai goi `play()` tu mot loi vao cu.
    if (!MUSIC_ENABLED) return;
    this.initAudio();
    if (!this.ctx || !this.masterGain) return;

    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }

    const track = TRACKS[this.currentTrackIndex];

    if (track.audioSrc && this.audioElement) {
      if (this.timerId) {
        window.clearInterval(this.timerId);
        this.timerId = null;
      }
      const isSameSrc = this.audioElement.src.endsWith(track.audioSrc);
      if (!isSameSrc) {
        this.audioElement.src = track.audioSrc;
        this.audioElement.currentTime = 0;
        this.currentTime = 0;
        this.notifyTime();
      } else if (!resume) {
        this.audioElement.currentTime = 0;
        this.currentTime = 0;
        this.notifyTime();
      }
      this.audioElement.play().then(() => {
        if (this.ctx && this.ctx.state === "suspended") {
          this.ctx.resume().catch(() => {});
        }
        this.startTimeLoop();
      }).catch(() => {});
      this.startTimeLoop();
      return;
    }

    // Synthesizer fallback for tracks without audioSrc
    if (this.audioElement) {
      this.audioElement.pause();
    }
    if (this.timerId) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }

    let step = 0;
    const notes = track.notes;
    const intervalMs = (60 / track.bpm) * 1000;

    const playNote = () => {
      if (!this.ctx || this.ctx.state === "closed" || !this.masterGain || !this.isPlaying)
        return;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      const filter = this.ctx.createBiquadFilter();

      filter.type = "lowpass";
      filter.frequency.setValueAtTime(800, this.ctx.currentTime);

      const freq = notes[step % notes.length];
      step++;

      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime);

      const t = this.ctx.currentTime;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.1);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + (intervalMs / 1000) * 1.5);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.masterGain);

      osc.start(t);
      osc.stop(t + (intervalMs / 1000) * 1.6);

      this.currentTime = (this.currentTime + intervalMs / 1000) % 240;
      this.notifyTime();
    };

    playNote();
    this.timerId = window.setInterval(playNote, intervalMs);
    this.startTimeLoop();
  }

  private stopPlayback() {
    this.stopTimeLoop();
    if (this.audioElement) {
      this.audioElement.pause();
    }
    if (this.timerId) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  public togglePlay = () => {
    // Nhac tam an: khong bao gio chuyen sang "dang phat" (UI se noi doi).
    if (!MUSIC_ENABLED) return;
    this.isPlaying = !this.isPlaying;
    if (this.isPlaying) {
      this.startTrack(true);
    } else {
      this.stopPlayback();
    }
    this.updateSnapshot();
  };

  public play = () => {
    if (!MUSIC_ENABLED) return;
    if (!this.isPlaying) {
      this.isPlaying = true;
      this.startTrack(true);
      this.updateSnapshot();
    }
  };

  public pause = () => {
    if (this.isPlaying) {
      this.isPlaying = false;
      this.stopPlayback();
      this.updateSnapshot();
    }
  };

  public setTrackIndex = (index: number) => {
    if (index < 0 || index >= TRACKS.length) return;
    this.currentTrackIndex = index;
    if (this.isPlaying) {
      this.startTrack(false);
    }
    this.updateSnapshot();
  };

  public nextTrack = () => {
    this.currentTrackIndex = (this.currentTrackIndex + 1) % TRACKS.length;
    if (this.isPlaying) {
      this.startTrack(false);
    }
    this.updateSnapshot();
  };

  public prevTrack = () => {
    this.currentTrackIndex =
      (this.currentTrackIndex - 1 + TRACKS.length) % TRACKS.length;
    if (this.isPlaying) {
      this.startTrack(false);
    }
    this.updateSnapshot();
  };
  /** Ha/tra am luong TAM THOI khi giong doc chuong giu tieng (chinh sach
      "duck" cua `lib/audioFocus.ts`). KHONG doi `this.volume` — muc nguoi
      dung da chon van nguyen. */
  public haAmLuong = (ha: boolean) => {
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setTargetAtTime(ha ? this.volume * 0.2 : this.volume, this.ctx.currentTime, 0.15);
    }
  };

  public setVolume = (v: number) => {
    this.volume = Math.max(0, Math.min(1, v));
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setValueAtTime(this.volume, this.ctx.currentTime);
    }
    this.updateSnapshot();
  };

  public seek = (timeInSeconds: number) => {
    const clamped = Math.max(0, timeInSeconds);
    this.currentTime = clamped;
    if (this.audioElement) {
      try {
        if (!Number.isNaN(this.audioElement.duration) && this.audioElement.duration > 0) {
          this.audioElement.currentTime = Math.min(clamped, this.audioElement.duration);
        } else {
          this.audioElement.currentTime = clamped;
        }
      } catch {
        // Audio element not yet ready or cross-origin
      }
    }
    this.notifyTime();
  };

  public getDurationSeconds = (): number => {
    if (this.audioElement && !Number.isNaN(this.audioElement.duration) && this.audioElement.duration > 0) {
      return this.audioElement.duration;
    }
    const track = TRACKS[this.currentTrackIndex];
    if (track?.duration) {
      return parseDurationToSeconds(track.duration);
    }
    return 180;
  };
}

export function parseDurationToSeconds(durationStr: string): number {
  if (!durationStr) return 180;
  const parts = durationStr.split(":");
  if (parts.length === 2) {
    const min = parseInt(parts[0], 10) || 0;
    const sec = parseInt(parts[1], 10) || 0;
    return min * 60 + sec;
  }
  return 180;
}

export function formatTime(seconds: number): string {
  if (Number.isNaN(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export function getActiveLyricLine(track: MusicTrack, time: number): LyricLine | null {
  if (!track.lyrics || track.lyrics.length === 0) return null;
  if (time < track.lyrics[0].start) {
    return track.lyrics[0];
  }
  for (let i = track.lyrics.length - 1; i >= 0; i--) {
    if (time >= track.lyrics[i].start) {
      return track.lyrics[i];
    }
  }
  return track.lyrics[0];
}

export function getTrackLyric(track: MusicTrack, time: number): string {
  const line = getActiveLyricLine(track, time);
  if (!line) {
    return `${track.icon} ${track.title} • ${track.subtitle}`;
  }
  return line.text;
}

export const musicStore = new MusicStore();

/*
  Kenh "ambient" cua bo dieu phoi tieng (`lib/audioFocus.ts`): giong doc
  chuong > nhac nen. Chinh sach hom nay la "pause" — dung hanh vi cu, khi
  `AudioEngine` con goi thang `musicStore.pause()`. Nhanh "duck" da noi san
  de san pham nhac sau nay chi phai doi MOT dong `CHINH_SACH`, khong cham
  toi dong co truyen.

  Nhac TAT (`lib/features.ts`): KHONG dang ky kenh, KHONG lo ra `window` —
  khong gi co the goi no phat.
*/
if (MUSIC_ENABLED) {
  audioFocus.dangKy("ambient", {
    uuTien: UU_TIEN.ambient,
    khiBiCat: (kieu) => (kieu === "duck" ? musicStore.haAmLuong(true) : musicStore.pause()),
    khiDuocTraLai: () => musicStore.haAmLuong(false),
  });

  if (typeof window !== "undefined") {
    (window as any).musicStore = musicStore;
  }
}

/**
 * Nạp LƯỜI runtime Ink Scout (v1.3.0) + manifest web — MỘT lần cho cả trang.
 *
 * Runtime là các tệp `ink-scout*.js` của bộ linh vật đã duyệt, GIỮ NGUYÊN từng byte
 * (`web/public/mascot/ink-scout/runtime/`, sha256 trong `SUBSET.json`). Chúng là các
 * IIFE cổ điển gắn `window.InkScout*` nên được nạp bằng thẻ `<script>` khi linh vật thật
 * sự cần hiện, không đi vào bundle JS của trang.
 *
 * THỨ TỰ BẮT BUỘC (HANDOFF §3): player → walk-rig → physics → presence. Mọi script được
 * chèn với `async = false` nên TẢI SONG SONG nhưng THỰC THI đúng thứ tự chèn. Mọi URL
 * mang `?v=<phiên bản>` cùng phiên bản với manifest (tránh runtime mới + manifest cũ);
 * `INK_SCOUT_VERSION` được test đối chiếu với `manifest.json` và `SUBSET.json`.
 *
 * `physics` (kéo thả, nhấc, rơi, đáp lên panel, đi bộ liên tục) và `presence` (nhìn theo
 * con trỏ, thở, xoa đầu) là mô-đun TUỲ CHỌN của gói: thiếu một mô-đun thì linh vật vẫn
 * chạy bằng player cơ bản (`loadInkScout` không bao giờ ném chỉ vì chúng không tải được).
 */
import type { RuntimeLike } from "./companionDirector";

export const INK_SCOUT_BASE = "/mascot/ink-scout/";
export const INK_SCOUT_VERSION = "1.3.0";

/** Đoạn ngang của một mặt phẳng để linh vật đáp lên (toạ độ của "gốc" host; `y` = top-left canvas khi chân chạm mặt). */
export interface Surface {
  left: number;
  right: number;
  y: number;
}

export interface InkScoutRuntime extends RuntimeLike {
  setBounds(bounds: { left?: number; right?: number; top?: number; bottom?: number }): void;
  setSize(size: number): void;
  setPaused(value: boolean): void;
  cancelMotion(): void;
  host: HTMLElement;
  state: string;
  paused: boolean;
  ready: Promise<boolean>;
  size: number;
}

export interface InkScoutCtor {
  new (host: HTMLElement, options: Record<string, unknown>): InkScoutRuntime;
}

/** Phần API của `InkScoutPhysics` mà sản phẩm dùng. */
export interface InkScoutPhysicsLike {
  enabled: boolean;
  /** `drag` | `fall` | `land` | `jump` | `walk` | `walk-settle` | `null` (đứng yên). */
  readonly mode: string | null;
  ready: Promise<void>;
  surfaces: () => Surface[];
}

export interface InkScoutPhysicsCtor {
  new (runtime: InkScoutRuntime, options: { surfaces: () => Surface[] }): InkScoutPhysicsLike;
}

/** Phần API của `InkScoutPresence` (nhìn theo con trỏ, thở, xoa đầu). Một instance cho mỗi runtime; bật/tắt bằng `enabled`. */
export interface InkScoutPresenceLike {
  enabled: boolean;
  pat(): Promise<boolean>;
  start(): void;
  stop(): void;
  reset(): void;
}

export interface InkScoutPresenceCtor {
  new (runtime: InkScoutRuntime, options: { stage?: HTMLElement; physics?: InkScoutPhysicsLike | null }): InkScoutPresenceLike;
}

export interface Loaded {
  Ctor: InkScoutCtor;
  /** `null` nếu mô-đun physics/rig không tải được (linh vật vẫn chạy, chỉ không kéo thả). */
  Physics: InkScoutPhysicsCtor | null;
  manifest: Record<string, unknown>;
}

interface InkScoutWindow {
  InkScout?: InkScoutCtor;
  InkScoutWalkRig?: unknown;
  InkScoutPhysics?: InkScoutPhysicsCtor;
  InkScoutPresence?: InkScoutPresenceCtor;
}

const scripts = new Map<string, Promise<void>>();

/** Chèn MỘT `<script async=false>`; gọi lại cùng `file` thì dùng lại (kể cả khi thẻ đã có trong DOM). */
function loadScript(file: string): Promise<void> {
  const cached = scripts.get(file);
  if (cached) return cached;
  const p = new Promise<void>((resolve, reject) => {
    const id = `ink-scout-${file.replace(/\.js$/, "")}`;
    let el = document.getElementById(id) as HTMLScriptElement | null;
    if (!el) {
      el = document.createElement("script");
      el.id = id;
      el.src = `${INK_SCOUT_BASE}runtime/${file}?v=${INK_SCOUT_VERSION}`;
      el.async = false; // tải song song, THỰC THI đúng thứ tự chèn (player → rig → physics → presence)
      document.head.appendChild(el);
    }
    el.addEventListener("load", () => resolve(), { once: true });
    el.addEventListener("error", () => reject(new Error(`Unable to load ${file}`)), { once: true });
  });
  scripts.set(file, p);
  p.catch(() => scripts.delete(file)); // cho phép thử lại ở lần mở sau
  return p;
}

let loading: Promise<Loaded> | null = null;

export function loadInkScout(): Promise<Loaded> {
  if (!loading) {
    const w = window as unknown as InkScoutWindow;
    // Player (bắt buộc) + rig + physics (tuỳ chọn, chèn NGAY SAU player để giữ thứ tự) + manifest, song song.
    const core = loadScript("ink-scout.js");
    const optional = loadScript("ink-scout-walk-rig.js")
      .then(() => loadScript("ink-scout-physics.js"))
      .then(() => w.InkScoutPhysics ?? null)
      .catch(() => null);
    const manifest = fetch(`${INK_SCOUT_BASE}manifest.json?v=${INK_SCOUT_VERSION}`, { credentials: "omit" }).then((r) => {
      if (!r.ok) throw new Error(`manifest ${r.status}`);
      return r.json() as Promise<Record<string, unknown>>;
    });
    loading = Promise.all([core, optional, manifest])
      .then(([, Physics, man]) => {
        if (!w.InkScout) throw new Error("InkScout missing");
        return { Ctor: w.InkScout, Physics, manifest: man };
      })
      .catch((e) => {
        loading = null; // cho phép thử lại ở lần mở sau
        throw e;
      });
  }
  return loading;
}

let presenceLoading: Promise<InkScoutPresenceCtor | null> | null = null;

/** `presence` chỉ nạp khi linh vật thật sự được tương tác (xem `AiCompanion`): vòng vẽ liên tục của nó không chạy ở trang thường. */
export function loadInkScoutPresence(): Promise<InkScoutPresenceCtor | null> {
  if (!presenceLoading) {
    const w = window as unknown as InkScoutWindow;
    presenceLoading = loadScript("ink-scout-presence.js")
      .then(() => w.InkScoutPresence ?? null)
      .catch(() => {
        presenceLoading = null;
        return null;
      });
  }
  return presenceLoading;
}

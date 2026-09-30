/**
 * Nạp LƯỜI runtime Ink Scout + manifest web — MỘT lần cho cả trang.
 *
 * Runtime là tệp `ink-scout.js` của bộ linh vật đã duyệt, GIỮ NGUYÊN từng byte
 * (`web/public/mascot/ink-scout/runtime/`, sha256 trong `SUBSET.json`) — nó là
 * một IIFE gắn `window.InkScout`, nên được nạp bằng thẻ `<script>` khi linh vật
 * thật sự cần hiện, không đi vào bundle JS của trang. Manifest là bản rút gọn do
 * `scripts/mascot/build_ink_scout_web.py` sinh (chỉ WebP, không PNG/Lottie).
 */
import type { RuntimeLike } from "./companionDirector";

export const INK_SCOUT_BASE = "/mascot/ink-scout/";
const SCRIPT_ID = "ink-scout-runtime";

export interface InkScoutRuntime extends RuntimeLike {
  setBounds(bounds: { left?: number; right?: number; top?: number; bottom?: number }): void;
  setSize(size: number): void;
  setPaused(value: boolean): void;
  host: HTMLElement;
  state: string;
  ready: Promise<boolean>;
}

export interface InkScoutCtor {
  new (host: HTMLElement, options: Record<string, unknown>): InkScoutRuntime;
}

interface Loaded {
  Ctor: InkScoutCtor;
  manifest: Record<string, unknown>;
}

let loading: Promise<Loaded> | null = null;

function loadScript(src: string): Promise<InkScoutCtor> {
  const w = window as unknown as { InkScout?: InkScoutCtor };
  if (w.InkScout) return Promise.resolve(w.InkScout);
  return new Promise((resolve, reject) => {
    let el = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (!el) {
      el = document.createElement("script");
      el.id = SCRIPT_ID;
      el.src = src;
      el.async = true;
      document.head.appendChild(el);
    }
    el.addEventListener("load", () => (w.InkScout ? resolve(w.InkScout) : reject(new Error("InkScout missing"))), { once: true });
    el.addEventListener("error", () => reject(new Error("Unable to load Ink Scout runtime")), { once: true });
  });
}

export function loadInkScout(): Promise<Loaded> {
  if (!loading) {
    loading = Promise.all([
      loadScript(`${INK_SCOUT_BASE}runtime/ink-scout.js`),
      fetch(`${INK_SCOUT_BASE}manifest.json`, { credentials: "omit" }).then((r) => {
        if (!r.ok) throw new Error(`manifest ${r.status}`);
        return r.json() as Promise<Record<string, unknown>>;
      }),
    ])
      .then(([Ctor, manifest]) => ({ Ctor, manifest }))
      .catch((e) => {
        loading = null; // cho phép thử lại ở lần mở sau
        throw e;
      });
  }
  return loading;
}

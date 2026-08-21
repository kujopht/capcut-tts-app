"use client";

/**
 * Nap YouTube IFrame API mot lan duy nhat, dung cho "Tiep tuc xem" (overnight
 * Phase 5, V6, Phan 5I) — doc vi tri/do dai TU CHINH iframe da nhung, khong
 * hoi lai YouTube qua backend (backend khong bao gio goi mang toi YouTube).
 *
 * CHI nap khi trang THAT SU can dieu khien mot iframe (sau khi nguoi dung da
 * bam Play tren `YouTubeFacadePlayer`) — khong nap san cho moi lan tai trang.
 */

export interface YTPlayerInstance {
  getCurrentTime(): number;
  getDuration(): number;
  destroy(): void;
}

interface YTPlayerOptions {
  events?: {
    onReady?: (event: { target: YTPlayerInstance }) => void;
    onStateChange?: (event: { data: number; target: YTPlayerInstance }) => void;
  };
}

interface YTNamespace {
  Player: new (elementId: string, options?: YTPlayerOptions) => YTPlayerInstance;
  PlayerState: { ENDED: number; PLAYING: number; PAUSED: number };
}

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let dangNap: Promise<YTNamespace> | null = null;

export function loadYouTubeIframeApi(): Promise<YTNamespace> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Không có window (server-side)."));
  }
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (dangNap) return dangNap;

  dangNap = new Promise((resolve) => {
    const truoc = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      truoc?.();
      resolve(window.YT as YTNamespace);
    };
    const the = document.createElement("script");
    the.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(the);
  });
  return dangNap;
}

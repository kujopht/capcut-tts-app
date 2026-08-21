"use client";

/**
 * Nap YouTube IFrame API mot lan duy nhat, dung cho "Tiep tuc xem" (overnight
 * Phase 5, V6, Phan 5I) — doc vi tri/do dai TU CHINH iframe da nhung, khong
 * hoi lai YouTube qua backend (backend khong bao gio goi mang toi YouTube).
 *
 * CHI nap khi trang THAT SU can dieu khien mot iframe (sau khi nguoi dung da
 * bam Play tren `YouTubeFacadePlayer`) — khong nap san cho moi lan tai trang.
 */

/**
 * Toan bo phuong thuc o day deu la API CHINH THUC, tai lieu tai
 * https://developers.google.com/youtube/iframe_api_reference — khong ham nao
 * tu bay them, dung dung nhu tai lieu mo ta (Phan Custom Fanfic Controls,
 * animation-player-v2-custom-controls). `isMuted()` dung de DOC trang thai
 * tat tieng THAT (khong doan tu volume === 0) — "khong gia trang thai phat".
 */
export interface YTPlayerInstance {
  playVideo(): void;
  pauseVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  getDuration(): number;
  getVolume(): number;
  setVolume(volume: number): void;
  mute(): void;
  unMute(): void;
  isMuted(): boolean;
  getPlayerState(): number;
  destroy(): void;
}

/** Gia tri THAT tu tai lieu YouTube IFrame API — dung de so sanh, khong
    dung so ma thuc (magic number) rai rac trong code. */
export const YT_PLAYER_STATE = {
  UNSTARTED: -1,
  ENDED: 0,
  PLAYING: 1,
  PAUSED: 2,
  BUFFERING: 3,
  CUED: 5,
} as const;

interface YTPlayerOptions {
  events?: {
    onReady?: (event: { target: YTPlayerInstance }) => void;
    onStateChange?: (event: { data: number; target: YTPlayerInstance }) => void;
    /**
     * Ma loi theo tai lieu YouTube IFrame API:
     * 2 = tham so (ID video) khong hop le; 5 = loi trinh phat HTML5;
     * 100 = video khong ton tai/da bi xoa/rieng tu; 101/150 = chu video
     * khong cho phep nhung o trang khac. Dung de hien thong bao tieng Viet
     * ro rang thay vi de nguoi xem nhin mot iframe trang/ket cung (Phan 3,
     * animation-youtube-polish-v1).
     */
    onError?: (event: { data: number }) => void;
  };
}

interface YTNamespace {
  Player: new (elementId: string, options?: YTPlayerOptions) => YTPlayerInstance;
  PlayerState: {
    UNSTARTED: number;
    ENDED: number;
    PLAYING: number;
    PAUSED: number;
    BUFFERING: number;
    CUED: number;
  };
}

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** Ma loi cua YouTube IFrame API -> thong bao tieng Viet ro rang (chuyen tu
    `animation/watch/[id]/page.tsx` sang day trong Phan Fanfic Cinema
    Controls, animation-player-v2-custom-controls — de `YouTubeFacadePlayer`
    dung chung, khong chi trang xem moi biet doc ma loi nay). Video da
    xoa/rieng tu/tat nhung deu la loi phia CHU video, khong phai loi cua
    Fanfic — khong doan them chi tiet ngoai tai lieu chinh thuc de tranh noi
    sai nguyen nhan. */
export function thongBaoLoiVideo(maLoi: number): string {
  switch (maLoi) {
    case 2:
      return "Đường dẫn video không hợp lệ.";
    case 5:
      return "Trình phát không hỗ trợ định dạng của video này.";
    case 100:
      return "Video này không còn tồn tại (có thể đã bị xoá hoặc đặt ở chế độ riêng tư).";
    case 101:
    case 150:
      return "Chủ video đã tắt tính năng phát trên trang khác cho video này.";
    default:
      return "Không thể phát video này lúc này.";
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

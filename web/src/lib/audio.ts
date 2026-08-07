/**
 * Lay URL phat duoc / tai duoc cho audio cua mot chuong.
 *
 * VI SAO PHUC TAP HON MOT DONG: da kiem chung tren trinh duyet that rang
 * khong the gan thang `/api/audio/{id}` vao `<audio src>` cho noi dung rieng
 * tu — the media khong gui duoc `Authorization`, con `fetch()` co header do
 * thi chet o buoc redirect sang R2 vi bucket khong mo CORS.
 *
 * Nen luong dung la: hoi backend URL (backend kiem quyen roi moi cap), sau do
 *   - che do R2   -> nhan URL ky, gan thang vao `<audio>` / `<a>`
 *   - che do cuc bo -> stream qua backend bang fetch kem token (cung origin
 *     nen khong vuong CORS), roi doi thanh blob URL
 */

import { API_BASE, ApiError, api, getToken } from "./api";

/**
 * Job vua bao `completed` khong co nghia la truy van tim thay `audio_track`
 * NGAY LAP TUC: backend tao track roi moi luu `completed`, nhung Appwrite doc
 * theo INDEX co the tre mot nhip. Da gap that: mo trinh phat ngay khi job xong
 * thi `/api/audio/{id}/url` tra 404.
 *
 * Nen thu lai vai lan khi gap 404 — chi 404, khong dung cho loi khac.
 */
const NOT_FOUND_RETRIES = 5;
const RETRY_DELAY_MS = 600;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function linkWithRetry(chapterId: string, download = false) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await api.audioLink(chapterId, download);
    } catch (cause) {
      const isMissing = cause instanceof ApiError && cause.status === 404;
      if (!isMissing || attempt >= NOT_FOUND_RETRIES) throw cause;
      await wait(RETRY_DELAY_MS);
    }
  }
}

export interface PlayableAudio {
  /** Gan vao `<audio src>`. */
  playUrl: string;
  /** Gan vao `<a href download>`. */
  downloadUrl: string;
  /** Blob URL can duoc thu hoi khi khong dung nua. */
  revoke: (() => void) | null;
  sizeBytes: number;
}

async function blobUrl(streamPath: string): Promise<string> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${streamPath}`, { headers });
  if (!response.ok) {
    throw new Error(`Không tải được audio (HTTP ${response.status}).`);
  }
  return URL.createObjectURL(await response.blob());
}

export async function resolveAudio(chapterId: string): Promise<PlayableAudio> {
  const link = await linkWithRetry(chapterId);

  if (link.url) {
    // Che do R2: URL da ky, dung truc tiep duoc o ca hai cho.
    const download = await linkWithRetry(chapterId, true);
    return {
      playUrl: link.url,
      downloadUrl: download.url ?? link.url,
      revoke: null,
      sizeBytes: link.size_bytes,
    };
  }

  // Che do kho cuc bo: khong co URL ky.
  const stream = link.stream_url ?? `/api/audio/${chapterId}`;
  const objectUrl = await blobUrl(stream);
  return {
    playUrl: objectUrl,
    downloadUrl: objectUrl,
    revoke: () => URL.revokeObjectURL(objectUrl),
    sizeBytes: link.size_bytes,
  };
}

/** Ten file goi y khi tai ve. */
export function audioFileName(title: string): string {
  const clean = title
    .normalize("NFD")
    // Bo dau tieng Viet bang thuoc tinh Unicode, khong go dai ky tu to hop
    // truc tiep vao source (de vo khi file bi doi bang ma).
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-zA-Z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .toLowerCase();
  return `${clean || "audio"}.mp3`;
}

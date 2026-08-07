/**
 * Lop goi backend.
 *
 * BAO MAT: trinh duyet CHI biet URL cua backend. Moi bi mat (Appwrite API key,
 * R2 access key) nam o server va khong bao gio duoc gui xuong day.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const TOKEN_KEY = "fas.token";

export type Tier = "free" | "listener_pro" | "creator_pro" | "ultra";
export type PublishState = "draft" | "published" | "archived";
export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface Profile {
  user_id: string;
  email: string;
  display_name: string;
  tier: Tier;
  listened_minutes: number;
  tts_characters_used: number;
  created_at: string;
}

export interface Novel {
  novel_id: string;
  owner_id: string;
  title: string;
  description: string;
  cover_key: string | null;
  state: PublishState;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Chapter {
  chapter_id: string;
  novel_id: string;
  owner_id: string;
  title: string;
  order_index: number;
  state: PublishState;
  char_count: number;
  content?: string;
  created_at: string;
  updated_at: string;
}

export interface Voice {
  voice_id: string;
  provider: string;
  provider_label: string;
  display_name: string;
  description: string;
  language: string;
  gender: string;
  installed: boolean;
  status: string;
  status_label: string;
  status_reason: string;
  /** Giong chay cuc bo chua xac minh giay phep -> false. */
  commercial_ready: boolean;
}

export interface TtsJob {
  job_id: string;
  owner_id: string;
  chapter_id: string;
  voice_id: string;
  content_hash: string;
  status: JobStatus;
  progress: number;
  total_parts: number;
  done_parts: number;
  output_key: string | null;
  error_kind: string | null;
  error_message: string;
  rate: string;
  chunk_chars: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AudioTrack {
  track_id: string;
  chapter_id: string;
  object_key: string;
  size_bytes: number;
  created_at: string;
}

/** Loi API kem thong bao tieng Viet de hien thi thang cho nguoi dung. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      "Không kết nối được máy chủ. Hãy kiểm tra backend đã chạy chưa.",
      0,
    );
  }

  if (!response.ok) {
    let message = `Máy chủ trả về lỗi ${response.status}.`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* giu thong bao mac dinh */
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Record<string, unknown>>("/api/health"),

  register: (email: string, password: string, displayName = "") =>
    request<{ token: string; profile: Profile }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName }),
    }),

  login: (email: string, password: string) =>
    request<{ token: string; profile: Profile }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<{ profile: Profile }>("/api/auth/me"),

  voices: () => request<{ voices: Voice[]; count: number }>("/api/voices"),

  listNovels: (mine = false) =>
    request<{ novels: Novel[]; count: number }>(
      `/api/novels${mine ? "?mine=true" : ""}`,
    ),

  createNovel: (title: string, description: string, tags: string[] = []) =>
    request<{ novel: Novel }>("/api/novels", {
      method: "POST",
      body: JSON.stringify({ title, description, tags }),
    }),

  getNovel: (novelId: string) =>
    request<{ novel: Novel; chapters: Chapter[] }>(`/api/novels/${novelId}`),

  publishNovel: (novelId: string) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}/publish`, {
      method: "POST",
    }),

  createChapter: (
    novelId: string,
    title: string,
    content: string,
    orderIndex = 1,
  ) =>
    request<{ chapter: Chapter }>("/api/chapters", {
      method: "POST",
      body: JSON.stringify({
        novel_id: novelId,
        title,
        content,
        order_index: orderIndex,
      }),
    }),

  getChapter: (chapterId: string) =>
    request<{ chapter: Chapter; audio: AudioTrack | null }>(
      `/api/chapters/${chapterId}`,
    ),

  createJob: (chapterId: string, voiceId: string, rate = "1.0") =>
    request<{ job: TtsJob; reused: boolean }>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        chapter_id: chapterId,
        voice_id: voiceId,
        rate,
      }),
    }),

  getJob: (jobId: string) => request<{ job: TtsJob }>(`/api/jobs/${jobId}`),

  listJobs: (chapterId?: string) =>
    request<{ jobs: TtsJob[]; count: number }>(
      `/api/jobs${chapterId ? `?chapter_id=${chapterId}` : ""}`,
    ),

  audioUrl: (chapterId: string) => `${API_BASE}/api/audio/${chapterId}`,

  /**
   * Xin URL phat duoc cho mot chuong, SAU KHI backend kiem tra quyen.
   *
   * The `<audio src>` khong gui duoc header `Authorization`, con `fetch()`
   * co header do thi chet o buoc redirect sang R2 vi bucket khong mo CORS.
   * Nen phai lay URL ky duoi dang JSON roi tu gan vao `<audio>` / `<a>`.
   */
  audioLink: (chapterId: string, download = false) =>
    request<AudioLink>(
      `/api/audio/${chapterId}/url${download ? "?download=true" : ""}`,
    ),
};

export interface AudioLink {
  /** URL ky san (che do R2). Gan thang vao `<audio src>` hoac `<a href>`. */
  url: string | null;
  /** Che do kho cuc bo: phai stream qua backend kem token. */
  stream_url: string | null;
  expires_in: number | null;
  size_bytes: number;
}

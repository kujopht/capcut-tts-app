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
  /** Tên công khai, dạng chuẩn. Chuỗi rỗng = chưa chọn. */
  username: string;
  bio: string;
  author_status: AuthorStatus;
}

/**
 * Được phép **xuất bản công khai** hay không. Đây là moderation, KHÔNG phải uy
 * tín — xem `docs/AUTHOR_RANK.md`.
 *
 * Giá trị này chỉ có ở hồ sơ **của chính mình**. Hồ sơ công khai của người khác
 * chỉ lộ đúng một bit: `is_author`.
 */
export type AuthorStatus =
  | "none"
  | "pending"
  | "approved"
  | "rejected"
  | "suspended";

/** Một bậc hạng. Ngưỡng do máy chủ cấp — KHÔNG nhúng vào frontend. */
export interface RankTier {
  key: string;
  title: string;
  min_listens: number;
  level: number;
}

/** Hạng hiện tại + chặng đường tới hạng sau. Máy chủ tính. */
export interface RankProgress {
  key: string;
  title: string;
  level: number;
  qualified_listens: number;
  next_key: string | null;
  next_title: string | null;
  next_at: number | null;
  remaining: number;
  percent: number;
}

export interface AuthorApplication {
  pen_name: string;
  bio: string;
  genres: string[];
  intro: string;
  accepted_rules: boolean;
  status: AuthorStatus;
  reviewer_note: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
}

/** Trạng thái khu Creator của chính mình, trong MỘT lần gọi. */
export interface CreatorState {
  author_status: AuthorStatus;
  can_publish: boolean;
  can_apply: boolean;
  apply_blocked_reason: string;
  username: string;
  bio: string;
  application: AuthorApplication | null;
  rank?: RankProgress;
  qualified_listens?: number;
  published_novels?: number;
  /** Chỉ có khi chưa chọn username. Là GỢI Ý, không phải tên được gán. */
  username_suggestion?: string;
}

/**
 * Hồ sơ **công khai** của một người.
 *
 * Danh sách cho phép ở backend (`creator.public_profile`) quyết định có gì ở
 * đây. Không bao giờ có email, tier, quota, hay trạng thái duyệt.
 */
export interface PublicProfile {
  user_id: string;
  username: string;
  display_name: string;
  bio?: string;
  is_author: boolean;
  rank?: RankProgress;
  published_novels?: number;
  novels?: Novel[];
  /**
   * Số liệu xã hội, ghép sẵn vào cùng một lần gọi.
   *
   * Tuỳ chọn để một client cũ (chưa biết trường này) vẫn biên dịch được — cùng
   * lý do với `Novel.cover_url`.
   */
  social?: ProfileSocial;
}

export interface Novel {
  novel_id: string;
  owner_id: string;
  title: string;
  description: string;
  cover_key: string | null;
  /**
   * URL xem duoc cua anh bia, do backend cap (trinh duyet khong co credential
   * cua kho nen khong tu dung tu `cover_key` duoc). `null` khi truyen chua co
   * bia — luc do giao dien dung anh du phong.
   *
   * Tuy chon de client cu (chua biet truong nay) van bien dich duoc.
   */
  cover_url?: string | null;
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
  /**
   * Chuong da co ban audio chua. Backend tra san trong danh sach chuong cua
   * `getNovel`, nen trang chi tiet khong phai hoi tung chuong mot nua.
   *
   * Tuy chon vi cac route khac (vi du `createChapter`) khong kem truong nay.
   * Thieu thi coi nhu chua co audio.
   */
  has_audio?: boolean;
  /**
   * Chuong da duoc sua SAU KHI tao audio, nen audio CO THE khong con khop noi
   * dung. La canh bao, khong phai bang chung: sua rieng tieu de cung lam co nay
   * bat len. Khong bao gio duoc dung lam ly do de xoa file audio.
   *
   * Tuy chon de client cu van bien dich duoc.
   */
  audio_outdated?: boolean;
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
  /**
   * Giong nay dang duoc phuc vu nguoi dung hay khong.
   *
   * Thay cho `commercial_ready` truoc day. Ten cu la mot phan doan ve GIAY
   * PHEP — thu ma may chu khong biet va khong nen doan. Day la mot su that ky
   * thuat: no den tu danh sach trang o `server/tts_bridge.py`.
   */
  public_enabled: boolean;
  /**
   * Model nam tren may worker, khong nam trong tien trinh API.
   *
   * Voi giong nay, `installed` cua API KHONG noi len dieu gi: Render khong co
   * file `.onnx` nao nen no luon false. Dung co nay de quyet dinh hien thi.
   */
  runs_on_worker: boolean;
  /** Thuoc muc "Giong de xuat" (danh sach do chu du an chon trong app desktop). */
  recommended: boolean;
  /**
   * Thu tu trong muc de xuat, tinh tu 0. `null` khi khong thuoc muc do.
   *
   * Do MAY CHU cap, lay tu `desktop_app/providers/recommended.py`. Frontend
   * khong duoc tu sap xep lai.
   */
  recommended_order: number | null;
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

  // ---------------------------------------------------------------- tác giả

  creatorMe: () => request<CreatorState>("/api/creator/me"),

  /** Bảng hạng. KHÔNG cần đăng nhập — giao diện vẽ thang bậc trước cả khi biết
      người dùng là ai. Ngưỡng là chính sách và nó sẽ đổi; một bản frontend cũ
      đang chạy trong tab của ai đó không được vẽ một hạng khác với hạng máy chủ
      công nhận. */
  ranks: () => request<{ tiers: RankTier[] }>("/api/creator/ranks"),

  setUsername: (username: string) =>
    request<{ profile: Profile }>("/api/creator/username", {
      method: "PUT",
      body: JSON.stringify({ username }),
    }),

  setBio: (bio: string) =>
    request<{ profile: Profile }>("/api/creator/bio", {
      method: "PUT",
      body: JSON.stringify({ bio }),
    }),

  applyAuthor: (payload: {
    pen_name: string;
    bio?: string;
    genres?: string[];
    intro: string;
    accepted_rules: boolean;
  }) =>
    request<{ application: AuthorApplication; author_status: AuthorStatus }>(
      "/api/creator/apply",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  publicProfile: (username: string) =>
    request<{ profile: PublicProfile }>(
      `/api/users/${encodeURIComponent(username)}`,
    ),

  /**
   * Tìm người ở **máy chủ**.
   *
   * Tải hết người dùng về rồi lọc ở trình duyệt là vừa chậm vừa là một cách tải
   * cả danh bạ người dùng về máy khách.
   */
  searchPeople: (q: string, kind: "users" | "authors" = "users",
                 limit = 8, offset = 0) =>
    request<{ people: PublicProfile[]; total: number; limit: number; offset: number }>(
      `/api/search/people?q=${encodeURIComponent(q)}&kind=${kind}` +
      `&limit=${limit}&offset=${offset}`,
    ),

  /**
   * Báo một lần nghe. Máy chủ là nguồn sự thật cho uy tín tác giả.
   *
   * KHÔNG bắt buộc đăng nhập: khách ẩn danh vẫn gọi được và nhận lại
   * `credited: false`. Không bao giờ trả về số lượt nghe của tác giả.
   */
  reportListen: (chapterId: string, listenedSeconds: number) =>
    request<{ credited: boolean; reason: string }>("/api/listens", {
      method: "POST",
      body: JSON.stringify({
        chapter_id: chapterId,
        listened_seconds: Math.max(0, Math.round(listenedSeconds)),
      }),
    }),

  /**
   * Kết thúc phiên ở phía máy chủ.
   *
   * Xoá token trong localStorage thôi là chưa đủ: session secret vẫn sống ở
   * Appwrite, và ai nhặt được nó vẫn dùng tiếp được.
   */
  logout: () =>
    request<{ da_huy_phien: boolean }>("/api/auth/logout", { method: "POST" }),

  /**
   * Dia chi bat dau dang nhap bang Google/Facebook.
   *
   * Tra ve CHUOI chu khong phai Promise, va do la chu y: buoc nay phai la mot
   * lan DIEU HUONG cua trinh duyet (`window.location.href = ...`), khong phai
   * `fetch`. Sau no la mot chuoi chuyen tiep qua Appwrite roi qua nha cung
   * cap, va chuoi do phai xay ra trong thanh dia chi cua nguoi dung.
   */
  oauthStartUrl: (provider: "google" | "facebook", next: string) =>
    `${API_BASE}/api/auth/oauth/${provider}?next=${encodeURIComponent(next)}`,

  /**
   * Doi cap dung-mot-lan tu URL callback lay token cua ung dung.
   *
   * Tra ve DUNG hinh dang ma `login`/`register` tra ve. Khong co he thong
   * phien thu hai: sau buoc nay, nguoi dung Google khong khac nguoi dung mat
   * khau.
   */
  exchangeOAuth: (userId: string, secret: string) =>
    request<{ token: string; profile: Profile }>("/api/auth/oauth/exchange", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, secret }),
    }),

  voices: () => request<{ voices: Voice[]; count: number }>("/api/voices"),

  listNovels: (mine = false) =>
    request<{ novels: Novel[]; count: number }>(
      `/api/novels${mine ? "?mine=true" : ""}`,
    ),

  /**
   * Trang kham pha: tim kiem, loc the va phan trang do BACKEND lam.
   *
   * `listNovels` o tren giu nguyen — khong truyen `limit` thi backend tra ve het
   * y nhu truoc, nen trang tac gia va `ensureStudioNovel` khong doi gi.
   */
  browseNovels: (opts: {
    query?: string;
    tag?: string;
    limit: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts.query?.trim()) params.set("q", opts.query.trim());
    if (opts.tag) params.set("tag", opts.tag);
    params.set("limit", String(opts.limit));
    params.set("offset", String(opts.offset ?? 0));
    return request<NovelPage>(`/api/novels?${params.toString()}`);
  },

  /** Cac the dang co, de dung bo loc ma khong phai tai het truyen ve. */
  novelTags: () =>
    request<{ tags: string[]; count: number }>("/api/novels/tags"),

  /**
   * MOI chuong cua chinh minh, trong MOT request.
   *
   * Thu vien audio can mot bang tra "chapter_id -> ten chuong". Truoc day no goi
   * `getNovel` cho TUNG truyen de dung bang do — nguoi co 40 truyen ton 42
   * request. Duong nay khong kem noi dung chuong va khong ky URL audio nao.
   */
  myChapters: () =>
    request<{ chapters: Chapter[]; count: number }>("/api/chapters?mine=true"),

  createNovel: (title: string, description: string, tags: string[] = []) =>
    request<{ novel: Novel }>("/api/novels", {
      method: "POST",
      body: JSON.stringify({ title, description, tags }),
    }),

  getNovel: (novelId: string) =>
    request<{
      novel: Novel;
      chapters: Chapter[];
      /** Trạng thái theo dõi, ghép sẵn. Vắng mặt với bản nháp — bản nháp không
          theo dõi được. Tuỳ chọn để client cũ vẫn biên dịch. */
      follow?: FollowState;
    }>(`/api/novels/${novelId}`),

  publishNovel: (novelId: string) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}/publish`, {
      method: "POST",
    }),

  unpublishNovel: (novelId: string) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}/unpublish`, {
      method: "POST",
    }),

  /** Sua truyen. Chi gui truong can doi; `state` khong doi duoc qua day. */
  updateNovel: (
    novelId: string,
    fields: { title?: string; description?: string; tags?: string[] },
  ) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),

  /** Xoa truyen cung moi chuong, job, audio_track va object cua no. */
  deleteNovel: (novelId: string) =>
    request<{ deleted: boolean; removed: RemovedCounts }>(
      `/api/novels/${novelId}`,
      { method: "DELETE" },
    ),

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

  updateChapter: (
    chapterId: string,
    fields: { title?: string; content?: string; order_index?: number },
  ) =>
    request<{ chapter: Chapter }>(`/api/chapters/${chapterId}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),

  /** Xoa chuong cung job, audio_track va object cua no. */
  deleteChapter: (chapterId: string) =>
    request<{ deleted: boolean; removed: RemovedCounts }>(
      `/api/chapters/${chapterId}`,
      { method: "DELETE" },
    ),

  getChapter: (chapterId: string) =>
    request<{
      chapter: Chapter;
      audio: AudioTrack | null;
      /** Truyen cha, kem san de luong nghe co bia ma khong phai goi them. */
      novel?: NovelBrief | null;
      /** Chuong sua sau khi tao audio -> audio co the khong con khop. */
      audio_outdated?: boolean;
    }>(`/api/chapters/${chapterId}`),

  /**
   * Dat lai thu tu chuong bang MOT request.
   *
   * Gui CA danh sach id theo thu tu moi. Neu goi `updateChapter` cho tung chuong
   * thi doi thu tu n chuong se thanh n request — dung cai N+1 da bo di o trang
   * chi tiet truyen. Danh sach phai gom dung cac chuong cua truyen, khong thieu
   * khong thua; lech mot cai thi backend tra 400 va khong ghi gi ca.
   */
  reorderChapters: (novelId: string, chapterIds: string[]) =>
    request<{ chapters: Chapter[] }>(`/api/novels/${novelId}/chapters/order`, {
      method: "POST",
      body: JSON.stringify({ chapter_ids: chapterIds }),
    }),

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

  /**
   * Job dang ke nhat cua MOT chuong — de tim lai sau khi tai lai trang.
   *
   * Dung khi chi quan tam mot chuong. Khoi phuc CA trang thi dung `listJobs()`
   * (mot request cho tat ca): goi ham nay trong vong lap la N+1, va
   * `tests/correctness-scale.test.mjs` khoa lai chinh cho do.
   */
  latestJobForChapter: (chapterId: string) =>
    request<{ job: TtsJob | null }>(
      `/api/chapters/${chapterId}/jobs/latest`,
    ),

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

/** Mot trang trong danh sach truyen. */
export interface NovelPage {
  novels: Novel[];
  /** So truyen TRONG trang nay. */
  count: number;
  /** Tong so truyen khop dieu kien — de biet con trang sau hay khong. */
  total: number;
  limit: number | null;
  offset: number;
  has_more: boolean;
}

/** Phan truyen kem theo chuong: vua du de hien bia va ten. */
export interface NovelBrief {
  novel_id: string;
  title: string;
  state: PublishState;
  cover_key: string | null;
  cover_url: string | null;
}

/** So luong da xoa, backend tra ve de doi soat. */
export interface RemovedCounts {
  chapters?: number;
  tracks: number;
  jobs: number;
  objects: number;
}

export interface AudioLink {
  /** URL ky san (che do R2). Gan thang vao `<audio src>` hoac `<a href>`. */
  url: string | null;
  /** Che do kho cuc bo: phai stream qua backend kem token. */
  stream_url: string | null;
  expires_in: number | null;
  size_bytes: number;
}

// ---------------------------------------------------------------- quản trị
//
// Mọi thứ dưới đây yêu cầu quyền quản trị **ở máy chủ**. Giao diện không bao giờ
// là nơi quyết định: người dùng thường gọi các hàm này sẽ nhận 403 và một thân
// rỗng. Xem `server/main.py` mục QUAN TRI.

export interface AdminOverview {
  pending_applications: number;
  approved_authors: number;
  rejected_applications: number;
  suspended_authors: number;
  published_novels: number;
  users_with_username: number;
  qualified_listens: number;
}

/** Danh tính kèm theo đơn / hàng tác giả. CÓ `email` — đây là đường quản trị. */
export interface AdminUser {
  user_id: string;
  email: string;
  display_name: string;
  username: string;
  author_status: AuthorStatus;
  created_at: string;
  qualified_listens: number;
  published_novels?: number;
  rank?: RankProgress;
  bio?: string;
  application?: AdminApplication | null;
  events?: ModerationEvent[];
  novels?: Novel[];
}

export interface AdminApplication {
  application_id: string;
  user_id: string;
  pen_name: string;
  bio: string;
  genres: string[];
  intro: string;
  accepted_rules: boolean;
  status: AuthorStatus;
  reviewer_note: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  user?: AdminUser | null;
}

export interface ModerationEvent {
  event_id: string;
  action:
    | "author_approved"
    | "author_rejected"
    | "author_suspended"
    | "author_restored";
  target_user_id: string;
  actor_id: string;
  note: string;
  created_at: string;
}

export interface AdminNovel extends Novel {
  chapters: number;
  owner: { display_name: string; username: string } | null;
}

export const adminApi = {
  overview: () => request<AdminOverview>("/api/admin/overview"),

  applications: (status = "", limit = 25, offset = 0) =>
    request<{ applications: AdminApplication[]; total: number }>(
      `/api/admin/author-applications?status_filter=${status}` +
        `&limit=${limit}&offset=${offset}`,
    ),

  application: (userId: string) =>
    request<{ application: AdminApplication }>(
      `/api/admin/author-applications/${encodeURIComponent(userId)}`,
    ),

  approve: (userId: string, note = "") =>
    request<{ application: AdminApplication }>(
      `/api/admin/author-applications/${encodeURIComponent(userId)}/approve`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  reject: (userId: string, note: string) =>
    request<{ application: AdminApplication }>(
      `/api/admin/author-applications/${encodeURIComponent(userId)}/reject`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  authors: (limit = 25, offset = 0) =>
    request<{ authors: AdminUser[]; total: number }>(
      `/api/admin/authors?limit=${limit}&offset=${offset}`,
    ),

  suspend: (userId: string, note: string) =>
    request<{ application: AdminApplication }>(
      `/api/admin/authors/${encodeURIComponent(userId)}/suspend`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  restore: (userId: string, note = "") =>
    request<{ application: AdminApplication }>(
      `/api/admin/authors/${encodeURIComponent(userId)}/restore`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  users: (q = "", limit = 25, offset = 0) =>
    request<{ users: AdminUser[]; total: number }>(
      `/api/admin/users?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`,
    ),

  user: (userId: string) =>
    request<{ user: AdminUser }>(`/api/admin/users/${encodeURIComponent(userId)}`),

  novels: (q = "", state = "", limit = 25, offset = 0) =>
    request<{ novels: AdminNovel[]; total: number }>(
      `/api/admin/novels?q=${encodeURIComponent(q)}&state=${state}` +
        `&limit=${limit}&offset=${offset}`,
    ),

  events: (limit = 50) =>
    request<{ events: ModerationEvent[]; total: number }>(
      `/api/admin/events?limit=${limit}`,
    ),
};

// ---------------------------------------------------------------------------
// Tầng xã hội
// ---------------------------------------------------------------------------
//
// MỌI kiểu ở đây khớp với `to_public_dict()` của `server/domain.py`, không phải
// với `to_dict()`. Khác biệt đó là chủ ý và nó có ý nghĩa bảo mật: bản công khai
// là một **danh sách cho phép**, nên `removed_by`, `removed_reason` và
// `image_key` không bao giờ xuống tới trình duyệt.

/** Thẻ tác giả gọn — cùng hình dạng với kết quả tìm kiếm. */
export interface AuthorCard {
  user_id: string;
  username: string;
  display_name: string;
  is_author: boolean;
  rank?: RankProgress;
  published_novels?: number;
}

export type PostKind = "post" | "story_update";
export type ContentState = "visible" | "removed";

export interface Post {
  post_id: string;
  author_user_id: string;
  kind: PostKind;
  novel_id: string;
  text: string;
  /** `has_image`, KHÔNG phải `image_key`: khóa đối tượng thô không bao giờ ra
      khỏi backend — nó không dùng trực tiếp được (kho là riêng tư) và nó lộ cấu
      trúc không gian tên. */
  has_image: boolean;
  image_width: number;
  image_height: number;
  /** URL đã ký, ngắn hạn. Vắng mặt khi bài không có ảnh. */
  image_url?: string;
  state: ContentState;
  like_count: number;
  comment_count: number;
  created_at: string;
  updated_at: string;
  author?: AuthorCard;
  /** Người đang xem đã thích chưa. `false` với khách vãng lai. */
  liked: boolean;
  /** Người đang xem có sửa được không. MÁY CHỦ vẫn là nơi cưỡng chế — cờ này
      chỉ để giao diện khỏi hiện một cái nút chắc chắn sẽ trả 403. */
  can_edit: boolean;
  /** Chỉ có với `story_update`. */
  novel?: { novel_id: string; title: string; cover_key: string | null };
}

export interface Comment {
  comment_id: string;
  post_id: string;
  /** Chuỗi rỗng khi bình luận đã bị gỡ — xem `Comment.to_public_dict`. */
  author_user_id: string;
  parent_id: string;
  text: string;
  state: ContentState;
  reply_count: number;
  created_at: string;
  updated_at: string;
  author?: AuthorCard;
  replies?: Comment[];
}

export type NotificationKind =
  | "follow"
  | "post_like"
  | "post_comment"
  | "comment_reply"
  | "story_chapter"
  | "author_approved"
  | "author_rejected";

export interface Notification {
  notification_id: string;
  kind: NotificationKind;
  actor_id: string;
  subject_id: string;
  subject_kind: string;
  preview: string;
  read: boolean;
  created_at: string;
  actor?: AuthorCard;
}

export type ReportReason =
  | "spam"
  | "harassment"
  | "inappropriate"
  | "copyright"
  | "other";

export interface FollowState {
  following: boolean;
  follower_count: number;
}

export interface LikeState {
  liked: boolean;
  like_count: number;
}

export interface FeedPage {
  items: Post[];
  total: number;
  limit: number;
  offset: number;
  /** Bài của người mình theo dõi có được ưu tiên hay không. `false` = đang xem
      bảng tin khám phá vì chưa theo dõi ai. */
  personalized: boolean;
  /** Danh sách người theo dõi đã bị cắt vì vượt trần truy vấn. Giao diện NÓI RÕ
      điều này thay vì im lặng bỏ bớt. */
  following_truncated: boolean;
}

export interface CommentPage {
  items: Comment[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotificationPage {
  items: Notification[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
}

/** Tóm tắt xã hội của chính mình, cho `/account`. */
export interface AccountSocial {
  follower_count: number;
  following_count: number;
  post_count: number;
  followed_stories: number;
  unread_notifications: number;
  /** Chỉ tác giả ĐÃ DUYỆT mới có ba trường dưới đây. */
  rank?: RankProgress;
  qualified_listens?: number;
  published_novels?: number;
}

/** Phần xã hội của một trang cá nhân. */
export interface ProfileSocial {
  follower_count: number;
  following_count: number;
  post_count: number;
  following: boolean;
  is_self: boolean;
}

/** Giới hạn do MÁY CHỦ quyết định. Xem `src/lib/limits.ts`. */
export interface ServerLimits {
  max_chapter_chars: number;
  max_active_jobs: number;
  post_max_chars: number;
  comment_max_chars: number;
  report_detail_max_chars: number;
  post_max_images: number;
  image: Record<
    string,
    {
      max_bytes: number;
      max_edge: number;
      mime: string[];
      preferred_mime: string[];
    }
  >;
  rate: Record<string, { count: number; minutes: number }>;
}

export const social = {
  limits: () => request<ServerLimits>("/api/limits"),

  // -- theo dõi -------------------------------------------------------------

  followUser: (userId: string) =>
    request<FollowState>(`/api/users/${encodeURIComponent(userId)}/follow`, {
      method: "POST",
      body: "{}",
    }),

  unfollowUser: (userId: string) =>
    request<FollowState>(`/api/users/${encodeURIComponent(userId)}/follow`, {
      method: "DELETE",
    }),

  followStory: (novelId: string) =>
    request<FollowState>(`/api/novels/${encodeURIComponent(novelId)}/follow`, {
      method: "POST",
      body: "{}",
    }),

  unfollowStory: (novelId: string) =>
    request<FollowState>(`/api/novels/${encodeURIComponent(novelId)}/follow`, {
      method: "DELETE",
    }),

  // -- bảng tin và bài đăng -------------------------------------------------

  feed: (limit = 20, offset = 0) =>
    request<FeedPage>(`/api/feed?limit=${limit}&offset=${offset}`),

  userPosts: (userId: string, limit = 20, offset = 0) =>
    request<FeedPage>(
      `/api/users/${encodeURIComponent(userId)}/posts` +
        `?limit=${limit}&offset=${offset}`,
    ),

  post: (postId: string) =>
    request<{ post: Post }>(`/api/posts/${encodeURIComponent(postId)}`),

  createPost: (payload: {
    text: string;
    kind?: PostKind;
    novel_id?: string;
    image_base64?: string;
    image_mime?: string;
    image_width?: number;
    image_height?: number;
  }) =>
    request<{ post: Post }>("/api/posts", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  editPost: (postId: string, text: string) =>
    request<{ post: Post }>(`/api/posts/${encodeURIComponent(postId)}`, {
      method: "PATCH",
      body: JSON.stringify({ text }),
    }),

  deletePost: (postId: string) =>
    request<{ deleted: boolean }>(`/api/posts/${encodeURIComponent(postId)}`, {
      method: "DELETE",
    }),

  // -- thích ----------------------------------------------------------------

  like: (postId: string) =>
    request<LikeState>(`/api/posts/${encodeURIComponent(postId)}/like`, {
      method: "POST",
      body: "{}",
    }),

  unlike: (postId: string) =>
    request<LikeState>(`/api/posts/${encodeURIComponent(postId)}/like`, {
      method: "DELETE",
    }),

  // -- bình luận ------------------------------------------------------------

  comments: (postId: string, limit = 20, offset = 0) =>
    request<CommentPage>(
      `/api/posts/${encodeURIComponent(postId)}/comments` +
        `?limit=${limit}&offset=${offset}`,
    ),

  createComment: (postId: string, text: string, parentId = "") =>
    request<{ comment: Comment }>(
      `/api/posts/${encodeURIComponent(postId)}/comments`,
      { method: "POST", body: JSON.stringify({ text, parent_id: parentId }) },
    ),

  replies: (commentId: string, limit = 20, offset = 0) =>
    request<CommentPage>(
      `/api/comments/${encodeURIComponent(commentId)}/replies` +
        `?limit=${limit}&offset=${offset}`,
    ),

  editComment: (commentId: string, text: string) =>
    request<{ comment: Comment }>(
      `/api/comments/${encodeURIComponent(commentId)}`,
      { method: "PATCH", body: JSON.stringify({ text }) },
    ),

  deleteComment: (commentId: string) =>
    request<{ deleted: boolean }>(
      `/api/comments/${encodeURIComponent(commentId)}`,
      { method: "DELETE" },
    ),

  // -- thông báo ------------------------------------------------------------

  notifications: (unread = false, limit = 20, offset = 0) =>
    request<NotificationPage>(
      `/api/notifications?unread=${unread}&limit=${limit}&offset=${offset}`,
    ),

  /** Chỉ con số, cho cái chuông. Nhẹ hơn danh sách — nó chạy ở mọi trang. */
  unreadCount: () => request<{ unread: number }>("/api/notifications/unread"),

  markRead: (notificationId: string) =>
    request<{ unread: number }>(
      `/api/notifications/${encodeURIComponent(notificationId)}/read`,
      { method: "POST", body: "{}" },
    ),

  markAllRead: () =>
    request<{ marked: number; unread: number }>(
      "/api/notifications/read-all",
      { method: "POST", body: "{}" },
    ),

  // -- báo cáo --------------------------------------------------------------

  report: (payload: {
    target_kind: "post" | "comment";
    target_id: string;
    reason: ReportReason;
    detail?: string;
  }) =>
    request<{ reported: boolean; created: boolean }>("/api/reports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // -- tìm kiếm ---------------------------------------------------------------

  /** Mục PHỤ của tìm kiếm toàn cục — truyện và người vẫn là ưu tiên. */
  searchPosts: (q: string, limit = 3) =>
    request<{ items: Post[]; total: number }>(
      `/api/search/posts?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  // -- của chính mình -------------------------------------------------------

  accountSocial: () => request<AccountSocial>("/api/account/social"),
};

// ---------------------------------------------------------------------------
// Kiểm duyệt xã hội (quản trị)
// ---------------------------------------------------------------------------
//
// Các kiểu ở đây khớp với `to_dict()` — bản QUẢN TRỊ, có `state`, `removed_by`
// và ghi chú nội bộ. Đó là cả mục đích của những màn hình này.

export type ReportStatus = "open" | "resolved" | "dismissed";

/** Bản quản trị của một bài — có thêm trường kiểm duyệt. */
export interface AdminPost extends Omit<Post, "liked" | "can_edit" | "has_image"> {
  image_key: string;
  image_mime: string;
  image_bytes: number;
  removed_by: string;
  removed_reason: string;
  open_reports: number;
}

export interface AdminComment extends Omit<Comment, "replies"> {
  removed_by: string;
  removed_reason: string;
  open_reports: number;
}

export interface ContentReport {
  report_id: string;
  reporter_id: string;
  target_kind: "post" | "comment";
  target_id: string;
  target_owner_id: string;
  reason: ReportReason;
  detail: string;
  status: ReportStatus;
  /** Ghi chú NỘI BỘ. Chỉ ra ở đường quản trị. */
  resolution_note: string;
  resolved_by: string;
  created_at: string;
  updated_at: string;
  /** Nội dung bị báo cáo, ghép sẵn để màn hình này không phải gọi thêm. `null`
      khi nội dung đã bị chính chủ xoá thật. */
  content: (AdminPost & AdminComment) | null;
  reporter?: AuthorCard;
  target_owner?: AuthorCard;
}

export interface SocialOverview {
  open_reports: number;
  total_reports: number;
  total_posts: number;
  removed_posts: number;
}

export const adminSocial = {
  overview: () => request<SocialOverview>("/api/admin/social/overview"),

  reports: (status = "open", targetKind = "", limit = 25, offset = 0) =>
    request<{
      items: ContentReport[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/api/admin/reports?status_filter=${encodeURIComponent(status)}` +
        `&target_kind=${encodeURIComponent(targetKind)}` +
        `&limit=${limit}&offset=${offset}`,
    ),

  resolveReport: (reportId: string, dismiss: boolean, note = "") =>
    request<{ report: ContentReport }>(
      `/api/admin/reports/${encodeURIComponent(reportId)}/resolve`,
      { method: "POST", body: JSON.stringify({ dismiss, note }) },
    ),

  posts: (q = "", limit = 25, offset = 0) =>
    request<{
      items: AdminPost[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/api/admin/posts?q=${encodeURIComponent(q)}` +
        `&limit=${limit}&offset=${offset}`,
    ),

  /** GỠ, không xoá. Hàng vẫn còn — xem `domain.ContentState`. */
  removePost: (postId: string, reason: string) =>
    request<{ post: AdminPost }>(
      `/api/admin/posts/${encodeURIComponent(postId)}/remove`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),

  restorePost: (postId: string) =>
    request<{ post: AdminPost }>(
      `/api/admin/posts/${encodeURIComponent(postId)}/restore`,
      { method: "POST", body: "{}" },
    ),

  postComments: (postId: string, limit = 50, offset = 0) =>
    request<{
      items: AdminComment[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/api/admin/posts/${encodeURIComponent(postId)}/comments` +
        `?limit=${limit}&offset=${offset}`,
    ),

  removeComment: (commentId: string, reason: string) =>
    request<{ comment: AdminComment }>(
      `/api/admin/comments/${encodeURIComponent(commentId)}/remove`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),

  restoreComment: (commentId: string) =>
    request<{ comment: AdminComment }>(
      `/api/admin/comments/${encodeURIComponent(commentId)}/restore`,
      { method: "POST", body: "{}" },
    ),
};

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
/** Admin Control Center V2 — ba mức, xem `docs/ADMIN.md`. */
export type AdminRole = "none" | "moderator" | "admin" | "owner";

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
  /**
   * Người này có phải quản trị không — do MÁY CHỦ trả lời (từ
   * `FAS_ADMIN_USER_IDS`), chỉ có ở hồ sơ của chính mình. Frontend không bao
   * giờ tự suy từ email/username: bit này chỉ quyết định việc HIỂN THỊ lối vào
   * `/admin`; quyền thật nằm ở từng route `/api/admin/*`.
   */
  is_admin?: boolean;
  /**
   * Mức quản trị THẬT (Admin Control Center V2) — "none" khi không phải quản
   * trị. CHỈ dùng để ẩn/hiện mục trong sidebar; mọi route `/api/admin/*` vẫn
   * tự kiểm lại quyền, sửa giá trị này trong DevTools không mở thêm được gì.
   */
  admin_role?: AdminRole;
  /** Khoá đối tượng R2 của avatar. Chuỗi rỗng = chưa tải — dùng `avatar_url`
      để hiển thị, không bao giờ tự dựng URL từ khoá này. */
  avatar_key?: string;
  /** URL xem được của avatar, do máy chủ ký. `null`/`undefined` = chưa có —
      giao diện lùi về chữ cái đầu tên. */
  avatar_url?: string | null;
}

/**
 * Một mục của `GET /api/progress/continue` — module "Tiếp tục đọc"/"Tiếp
 * tục nghe" ở trang chủ. CON TRỎ duy nhất tới nơi đang dở dang, không phải
 * lịch sử — xem `server/main.py` khu "TIEP TUC DOC / NGHE".
 */
export interface ContinueItem {
  novel_id: string;
  novel_title: string;
  chapter_id: string;
  chapter_title: string;
  chapter_order_index: number;
  updated_at: string;
  /** Chỉ có ở mục "đang nghe". */
  position_seconds?: number;
  /** `null` khi chưa rõ độ dài (track cũ/đã xoá) — đừng vẽ "x / 0:00". */
  duration_seconds?: number | null;
}

/**
 * Mục "Tiếp tục xem" Animation (V6, overnight Phase 5) — CÙNG vai trò với
 * `ContinueItem`, hình dạng riêng vì series/episode không phải novel/chapter.
 */
export interface ContinueWatchItem {
  series_id: string;
  series_title: string;
  episode_id: string;
  episode_title: string;
  episode_order_index: number;
  position_seconds: number;
  /** `null` khi chưa rõ độ dài — CLIENT tự ghi lại từ YouTube IFrame API. */
  duration_seconds: number | null;
  updated_at: string;
}

/** Một bậc danh xưng (Phần G-I, V4 visual completion vòng 2) — độc lập với
 * huy hiệu tác giả (`is_author`/`AuthorStatus`). Xem `server/gamification.py::LEVEL_TIERS`. */
export interface TitleTier {
  key: string;
  title: string;
  level: number;
  min_xp: number;
  unlocked: boolean;
}

/** Cấp độ CỦA CHÍNH MÌNH — mọi giá trị do máy chủ tính. */
export interface OwnProgress {
  xp: number;
  level: number;
  level_key: string;
  current_level_xp: number;
  next_level_xp: number | null;
  progress_percent: number;
  equipped_title_key: string;
  equipped_title: string;
  pending_reward_packs: number;
}

/** Cấp độ CÔNG KHAI (trên `/u/[username]`) — KHÔNG có xp/tiến trình nội bộ. */
export interface PublicProgress {
  level: number;
  level_key: string;
  equipped_title_key: string;
  equipped_title: string;
}

export interface CosmeticItem {
  key: string;
  name: string;
  rarity: "common" | "rare" | "epic" | "legendary" | "mythic";
  slot: "avatar_frame" | "profile_ornament" | "badge" | "card_border" | "title_effect";
  asset_ref: string;
  equipped?: boolean;
  acquired_at?: string;
}

/** Chuỗi ngày đọc CỦA CHÍNH MÌNH — xem `server/gamification_domain.py::ReadingStreak`. */
export interface ReadingStreak {
  current_streak: number;
  longest_streak: number;
  last_read_date: string | null;
}

/** Một nhiệm vụ (ngày/tuần) kèm tiến độ CỦA CHÍNH MÌNH trong kỳ hiện tại. */
export interface QuestItem {
  key: string;
  name: string;
  description: string;
  period: "daily" | "weekly";
  target_count: number;
  xp_reward: number;
  cosmetic_reward_key: string | null;
  count: number;
  completed: boolean;
  claimed: boolean;
}

/** Một hàng trong bảng xếp hạng XP — xem `gamification_service._the_bang_xep_hang`. */
export interface LeaderboardEntry {
  user_id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  title: string;
  rank: number;
  xp: number;
  is_you: boolean;
  equipped_cosmetics: CosmeticItem[];
}

export interface LeaderboardResponse {
  items: LeaderboardEntry[];
  total: number;
  limit: number;
  offset: number;
  /** Hạng THẬT của người xem dù họ có nằm trong `items` hay không —
      `null` khi chưa đăng nhập hoặc chưa có XP nào. */
  viewer_entry: LeaderboardEntry | null;
}

/**
 * Một thành tựu (V4 visual completion). Điều kiện tính tại chỗ từ dữ liệu
 * đã có, nhưng lần đầu đạt điều kiện được LƯU THẬT kèm `unlocked_at` (xem
 * `server/gamification_domain.py::UnlockedAchievement`) — không mất khi
 * dữ liệu nguồn giảm sau đó (ví dụ xoá truyện).
 *
 * `description`/`progress` chỉ có ở phiên bản CỦA CHÍNH MÌNH
 * (`/api/account/achievements`); bản công khai (`/u/[username]`) chỉ có
 * `key`/`name`/`icon`/`rarity`/`unlocked`.
 */
export interface Achievement {
  key: string;
  name: string;
  description?: string;
  icon: string;
  rarity: "common" | "rare" | "epic" | "legendary" | "mythic";
  unlocked: boolean;
  progress?: [number, number] | null;
  unlocked_at?: string | null;
}

/** Được phép **xuất bản công khai** hay không. Đây là moderation, KHÔNG phải uy
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
  /** URL avatar đã ký, hoặc `null` khi chưa tải. Tuỳ chọn để client cũ vẫn
      biên dịch được — cùng lý do với `Novel.cover_url`. */
  avatar_url?: string | null;
  /**
   * Số liệu xã hội, ghép sẵn vào cùng một lần gọi.
   *
   * Tuỳ chọn để một client cũ (chưa biết trường này) vẫn biên dịch được — cùng
   * lý do với `Novel.cover_url`.
   */
  social?: ProfileSocial;
  /**
   * Gamification CÔNG KHAI (V4 visual completion vòng 2) — bậc/danh xưng
   * đang trang bị, thành tựu đã mở (chỉ boolean, không lộ điều kiện gốc),
   * vật phẩm đang trang bị. Tuỳ chọn để client cũ vẫn biên dịch được.
   */
  gamification?: PublicProgress & {
    achievements: Achievement[];
    equipped_cosmetics: CosmeticItem[];
  };
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

/**
 * Mot series Animation (V6, overnight Phase 5) — tuong duong `Novel` nhung
 * cho san pham XEM, doc lap voi Truyen/Audio. Xem docstring dau
 * `server/animation_domain.py`.
 */
export interface AnimationSeries {
  series_id: string;
  owner_id: string;
  title: string;
  description: string;
  cover_key: string | null;
  cover_url?: string | null;
  state: PublishState;
  tags: string[];
  /** Lien ket TUY CHON toi mot truyen — chuoi rong = khong lien ket. */
  related_novel_id: string;
  /**
   * Kiem duyet (Phase 4, Admin Control Center V2) — TACH BACH voi `state` o
   * tren. `state` la truc XUAT BAN cua chu so huu; `moderation_state` la
   * truc GO XUONG cua quan tri, chu so huu KHONG doi duoc qua bat ky route
   * nao cua ho. Xem `server/animation_domain.py::AnimationSeries`.
   */
  moderation_state: "visible" | "removed";
  removed_by: string;
  removed_reason: string;
  created_at: string;
  updated_at: string;
}

export type AnimationSource =
  | "youtube"
  // Danh san — CHUA trien khai, xem `AnimationSource` o backend.
  | "native"
  | "google_drive_private"
  | "cloudflare_stream";

/** Mot tap trong mot series — tuong duong `Chapter`. */
export interface AnimationEpisode {
  episode_id: string;
  series_id: string;
  owner_id: string;
  title: string;
  source: AnimationSource;
  /** ID YouTube 11 ky tu DA CHUAN HOA — KHONG PHAI url tho. */
  external_id: string;
  order_index: number;
  state: PublishState;
  /** Giay — `0` = chua biet (client tu ghi lai tu YouTube IFrame API). */
  duration_seconds: number;
  /** Kiem duyet (Phase 4) — cung y nghia voi `AnimationSeries.moderation_state`,
      nhung RIENG cho tung tap: go mot tap KHONG dong toi series cha. */
  moderation_state: "visible" | "removed";
  removed_by: string;
  removed_reason: string;
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

/** Mot doan hien thi cua phu de dong bo — xem `server/transcript.py`. */
export interface TranscriptSegment {
  text: string;
  start_ms: number;
  end_ms: number;
}

/**
 * Phu de dong bo sinh TU CHINH van ban TTS, khong phai ASR — xem
 * `server/transcript.py`. `available: false` khi chua co (audio cu, hoac
 * mot phan khong do duoc luc tong hop): CAC TRUONG KHAC deu vang mat luc do,
 * dung kiem `available` truoc khi doc bat ky truong nao khac.
 */
export type ChapterTranscript =
  | { available: false }
  | {
      available: true;
      version: number;
      track_id: string;
      chapter_id: string;
      source_content_hash: string;
      duration_ms: number;
      /**
       * Chuoi CO NGHIA mo ta do chinh xac — vi du
       * `"part_exact_sentence_estimated"`: thoi luong CA PHAN chinh xac
       * (do bang ffprobe), thoi diem TUNG DOAN la UOC LUONG theo ty le ky
       * tu. KHONG BAO GIO chinh xac tung tu.
       */
      timing_quality: string;
      segments: TranscriptSegment[];
    };

/** Loi API kem thong bao tieng Viet de hien thi thang cho nguoi dung. */
export class ApiError extends Error {
  status: number;
  /** V5.1 BYOK — ma loi SACH khi backend tra `detail` dang object
      (`{code, message}`, xem `ConnectionCheckError` o server). Rong voi
      moi loi khac (detail dang chuoi nhu truoc gio). */
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
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
    let code: string | undefined;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (body?.detail && typeof body.detail === "object") {
        // V5.1 BYOK — `{code, message}` (xem `ConnectionCheckError`).
        if (typeof body.detail.message === "string") message = body.detail.message;
        if (typeof body.detail.code === "string") code = body.detail.code;
      }
    } catch {
      /* giu thong bao mac dinh */
    }
    throw new ApiError(message, response.status, code);
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

  /**
   * Tai/doi avatar. `image` da qua xu ly o trinh duyet — xem
   * `lib/image.ts::xuLyAnh`. May chu van kiem lai MIME/kich thuoc that.
   */
  setAvatar: (
    image: { base64: string; mime: string; width: number; height: number },
  ) =>
    request<{ profile: Profile }>("/api/creator/avatar", {
      method: "PUT",
      body: JSON.stringify(image),
    }),

  /** Go avatar — giao dien lui ve chu cai dau ten. */
  removeAvatar: () =>
    request<{ profile: Profile }>("/api/creator/avatar", { method: "DELETE" }),

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
   * Truyện có audio khớp từ khoá (V4 visual completion, vòng 2, Bước 11).
   * Chỉ truyện đã xuất bản và có ít nhất một chương đã có bản audio.
   */
  searchAudio: (q: string, limit = 5) =>
    request<{ novels: (Novel & { audio_chapter_count: number })[] }>(
      `/api/search/audio?q=${encodeURIComponent(q)}&limit=${limit}`,
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
   * Ghi con trỏ "đang đọc chương nào" cho module Tiếp tục đọc ở trang chủ.
   *
   * Khác `reportListen`: đây là TIỆN ÍCH CÁ NHÂN (bắt buộc đăng nhập), không
   * phải uy tín công khai — xem `server/main.py` khu "TIEP TUC DOC / NGHE".
   */
  reportReadProgress: (novelId: string, chapterId: string) =>
    request<{ ok: boolean }>("/api/progress/read", {
      method: "POST",
      body: JSON.stringify({ novel_id: novelId, chapter_id: chapterId }),
    }),

  /** Cùng vai trò với `reportReadProgress`, kèm vị trí giây để vẽ thanh tiến độ. */
  reportListenProgress: (novelId: string, chapterId: string, positionSeconds: number) =>
    request<{ ok: boolean }>("/api/progress/listen", {
      method: "POST",
      body: JSON.stringify({
        novel_id: novelId,
        chapter_id: chapterId,
        position_seconds: Math.max(0, positionSeconds),
      }),
    }),

  /** Dữ liệu cho ba module trang chủ: Tiếp tục đọc / nghe / xem. */
  getContinueProgress: () =>
    request<{
      reading: ContinueItem | null;
      listening: ContinueItem | null;
      watching: ContinueWatchItem | null;
    }>("/api/progress/continue"),

  /** Cùng vai trò với `reportListenProgress`, cho Animation. Vị trí/độ dài do
      YouTube IFrame API ở trình duyệt báo về. */
  reportWatchProgress: (
    seriesId: string,
    episodeId: string,
    positionSeconds: number,
    durationSeconds: number,
  ) =>
    request<{ ok: boolean }>("/api/progress/watch", {
      method: "POST",
      body: JSON.stringify({
        series_id: seriesId,
        episode_id: episodeId,
        position_seconds: Math.max(0, positionSeconds),
        duration_seconds: Math.max(0, durationSeconds),
      }),
    }),

  /**
   * Thành tựu CỦA CHÍNH MÌNH — tính tại chỗ từ dữ liệu đã có (xem
   * `server/gamification.py`). Chỉ chính chủ, không dùng cho hồ sơ công khai.
   */
  getAchievements: () =>
    request<{ achievements: Achievement[] }>("/api/account/achievements"),

  /** Cấp độ/XP/danh xưng đang trang bị CỦA CHÍNH MÌNH. */
  getProgress: () => request<OwnProgress>("/api/account/progress"),

  /** Toàn bộ thang danh xưng, kèm cờ đã-mở-khoá — để vẽ danh sách chọn. */
  getTitles: () => request<{ titles: TitleTier[] }>("/api/account/titles"),

  /** Trang bị một danh xưng đã mở khoá. `titleKey` rỗng = quay về mặc định. */
  equipTitle: (titleKey: string) =>
    request<OwnProgress>("/api/account/title", {
      method: "POST",
      body: JSON.stringify({ title_key: titleKey }),
    }),

  /** Vật phẩm CỦA CHÍNH MÌNH — cả đang trang bị lẫn chưa. */
  getCosmetics: () => request<{ cosmetics: CosmeticItem[] }>("/api/account/cosmetics"),

  equipCosmetic: (cosmeticKey: string) =>
    request<{ cosmetic_key: string; equipped: boolean }>(
      `/api/account/cosmetics/${encodeURIComponent(cosmeticKey)}/equip`,
      { method: "POST" },
    ),

  /** Danh sách gói thưởng hiện có — công khai, không cần đăng nhập. */
  getRewardPacks: () =>
    request<{ packs: { key: string; name: string; rarity_weights: Record<string, number> }[] }>(
      "/api/account/reward-packs",
    ),

  /**
   * Mở một gói thưởng đang chờ. Kết quả do MÁY CHỦ rút và đã LƯU trước khi
   * trả lời — tải lại trang không mở lại được (xem
   * `server/gamification_service.py::open_reward_pack`).
   */
  openRewardPack: (packKey: string) =>
    request<{
      cosmetic: CosmeticItem;
      duplicate: boolean;
      pending_reward_packs: number;
    }>(`/api/account/reward-packs/${encodeURIComponent(packKey)}/open`, {
      method: "POST",
    }),

  /** Chuỗi ngày đọc CỦA CHÍNH MÌNH. */
  getStreak: () => request<ReadingStreak>("/api/account/streak"),

  /** Toàn bộ nhiệm vụ (ngày + tuần) kèm tiến độ kỳ hiện tại. */
  getQuests: () => request<{ quests: QuestItem[] }>("/api/account/quests"),

  /**
   * Nhận thưởng một nhiệm vụ ĐÃ hoàn thành, CHƯA nhận. Máy chủ đã lưu
   * `claimed=true` trước khi trả lời — tải lại trang không nhận lại được
   * (xem `server/gamification_service.py::claim_quest_reward`).
   */
  claimQuest: (questKey: string) =>
    request<{ quest_key: string; xp_awarded: number; cosmetic: CosmeticItem | null }>(
      `/api/account/quests/${encodeURIComponent(questKey)}/claim`,
      { method: "POST" },
    ),

  /**
   * Bảng xếp hạng XP — CÔNG KHAI, không cần đăng nhập (khi có, kèm
   * `viewer_entry` riêng của người xem). `mode`: `"all_time"` (mặc định)
   * hoặc `"weekly"` (XP kiếm được trong tuần ISO hiện tại).
   */
  getLeaderboard: (
    mode: "all_time" | "weekly" = "all_time",
    limit = 20,
    offset = 0,
  ) =>
    request<LeaderboardResponse>(
      `/api/leaderboard?mode=${mode}&limit=${limit}&offset=${offset}`,
    ),

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

  /**
   * Tai/doi anh bia truyen. `image` da qua xu ly o trinh duyet (WebP, da nen)
   * — xem `lib/image.ts::xuLyAnh`. May chu van kiem lai MIME/kich thuoc that.
   */
  setNovelCover: (
    novelId: string,
    image: { base64: string; mime: string; width: number; height: number },
  ) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}/cover`, {
      method: "PUT",
      body: JSON.stringify(image),
    }),

  /** Go anh bia — truyen lui ve hien thi gradient + rune du phong. */
  removeNovelCover: (novelId: string) =>
    request<{ novel: Novel }>(`/api/novels/${novelId}/cover`, {
      method: "DELETE",
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
   * Phu de dong bo cua audio HIEN TAI cua chuong (V4, Phan 2F-2I).
   *
   * `available: false` la trang thai HOP LE (chua co audio, audio cu tu
   * truoc tinh nang nay, hoac mot phan khong do duoc thoi luong luc tong
   * hop) — KHONG phai loi. Giao dien phai ve duoc ca hai truong hop, khong
   * coi `false` la mot ngoai le can bat.
   */
  getChapterTranscript: (chapterId: string) =>
    request<ChapterTranscript>(`/api/chapters/${chapterId}/transcript`),

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

  // -- Subtitle Studio (overnight Phase 4, Phan 4E) --------------------------

  /**
   * Dich MOT LO dong phu de (toi da 50 dong/lan, khop gioi han backend) —
   * CHI van ban, khong bao gio gui video. Dung `lib/subtitles/translate.ts`
   * (`dichDongPhuDe`) de tu chia lo cho danh sach dai hon.
   */
  translateSubtitleLines: (texts: string[]) =>
    request<{ translated: string[] }>("/api/tools/subtitles/translate", {
      method: "POST",
      body: JSON.stringify({ texts }),
    }),

  // -- Animation (overnight Phase 5, V6) --------------------------------------

  /** Thu vien Animation cong khai, hoac danh sach cua rieng minh khi `mine`. */
  listAnimationSeries: (opts: {
    mine?: boolean;
    query?: string;
    tag?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const params = new URLSearchParams();
    if (opts.mine) params.set("mine", "true");
    if (opts.query?.trim()) params.set("q", opts.query.trim());
    if (opts.tag) params.set("tag", opts.tag);
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.offset != null) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<{
      series: AnimationSeries[];
      count: number;
      total: number;
      limit: number | null;
      offset: number;
      has_more: boolean;
    }>(`/api/animation/series${qs ? `?${qs}` : ""}`);
  },

  /** Cac the dang co tren series DA XUAT BAN, cho bo loc. */
  animationSeriesTags: () =>
    request<{ tags: string[]; count: number }>("/api/animation/series/tags"),

  createAnimationSeries: (
    title: string,
    description: string,
    tags: string[] = [],
    relatedNovelId = "",
  ) =>
    request<{ series: AnimationSeries }>("/api/animation/series", {
      method: "POST",
      body: JSON.stringify({
        title,
        description,
        tags,
        related_novel_id: relatedNovelId,
      }),
    }),

  /** Series kem DANH SACH TAP, trong MOT request. */
  getAnimationSeries: (seriesId: string) =>
    request<{ series: AnimationSeries; episodes: AnimationEpisode[] }>(
      `/api/animation/series/${seriesId}`,
    ),

  updateAnimationSeries: (
    seriesId: string,
    fields: {
      title?: string;
      description?: string;
      tags?: string[];
      related_novel_id?: string;
    },
  ) =>
    request<{ series: AnimationSeries }>(`/api/animation/series/${seriesId}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),

  publishAnimationSeries: (seriesId: string) =>
    request<{ series: AnimationSeries }>(
      `/api/animation/series/${seriesId}/publish`,
      { method: "POST" },
    ),

  unpublishAnimationSeries: (seriesId: string) =>
    request<{ series: AnimationSeries }>(
      `/api/animation/series/${seriesId}/unpublish`,
      { method: "POST" },
    ),

  /** Xoa series cung moi tap cua no. KHONG dong toi YouTube. */
  deleteAnimationSeries: (seriesId: string) =>
    request<{ deleted: boolean; removed_episodes: number }>(
      `/api/animation/series/${seriesId}`,
      { method: "DELETE" },
    ),

  /** `youtubeUrl` nhan MOI dang URL YouTube pho bien, hoac ID tran. */
  createAnimationEpisode: (
    seriesId: string,
    title: string,
    youtubeUrl: string,
    orderIndex = 1,
  ) =>
    request<{ episode: AnimationEpisode }>("/api/animation/episodes", {
      method: "POST",
      body: JSON.stringify({
        series_id: seriesId,
        title,
        youtube_url: youtubeUrl,
        order_index: orderIndex,
      }),
    }),

  /** Mot tap kem series cha va tap ke truoc/sau. */
  getAnimationEpisode: (episodeId: string) =>
    request<{
      episode: AnimationEpisode;
      series: AnimationSeries;
      prev_episode_id: string | null;
      next_episode_id: string | null;
    }>(`/api/animation/episodes/${episodeId}`),

  updateAnimationEpisode: (
    episodeId: string,
    fields: { title?: string; youtube_url?: string; order_index?: number },
  ) =>
    request<{ episode: AnimationEpisode }>(
      `/api/animation/episodes/${episodeId}`,
      { method: "PATCH", body: JSON.stringify(fields) },
    ),

  deleteAnimationEpisode: (episodeId: string) =>
    request<{ deleted: boolean }>(`/api/animation/episodes/${episodeId}`, {
      method: "DELETE",
    }),

  reorderAnimationEpisodes: (seriesId: string, episodeIds: string[]) =>
    request<{ episodes: AnimationEpisode[] }>(
      `/api/animation/series/${seriesId}/episodes/order`,
      { method: "POST", body: JSON.stringify({ episode_ids: episodeIds }) },
    ),

  /** Danh muc "Animation" cua tim kiem toan cuc. */
  searchAnimation: (q: string, limit = 5) =>
    request<{ series: AnimationSeries[] }>(
      `/api/search/animation?q=${encodeURIComponent(q)}&limit=${limit}`,
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

/**
 * Mot chi so co the CHUA CO du lieu (schema chua theo doi, hoac nha cung cap
 * ngoai chua cau hinh) — `null` nghia la "chua co", KHONG PHAI 0. Giao dien
 * PHAI phan biet hai truong hop nay (Admin Control Center V2, A1: "Do not
 * fabricate numbers").
 */
export type ChiSo = number | null;

export interface AdminOverview {
  // Cac truong CU, tu ban dau — giu nguyen, khong doi kieu.
  pending_applications: number;
  approved_authors: number;
  rejected_applications: number;
  suspended_authors: number;
  published_novels: number;
  users_with_username: number;
  qualified_listens: number;

  // Admin Control Center V2, Phase 2 — cac muc MOI cua bang dieu khien.
  users: {
    total: number;
    new_today: number;
    new_7d: number;
    new_30d: number;
    verified: ChiSo;
    unverified: ChiSo;
    suspended: ChiSo;
  };
  content: {
    novels_total: number;
    chapters_total: number;
    comments_total: number;
    animation_series_total: number;
    animation_series_published: number;
    animation_episodes_total: number;
    pending_reports: number;
  };
  product: {
    translation_projects_total: number;
    tts_jobs_total: number;
    image_studio_spend_usd: number;
    image_studio_budget_usd: number;
    image_generations_total: ChiSo;
  };
  trusted_sources: {
    configured: boolean;
    total?: number;
    enabled_total?: number;
    /** `null` — kho chưa lọc video phát hiện theo ngày, xem `server/main.py`. */
    detected_today?: ChiSo;
    auto_imported_total?: number;
    pending_total?: number;
    error_total?: number;
  };
  traffic: {
    configured: boolean;
    visits_7d: ChiSo;
    pageviews_7d: ChiSo;
    visits_30d: ChiSo;
    pageviews_30d: ChiSo;
    top_paths: Array<{ path: string; count: number }> | null;
    message: string;
  };
  system: {
    backend: string;
    data_backend: string;
    appwrite_configured: boolean;
    appwrite_healthy: boolean | null;
    inline_worker: boolean;
    translation_provider_configured: boolean;
    image_studio_shared_premium_configured: boolean;
  };
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

  // Phase 3, Admin Control Center V2 — tu Appwrite Users API (native),
  // KHONG phai `profiles`. Xem `AccountStatus` o server/domain.py.
  email_verified?: boolean;
  account_enabled?: boolean;
  registered_at?: string;
  /** Vai tro quan tri, doc qua `Settings.admin_role_of` — CHI de hien thi,
      khong phai bien kiem quyen (backend luon tu kiem lai). */
  admin_role?: AdminRole;
  /** Chi co o CHI TIET mot tai khoan (`/api/admin/users/{id}`). `null` =
      khong doc duoc tu Appwrite Users API (tai khoan khong ton tai native,
      truong hop hau nhu khong xay ra vi user_id luon den tu Auth). */
  account?: AdminAccountStatus | null;
  sessions?: AdminAccountSession[];
}

/** Trang thai tai khoan NATIVE (Appwrite Auth) — TACH BACH voi
    `author_status` (quyen xuat ban). `enabled=false` = khoa dang nhap HOAN
    TOAN, o moi duong (email lan OAuth). */
export interface AdminAccountStatus {
  user_id: string;
  email: string;
  name: string;
  enabled: boolean;
  email_verified: boolean;
  phone_verified: boolean;
  registered_at: string;
}

/** Mot phien dang nhap, doc tu Appwrite Users API. */
export interface AdminAccountSession {
  session_id: string;
  provider: string;
  ip: string;
  os_name: string;
  client_name: string;
  device_name: string;
  country_name: string;
  current: boolean;
  created_at: string;
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

/** Vi du tu vung `action` hien tai (server/scripts/setup_appwrite.py) — danh
    sach That con dai hon, kieu string de khong phai doi frontend moi khi
    backend mo rong enum. */
export type AdminAuditAction =
  | "author_approved" | "author_rejected"
  | "author_suspended" | "author_restored"
  | "post_removed" | "post_restored"
  | "comment_removed" | "comment_restored"
  | "report_resolved" | "report_dismissed"
  | "user_suspend" | "user_unsuspend" | "user_session_terminate"
  | "user_role_change" | "user_delete"
  | "content_unpublish" | "content_restore"
  | "trusted_source_add" | "trusted_source_disable" | "trusted_source_enable"
  | "youtube_mapping_create" | "youtube_mapping_update"
  | "auto_import_approve" | "auto_import_reject" | "auto_publish_toggle"
  | (string & {});

export interface ModerationEvent {
  event_id: string;
  action: AdminAuditAction;
  target_user_id: string;
  actor_id: string;
  /** Admin Control Center V2 — rỗng cho bản ghi cũ trước migration. */
  actor_role?: AdminRole | "";
  target_type?: string;
  target_id?: string;
  note: string;
  metadata?: string;
  created_at: string;
}

export interface AdminNovel extends Novel {
  chapters: number;
  owner: { display_name: string; username: string } | null;
}

/** Mot dong trong danh sach series cho khu quan tri (Phase 4). */
export interface AdminAnimationSeriesRow extends AnimationSeries {
  owner: { display_name: string; username: string } | null;
  episode_count: number;
  related_novel: { novel_id: string; title: string } | null;
}

/** Chi tiet MOT series cho khu quan tri — kem TOAN BO tap (ke ca da bi go)
    va lich su kiem duyet cua CHINH series (khong phai cua tung tap). */
export interface AdminAnimationSeriesDetail {
  series: AnimationSeries;
  owner: { display_name: string; username: string } | null;
  related_novel: { novel_id: string; title: string; state: PublishState } | null;
  episodes: AnimationEpisode[];
  events: ModerationEvent[];
}

// -- Trusted Video Sources (Phase 5, Admin Control Center V2) ---------------
//
// Kieu khop `to_dict()` cua `server/trusted_source_domain.py`. YouTube API
// key KHONG BAO GIO xuat hien o day — backend giu rieng, frontend chi thay
// KET QUA da tra cuu (ten kenh, thumbnail...).

export type TrustedSourceType =
  | "youtube_channel" | "youtube_playlist" | "youtube_video"
  | "direct_hls" | "direct_mp4";

export type SubscriptionStatus = "none" | "pending" | "active" | "expired" | "failed";

/** Vong doi MOT video phat hien duoc — xem docstring `ImportStatus` phia
    server de biet y nghia day du cua tung gia tri. */
export type VideoImportStatus =
  | "new" | "pending" | "auto_imported" | "auto_published" | "imported"
  | "rejected" | "ignored" | "duplicate" | "conflict" | "unavailable" | "failed";

export interface TrustedSource {
  source_id: string;
  source_type: TrustedSourceType;
  youtube_channel_id: string;
  youtube_playlist_id: string;
  youtube_video_id: string;
  display_name: string;
  thumbnail_url: string;
  enabled: boolean;
  auto_discover: boolean;
  auto_import: boolean;
  auto_publish: boolean;
  minimum_confidence: number;
  created_by: string;
  last_scan_at: string;
  last_success_at: string;
  last_error_at: string;
  last_error_message: string;
  subscription_status: SubscriptionStatus;
  subscription_expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface AdminTrustedSourceRow extends TrustedSource {
  mapping_count: number;
}

export interface SeriesMapping {
  mapping_id: string;
  trusted_source_id: string;
  animation_series_id: string;
  aliases: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  /** `null` = ke thua nguong/co cua nguon (`TrustedSource`). */
  minimum_confidence: number | null;
  auto_import: boolean | null;
  auto_publish: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface AdminSeriesMappingRow extends SeriesMapping {
  series_title: string;
}

export interface VideoImport {
  import_id: string;
  trusted_source_id: string;
  youtube_video_id: string;
  title: string;
  channel_id: string;
  channel_title: string;
  thumbnail_url: string;
  published_at: string;
  duration_seconds: number;
  detected_mapping_id: string;
  detected_series_id: string;
  detected_episode_number: number | null;
  confidence: number;
  signals: string[];
  status: VideoImportStatus;
  reason: string;
  created_episode_id: string;
  reviewed_by: string;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}

export interface AdminVideoImportRow extends VideoImport {
  source_display_name: string;
  series_title: string;
}

/** Ket qua xem truoc MOT url/ID YouTube — CHUA tao gi ca, xem
    `adminApi.previewTrustedSourceUrl`. */
export interface TrustedSourcePreview {
  source_type: TrustedSourceType;
  youtube_channel_id: string;
  youtube_playlist_id: string;
  youtube_video_id: string;
  display_name: string;
  thumbnail_url: string;
  channel_title: string;
  channel_thumbnail_url?: string;
  item_count?: number;
}

export interface AdminTrustedSourceDetail {
  source: TrustedSource;
  mappings: AdminSeriesMappingRow[];
  recent_imports: VideoImport[];
}

/** Ket qua MOT lan "Quet video co san" — xem `TrustedSourceService.scan_source`. */
export interface TrustedSourceScanResult {
  detected: number;
  matched: number;
  pending: number;
  auto_imported: number;
  auto_published: number;
  excluded: number;
  conflicts: number;
  duplicates: number;
  already_tracked: number;
  next_page_token: string;
}

export interface AdminImageStudioSpending {
  month: string;
  spent_usd: number;
  budget_usd: number;
  warning_usd: number;
  kill_switch_engaged: boolean;
  active_concurrent: number;
  max_concurrent: number;
  shared_premium_enabled_config: boolean;
  shared_premium_configured: boolean;
}

export const adminApi = {
  overview: () => request<AdminOverview>("/api/admin/overview"),

  /** AI / Credits (Admin Control Center V2) — chi tieu Image Studio. */
  imageStudioSpending: () =>
    request<AdminImageStudioSpending>("/api/admin/image-studio/spending"),

  /** CHI OWNER goi duoc — server tu choi 403 voi vai tro thap hon. */
  imageStudioKillSwitch: (engaged: boolean) =>
    request<{ kill_switch_engaged: boolean }>(
      "/api/admin/image-studio/kill-switch",
      { method: "POST", body: JSON.stringify({ engaged }) },
    ),

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

  /** Khoa dang nhap HOAN TOAN — TACH BACH voi `suspend()` o tren (chi chan
      xuat ban). Phase 3, Admin Control Center V2. */
  suspendAccount: (userId: string, note = "") =>
    request<{ account: AdminAccountStatus }>(
      `/api/admin/users/${encodeURIComponent(userId)}/suspend`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  unsuspendAccount: (userId: string, note = "") =>
    request<{ account: AdminAccountStatus }>(
      `/api/admin/users/${encodeURIComponent(userId)}/unsuspend`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  terminateSession: (userId: string, sessionId: string, note = "") =>
    request<{ terminated: boolean }>(
      `/api/admin/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/terminate`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  terminateAllSessions: (userId: string, note = "") =>
    request<{ terminated_count: number }>(
      `/api/admin/users/${encodeURIComponent(userId)}/sessions/terminate-all`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  novels: (q = "", state = "", limit = 25, offset = 0) =>
    request<{ novels: AdminNovel[]; total: number }>(
      `/api/admin/novels?q=${encodeURIComponent(q)}&state=${state}` +
        `&limit=${limit}&offset=${offset}`,
    ),

  events: (
    limit = 50,
    opts: {
      offset?: number; targetUserId?: string; targetType?: string;
      targetId?: string; action?: string;
    } = {},
  ) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (opts.offset) p.set("offset", String(opts.offset));
    if (opts.targetUserId) p.set("target_user_id", opts.targetUserId);
    if (opts.targetType) p.set("target_type", opts.targetType);
    if (opts.targetId) p.set("target_id", opts.targetId);
    if (opts.action) p.set("action", opts.action);
    return request<{ events: ModerationEvent[]; total: number }>(
      `/api/admin/events?${p.toString()}`,
    );
  },

  // -- Animation (Phase 4, Admin Control Center V2) ------------------------
  //
  // Kiem duyet series/tap: go xuong (`moderation_state`) TACH BACH voi
  // `state` xuat ban cua chu so huu — xem `AnimationSeries.moderation_state`.

  animationSeries: (
    opts: {
      q?: string; state?: "" | "draft" | "published";
      sort?: "newest" | "oldest"; limit?: number; offset?: number;
    } = {},
  ) => {
    const p = new URLSearchParams({
      q: opts.q ?? "", state: opts.state ?? "", sort: opts.sort ?? "newest",
      limit: String(opts.limit ?? 25), offset: String(opts.offset ?? 0),
    });
    return request<{ series: AdminAnimationSeriesRow[]; total: number;
                    limit: number; offset: number }>(
      `/api/admin/animation/series?${p.toString()}`,
    );
  },

  animationSeriesDetail: (seriesId: string) =>
    request<AdminAnimationSeriesDetail>(
      `/api/admin/animation/series/${encodeURIComponent(seriesId)}`,
    ),

  unpublishAnimationSeries: (seriesId: string, reason: string) =>
    request<{ series: AnimationSeries }>(
      `/api/admin/animation/series/${encodeURIComponent(seriesId)}/unpublish`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),

  restoreAnimationSeries: (seriesId: string) =>
    request<{ series: AnimationSeries }>(
      `/api/admin/animation/series/${encodeURIComponent(seriesId)}/restore`,
      { method: "POST", body: "{}" },
    ),

  unpublishAnimationEpisode: (episodeId: string, reason: string) =>
    request<{ episode: AnimationEpisode }>(
      `/api/admin/animation/episodes/${encodeURIComponent(episodeId)}/unpublish`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),

  restoreAnimationEpisode: (episodeId: string) =>
    request<{ episode: AnimationEpisode }>(
      `/api/admin/animation/episodes/${encodeURIComponent(episodeId)}/restore`,
      { method: "POST", body: "{}" },
    ),

  // -- Trusted Video Sources (Phase 5, Admin Control Center V2) ------------
  //
  // Xem/danh sach: MODERATOR tro len. Them/sua/xoa/quet/nhap: CHI ADMIN/OWNER
  // (xem `admin_or_owner_profile` phia server) — day la hanh dong xac nhan
  // tin cay/tao noi dung that, khac voi kiem duyet thong thuong.
  //
  // Loi 503 = YouTube Data API CHUA CAU HINH — hien qua `<ChuaCauHinh>`,
  // khong phai mot thong bao loi chung.

  previewTrustedSourceUrl: (url: string) =>
    request<TrustedSourcePreview>("/api/admin/animation/sources/preview", {
      method: "POST", body: JSON.stringify({ url }),
    }),

  trustedSources: (
    opts: { q?: string; enabled?: boolean; limit?: number; offset?: number } = {},
  ) => {
    const p = new URLSearchParams({
      q: opts.q ?? "", limit: String(opts.limit ?? 25), offset: String(opts.offset ?? 0),
    });
    if (opts.enabled !== undefined) p.set("enabled", String(opts.enabled));
    return request<{ sources: AdminTrustedSourceRow[]; total: number;
                    limit: number; offset: number }>(
      `/api/admin/animation/sources?${p.toString()}`,
    );
  },

  createTrustedSource: (payload: {
    source_type: TrustedSourceType; youtube_channel_id?: string;
    youtube_playlist_id?: string; youtube_video_id?: string; display_name: string;
    thumbnail_url?: string; auto_discover?: boolean; auto_import?: boolean;
    auto_publish?: boolean; minimum_confidence?: number;
  }) =>
    request<{ source: TrustedSource }>("/api/admin/animation/sources", {
      method: "POST", body: JSON.stringify(payload),
    }),

  trustedSourceDetail: (sourceId: string) =>
    request<AdminTrustedSourceDetail>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}`,
    ),

  updateTrustedSource: (sourceId: string, fields: Partial<{
    display_name: string; auto_discover: boolean; auto_import: boolean;
    auto_publish: boolean; minimum_confidence: number;
  }>) =>
    request<{ source: TrustedSource }>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}`,
      { method: "PATCH", body: JSON.stringify(fields) },
    ),

  setTrustedSourceEnabled: (sourceId: string, enabled: boolean) =>
    request<{ source: TrustedSource }>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}/enabled`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    ),

  removeTrustedSource: (sourceId: string) =>
    request<{ ok: boolean }>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}`,
      { method: "DELETE" },
    ),

  scanTrustedSource: (
    sourceId: string, opts: { pageToken?: string; maxPages?: number } = {},
  ) =>
    request<TrustedSourceScanResult>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}/scan`,
      { method: "POST", body: JSON.stringify({
        page_token: opts.pageToken ?? "", max_pages: opts.maxPages ?? 2 }) },
    ),

  createSeriesMapping: (sourceId: string, payload: {
    animation_series_id: string; aliases?: string[]; include_keywords?: string[];
    exclude_keywords?: string[]; minimum_confidence?: number | null;
    auto_import?: boolean | null; auto_publish?: boolean | null;
  }) =>
    request<{ mapping: SeriesMapping }>(
      `/api/admin/animation/sources/${encodeURIComponent(sourceId)}/mappings`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  updateSeriesMapping: (mappingId: string, fields: Partial<{
    aliases: string[]; include_keywords: string[]; exclude_keywords: string[];
    minimum_confidence: number | null; auto_import: boolean | null;
    auto_publish: boolean | null;
  }>) =>
    request<{ mapping: SeriesMapping }>(
      `/api/admin/animation/mappings/${encodeURIComponent(mappingId)}`,
      { method: "PATCH", body: JSON.stringify(fields) },
    ),

  removeSeriesMapping: (mappingId: string) =>
    request<{ ok: boolean }>(
      `/api/admin/animation/mappings/${encodeURIComponent(mappingId)}`,
      { method: "DELETE" },
    ),

  videoImports: (
    opts: { status?: string; trustedSourceId?: string; seriesId?: string;
           limit?: number; offset?: number } = {},
  ) => {
    const p = new URLSearchParams({
      status_filter: opts.status ?? "",
      trusted_source_id: opts.trustedSourceId ?? "", series_id: opts.seriesId ?? "",
      limit: String(opts.limit ?? 25), offset: String(opts.offset ?? 0),
    });
    return request<{ imports: AdminVideoImportRow[]; total: number;
                    limit: number; offset: number }>(
      `/api/admin/animation/imports?${p.toString()}`,
    );
  },

  setImportSeries: (importId: string, seriesId: string, episodeNumber: number | null) =>
    request<{ import: VideoImport }>(
      `/api/admin/animation/imports/${encodeURIComponent(importId)}/series`,
      { method: "PATCH", body: JSON.stringify({
        series_id: seriesId, episode_number: episodeNumber }) },
    ),

  importVideo: (importId: string, publish: boolean) =>
    request<{ import: VideoImport }>(
      `/api/admin/animation/imports/${encodeURIComponent(importId)}/import`,
      { method: "POST", body: JSON.stringify({ publish }) },
    ),

  rejectVideoImport: (importId: string, reason: string) =>
    request<{ import: VideoImport }>(
      `/api/admin/animation/imports/${encodeURIComponent(importId)}/reject`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),

  ignoreVideoImport: (importId: string) =>
    request<{ import: VideoImport }>(
      `/api/admin/animation/imports/${encodeURIComponent(importId)}/ignore`,
      { method: "POST", body: "{}" },
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
  /** URL avatar đã ký, hoặc `null`/vắng mặt khi chưa tải — nơi hiển thị lùi
      về chữ cái đầu tên. Cùng một chỗ (`_the_nguoi` ở backend) phục vụ mọi
      nơi thẻ này xuất hiện: bài đăng, bình luận, thông báo, tìm kiếm. */
  avatar_url?: string | null;
  /** Vật phẩm sưu tầm ĐANG TRANG BỊ (V4 visual completion, vòng 4) — cùng
      một chỗ (`_the_nguoi`) nên khung avatar hiện NHẤT QUÁN ở mọi nơi thẻ
      này xuất hiện. Vắng mặt/rỗng = không trang bị gì, không phải lỗi. */
  equipped_cosmetics?: CosmeticItem[];
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
  /** V3: URL đã ký của TỪNG ảnh, cùng thứ tự với `images`. */
  image_urls?: string[];
  /** Kích thước từng ảnh cho gallery — không bao giờ kèm khóa kho. */
  images: Array<{ width: number; height: number }>;
  /** 2 bình luận mới nhất, ghép sẵn cho bảng tin — hiển thị cũ→mới. */
  comments_preview?: Comment[];
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
  novel?: {
    novel_id: string;
    title: string;
    cover_key: string | null;
    /** Tuỳ chọn để client cũ vẫn biên dịch được — cùng lý do với `Novel.cover_url`. */
    cover_url?: string | null;
  };
}

export interface Comment {
  comment_id: string;
  /** Id của ĐÍCH: bài đăng, hoặc chương (bình luận audio). Tên cột giữ nguyên
      vì lịch sử — xem `domain.Comment`. */
  post_id: string;
  /** Chuỗi rỗng khi bình luận đã bị gỡ — xem `Comment.to_public_dict`. */
  author_user_id: string;
  parent_id: string;
  /** `""` = bình luận bài đăng; `"chapter"` = bình luận chương/audio. */
  target_kind: string;
  /** Vị trí audio đính kèm, mili giây. `null` = không đính kèm — 0 là một mốc
      HỢP LỆ (đầu chương). */
  timestamp_ms: number | null;
  /** Người viết tự đánh dấu có spoiler — thân bị che cho tới khi bấm hiện. */
  spoiler: boolean;
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
  | "chapter_comment"
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
  /** Trần TỔNG dung lượng ảnh của một bài, sau xử lý. */
  post_total_media_bytes: number;
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
    /** V3: tối đa 4 ảnh. Trần thật ở máy chủ (`/api/limits`). */
    images?: Array<{
      base64: string;
      mime: string;
      width: number;
      height: number;
    }>;
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

  // -- bình luận chương (audio) ----------------------------------------------

  /** Đích là CHƯƠNG, không phải file MP3 — tác giả tạo lại audio thì chuỗi
      bình luận vẫn còn. Mặc định MỚI NHẤT trước. */
  chapterComments: (chapterId: string, sort: "moi" | "cu" = "moi",
                    limit = 20, offset = 0) =>
    request<CommentPage & { sort: string }>(
      `/api/chapters/${encodeURIComponent(chapterId)}/comments` +
        `?sort=${sort}&limit=${limit}&offset=${offset}`,
    ),

  createChapterComment: (chapterId: string, payload: {
    text: string;
    parent_id?: string;
    /** Mili giây. Bỏ qua = không đính kèm. */
    timestamp_ms?: number | null;
    spoiler?: boolean;
  }) =>
    request<{ comment: Comment }>(
      `/api/chapters/${encodeURIComponent(chapterId)}/comments`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // -- bình luận tập animation (overnight Phase 5, V6) ------------------------

  /** Đích là TẬP — cùng vai trò với `chapterComments`. */
  episodeComments: (episodeId: string, sort: "moi" | "cu" = "moi",
                    limit = 20, offset = 0) =>
    request<CommentPage & { sort: string }>(
      `/api/animation/episodes/${encodeURIComponent(episodeId)}/comments` +
        `?sort=${sort}&limit=${limit}&offset=${offset}`,
    ),

  createEpisodeComment: (episodeId: string, payload: {
    text: string;
    parent_id?: string;
  }) =>
    request<{ comment: Comment }>(
      `/api/animation/episodes/${encodeURIComponent(episodeId)}/comments`,
      { method: "POST", body: JSON.stringify(payload) },
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
  /** Đường tới NGUỒN: `/posts/{id}` hoặc `/chapters/{id}`. Backend tính. */
  context_url?: string;
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
  /** Đường tới nguồn của nội dung bị báo cáo. Backend tính. */
  context_url?: string;
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

  /** Duyệt bình luận toàn hệ thống, tách bài đăng / chương / tập Animation. */
  browseComments: (
    targetKind: "" | "chapter" | "animation_episode" = "",
    limit = 25,
    offset = 0,
  ) =>
    request<{
      items: AdminComment[];
      total: number;
      limit: number;
      offset: number;
    }>(
      `/api/admin/comments?target_kind=${targetKind}` +
        `&limit=${limit}&offset=${offset}`,
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

// =============================================================================
// V5 — Novel Translation Studio
// =============================================================================
//
// Kieu o day khop `to_dict()` cua `server/translation_domain.py`. Subsystem
// RIENG voi TTS — khong dung chung `Job`/`Chapter` o tren.

export type GenrePreset =
  | "tien_hiep" | "huyen_huyen" | "vo_hiep" | "do_thi" | "ngon_tinh"
  | "lich_su" | "he_thong" | "dong_nhan" | "kinh_di" | "auto";

export type NamingMode = "han_viet" | "pinyin" | "thuan_viet" | "fandom" | "auto";
export type QualityMode = "nhanh" | "can_bang" | "van_hoc";

export type TranslationJobStatus =
  | "queued" | "analyzing" | "glossary" | "translating" | "reviewing" | "qa"
  | "waiting_for_provider" | "completed" | "failed" | "cancelled";

export interface TranslationProject {
  project_id: string;
  owner_id: string;
  title: string;
  source_language: string;
  target_language: string;
  genre: GenrePreset;
  genre_label: string;
  naming_mode: NamingMode;
  naming_mode_label: string;
  quality_mode: QualityMode;
  custom_instruction: string;
  source_filename: string;
  chapter_count: number;
  translated_chapter_count: number;
  imported_to_novel_id: string | null;
  /** Part Q3 — "auto" hoặc "manual". */
  provider_mode: "auto" | "manual";
  selected_provider_id: string | null;
  allow_fallback: boolean;
  /** V5.1 Part F — "Ưu tiên API key cá nhân". */
  prefer_personal_provider: boolean;
  created_at: string;
  updated_at: string;
}

export type WaitingReason = "shared_free_quota_exhausted" | "personal_quota_exhausted";
export type WaitingAction = "connect_personal_provider";

export interface TranslationJob {
  job_id: string;
  project_id: string;
  status: TranslationJobStatus;
  current_chapter: number;
  total_chapters: number;
  /** Vai trò provider đang chạy ngay lúc này ("translator"/"editor"/"qa"), rỗng khi chưa chạy/đã xong. */
  current_pass: string | null;
  progress: number;
  attempts: number;
  error: string | null;
  /** Giống hệt `error` — tên khác cho cùng giá trị, dùng ở UI tiến trình. */
  last_error: string | null;
  /** Part Q4 — chỉ có ý nghĩa khi `status === "waiting_for_provider"`. */
  waiting_retry_at: string | null;
  /** V5.1 Part G — an toàn, không lộ chi tiết nội bộ. */
  waiting_reason: WaitingReason | null;
  waiting_action: WaitingAction | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

/** V5.1 BYOK — metadata AN TOÀN, không bao giờ chứa api key. */
export interface ProviderConnection {
  provider_id: string;
  connected: true;
  last4: string;
  status: ProviderStatusValue;
  selected_model: string | null;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export type ConnectionErrorCode =
  | "INVALID_KEY" | "RATE_LIMITED" | "PROVIDER_UNAVAILABLE" | "MODEL_UNAVAILABLE";

export interface GlossaryEntry {
  term_id: string;
  category: string;
  original: string;
  translated: string;
  note: string;
  locked: boolean;
}

/** Part N — chi tiet editor cua MOT chuong. */
export interface ChapterDetail {
  chapter_index: number;
  chapter_count: number;
  source_text: string;
  translated_text: string;
  source_paragraphs: string[];
  translated_paragraphs: string[];
  warnings: string[];
  manually_edited: boolean;
  previous_chapter_summary: string;
  is_translated: boolean;
}

/** Part O — mot ban ghi lich su ban dich. */
export interface TranslationVersion {
  version_id: string;
  project_id: string;
  chapter_index: number;
  paragraph_index: number | null;
  operation: string;
  pass_type: string;
  previous_text: string;
  new_text: string;
  actor_id: string | null;
  provider_id: string | null;
  model_id: string | null;
  created_at: string;
}

export type ProviderStatusValue =
  | "available" | "rate_limited" | "quota_exhausted" | "unavailable"
  | "disabled" | "unknown";

/** Part Q1/Q2 — catalog AN TOAN, khong bao gio chua bi mat. */
export interface ProviderCatalogEntry {
  provider_id: string;
  model_id: string;
  display_name: string;
  quality_hint: string;
  free_tier: boolean;
  status: ProviderStatusValue;
  reset_at: string;
}

/** Nhan tieng Viet cho giao dien — khop `GENRE_LABELS`/`NAMING_LABELS` o
    `server/translation.py`, chi de dung khi CHUA co du lieu tu may chu
    (vd trong dropdown truoc khi goi API nao). */
export const GENRE_OPTIONS: { value: GenrePreset; label: string }[] = [
  { value: "auto", label: "Tự động nhận diện" },
  { value: "tien_hiep", label: "Tiên hiệp" },
  { value: "huyen_huyen", label: "Huyền huyễn" },
  { value: "vo_hiep", label: "Võ hiệp" },
  { value: "do_thi", label: "Đô thị" },
  { value: "ngon_tinh", label: "Ngôn tình" },
  { value: "lich_su", label: "Lịch sử" },
  { value: "he_thong", label: "Hệ thống" },
  { value: "dong_nhan", label: "Đồng nhân" },
  { value: "kinh_di", label: "Kinh dị" },
];

export const NAMING_OPTIONS: { value: NamingMode; label: string }[] = [
  { value: "auto", label: "Tự động" },
  { value: "han_viet", label: "Hán Việt" },
  { value: "pinyin", label: "Pinyin" },
  { value: "thuan_viet", label: "Việt hoá ngữ nghĩa" },
  { value: "fandom", label: "Thuật ngữ fandom" },
];

export const QUALITY_OPTIONS: { value: QualityMode; label: string; hint: string }[] = [
  { value: "nhanh", label: "Nhanh", hint: "Một lượt dịch, rẻ và nhanh nhất." },
  { value: "can_bang", label: "Cân bằng",
    hint: "Dịch + kiểm tra nhất quán thuật ngữ." },
  { value: "van_hoc", label: "Văn học",
    hint: "Thêm một lượt biên tập văn học — tốn thời gian/API hơn." },
];

export const translate = {
  estimate: (sourceText: string) =>
    request<{ characters: number; estimated_tokens: number; chapters: number }>(
      "/api/translate/estimate",
      { method: "POST", body: JSON.stringify({ source_text: sourceText }) },
    ),

  createProject: (fields: {
    title?: string;
    sourceText: string;
    genre?: GenrePreset;
    namingMode?: NamingMode;
    qualityMode?: QualityMode;
    customInstruction?: string;
  }) =>
    request<{ project: TranslationProject }>("/api/translate/projects", {
      method: "POST",
      body: JSON.stringify({
        title: fields.title ?? "",
        source_text: fields.sourceText,
        genre: fields.genre ?? "auto",
        naming_mode: fields.namingMode ?? "auto",
        quality_mode: fields.qualityMode ?? "can_bang",
        custom_instruction: fields.customInstruction ?? "",
      }),
    }),

  /** `base64` la NOI DUNG TEP (khong phai van ban da giai ma) — xem
      `TranslateUploadIn` o backend, cung ly do voi anh: tranh phu thuoc
      `python-multipart` chua khai bao trong server/requirements.txt. */
  uploadProject: (fields: {
    filename: string;
    base64: string;
    title?: string;
    genre?: GenrePreset;
    namingMode?: NamingMode;
    qualityMode?: QualityMode;
    customInstruction?: string;
  }) =>
    request<{ project: TranslationProject }>("/api/translate/projects/upload", {
      method: "POST",
      body: JSON.stringify({
        filename: fields.filename,
        base64: fields.base64,
        title: fields.title ?? "",
        genre: fields.genre ?? "auto",
        naming_mode: fields.namingMode ?? "auto",
        quality_mode: fields.qualityMode ?? "can_bang",
        custom_instruction: fields.customInstruction ?? "",
      }),
    }),

  listProjects: () =>
    request<{ projects: TranslationProject[]; total: number }>(
      "/api/translate/projects",
    ),

  getProject: (projectId: string) =>
    request<{
      project: TranslationProject;
      chapters: {
        index: number; translated: boolean; text: string;
        has_warnings: boolean;
      }[];
      jobs: TranslationJob[];
    }>(`/api/translate/projects/${encodeURIComponent(projectId)}`),

  createJob: (projectId: string) =>
    request<{ job: TranslationJob }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/jobs`,
      { method: "POST", body: "{}" },
    ),

  getJob: (jobId: string) =>
    request<{ job: TranslationJob }>(
      `/api/translate/jobs/${encodeURIComponent(jobId)}`,
    ),

  cancelJob: (jobId: string) =>
    request<{ job: TranslationJob }>(
      `/api/translate/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST", body: "{}" },
    ),

  /** Thử lại một job đã `failed` — tiếp tục đúng từ chương còn thiếu, không dịch lại từ đầu. */
  retryJob: (jobId: string) =>
    request<{ job: TranslationJob }>(
      `/api/translate/jobs/${encodeURIComponent(jobId)}/retry`,
      { method: "POST", body: "{}" },
    ),

  listGlossary: (projectId: string) =>
    request<{ entries: GlossaryEntry[]; total: number }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/glossary`,
    ),

  addGlossaryEntry: (projectId: string, fields: {
    category: string; original: string; translated: string; note?: string;
  }) =>
    request<GlossaryEntry>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/glossary`,
      { method: "POST", body: JSON.stringify(fields) },
    ),

  updateGlossaryEntry: (projectId: string, termId: string, fields: {
    translated?: string; note?: string; locked?: boolean;
  }) =>
    request<GlossaryEntry>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/glossary/` +
        encodeURIComponent(termId),
      { method: "PATCH", body: JSON.stringify(fields) },
    ),

  deleteGlossaryEntry: (projectId: string, termId: string) =>
    request<{ deleted: boolean }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/glossary/` +
        encodeURIComponent(termId),
      { method: "DELETE" },
    ),

  importToDraft: (projectId: string, fields: {
    novelId?: string; newNovelTitle?: string;
  } = {}) =>
    request<{ novel_id: string; already_imported: boolean; chapters_created: number }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/import`,
      {
        method: "POST",
        body: JSON.stringify({
          novel_id: fields.novelId ?? "",
          new_novel_title: fields.newNovelTitle ?? "",
        }),
      },
    ),

  // ---------------------------------------------------------- Editor (Part N)

  getChapter: (projectId: string, chapterIndex: number) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/chapters/${chapterIndex}`,
    ),

  saveChapterEdit: (projectId: string, chapterIndex: number, newText: string) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/chapters/${chapterIndex}`,
      { method: "PUT", body: JSON.stringify({ new_text: newText }) },
    ),

  /** 409 (`ApiError.status === 409`) neu chuong da bi sua tay va `force` chua bat — hien
      `ConfirmDialog` roi goi lai voi `force: true`. */
  regenerateChapter: (projectId: string, chapterIndex: number, force = false) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/chapters/${chapterIndex}/regenerate`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),

  regenerateParagraph: (
    projectId: string, chapterIndex: number, paragraphIndex: number, force = false,
  ) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/chapters/` +
        `${chapterIndex}/paragraphs/${paragraphIndex}/regenerate`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),

  rerunPass: (
    projectId: string, chapterIndex: number,
    passType: "translator" | "editor" | "qa", force = false,
  ) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/chapters/${chapterIndex}/rerun`,
      { method: "POST", body: JSON.stringify({ pass_type: passType, force }) },
    ),

  // ---------------------------------------------------------- Lich su (Part O)

  listVersions: (projectId: string, chapterIndex?: number) =>
    request<{ versions: TranslationVersion[]; total: number }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/versions` +
        (chapterIndex === undefined ? "" : `?chapter_index=${chapterIndex}`),
    ),

  revertToVersion: (projectId: string, versionId: string) =>
    request<{ chapter: ChapterDetail }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/versions/` +
        `${encodeURIComponent(versionId)}/revert`,
      { method: "POST", body: "{}" },
    ),

  // ---------------------------------------------------------- Provider (Part Q)

  listProviders: () =>
    request<{ providers: ProviderCatalogEntry[]; total: number }>(
      "/api/translate/providers",
    ),

  updateProviderSettings: (projectId: string, fields: {
    providerMode?: "auto" | "manual";
    selectedProviderId?: string;
    allowFallback?: boolean;
    preferPersonalProvider?: boolean;
  }) =>
    request<{ project: TranslationProject }>(
      `/api/translate/projects/${encodeURIComponent(projectId)}/provider`,
      {
        method: "PATCH",
        body: JSON.stringify({
          provider_mode: fields.providerMode,
          selected_provider_id: fields.selectedProviderId,
          allow_fallback: fields.allowFallback,
          prefer_personal_provider: fields.preferPersonalProvider,
        }),
      },
    ),

  // ---------------------------------------------------------- BYOK (V5.1)

  listConnections: () =>
    request<{ connections: ProviderConnection[]; total: number }>(
      "/api/translate/provider-connections",
    ),

  /** Ket noi (hoac THAY THE) mot provider ca nhan. Nem `ApiError` voi
      `.code` la mot trong `ConnectionErrorCode` khi that bai — hien dung
      thong bao theo `.code`, khong doan tu `.message`. */
  connectProvider: (providerId: string, apiKey: string, selectedModel?: string) =>
    request<{ connection: ProviderConnection }>(
      `/api/translate/provider-connections/${encodeURIComponent(providerId)}`,
      {
        method: "POST",
        body: JSON.stringify({
          api_key: apiKey, selected_model: selectedModel ?? "",
        }),
      },
    ),

  testConnection: (providerId: string) =>
    request<{ connection: ProviderConnection }>(
      `/api/translate/provider-connections/${encodeURIComponent(providerId)}/test`,
      { method: "POST", body: "{}" },
    ),

  deleteConnection: (providerId: string) =>
    request<{ deleted: boolean }>(
      `/api/translate/provider-connections/${encodeURIComponent(providerId)}`,
      { method: "DELETE" },
    ),

};

/**
 * Image Studio V1 (overnight build) — export RIENG, cung khuon voi
 * `translate`/`social`, khong nhet vao `api` chung.
 */
export const imageStudio = {
  imageModels: () => request<ImageModelsResponse>("/api/image/models"),

  /** An danh, KHONG can dang nhap. Nhan hien thi CO DINH la "Quick Free"/
      "Auto model" — KHONG BAO GIO ten mot model rieng le (xem
      `docs/reports/pollinations-anonymous-probe-summary.md`: endpoint an
      danh bo qua/chuan hoa tham so model). */
  imageQuickFree: (prompt: string, aspectRatio: string, signal?: AbortSignal) =>
    request<ImageGenerationResult>("/api/image/quick-free", {
      method: "POST",
      body: JSON.stringify({ prompt, aspect_ratio: aspectRatio }),
      signal,
    }),

  imageSharedPremiumEstimate: (model: string, quality: string) =>
    request<{ estimated_credit_micro: number }>(
      "/api/image/shared-premium/estimate",
      { method: "POST", body: JSON.stringify({ prompt: "_", model, quality }) },
    ),

  imageSharedPremium: (params: {
    prompt: string; negativePrompt: string; model: string;
    aspectRatio: string; quality: string; idempotencyKey: string;
  }, signal?: AbortSignal) =>
    request<ImageGenerationResult>("/api/image/shared-premium", {
      method: "POST",
      body: JSON.stringify({
        prompt: params.prompt, negative_prompt: params.negativePrompt,
        model: params.model, aspect_ratio: params.aspectRatio,
        quality: params.quality, idempotency_key: params.idempotencyKey,
      }),
      signal,
    }),

  imageByop: (params: {
    prompt: string; negativePrompt: string; model: string;
    aspectRatio: string; quality: string;
  }, signal?: AbortSignal) =>
    request<ImageGenerationResult>("/api/image/byop", {
      method: "POST",
      body: JSON.stringify({
        prompt: params.prompt, negative_prompt: params.negativePrompt,
        model: params.model, aspect_ratio: params.aspectRatio,
        quality: params.quality,
      }),
      signal,
    }),

  imageWallet: () =>
    request<{ available_micro: number; reserved_micro: number; total_micro: number }>(
      "/api/image/wallet",
    ),

  imageByopStatus: () =>
    request<{ connected: boolean; scope: string; expires_at: string; byop_enabled: boolean }>(
      "/api/image/byop/status",
    ),

  imageByopConnect: () =>
    request<{ authorize_url: string }>("/api/image/byop/connect", { method: "POST" }),

  imageByopCallback: (state: string, code: string, redirectUri: string) =>
    request<{ connected: boolean; scope: string }>("/api/image/byop/callback", {
      method: "POST",
      body: JSON.stringify({ state, code, redirect_uri: redirectUri }),
    }),

  imageByopDisconnect: () =>
    request<{ connected: boolean }>("/api/image/byop/disconnect", { method: "POST" }),

  imageLibrarySave: (params: {
    generationId: string; prompt: string; negativePrompt: string; model: string;
    mode: string; aspectRatio: string; imageBase64: string;
  }) =>
    request<{ image_id: string }>("/api/image/library", {
      method: "POST",
      body: JSON.stringify({
        generation_id: params.generationId, prompt: params.prompt,
        negative_prompt: params.negativePrompt, model: params.model,
        mode: params.mode, aspect_ratio: params.aspectRatio,
        image_base64: params.imageBase64,
      }),
    }),

  imageLibraryList: () => request<{ images: SavedImageEntry[] }>("/api/image/library"),

  imageLibraryDelete: (imageId: string) =>
    request<{ deleted: boolean }>(
      `/api/image/library/${encodeURIComponent(imageId)}`, { method: "DELETE" },
    ),

  /** Cong Free — model cong dong Pollinations dang bao gia 0 pollen NGAY
      BAY GIO. `available: false` nghia la khong lay duoc danh sach (loi
      mang), KHAC voi `models: []` (lay duoc, nhung hien khong model nao
      mien phi — xem ADDENDUM, day la trang thai THAT co the xay ra). */
  imageCommunityFreeModels: () =>
    request<ImageCommunityFreeModelsResponse>("/api/image/community-free/models"),

  imageCommunityFree: (params: {
    prompt: string; negativePrompt: string; model: string;
    aspectRatio: string; quality: string; idempotencyKey: string;
  }, signal?: AbortSignal) =>
    request<ImageGenerationResult>("/api/image/community-free", {
      method: "POST",
      body: JSON.stringify({
        prompt: params.prompt, negative_prompt: params.negativePrompt,
        model: params.model, aspect_ratio: params.aspectRatio,
        quality: params.quality, idempotency_key: params.idempotencyKey,
      }),
      signal,
    }),
};

export interface ImageModelInfo {
  model_id: string;
  display_name: string;
  supports_text_to_image: boolean;
  supports_image_edit: boolean;
  quality_levels: string[];
  estimated_credit_cost: number;
}

export interface ImageModelsResponse {
  models: ImageModelInfo[];
  aspect_ratios: string[];
  shared_premium_available: boolean;
}

export interface ImageGenerationResult {
  image_base64: string;
  content_type: string;
  byte_size: number;
  provider_id: string;
  generation_id?: string;
  status?: string;
  estimated_cost_micro?: number;
  actual_cost_micro?: number | null;
}

export interface CommunityFreeImageModel {
  model_id: string;
  display_name: string;
  provider_badge: string;
  is_official: boolean;
  per_user_rpm: number | null;
  capabilities: string[];
  description: string;
  alpha_hint: string;
}

export interface ImageCommunityFreeModelsResponse {
  available: boolean;
  error: string;
  models: CommunityFreeImageModel[];
}

export interface SavedImageEntry {
  image_id: string;
  prompt: string;
  model: string;
  mode: string;
  aspect_ratio: string;
  created_at: string;
  url: string;
}

/** https://console.groq.com/keys — trang tao/quan ly API key Groq CA NHAN
    cua nguoi dung. Hang so RIENG (khong phai bien moi truong): day la mot
    URL cong khai, on dinh, cua chinh Groq, khong phai cau hinh trien khai. */
export const GROQ_CONSOLE_KEYS_URL = "https://console.groq.com/keys";

/** https://cloud.cerebras.ai — trang chu Cerebras Cloud Console (API Keys o
    thanh dieu huong trai sau dang nhap). KHONG co duong dan sau rieng cho
    trang API key duoc Cerebras cong bo chinh thuc (khac Groq co
    `/keys` on dinh) — dung goc de tranh 404 neu console doi giao dien, chi
    goc `/` la thu duy nhat Cerebras xac nhan on dinh. */
export const CEREBRAS_CONSOLE_KEYS_URL = "https://cloud.cerebras.ai";

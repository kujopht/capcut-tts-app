/**
 * CỜ TÍNH NĂNG của web — MỘT chỗ duy nhất (Social & Play V1).
 *
 * `MUSIC_ENABLED` — nhạc nền/danh sách nhạc/lời bài hát tạm ẩn cho tới khi chủ
 * dự án có kho nhạc mới. TẮT mặc định. Bật lại = build với
 * `NEXT_PUBLIC_MUSIC_ENABLED=1`, không phải viết lại mã:
 *
 *   * `lib/musicStore.ts` không phát, không tạo `AudioContext`/`<audio>`, không
 *     đăng ký kênh "ambient" với bộ điều phối tiếng, không lộ ra `window`;
 *   * không gắn `LiveLyricTicker` (layout), `DockSoundwaveFrame` (header),
 *     `SoundwaveMini` (thanh điều hướng);
 *   * trang Giải trí không có tab/đầu phát nhạc; `?tab=music` cũ rơi về game;
 *   * thẻ "Âm Nhạc" trên trang chủ đổi thành "Giải trí".
 *
 * KHÔNG xoá gì: tệp nhạc trong `public/`, danh sách bài, mã đầu phát vẫn còn
 * nguyên. Giọng đọc truyện, nghe thử Studio và audio trợ năng KHÔNG đi qua cờ
 * này — chúng không phải "nhạc".
 *
 * Giá trị đọc lúc BUILD (như `NEXT_PUBLIC_API_BASE`) — trình duyệt không bật
 * được bằng cách sửa localStorage.
 */
export const MUSIC_ENABLED = process.env.NEXT_PUBLIC_MUSIC_ENABLED === "1";

/**
 * `CHAT_V1_ENABLED` — tin nhắn 1:1 (Chat V1 trên Appwrite). TẮT mặc định: chưa bật thì KHÔNG có nút Tin
 * nhắn, nút "Nhắn tin" ở hồ sơ, khung chat, và `/messages` chỉ báo "chưa mở" — 0 request chat nào. Bật
 * cần CẢ HAI: build web với `NEXT_PUBLIC_CHAT_V1_ENABLED=1` VÀ máy chủ `FAS_CHAT_V1=1` (thiếu máy chủ thì
 * giao diện hiện lỗi trung thực `not_configured`). Nhờ vậy merge vào `main` rồi deploy web KHÔNG tự mở
 * một tính năng nửa vời trên production.
 */
export const CHAT_V1_ENABLED = process.env.NEXT_PUBLIC_CHAT_V1_ENABLED === "1";

/**
 * `AI_ASSISTANT_ENABLED` — Fanfic AI Assistant V1 (`/api/ai/*`, xem
 * `docs/` thiết kế nền móng). TẮT mặc định: chưa bật thì KHÔNG có nút mở trợ
 * lý (desktop lẫn mobile), không mục "Trợ lý AI" trong menu tài khoản, và
 * `/assistant` báo chưa mở — 0 request `/api/ai/*` nào rời trình duyệt.
 *
 * Bật cần CẢ HAI: build web với `NEXT_PUBLIC_AI_ASSISTANT_ENABLED=1` VÀ máy
 * chủ `FAS_AI_ASSISTANT_V1=1` (thiếu máy chủ thì `GET /api/ai/availability`
 * trả `enabled=false` và giao diện im lặng, không tự bật một tính năng
 * nửa vời trên production — cùng khuôn với `CHAT_V1_ENABLED`).
 *
 * Cờ bật cũng CHƯA đủ để vẽ lối vào: nút nổi / menu / lối vào trang truyện chỉ
 * hiện khi máy chủ xác nhận người đang đăng nhập thuộc khán giả
 * (`GET /api/ai/access`, xem `lib/ai/quyenTruyCap.ts`).
 *
 * Production: giá trị do `production-deploy.yml` truyền TƯỜNG MINH từ biến
 * GitHub `PRODUCTION_AI_ASSISTANT_ENABLED` / `PRODUCTION_AI_COMPANION_ENABLED`
 * (bắt buộc "0" hoặc "1"; thiếu/sai là workflow DỪNG) — một lần deploy tự động
 * sau không thể lặng lẽ đổi cờ.
 *
 * Tên/model provider KHÔNG BAO GIỜ lộ ra người dùng thường — chỉ tên hiển thị
 * (`availability.name`) và mode.
 */
export const AI_ASSISTANT_ENABLED = process.env.NEXT_PUBLIC_AI_ASSISTANT_ENABLED === "1";

/**
 * `AI_COMPANION_ENABLED` — linh vật Ink Scout đi cùng Trợ lý AI
 * (`components/ai/companion/`, `docs/ai/INK_SCOUT_COMPANION.md`). TẮT mặc định.
 *
 * Luôn đi SAU `AI_ASSISTANT_ENABLED`: trợ lý tắt thì linh vật tắt, bất kể cờ
 * này. Trợ lý bật + cờ này tắt = giao diện AI bình thường, không linh vật và
 * KHÔNG một byte mã/asset linh vật nào được TẢI: `loader` của cổng là `null`,
 * nên chunk lười (~3 KB gzip — Turbopack vẫn xuất tệp này ra thư mục build)
 * không bao giờ được yêu cầu; JS ban đầu chỉ thêm phần cổng nhỏ (đo: +153 B
 * gzip so với `main`). Bật = build với `NEXT_PUBLIC_AI_COMPANION_ENABLED=1`.
 */
export const AI_COMPANION_ENABLED =
  AI_ASSISTANT_ENABLED && process.env.NEXT_PUBLIC_AI_COMPANION_ENABLED === "1";

/**
 * `GAME_INK_SCOUT_ENABLED` — game hành động 2D "Ink Scout: The Lost Chapter" (`src/game/inkscout/`, `docs/games/INK_SCOUT_LOST_CHAPTER.md`).
 * TẮT mặc định; KHÔNG bật ở production khi chưa có chủ phê duyệt. Tắt thì: thẻ game không hiện ở trang Giải trí, route `/entertainment/ink-scout`
 * chỉ trả một thông báo tĩnh, và KHÔNG một byte mã game nào được tải (runtime chỉ `import()` khi người chơi bấm Chơi). Giá trị đọc lúc BUILD.
 * Bật = build với `NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED=1`.
 */
export const GAME_INK_SCOUT_ENABLED = process.env.NEXT_PUBLIC_GAME_INK_SCOUT_ENABLED === "1";

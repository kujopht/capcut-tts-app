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

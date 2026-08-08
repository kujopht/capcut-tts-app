/**
 * Giới hạn do MÁY CHỦ quyết định, chép lại ở đây để giao diện nói trước.
 *
 * MÁY CHỦ MỚI LÀ NƠI CƯỠNG CHẾ. Con số ở đây chỉ để người dùng biết trước khi
 * bấm Lưu, thay vì gõ xong ba nghìn chữ rồi nhận một lỗi 422. Sửa file này
 * không nới được giới hạn thật.
 *
 * Phải khớp với `MAX_CHAPTER_CHARS` trong `server/main.py`
 * (`FAS_MAX_CHAPTER_CHARS`). Có test Python đọc chính file này và so hai con
 * số — lệch là đỏ, nên không âm thầm trôi được:
 * `server/tests/test_limits.py`.
 */
export const MAX_CHAPTER_CHARS = 100000;

/** Bắt đầu cảnh báo khi còn cách trần 15%. */
export const WARN_RATIO = 0.85;

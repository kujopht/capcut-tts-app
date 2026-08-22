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

/**
 * Số chương tối đa trong MỘT lô nhập hàng loạt. Phải khớp `MAX_IMPORT_ITEMS`
 * trong `server/main.py` (`FAS_MAX_IMPORT_ITEMS`) — cùng cơ chế đối soát với
 * `MAX_CHAPTER_CHARS`, xem `server/tests/test_bulk_chapter_import.py`.
 *
 * Truyện dài hơn thì chia nhiều lô: các lô nối tiếp nhau đúng thứ tự vì lô sau
 * đọc `order_index` lớn nhất đang có.
 */
export const MAX_IMPORT_ITEMS = 500;

/**
 * Tổng số ký tự tối đa trong MỘT lô. Đây là giới hạn của một THÂN REQUEST, không
 * phải của Appwrite. Phải khớp `MAX_IMPORT_TOTAL_CHARS` trong `server/main.py`.
 */
export const MAX_IMPORT_TOTAL_CHARS = 5000000;

/**
 * Cạnh dài nhất của ảnh bìa truyện SAU khi xử lý, khớp
 * `CHINH_SACH_ANH["cover"].canh_toi_da` trong `server/social.py`. Cùng cơ chế
 * đối soát với `MAX_CHAPTER_CHARS` — xem `test_giao_dien_va_may_chu...` trong
 * `server/tests/test_limits.py`.
 */
export const MAX_COVER_EDGE = 1600;

/**
 * Cạnh dài nhất của avatar SAU khi xử lý, khớp
 * `CHINH_SACH_ANH["avatar"].canh_toi_da` trong `server/social.py`. Cùng cơ
 * chế đối soát — xem `test_giao_dien_va_may_chu...` trong
 * `server/tests/test_limits.py`.
 */
export const MAX_AVATAR_EDGE = 512;

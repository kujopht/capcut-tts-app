# VẤN ĐỀ SẢN PHẨM KẾ TIẾP — dữ liệu nội bộ lộ ra thẻ truyện công khai

Ghi nhận 2026-09-03 trong đợt Web Product Pass. **CỐ Ý KHÔNG sửa trong đợt
này** (đề bài loại trừ), ghi lại để làm việc kế tiếp.

## Hiện tượng

Trên `fanfic.world/fanfic` và trang chủ, cả **13 truyện đã xuất bản** đều hiện
dữ liệu nội bộ ra chỗ người đọc nhìn thấy đầu tiên:

- **Mô tả** là chuỗi provenance thô, không phải mô tả truyện:
  `Fandom: One Piece Nguồn: https://www.youtube.com/watch?v=ewAiT2hWo9w (kênh: vucthamaudio) B…`
- **Badge** hiện ID nội bộ: `work:OP-6e7aeb886f`, `work:CAT-0cd07945f7b7`
- **Badge** `imported`, `long_form_audio` — thuật ngữ vận hành, không phải thẻ
  cho người đọc
- Các thẻ nội bộ đó còn được đưa vào **hàng bộ lọc** ở `/fanfic`, nên người
  dùng được mời lọc theo `work:CAT-05770823184`

## Vì sao là vấn đề thật

Đây là mặt tiền của sản phẩm. Một thẻ truyện mà mô tả là URL YouTube thô đọc
như dữ liệu rò rỉ, không phải như một truyện đáng đọc — và nó chiếm đúng chỗ
mà mô tả thật phải nằm.

## Gốc rễ: DỮ LIỆU, không phải giao diện

Bộ nhập ghi provenance **vào ô `description`** của bản ghi Novel, và ghi ID
vận hành vào `tags`. Giao diện đang vẽ đúng những gì backend trả về.

Nên cách sửa đúng KHÔNG phải lọc chuỗi ở frontend (làm vậy sẽ che mất mô tả
thật của những truyện có mô tả tử tế, và vẫn để dữ liệu bẩn trong kho). Cần:

1. **Chuyển provenance sang trường riêng đã có**: `external_source_url`,
   `external_author_name`, `fandom_ids` — cả ba đã tồn tại trong `Novel` và
   đã được trang chi tiết truyện vẽ ra (đợt này đã làm). Không cần trường mới.
2. **Tách thẻ vận hành khỏi thẻ người đọc.** `work:*`, `imported`,
   `long_form_audio` không nên nằm cùng một danh sách với `Naruto`,
   `Romance`. Một tiền tố quy ước hoặc một trường riêng, và
   `GET /api/novels/tags` chỉ trả thẻ dành cho người đọc.
3. **Dọn 13 bản ghi hiện có** — một lần, có kiểm lại, không tự động.
4. Sửa bộ nhập để không tái tạo vấn đề.

## Ràng buộc

- 13 truyện này **đã công khai**; sửa dữ liệu là sửa nội dung đang phục vụ
  người thật. Phải có bước xem trước và đường hoàn tác.
- Không đổi `state` của truyện nào khi dọn dữ liệu.
- `fanficOnly()` ở `web/src/app/fanfic/page.tsx` là lớp phòng vệ, KHÔNG phải
  bộ lọc — đừng biến nó thành chỗ giấu dữ liệu bẩn.

## Kích cỡ ước lượng

Nhỏ ở frontend, trung bình ở dữ liệu. Việc thật nằm ở bước 1 và 3.

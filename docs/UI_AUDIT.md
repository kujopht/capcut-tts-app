# Báo cáo audit giao diện web

Chạy trên commit `57e1059`, backend chế độ `appwrite` + `r2` thật, đo trên DOM
thật bằng trình duyệt (không phải đọc code). Bảy trang, desktop 1440×900 và
mobile 390×844. Ảnh ở `docs/screenshots/audit/`.

Ghi lại đây vì bản gốc chỉ tồn tại trong hội thoại và đã một lần phải đào lại
từ transcript.

## Tình trạng xử lý

| Mã | Mức | Vấn đề | Trạng thái |
|---|---|---|---|
| H1 | 🟠 High | Trang tác giả tràn ngang trên mobile | ✅ `afea269` |
| H2 | 🟠 High | Trang chi tiết truyện có vấn đề N+1 | ✅ `15cbf71` |
| M1 | 🟡 Medium | Vùng bấm nhỏ hơn khuyến nghị trên mobile | ✅ lượt này |
| M2 | 🟡 Medium | Trang chi tiết truyện không nghe được tại chỗ | ✅ lượt này |
| M3 | 🟡 Medium | Không có cách sắp xếp lại thứ tự chương | ✅ lượt này |
| M4 | 🟡 Medium | Sửa nội dung chương không nhắc tạo lại audio đủ mạnh | ✅ lượt này |
| L1 | 🟢 Low | Ảnh bìa truyện chưa dùng | ✅ `afea269` |
| L2 | 🟢 Low | Chưa có phân trang, tìm kiếm chạy phía client | ⬜ chưa làm |
| L3 | 🟢 Low | Badge lịch sử ở Studio cập nhật trễ | ⬜ chưa làm |
| L4 | 🟢 Low | Vài giá trị màu hard-code | ⬜ chưa làm |

Ngoài danh sách trên, quá trình sửa H2 còn phát hiện và sửa thêm: lỗ hổng cho
người lạ đọc truyện nháp, `q_select` đặt sai khoá, và `list_chapters` mất chương
khi truyện quá 25 chương. Xem `docs/HANDOFF.md`.

## Phát hiện thêm khi làm M3–M4, CHƯA sửa

**Liên kết văn bản trong câu chỉ cao 17px.** Breadcrumb `← Khám phá Fanfic` ở
`/novels/[id]` và `← Hải Tặc Mũ Rơm` ở `/chapters/[id]` cao 17px ở khung 390px —
dưới cả mức 24×24 của WCAG 2.5.8. Không phát hiện ở lượt M1 vì phép đo lúc đó
chụp trang khi phần nội dung chính **chưa tải xong**, nên chỉ đo được các phần tử
trong header. Chúng là liên kết văn bản chứ không phải nút, nên cách sửa (thêm
`padding-block`, hoặc biến thành nút ở mobile) là một quyết định thiết kế riêng,
không thuộc phạm vi M3–M4.

---

## 🔴 Critical

Không có. Không lỗi nào làm mất dữ liệu, rò rỉ quyền, hay chặn luồng chính.

*(Ghi chú thêm sau: lỗ hổng đọc truyện nháp đúng ra thuộc mức này, nhưng audit
chỉ soi giao diện nên không phát hiện — nó lộ ra khi kiểm authorization lúc sửa
H2.)*

## 🟠 High

### H1 — Trang tác giả tràn ngang trên mobile

Đo tại 390px: `scrollWidth = 578px` so với khung `375px`. Trang cuộn ngang được,
mọi thẻ bị cắt cụt (thấy rõ ở `b7-write-mobile.png`).

Thủ phạm: `web/src/app/write/page.tsx:682` — `<select>` giọng đọc có
`style={{ width: "auto", minWidth: 200 }}` nằm trong `.row`, đẩy trang rộng thêm
203px. Đây là **chỗ duy nhất** trong toàn bộ code có kích thước cứng gây tràn
(đã grep hết).

Các trang khác ở 390px đều sạch: `/studio`, `/library`, `/novels/[id]`,
`/fanfic`, `/`, `/login` — `scrollWidth == 375`.

### H2 — Trang chi tiết truyện có vấn đề N+1

Một truyện 2 chương phát sinh **8 request API**, mỗi request **3,3–7 giây** với
Appwrite Cloud. Nguyên nhân: sau khi lấy `/novels/{id}`, trang gọi thêm
`/chapters/{id}` cho **từng chương** chỉ để biết chương đó đã có audio chưa.

Với truyện 50 chương thì thành 51 request. Và trang chỉ hiện skeleton cho tới
khi **tất cả** giải quyết xong — ảnh `a6` lần chụp đầu bắt đúng lúc đó.

Con số 8 gồm cả nhân đôi do React StrictMode ở chế độ dev; production sẽ là 4.
Nhưng bản chất N+1 vẫn còn.

Cùng vấn đề ở `/write` và `/library` (library còn gọi `getNovel` cho **mọi**
truyện).

## 🟡 Medium

### M1 — Vùng bấm nhỏ hơn khuyến nghị trên mobile

14 phần tử bấm được có chiều cao **28–39px** ở khung 390px (`btn-sm` = 32px,
`btn` = 39px, avatar = 28px). Hướng dẫn của Apple là 44×44, WCAG 2.5.8 mức AA là
24×24 — nên không vi phạm chuẩn, nhưng ở hàng chương của `/write` có 4 nút sát
nhau (`Tạo audio · Sửa · Xoá`) thì dễ bấm nhầm.

### M2 — Trang chi tiết truyện không nghe được tại chỗ

Chương hiện badge "Có audio" nhưng **không có nút phát**. Muốn nghe phải bấm vào
chương rồi mới thấy trình phát. Với người đọc muốn nghe lướt vài chương thì mất
thêm một bước mỗi lần.

### M3 — Không có cách sắp xếp lại thứ tự chương

Backend đã nhận `order_index` qua `PATCH /api/chapters/{id}`, nhưng giao diện ép
cứng `chapters.length + 1` và không có nút lên/xuống hay kéo-thả.

### M4 — Sửa nội dung chương không nhắc tạo lại audio đủ mạnh

Form sửa có cảnh báo dạng chữ, nhưng sau khi lưu thì badge vẫn là "Có audio" —
trong khi audio đang ứng với **nội dung cũ**. Người dùng dễ tưởng audio đã cập
nhật theo.

## 🟢 Low

### L1 — Ảnh bìa truyện chưa dùng
`cover_key` có trong dữ liệu nhưng mọi bìa vẫn là emoji 📖.

### L2 — Chưa có phân trang, tìm kiếm chạy phía client
`/fanfic` lọc trong trình duyệt trên toàn bộ danh sách. Đủ cho vài chục truyện,
không đủ cho vài nghìn.

### L3 — Badge lịch sử ở Studio cập nhật trễ
Trong lúc job chạy, khung "Tiến trình" hiện "Đang xử lý" còn thẻ trong "Lịch sử
audio" vẫn là "Đang xếp hàng" — lịch sử chỉ cập nhật khi job kết thúc.

### L4 — Vài giá trị màu hard-code
`page.tsx` đặt `--glow` bằng hex thay vì token (`#7c8cff3d`, `#4dd6c133`). Vô
hại nhưng lệch quy ước. Riêng `opengraph-image.tsx` buộc phải hard-code vì
Satori không đọc CSS variable.

---

## Nhất quán thiết kế — đạt

Đo trên DOM thật, không phải đọc code:

| Hạng mục | Kết quả |
|---|---|
| Cỡ chữ | Chỉ **5 giá trị**, đều từ thang token (15/13/12/18/25px) |
| Màu chữ | 8 giá trị, **tất cả** khớp token |
| Bo góc | 4 giá trị (10/14/999/6px), đều từ token |
| Button | 13 nút, **không nút nào** lách khỏi `.btn`/`.seg-item`/`.chip` |
| Chiều cao nút | Chỉ 2 mức: 32px (`btn-sm`), 39px (`btn`) |
| Loading/empty/error | Có đủ ở mọi trang có fetch; skeleton, empty state, error state kèm "Thử lại" |
| Toast | Một cơ chế duy nhất, `aria-live` |

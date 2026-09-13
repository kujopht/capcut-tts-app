# Rà soát đường dẫn công khai — khuyến nghị, CHƯA đổi

Ngày: 2026-09-13 · Phạm vi: 53 route dưới `web/src/app`

**Kết luận ngắn: KHÔNG đổi đường dẫn trong đợt này.** Lý do ở mục 4.

---

## 1. Hiện trạng

Giao diện tiếng Việt, đường dẫn tiếng Anh. Ba nhóm:

| Nhóm | Route | Ghi chú |
|---|---|---|
| **Khu vực duyệt** | `/`, `/fanfic`, `/animation`, `/community`, `/library`, `/leaderboard`, `/authors` | `/fanfic` mang nhãn "Khám phá" |
| **Tài nguyên** | `/novels/[id]`, `/chapters/[id]`, `/listen/[id]`, `/posts/[postId]`, `/u/[username]` | danh từ số nhiều, chuẩn REST |
| **Công cụ** | `/studio`, `/studio/{write,translate,audio,image,subtitle,library}` | đã gom ở #197 |
| **Quản trị** | `/admin/*` (25 route) | nội bộ, không index |
| **Kỹ thuật** | `/auth/callback`, `/image-studio/connect/callback` | OAuth callback |

## 2. Điểm thật sự lệch

1. **`/fanfic` mang nhãn "Khám phá."** Đường dẫn nói một đằng, nhãn nói một nẻo. Đây là chỗ lệch rõ nhất.
2. **`/image-studio/connect/callback`** còn sống ở đường dẫn CŨ, trong khi trang đã dời sang `/studio/image` (#197). Một địa chỉ OAuth mồ côi mang tên sản phẩm cũ.
3. **`/library` vs `/studio/library`** — hai "thư viện" khác nghĩa (người đọc / audio của người sáng tác). Đã tách đúng ở #200 nhưng tên vẫn trùng nhau.
4. Lẫn lộn số ít/số nhiều: `/novels/[id]` và `/chapters/[id]` (số nhiều) cạnh `/listen/[id]` (động từ).

## 3. Vì sao KHÔNG đổi bây giờ

- **`/fanfic` đã được chia sẻ thật.** `NavAuth.tsx` ghi rõ: *"giữ nguyên đường dẫn, chỉ mang nhãn Khám phá: đổi đường dẫn sẽ làm hỏng mọi liên kết đã chia sẻ."* Đó là quyết định đã cân nhắc, không phải nợ bỏ quên.
- **Đã có 5 chuyển hướng 308 vĩnh viễn** từ #197 (`/image-studio`, `/translate`, `/tools/subtitles`, `/write`, `/write/import`). Thêm một tầng nữa sẽ tạo chuỗi chuyển hướng, và 308 thì **không gỡ được** khỏi bộ nhớ đệm trình duyệt.
- **Lợi ích thẩm mỹ, rủi ro thật.** Người dùng không đọc đường dẫn; họ bấm liên kết. Đổi `/novels` → `/truyen` không làm ai đọc truyện dễ hơn.
- `/library` chỉ vừa đổi nghĩa ở #200 — đổi tiếp ngay là churn.

## 4. Khuyến nghị

**Bây giờ:** không đổi gì. Ghi nhận ở đây.

**Khi nào đáng làm** — gom vào MỘT đợt, không nhỏ giọt:

1. `/image-studio/connect/callback` → `/studio/image/connect/callback`. **Đây là việc đáng làm sớm nhất**: đường dẫn mồ côi mang tên sản phẩm cũ. Nhưng nó là **OAuth redirect URI đã đăng ký với nhà cung cấp** — đổi phía ứng dụng mà quên đổi phía nhà cung cấp là làm hỏng đăng nhập. Phải đổi hai nơi cùng lúc, nên không gộp vào một đợt giao diện.
2. Nếu có ngày chuyển sang đường dẫn tiếng Việt, đổi **một lần cho tất cả** (`/truyen`, `/chuong`, `/nghe`, `/thu-vien`), kèm 308 cho từng đường cũ và bài kiểm giữ tương thích — chứ không đổi lẻ tẻ từng route.
3. Giữ `/admin/*` và `/auth/*` nguyên trạng: nội bộ/kỹ thuật, không ai chia sẻ.

**Nguyên tắc:** một URL công khai là một lời hứa. Đổi nó phải trả giá bằng chuyển hướng vĩnh viễn, nên chỉ đổi khi thu lại được nhiều hơn thế.

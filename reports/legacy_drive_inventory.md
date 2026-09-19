# Báo Cáo Kiểm Toán Toàn Diện Kho Nội Dung Google Drive (Legacy Drive Inventory)

*Thời điểm kiểm toán: 2026-09-19 14:00:58 (Giờ hệ thống)*
*Chế độ vận hành: **READ-ONLY 100%** (Không tạo/xoá/sửa/di chuyển bất kỳ tệp nào trên Google Drive)*

## 1. Tổng Quan Kiểm Toán & Số Liệu Tổng Hợp

- **Tổng số thư mục / chương / tập đã kiểm toán**: **316** mục
- **Tổng dung lượng Audio phát hiện**: **31.59 GB**
- **Tổng dung lượng Text phát hiện**: **6.52 MB**
- **Thay đổi dữ liệu Production**: **0** (Tuyệt đối không can thiệp Database Production / Appwrite)

### Bảng Phân Loại Theo 7 Trạng Thái Nghiêm Ngặt

| Trạng thái (Category) | Số lượng | Dung lượng Audio | Dung lượng Text | Hành động định tuyến / Xử lý |
| :--- | :---: | :---: | :---: | :--- |
| **`READY_TEXT_AUDIO`** | **230** | 4544.5 MB | 6676.6 KB | Ưu tiên 1: Tái sử dụng nguyên vẹn cả Text tiếng Việt & TTS Audio. Không cần dịch hay sinh lại âm thanh. |
| **`READY_TEXT_ONLY`** | **0** | 0.0 MB | 0.0 KB | Ưu tiên 2: Tái sử dụng ngay phần Text tiếng Việt đã chuẩn hóa. Đẩy tác vụ TTS vào hàng đợi bất đồng bộ. |
| **`RAW_SOURCE`** | **0** | 0.0 MB | 0.0 KB | Ưu tiên 3: Nguồn thô chưa qua dịch/biên tập. Chuyển giao qua Gemini Translation Scheduler. |
| **`AUDIO_ONLY_EXTERNAL`** | **83** | 27801.6 MB | 0.0 KB | Cô lập nghiêm ngặt: Audio sách nói 5 tiếng từ YouTube/Facebook không có text chuẩn. KHÔNG nhập vào danh mục truyện chữ Fanfic. |
| **`AUDIO_GENERATED_UNMATCHED`** | **0** | 0.0 MB | 0.0 KB | Cách ly / Tạm giữ: Audio đã sinh nhưng thiếu mapping văn bản xác thực. |
| **`INCOMPLETE_OR_CORRUPT`** | **3** | 4.9 MB | 0.0 KB | Bỏ qua: Tệp nháp rỗng, tệp test tạm thời hoặc dữ liệu hỏng. |
| **`UNKNOWN`** | **0** | 0.0 MB | 0.0 KB | Cần can thiệp thủ công: Không xác định được cấu trúc. |

### Phân Bổ Theo Thư Mục Google Drive

| Khu vực Google Drive | Số lượng mục | Bản chất & Vai trò dữ liệu |
| :--- | :---: | :--- |
| `production/works/fanfic-tts` | 129 | Pipeline Fanfic nội bộ (Chuẩn Text Tiếng Việt + Audio CapCut/Piper) |
| `archive/old_fanfic_tts` | 103 | Kho lưu trữ Audio ngoài YouTube / Thử nghiệm cũ |
| `production/works/existing-audio` | 49 | Kho lưu trữ Audio ngoài YouTube / Thử nghiệm cũ |
| `archive/old_existing_audio` | 35 | Kho lưu trữ Audio ngoài YouTube / Thử nghiệm cũ |

## 2. Danh Sách Tác Phẩm Đạt Chuẩn Xuất Bản (`READY_TEXT_AUDIO`)

Toàn bộ các tác phẩm dưới đây do chính Pipeline nội bộ sinh ra, đầy đủ tệp `story_vi.txt`, `audio.mp3`, `transcript.json`, `metadata.json`:

| Tên Tác Phẩm | Khu vực lưu trữ | Số chương | Fandom | Trạng thái ghép cặp | Tệp thành phần |
| :--- | :--- | :---: | :--- | :---: | :--- |
| **[One Piece (Hải Tặc Vương)] HẢI TẶC - TỪ ROCKS PHÓ THUYỀN TRƯỞNG ** | `production/works/fanfic-tts` | 28 (Chương 1 → 28) | One Piece (Hải Tặc Vương) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] ĐỒNG NHÂN ONE PIECE - TRỌNG SINH PHÓ THUYỀN ROCKS, TA** | `production/works/fanfic-tts` | 19 (Chương 1 → 19) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Mộc Diệp - Thần Mộc Tái Sinh, Từ Đệ Tử Jiraiya Bắt Đầu C** | `production/works/fanfic-tts` | 18 (Chương 1 → 18) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Detective Conan (Thám tử lừng danh Conan)] DƯỚI TÀNG HOA ANH ĐÀO** | `production/works/fanfic-tts` | 16 (Chương 1 → 16) | Detective Conan (Thám tử lừng danh Conan) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Hoa Khôi Lớp Bên Và Bản Tình Ca Tháng Chín - Nhậ** | `production/works/fanfic-tts` | 15 (Chương 1 → 15) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact (Modern - School AU)] Thanh Xuân Là Bản Khảo Sát ** | `production/works/fanfic-tts` | 14 (Chương 1 → 14) | Genshin Impact (Modern - School AU) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu ** | `archive/old_fanfic_tts` | 11 (Chương 1 → 11) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Honkai - Star Rail] Nhật Ký Rung Động - Tôi Tình Cờ Nắm Giữ Bí M** | `production/works/fanfic-tts` | 7 (Chương 1 → 7) | Honkai - Star Rail | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter (Đồng Nhân)] Hogwarts - Thao Túng Chi Chủ — Bắt Đầu** | `production/works/fanfic-tts` | 4 (Chương 1 → 4) | Harry Potter (Đồng Nhân) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Dragon Ball (Bảy Viên Ngọc Rồng)] Long Châu - Cuồng Bạo Tái Sinh** | `production/works/fanfic-tts` | 3 (Chương 1 → 3) | Dragon Ball (Bảy Viên Ngọc Rồng) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact (Đồng Nhân)] Nguyên Tố Thứ Tám - Kẻ Nghịch Mệnh T** | `production/works/fanfic-tts` | 2 (Chương 1 → 2) | Genshin Impact (Đồng Nhân) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Dragon Ball (Bảy Viên Ngọc Rồng)] Dragon Ball - Cuồng Thần Trùng** | `production/works/fanfic-tts` | 2 (Chương 1 → 2) | Dragon Ball (Bảy Viên Ngọc Rồng) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Genshin - Bị Phong Ấn Thất Thần Lực, Ta Thức Tỉn** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Hải Tặc Chi Tuyệt Thế Kiếm Hào - Nhất Đao Trảm Đoán T** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Thần Thoại Khởi Nguyên, Bắt Đầu Thao Tú** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] HỎA ẢNH - KHAI CỤC LUÂN HỒI NHÃN, NGHỊCH THIÊN CỨU VỚT U** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Khai Mở Luân Hồi Nhãn, Đêm Diệt Tộc Ta Nghịch Mệnh Cứu U** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Mộc Diệp - Khởi Đầu Luân Hồi Nhãn, Ta Đạp Nát Kịch Bản D** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Kẻ Thao Túng Huyết Thống Cổ Đại** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Mộc Diệp Chi Luân Hồi - Ta Nghịch Chuyển Đêm Diệt Tộc Uc** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Kiếm Hào Vô Song, Bắt Đầu Rút Kiếm Tại Tân Thế Giới** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Thức Tỉnh Cổ Thần Huyết Mạch, Chiếc Nón** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Uchiha Chi Thần - Khai Cục Luân Hồi Nhãn, Đêm Diệt Tộc N** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Bleach] Thức Tỉnh Trảm Cổ Thần Binh, Ta Trọng Tái Thi Hồn Giới!** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Bleach | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Re - Zero kara Hajimeru Isekai Seikatsu] Re - Zero - Thái Cổ Ngh** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Re - Zero kara Hajimeru Isekai Seikatsu | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Jujutsu Kaisen (Chú Thuật Hồi Chiến)] Jujutsu Kaisen - Lãnh Địa ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Jujutsu Kaisen (Chú Thuật Hồi Chiến) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Genshin - Ngày Ta Thức Tỉnh Nguyên Tố Thứ Tám, C** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Trọng Sinh Tân Thế Giới, Ta Lấy Kiếm Khai Thiên** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Thức Tỉnh Huyết Thống Viễn Cổ, Ta Nắm G** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Khai Cục Thức Tỉnh Luân Hồi Nhãn, Ta Cứu Rỗi Gia Tộc Uch** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Khởi Nguyên Thứ Tám Khiến Thiên Lý Run Rẩy** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Từ Tân Thế Giới Trảm Ra Vô Song Kiếm Đạo** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Thao Túng Vận Mệnh Từ Huyết Thống Cổ Xư** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Khai Cục Luân Hồi Nhãn, Ta Nghịch Chuyển Diệt Tộc Chi Dạ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Bleach (Đồng Nhân)] Bleach - Thức Tỉnh Thái Cổ Ma Nhận, Ta Chấn ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Bleach (Đồng Nhân) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Re - Zero kara Hajimeru Isekai Seikatsu] Re - Zero - Nghịch Luân** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Re - Zero kara Hajimeru Isekai Seikatsu | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Jujutsu Kaisen (Chú Thuật Hồi Chiến)] Jujutsu Kaisen - Sở Hữu Lã** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Jujutsu Kaisen (Chú Thuật Hồi Chiến) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Thức Tỉnh Nguyên Tố Thứ Tám, Ta Khiến Thiên Lý K** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Trảm Tẫn Tinh Hải, Tân Thế Giới Vô Song Kiếm Hào!** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Cổ Huyết Thức Tỉnh, Kẻ Thao Túng Ngàn N** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Khai Cục Luân Hồi Nhãn, Nghịch Mệnh Cứu Gia Tộc Uchiha** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Bleach (Tử Thần)] Tử Thần - Thức Tỉnh Cổ Thần Đao, Ta Tái Lập Tr** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Bleach (Tử Thần) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Re - Zero - Đồng Nhân Light Novel] Re - Zero - Thái Cổ Cấm Kỵ - ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Re - Zero - Đồng Nhân Light Novel | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Chú Thuật Hồi Chiến (Jujutsu Kaisen)] Chú Thuật Hồi Chiến - Vô H** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Chú Thuật Hồi Chiến (Jujutsu Kaisen) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact (Nguyên Thần)] Nguyên Thần - Thức Tỉnh Nguyên Tố ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact (Nguyên Thần) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] HẢI TẶC - BÁT HOANG KIẾM TÔN — TA TẠI TÂN THẾ GIỚI ĐĂ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter - Đồng Nhân Harry Potter] Hogwarts - Thượng Cổ Huyế** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter - Đồng Nhân Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Konoha - Ta Mang Luân Hồi Nhãn Nghịch Mệnh Cứu Uchiha** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Konoha - Khởi Đầu Luân Hồi Nhãn, Nghịch Chuyển Đêm Diệt ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Genshin Impact] Genshin - Ngày Nhà Lữ Hành Thức Tỉnh Nguyên Tố T** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Genshin Impact | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Tuyệt Thế Kiếm Thần Băng Mũ Rơm** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Vương Tọa Lục Bảo - Cứu Thế Chủ Nghịch Mệnh Trọng ** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto (Đồng Nhân)] Hokage - Khai Cục Thức Tỉnh Song Thần Thuật,** | `archive/old_fanfic_tts` | 2 (Chương 1 → 2) | Naruto (Đồng Nhân) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece] Hải Tặc - Trọng Sinh Băng Rocks Phó Thuyền Trưởng, Bắ** | `production/works/fanfic-tts` | 1 (Chương 1) | One Piece | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Kẻ Thao Túng Huyết Mạch Cổ Đại** | `archive/old_fanfic_tts` | 1 (Chương 1) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Hogwarts - Huyết Thống Cổ Đại Chi Phối Vận Mệnh** | `archive/old_fanfic_tts` | 1 (Chương 1) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Đêm Trăng Máu, Ta Thức Tỉnh Luân Hồi Nhãn Cứu Vớt Uchiha** | `archive/old_fanfic_tts` | 1 (Chương 1) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[One Piece (Đảo Hải Tặc)] Hải Tặc - Trảm Đoạn Vận Mệnh, Cực Đạo K** | `archive/old_fanfic_tts` | 1 (Chương 1) | One Piece (Đảo Hải Tặc) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Khởi Đầu Luân Hồi Nhãn, Đêm Diệt Tộc Ta Nghịch Thiên Cứu** | `archive/old_fanfic_tts` | 1 (Chương 1) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Harry Potter] Vương Tọa Bạc Lục - Kẻ Thao Túng Vận Mệnh** | `archive/old_fanfic_tts` | 1 (Chương 1) | Harry Potter | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto (Đồng Nhân)] Huyết Nguyệt Chi Dạ - Thụ Giới Phá Diệt, Ma ** | `archive/old_fanfic_tts` | 1 (Chương 1) | Naruto (Đồng Nhân) | HIGH (100% Khớp) | Text, Audio, Sub, Cover |
| **[Naruto] Đêm Nghịch Mệnh - Huyết Đồng Tái Thế** | `archive/old_fanfic_tts` | 1 (Chương 1) | Naruto | HIGH (100% Khớp) | Text, Audio, Sub, Cover |

## 3. Danh Mục Audio Ngoài Đã Cô Lập (`AUDIO_ONLY_EXTERNAL`)

> [!IMPORTANT]
> Theo đúng định hướng của Phase B, các bản thu âm ngoài từ YouTube/Facebook dưới đây không có tệp văn bản truyện chữ chuẩn (`story_vi.txt`) và không trải qua chuẩn hóa câu. Chúng được **tách biệt hoàn toàn** khỏi danh mục truyện chữ của Fanfic World, không được tự ý import vào bảng `novels` / `chapters`.

| Tên Series Audio Ngoài | Số tập | Dung lượng Audio | Nguồn gốc | Ghi chú cô lập |
| :--- | :---: | :---: | :--- | :--- |
| [One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển | 11 tập | 3738.4 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất | 8 tập | 2485.3 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái | 7 tập | 1931.1 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Cô | 6 tập | 1397.2 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Fanfic] [Naruto x Genshin Impact (Crossover - Đồng Nhân)] Audio  | 6 tập | 1868.6 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ -  | 4 tập | 962.4 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ | 4 tập | 847.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạ | 3 tập | 820.0 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Doraemon (Đồng Nhân)] Doraemon - Toàn Vương Nobita Trấn Áp Chư T | 3 tập | 668.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Đô Thị Dị Năng - One Piece] Toàn Dân Thức Tỉnh - Trái Bóng Tối T | 3 tập | 558.7 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] 💥 Fanfic One Piece - Khởi Đầu, Ta Mắc Garp Và Luffy L | 3 tập | 295.4 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] Thế Giới Chi Vương - Đồng Nhân | 3 tập | 980.2 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] Orochimarus Disciple | 3 tập | 883.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] Gamer System Ch. 1–50 - Fanfic (Overpowered MC, Isekai) | 3 tập | 926.1 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto (Đồng Nhân)] [ Truyện Audio ] - Nhân Tại Naruto, Để Uchih | 1 tập | 428.0 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto - Genshin Impact] Audio Naruto Fanfic - Đóng Vai Zhongli  | 1 tập | 1868.6 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] [ Truyện Audio ] - Nhân Tại Naruto, Để Uchiha Lần Nữa Vĩ | 1 tập | 360.2 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto x Genshin Impact (Crossover - Đồng Nhân)] Audio Naruto Fa | 1 tập | 1868.6 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Harry Potter] và Hòn đá phù thuỷ - - Hành trình từ sân ga 9 ba p | 1 tập | 62.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Harry Potter] Sách nói - Harry Potter và hòn đá phù thủy. +4 (au | 1 tập | 71.1 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Harry Potter] Harry Potter và Phòng Chứa Bí Mật - Phần 02 | 1 tập | 968.5 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Harry Potter] và Hòn đá phù thuỷ - - Đứa bé vẫn sống - J.K. Rowl | 1 tập | 42.7 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [One Piece] One Piece Thế Giới Chi Vương - Đồng Nhân | 1 tập | 980.2 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto x Genshin Impact] Audio Naruto Fanfic - Đóng Vai Zhongli  | 1 tập | 866.0 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto (Crossover One Piece & Marvel)] Audio Naruto Fanfic - Xuy | 1 tập | 0.0 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] Gamer System Ch. 1–50 - Fanfic (Overpowered MC, Isekai)  | 1 tập | 926.1 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Harry Potter] và Hòn đá phù thuỷ - - Đứa bé vẫn sống - J.K. Rowl | 1 tập | 42.7 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Jujutsu Kaisen] MODULO - Chân Kiếm và Phục Hương, giương buồm ra | 1 tập | 13.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] [BL - ĐAM MỸ AUDIO ] [ĐN NARUTO] OBIKAKA] KAKASHI Ở THẾ  | 1 tập | 54.6 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |
| [Naruto] Orochimaru's Disciple - Phần 01 | 1 tập | 883.8 MB | YouTube Audiobook | Đã cách ly, không nhập vào text novel |

## 4. Danh Sách Tác Vụ Hỏng / Thiếu Tệp (`INCOMPLETE_OR_CORRUPT`)

Phát hiện **3** thư mục rỗng hoặc lỗi phát sinh trong quá khứ:

- `fanfic-gdrive:FanficWorld/archive/old_fanfic_tts/dogbertcarroll-let-it-ride-htm-w_4de1ca99c693fb298e1e`: Không tìm thấy text hay audio hợp lệ.
- `fanfic-gdrive:FanficWorld/archive/old_fanfic_tts/ignotus-always-know-where-your-towel-is-htm-w_48c964543a00b2bc476e`: Không tìm thấy text hay audio hợp lệ.
- `fanfic-gdrive:FanficWorld/archive/old_existing_audio/test-cloud-download`: Không tìm thấy text hay audio hợp lệ.
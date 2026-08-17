# Live Wallpaper V1 — Kiểm kê nền tĩnh hiện có

Trạng thái: **audit-only, KHÔNG sửa artwork gốc**. Ghi lại đúng những gì đang
tồn tại thật trong `web/public/artwork/fantasy-backgrounds/` (bộ nền đang
được `web/src/lib/backgrounds.ts` sử dụng thật — xem cột "Route" bên dưới,
lấy trực tiếp từ bảng `NEN`/`TEP` trong file đó) trước khi làm bất kỳ điều
gì với Live Wallpaper.

Có một bộ nền THỨ HAI, `web/public/artwork/backgrounds/fanfic_global_backgrounds_hd/`
— **không được tham chiếu ở bất kỳ đâu trong `web/src`** (đã `grep` xác
nhận). Đây là tài sản cũ/không dùng, không nằm trong phạm vi audit này.

## Bảng nền đang hoạt động (`fantasy-backgrounds/`)

Tất cả đều **1672×941px** (đúng tỉ lệ 16:9), mỗi ảnh có bản `.webp` đầy đủ và
một bản `-sm.webp` nhỏ hơn cho di động (chọn qua media query trong CSS, xem
`anhNen()`/`tenNen()` ở `backgrounds.ts`).

| Route/trang | File nguồn | Kích thước | Dung lượng đầy đủ | Dung lượng bản `-sm` | Cảnh chủ đạo | Vùng có thể hoạt hình | Vùng PHẢI giữ tĩnh | Dùng chung? | Ưu tiên Live Wallpaper |
|---|---|---|---|---|---|---|---|---|---|
| `/` (Home) | `01-home-sunny-harbor.webp` | 1672×941 | 436 KB | 151 KB | Vịnh biển nắng, lâu đài trên đồi, thuyền neo, mây | Mặt biển (sóng/phản chiếu), mây trôi, tán lá cây bên phải khung hình, thuyền/cờ đung đưa nhẹ | Lâu đài, kiến trúc thị trấn, cầu, núi, bố cục/khung hình tổng thể | Không — riêng cho Home | **CAO (Phase 9 bắt buộc — cảnh ĐẦU TIÊN)** |
| `/fanfic`, `/novels/*`, `/u/*` (Explore) | `02-explore-sky-kingdom.webp` | 1672×941 | 341 KB | 122 KB | Đảo nổi trên trời, lâu đài, chim/rồng bay | Mây trôi, chim bay xa, ánh sáng khí quyển | Đảo nổi, lâu đài, kiến trúc | Có — dùng chung cho 3 route | Trung bình (chưa nằm trong phạm vi đêm nay) |
| `/chapters/*` (Reader) | `03-reader-moonlit-shrine.webp` | 1672×941 | 384 KB | 130 KB | Đền thờ dưới trăng | — | Toàn cảnh (trang đọc ưu tiên tuyệt đối khả năng đọc, không nên có chuyển động nền) | Không | **THẤP — không nên làm sống động** (nội dung đọc dài, chuyển động nền gây mỏi mắt) |
| `/studio` (Audio Studio) | `04-studio-sky-workshop.webp` | 1672×941 | 473 KB | 159 KB | Xưởng làm việc trên trời | Mây, khói/hơi nước nhẹ | Kiến trúc xưởng, thiết bị | Không | Thấp |
| `/write`, `/creator/*`, `/admin` (Write) | `05-write-creators-room.webp` | 1672×941 | 392 KB | 132 KB | Phòng sáng tác | Ánh nến/đèn nhấp nháy rất nhẹ, rèm cửa | Bàn viết, kiến trúc phòng | Có — dùng chung 3 route (kể cả `/admin`, nơi KHÔNG nên có chuyển động trang trí — đây là bề mặt làm việc) | Thấp (và `/admin` nên loại trừ khỏi phạm vi Live Wallpaper vĩnh viễn) |
| `/library` (Library) | `06-library-arcane-archive.webp` | 1672×941 | 458 KB | 148 KB | Thư viện phép thuật/kiến trúc thiên văn | Ánh sáng cửa sổ kính màu, hạt bụi trong ánh sáng | Kệ sách, kiến trúc, đĩa thiên văn | Không | Thấp |
| `/account` (Account) | `07-account-blossom-realm.webp` | 1672×941 | 430 KB | 144 KB | Cảnh hoa anh đào | Cánh hoa rơi, mây | Kiến trúc, bố cục | Không | Thấp |
| `/login`, `/auth/*`, **mặc định** (Animation + Community hiện đang rơi vào đây do chưa có nền riêng) | `08-login-starlight-gate.webp` | 1672×941 | 339 KB | 107 KB | Cổng sao, bầu trời đêm | Sao lấp lánh, mây trôi, năng lượng cổng | Cổng, kiến trúc, núi | **Có — Animation VÀ Community đang dùng chung nền này** (xem `NEN` trong `backgrounds.ts`: hai route đó không khớp mẫu nào nên rơi vào `MAC_DINH = "auth"`) | Trung bình — nhưng ĐANG DÙNG CHUNG cho 3 đích khác nhau, nên làm sống động ở đây ảnh hưởng cả Animation/Community/Auth cùng lúc, cần cẩn trọng hơn |

## Kết luận phạm vi cho đêm nay (Phase 9)

Theo đúng chỉ thị: **CHỈ Home** (`01-home-sunny-harbor.webp`) nằm trong phạm
vi bắt buộc đêm nay. Không tự động chuyển đổi bất kỳ trang nào khác. Login
(`08-login-starlight-gate.webp`) là cảnh THỨ HAI tùy chọn, chỉ làm SAU KHI
Home đã qua được vòng duyệt chất lượng — và vì Home bị chặn ở bước sinh video
(xem báo cáo overnight), cảnh Login cũng không được thực hiện đêm nay.

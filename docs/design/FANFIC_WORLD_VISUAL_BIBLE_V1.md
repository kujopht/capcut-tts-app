# Fanfic World — Visual Bible V1

Trạng thái: **nền tảng cho `feature/fanfic-visual-renaissance-v1`**, viết trước
khi chạm vào bất kỳ trang nào ngoài trang chủ. Tài liệu này **mở rộng** hệ
token đã có trong `web/src/app/globals.css`, không thay thế nó — mọi giá trị
hex/màu hiện có (`--brand`, `--accent`, `--vang`, `--sac-*`, thang `--s*`,
`--r*`, `--dur*`) vẫn là nguồn sự thật; các token MỚI ở đây được thêm cạnh
chúng, cùng quy ước đặt tên tiếng Việt không dấu của file gốc.

Tài liệu tham khảo trực tiếp: `anthropics/skills/frontend-design/SKILL.md`
(nguyên tắc thiết kế) và `Leonxlnx/taste-skill` — `redesign-skill` (danh sách
kiểm AI-slop) và `imagegen-frontend-web` (kỷ luật bố cục/hình ảnh). Không có
gói nào được cài vào repo — chỉ đọc để lấy định hướng, như Phần 0 của yêu cầu
đã nêu rõ.

---

## 1. Ý tưởng thương hiệu

Fanfic World không phải một "công cụ TTS có thêm trang đọc truyện". Nó là
**một cổng vào thế giới hư cấu do cộng đồng dựng nên** — nơi một bộ truyện có
thể được đọc bằng mắt, nghe bằng tai, xem bằng Animation, và bàn luận cùng
người khác, tất cả trong cùng một "vùng đất". Mỗi khu vực chính (Trang chủ,
Khám phá, Animation, Audio, Đọc truyện, Cộng đồng, Sáng tác, Image Studio,
Hồ sơ) là một **quận (district)** riêng của thế giới đó, không phải một trang
dashboard SaaS đổi tên.

Câu định vị: *"Truyện của cộng đồng — đọc bằng mắt hoặc bằng tai, xem bằng
Animation, và được tạo ra bởi chính bạn."*

## 2. Khái niệm thế giới truyện — "Moonlit Storyworld"

Bầu trời đêm trăng, năng lượng huyền bí (tím/xanh lam) chảy qua các đường
viền như mạch phép thuật, và ánh sáng ấm (vàng đèn lồng) đánh dấu những gì
con người thật đã chạm vào (tác giả, bài viết, thành tựu). Đây **không** phải
một giao diện game nhập vai — không thanh HP, không khung gỗ giả trung cổ,
không font gothic. Chất fantasy đến từ **ánh sáng, độ sâu lớp, và chuyển động
kiệm lời**, không phải từ ốp da (skin) trang trí.

Ba trục hình ảnh giữ mọi trang lại với nhau:

- **Đêm trăng (navy/mist)** — nền tối có chiều sâu, không phẳng, không đen
  tuyền (`redesign-skill` gọi đúng bệnh: "Pure #000000 background").
- **Năng lượng huyền bí (tím→xanh lam)** — token `--brand`/`--accent` đã có,
  dùng cho hành động và trạng thái đang diễn ra (đang xem, đang phát, đang
  tải), KHÔNG dùng tràn lan cho trang trí tĩnh.
- **Ánh đèn lồng (vàng ấm)** — token `--vang` đã có, dùng cho dấu vết CON
  NGƯỜI THẬT: tác giả, huy hiệu, thành tựu, một câu trích. Quy tắc cũ của dự
  án ("không trang nào được phép nhìn vàng") vẫn đúng và được giữ nguyên ở
  đây — vàng là gia vị, không phải nước sốt.

## 3. Hệ màu (token — chỉ THÊM, không đổi giá trị cũ)

Token nền/màu hiện có (`--bg`, `--bg-1..3`, `--brand*`, `--accent*`, `--vang*`,
`--sac-*`, `--rarity-*`) giữ nguyên. Bổ sung cho hướng "Moonlit Storyworld":

```css
/* --- suong/ma (mist) — lop khi quyen giua nen va noi dung --- */
--mist-1: #1a1f3312;   /* rat mo, dat sau anh nen/artwork */
--mist-2: #2a2f4a1f;   /* dam hon, dung o vien section khi can tach lop */

/* --- muc/giay (ink/parchment) — CHI danh cho be mat doc truyen --- */
--ink: #12131c;         /* nen doc, am hon --bg-2 mot chut, khong phai giay that */
--ink-line: #2a2d3d;    /* gach chan chuong, KHONG dung --line (qua lanh) */
--parchment-whisper: #e8dfc84d; /* net vien SIEU mo o ria trang doc — 1 lan/chuong, khong lap lai moi doan */

/* --- bac (silver) — kim loai nguoi lon, danh cho Admin/Profile-codex --- */
--silver: #c7cede;
--silver-line: #c7cede3d;

/* --- vien nang luong (dung cho .nav-vach va cac khung dang-hoat-dong) --- */
--vien-phep: conic-gradient(from 0deg, transparent, var(--brand), var(--accent), transparent);
```

Quy tắc cứng: **không hex rời** trong component (`.tsx`) — quy tắc này đã có
test khoá (`social.test.mjs`, `motion-v2.test.mjs` quét `#[0-9a-f]{6}` trong
`NavIndicator.tsx`/`NavAuth.tsx`); mọi trang mới trong Renaissance phải tuân
theo, và bài test tương đương nên được viết cho từng trang khi triển khai.

## 4. Hệ chữ

Hiện trạng: `--font` là `ui-sans-serif, system-ui, "Segoe UI", ...` — không
có mặt chữ hiển thị (display face) nào, đúng như `redesign-skill` cảnh báo
("browser default fonts... headlines lack presence").

Quyết định (đối chiếu `frontend-design` SKILL — "typography carries the
personality of the page"):

| Vai trò | Mặt chữ | Dùng ở đâu | Lý do |
|---|---|---|---|
| **DISPLAY** | `Fraunces` (variable, có optical size) | `<h1>` Hero mỗi khu vực, số chương lớn, tiêu đề Animation series | Serif biên tập có cá tính nhưng KHÔNG "gothic trung cổ" — tránh đúng cái bẫy Phần J đã cấm |
| **BODY/UI** | Giữ `--font` hiện tại (system-ui stack) | Toàn bộ UI, nút, form, nav | Đã tối ưu cho tiếng Việt, đổi cả hệ thống là rủi ro không cần thiết |
| **ĐỌC TRUYỆN** | `Source Serif 4` hoặc giữ hệ thống nếu người dùng đã quen | Nội dung chương (`.chapter-body` hiện có) | Serif đọc dài hạn, không phải serif trang trí |
| **UTILITY** | `--font-mono` hiện có | Metadata, số liệu Admin, timestamp | Đã đúng, không đổi |

**Bắt buộc trước khi chốt bất kỳ mặt chữ nào**: kiểm tra trực tiếp trên trình
duyệt rằng đủ dấu tiếng Việt (ă, â, đ, ê, ô, ơ, ư và tổ hợp thanh điệu) không
bị vỡ/thiếu nét — đây là yêu cầu bắt buộc của Phần J, kiểm bằng cách render
một câu tiếng Việt có đủ dấu (ví dụ chính câu định vị ở Mục 1) trong DevTools
trước khi đưa vào `next/font`. Nếu `Fraunces`/`Source Serif 4` thiếu dấu nào,
rút về hệ thống hiện tại cho phần đó — không đánh đổi khả năng đọc lấy cá
tính.

Áp dụng qua `next/font` (self-host, không gọi Google Fonts runtime — khớp
"Backend web không được lộ bí mật ra ngoài" tinh thần chung của dự án: không
thêm phụ thuộc mạng ngoài cho một request tưởng như miễn phí).

## 5. Bề mặt & vật liệu

Token `--glass`, `--kinh`, `--kinh-vien`, `--kinh-sang`, `--do-sau*` đã có và
ĐÃ ĐÚNG hướng (kính có ranh giới rõ, không phải "sương mù"). Mở rộng:

- **Lớp sương (`--mist-1/2`)**: đặt SAU artwork nền, KHÔNG đặt trên
  `backdrop-filter` đã có — tránh chồng blur (taste-skill: "excessive nested
  filters" → Phần M đã cấm rõ).
- **Mực/giấy (`--ink`, `--parchment-whisper`)**: CHỈ dùng ở vùng đọc chương
  (Reader). Không lan sang Home/Explore — nếu không, cả site sẽ trông như
  đang giả trung cổ (chính là AI-slop mà taste-skill gọi "giả cổ điển cliché"
  cho toàn bộ UI, trong khi bản chất sản phẩm là đọc + nghe + xem hiện đại).
- **Bạc (`--silver`)**: chỉ Admin/Profile-codex — một điểm nhấn kim loại
  "người thật", tách biệt hẳn khỏi năng lượng phép thuật tím/lam.

## 6. Ánh sáng

Quy tắc kế thừa nguyên vẹn từ `--vang` hiện có: "một nguồn sáng nhất quán".
Mở rộng cho Renaissance:

- Mỗi khu vực có ĐÚNG MỘT "nguồn sáng ẩn dụ": Home = trăng phía sau các đảo
  nổi (đã có trong artwork nền); Explore = ánh sáng thư viện từ trên xuống;
  Animation = ánh chiếu máy chiếu; Audio = ánh sáng dịu phòng nghe đêm.
- Không bao giờ hai nguồn sáng cạnh tranh trong cùng một khung nhìn (taste-
  skill: "inconsistent lighting direction").
- `box-shadow`/`glow` LUÔN nhuộm theo hue của bề mặt đang đứng trên
  (`--brand-glow`/`--accent-glow`/`--vang-*` đã đúng mẫu này) — không dùng
  glow đen thuần hay glow không nhuộm màu.

## 7. Ngôn ngữ viền & hoạ tiết (ornament)

- **Viền năng lượng** (`.nav-vach`, và các khung "đang hoạt động" tương lai):
  dùng lại đúng kỹ thuật double-mask + `transform` đã xây ở Phase 1
  (`NavIndicator.tsx`) — không phát minh kỹ thuật viền mới cho mỗi tính năng.
- **Góc phép (corner rune)**: một hoạ tiết SVG góc, dùng RẤT hiếm — tối đa
  một lần mỗi màn hình, cho khung nội dung quan trọng nhất trên trang đó
  (ví dụ: thẻ truyện nổi bật duy nhất, không phải mọi thẻ). Vẽ tay bằng SVG
  path, không dùng icon font, không lấy biểu tượng từ franchise có sẵn (yêu
  cầu Phần G).
- **Đường chia (divider)**: một nét mảnh có gradient nhạt dần hai đầu
  (`linear-gradient(90deg, transparent, var(--line-strong), transparent)`),
  thay cho `<hr>` phẳng — rẻ, không cần SVG, đã đúng tinh thần "restrained".

## 8. Ngôn ngữ icon

Hiện trạng: bộ icon tự vẽ trong `Icons.tsx` (SVG nội bộ, KHÔNG phải Lucide
import hàng loạt) — đây đã là lựa chọn ĐÚNG theo `redesign-skill` ("Lucide
hoặc Feather icons exclusively" là dấu hiệu AI mặc định). Giữ nguyên chiến
lược này. Mở rộng:

- Icon tiện ích chung (mũi tên, đóng, tìm kiếm) → tiếp tục dùng bộ hiện có.
- Icon "chữ ký" cho 6 khu vực chính (Truyện/Animation/Audio/Cộng đồng/Sáng
  tác/Image Studio) → xét vẽ lại thành một bộ NHẤT QUÁN về stroke-width và
  cảm giác "vật thể phép thuật nhỏ" (cuốn sách phát sáng, cuộn phim có hào
  quang) thay vì icon Lucide-style phẳng — nhưng CHỈ khi Phase 3+ chạm tới
  lưới tính năng đó; không đổi icon ở nơi không nằm trong phạm vi phase.

## 9. Nhịp khoảng cách

Thang `--s1..--s8` (4px cơ số) đã đủ tốt và đã dùng nhất quán toàn site — giữ
nguyên 100%. Nguyên tắc mới cho Renaissance (theo `imagegen-frontend-web`
§12 "Density & Spacing Discipline"):

- Khoảng cách GIỮA các section lớn nên dùng `--s7`/`--s8`, không phải `--s4`
  — trang chủ hiện tại (trước Renaissance) đã hơi chật giữa các khối.
- Padding dọc không đối xứng khi có lý do quang học: đáy thường cần nhỉnh
  hơn đỉnh 15-20% để "trông cân" (mắt người bù trừ trọng lượng chữ phía trên).
- KHÔNG ép mọi thẻ trong một lưới cùng chiều cao bằng flexbox nếu nội dung
  lệch nhau tự nhiên (taste-skill: "cards of equal height forced").

## 10. Ngôn ngữ chuyển động

Quy ước đã có và PHẢI giữ nguyên tuyệt đối:

- `transform`/`opacity` là hai thuộc tính duy nhất được hoạt hình liên tục.
- Không `requestAnimationFrame` cho hiệu ứng trang trí (đo bằng
  `ResizeObserver`/CSS transition, xem `NavIndicator.tsx`).
- Mái `@media (prefers-reduced-motion: reduce)` toàn cục ép
  `animation-duration`/`transition-duration` gần 0 — mọi hoạt ảnh MỚI không
  được tự đặt `!important` đè lên mái này, và mọi phần tử "bị dịch chỗ" hay
  "vệt sáng lặp" phải có dòng tắt tường minh riêng (bài học đã ghi ở
  `globals.css`, không lặp lại lỗi "rút thời lượng chưa đủ").

Từ vựng chuyển động MỚI cho Renaissance (một khoảnh khắc dàn dựng, không
phải hai mươi hiệu ứng rời rạc — đúng tinh thần Phần H):

| Ngữ cảnh | Chuyển động | Ghi chú |
|---|---|---|
| Điều hướng route | Đã xong ở Phase 1: `.nav-vach` trượt + một vệt sáng một lần | Không đổi thêm |
| Thẻ nội dung (hover) | Nâng nhẹ (`translateY(-2px)`) + tăng viền sáng, KHÔNG scale (scale làm layout giật ở lưới sát nhau) | |
| Nội dung xuất hiện lần đầu | `.rise`/`.rise-1..3` đã có — tái dùng, không phát minh keyframe mới | |
| Ảnh lớn (Hero) | Parallax RẤT nhẹ (dịch nền chậm hơn foreground khi cuộn `<8px`) — CHỈ nếu đo được không giật trên máy yếu, có `will-change: transform` hạn chế phạm vi | Đánh giá per-page ở Phase 3, không bắt buộc |
| Hạt trang trí (`AmbientScene`) | Đã có, giữ nguyên kỷ luật "tối đa 10 phần tử/trang, viết tay toạ độ" | Mở rộng danh sách `ViTri` cho Animation/Community/Write/Image Studio ở Phase 4-7, theo đúng khuôn mẫu cũ |
| Modal/dialog | Scale nhẹ + fade (`modal-in` đã có) | Không đổi |

## 11. Xử lý hình ảnh

- Nền artwork hiện tại (đảo nổi, nhân vật) là tài sản gốc — giữ nguyên theo
  đúng yêu cầu "preserve current identity/background" của nhiệm vụ trước.
- Không chèn ảnh stock. Nơi cần hình mà chưa có tài sản thật: dùng SVG/CSS
  thay vì ảnh giữ chỗ (Phần G ưu tiên 1-2-3: tài sản có sẵn → SVG/CSS →
  procedural → chỉ generate ảnh khi công cụ thật sự sẵn có).
- Overlay/gradient LUÔN phục vụ khả năng đọc chữ trước, hiệu ứng thẩm mỹ sau
  — không overlay tối toàn trang nếu chỉ một vùng chữ cần tương phản.

## 12. Quy tắc trợ năng (accessibility)

Không đổi so với quy ước hiện có của site — Renaissance KHÔNG được hạ thấp:

- Mọi khung "đang chọn/đang focus" phải có `box-shadow`/viền đủ tương phản
  ở CẢ hai theme màu khu vực (`--sac-*`) lẫn khi `prefers-contrast: more`
  nếu trình duyệt hỗ trợ.
- `aria-current="page"`, `aria-labelledby` theo từng section — mẫu đã áp
  dụng ở Homepage Hub V2, tiếp tục dùng cho mọi trang mới.
- Không bao giờ dùng màu là tín hiệu DUY NHẤT (rarity, trạng thái) — luôn
  kèm chữ/icon, đúng thang `--rarity-*` đã thiết kế sẵn với nhãn text.

## 13. Reduced motion

Không tạo mái `prefers-reduced-motion` cục bộ mới cho bất kỳ trang nào —
LUÔN dựa vào mái toàn cục cuối `globals.css`. Với mỗi hiệu ứng mới thêm ở
Renaissance, checklist bắt buộc (rút từ bài học Phase 1):

1. Hoạt ảnh có `transform`/dịch chuyển vị trí? → cần dòng tắt tường minh
   (không chỉ dựa `animation-duration: 0.01ms`).
2. Hoạt ảnh lặp vô hạn (`infinite`)? → cần `display: none` tường minh dưới
   mái reduced-motion (xem tiền lệ `.progress-bar::after`, `.nav-vach-streak`).
3. Hoạt ảnh một lần, ngắn (`sheen`-style)? → mái toàn cục đã đủ (rút về gần
   như tức thời là chấp nhận được cho một hiệu ứng chỉ chạy một lần).

## 14. Nguyên tắc mobile

- Breakpoint đã dùng nhất quán: `900px` (gộp hàng header), `768px`, `640px`.
  Giữ nguyên, không thêm breakpoint tuỳ tiện.
- Vùng bấm tối thiểu 44px ở mobile — quy tắc `.btn, .btn-sm, .chip, ...` đã
  có ở `globals.css` (mục "vung bam ngon tay"); MỌI thành phần bấm được mới
  trong Renaissance phải được thêm vào đúng danh sách selector đó, không tạo
  quy tắc 44px rời rạc ở nơi khác (bài học đã rút ở Homepage Hub V2 — pill
  phụ trong Hero từng bị bỏ sót).
- Không thu nhỏ nguyên xi bố cục desktop — mỗi trang trong Phần E cần một
  bản dựng lại có chủ đích cho 390px, không phải một phép chia tỉ lệ.

## 15. Bản sắc riêng theo trang

Tổng hợp ngắn (chi tiết đầy đủ đã có ở yêu cầu gốc Phần E — không lặp lại ở
đây, chỉ ghi phần ÁP DỤNG THỰC TẾ vào hạ tầng đang có):

| Trang | Ẩn dụ | Tín hiệu thị giác chính | Hạ tầng tái dùng |
|---|---|---|---|
| Home | Cổng vào thế giới | Hero môi trường + `AmbientScene` "home" (đã có) | `.hero-v2*`, `AmbientScene` |
| Explore (`/fanfic`) | Thư viện/kho lưu trữ pháp thuật | `AmbientScene` "explore" (mây/chim, đã có) + thẻ dạng "hiện vật" | `.story-card`, cần bố cục biên tập mới |
| Animation | Rạp chiếu phim fantasy | Khung chiếu, ánh sáng máy chiếu — CẦN thêm `ViTri` mới vào `AmbientScene` | `.anim-card` đã có |
| Audio | Phòng nghe dưới trăng | Sóng âm nhẹ, bề mặt tĩnh hơn Home/Animation | `.tim-*`/player hiện có |
| Reader | Thánh đường đọc truyện | `--ink`/`--parchment-whisper` MỚI, ưu tiên tuyệt đối khả năng đọc | `.chapter-body` hiện có |
| Community | Bảng tin hội quán | Ghim bài, huy hiệu, không giả trung cổ lộ liễu | `.bai-dang` đã có |
| Write/Creator | Xưởng viết | Khung bản thảo, dòng chảy sáng tác | Editor hiện có |
| Image Studio | Phòng triệu hồi hình ảnh | Khung canvas, chọn mô hình rõ ràng, không glow tràn lan | UI hiện có |
| Profile | Codex nhân vật | Thẻ định danh, XP, thành tựu thật | `.ho-so-*`, `--rarity-*` |
| Auth | Cổng yên tĩnh | Tối giản, đẹp, không hiệu ứng thừa | `AmbientScene` "ngoai" (sao, đã có) |
| Admin | Chuyên nghiệp | CHỈ kế thừa màu/chữ/logo — không fantasy hoá | Không đổi kiến trúc hiện có |

---

## Việc KHÔNG làm ở đây (nhắc lại phạm vi)

Tài liệu này KHÔNG tự ý đổi màu/token đã tồn tại, KHÔNG code CSS/component
cho các trang Phase 3-8 — đó là việc của từng phase kế tiếp, mỗi phase có
checkpoint QA + commit riêng theo đúng Phần N của yêu cầu.

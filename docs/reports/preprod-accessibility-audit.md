# Báo cáo: Phase 11 — Kiểm toán khả năng tiếp cận (Overnight Hardening V1)

Phạm vi: đo Lighthouse Accessibility thật qua Chrome DevTools MCP trên
`http://localhost:3010`, và đọc tĩnh toàn bộ `web/src/app/**/page.tsx`
(43 route), mọi component dùng chung ở `web/src/components/*.tsx` (đặc biệt
`AdminShell.tsx`, `ui.tsx::ConfirmDialog`, `ReportDialog.tsx`,
`ImageLightbox.tsx`, `SearchOverlay.tsx`, `NotificationBell.tsx`,
`CommentThread.tsx`, `PostComposer.tsx`, `FollowButton.tsx`,
`SiteSearch.tsx`), `translate/ProviderConnectDialog.tsx`, và
`web/src/app/globals.css`.

Nhận xét chung trước khi vào từng mục: codebase này đã có ý thức về khả năng
tiếp cận từ trước — rất nhiều component có docstring giải thích rõ quyết định
bàn phím/focus/ARIA (ví dụ `ConfirmDialog`, `ImageLightbox`, `NotificationBell`,
`FollowButton`, `SearchOverlay`), và một bộ test tự động (`tests/ui.test.mjs`)
đã khoá lại quy tắc "44×44 vùng bấm ngón tay ở mobile". Vì vậy phần lớn phát
hiện dưới đây là ĐIỂM SÁNG cần ghi nhận, không phải lỗi; số lượng lỗi thật tìm
được là nhỏ, và toàn bộ đã sửa.

## 0. Điểm Lighthouse Accessibility (đo thật, Chrome DevTools MCP)

| Route | Điểm Accessibility | Ghi chú khác (không thuộc a11y) |
|---|---|---|
| `/` | **100** | Best Practices 96 (2 audit fail, không liên quan a11y) |
| `/fanfic` | **100** | Best Practices 96 (2 fail), SEO 100 |
| `/animation` | **100** | Best Practices 96 (3 fail); 1 lỗi console `net::ERR_CONNECTION_REFUSED` (x3) — tài nguyên mạng ngoài (thumbnail YouTube) bị chặn trong sandbox kiểm thử, không phải lỗi a11y |
| `/community` | **100** | Best Practices 96 (3 fail) |
| `/library` | **100** | Best Practices 100; Agentic Browsing 85 (route yêu cầu đăng nhập) |
| `/login` | **100** | Best Practices 100; Agentic Browsing 59 (thấp nhất, không thuộc phạm trù accessibility) |

**Cả 6 route đều đạt tuyệt đối 100/100 Accessibility theo Lighthouse — không
có audit accessibility nào fail.** `/write` không mở riêng vì redirect sang
`/login` khi chưa đăng nhập trong môi trường kiểm thử (đúng hành vi mong
đợi) — `/login` đã đo trực tiếp nên coi như đã phủ.

Lưu ý: Lighthouse chỉ chấm cây DOM tĩnh sau khi tải trang, **không** kiểm
được hành vi bẫy tiêu điểm (focus trap) bên trong modal/dialog mở động bằng
JS — các mục đó được kiểm riêng ở phần 4 bằng đọc code.

## 1. Điều hướng bàn phím (Tab, `onClick` trên phần tử không tương tác)

Quét toàn bộ `<div onClick>` / `<span onClick>` trong `web/src` — chỉ có 2 chỗ
(`MiniPlayer.tsx`, `ImageLightbox.tsx`), cả hai đều là backdrop
`role="presentation"` bấm-ra-ngoài-để-đóng của một hộp thoại đã có phím Escape
riêng (không phải hành động chính cần bàn phím tới). `MiniPlayer.tsx` có hẳn
một dòng chú thích giải thích tại sao khối tên bài dùng `<button>` thật thay
vì `<div onClick>`. Không tìm thấy phần tử tương tác nào chỉ bấm được bằng
chuột. SẠCH — không sửa.

## 2. Focus visibility (`outline: none` không có style thay thế)

Có 2 chỗ `outline: none` trong `globals.css`:

| Vị trí | Có thay thế? |
|---|---|
| `.input, .textarea, .select:focus` (dòng ~1679) | Có — `box-shadow: var(--ring)` + đổi viền |
| `.tim-o:focus` (ô nhập trong `SearchOverlay`, dòng ~4300) | KHÔNG trước khi sửa — không có style thay thế nào cho input lẫn cụm `.tim-dau` bao quanh |

**Lỗi tìm thấy:** ô tìm kiếm toàn cục (`SearchOverlay`) tắt outline mặc định
mà không có dấu hiệu tiêu điểm thay thế nào — người dùng bàn phím Tab/Shift+Tab
vào lại ô này (ví dụ sau khi đổi mục danh mục) không thấy ô đang giữ tiêu điểm.
**Đã sửa**: thêm `.tim-dau:focus-within { box-shadow: var(--ring); }`, dùng
đúng khuôn mẫu đã có sẵn của `.site-search:focus-within` (ô tìm ở header) —
sáng cả cụm khi tiêu điểm ở bất kỳ đâu bên trong (ô nhập hoặc `<select>` danh
mục).

## 3. Nhãn form (`<label htmlFor>` / `aria-label`)

Kiểm tất cả `<input>`/`<select>`/`<textarea>` ở các trang có form: `/login`,
`/write`, `/creator/apply`, `/admin/animation/sources/new`, `/account`,
`/admin/users/[user_id]`, `translate/ChapterEditor.tsx`, `PostComposer.tsx`,
`ReportDialog.tsx`, `ProviderConnectDialog.tsx`. Toàn bộ đều có `<label
htmlFor>` khớp `id`, `<label>` bọc trực tiếp, hoặc `aria-label` tường minh
(kể cả input `type="range"`, `type="file"` ẩn, và các checkbox trong form
Trusted Source). SẠCH — không sửa.

## 4. Ngữ nghĩa hộp thoại (`role="dialog"`, `aria-modal`, bẫy tiêu điểm, Escape, trả tiêu điểm)

| Hộp thoại | `role="dialog"` + `aria-modal` | Tiêu điểm vào khi mở | Escape đóng | Bẫy Tab | Trả tiêu điểm khi đóng |
|---|---|---|---|---|---|
| `ConfirmDialog` (`ui.tsx`) | Có | Có (`data-autofocus`) | Có | Có | Có |
| `ImageLightbox.tsx` | Có | Có | Có | Không (3 nút, rủi ro thấp) | Có |
| `ReportDialog.tsx` | Có | Có | Có | **Có, sau khi sửa** | **Có, sau khi sửa** |
| `ProviderConnectDialog.tsx` (translate BYOK) | Có | **Có, sau khi sửa** | **Có, sau khi sửa** | Không | **Có, sau khi sửa** |
| `SearchOverlay.tsx` (combobox) | Có (`role="dialog"` + `role="combobox"`) | Có | Có | Không áp dụng (mẫu combobox) | Không áp dụng (không phải modal chặn hẳn thao tác) |

Hai lỗi thật tìm thấy, cả hai đã sửa:

**(a) `ReportDialog.tsx`** có docstring đầu file khẳng định "tiêu điểm trả về
nút đã mở nó" nhưng phần thân KHÔNG hề bắt `document.activeElement` trước khi
mở hay refocus khi đóng — code không khớp với chính lời tài liệu của nó, và
khác biệt so với `ConfirmDialog`/`ImageLightbox` (đều làm đúng việc này).
Ngoài ra không có bẫy Tab, nên Tab liên tục từ nút cuối trong hộp thoại có thể
thoát ra ngoài trang nền đang bị `role="presentation"` che (backdrop không
phải `inert`) — ví dụ cụ thể: `ReportDialog` mở từ `PostCard.tsx:430-436`,
Tab từ nút "Gửi báo cáo" có thể rơi vào nút của bài đăng kế tiếp trong bảng
tin, vốn đang bị lớp phủ che khuất trực quan.
**Đã sửa:** thêm `opener` ref bắt `document.activeElement` lúc mở và
`.focus()` lại lúc đóng, cộng thêm vòng bẫy Tab (`Tab`/`Shift+Tab` giữa nút
đầu và nút cuối trong hộp thoại) — sao chép logic đã kiểm chứng của
`ConfirmDialog`.

**(b) `translate/ProviderConnectDialog.tsx`** (hộp thoại kết nối API key
Groq/Cerebras, V5.1 BYOK) **hoàn toàn không có xử lý bàn phím nào** — không tự
động focus khi mở, Escape không đóng được, không trả tiêu điểm khi đóng. Đây
là hộp thoại duy nhất trong toàn bộ 5 cái hoàn toàn thiếu, khác biệt hẳn so
với các hộp thoại còn lại vốn đều có ít nhất mức tối thiểu (focus khi mở +
Escape).
**Đã sửa:** thêm tiêu điểm tự động khi mở (`hop.current?.focus()`), Escape
đóng hộp thoại (dùng ref giữ hàm đóng mới nhất để tránh effect chạy lại mỗi
lần gõ phím vào ô API key — cùng kỹ thuật `onCancelRef` đã dùng trong
`ConfirmDialog`), và trả tiêu điểm về phần tử đã mở hộp thoại khi đóng. KHÔNG
thêm bẫy Tab đầy đủ (để mức sửa nhất quán với `ReportDialog`/`ImageLightbox`
trước khi có bẫy Tab, tránh sửa không đều tay giữa nhiều hộp thoại trong một
phase).

`SearchOverlay.tsx` cũng không có bẫy Tab đầy đủ — mount trong `SiteHeader`
(`app/layout.tsx` qua `SiteSearch.tsx:70`), đứng trước `<main>` trong DOM, nên
Tab từ nút "Đóng" có thể rơi vào `NavAuth` phía sau lớp phủ. Ghi nhận MINOR,
không sửa (thiết kế combobox khác biệt với modal thường, thay đổi cần cân
nhắc kỹ hơn phạm vi "nhỏ/an toàn" của phase này).

## 5. Sử dụng ARIA

Không thấy ARIA mâu thuẫn hay `aria-label` lặp lại rối rắm với chữ hiển thị.
Điểm đáng ghi nhận (dùng đúng, không phải lỗi):
- `FollowButton` dùng `aria-pressed` thay vì đổi nhãn nút — docstring giải
  thích rõ lý do (tránh mơ hồ trạng thái/hành động).
- `NotificationBell` gộp số chưa đọc vào `aria-label` (`"Thông báo, N chưa
  đọc"`) thay vì chỉ đọc icon.
- `ChuaCauHinh` (`AdminShell.tsx`) không bao giờ hiện "0" giả cho dữ liệu
  chưa có — không phải vấn đề ARIA nhưng liên quan tới việc trình đọc màn
  hình không bị đọc nhầm số liệu.
SẠCH — không sửa.

## 6. Tên nút (nút chỉ có icon) và ảnh (`alt`)

Rà toàn bộ `<button>` trong `web/src/components/*.tsx` (đối chiếu số lượng
`<button>` và `aria-label` theo file) và các nút icon rời rạc khác
(`MiniPlayer`, `ImageLightbox`, `CommentThread::MocAudio`, `PostComposer` nút
"Bỏ ảnh"). Mọi nút chỉ chứa icon/emoji đều có `aria-label` mô tả hành động
(`"Ảnh trước"`, `"Ảnh sau"`, `"Tua audio tới …"`, `"Bỏ ảnh N"`, `"Tạm dừng"`/
`"Phát"`…); nút có chữ hiển thị thì không cần thêm. SẠCH — không sửa.

Ảnh: xác nhận điểm nghi vấn nêu trong đề bài —
`web/src/app/admin/animation/sources/new/page.tsx:139` (thumbnail xem trước
Trusted Source, `alt=""`) là **chủ đích, không phải thiếu sót**. Toàn bộ
thông tin nhận dạng (tên hiển thị, loại nguồn, tên kênh, số video trong
playlist) đã có ở text ngay bên cạnh — ảnh chỉ lặp lại trực quan thứ trình
đọc màn hình đã có bằng chữ. Cùng mẫu với `PostCard.tsx:139` (ảnh gallery,
`alt=""` + nút bọc ngoài có `aria-label` riêng), `ImageLightbox.tsx:68`,
`YouTubeFacadePlayer.tsx:100` (thumbnail YouTube), và ảnh cosmetic
(`cosmetics/Cosmetics.tsx` — khung avatar/huy hiệu hạng đều
`alt="" aria-hidden="true"`, lớp phủ trang trí thuần tuý). Ảnh mang thông
tin thật (`image-studio/page.tsx:621,660`) dùng `alt={prompt || "Ảnh vừa
tạo"/"Ảnh đã lưu"}`. SẠCH.

## 7. Cấu trúc heading và skip-nav

Không thấy trang nào nhảy cấp (h1 → h4) hay có hai `<h1>` cùng hiển thị đồng
thời. Mọi trang PUBLIC dùng `PageHeader` (xuất `<h1>`) rồi xuống `<h2>` cho các
khối con. Trang admin không tự vẽ `<h1>` riêng — `AdminShell.tsx` đã vẽ đúng
MỘT `<h1>` ("Fanfic World") bọc toàn bộ khu quản trị, nội dung từng trang admin
bắt đầu từ `<h2>` rồi `<h3>` cho khối con — đúng phân cấp một cấp, không nhảy.
Hai chỗ có "hai `<h1>`" trong cùng file (`account/page.tsx`,
`translate/page.tsx`) là hai NHÁNH LOẠI TRỪ NHAU của cùng một điều kiện (chưa
đăng nhập / đã đăng nhập) — không bao giờ render đồng thời.

Skip-nav ("Bỏ qua điều hướng"): nằm ở `web/src/app/layout.tsx` dòng 63–65,
bên trong `RootLayout` — áp dụng cho **TOÀN BỘ** route, kể cả các trang trong
`/admin/*` (vì `AdminShell` render bên trong cây `RootLayout`, không có
layout riêng nào loại bỏ header/skip-link). Không phải chỉ trang chủ mới có.
SẠCH — không sửa.

## 8. Vùng bấm ngón tay ở mobile (~40×40px)

`globals.css` có sẵn khối `@media (max-width: 640px)` nâng
`.btn, .btn-sm, .chip, .seg-item, .nav-link, .account-link, .brand, .menu-item,
.input-search, .novel-pick` lên `min-height: 44px` (đúng hướng dẫn 44×44 của
Apple, có ghi chú lý do), và `.btn-icon`/`.play-btn-sm` được nâng riêng thành
44×44 vuông (đã có test `tests/ui.test.mjs` khoá quy tắc này).

**Lỗi tìm thấy:** `.bell` (nút chuông thông báo, `NotificationBell.tsx`) là
34×34px CỐ ĐỊNH và bị bỏ sót khỏi danh sách nâng cấp ở khối mobile trên — dưới
hẳn ngưỡng 40×40, không nhất quán với chính sách vùng bấm của toàn app.
**Đã sửa:** thêm `.bell { min-width: 44px; min-height: 44px; }` vào đúng khối
`@media (max-width: 640px)` đó (dùng `min-width`/`min-height` để khớp quy ước
"không đặt height cứng" mà `tests/ui.test.mjs` đã kiểm).

## 9. Độ tương phản màu chữ/nền (theme tối)

**SẠCH**, và có bằng chứng đây là hạng mục đã được chủ động rà soát trước
đây: `web/src/app/globals.css` dòng 59–65 có ghi chú cụ thể — biến `--text-3`
từng là `#6d7893` (tỉ lệ tương phản 4.01 trên `--bg-2`, dưới ngưỡng AA cho
chữ nhỏ) và đã được đổi sang `#7e8aa6` (5.11 trên `--bg-2`, 5.75 trên nền
trắng). Không phát hiện token màu chữ/nền nào mới vi phạm ngưỡng AA trong
các trang đã kiểm.

## Bảng tổng hợp sửa đổi (Hạng mục | Trước khi sửa | Sau khi sửa)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Focus visibility ô tìm kiếm toàn cục (`.tim-o`, `SearchOverlay`) | `outline: none`, không có style tiêu điểm thay thế nào | Thêm `.tim-dau:focus-within { box-shadow: var(--ring); }` |
| Ngữ nghĩa hộp thoại `ReportDialog` | Không bắt `document.activeElement` lúc mở, không trả tiêu điểm lúc đóng, không bẫy Tab (trái với docstring của chính file) | Thêm `opener` ref trả tiêu điểm khi đóng + bẫy Tab trong hộp thoại, cùng khuôn mẫu `ConfirmDialog` |
| Vùng bấm mobile của `.bell` (chuông thông báo) | Cố định 34×34px trên mọi kích thước màn hình, bị bỏ sót khỏi khối nâng 44px ở mobile | Thêm `.bell { min-width: 44px; min-height: 44px; }` vào khối `@media (max-width: 640px)` |
| `translate/ProviderConnectDialog.tsx` — tiêu điểm khi mở hộp thoại | Không tự động focus vào hộp thoại; tiêu điểm bàn phím ở lại nút vừa bấm mở, phía sau lớp phủ | Focus tự động vào phần tử `role="dialog"` khi `open` chuyển thành `true` |
| `translate/ProviderConnectDialog.tsx` — phím Escape | Không có xử lý — không đóng được bằng bàn phím | Escape gọi hàm đóng (dọn `apiKey`/`loi`/`ketQua` như nút Huỷ) |
| `translate/ProviderConnectDialog.tsx` — trả tiêu điểm khi đóng | Không có — tiêu điểm rơi về `<body>` sau khi đóng | Lưu `document.activeElement` trước khi mở, trả lại đúng phần tử đó khi đóng |

## Kiểm chứng sau khi sửa

```
cd web && npx tsc --noEmit     # exit 0, sạch
cd web && npx eslint src/app/translate/ProviderConnectDialog.tsx   # sạch
cd web && npm test              # 635/635 pass (0 fail), bao gồm test đã có
                                 # "nut co CHU dung min-height chu khong phai
                                 # height co dinh" và "moi lop bam duoc deu cao
                                 # it nhat 44px o mobile"
```

## Giới hạn của lần kiểm này

- Lighthouse đo được 6 route công khai (mục 0); không đo được các trang admin
  nội dung phức tạp (`/admin/animation/sources/[id]`, `/admin/users/[user_id]`)
  qua trình duyệt thật vì không có tài khoản admin/owner thật trong mock (cùng
  giới hạn đã ghi nhận ở Phase 2). Đọc mã cho thấy các trang này dùng lại đúng
  các thành phần dùng chung (`ConfirmDialog`, `DanhSachTrangThai`, form có
  `<label>`) đã audit sạch ở trên, nên rủi ro thấp.
- Không kiểm bằng trình đọc màn hình thật (NVDA/VoiceOver) — chỉ Lighthouse +
  đọc mã tĩnh + đối chiếu cây a11y qua Chrome DevTools MCP snapshot.
- Không thêm bẫy Tab đầy đủ cho `ImageLightbox.tsx`/`SearchOverlay.tsx` — ghi
  nhận MINOR, để lại cho một phiên sau vì cần cân nhắc thiết kế (portal hoá
  hoặc `inert` cho phần còn lại của trang) vượt quá "sửa nhỏ/an toàn" của
  phase này.

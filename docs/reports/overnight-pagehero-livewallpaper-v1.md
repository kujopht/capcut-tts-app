# Overnight Marathon — Themed Page Hero V1 + Live Wallpaper V1

Trạng thái: **HOÀN THÀNH MỘT PHẦN, có blocker rõ ràng.** Themed Page Hero V1
và bảo toàn Animation Player V2 **XONG, đã deploy staging**. Live Wallpaper
V1 **CHỈ hoàn tất phần kiến trúc** — bước sinh video thực tế bị chặn (xem
mục 16-17). Theo đúng quy tắc đã nêu ("nếu bị chặn thì không được tự nhận
hoàn tất, không được tắt máy"), marathon này **KHÔNG** được coi là 100%
xong, và máy **KHÔNG** bị tắt.

## 1. Nhánh/SHA khởi điểm

`feature/fanfic-visual-renaissance-v1` @ `87d0ba779fcc448ead7ae3bd354080c272d99207`
("Khôi phục Animation Player V2..."), khớp `origin`, working tree sạch tại
thời điểm bắt đầu.

## 2. Kiểm kê stash (trước khi động vào bất cứ thứ gì)

```
stash@{0}: On feature/fanfic-visual-renaissance-v1: WIP: Themed Page Hero V1
           (paused for Animation Player V2 recovery)
stash@{1}: On feature/animation-player-v2-custom-controls: animation-player-v2
           dim/glow/pulse WIP - not yet committed, awaiting user review
```

## 3. Stash PageHero được chọn

`stash@{0}`, xác định bằng **nội dung/thông điệp** (không chỉ vì là index
0): `git stash show --stat` xác nhận đúng 3 file (`globals.css`,
`Ornaments.tsx`, `ui.tsx`), khớp với công việc Themed Page Hero đã tạm dừng
ở phiên trước. `stash@{1}` (dim/glow/pulse) được xác định và **loại trừ rõ
ràng** — không đọc nội dung sâu hơn mức cần để nhận diện, không áp dụng.

## 4. File được khôi phục + wiring thêm

Từ stash: `web/src/app/globals.css` (8 khối `[data-hero-theme]` + cập nhật
`.page-head::before`), `web/src/components/Ornaments.tsx` (4 hoạ tiết SVG
mới), `web/src/components/ui.tsx` (`PageHeader` nhận prop `motif`).

Wiring thêm đêm nay (chưa có trong stash — phần còn dang dở của phiên
trước): gắn `data-hero-theme` + `motif` vào 7 trang (`page.tsx` Home,
`fanfic`, `animation`, `community`, `library`, `studio`, `image-studio`),
cập nhật `.hero-v2::before` để đọc biến theme (bị bỏ sót lúc tạm dừng),
thống nhất 2 nhánh khách (`/library`, `/studio`) từ `<h1>` trần sang
`PageHeader` thật.

## 5. Xung đột/giải quyết

`git stash apply stash@{0}` lên HEAD `87d0ba7` — **auto-merge sạch, không
xung đột** (Player V2 chạm `Icons.tsx`/`animation/*`/`next.config.mjs`,
PageHero chạm `globals.css`/`Ornaments.tsx`/`ui.tsx` — hai bộ file không
giao nhau ngoại trừ `globals.css`, mà git tự gộp đúng vì hai bên sửa hai
vùng khác nhau trong file). Stash gốc **vẫn còn nguyên** sau `apply` (xác
nhận bằng `git stash list` — không dùng `pop`).

## 6. Bản đồ theme cuối cùng

| Theme | `--hero-accent` | `--hero-accent-secondary` | Hoạ tiết |
|---|---|---|---|
| home | cyan trời (`--accent`) | `#2f6fb0` xanh biển | (không — nghệ thuật nền đã đủ) |
| explore | `#3fa9f0` azure | `#2dd4bf` turquoise | `MotifCompassArc` (mới) |
| animation | `#7c8cf8` indigo | `#e0788f` coral kiềm chế | `MotifFilmFrame` (tái dùng) |
| community | cyan (`--accent`) | `#d99a52` hổ phách ấm | `MotifConstellation` (mới) |
| library | `#4a6fc4` sapphire | `var(--vang)` **antique gold** | `MotifCelestialDial` (mới) |
| audio | cyan (`--accent`) | tím lạnh (`--brand-hover`) | `MotifWaveform` (tái dùng) |
| image-studio | tím (`--brand`) | cyan (`--accent`) | `MotifInkBloom` (mới) |
| creator | tím nhạt (`--brand-hover`) | hồng anh đào (`#f0a6c8`) | (chưa gắn trang nào — token sẵn sàng) |

Ngân sách màu vàng (`--vang`) toàn site: nâng có chủ đích từ 48 → 49 (xem
`fantasy-identity.test.mjs`) — **chỉ Library** dùng vàng thật, 7 theme còn
lại không đụng tới ngân sách này.

## 7-12. Kết quả từng khu vực

- **Home (Ocean Sky)**: `.hero-v2::before` đổi từ elip navy-đen cứng sang
  đọc `--hero-mist-1/-2` (vẫn cùng giá trị cyan hiện tại vì Home vốn đã
  dùng đúng tông này — không đổi thị giác, chỉ đổi CƠ CHẾ sang theme).
- **Explore (Sky Manuscript)**: `data-hero-theme="explore"`, hoạ tiết cung
  compa mới, `.filter-bar .input` tự tô theo `--hero-mist-2` của theme này.
- **Animation (Cinematic Nebula)**: tái dùng `MotifFilmFrame` đã có (dùng
  cho cả empty-state VÀ page-hero — nhất quán một hình cho một khu vực).
- **Community (Guild Aurora)**: theme gắn trên `.cong-dong-luoi` (bố cục
  lưới có sidebar, không phải `.page` như các trang khác) — xác nhận biến
  CSS vẫn kế thừa đúng qua cây DOM bất kể độ sâu.
- **Library (Arcane Archive)**: theme duy nhất dùng vàng thật + hoạ tiết
  đĩa thiên văn mới; cả nhánh khách và nhánh đã đăng nhập đều dùng chung
  `PageHeader` (trước đây nhánh khách là `<h1>` trần).
- **Audio/Image Studio**: tái dùng `MotifWaveform`/hoạ tiết mực loang mới;
  cả nhánh "đang kiểm tra phiên" và nhánh chính đều có theme.

## 13. Kết quả hồi quy Player V2

**PASS.** Chạy lại đúng 2 bộ test đã khôi phục
(`animation-player-v2-custom-controls.test.mjs`,
`animation-youtube-polish-v1.test.mjs`) cùng toàn bộ 851 test — không có gì
vỡ sau khi áp PageHero. `themed-page-hero-v1.test.mjs` có test riêng xác
nhận `YouTubePlayerControls.tsx`/`YouTubeFacadePlayer.tsx`/
`youtubeIframeApi.ts` **không hề nhắc tới `data-hero-theme`** — hai hệ
thống không đụng nhau.

## 14. Kết quả hồi quy NavIndicator

**PASS.** Toàn bộ test V4-V7 (`nav-indicator-motion-correction-v*.test.mjs`,
`phase3.6-nav-v6-navbar-pagehead.test.mjs`) vẫn xanh. `.nav-login`/
`.nav-right` được xác nhận rõ ràng KHÔNG đổi màu theo theme trang (điều
hướng vẫn nhất quán toàn site — đúng yêu cầu Phase 3.6 Phần 15).

## 15. Kiểm kê nền

Xem đầy đủ: `docs/design/LIVE_WALLPAPER_MANIFEST.md`. Tóm tắt: 8 nền
`fantasy-backgrounds/*.webp`, đều 1672×941 (16:9 sạch), Home là
`01-home-sunny-harbor.webp` (436 KB). Phát hiện phụ (không sửa đêm nay):
Animation và Community hiện đang dùng CHUNG nền `auth` (starlight-gate) vì
không khớp mẫu route riêng nào trong `backgrounds.ts`.

## 16. Provider/model sinh video

**Không tìm thấy provider nào đã cấu hình trong repo** — đã `grep` toàn bộ
tên biến trong `server/.env*`, `web/.env*`, `docs/`, `scripts/` tìm các từ
khoá `video|ltx|comfy|runway|pika|stability|replicate|luma|kling|wan|gpu`:
**0 kết quả**. Không có GPU VM, không có ComfyUI endpoint, không có LTX
credential nào ở bất kỳ đâu.

Đường khả dĩ DUY NHẤT: MCP Pollinations (`mcp__pollinations__generateVideo`)
— công cụ này CÓ tồn tại trong danh sách công cụ của phiên và ĐÃ được xác
thực thành công (`getKeyInfo` trả `authenticated: true`) ở một vòng làm
việc trước (dùng để sinh ảnh cho Phase 3.5). Nhưng **trong phiên overnight
này, MCP Pollinations không còn kết nối** — `ToolSearch` không tìm thấy bất
kỳ công cụ `mcp__pollinations__*` nào, cùng nguyên nhân với việc mất
`chrome-devtools`/`playwright`: hệ quả của lệnh `taskkill /IM node.exe /F`
chạy ở MỘT LƯỢT LÀM VIỆC TRƯỚC ĐÊM NAY (không phải do overnight này gây
ra — overnight này không chạy bất kỳ lệnh diệt tiến trình nào).

## 17. Có tìm thấy credential sẵn có không

**Có, nhưng không dùng được** — key Pollinations tồn tại và đã từng xác
thực thành công, nhưng công cụ MCP để gọi nó không còn kết nối trong phiên
này và không có cách nào tự khởi động lại một MCP server từ bên trong quy
tắc an toàn đã cho (cấm mọi hình thức diệt tiến trình rộng). Đây là blocker
về KẾT NỐI CÔNG CỤ trong phiên, không phải thiếu credential hay thiếu uỷ
quyền chi tiêu.

## 18-23. Kế hoạch chuyển động Home, prompt, ứng viên, vòng lặp, kích thước

**Không thực hiện được** — không có bước sinh video nào chạy, nên không có
kế hoạch chuyển động cụ thể hoá thành video thật, không có ứng viên, không
có vòng lặp/kích thước để đo. `ffmpeg`/`ffprobe` đã xác nhận sẵn có trên
máy (`8.1.1-full_build`, có `libvpx`/`libx264`) cho bước encode MỘT KHI có
video nguồn — không phải blocker ở khâu này.

## 24. Kiến trúc LiveBackground

`web/src/components/LiveBackground.tsx` (mới, CHƯA gắn vào trang nào):

- Poster (`<img>`) luôn render đầu tiên, không nằm trong nhánh điều kiện
  nào — không chặn LCP, không có khung trắng/đen chờ video.
- Video chỉ render khi `hienVideo = choPhep && coNguon && !loi` — crossfade
  bằng CSS `opacity`/`transition` (không phải vòng lặp JS) sau sự kiện
  `onCanPlay`.
- Lỗi tải video (`onError`) → `loi=true` → quay về CHỈ còn poster, vĩnh
  viễn cho lần render đó.
- `muted`/`loop`/`playsInline`/`autoPlay`, không `controls`, không thẻ
  `<audio>` nào — không tự phát âm thanh.
- `preload="none"` — không tải trước video khi chưa cần.

## 25. Hành vi reduced-motion/save-data

`prefers-reduced-motion: reduce` → `choPhep=false` vĩnh viễn cho phiên đó,
**thắng tuyệt đối** bất kể lựa chọn tương lai nào (xem mục 21).
`navigator.connection.saveData === true` → ưu tiên nền tĩnh (đọc AN TOÀN
qua optional chaining vì Safari không có API này). Tab ẩn (`document.
hidden`) → `pause()`; tab hiện lại → `play()` lại nếu đã sẵn sàng và không
lỗi — qua sự kiện `visibilitychange`, không phải vòng lặp polling.

## 26. Chính sách di động

Mặc định **KHÔNG** phát video ở màn hình ≤640px (`mobileVideo` prop mặc
định `false`) — chỉ nền tĩnh, trừ khi có bản mã hoá riêng cho di động và
chủ động bật cờ này lên trong tương lai. Chưa cần quyết định "encode nhẹ
hơn" vì chưa có video nào để encode.

## 27. Hiệu năng trước/sau

**Không đổi** — `LiveBackground.tsx` chưa được import ở bất kỳ trang nào
(dead code, bị tree-shake hoàn toàn). Xác nhận thực tế: deploy Checkpoint B
lên staging chỉ tải lên đúng **1 file thay đổi** (`BUILD_ID`) trong tổng số
tài sản tĩnh — nghĩa là không một chunk JS/CSS nào của bất kỳ trang thật
nào bị ảnh hưởng bởi Checkpoint B.

## 28. Số lượng test đầy đủ

| Checkpoint | Frontend | Backend | Typecheck | Lint | Build |
|---|---|---|---|---|---|
| A (Themed Page Hero) | 834/834 | 2410/2410 (1 skip) | sạch | sạch | sạch |
| B (Live Wallpaper kiến trúc) | 851/851 | 2410/2410 (1 skip) | sạch | sạch | sạch |

## 29. SHA commit

- Checkpoint A: `60f4cf1` — "Checkpoint A: Themed Page Hero V1 hoan tat + Player V2 con nguyen"
- Checkpoint B: `fdd24d6` — "Checkpoint B: Live Wallpaper V1 architecture (khong co video - xem bao cao)"
- Cả hai đã push lên `origin/feature/fanfic-visual-renaissance-v1`.

## 30. Trạng thái staging

Đã deploy **cả hai checkpoint** lên `https://staging.fanfic.world`
(`fanfic-web-staging`), xác nhận `HTTP 200` trên `/`, `/fanfic`,
`/animation/watch/test` sau lần deploy cuối. Đã xác nhận qua `curl` trực
tiếp rằng CSS biên dịch trên staging khớp đúng cả 8 khối `[data-hero-theme]`
trong mã nguồn.

## 31. Blocker còn lại

1. **Sinh video Home bị chặn** — không có provider video khả dụng trong
   phiên (xem mục 16-17). Đây là lý do marathon KHÔNG được coi là hoàn tất
   100% theo đúng quy tắc đã cho.
2. **QA trình duyệt thật không thực hiện được** — `chrome-devtools`/
   `playwright` MCP vẫn chưa khôi phục kết nối từ sự cố trước đó; overnight
   này không chạy lệnh diệt tiến trình nào để tránh làm tình hình xấu thêm.
   Đã bù bằng: xác minh CSS/HTML thật qua `curl` trực tiếp trên staging,
   chạy toàn bộ test tĩnh, xác nhận build production sạch.
3. **Đề xuất cho phiên kế tiếp**: (a) khởi động lại kết nối MCP
   (chrome-devtools/playwright/pollinations) trong một phiên MỚI — không
   có cách nào tôi tự làm được điều này từ bên trong các ràng buộc an toàn
   hiện tại; (b) sau khi có lại Pollinations (hoặc một provider được duyệt
   khác), tiếp tục đúng từ Phase 9 (sinh video Home) — kiến trúc
   `LiveBackground`/manifest đã sẵn sàng, không cần làm lại.

## 32. Xác nhận an toàn

- **KHÔNG** đụng `main` — nhánh làm việc suốt overnight là
  `feature/fanfic-visual-renaissance-v1`; `main` vẫn dừng ở SHA cũ trước
  overnight này (không có commit nào được tạo/merge vào `main`).
- **KHÔNG** deploy `fanfic.world` (production) — chỉ deploy
  `fanfic-web-staging` (`staging.fanfic.world`) đúng 2 lần, dùng
  `wrangler.staging.jsonc`.
- **KHÔNG** đụng Appwrite Cloud production — không có thao tác Appwrite
  nào trong overnight này (thuần frontend + git + docs).
- **KHÔNG** xoá bất kỳ stash nào — cả `stash@{0}` (PageHero, đã `apply`
  nhưng vẫn giữ nguyên bản gốc) lẫn `stash@{1}` (dim/glow/pulse, hoàn toàn
  không động tới) đều còn nguyên trong `git stash list`.
- **KHÔNG** dùng `git stash pop`, không `force-push`, không viết lại lịch
  sử, không chạy `taskkill /IM node.exe /F` hay bất kỳ lệnh diệt tiến trình
  rộng nào.
- **KHÔNG** tạo hạ tầng trả phí mới, không bật billing, không mua credit,
  không sinh video giả để thay thế.
- Working tree sạch tại thời điểm viết báo cáo này (xác nhận `git status`
  ngay trước khi commit file này).

---

**Máy KHÔNG được tắt tự động** — theo đúng Phase 31/32: vì tiêu chí E
("Homepage live wallpaper itself is generated and integrated") không đạt
do blocker ngoài tầm kiểm soát (mất kết nối MCP từ trước, không phải thiếu
credential hay thiếu uỷ quyền), toàn bộ marathon không được tự nhận là
hoàn tất, và lệnh `shutdown.exe` không được gọi.

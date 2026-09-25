# Sprint UX 1 — Đọc và nghe một chương trên cùng một trang

Ngày: 2026-09-24/25 · Nhánh `feat/reader-listener-ux-sprint1` (từ `main` @ 685eadf) ·
commit `95f059d`, `e0c2157` · **Chưa triển khai** (xem mục 7).

Bằng chứng trực quan (ảnh TRƯỚC/SAU ở 1600×900, 1366×768, 390×844 và luồng 9
bước): trang Artifact riêng tư https://claude.ai/artifact/Rmk5AjnGTmnAH19tugQHZ1

Content Factory giữ nguyên trạng thái đóng băng: không tổng hợp thêm, không
xuất bản truyện mới, không đụng crawler/pipeline/backend. RR143557 vẫn dừng ở
3/80 canary TTS.

## 1. Kiến trúc

- `/chapters/[id]` là tuyến chương DUY NHẤT: ba chế độ `read` / `read_listen` /
  `listen`. `/listen/:id` → 307 → `/chapters/:id?mode=listen` (cố ý 307 để có
  thể lùi; nâng 308 khi ổn định). `MiniPlayer` và trang Nghe cũ bị xoá.
- Server Component vẫn vẽ chữ (SEO, canonical, OpenGraph `article` giữ nguyên);
  đoạn văn chia bằng `lib/chapterSync.tachDoanVan` — cùng hàm bộ đồng bộ dùng.
- Chế độ + khung chữ + thu nhỏ + "theo giọng đọc" nằm trong cookie
  `fas_doc_chedo` (4 lựa chọn hiển thị, không dữ liệu cá nhân) để máy chủ vẽ
  đúng bố cục ngay lần đầu. Tiến độ từng chương nằm trong `localStorage`.
- `ChapterExperience` (client) điều phối: `ReaderText` (đoạn `memo`, tô sáng),
  `ChapterPlayer` (trình phát lớn ở chế độ Nghe), `ChapterAudioDock` (trình phát
  nổi, render qua portal vào `<body>`), `ChapterNavLink` (giao audio khi sang
  chương lúc đang nghe).
- `AudioEngine` vẫn MỘT thẻ `<audio>` trong layout, nay luôn mount; thêm ý định
  phát (`batDauTu`, `tuPhat`), `tuaTuongDoi`, `choPhat`/`tamDung`, Media Session,
  làm mới URL ký trước khi phát / khi 403 / khi đứng hình với URL đã hết hạn.
- `lib/audioFocus.ts`: giọng đọc > nhạc nền. Nhạc nền đăng ký kênh "ambient",
  chính sách hôm nay "pause" (như cũ), nhánh "duck" đã nối sẵn.
- Logic thuần có kiểm thử hành vi: `chapterSync`, `followScroll`,
  `readerSession`, `audioFocus`, `audioReload`.

Ba truyện đang chạy (Butterfly Effect, Cold Between Wars, Genshin) không có
phụ đề đồng bộ (`available: false` ở mọi chương đã thử) → vạch sáng dùng ước
lượng theo độ dài chữ (trọng số ngắt đoạn/câu). Có phụ đề thì dùng phụ đề.

## 2. So sánh

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Tuyến đọc / nghe | Hai trang (`/chapters`, `/listen`) | Một trang, ba chế độ; `/listen` chuyển hướng |
| Thẻ `<audio>` truyện | 1, mount lại mỗi chương | 1, luôn mount (quét toàn `src/` trong kiểm thử) |
| Đoạn đang đọc | Không có | Tô sáng; phụ đề hoặc ước lượng theo độ dài |
| Người dùng cuộn tay khi đang theo | Không áp dụng | Tạm dừng + nút "Tới đoạn đang đọc"; không kéo về |
| Ẩn/hiện chữ | Mở/đóng bản chữ ở trang Nghe | Mở · Thu gọn · Đóng, nhớ qua cookie, không dừng audio |
| Trình phát | Phát, tua, tốc độ, âm lượng | + ±10 s, chương trước/sau, thu nhỏ, phím K/J/L, Media Session |
| Sang chương khi đang nghe | Chương cũ vẫn phát | Chương sau phát tiếp; đang dừng thì chỉ chuyển trang |
| Tiếp tục | Chỉ trang chủ, cần đăng nhập | Thêm gợi ý trên chương cho mọi người, không tự phát |
| URL ký hết hạn | Làm mới khi `error`, tối đa 2 lần | + trước khi phát, khi đứng hình; kiểm bằng 403 thật |
| Danh sách chương chậm | Trang chờ vô hạn | Chờ tối đa 6 s (mất nút trước/sau, chữ vẫn hiện) |
| Giảm chuyển động | Không áp dụng | Không tự cuộn, không hiệu ứng vạch sáng |

## 3. Luồng tương tác (đã chạy trên trình duyệt thật)

1. Mở chương → Đọc + Nghe, viên "Nghe chương này", không tự phát.
2. Bấm Phát → trình phát nở ra, vạch sáng đoạn 1.
3. Tua 42% → tự cuộn đưa đoạn đang đọc vào tầm mắt.
4. Cuộn tay đi chỗ khác → tạm dừng theo dõi, nút "Tới đoạn đang đọc", audio vẫn phát.
5. Bấm nút → quay về đúng đoạn.
6. "Ẩn truyện chữ" → chế độ Nghe, chữ đóng, audio không ngắt.
7. "Hiện truyện chữ" → chữ trở lại.
8. "Chương sau" khi đang nghe → trang chuyển, chương sau phát tiếp.
9. Mở lại chương cũ → "Tiếp tục đọc / Tiếp tục nghe", chỉ phát khi bấm.

## 4. Kiểm thử

| Hạng mục | Kết quả |
|---|---|
| `npm test` | 1034 đạt · 0 lỗi · 6 bỏ qua (sẵn có) |
| `npm run typecheck` | 0 lỗi |
| `npm run lint` | 0 lỗi · 3 cảnh báo cũ ở tệp không đụng |
| `npm run build` + `npm run cf:build` (API production) | đạt; `.open-next` không còn chuỗi `localhost` |
| Trình duyệt thật (CDP, chương thật, audio R2 thật) | **153/153** (1600: 47, 1366: 47, 390: 53, đặc biệt: 6) |

Kiểm thử mới: `reader-sync-mapping`, `reader-follow-scroll`,
`reader-session-resume`, `audio-focus`, `reader-listener-ux`. 11 tệp kiểm thử cũ
khoá hành vi "hai trang" được viết lại cho trang mới, giữ bất biến gốc (một thẻ
audio, nút/thanh trượt thật, tên đọc được, cảnh báo audio cũ M4 + nút tạo lại
cho chủ chương).

QA trình duyệt lặp lại được: `scripts/qa/reader_ux/` (driver CDP, proxy CHỈ ĐỌC
tới API production — mọi request ghi bị từ chối 405 —, và bộ 153 kiểm tra).

Lỗi thật do QA trình duyệt bắt được (đã sửa, không bài kiểm chuỗi nào thấy):

- `.page` giữ `transform` sau hoạt ảnh vào trang → trình phát nổi nằm ở cuối
  tài liệu (y = 17.325 px). Sửa: portal vào `<body>`.
- 1600 px: ô tốc độ đè nút "Chương sau". Sửa: cột công cụ `minmax(max-content, 1fr)`.
- Chrome không bắn `error` khi request media bị chặn ở tầng mạng → thêm canh
  đứng hình khi URL đã hết hạn.

## 5. Phát hiện ngoài phạm vi

- API production có lúc xuống cấp trong phiên: `/api/novels/nov_rr_136586`
  > 180 s, `nov_rr_156206` 243 s, cùng lúc `getChapter` ~2 s; vài 503 rời rạc.
  Đo lại sau đó: trang chương production ~2 s, API 1 s. Không sửa backend trong
  sprint này; phía web đã chặn thời gian chờ (6 s).

## 6. Tệp thay đổi

38 tệp web (+4592 / −909): 4 component `components/reader/*`, 5 module
`lib/*`, `app/chapters/[id]/page.tsx`, `AudioEngine`, `ChapterPlayer`,
`GlobalMiniPlayer`, `Icons`, `lib/audio.ts`, `lib/musicStore.ts`,
`globals.css`, `novels/[id]`, `studio/library`, `next.config.mjs`; xoá
`app/listen/[id]/page.tsx`, `components/MiniPlayer.tsx`; 16 tệp kiểm thử.
Thêm `scripts/qa/reader_ux/` (3 tệp).

## 7. Triển khai

Chưa triển khai. Điều kiện "xanh" đã đạt, nhưng `~/.claude/settings.json` của
người dùng chặn cứng lệnh triển khai và `wrangler deploy*` với agent (kể cả
`wrangler deployments list`). Agent đã làm mọi bước trước đó: build
Cloudflare với API production, kiểm bundle sạch. Người dùng chạy (từ worktree):

```bash
! cd /c/FanficWorkers/reader-ux-sprint1/web && npx wrangler deployments list --name fanfic-web && NEXT_PUBLIC_API_BASE=https://fas-prod-api.onrender.com npm run cf:deploy:production
```

Sau triển khai, kiểm nhanh: `/chapters/ch_136586_0002` (ba chế độ, viên phát),
`/listen/ch_136586_0002` → 307 → `?mode=listen`, bấm Phát → đoạn sáng lên.
Lùi bản: `npx wrangler rollback` trên worker `fanfic-web`.

Lưu ý: bản này chạy từ nhánh chưa merge vào `main`; production sẽ chứa commit
không có trên `main` cho tới khi mở PR/merge (chưa push, chờ yêu cầu).

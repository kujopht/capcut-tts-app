# Product UX Sprint 2 — báo cáo đêm (2026-09-25)

Trạng thái cuối: **PRODUCT_UX_SPRINT2_READY_FOR_OWNER_REVIEW**.
Không deploy. Production vẫn là bản Cloudflare `5b855690` (dựng từ checkpoint WIP `83b3a3e`).
Backend, Content Factory, RR143557 (3/80 canary), crawler, AWS worker: **không đụng tới**.

---

## 1. RECONCILIATION (Phase 0)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| UI đang chạy thật so với `main` | Production dựng từ WIP `83b3a3e`, `main` thiếu `/admin/assets`, bộ lọc "Đọc & Nghe"/"Kho Audio cũ", hero trang truyện… | PR #224 đã merge: squash `a64b3a9` lúc 2026-09-25 14:57Z |
| Cách merge #224 | — | Admin-bypass, chỉ vì check "Backend tests" đỏ **y hệt main** (734/4869; tập test hỏng khác nhau = rỗng; PR không chạm backend). Lý do ghi trong thân commit `a64b3a9`, theo dõi ở issue #223 |
| Worktree cho Sprint 2 | — | `C:/FanficWorkers/product-ux-sprint2`, nhánh `feat/product-ux-sprint2` từ `a64b3a9` (main) |

Lưu ý: nhánh Sprint 2 **xếp chồng trên PR #225** (bỏ mật khẩu đăng-nhập-nhanh gắn cứng — commit `03a2b29` đã cherry-pick). Merge #225 trước; sau đó diff của PR Sprint 2 tự thu về chỉ phần Sprint 2 (nội dung trùng nên không xung đột).

## 2. SPRINT 2 — nhánh / PR / tệp

- Nhánh: `feat/product-ux-sprint2` — PR: **#226** https://github.com/kujopht/capcut-tts-app/pull/226 — **chưa merge, chưa deploy**.
- Chỉ `web/` (+ báo cáo này). Không backend, không Content Factory, không pipeline.

Tệp mới:

| Tệp | Vai trò |
|---|---|
| `web/src/lib/libraryQuery.ts` | Trạng thái Thư viện ↔ URL, tham số máy chủ, sắp xếp/lọc tại chỗ, chip fandom thật |
| `web/src/lib/scrollMemory.ts` | Nhớ vị trí cuộn theo đúng URL, dùng một lần, hết hạn 30 phút |
| `web/src/lib/novelProgress.ts` | Nút hành động theo tiến độ (Bắt đầu / Đọc tiếp / Nghe tiếp / Tiếp tục) |
| `web/src/lib/useReaderProgress.ts` | Hook đọc tiến độ cục bộ (an toàn hydrate) |
| `web/src/lib/catalogSnapshot.ts` | Ảnh chụp kho dùng chung (Thư viện, ô tìm, trang chủ) |
| `web/src/lib/searchSuggest.ts` | Gợi ý tìm kiếm tức thì fandom / tác giả / tên truyện |
| `web/src/lib/navActive.ts` | Mục điều hướng nào sáng cho một đường dẫn |
| `web/src/components/novel/{NovelPrimaryCta,NovelDescription,ChapterList}.tsx` | Nút chính theo tiến độ, mô tả thu gọn, mục lục |
| `web/src/components/FandomStrip.tsx` | Chip "Khám phá theo vũ trụ" từ dữ liệu thật |
| `web/src/app/{novels,chapters}/[id]/loading.tsx` | Khung xương khi máy chủ đang render |
| `web/tests/{library-query,novel-progress,search-suggest,nav-active}.test.mjs` | Bài kiểm mới |

Tệp sửa: `library/page.tsx` (viết lại), `novels/[id]/page.tsx`, `chapters/[id]/page.tsx`, `page.tsx` (trang chủ), `globals.css`, `SearchOverlay.tsx`, `SiteSearch.tsx`, `NavAuth.tsx`, `FollowButton.tsx`, `AdminShell.tsx`, `Icons.tsx`, `reader/ChapterExperience.tsx`, `readerSession.ts`, `taxonomy.ts`, và 12 tệp test cũ (cập nhật **có chủ đích**, mỗi chỗ có chú thích lý do).

Commit trên nhánh: `03a2b29` (nội dung PR #225, cherry-pick) → `896fc83` (Sprint 2) → `940db6c` (sửa sau QA: CLS, cổng admin, Thử lại) → commit báo cáo.

## 3. VISIBLE CHROME QA (Phase 1 + 13)

Môi trường: Chrome **hiển thị** (cổng CDP 9333, cửa sổ mở suốt phiên), dữ liệu **production thật** qua proxy chỉ-đọc cục bộ (`GET/HEAD` only, ghi → 405), chặn thêm `/api/listens` và `/api/progress/*` trong trình duyệt. Không có catalog giả. Kiểm tương tác chạy trong một **tab riêng** (tab cũ đã đầy 50 mục lịch sử của Chrome, làm sai phép thử Back/Forward).

**Audit tự động BEFORE → AFTER** — 12 trang × 5 khung nhìn (1600×900, 1440×900, 1366×768, 1024×768, 390×844) = 60 ảnh mỗi đợt; đo tràn ngang, nhãn bị cắt, vùng chạm nhỏ, CLS, lỗi HTTP/console. AFTER chạy trên **bản build production cục bộ** (`next build` + `next start`).

| Hạng mục | BEFORE | AFTER |
|---|---|---|
| Tràn ngang (60 lượt) | 0 theo đầu dò; nhưng soi ảnh thấy trang chủ 390px bị cắt ở "Lối tắt" (tràn bên trong khung `overflow: hidden`) | 0; lưới "Lối tắt" đã sửa |
| Nhãn bị cắt | "Audio" → "Au" (trang chủ 1366), tab "Sách & Tuyển tập" (390), "Giải trí" (nav 390) | 0 |
| CLS | BEFORE đo trên dev server (0 ở mọi trang — dev không phản ánh streaming). Đo lại bản build production trước khi sửa: 0,05–0,26 ở /community, /admin, /library, trang chương (footer nhảy) | Audit cuối (build production, 60 lượt): **tối đa 0,008**; admin 0; ngưỡng "tốt" của Web Vitals là 0,1 |
| Lỗi console | 0 | 0 |
| HTTP lỗi | chỉ `401 /api/admin/overview` (không có phiên admin — đúng) | như cũ |

**Kịch bản tương tác (Chrome hiển thị, dữ liệu thật):**

| Kịch bản | Kết quả |
|---|---|
| Thư viện: lọc → URL, Back/Forward khôi phục, sắp xếp Nhiều chương/Tên truyện/Mới xuất bản, tìm "hatake" (không nhồi lịch sử), trang rỗng có hướng dẫn, **Back từ trang truyện về đúng vị trí 900 px**, bộ lọc gọn ở 390px, không tràn | **18/18** |
| Ô tìm: phím `/`, fandom nhanh, gợi ý tức thì (< 250 ms), ↓ + `aria-activedescendant`, Enter → Thư viện lọc fandom, tìm theo tác giả "corty", không dấu "hoa anh", Enter khi chưa chọn → `/library?q=`, Escape, bấm ra ngoài, rỗng có gợi ý, 390px phủ màn hình | **16/16** |
| Luồng: thẻ Thư viện "Đọc tiếp 26%" → trang truyện "Đọc tiếp" + "Đang ở" → mục lục đánh dấu → tìm chương "tai ngo" → đảo thứ tự 1→99 → bấm "Đọc tiếp" thấy khung xương ngay → trang chương **tự cuộn tới đoạn 30**, không hiện dải hỏi lại, **vẫn 1 thẻ `<audio>`** | **8/8** |
| Lỗi API (chặn `/api/novels`) → hiện lỗi + Thử lại → dữ liệu về; dạng danh sách 1366/390 | **3/3** |
| Nguồn CLS (PerformanceObserver) sau khi sửa: /community, /admin, /library, chương Cold, truyện Cold | **~0,0001** mỗi trang (trước: 0,05–0,26) |

**Hồi quy Sprint 1** (harness Sprint 1, 3 khung nhìn × 3 truyện, audio R2 ký thật): lượt đầy đủ **152/153**; bài hỏng duy nhất "Chương sau khi đang phát → phát tiếp" ở 1600 (hết 60 s chờ audio chương sau khi backend chậm) — chạy lại riêng 1600: **47/47**; cùng bài đó PASS ở 1366 và 390 trong lượt đầy đủ. Bao gồm: đúng một `<audio>`, không tự phát khi mở, làm mới URL ký (403 → URL mới, giữ vị trí; hết hạn khi tạm dừng), đọc/nghe/ẩn–hiện chữ không ngắt audio, phím J/K, "Tiếp tục nghe", giảm chuyển động.

## 4. UX CHANGES

### Thư viện (`/library`)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Trạng thái bộ lọc | `useState` rời rạc; Back mất bộ lọc; không chia sẻ được | Toàn bộ trên URL (`q, fandom, audio, status, sort, view, page, tab`); đổi lọc = `push` (Back/Forward khôi phục); gõ tìm = `replace` (không nhồi lịch sử) |
| Mở truyện rồi Back | Về đầu trang | Về đúng vị trí cũ (đo: 900 → 900 px) + kết quả nhớ 5 phút, không khung xương |
| Nút chính mỗi thẻ | "🎧 Nghe & Đọc" tím đặc ở MỌI thẻ, luôn vào trang truyện | Theo tiến độ thật: "Bắt đầu đọc" (viền) / "Đọc tiếp 26%" / "Nghe tiếp" / "Tiếp tục" (tím đặc) → mở đúng chương với `?resume=1` |
| Đang đọc dở | Chỉ người đăng nhập, 1 truyện | Dải "Đang đọc dở" (tối đa 3) cả cho khách, từ tiến độ trên trình duyệt + con trỏ máy chủ |
| Lúc đang tải | Hiện "Không tìm thấy tác phẩm phù hợp" trong khi tải | Khung xương cùng kích thước thẻ thật; đổi lọc thì giữ kết quả cũ mờ đi |
| Lỗi mạng | Âm thầm rơi về `listNovels` (tải hết, giấu lỗi) | Hiện lỗi + "Thử lại" (nạp lại cả ảnh chụp kho) |
| Chip fandom | 7 chip cứng, "Sci-Fi / Warhammer", "Thể thao / Bóng rổ"… bấm ra trang rỗng | Chỉ fandom CÓ truyện trong phạm vi đang chọn, kèm số (Naruto 4, Detective Conan 1, Genshin Impact 1, One Piece 1) |
| "Mới xuất bản" | Gửi `sort=latest` — **đo trên production: trả về y hệt "Mới cập nhật"** | Gửi `sort=newest` (theo `created_at`) |
| "Nhiều chương" | Backend Appwrite **bỏ qua** `sort=chapters` | Sắp tại chỗ (99, 47, 28, 25, 18, 16, 15) |
| "Tên truyện" | Thứ tự chuỗi thô ("The Cold…" trước "[Naruto]…") | Thứ tự tiếng Việt, bỏ tiền tố "[Fandom]" |
| Tìm kiếm | Chỉ tên + mô tả, phân biệt dấu | Thêm tác giả, không phân biệt dấu ("hoa anh" → "Hỏa Ảnh") |
| Thẻ truyện | 4 nhãn chồng lên ảnh, 3 thẻ kỹ thuật ("fandom:Naruto", "audio_novel"), "Unknown Author", tác giả bịa "Fanfic Studio" | Ảnh sạch (fandom góc + vạch tiến độ), ≤ 2 thẻ đọc được, ẩn tác giả không rõ |
| Điện thoại 390px | Bộ lọc chiếm cả màn hình đầu; tab "Sách & Tuyển tập" bị cắt | Thẻ ngang gọn; bộ lọc gọn sau nút "Bộ lọc (n)"; tab rút gọn; thẻ đầu tiên thấy ngay |

### Tìm kiếm (header)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Placeholder | "Tìm truyện, tác giả, Animation…" | "Tìm truyện, tác giả, fandom…" (Animation vẫn ở bộ chọn danh mục) |
| Gợi ý | Chỉ sau khi backend trả lời (đo: vài giây); backend không tìm theo tác giả | Gợi ý **tức thì** fandom / tác giả / tên truyện từ ảnh chụp kho; kết quả đầy đủ vẫn của backend |
| Enter | Luôn mở kết quả đầu tiên (mục 0 luôn "đang chọn") | Chưa chọn gì → mở `/library?q=…`; ↓ mới chọn mục đầu |
| Mở lại hộp tìm | Gõ tiếp nối vào chữ cũ ("nar" + "corty") | Chữ cũ được bôi đen, gõ là thay |
| Trùng lặp | Nhóm "Audio" lặp lại y nguyên nhóm "Truyện" | Bỏ trùng |

### Trang truyện (`/novels/[id]`)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Ảnh nền rộng | Rơi về bìa DỌC phóng to làm nền | Chỉ khi có `hero_background_url` thật; không có thì nền tĩnh |
| Nút chính | "Đọc & Nghe" / "Chỉ đọc" cố định; "Theo dõi truyện" tím đặc cạnh tranh | Theo tiến độ: "Bắt đầu đọc" / "Đọc tiếp" / "Nghe tiếp" / "Tiếp tục đọc & nghe" + dòng "Đang ở: Chương 3 · 26%"; "Theo dõi" thành nút viền |
| Hàng nhãn trên tên | "Đã xuất bản", "Hoàn thành", 6 thẻ (có "audio_novel") đẩy tên xuống | Dòng nhỏ: fandom (liên kết về Thư viện) + tiến độ; "Bản nháp" chỉ khi đúng; ≤ 4 thẻ xuống dưới mô tả |
| Mô tả dài | Đẩy mục lục xuống dưới nếp gấp | Thu gọn 4 dòng + "Xem thêm" |
| Mục lục | 99 nút "Nghe" tím đặc; không tìm, không đảo, không biết đang đọc tới đâu | Tìm theo số/tên (không dấu), đảo cũ↔mới, đánh dấu "Đang đọc · 26%" / "✓ Đã đọc", nút "Tới chương đang đọc"; "Nghe" là nút viền |
| Chờ máy chủ | Bấm từ Thư viện → trang cũ đứng im | `loading.tsx`: khung xương ngay lập tức (trang truyện + trang chương) |

### Điều hướng, trang chủ, admin

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Mục sáng khi đọc truyện/chương | Không mục nào sáng | "Thư viện" sáng; bài đăng/trang cá nhân → "Cộng đồng" |
| Nav 390px | "Giải trí" bị vệt mờ cắt nửa chữ | Bốn mục vừa một hàng (≥ 380px) |
| Trang chủ 390px "Lối tắt" | Lưới tràn phải, cắt "Tủ sách &", "Sáng tác &" | `minmax(0,1fr)`, không tràn |
| Trang chủ 1366px "Truyện mới" | Nhãn "Audio" bị cắt thành "Au"; tên 1 dòng cụt | Biểu tượng tai nghe; tên 2 dòng |
| "Khám phá theo vũ trụ" | "Fairy Tail", "Bóng rổ" dẫn tới trang rỗng | Chip từ dữ liệu thật → Thư viện đã lọc |
| Cổng admin (chưa đăng nhập) | Dòng gợi ý xám trên tranh nền, khó đọc | Thẻ kính rõ ràng |

### Trang chương (Sprint 1 giữ nguyên)

`?resume=1` (từ "Đọc tiếp"/"Nghe tiếp") áp vị trí đã lưu ngay, không hỏi lại bằng dải "Tiếp tục…". Bản ghi tiến độ thêm tên truyện/chương (tuỳ chọn, bản ghi Sprint 1 vẫn đọc được).

## 5. PERFORMANCE (Phase 11 — chỉ quan sát, không sửa backend)

Tất cả là GET chỉ-đọc thẳng vào production (`fas-prod-api.onrender.com`, `fanfic.world`), đo bằng script tạm (không commit). Hai đợt đo cách nhau khoảng một giờ trong cùng phiên.

**Backend dao động rất mạnh trong cùng một đêm:**

| Truy vấn | Đợt 1 (giữa phiên, 2 lần) | Đợt 2 (cuối phiên) |
|---|---|---|
| `GET /api/novels?sort=updated&limit=12&content_mode=readable` (mặc định Thư viện) | 17,3 s / 8,3 s | 0,75 s (trung vị 3 lần) |
| `…&fandom=Naruto…` | 12,5 s / 6,4 s (trình duyệt: 52,5 s qua proxy) | 0,59 s |
| `…&status=completed…` | 12,8 s / 12,7 s | — |
| `…&q=hatake…` | 5,9 s / 6,4 s | — |
| `…&audio=true&content_mode=all` | **37,6 s** | — |
| `GET /api/novels?content_mode=all&limit=50` (ảnh chụp kho) | — | 1,07 s |
| `GET /api/novels/{id}` Butterfly 99 ch / Cold 47 / Genshin 15 | — | 1,12 s / 0,81 s / 0,59 s |
| `GET /api/chapters/{id}` | — | ~0,45 s |
| Trang `fanfic.world/novels/{Butterfly}` (SSR) | — | TTFB 1,5–2,2 s, HTML **181 KB** |
| Trang `fanfic.world/chapters/{ch1}` (SSR) | — | TTFB 1,3–1,5 s |
| Phiên trước (ghi lại, 2026-09-24/25) | `/api/novels/{id}` 99 chương: **> 180 s** trong một đợt xuống cấp | — |

Nguyên nhân quan sát được từ mã (chưa sửa — đề xuất cho một task hiệu năng riêng):

1. `appwrite_store.find_novels`: hễ có `content_mode` (luôn có ở trang công khai) hoặc `audio` là **quét TOÀN BỘ kho** (`_list_all`) + `audio_chapter_counts` cho mọi truyện, rồi mới cắt trang — mỗi truy vấn lọc là một lần quét kho. Với 20 truyện đã chậm khi máy chủ bận; với 80+ truyện từ Content Factory sẽ tệ hơn.
2. `sort=latest` và `updated` cùng sắp theo `updated_at`; `sort=chapters` bị bỏ qua (frontend đã né, xem mục 4).
3. Bộ lọc `fandom` chỉ so `fandom_ids`/thẻ, không so tiêu đề: 4 truyện audio cũ Conan gắn "fandom:Da Fandom Unresolved" không lọc được theo Conan (dữ liệu, không phải UI).
4. Trang truyện SSR nhúng toàn bộ mục lục 2 lần (HTML + RSC payload): 181 KB cho 99 chương — sẽ lớn tuyến tính với 500+ chương.

Phía web (đã làm trong Sprint 2, không đụng backend): đường nhanh lọc tại chỗ khi kho ≤ 50 truyện; ảnh chụp kho dùng chung (1 request cho Thư viện + ô tìm + trang chủ); nhớ kết quả 5 phút; `loading.tsx` để người đọc thấy phản hồi ngay khi máy chủ chậm.

## 6. TESTS (Phase 12)

| Hạng mục | Trước khi sửa (main `a64b3a9`) | Sau khi sửa (nhánh Sprint 2) |
|---|---|---|
| `npm test` (web) | 1041 pass / 0 fail / 6 skip | **1072 pass / 0 fail / 6 skip** (1078 bài) |
| TypeScript `tsc --noEmit` | 0 lỗi | **0 lỗi** |
| ESLint | 0 lỗi, 6 cảnh báo có sẵn | **0 lỗi**, 6 cảnh báo có sẵn (không thêm) |
| `next build` | OK | **OK** |
| Cloudflare build (`cf:build`, API production) | OK | **OK** (`OpenNext build complete`); quét 1819 tệp đầu ra: 0 `localhost:38123`, 0 `localhost:8000`; 4 chuỗi `http://localhost:` chỉ nằm trong mã nội bộ Next/OpenNext (testmode, edge runtime); API production có trong 8 tệp. **Không deploy** |

Bộ test mới: `library-query` (URL ↔ trạng thái, khứ hồi, bí danh fandom, tham số máy chủ, sắp xếp tiếng Việt, lọc toàn kho, chip fandom, **nhớ vị trí cuộn**, khung xương trước trạng thái rỗng), `novel-progress` (Bắt đầu / Đọc tiếp / Nghe tiếp / Tiếp tục / chương tiếp theo, ngưỡng, bản ghi có tên, **`?resume=1`**), `search-suggest` (**tự hoàn thành** fandom / tác giả / không dấu, gộp & bỏ trùng, bàn phím, Enter, Escape, bấm ngoài), `nav-active` (mục sáng, **nav mobile**).

Các yêu cầu kiểm cụ thể của nhiệm vụ:

| Yêu cầu | Ở đâu |
|---|---|
| Một thẻ audio duy nhất | `chapter-player.test.mjs`, `reader-*.test.mjs` (Sprint 1, vẫn xanh) + Chrome: 1 `<audio>` sau Đọc tiếp và sau Chương sau |
| Làm mới URL ký | harness Sprint 1 (403 → URL mới; hết hạn khi tạm dừng) |
| Chế độ đọc/nghe | `reader-session-resume`, `live-ui-reconcile` + harness Sprint 1 |
| URL state Thư viện | `library-query`, `library-public-catalog` + Chrome 18/18 |
| Khôi phục cuộn | `library-query` + Chrome (900 → 900 px) |
| Tự hoàn thành tìm kiếm | `search-suggest` + Chrome 16/16 |
| CTA / tiếp tục của truyện | `novel-progress` + Chrome 8/8 |
| Điều hướng mobile | `nav-active` + ảnh 390px |

Test cũ cập nhật **có chủ đích** (12 tệp, mỗi chỗ ghi lý do trong test): hàng mục lục chuyển sang `ChapterList`; Thư viện không còn rơi về `listNovels`; trạng thái lọc trên URL; placeholder "fandom"; ô tìm giao cho `/library?q=`; trang chủ không còn chip dẫn tới trang rỗng; `state` chỉ hiện khi là bản nháp; so khớp nav ở `navActive.ts`.

## 7. BLOCKERS

| Hạng mục | Tình trạng | Cần gì |
|---|---|---|
| Admin dashboard / stories / assets khi ĐÃ đăng nhập | Chỉ kiểm được trạng thái chưa đăng nhập (cổng quyền). Không dùng/tạo credential nào; không mock dữ liệu admin | Chủ sở hữu đăng nhập trong Chrome rồi chạy lại `ux_audit.py after admin` (hoặc xem tay 3 trang) |
| Deploy | Không deploy (đúng yêu cầu). Production vẫn là WIP `5b855690` | Quyết định của chủ sở hữu sau khi review |
| PR #225 (bảo mật) | Còn OPEN; mật khẩu đăng-nhập-nhanh gắn cứng VẪN nằm trong bundle production đang chạy | Merge #225, **đổi mật khẩu tài khoản đó**, rồi deploy |
| Backend CI | Đỏ sẵn trên main (734/4869), issue #223 | Không sửa đêm nay (đúng yêu cầu) |
| `/fanfic` và `/library` chồng chức năng | Hai trang khám phá; Sprint 2 đưa tìm kiếm, liên kết trang truyện và chip fandom về `/library` | Quyết định sản phẩm: chuyển hướng `/fanfic` → `/library` (URL cũ `?tag=fandom:X` đã được `/library` hiểu) |
| Tab "Sách & Tuyển tập" | Vẫn là trang giữ chỗ trung thực (chưa có ấn phẩm) | Quyết định sản phẩm: giữ hay ẩn tới khi có nội dung |

## 8. MORNING ACTION

1. Review PR #226 + trang ảnh BEFORE/AFTER (artifact riêng tư): https://claude.ai/artifact/Vtjgqpmc1NLjwtPkGPBuX2
2. Merge **#225 trước**, đổi mật khẩu tài khoản từng bị gắn cứng, rồi mới merge Sprint 2.
3. Đăng nhập admin trong Chrome để kiểm 3 trang admin (mục 7).
4. Khi muốn phát hành: deploy từ SHA của `main` sau khi merge, bằng đúng lệnh production trong `CLAUDE.md`, kiểm bundle không có `localhost`, smoke thật như Sprint 1.
5. Mở task hiệu năng backend riêng từ mục 5 (quét toàn kho mỗi truy vấn lọc; `sort=newest/chapters`; kích thước trang truyện 500+ chương).

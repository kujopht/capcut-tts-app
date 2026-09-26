# UX / Performance Sprint 3 — báo cáo đêm (2026-09-26 → 2026-09-27)

**Trạng thái cuối: `UX_PERF_SPRINT3_PARTIAL`**. Lý do nằm ở §18 và cuối báo cáo.

- **Khung giờ:** 2026-09-26 18:40Z → 21:15Z (01:40 → 04:15 giờ Việt Nam). Owner ngủ, agent tự chạy.
- **Không làm (theo lệnh):** crawl, RR143557, TTS production, Icons8, AWS worker, migration Appwrite, merge/deploy, bật `FAS_GAMES_V1`, tạo tài nguyên trả phí, xoá dữ liệu production.
- **Lightning:** dùng Studio CPU có sẵn để mã hoá video; phiên này tự bật và đã tắt.
- **Quy ước nguồn số liệu.** "Production" chỉ dùng cho số đo thật trên `fanfic.world` (khách, chỉ đọc). Còn lại ghi rõ là "bản production cục bộ" (`next start` + API mock + tài khoản thử).

## 1. Phiên bản chính và bản đang chạy

| Hạng mục | Giá trị (đo 2026-09-26 18:40Z, chỉ đọc) |
|---|---|
| `origin/main` | `eea7dad` (gói B, #230) |
| Web production | Build chunk khớp `eea7dad` 14/14. Version Cloudflare ghi lần cuối: `85a15fdf-55e0-4656-b886-85d3c3522726` (owner deploy) |
| Bản web để rollback | `4899c513-3513-4bdb-a839-9846eb26899f` |
| API (Render `fas-prod-api`) | `commit_sha e293a01`, `production`, appwrite + r2. `/api/health` mất **42,6 s** ở lần gọi đầu (lần trước đo 42,8 s); các endpoint khác 0,2–0,5 s |
| Cờ mới | Chưa có trong API đang chạy: `/api/limits` → `capabilities: None`; `/api/games/config` → 404 |
| Gói B | Đã live. Việc owner tự bấm Phát trong Studio khi đã đăng nhập **vẫn chặn**: lúc 18:41Z cửa sổ Chrome của owner vẫn `hidden`, `outerWidth 0` |
| Appwrite production | 1.9.6 + MongoDB 8.2.5; `appwrite-dev.fanfic.world` (Cloudflare) → AWS `54.179.200.223` (`i-064abacf35ebe2c8a`); project `fanfic-world-prod`, db `fanfic_world_prod` |

## 2. Bảng PR

| PR | Nhánh / base | Head | Phạm vi | CI (so với `main`) | Trạng thái |
|---|---|---|---|---|---|
| #229 | `feat/social-play-a-community` / main | `5770e2c` | Cộng đồng + hồ sơ (A) | Web + gitleaks pass. Backend: cùng tập 734 lỗi nền, khác duy nhất ở một test được đổi tên | MERGEABLE, BLOCKED (check bắt buộc đỏ vì lỗi nền) |
| #231 | `feat/social-play-c-games` / main | `1185a32` | Game + XP nguyên tử (C) | Web pass; backend 734 = 734, 0 lỗi mới | MERGEABLE, BLOCKED |
| #232 | `fix/studio-voices-load-state` / main | `596fcd4` | Danh sách giọng trong Studio | Web pass; backend 0 lỗi mới | MERGEABLE, BLOCKED |
| #233 | `fix/home-single-fetch` / main | `2e8906f` | Trang chủ tải một lần + ảnh nền đúng bản điện thoại | Web pass; backend 0 lỗi mới | MERGEABLE, BLOCKED |
| **#234** (mới) | `fix/login-prefetch-loop` / main | `635e6e0` | **Chặn vòng prefetch `/login` vô hạn trên production** | Web pass; backend 0 lỗi mới | MERGEABLE, BLOCKED |
| **#235** (mới) | `perf/background-media` / **#233** | `497daf8` | Video nền nhẹ hơn khoảng 70%, tải sau nội dung | Không có CI vì base không phải `main`. Đã chạy cục bộ: 1095/0, typecheck, lint, `cf:build` | MERGEABLE (xếp chồng) |
| **#236** (mới) | `feat/admin-ops-ux` / main | `9badb15` | Trang admin Cộng đồng / Games / Features, chỉ đọc | Web pass; backend 0 lỗi mới | MERGEABLE, BLOCKED |

## 3. Kết quả #232

Nhánh không đổi mã trong đêm; đêm nay chỉ kiểm lại cho đủ các hạng mục yêu cầu.

- **Build:** `next build` đạt; `cf:build` đạt (exit 0, "OpenNext build complete").
- **Chrome, bản production cục bộ:** 12/12.
  - Mỗi lần tải trang chỉ 1 lần `GET /api/voices` (1440 và 390).
  - API lỗi thì hiện "Không tải được danh sách giọng đọc — kiểm tra kết nối rồi **thử lại**".
  - Thử lại phục hồi 34 giọng, bấm bằng chuột, cảm ứng hoặc **bàn phím** (focus + Enter, vòng focus nhìn thấy).
  - Thứ tự Tab: ô văn bản → chọn giọng → tốc độ → Tuỳ chọn thêm.
  - Khu "Audio gần đây" vẫn hiện trạng thái rỗng rõ ràng.
  - Không tràn ngang; **0 `POST /api/jobs`**, không tạo job TTS nào.

![](anh/ux_perf_sprint3/studio_232_loi_giong_1440.webp) ![](anh/ux_perf_sprint3/studio_232_loi_giong_390.webp)

## 4. Kết quả #233

- **Build:** `next build` và `cf:build` đạt.
- **Chrome, bản production cục bộ:** 10/10.
  - SSR/SEO: HTML thô của `/` vẫn có `<title>`, meta description, `og:title`, `og:image` và `<h1>`.
  - Đăng nhập: 12 request, 0 trùng (trước là 17).
  - Chuyển trang client sang `/library` rồi bấm Back: mỗi nguồn tải lại **đúng một lần** để lấy dữ liệu mới (10 request, 0 trùng, không lặp). Forward: 0 trùng.
  - Đăng xuất: khối XP biến mất ngay, không gọi API riêng, không còn dữ liệu cũ.
- **Ảnh nền điện thoại:** chỉ tải bản 960px (§7).

## 5. Video nền: trước / sau

**Kiểm kê (ffprobe, trước khi sửa):** 8 video, tổng **42.011 KB**. Tất cả H.264 High 1920×1080, 30 fps, yuv420p, không âm thanh, vòng lặp 10,1–15,4 s, 2,3–5,5 Mbps (3,5–6,7 MB/tệp). Poster có sẵn: bản 1672px và bản 960px (`-sm`).

| Tệp | KB gốc | Thời lượng | Bitrate | Dùng ở | → AV1 900p | → H.264 720p |
|---|---|---|---|---|---|---|
| 01-home | 6.747 | 10,1 s | 5.491 kbps | `/` | 2.099 | 1.953 |
| 02-explore | 5.264 | 14,9 s | 2.894 kbps | `/entertainment`, `/novels/*` | 1.819 | 1.879 |
| 03-reader | 5.711 | 11,6 s | 4.045 kbps | `/chapters/*` | 1.421 | 1.688 |
| 04-studio | 5.662 | 12,3 s | 3.771 kbps | `/studio/*` | 1.767 | 1.880 |
| 05-write | 3.816 | 11,6 s | 2.687 kbps | `/admin`, trang viết | 1.149 | 1.249 |
| 06-library | 6.055 | 15,4 s | 3.221 kbps | `/library` | 1.651 | 1.942 |
| 07-account | 5.213 | 12,5 s | 3.417 kbps | `/community`, `/account` | 1.617 | 1.708 |
| 08-auth | 3.543 | 12,6 s | 2.310 kbps | `/login` | 1.243 | 1.338 |

**Benchmark mã hoá** (Lightning CPU `scratch-studio-devbox`, 4 vCPU / 15,7 GB; **chạy tuần tự**, mỗi lúc 1 tiến trình ffmpeg, RAM dùng ~2,4 GB; 2 vòng, 72 lần mã hoá, khoảng 35 phút; SSIM tính so với bản gốc sau khi phóng về 1920×1080):

| Phương án | Tổng KB | Giảm | SSIM trung bình / thấp nhất | s/tệp |
|---|---|---|---|---|
| **AV1 1600×900 CRF 50 (chọn)** | **12.762** | **−70%** | **0,978 / 0,970** | 49 |
| AV1 1280×720 CRF 46 | 11.745 | −72% | 0,977 / 0,963 | 37 |
| AV1 1600×900 CRF 40 | 21.006 | −50% | 0,984 / 0,978 | 57 |
| **H.264 1280×720 CRF 28 (dự phòng)** | **13.634** | **−68%** | **0,968 / 0,951** | 8 |
| H.264 1600×900 CRF 28 | 19.260 | −54% | 0,974 / 0,964 | 11 |
| H.264 1920×1080 CRF 30 | 20.081 | −52% | 0,975 / 0,967 | 13 |
| VP9 1600×900 CRF 36 | 19.861 | −53% | 0,974 / 0,965 | 47 |

- **Bằng mắt** (cùng vùng, tỉ lệ 100%, khung t=4 s của `01-home`, video có SSIM thấp nhất): AV1 900p gần như không phân biệt được với bản gốc; H.264 720p hơi mềm hơn. Nền nằm dưới lớp phủ tối `--toi 0,30–0,50` và bề mặt kính.
- **Nguyên tắc tài sản:** bản mới nằm ở `live/v2/`; bản gốc ở `live/` **giữ nguyên**, không nâng độ phân giải.

![](anh/ux_perf_sprint3/bg_so_sanh_khung_100pct.webp)

**Hành vi tải** (#235):

- **Chỉ mount video khi đủ bốn điều kiện:** tab đang hiện, trang đã `load`, đã qua ít nhất 2,5 s từ lúc mount, và trình duyệt rảnh.
- **Không phát video** trên thiết bị cảm ứng là chính (kể cả tablet), khi mạng 2g/3g, hoặc khi bật Save-Data. Vẫn tôn trọng `prefers-reduced-motion`.
- **Gỡ video thì giải phóng mạng và bộ giải mã.**
- **Nguồn:** AV1 đứng trước, H.264 là dự phòng.
- **Lỗi đã sửa:** một `<source>` hỏng từng làm mất cả video.

| Luồng (bộ đo `sp_bg_video`) | Trước (production) | Sau (bản production cục bộ) |
|---|---|---|
| 1440, vào `/` | 6.749 KB, request lúc 1.095 ms, **trước** LCP 1.976 ms | **2.099 KB** AV1, lúc 2.836 ms, **sau** LCP 1.028 ms |
| 1440, `/` → `/library` | 6.057 KB | **1.652 KB**, 3.103 ms sau cú bấm |
| Back về `/` | 0 KB | 0 KB |
| 1024 chuột | 6.749 KB | 2.099 KB |
| **1024 cảm ứng (tablet)** | 6.749 KB | **0** |
| 390 | 0 video, ảnh 587 KB | 0 video, ảnh **151 KB** |
| Chặn bản AV1 | — | Tự rơi xuống H.264 720p |
| Chặn cả hai bản | — | Chỉ poster, không lỗi |

| Trước: production, 1080p kẹt ở giây 0,5 | Sau: AV1 900p đang phát (t = 1,7 s → 9,6 s) |
|---|---|
| ![](anh/ux_perf_sprint3/bg_truoc_video_1440.webp) | ![](anh/ux_perf_sprint3/bg_sau_video_av1_1440.webp) |

## 6. Giảm byte trên desktop (1440)

Đo có đối chứng: cùng máy, cùng API mock, cache lạnh mỗi trang, cửa sổ 12 s (tính cả phần video tải trễ). Bản "trước" là `main` build bằng `next start`.

| Trang | Trước KB | Sau KB | Giảm | Nền trước → sau |
|---|---|---|---|---|
| `/` | 7.446 | 2.798 | −62% | 7.184 → 2.535 |
| `/community` | 5.909 | 2.313 | −61% | 5.643 → 2.047 |
| `/library` | 6.774 | 2.370 | −65% | 6.514 → 2.110 |
| `/entertainment` | 5.858 | 2.414 | −59% | 5.605 → 2.160 |
| `/studio/audio` | 6.407 | 2.512 | −61% | 6.136 → 2.241 |
| `/admin` | 4.465 | 1.798 | −60% | 4.208 → 1.541 |
| **Tổng 6 trang** | **36.859** | **14.205** | **−61%** | |

## 7. Giảm byte trên điện thoại (390)

| Trang | Trước KB | Sau KB | Giảm | Nền trước → sau |
|---|---|---|---|---|
| `/` | 849 | 414 | −51% | 587 → 151 |
| `/community` | 839 | 410 | −51% | 574 → 144 |
| `/library` | 866 | 409 | −53% | 606 → 148 |
| `/entertainment` | 716 | 376 | −47% | 463 → 122 |
| `/studio/audio` | 903 | 430 | −52% | 633 → 159 |
| `/admin` | 780 | 389 | −50% | 524 → 132 |
| **Tổng** | **4.953** | **2.428** | **−51%** | |

![](anh/ux_perf_sprint3/bg_truoc_390.webp) ![](anh/ux_perf_sprint3/bg_sau_390.webp)

## 8. Cộng đồng: trước / sau

| Trước (production hôm nay, khách) | Sau (#229, 1440) | Sau (#229, 1024) | Sau (#229, 390) |
|---|---|---|---|
| ![](anh/ux_perf_sprint3/a_truoc_cong_dong_prod_1440.webp) | ![](anh/ux_perf_sprint3/a_sau_cong_dong_1440.webp) | ![](anh/ux_perf_sprint3/a_sau_cong_dong_1024.webp) | ![](anh/ux_perf_sprint3/a_sau_cong_dong_390.webp) |

Tương tác (Chrome, #229, bản production cục bộ), **18/18**:

- bấm Thích 5 lần liền → **1 request**;
- API thích lỗi → hoàn tác và hiện "chưa được ghi nhận";
- gửi bài lỗi mạng → **bản nháp còn nguyên**;
- bấm "Đăng" 3 lần liền → **1 POST** (trước khi sửa là 3);
- vào một bài rồi Back → về đúng vị trí cuộn (900 → 900);
- 5 viewport 1600/1440/1366/1024/390: không tràn ngang, 0 lỗi console.

Không có realtime giả: bài mới chỉ hiện khi tải lại.

## 9. Hồ sơ: trước / sau

| Trước (#229 đầu đêm, `5f88f1a`) | Sau (#229 `5770e2c`) — "Lv. 3 · Học Giả Ma Pháp" | Sau 390 | Đóng trình sửa khi chưa lưu |
|---|---|---|---|
| ![](anh/ux_perf_sprint3/a_truoc_ho_so_1440.webp) | ![](anh/ux_perf_sprint3/a_sau_ho_so_1440.webp) | ![](anh/ux_perf_sprint3/a_sau_ho_so_390.webp) | ![](anh/ux_perf_sprint3/a_sau_hoi_bo_thay_doi_1440.webp) |

- Khung Ngọc của `qa_lan` hiện ở **navbar, bảng tin, hồ sơ, `/account`, bảng xếp hạng** (Chrome 5/5).
- Avatar Google không ghi đè được avatar tự chọn: backend chỉ suy avatar từ `avatar_key` (ảnh người dùng tải lên R2), và phía web không có chỗ nào dùng ảnh Google.

## 10. Admin (#236)

| Cộng đồng (số thật từ `/api/admin/social/overview`) | Games, trạng thái như production (API 404) | Features, chỉ đọc | Games 390 |
|---|---|---|---|
| ![](anh/ux_perf_sprint3/admin_cong_dong_1440.webp) | ![](anh/ux_perf_sprint3/admin_games_404_1440.webp) | ![](anh/ux_perf_sprint3/admin_features_404_1440.webp) | ![](anh/ux_perf_sprint3/admin_games_390.webp) |

Chrome **16/16**:

- 5 trang ở 1440/390, 0 lỗi, không tràn ngang.
- Features **không có công tắc** nào.
- Games luôn có cảnh báo **MULTIPLAYER PRODUCTION BLOCKED**.
- Giả lập `/api/games/config` trả 404 như production: trang hiện "Chưa có API", không vỡ.

Đăng nhập admin bằng một tài khoản thử được tạo trong tiến trình mock trên localhost; không có credential thật nào.

## 11. Memory / Caro (#231)

| Memory lật thẻ (390, animation đang chạy) | Memory tính điểm (+XP sau quyết toán) | Caro luyện với máy (1440) | Caro kết quả (390) |
|---|---|---|---|
| ![](anh/ux_perf_sprint3/c_memory_lat_the_390.webp) | ![](anh/ux_perf_sprint3/c_memory_tinh_diem_390.webp) | ![](anh/ux_perf_sprint3/c_caro_may_1440.webp) | ![](anh/ux_perf_sprint3/c_caro_ket_qua_390.webp) |

- **Mới trong đêm:**
  - lật thẻ 180 ms và nảy khi khớp cặp, tắt hẳn ở giảm chuyển động (2/2);
  - cú cuộn tới bàn Caro cũng theo giảm chuyển động;
  - tab bảng xếp hạng giữ một dòng ở 390.
- **Hồi quy:** luyện tập 10/10 ×2, phòng 2 người trên di động 6/6, Memory tính điểm 9/9; link bảng xếp hạng mở đúng hồ sơ thật.
- **Multiplayer:** vẫn chỉ bật ở bản thử.

## 12. XP / Bảng xếp hạng

| Trước (production 390) | Sau (#231, 390) | Sau (#231, 1440) | Trang chủ #229: một dòng cấp |
|---|---|---|---|
| ![](anh/ux_perf_sprint3/xp_truoc_bxh_prod_390.webp) | ![](anh/ux_perf_sprint3/xp_sau_bxh_390.webp) | ![](anh/ux_perf_sprint3/xp_sau_bxh_1440.webp) | ![](anh/ux_perf_sprint3/xp_trang_chu_lan_1440.webp) |

- **Thang cấp tài khoản thống nhất "Lv. N"** qua `CapDoTaiKhoan` (trang chủ, tài khoản, hồ sơ). Trước đây trang tài khoản ghi "Bậc N", dễ lẫn với "Hạng" của tác giả.
- **Tách bạch rõ:** XP tài khoản, điểm Caro theo mùa và điểm Memory là ba thang riêng, không cộng lẫn.
- **Không có XP lạc quan giả:** XP chỉ hiện sau khi máy chủ quyết toán, không có toast trùng.

## 13. Lỗi phát hiện trong đêm

| # | Lỗi | Nơi | Mức |
|---|---|---|---|
| 1 | **Vòng prefetch `/login` vô hạn:** khách ở `/community` và `/novels/*` gửi **22–27 request/giây** chừng nào tab còn mở; mỗi request là một lần gọi Worker (`x-opennext-cache: HIT`) | production | **Cao** |
| 2 | Video nền 4,2–7,2 MB/trang (73–95% byte), tải trước LCP, tải cả trên tablet | production | Cao |
| 3 | Trên Chrome QA, video H.264 1080p **kẹt ở giây 0,5** dù đã nạp đủ, cả trên production lẫn `next start` cục bộ; AV1 thì phát mượt. Chưa kết luận người dùng thật có gặp không (phiên Windows đang khoá) | production? | Cần owner kiểm |
| 4 | Tài nguyên tĩnh bỏ qua header `Range`: luôn `200` + cả tệp, không có `Accept-Ranges` | production | Thấp–trung bình |
| 5 | `/api/health` mất khoảng 42 s ở lần gọi đầu | production | Trung bình (cần tìm hiểu) |
| 6 | Bấm "Đăng"/"Gửi" nhanh gửi 3 POST (máy chủ khử trùng còn 1 bài, nhưng mỗi POST mang cả ảnh base64) | #229 | Trung bình |
| 7 | Một `<source>` hỏng làm mất cả video, không rơi xuống bản dự phòng | #235 (lỗi do chính PR này đưa vào, đã sửa trước khi đẩy) | — |
| 8 | Cấp tài khoản hiển thị ba kiểu, trang tài khoản dùng chữ "Bậc" lẫn với hạng tác giả | #229 | Thấp |
| 9 | Còn 6 chỗ `<Avatar>` trần không mang khung | #229 | Thấp |
| 10 | Memory không có phản hồi lật/khớp | #231 | Thấp |
| 11 | Tab bảng xếp hạng ngắt 3 dòng ở 390 | #231 | Thấp |

## 14. Lỗi đã sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Prefetch `/login` (#234, cũng áp vào #229) | 22–27 request/giây liên tục (production). 5 link `/login` và 7 link tới route tĩnh còn prefetch mặc định | `prefetch={false}` cho cả 12 link; test quét cấm tái phát. Bản cục bộ: 4 → 0 request `/login` |
| Video nền (#235) | 42 MB (8 tệp), tải trước LCP, cả trên tablet | 12,8 MB AV1 + H.264 dự phòng; tải sau LCP; tablet/mạng chậm chỉ poster; giải phóng khi gỡ; dự phòng hoạt động |
| Gửi bài/bình luận (#229) | 3 cú bấm → 3 POST | 1 POST (cờ chặn bằng ref) |
| Danh tính (#229) | 6 chỗ avatar thiếu khung; cấp hiển thị ba kiểu | `UserAvatar` ở mọi nơi hiện người dùng; `CapDoTaiKhoan` "Lv. N" |
| Memory (#231) | Đổi mặt tức thì | Lật 180 ms + nảy khi khớp; tắt ở giảm chuyển động |
| Tab bảng xếp hạng (#231) | "Toàn thời gian" ngắt 3 dòng ở 390 | Một dòng, thanh tab cuộn ngang |
| Admin (#236) | `social/overview` có sẵn nhưng không trang nào dùng; không có trang trạng thái games/cờ | 3 trang chỉ đọc + lọc vai trò ở Users |

## 15. Số lượng test

| Nhánh | Web test | Typecheck | Lint | Build |
|---|---|---|---|---|
| #229 `5770e2c` | 1098 pass / 0 fail / 6 skip | sạch | 0 lỗi | `next build` ✓ |
| #231 `1185a32` | 1093 / 0 / 6 | sạch | 0 lỗi | `next build` ✓ |
| #232 `596fcd4` | (không đổi) 1086 / 0 | sạch | 0 lỗi | `next build` + `cf:build` ✓ |
| #233 `2e8906f` | 1088 / 0 / 6 | sạch | 0 lỗi | `next build` + `cf:build` ✓ |
| #234 `635e6e0` | 1084 / 0 / 6 | sạch | 0 lỗi | `next build` ✓ |
| #235 `497daf8` | 1095 / 0 / 6 | sạch | 0 lỗi | `next build` + `cf:build` ✓ |
| #236 `9badb15` | 1094 / 0 / 6 | sạch | 0 lỗi | `next build` ✓ |

Backend: không chạy suite đầy đủ trên Windows (đúng lệnh). CI GitHub: 734 = 734 lỗi nền cho mọi PR vào `main`; lỗi "mới" duy nhất ở #229 là bài test avatar đã đổi tên.

## 16. Ma trận QA bằng Chrome

Một cửa sổ Chrome QA duy nhất (profile riêng, cổng 9333), dùng lại suốt đêm; không chạm Chrome của owner.

| Bộ kiểm | Viewport | Kết quả |
|---|---|---|
| #233 SSR / Back / Forward / đăng xuất | 1440 | 10/10 |
| #232 Studio (giọng, lỗi, thử lại, bàn phím, thẻ gần đây, 0 job) | 1440, 390 | 12/12 |
| Video nền (tải trễ, tablet, điện thoại, Back) | 1440, 1024, 1024 cảm ứng, 390 | Đạt (§5) |
| Dự phòng nguồn video (bình thường / chặn AV1 / chặn cả hai) | 1440 | 3/3 |
| #229 tương tác + danh tính + bố cục | 1600, 1440, 1366, 1024, 390 | 18/18 |
| #236 admin + trạng thái 404 như production | 1440, 390 | 16/16 |
| #231 lật thẻ / giảm chuyển động | 390 | 2/2 |
| #231 E2E: luyện tập / phòng / Memory tính điểm / link | 1440, 390 | 10/10 ×2, 6/6, 9/9, link ✓ |
| Production (khách, chỉ đọc): ma trận, prefetch, Range, video | 1440, 390 | §13, §17 |

## 17. Ma trận hiệu năng

**Production "trước", khách, cache lạnh, cửa sổ 12 s:**

| Trang | 1440 KB (nền / video) | req | LCP | 390 KB (nền) | req | Ghi chú |
|---|---|---|---|---|---|---|
| `/` | 7.715 (7.185 / 6.749) | 37 | 1.492 | 1.118 (587) | 36 | CLS 390: 0,0144 |
| `/community` | 5.961 (5.645 / 5.215) | **277** | 1.076 | 888 (574) | **286** | **230 request prefetch `/login`** (#234) |
| `/library` | 9.363 (6.515 / 6.057) | 35 | 1.676 | **6.007** (607) | 40 | 390: bìa truyện 641 KB tải 2 lần (ngoài phạm vi, đề xuất) |
| `/novels/nov_rr_136586` | 5.967 (5.606 / 5.265) | **268** | 392 | 817 (463) | **263** | Vòng prefetch `/login` (#234) |
| `/chapters/ch_136586_0001` | 6.395 (6.098 / 5.713) | 33 | 380 | 812 (515) | 32 | |
| `/studio/audio` | 6.425 (6.138 / 5.664) | 26 | 912 | 920 (633) | 25 | |
| `/entertainment` | 5.883 (5.606 / 5.265) | 23 | 420 | 741 (463) | 22 | |
| `/admin` (khách) | 4.490 (4.209 / 3.817) | 25 | 484 | 805 (524) | 25 | |
| `/u/*` (hồ sơ) | Không đo được: production chưa có hồ sơ công khai nào có username | | | | | Đã đo trên bản cục bộ #229 (§8) |

- **Mọi trang production:** CLS ≤ 0,0144, không tràn ngang, 0 lỗi console, 0 request API trùng (khách).
- **"Sau":** đo có đối chứng ở §6/§7 (−61% desktop, −51% điện thoại).
- **Novel, chapter, profile:** chưa đo lại phần "sau" trên bản cục bộ (API mock không có truyện thật). Hai trang novel/chapter dùng cùng cơ chế nền (video 02/03), nên mức giảm sẽ tương tự; #234 xử lý phần request.

## 18. Rào chặn còn lại

1. **Gói B:** owner bấm Phát một thẻ Studio khi đã đăng nhập. Vẫn chặn vì phiên Windows khoá.
2. **Migration Appwrite:** không truy cập được host. Lúc **2026-09-26T20:57:42Z**, `54.179.200.223:22` và `:443` đều **TIMEOUT 8 s** (còn `appwrite-dev.fanfic.world:443` qua Cloudflare thì mở). Máy này không có `aws` CLI, không có credential AWS, nên **không kiểm được SSM**. Theo lệnh: DỪNG, không mở cổng hay security group, không lách bằng máy khác.
3. **Merge:** check backend bắt buộc đỏ vì 734 lỗi nền (#223), nên mọi PR vào `main` cần owner merge bằng quyền admin.
4. **Deploy web/API:** việc của owner; agent bị chặn lệnh deploy.
5. **Hạng mục chưa xong (vì sao PARTIAL):**
   - Avatar trong thẻ kết quả game chưa dùng `UserAvatar`: #231 không có component này cho tới khi #229 vào `main`.
   - Dashboard `/admin` chưa có khối "việc chờ owner / trạng thái tính năng" (mới có các trang riêng).
   - Chưa đo "sau" cho novel/chapter/profile.
   - Hiện tượng kẹt video H.264 cần kiểm trên máy thật.
6. **Đồng bộ nhánh A:** #229 chưa có gói B. Trang chủ của A còn lối tắt "Âm Nhạc", và khi merge sẽ phải hoà xung đột ở `page.tsx`.

## 19. Sẵn sàng migration Appwrite (chỉ chuẩn bị, KHÔNG chạy)

**Đích chính xác:** `https://appwrite-dev.fanfic.world/v1`; project `fanfic-world-prod`; db `fanfic_world_prod`; host AWS `54.179.200.223`, instance `i-064abacf35ebe2c8a`, hostname `ip-172-31-35-102` (theo báo cáo đã được phép ngày 2026-09-07, `docs/reports/appwrite-backup-proven-2026-09-07.md`).

**Trình tự (sau khi owner khôi phục được đường truy cập host):**

```bash
# 0) Trên host — XÁC ĐỊNH đúng máy + container (chỉ đọc)
hostname; curl -s https://appwrite-dev.fanfic.world/v1/health/version    # phải là 1.9.6
MONGO=$(docker ps --format '{{.Names}}' | grep -i mongo | head -1); echo "$MONGO"
docker exec "$MONGO" sh -c 'env | cut -d= -f1 | grep -i -E "mongo|pass|user"'   # chỉ TÊN biến, không giá trị

# 1) SAO LƯU MỚI (cùng phương pháp đã chứng minh 2026-09-07; mật khẩu tham chiếu bằng TÊN biến trong container)
STAMP=$(date -u +%Y%m%dT%H%M%SZ); OUT=/var/backups/appwrite/$STAMP; sudo mkdir -p "$OUT"
docker exec "$MONGO" sh -c 'mongodump --username "$<TEN_BIEN_USER>" --password "$<TEN_BIEN_PASS>" \
  --authenticationDatabase admin --oplog --archive --gzip' | sudo tee "$OUT/mongodb.archive.gz" > /dev/null
sha256sum "$OUT/mongodb.archive.gz" | sudo tee "$OUT/SHA256SUMS.txt"

# 2) KIỂM TOÀN VẸN
docker exec -i "$MONGO" mongorestore --dryRun --archive --gzip < "$OUT/mongodb.archive.gz" 2>&1 | tail -3
#    + khôi phục THẬT lên container dùng-một-lần (--ulimit nofile=64000:64000), đếm document == nguồn
#    + copy ra ngoài host, sha256 hai phía khớp

# 3) Deploy API từ main đã merge với MỌI cờ tắt (Render, owner)
#    FAS_SOCIAL_V1_SCHEMA=off FAS_XP_ATOMIC=off FAS_GAMES_V1=off; /api/health commit_sha = SHA vừa merge

# 4) DRY-RUN migration (máy owner, khoá SCHEMA trong tệp env cục bộ — không dùng khoá runtime)
APPWRITE_ENDPOINT=https://appwrite-dev.fanfic.world/v1 APPWRITE_PROJECT_ID=fanfic-world-prod \
APPWRITE_DATABASE_ID=fanfic_world_prod .venv\Scripts\python.exe -m scripts.setup_appwrite --dry-run
#    -> in danh sách thuộc tính/index sẽ tạo cho owner duyệt

# 5) MIGRATE thật: cùng lệnh, bỏ --dry-run
# 6) ĐỐI SOÁT từng mục qua /attributes/{key} và /indexes/{key}: 0 thiếu, 0 chưa available; khởi động lại API
# 7) FAS_SOCIAL_V1_SCHEMA=on -> smoke Cộng đồng/Hồ sơ (tài khoản thử)
# 8) FAS_XP_ATOMIC=on -> smoke XP/phần thưởng/nhiệm vụ
# 9) FAS_GAMES_V1 GIỮ OFF  (MULTIPLAYER_PRODUCTION_BLOCKED)
```

- **`<TEN_BIEN_USER>` / `<TEN_BIEN_PASS>`:** đây là chỗ duy nhất chưa biết chính xác. Lệnh của lần 07-09 không được lưu trong repo. Owner đọc tên biến ở bước 0 rồi điền vào; không bao giờ in giá trị.
- **Rollback:**
  - Tắt cờ: có hiệu lực ngay.
  - Schema chỉ được thêm, không sửa, nên để nguyên.
  - Web: `npx wrangler rollback 4899c513-3513-4bdb-a839-9846eb26899f`.
  - Dữ liệu: `mongorestore --oplogReplay --archive --gzip` từ bản ở bước 1. Chỉ dùng khi thật cần, vì sẽ ghi đè mọi thứ ghi sau thời điểm sao lưu.

## 20. Đúng MỘT việc tiếp theo cho owner

Merge **#234**, bản chặn vòng prefetch `/login` đang tạo khoảng 20 lần gọi Worker mỗi giây cho mỗi khách mở `/community` hoặc trang truyện. PR chỉ sửa web, không đụng dữ liệu, rollback bằng revert.

```
gh pr merge 234 --repo kujopht/capcut-tts-app --squash --admin
```

Bước kế tiếp sau đó là deploy web production bằng lệnh tường minh của repo (`npm run cf:deploy:production`, cấu hình `web/wrangler.jsonc`).

---

**`UX_PERF_SPRINT3_PARTIAL`**

- **Đã sẵn sàng để owner review:** 7 PR, gồm 3 PR mới. #234 sửa một lỗi production nghiêm trọng; video nền nhẹ hơn khoảng 61% trên desktop và 51% trên điện thoại.
- **Còn thiếu (§18.5):** avatar trong kết quả game chưa hợp nhất; khối tổng quan dashboard admin; phần đo "sau" cho novel/chapter/profile; kiểm hiện tượng kẹt video H.264 trên máy thật.

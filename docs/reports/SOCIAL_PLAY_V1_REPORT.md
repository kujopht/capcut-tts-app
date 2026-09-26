# FANFIC WORLD — SOCIAL & PLAY V1: báo cáo tổng

Ngày 2026-09-26. Gốc: `main` @ `3f046e8` (sau #228). Ba PR độc lập theo thứ tự ưu tiên của chủ dự án: Cộng đồng → hồ sơ → Studio → Giải trí/game và điểm. **Không merge, không deploy, không migrate production, không tạo tài nguyên trả phí.** Báo cáo chi tiết từng gói: `SOCIAL_PLAY_V1_A.md` (nằm trên nhánh PR A), `SOCIAL_PLAY_V1_B.md` (PR B), `SOCIAL_PLAY_V1_C.md` (PR C).

## 1. Trạng thái

| Gói | PR / nhánh | Trạng thái | Chặn production |
|---|---|---|---|
| A — Cộng đồng phản hồi nhanh + hồ sơ tuỳ chỉnh | #229 `feat/social-play-a-community` (`9f0e81f`, `07664fe`) | **READY_FOR_OWNER_REVIEW** (mock) · kiểm trên Appwrite thật **BLOCKED** | Migration `docs/migrations/SOCIAL_PLAY_V1_SCHEMA.md` + cờ `FAS_SOCIAL_V1_SCHEMA` (mặc định tắt); cần Appwrite **thử nghiệm** để kiểm cursor/lọc fandom/hồ sơ/chặn trên truy vấn thật |
| B — Audio Studio, ẩn nhạc có thể bật lại, khung Giải trí | #230 `feat/social-play-b-studio-music` (`351e8da`) | **READY_FOR_OWNER_REVIEW — đủ điều kiện release riêng** (kế hoạch release + rollback đã đăng trên PR) | Không (chỉ web). Đường TTS production **chưa** được kiểm bằng E2E Piper cục bộ |
| C — Mini-game có máy chủ làm trọng tài, XP, bảng xếp hạng theo game | #231 `feat/social-play-c-games` (`88e8b96`, `118b352` + báo cáo), **chồng trên B** | **READY_FOR_OWNER_REVIEW** (mock) · **MULTIPLAYER_PRODUCTION_BLOCKED** | Migration 6 collection; `FAS_XP_ATOMIC` (đã cài, tắt trên Appwrite) cần kiểm trên Appwrite **thử nghiệm** (chưa có → BLOCKED); `FAS_GAMES_V1` giữ tắt trên production |

## 2. Trước / sau (tóm tắt — ảnh đầy đủ trong báo cáo từng gói, thư mục `docs/reports/anh/social_play_v1/`)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Bảng tin cộng đồng | Tải theo offset, chèn bài mới lên đầu, không lọc | Cursor không trùng, tab Mới nhất/Đang theo dõi, chip fandom, "N bài mới", giữ vị trí khi Back, soạn bài dạng hộp thoại/tấm trượt có nháp, đăng không trùng (khoá gửi) |
| An toàn | Chỉ báo cáo bài/bình luận | + báo cáo người dùng, ẩn/chặn hai chiều, quản lý danh sách chặn |
| Hồ sơ | Sửa ở `/account`, chỉ username/bio/avatar | Trang `/u/…` có ảnh bìa, màu nhấn, fandom, tab Bài viết/Truyện/Thành tựu; trình sửa có cắt ảnh; máy chủ giải mã + chuẩn hoá ảnh (WebP, bỏ EXIF, trần 24 MP) |
| Nhạc | Ticker, sóng nhạc, trình phát luôn có | Một cờ build ẩn hết, không xoá dữ liệu; bật lại được (đã đo trên build production) |
| Audio Studio | Thẻ gần đây "0:00 / --:--", có thể tạo trùng | Văn bản là ô chính, chống bấm đúp, thẻ có tên/giọng/thời lượng thật, phát qua động cơ toàn cục, tải MP3 |
| Giải trí | Tab nhạc mặc định; 2 game 3D không XP | Hub "Chơi ngay" nói thật chế độ/số người/thời lượng/XP; + Memory Runes và Caro 15×15 (phòng 2 người thật) |
| Điểm | Bảng XP toàn thời gian/tuần | Giữ nguyên + bảng Caro theo mùa và Memory theo độ khó, tách khỏi XP |

## 3. Tái sử dụng (không có hệ tài khoản hay hệ điểm thứ hai)

- Tài khoản/đăng nhập: `current_profile` / `optional_profile`, Google OAuth giữ nguyên, không mật khẩu cục bộ của chủ dự án.
- Cộng đồng: `social.py`, `social_service.py`, `social_store.py`, `appwrite_social.py`, `PostCard`/`CommentThread`/`ReportDialog`/`Avatar`/`CosmeticFrame` có sẵn.
- XP/cấp độ/vật phẩm: `gamification_service`, `xp_ledger` (`XpLedgerEntry`, `id_xp_entry`), `user_progress`, `XP_EVENTS`, `level_for`, `cosmetic_inventory` (khung chưa sở hữu không trang bị được — kiểm ở gói A).
- TTS: `ProviderRegistry`, `useJobTracker`, `AudioEngine` toàn cục, `audioFocus` — không đổi hành vi, không tự đổi giọng.
- Mẫu CAS của Appwrite: giao dịch TablesDB + hàng khoá như `appwrite_store.claim_job` (đã đo trên Appwrite 1.9.6).

## 4. Bằng chứng chính

| Hạng mục | Kết quả |
|---|---|
| Hồ sơ/avatar/khung, bền qua tải lại (A) | Trình sửa 12/12 (cắt ảnh bằng chuột thật, lưu, tải lại còn nguyên); ảnh lưu 0 thẻ EXIF; khung chưa sở hữu bị từ chối |
| Đăng bài/thích/bình luận trên dữ liệu thử tách biệt (A) | API 41/41; trình duyệt 8/8 (mất mạng giữ nháp, bấm đúp 1 bài, thích bị từ chối thì hoàn lại); Back 700→700 px; web mới + API cũ 7/7 |
| Studio gửi → kết quả (B) | 7/7 với Piper cục bộ: bấm đúp → 1 job, `running → completed`, thời lượng thật, Phát, Tải MP3 (tệp thật), mất mạng giữ chữ. Lần chạy đầu dùng giọng mặc định Hoài My (Edge TTS công khai, miễn phí) với chuỗi thử có nhãn — ghi trong báo cáo B |
| Ẩn nhạc, lời đọc không ảnh hưởng (B) | build production cờ tắt 4/4 (0 tệp nhạc, chunk trình phát không tải), cờ bật 1/1; lời đọc vẫn phát khi chuyển trang và tạm dừng khi mở game 4/4 |
| Hai người chơi thật + sổ cái (C) | Hai BrowserContext, hai tài khoản thử: 26/26 (trình tự nước: `c_logs/duel_replay.json`); người thắng `game_match_completed` + `game_match_won` (+5), người thua `game_match_completed` (+2); XP tài khoản tăng đúng; nước trùng/cũ/sai lượt/người ngoài/sau khi kết thúc/giả mạo kết quả bị từ chối; mất kết nối → nhận thắng 6/6 |
| Giữ XP/vật phẩm cũ (C) | XP có sẵn của tài khoản thử (80 từ seed) chỉ tăng đúng phần game; không đổi ngưỡng cấp, không xoá/reset gì; đường XP cũ không bị sửa |
| Full suite backend (C, Lightning CPU, Python 3.12, lệnh CI) | baseline 4869 / 734 hỏng vs candidate 4964 / 734 hỏng — **cùng tập theo tên, 0 lỗi mới**; commit `88e8b96` khớp 1723/1723 tệp của snapshot đã kiểm |
| Đường XP nguyên tử + trần dưới tải (C, phần D, commit `118b352`) | Test mục tiêu 212/212; full 4977 / 734 hỏng vs baseline 4869 / 734 — cùng tập, 0 lỗi mới. Đồng thời game + nhiệm vụ + nghe + đổi danh xưng: không mất, không trùng; trần không khoá 8/3 · 40/30 · 8/5 → có khoá 3/3 · 30/30 · 5/5 (cứng trong một tiến trình, mềm nếu nhiều instance) |
| Web trên nhánh C (chứa B + C, chưa có A) | 1096 bài: 1090 đạt, 0 hỏng, 6 bỏ qua; typecheck/lint/build sạch. Nhánh A: 1088 đạt / 0 hỏng |

## 5. Hiệu năng

- Bảng tin: cursor + giới hạn độ sâu (500), gộp hồ sơ theo lô (không N+1); thăm dò "bài mới" 60 s, dừng khi tab ẩn.
- Mã game tải theo route: chunk của Memory/Caro chỉ nằm trong `/entertainment*`; trình phát nhạc tải lười (không nằm trong HTML ban đầu của trang nào). Iframe game 3D chỉ gắn khi mở, gỡ khi đóng.
- Phòng Caro: thăm dò 1 s khi chơi, 2,5 s ở sảnh, ≥ 3 s khi tab ẩn; cập nhật hiện diện không tăng phiên bản (tránh bão CAS).
- Điểm nghẽn còn lại: bảng xếp hạng theo mùa tổng hợp lại từ `game_results` của mùa mỗi lần gọi (cần bảng tổng hợp nếu lưu lượng lớn); rate limit là bộ đếm trong tiến trình (có từ trước).
- Bộ test backend đầy đủ cần ~4,3–4,8 GB RSS — lý do chuyển sang Lightning.

## 6. Schema / migration còn chờ duyệt (không tự chạy)

- A: `docs/migrations/SOCIAL_PLAY_V1_SCHEMA.md` — thuộc tính mới cho `posts`/`comments`/`profiles`, enum báo cáo `user`, collection `user_blocks`. Thứ tự: deploy API (cờ tắt) → dry-run → migrate → đối soát → bật cờ → deploy web.
- C: `docs/migrations/SOCIAL_PLAY_V1_GAMES_SCHEMA.md` — `game_rooms`, `game_room_versions`, `game_runs`, `game_run_versions`, `game_results`, `xp_progress_cas`. Additive; rollback = xoá 6 collection. Đường XP cũ đã chuyển sang ghi nguyên tử (sau cờ `FAS_XP_ATOMIC`); bật cờ đó trên production chỉ sau khi kiểm trên Appwrite thử nghiệm.
- Appwrite thử nghiệm: **chưa có target được phép** (`appwrite-dev.fanfic.world` thực ra là production; project "dev" dùng chung máy production; staging đã retired). Đề xuất cấu hình + quyền tối thiểu: `docs/migrations/SOCIAL_PLAY_V1_TEST_APPWRITE.md` (Appwrite 1.9.6 + MongoDB dùng-một-lần trên Lightning CPU có sẵn, lưu ảnh cục bộ, không R2).

## 7. Phê duyệt hạ tầng / chi phí

- Không cần hạ tầng mới: phòng chơi dùng FastAPI + kho hiện có (thăm dò HTTP), không WebSocket/Durable Object/worker mới, không bật AWS worker hay Lightning cho phòng chơi.
- Kiểm thử nặng dùng Lightning CPU Studio **có sẵn** (`scratch-studio-devbox`, CPU, `max_runtime` 1 giờ, đã tắt lại). Còn để lại trên Studio: `sp_c_tests/68dde9ad4bd8` (lần chạy bị nhiễu, giữ làm bằng chứng) và `sp_c_tests/c3844124bdec` (lần chạy chính thức), ~242 MB mỗi thư mục, chưa xoá.
- Cần phê duyệt: (1) dựng Appwrite **thử nghiệm** theo `SOCIAL_PLAY_V1_TEST_APPWRITE.md` (hoặc chỉ định target khác được phép), (2) migration A và C trên target đó rồi mới tới production, (3) bật `FAS_XP_ATOMIC` rồi `FAS_GAMES_V1` trên production chỉ sau khi (1)–(2) đạt.

## 8. Không làm (đúng yêu cầu)

Không tiếp tục RR143557, không crawl/import truyện/sách, không Icons8, không nhập/tạo/xoá nhạc, không bật AWS worker hay GPU, không sửa luật chặn deploy, không cho đăng nhập nhanh bằng mật khẩu, không đụng dữ liệu người dùng thật hay schema production, không reset XP/cấp/vật phẩm/thành tựu.

## 9. Danh sách chấp nhận cho chủ dự án

- [ ] A: khách xem `/community`; đăng nhập, mất mạng khi đăng → chữ còn; bấm tên tác giả rồi Back → đúng chỗ cũ; sửa hồ sơ (cắt avatar, ảnh bìa) → tải lại còn nguyên.
- [ ] B: `/entertainment` không còn nhạc; trang chủ có thẻ "Giải trí"; Audio Studio tạo xong thấy thẻ có tên, giọng, thời lượng; Phát/Tải MP3 chạy.
- [ ] C: hai tài khoản chơi hết một ván Caro qua liên kết mời, cùng thấy kết quả + XP; Memory tính điểm hiện XP; bảng xếp hạng có tab Caro/Memory.
- [ ] Quyết định về hai migration và việc chuyển đường XP cũ trước khi bật cờ trên production.

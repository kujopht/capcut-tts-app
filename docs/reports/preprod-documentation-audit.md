# Báo cáo Phase 16 — Kiểm tra tính nhất quán tài liệu

Nhánh: `chore/preprod-overnight-hardening-v1`. Phạm vi: chỉ sửa tài liệu,
không đụng code/hành vi, không commit (để người dùng tự soát xét).

## Tóm tắt

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `docs/ADMIN.md` mục 3 (danh sách API) | Chỉ liệt kê ~12 route API GỐC (V1) — không nhắc gì tới ~40 route Admin Control Center V2 (quản lý tài khoản, kiểm duyệt Animation, Trusted Video Sources, bài đăng/bình luận/báo cáo, analytics, kill-switch Image Studio) | Thêm đoạn "LỖI THỜI kể từ Admin Control Center V2" ngay sau danh sách, nói rõ đây chỉ là API gốc, trỏ tới `server/main.py` và mục 9 của handoff Admin V2 để có danh sách đầy đủ |
| `docs/ADMIN.md` mục 6 (schema `moderation_events`) | Tiêu đề "CHƯA áp lên production" và bảng chỉ có enum 4 giá trị gốc (`author_approved/rejected/suspended/restored`), không nhắc `actor_role`/`target_type`/`target_id`/`metadata` đã thêm hay việc enum đã mở rộng nhiều lần | Thêm ghi chú: enum đã mở rộng qua nhiều phase (author_*/post_*/comment_*/report_*/user_*/content_*/trusted_source_*/youtube_mapping_*/auto_import_*), 4 trường mới đã có, và làm rõ "CHƯA áp lên production" chỉ còn đúng cho Appwrite Cloud production — trên self-host dev **đã áp dụng và đã smoke test thật** |
| `docs/ADMIN.md` mục 7 (tạo quản trị đầu tiên) | Chỉ nhắc `FAS_ADMIN_USER_IDS`, không nhắc mô hình ba mức mới (`FAS_OWNER_USER_IDS`/`FAS_MODERATOR_USER_IDS`) | Thêm câu dẫn giải thích có BA biến từ Admin Control Center V2, các bước minh hoạ áp dụng tương tự cho cả ba |
| `docs/ADMIN.md` mục 8 (việc còn lại — takedown) | Nói chung chung "gỡ truyện xuống chưa có" mà không phân biệt Truyện (novel) và Animation — dễ hiểu nhầm là CẢ HAI đều chưa có, trong khi Animation đã có gỡ/phục hồi từ Phase 4 | Làm rõ tiêu đề chỉ áp dụng cho `novels`, và ghi chú Animation đã có cơ chế `moderation_state` riêng (gỡ/phục hồi series/tập) từ Admin V2 Phase 4, trỏ tới handoff mục 4c |
| `docs/WEB_README.md` mục "Giới hạn hiện tại" | Bảng nói "Kiểm chứng Appwrite/R2 thật: ❌ Chưa" và liệt kê `AppwriteIdentityAdapter`/`AppwriteMetadataStore`/`R2StorageAdapter`/`scripts/setup_appwrite.py` là "chưa từng chạy với credential thật" — SAI, đã lỗi thời từ giai đoạn MVP ban đầu | Cập nhật bảng: tách rõ ba mức — self-host Appwrite dev (✅ đã smoke test thật nhiều lần), Appwrite Cloud + R2 staging (✅ đã diễn tập thật, 82/82), Appwrite Cloud **production** (⚠️ chưa deploy — không nhầm với hai mức trên). Thêm ghi chú DEFERRED cho lỗi datetime-rỗng trên profile production (chờ khôi phục quyền truy cập Cloud) và cho ví Fanfic Credit (`MockWalletStore`, chưa có ledger bền vững theo người dùng) |
| `docs/handoffs/admin-trusted-video-v2-handoff.md` (đầu file) | Mục 10/15 viết TRƯỚC khi merge, nói việc "xét duyệt tích hợp toàn nhánh" là quyết định còn treo của người dùng — trong khi nhánh **ĐÃ được merge** vào `integration/pre-prod-v1` (commit `5fd5ef7`, xác nhận bằng `git merge-base --is-ancestor`) trước khi nhánh hardening hiện tại được tạo | Thêm khối "CẬP NHẬT SAU KHI VIẾT XONG FILE NÀY" ngay dưới dòng "Cập nhật lần cuối", nói rõ merge đã xảy ra, ghi SHA, tránh agent phiên sau hiểu nhầm là quyết định còn treo |
| `docs/APPWRITE_SCHEMA.md` mục "Collections" | Chỉ tài liệu hoá các collection GỐC (`profiles`, `novels`, ...), hoàn toàn không nhắc `moderation_events`, `animation_series`, `animation_episodes`, `trusted_sources`, `series_mappings`, `video_imports` — không phải sai, nhưng là khoảng trống dễ khiến người đọc tưởng đó là TOÀN BỘ schema | Thêm ghi chú ngắn ngay đầu mục "Collections": các collection thêm sau chưa được viết vào đây, nguồn thật nằm ở `scripts/setup_appwrite.py`, trỏ tới `docs/ADMIN.md` và handoff Admin V2 |
| `docs/DEV_SELFHOST_APPWRITE.md` | Đã kiểm — lệnh, cổng (8010), biến môi trường, quy trình smoke test/migration đều khớp thực tế hiện tại (đối chiếu với các phase smoke test thật gần đây) | **Không sửa** — không có gì lỗi thời |
| `README.md` (gốc repo) | Toàn bộ nội dung mô tả SDK/CLI `capcut_tts_api` (sản phẩm desktop CapCut TTS), không nhắc gì tới Admin Control Center/Trusted Video Sources/nền tảng web | **Không sửa** — nằm ngoài phạm vi tính năng được audit (Admin V2/Trusted Video/web), nội dung mô tả vẫn khớp đúng SDK hiện có, không có claim sai |

## Không sửa nhưng cố ý không mở rộng (ghi nhận để người dùng quyết định)

- `docs/HANDOFF.md` (đề ngày 2026-08-08, nhánh `feature/web-mvp`) là một tài
  liệu chốt mốc lịch sử cho một giai đoạn cũ, không thuộc danh sách tài liệu
  cần audit của phase này (không nói cụ thể về Admin V2/Trusted Video). Dòng
  "Production **CHƯA DEPLOY**" của nó khớp với `CLAUDE.md` hiện tại ("production
  chưa deploy, chưa thương mại") nên **không phải** một claim sai — không sửa.
  Tuy nhiên `CLAUDE.md` vẫn trỏ người đọc mới tới file này để biết "mốc nào đã
  xong" trong khi nhiều mốc mới hơn (Admin V2, Trusted Video, WebSub) đã nằm ở
  các handoff riêng — đây là một khoảng trống về mặt điều hướng tài liệu, không
  phải một claim sai, nên không tự ý sửa `CLAUDE.md` (nằm ngoài quyền hạn của
  phase này).
- `docs/reports/*.md` (báo cáo diễn tập/audit) không sửa — đây là các bản ghi
  tại một thời điểm cụ thể (point-in-time), không phải tài liệu "sống" cần
  theo kịp code.

## Ba mục bắt buộc phải giữ đúng — đã kiểm tra, không cần sửa gì thêm

1. **YouTube WebSub end-to-end thật bị BLOCKED** (thiếu callback HTTPS công
   khai) — đã được ghi rất rõ ràng và nhất quán ở
   `docs/handoffs/admin-trusted-video-v2-handoff.md` (mục 4e, 10, 12, 15) từ
   trước, không cần sửa.
2. **Ví Fanfic Credit (MockWalletStore) là DEFERRED** — cũng đã ghi rõ ở
   handoff trên (mục 9, 15); đã bổ sung tham chiếu tới ghi chú này trong
   `docs/WEB_README.md` (xem bảng trên) để tài liệu đó không còn im lặng về
   giới hạn này.
3. **Lỗi datetime rỗng trên profile production là DEFERRED** chờ khôi phục
   quyền truy cập Appwrite Cloud — đã ghi rõ ở handoff (mục 4f, 10, 15); đã bổ
   sung tham chiếu trong `docs/WEB_README.md` để không ai đọc nhầm là production
   đã được sửa.

## Danh sách file đã sửa

- `docs/ADMIN.md`
- `docs/WEB_README.md`
- `docs/handoffs/admin-trusted-video-v2-handoff.md`
- `docs/APPWRITE_SCHEMA.md`

Không sửa: `README.md` (gốc), `docs/DEV_SELFHOST_APPWRITE.md`,
`docs/HANDOFF.md`, các file dưới `docs/reports/`.

Tất cả thay đổi ở dạng chèn ghi chú/đoạn ngắn ("LỖI THỜI", cập nhật bảng
trạng thái, thêm câu dẫn) — không viết lại toàn bộ tài liệu nào. Chưa commit,
chờ soát xét.

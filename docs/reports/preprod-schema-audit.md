# Audit nhất quán dữ liệu/schema — Overnight Hardening V1, Phase 13

Phạm vi: `scripts/setup_appwrite.py::SCHEMA` (39 collection, ground truth duy
nhất — đọc trực tiếp bằng mắt, không kết nối Appwrite thật nào), đối chiếu với
toàn bộ đường ghi/đọc trong `server/appwrite_*.py`, `server/*_domain.py`,
`server/domain.py`, và hai tài liệu `docs/APPWRITE_V2.md`/
`docs/APPWRITE_SCHEMA.md`. Hoàn toàn tĩnh/đọc file — không có kết nối Appwrite
sống nào được dùng.

## Tóm tắt

| Mức độ | Số lượng |
|---|---|
| Đã tự sửa tại chỗ (khớp FIX POLICY) | 3 nhóm (9 chỉ mục thiếu, 4 điểm đọc enum không an toàn, 9 thuộc tính datetime còn sót) |
| Ghi nhận, KHÔNG sửa (đúng ý đồ/ngoài phạm vi) | 3 (xem mục 4, và ghi chú `profiles.tier`) |
| Blocker tài liệu (báo cáo riêng, không sửa) | 2 file (`APPWRITE_V2.md`, `APPWRITE_SCHEMA.md`) lỗi thời nặng |
| Test sau sửa | 2408/2408 pass (1 skip không liên quan) — khớp baseline đầu phiên |

## 1. Chỉ mục Appwrite còn thiếu — ĐÃ SỬA

Đối chiếu mọi `Query.equal/contains/greaterThan/orderDesc(...)` trong
`server/appwrite_*.py` với chỉ mục khai báo trong `SCHEMA`. Tìm thấy 7 điểm lọc
thật không có chỉ mục nào phủ (kể cả chỉ mục tổ hợp có cột đó làm cột dẫn đầu),
nghĩa là mỗi lần gọi là một phép quét toàn bảng. Đã thêm 9 chỉ mục `key` mới
vào `scripts/setup_appwrite.py` (chỉ sửa dict Python — KHÔNG chạy tạo chỉ mục
thật trên Appwrite nào):

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `profiles` | Không có chỉ mục nào phủ `equal("user_id", ...)` từ `profiles_by_ids` (`appwrite_adapter.py`) | Thêm `user_idx` (`key`, `["user_id"]`) |
| `moderation_events` | `list_events(target_id=...)`/`list_events(action=...)` (`appwrite_store.py`) không có chỉ mục nào lấy `target_id`/`action` làm cột dẫn đầu | Thêm `target_id_idx`, `action_idx` |
| `posts` | `posts_by_ids` lọc `equal("post_id", ...)` hàng loạt, không chỉ mục | Thêm `post_id_idx` |
| `comments` | `comments_by_ids` lọc `equal("comment_id", ...)` hàng loạt, không chỉ mục | Thêm `comment_id_idx` |
| `content_reports` | `list_reports(target_kind=...)` có thể lọc CHỈ theo `target_kind` (không kèm `status`) — không chỉ mục nào có cột này đứng đầu | Thêm `target_kind_idx` |
| `user_progress` | `list_all_progress_ranked` (bảng xếp hạng XP) sắp `orderDesc("xp")`, `count_users_above_xp` lọc `greaterThan("xp", ...)` — không chỉ mục | Thêm `xp_idx` |
| `xp_ledger` | `xp_earned_since` quét toàn bộ nhật ký XP từ một mốc `created_at` — không chỉ mục | Thêm `created_idx` |

Mỗi chỉ mục mới đều có chú thích tại chỗ trong `scripts/setup_appwrite.py`
(tiền tố "Phase 13 (overnight hardening)") trỏ đúng vào hàm gọi truy vấn tương
ứng. Không đổi/xoá chỉ mục nào đã có.

## 2. An toàn tuần tự hoá enum — ĐÃ SỬA 4 điểm đọc không an toàn

Rà toàn bộ ~31 thuộc tính kiểu `enum` trong `SCHEMA` qua các adapter
(`appwrite_adapter.py`, `appwrite_social.py`, `appwrite_animation_store.py`,
`appwrite_store.py`, `appwrite_translation_store.py`,
`appwrite_trusted_source_store.py`).

**Phía GHI**: toàn bộ đều tuần tự hoá qua `.value` (không nơi nào ghi thẳng
đối tượng `Enum` hay chuỗi tự đặt tay) — sạch, không có gì để sửa.

**Phía ĐỌC**: phần lớn đã an toàn từ trước — hoặc bọc `try/except ValueError`
riêng lẻ (`_moderation_state_from_doc`, `_nguon_tu_doc`/`_import_tu_doc` trong
`appwrite_trusted_source_store.py`, `_project_from_row`/`_job_from_row`/
`_glossary_from_row` trong `appwrite_translation_store.py`, đọc
`AuthorStatus`/`author_status` trong `appwrite_adapter.py`), hoặc dùng chung
một hàm `_enum(kieu, gia_tri, mac_dinh)` (`appwrite_social.py`) áp cho
`PostKind`/`ContentState`/`NotificationKind`/`ReportReason`/`ReportStatus`.

Tìm thấy 4 điểm đọc **KHÔNG bọc**, gọi thẳng `EnumClass(str(doc.get(...)))` —
một giá trị lạ/cũ trong Appwrite sẽ ném `ValueError` làm sập nguyên request:

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `animation_series.state`, `animation_episodes.state` (`appwrite_animation_store.py`) | `state=PublishState(str(doc.get("state") or "draft"))` — ném thẳng | Thêm hàm `_publish_state_from_doc()` (try/except → `PublishState.DRAFT`), áp cho cả hai |
| `novels.state`, `chapters.state` (`appwrite_store.py`) | `state=PublishState(str(doc.get("state") or "draft"))` — ném thẳng | Thêm `_publish_state_from_doc()` riêng cùng khuôn, áp cho cả hai |
| `tts_jobs.status` (`appwrite_store.py`) | `status=JobStatus(str(doc.get("status") or "pending"))` — ném thẳng | Thêm `_job_status_from_doc()` (try/except → `JobStatus.PENDING`) |

Ghi nhận KHÔNG sửa: `profiles.tier` trong `appwrite_adapter.py::_profile_from`
không hề đọc giá trị đã lưu — luôn gán cứng `tier=Tier.FREE`. Đây không phải
rủi ro sập (không có lệnh parse nào để ném lỗi) nên không thuộc phạm vi audit
này; đổi hành vi đó là thay đổi tính năng (tier trả phí), ngoài FIX POLICY
"an toàn/nhỏ". Chỉ ghi lại để người quyết định tính năng biết.

`author_applications.status`/`translation_provider_connections.status` không
có gì để kiểm — hai collection này **chưa có adapter Appwrite thật** (ghi rõ
trong `SCHEMA`: "CHƯA áp lên bất kỳ môi trường nào"), tương tự bốn collection
Image Studio (`image_wallet_transactions`, `image_generation_reservations`,
`image_saved_library`, `image_byop_connections`) — hiện chạy hoàn toàn trên
Mock store trong bộ nhớ, không có đường đọc/ghi Appwrite thật nào để audit.

## 3. Tái xác minh datetime rỗng — ĐÃ SỬA 1 điểm sót thật

Nhắc lại: đợt hardening trước trên nhánh này (checkpoint `8b1c544`) đã sửa các
chỗ ghi `""` thay vì `None` cho thuộc tính `datetime` tuỳ chọn (Appwrite tự
diễn dịch chuỗi rỗng thành GIỜ HIỆN TẠI thay vì NULL). Nhiệm vụ ở đây là
**tái xác minh**, không làm lại.

Rà toàn bộ ~15 thuộc tính `datetime` tuỳ chọn còn lại (`profiles.last_read_at`
v.v., `tts_jobs.lease_expires_at/started_at/finished_at`,
`trusted_sources.*`, `video_imports.published_at/reviewed_at`,
`translation_jobs.*`, `translation_provider_connections.last_verified_at`) ở
tầng adapter (`_to_doc`/`to_row` trong `appwrite_adapter.py`,
`appwrite_store.py`, `appwrite_translation_store.py`) — toàn bộ sạch, đã dùng
đúng mẫu `... or None`.

Tìm thấy 1 điểm sót **ở một tầng khác** mà đợt trước và lần rà tầng-adapter
không chạm tới: `server/trusted_source_domain.py`, hai hàm `to_dict()` của
chính dataclass miền (`TrustedSource`/`VideoImport`) — nơi trực tiếp tạo dict
gửi lên Appwrite trong `create_source()`/`create_import()`, KHÔNG đi qua một
hàm `_to_doc` riêng ở tầng adapter nên không nằm trong phạm vi tìm kiếm theo
tên hàm quen thuộc:

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `TrustedSource.to_dict()`: `last_scan_at`, `last_success_at`, `last_error_at`, `subscription_expires_at`, `last_subscription_attempt_at`, `last_notification_at`, `last_successful_sync_at` | Gán thẳng `self.<field>` — nếu giá trị Python là `""` (mặc định dataclass khi chưa từng quét/đăng ký) thì gửi thẳng `""` lên Appwrite | Đổi thành `self.<field> or None` cho cả 7 trường |
| `VideoImport.to_dict()`: `published_at`, `reviewed_at` | Cùng vấn đề | Đổi thành `self.<field> or None` |

Đây là bug thật (nguồn Trusted Video mới tạo sẽ mang giá trị "đã quét/đã đăng
ký" giả ngay từ đầu do Appwrite tự gán giờ hiện tại), thuộc đúng loại lỗi mà
`8b1c544` nhắm sửa nhưng không quét tới tầng dataclass `to_dict()` này. Đã sửa
theo đúng mẫu đã dùng ở `8b1c544`.

## 4. Tính duy nhất qua `documentId` tất định — SẠCH, xác nhận có chủ đích

`SCHEMA` ghi chú nhiều collection dùng `documentId` tất định thay vì chỉ mục
`unique` để cưỡng chế tính duy nhất (`listen_credits`, `post_likes`,
`notifications`, `job_locks`, `video_imports.import_id`, `user_progress`,
`xp_ledger`, `achievement_unlocks`, `reading_streaks`, `quest_progress`,
`job_claims`/`translation_job_claims`). Đã xác minh trực tiếp bằng code (không
chỉ đọc chú thích) rằng các hàm sinh khoá tất định tương ứng THẬT SỰ tồn tại
và được dùng: `creator.credit_key`, `social.post_like_key`,
`social.notification_key`, `trusted_source_domain.video_import_id`,
`gamification.id_tien_do_nhiem_vu`, và các mẫu `documentId = user_id` trong
`appwrite_gamification_store.py` (`user_progress`, `xp_ledger`,
`achievement_unlocks`, `reading_streaks`, `quest_progress` — dòng 341, 401,
438, 481, 510, 532). Đây là mẫu có chủ đích, nhất quán, KHÔNG phải sơ sót —
không sửa gì.

## 5. Đối chiếu tài liệu APPWRITE_V2/SCHEMA với `SCHEMA` thật — Blocker tài liệu, không sửa

Cả hai tài liệu đều tự nhận là chưa đầy đủ, nhưng khoảng trống thực tế rộng
hơn nhiều so với mức tự nhận:

- **18/39 collection hoàn toàn không được nhắc tới** ở cả hai file: toàn bộ
  tầng xã hội (`user_follows`, `story_follows`, `posts`, `post_likes`,
  `comments`, `notifications`, `content_reports`), Translation Studio (6
  collection), Gamification (6 collection), Image Studio (4 collection).
- `docs/APPWRITE_SCHEMA.md` (dòng 39-46) đã có ghi chú trỏ do Phase 16 (fork
  tài liệu khác, chạy song song trong cùng phiên) cho 6 collection nữa
  (`moderation_events`, `animation_series`, `animation_episodes`,
  `trusted_sources`, `series_mappings`, `video_imports`) — xác nhận ghi chú
  này đúng và còn hợp lệ, KHÔNG hoàn tác.
- Không có collection/field nào được tài liệu hoá nhưng đã bị xoá khỏi code
  (không có mục "documented-but-nonexistent").
- Mismatch trường trên các collection ĐÃ được tài liệu: `profiles` thiếu 13
  trường V4/V6 (`avatar_key`, cụm `last_read_*`/`last_listen_*`/`last_watch_*`);
  `audio_tracks` thiếu 3 trường phụ đề (`transcript_key`, `transcript_version`,
  `source_content_hash`); `moderation_events.action` — bảng enum trong
  `APPWRITE_V2.md` §5 chỉ liệt kê 4/~30 giá trị hiện có (dừng ở trước khi
  Admin V2 mở rộng từ vựng action).

Đây là phát hiện mức BLOCKER tài liệu (khối lượng thiếu quá lớn để coi là
"chưa cập nhật nhỏ"), nhưng việc VIẾT LẠI hai tài liệu này vượt phạm vi
"sửa an toàn/nhỏ" của phase — không thuộc `scripts/setup_appwrite.py` hay code
runtime nào, chỉ ghi nhận để Phase 17 tổng hợp cùng phát hiện tài liệu tương tự
của Phase 16.

## Kết quả kiểm thử

```
.venv/Scripts/python.exe -m unittest discover -s server/tests -t .
Ran 2408 tests in ~69s
OK (skipped=1)
```

Khớp đúng baseline đầu phiên overnight (2408/2408, 1 skip không liên quan —
thiếu file `.onnx.json` test model cục bộ). Không có test nào hỏng sau các
sửa đổi ở mục 1-3.

## Tệp đã sửa

- `scripts/setup_appwrite.py` — 9 chỉ mục mới (mục 1).
- `server/appwrite_animation_store.py` — `_publish_state_from_doc()` an toàn (mục 2).
- `server/appwrite_store.py` — `_publish_state_from_doc()`, `_job_status_from_doc()` an toàn (mục 2).
- `server/trusted_source_domain.py` — `or None` cho 9 thuộc tính datetime tuỳ chọn (mục 3).

Tất cả đều là sửa đổi tại chỗ (uncommitted), chờ người dùng xem xét trước khi
commit — không có gì được tự ý commit hay push.

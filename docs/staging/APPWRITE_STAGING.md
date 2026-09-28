# Appwrite STAGING: `fanfic-staging` trên Appwrite Cloud (Education)

**Không phải production.** Production vẫn là Appwrite **1.9.6** tự host trên AWS, và **không bị chạm**: không migration, không ghi, không cờ nào được bật. Staging chỉ chứa **dữ liệu tổng hợp** (`qa-*@example.test`). Không sao chép dữ liệu người dùng hay nội dung production.

## Đích được duyệt (chủ dự án, 2026-09-28)

| | |
|---|---|
| Endpoint | `https://sgp.cloud.appwrite.io/v1` (Singapore) |
| Project | `6ab9f4fa0036791d13d1` (tên hiển thị `fanfic-staging`; ID do Appwrite tự sinh) |
| Database | `fanfic_staging` |
| Phiên bản | Appwrite Cloud **2.3.0** |
| Lúc duyệt | 0 database · 0 người dùng · 0 bucket (xác minh chỉ đọc) |

Nguồn sự thật duy nhất của đích: `server/appwrite_tablesdb_compat.py::STAGING_*`. Guard ở `scripts/staging/guard.py` đọc từ đó.

## Rào an toàn

1. **`guard.kiem_dich`**, không gọi mạng:
   - endpoint và project phải khớp **chính xác** đích đã duyệt;
   - host phải là `*.cloud.appwrite.io`, không bao giờ là `fanfic.world`;
   - không trùng toạ độ production nào trong `scripts/ops/cutover_target.py` (có cả lớp kiểm ngược `khang_dinh_khong_phai_production`);
   - tiến trình gọi không được có `FAS_ENV=production`.
2. **`guard.xac_minh_song`**, chỉ đọc, chạy trước **mọi** thao tác ghi: đọc phiên bản, xác nhận khoá thuộc đúng project, và **mọi tài khoản phải có đuôi `@example.test`**. Có tài khoản thật thì dừng.
3. **`guard.moi_truong_con`**: tiến trình con chỉ nhận `APPWRITE_*` là toạ độ staging, `FAS_ENV_FILE` rỗng (không nạp `server/.env` nào), và **không** thừa kế `APPWRITE_*`, `R2_*`, `FAS_*`, `SENTRY_*` của shell gọi.
4. **Lớp dịch staging** (`server/appwrite_tablesdb_compat.py`, xem dưới) chỉ bật khi `APPWRITE_ENV=staging` hoặc project ID trùng chính xác. **Bật với project khác, kể cả production, thì tiến trình chết ngay lúc khởi động.** Ở từng request, chỉ dịch khi URL thuộc endpoint staging **và** `X-Appwrite-Project` là project staging.
5. **Bí mật:**
   - nạp qua `FAS_STAGING_SECRETS_FILE` (tệp ghi chú của chủ dự án, nằm ngoài kho) hoặc biến `FAS_STAGING_*`;
   - `CauHinhStaging` ẩn khoá khỏi `repr`;
   - mọi log và báo cáo đi qua `cfg.an()`.
6. **Test sống** nằm ở `scripts/staging/live/`, **ngoài** gói hermetic `server/tests`. `server/tests/__init__.py` ép mock và xoá biến Appwrite/R2; rào đó giữ nguyên. CI không bao giờ chạy bộ test sống.

## Migration đã chạy (chính xác)

`python -m scripts.staging.migrate --apply`, chạy trên nhánh tích hợp cục bộ `main` + #229 + #231, vì SCHEMA lấy từ chính cây mã. Mỗi bảng đi qua `scripts.setup_appwrite --only <bảng>` (script đã kiểm chứng, idempotent, chờ `available`) trong tiến trình con đã khoá đích. Kiểm lại bằng `--kiem` (chỉ đọc): **24/24 bảng khớp SCHEMA, 243 cột và 63 index đều `available`, `rowSecurity` bật ở mọi bảng.**

| Nhóm | Bảng (cột · index) |
|---|---|
| Nền | `profiles` (26·3), `author_stats` (4·1) |
| Community #229 | `posts` (21·5), `post_likes` (4·2), `comments` (15·5), `notifications` (9·2), `content_reports` (12·4), `user_blocks` (5·3), `user_follows` (4·3), `story_follows` (4·3), `moderation_events` (10·5), `novels` (31·4) |
| XP | `user_progress` (5·2), `cosmetic_inventory` (4·1), `xp_ledger` (7·3), `achievement_unlocks` (3·2), `reading_streaks` (6·1), `quest_progress` (6·1), `xp_progress_cas` (4·1) |
| Games #231 | `game_rooms` (26·4), `game_room_versions` (3·1), `game_runs` (17·3), `game_run_versions` (2·1), `game_results` (15·3) |

- `author_stats` và `novels` được thêm **sau khi đo**, vì đó là phụ thuộc thật:
  - đăng bài cập nhật thống kê tác giả ngay sau khi ghi (thiếu bảng thì bài vẫn được tạo nhưng request trả 503);
  - feed lọc fandom đọc `novels`.
- **AI Support / sự cố:** V1 lưu trong bộ nhớ, nên **không** tạo bảng nào. Xem `docs/support/SUPPORT_STORAGE_PROPOSAL.md`.
- Không bucket, không function, không team.

## Rollback / đặt lại

```bash
# FAS_STAGING_SECRETS_FILE=<tệp ghi chú>  (không in giá trị)
python -m scripts.staging.reset --du-lieu            # KẾ HOẠCH: xoá tài khoản @example.test + document
python -m scripts.staging.reset --du-lieu --apply    # xoá dữ liệu tổng hợp, GIỮ schema
python -m scripts.staging.reset --database --apply   # ROLLBACK migration: xoá cả database fanfic_staging
python -m scripts.staging.migrate --apply            # dựng lại (idempotent)
```

Cả hai lệnh đều qua guard và xác minh chỉ đọc. Chỉ xoá tài khoản `@example.test`, và chỉ xoá database `fanfic_staging` của project đã duyệt.

## Khác biệt ngữ nghĩa đo được: Appwrite 1.9.6 (production) và Cloud 2.3 (staging)

| # | Hạng mục | 1.9.6 + MongoDB (production) | Cloud 2.3 (staging), đo 2026-09-28 | Xử lý |
|---|---|---|---|---|
| 1 | Scope API key | Có `collections.*`, `documents.*` | **Chỉ** `tables.*`, `columns.*`, `rows.*`; API Databases kiểu cũ trả **401 missing scopes** (deprecate từ 1.8) | Lớp dịch chỉ cho staging; production giữ nguyên |
| 2 | Tạo database | `POST /v1/databases` | Phải qua `POST /v1/tablesdb` | `migrate._dam_bao_database` |
| 3 | Hình dạng phản hồi | `documents`, `attributes`, `$collectionId`, `documentSecurity`, lỗi `document_*` | `rows`, `columns`, `$tableId`, `rowSecurity`, lỗi `row_*` / `table_*` / `column_*` | Dịch hai chiều trong lớp dịch |
| 4 | **Cập nhật không đổi dữ liệu** | Luôn tăng `$updatedAt` | **Vẫn commit nhưng giữ `$updatedAt`** | Làm lộ **lỗi khoá CAS XP** của #231: marker trùng trạng thái hiện tại thì mọi writer xung đột **vĩnh viễn**. Sửa ở nhánh `fix/xp-cas-noop-update` (mọi lần ghi đặt `updated_at` mới) |
| 5 | Tranh chấp CAS | — | Trước khi sửa: 5/10 lượt hết số lần thử khi 10 writer cùng ghi một dòng qua mạng tới SGP. Sau khi sửa: **0/10** | Bất biến "tiến độ == sổ cái" giữ đúng trong mọi lần đo |
| 6 | Cột trùng tên khoá phản hồi | — | `game_runs.rows` trùng khoá `rows` của danh sách | Lớp dịch chỉ coi là danh sách khi có `total` và `rows` là list |
| 7 | Engine | MongoDB replica set | Engine do Cloud quản lý | Chưa đo giới hạn độ dài index/dòng riêng; toàn bộ 24 bảng và 63 index tạo được |
| 8 | Transaction | `/v1/tablesdb/transactions` | Cùng API; xung đột trả **409 `transaction_conflict`** | Không cần dịch |

**Giới hạn của bằng chứng:** staging kiểm được schema, index, truy vấn, quyền, transaction và đồng thời trên một Appwrite **thật**, nhưng là **Cloud 2.3**, không phải 1.9.6 + MongoDB. Các hành vi riêng của MongoDB 1.9.6 (vd bộ đệm collection cũ, 500 khi gọi `GET /v1/account` đồng thời) vẫn chỉ đo được trên production-parity. Xem `docs/migrations/SOCIAL_PLAY_V1_TEST_APPWRITE.md`.

## Ma trận test tích hợp thật (`python -m scripts.staging.run_live`)

**22/22 ĐẠT** (lần 4, 251 giây, backend thật và Appwrite Cloud thật qua lớp dịch).

| Nhóm | Kiểm |
|---|---|
| Kết nối / cấu hình | backend `appwrite` + `staging`, cờ Social V1 / XP nguyên tử / Games bật, `/api/health` không lộ khoá |
| Community | đăng bài idempotent theo `client_key` (lần lặp trả 200 và giữ nội dung lần đầu; người khác cùng khoá không va chạm); sửa/xoá chỉ chủ bài (403 với người khác); khách trả 401; bình luận idempotent và `comment_count` đếm một lần; chỉ tác giả sửa được bình luận; like hai lần tính một; feed `scope=latest` có cursor không lặp, lọc fandom đúng, cursor hỏng trả 400; chặn thì ẩn bài; báo cáo; feed không lộ email/token |
| Hồ sơ | bio/fandom/accent lưu thật; fandom sai thì **không ghi gì**; avatar lưu thật (`avatars/<uid>/`), dữ liệu rác trả 400; khung chỉ trang bị được khi sở hữu, gỡ được |
| XP nguyên tử | 16 lượt ghi đồng thời (8 entry, mỗi entry gửi 2 lần) cho XP 16, sổ cái 8 dòng, không trùng; 6 lượt cộng + 4 lượt đổi danh xưng đồng thời: tiến độ == sổ cái, thử lại tuần tự idempotent |
| Games | ván Caro quyết toán đúng một lần (+5 / +2 XP) kể cả khi **5 worker cùng thấy "pending"**; sau khi kết thúc, body không đổi được kết quả (409); bảng xếp hạng có người thắng (3 điểm) và người thua (0); Memory không lộ bố cục, chỉ chủ lượt thao tác được (403) |
| Hạn mức và đồng thời | trần đăng bài **đếm trên dữ liệu Appwrite** (bài 13 trả 429; gửi lại `client_key` không bị tính); 6 lượt đăng cùng `client_key` đồng thời cho đúng 1 bài; 6 lượt like đồng thời cho `like_count` = 1 |

## Đề xuất dài hạn (CHƯA làm): chuyển production sang TablesDB

API Databases kiểu cũ đã bị deprecate từ Appwrite 1.8; khoá tạo trên 2.x không còn scope cũ. Nâng production lên 2.x mà không chuyển đổi thì **mọi** đường dữ liệu hỏng. Đề xuất một PR riêng, **sau khi** staging đạt và chủ dự án duyệt:

1. Chuyển tầng dữ liệu (`server/appwrite_*.py`, `scripts/setup_appwrite.py`) sang TablesDB: `tables/rows/columns`, `tableId/rowId`, `rowSecurity`. Production 1.9.6 đã hỗ trợ TablesDB, nên chuyển đổi được **trước** khi nâng phiên bản.
2. Tái dùng bảng ánh xạ và bộ test của `appwrite_tablesdb_compat.py` làm hợp đồng: mỗi endpoint cũ có đúng một endpoint mới tương ứng.
3. Chạy bộ `scripts/staging/live` trên staging **không có** lớp dịch để chứng minh tương đương; sau đó chạy trên một bản sao production-parity (1.9.6 + MongoDB).
4. Gỡ lớp dịch khi không còn đường gọi kiểu cũ.

Cờ và thứ tự triển khai cần quyết định riêng. **Không có gì ở đây được thực thi trong đợt này.**

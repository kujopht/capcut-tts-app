# Thiết kế dài hạn: API Databases (Appwrite 1.9.6) → TablesDB (Appwrite Cloud)

**Trạng thái: THIẾT KẾ, chưa thực thi.** Đợt này không đổi dòng mã production nào, không migration, không ghi Appwrite production. Mọi quyết định bên dưới cần chủ dự án duyệt riêng.

## 1. Vì sao phải làm (đo 2026-09-28)

- Production dùng API Databases **kiểu cũ** (`/v1/databases/{db}/collections/{c}/documents`) ở 10 module lưu trữ: `appwrite_adapter.py`, `appwrite_store.py`, `appwrite_gamification_store.py` cùng các store animation, bulk import, scrape run, site profile, translation, trusted source, cộng `adapters.py` và `scraper/universal/router.py`. Transaction thì **đã** dùng TablesDB (`/v1/tablesdb/transactions`).
- API cũ bị deprecate từ 1.8. Khoá tạo trên Appwrite 2.x (Cloud 2.3) **không còn** scope `collections.*` hay `documents.*`: mọi request kiểu cũ trả 401. Vì vậy nâng production lên 2.x, hay dời lên Cloud, mà không chuyển đổi trước thì **mọi đường dữ liệu hỏng**.
- Appwrite 1.9.6 (bản production đang chạy) **đã có** TablesDB. Nghĩa là có thể đổi API **trước**, trên đúng máy chủ và dữ liệu hiện tại, không phải dời dữ liệu.

Vì thế kế hoạch tách thành **hai giai đoạn độc lập**:

| | Giai đoạn 1: đổi API | Giai đoạn 2: dời nơi chạy (tuỳ chọn) |
|---|---|---|
| Làm gì | Mã backend gọi TablesDB thay cho Databases, **trên chính Appwrite 1.9.6 hiện tại** | Dời dữ liệu 1.9.6 tự host sang Appwrite Cloud (hoặc bản tự host 2.x) |
| Dữ liệu có di chuyển không | **Không**: cùng database, cùng bản ghi, chỉ đổi mặt tiền API | **Có** |
| Rủi ro chính | Khác biệt ngữ nghĩa giữa hai API | Tính toàn vẹn khi chuyển dữ liệu, thời gian gián đoạn, danh tính người dùng |
| Rollback | Lật cờ về API cũ | Trỏ lại máy chủ cũ, kèm quy tắc cho các lần ghi phát sinh sau khi chuyển (§9) |

## 2. Phạm vi schema

Schema lấy từ `scripts/setup_appwrite.py::SCHEMA` sau khi gộp #229 và #231:
- **53 collection**;
- **144 index** (130 `key`, 14 `unique`), **không có** `fulltext` và **không có** relationship;
- 24 trong số đó đã dựng và kiểm trên staging Cloud 2.3 (xem `docs/staging/APPWRITE_STAGING.md`).

## 3. Ánh xạ schema và API

Nguồn sự thật: bảng ánh xạ và bộ test của `server/appwrite_tablesdb_compat.py`. Lớp dịch đó đã chạy thật 23/23 trên Cloud 2.3, nên có thể dùng làm **hợp đồng**.

| Databases (cũ) | TablesDB (mới) | Ghi chú |
|---|---|---|
| `/v1/databases[/{db}]` | `/v1/tablesdb[/{db}]` | Tạo database phải qua `POST /v1/tablesdb` |
| collection, `collectionId` | table, `tableId` | |
| attribute: `/attributes/{kiểu}` | column: `/columns/{kiểu}` | Kiểu giữ nguyên: string, integer, float, boolean, datetime, enum… |
| index `attributes: [...]` | index `columns: [...]` | Loại `key`/`unique` giữ nguyên |
| document, `documentId`, `/documents` | row, `rowId`, `/rows` | Danh sách: `{total, documents}` đổi thành `{total, rows}` |
| `documentSecurity` | `rowSecurity` | |
| `$collectionId` trong phản hồi | `$tableId` | |
| loại lỗi `document_*`, `collection_*`, `attribute_*` | `row_*`, `table_*`, `column_*` | Mã hiện tại nhận diện lỗi theo **type**, nên phải đổi đồng bộ |
| `/documents/{id}/{attr}/increment` | `/rows/{id}/{col}/increment` | Dùng cho bộ đếm (`like_count`…) |
| Query (JSON) | giữ nguyên | Không cần đổi cú pháp |

Cạm bẫy đã đo được: một bảng có **cột tên `rows`** (`game_runs.rows`) làm phản hồi tạo một dòng trông giống một danh sách. Khi đọc phản hồi phải kiểm **cả** `total` lẫn việc `rows` có phải list không.

## 4. Ngữ nghĩa thời gian

| Hạng mục | 1.9.6 + MongoDB | Cloud 2.3 (đo) | Quy tắc cho mã mới |
|---|---|---|---|
| `$createdAt` | Máy chủ đặt | Máy chủ đặt | Chỉ dùng để hiển thị/sắp xếp (`appwrite_adapter.py:901`, đúng như hiện nay) |
| `$updatedAt` khi cập nhật **không đổi dữ liệu** | Luôn tăng | **Giữ nguyên**, dù vẫn commit | **Không bao giờ** dùng `$updatedAt` làm token phiên bản/CAS. Nếu cần phiên bản, dùng một trường do ứng dụng đặt và **luôn đổi** ở mỗi lần ghi |
| Độ phân giải | micro-giây, ISO 8601 | như bên trái | So sánh dạng chuỗi ISO có múi giờ; không so ở độ phân giải giây |

Kiểm kê hiện tại: chỉ đường CAS của XP (#231) dựa vào `$updatedAt`, và đã sửa ở #246 (mọi lần ghi nguyên tử đặt `updated_at` mới). Có bài test sống: đỏ khi không có bản sửa, xanh khi có. Mọi đoạn mã mới dùng `$updatedAt` phải qua review riêng.

## 5. Quyền

- **Mô hình hiện tại giữ nguyên.** Quyền theo từng bản ghi (`documentSecurity`, tức `rowSecurity`) **chỉ cấp đọc** cho chủ sở hữu (`read("user:<id>")`), thêm `read("any")` khi nội dung công khai. **Không** cấp `update`/`delete` cho người dùng. Mọi lần ghi đi qua backend bằng API key, và API key bỏ qua quyền bản ghi (`profile_permissions`, `_owner_permissions`).
- Chuỗi quyền giống hệt nhau ở hai API, nên dữ liệu quyền không cần chuyển đổi.
- **API key:**
  - giai đoạn 1 cần một khoá production **mới** có scope `tables.*`, `columns.*`, `rows.*` (và transaction);
  - khoá cũ giữ tới hết cửa sổ rollback, rồi thu hồi;
  - không bao giờ dùng chung khoá giữa production và staging.

## 6. ID

- `rowId` chính là `documentId`: cùng giới hạn độ dài và bộ ký tự. Mã đang dùng ba kiểu ID:
  - ID **tất định** (`doc_id`, `user_id` cho `profiles`, `xp_progress_cas_row_id`…);
  - `unique()`;
  - ID do dịch vụ sinh.
- Giai đoạn 1: **không đổi ID nào**, vì cùng bản ghi.
- Giai đoạn 2: công cụ chuyển dữ liệu **bắt buộc giữ nguyên ID**. Tính idempotent (bài đăng theo `client_key`, sổ cái XP, marker CAS) dựa vào ID tất định; đổi ID là mất idempotency và trùng dữ liệu.

## 7. Index

- Giai đoạn 1: **không đổi**, vì đó là cùng index trên cùng database.
- Giai đoạn 2:
  - dựng lại **144 index** bằng `scripts/setup_appwrite.py` (idempotent, chờ `available`), rồi đối chiếu bằng một bản kiểm chỉ đọc kiểu `migrate --kiem`;
  - staging đã tạo được toàn bộ 63 index của 24 bảng;
  - **chưa đo** giới hạn độ dài index/dòng của engine Cloud cho 29 bảng còn lại; phải chạy `--kiem` trên đích trước khi chuyển;
  - index `unique` phải dựng **sau** khi nạp dữ liệu và kiểm trùng, hoặc trước nhưng dừng ngay khi gặp lỗi trùng.

## 8. Lưu trữ tệp

- Audio, ảnh bìa và avatar nằm ở **R2** (`server/r2_adapter.py`), không ở Appwrite Storage. Bản ghi chỉ lưu **khoá** đối tượng.
- Cả hai giai đoạn **không di chuyển tệp nào**. Chỉ cần kiểm các trường khoá (`object_key`, `output_key`…) còn nguyên.
- URL ký R2 do backend sinh lúc đọc, nên không phụ thuộc Appwrite.

## 9. Dual-run và cutover

### Giai đoạn 1: đổi API trên 1.9.6

1. **Cờ** `FAS_APPWRITE_API=legacy|tablesdb`, mặc định `legacy`.
   - Mã gọi qua một lớp mỏng, tái dùng bảng ánh xạ ở §3 theo chiều ngược lại: mã nói TablesDB, chế độ `legacy` dịch về API cũ.
   - Lớp dịch staging sẽ bị gỡ khi xong.
2. **Đọc bóng (shadow read)**, chỉ đọc:
   - với một mẫu nhỏ request đọc ở production, chạy thêm bản TablesDB song song;
   - so kết quả sau khi chuẩn hoá (bỏ `$tableId`/`$collectionId`, sắp theo ID);
   - ghi **số lượng** lệch theo collection vào log, không ghi nội dung;
   - không có lần ghi nào, nên không có rủi ro dữ liệu.
3. Lật **đọc** sang TablesDB, rồi lật **ghi** (transaction vốn đã là TablesDB). Theo dõi tỷ lệ 5xx/409 qua Sentry (#244).
4. Giữ cờ `legacy` một chu kỳ phát hành, rồi xoá mã cũ.

**Rollback giai đoạn 1:** đặt `FAS_APPWRITE_API=legacy` rồi khởi động lại. Không cần dọn dữ liệu, vì cùng dữ liệu.

### Giai đoạn 2: dời sang Cloud (nếu chủ dự án chọn)

1. **Chuẩn bị:**
   - project đích riêng (không phải `fanfic-staging`), plan phù hợp production (**plan Education không dùng cho production**);
   - dựng schema và kiểm `--kiem`.
2. **Tổng duyệt** trên một bản sao: chạy công cụ chuyển (ưu tiên Appwrite Migrations Appwrite→Appwrite, gồm cả Users kèm băm mật khẩu; **phải kiểm tra lại** tính năng này với phiên bản thật lúc đó), rồi chạy `scripts/staging/live` và bộ production-parity.
3. **Cutover:**
   - bật chế độ **chỉ đọc** ở backend (một cờ bảo trì; ghi trả 503 có thông báo);
   - chụp nhanh dữ liệu và chuyển phần chênh;
   - đếm dòng theo collection ở hai phía và đối chiếu checksum của các trường chính;
   - đổi `APPWRITE_ENDPOINT`/`PROJECT_ID`/khoá;
   - tắt chỉ-đọc.
4. **Rollback giai đoạn 2:**
   - nếu phát hiện lỗi **trong** cửa sổ chỉ-đọc: trỏ lại máy chủ cũ, không mất gì;
   - nếu sau khi đã mở ghi: lần ghi mới chỉ nằm ở đích, nên hoặc sửa tiến ở đích, hoặc chạy chuyển ngược phần phát sinh. Vì vậy cửa sổ quan sát nên **ngắn và có kế hoạch**. Giữ máy chủ cũ nguyên trạng ít nhất tới hết cửa sổ đó.

## 10. Kế hoạch kiểm

| Mức | Kiểm |
|---|---|
| Đơn vị | Bảng ánh xạ hai chiều (tái dùng `test_appwrite_tablesdb_compat.py`); fake trong test contract phải mô phỏng đúng hành vi 2.x (ghi không đổi dữ liệu thì giữ `$updatedAt`, đã có) |
| Staging Cloud 2.3 | `scripts/staging/live` **không** lớp dịch, gọi TablesDB trực tiếp, phải 23/23 |
| Production-parity 1.9.6 + MongoDB | Cùng bộ test; đo riêng các hành vi chỉ Mongo mới có (bộ đệm collection cũ, 500 khi `GET /v1/account` đồng thời) |
| Production | Chỉ đọc bóng, đếm độ lệch; không có test ghi |

## 11. Việc cần chủ dự án quyết

1. Có làm giai đoạn 1 không, và khi nào (khuyến nghị: làm, vì nó gỡ rủi ro nâng cấp mà không di chuyển dữ liệu).
2. Giai đoạn 2 có cần không: ở lại tự host 1.9.6/2.x hay lên Cloud, và plan nào.
3. Cửa sổ chỉ-đọc chấp nhận được cho giai đoạn 2.

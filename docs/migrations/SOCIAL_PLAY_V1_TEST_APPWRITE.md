# Social & Play V1 — Appwrite THỬ NGHIỆM cho gói A và C (cần duyệt, CHƯA tạo)

Trạng thái: **BLOCKED — chưa có target được phép.** Tài liệu này ghi đúng cấu hình cần tạo và quyền tối thiểu cần cấp. Không có tài nguyên nào được tạo, mua hay đổi; production không bị chạm.

## 1. Vì sao chưa có target được phép

| Ứng viên | Thực tế đo được | Dùng được? |
|---|---|---|
| `appwrite-dev.fanfic.world` (máy `fanfic-appwrite-temp`) | **Chính là production** dù tên có "dev"/"temp" (`docs/reports/production-cutover-2026-09-04.md` §1) | **Không** |
| Project "dev" trên cùng máy Appwrite đó (các khoá `schema-migration-key-v2`, `staging-schema-runtime-…`) | Tách project/database nhưng **dùng chung máy, MongoDB và tài nguyên với production** (`docs/APPWRITE_MIGRATION.md`) | **Không** nếu chưa được chủ dự án cho phép rõ; kể cả khi được phép thì migration thử vẫn chạy trên máy production |
| `staging.fanfic.world` / Appwrite Cloud staging | Đã **retired** (2026-08), không dựng lại; Cloud khác phiên bản/engine CSDL với production | **Không** |

Production: Appwrite **1.9.6** tự lưu trữ, `_APP_DB_ADAPTER=mongodb`, MongoDB chạy replica set (`docs/APPWRITE_MIGRATION.md` §1). Target thử phải khớp phiên bản và engine này.

## 2. Đề xuất (khuyến nghị): Appwrite 1.9.6 + MongoDB dùng-một-lần trên Lightning CPU Studio có sẵn

- **Ở đâu:** `scratch-studio-devbox` (CPU, đã dùng cho test backend; có sẵn Docker). **Không tạo máy/Studio mới, không GPU, không EC2, không DNS công khai.** Studio tự tắt theo `max_runtime`.
- **Cái gì:** docker compose chính thức của Appwrite **1.9.6** với `_APP_DB_ADAPTER=mongodb` (MongoDB replica set một node). Chỉ bind `127.0.0.1`. Không dùng chung volume, khoá hay dữ liệu nào với production.
- **Tách biệt:** project riêng (vd `fas-socialplay-test`), database riêng (vd `fas_test`), API key riêng. Người dùng chỉ là **tài khoản thử tạo mới** (`qa_*@example.test`); không dùng phiên hay dữ liệu thật của ai.
- **Lưu ảnh:** `STORAGE_BACKEND=local` trên Studio. **Không dùng R2**, kể cả bucket canonical production.
- **Vòng đời:** dựng → migration → kiểm schema/index → bật cờ → test A và C → lấy log về → `docker compose down -v` (xoá sạch). Chạy tuần tự, trong thư mục riêng, không đụng môi trường Piper/TTS có sẵn trên Studio.
- **Chi phí:** không có tài nguyên trả phí mới; chỉ dùng giờ CPU của Studio đang có.

Phương án B (nếu không muốn dùng Studio): một máy CPU tạm do chủ dự án cấp, cấu hình như trên. Việc này có thể phát sinh chi phí nên cần duyệt riêng.

## 3. Quyền tối thiểu (API key của project thử)

| Khoá | Scope | Dùng cho |
|---|---|---|
| Schema (chỉ khi migrate) | `databases.read`, `databases.write`, `collections.read`, `collections.write`, `attributes.read`, `attributes.write`, `indexes.read`, `indexes.write` (tên TablesDB tương ứng: `tables.*`, `columns.*`) | `scripts/setup_appwrite.py` tạo schema A + C |
| Runtime backend | `users.read`, `users.write`, `sessions.write`, `databases.read`, `collections.read`, `documents.read`, `documents.write` (TablesDB: `rows.read`, `rows.write`, gồm giao dịch `/v1/tablesdb/transactions`), `health.read` | tài khoản thử, hồ sơ, bài/bình luận, chặn, phòng/lượt/kết quả game, sổ cái XP, giao dịch CAS |

Không cấp `buckets.*`/`files.*` (không dùng Appwrite Storage), `functions.*`, `teams.*`, `projects.*`. Khoá chỉ sống trong phiên test trên Studio, không ghi vào repo, không đưa vào log.

## 4. Cấu hình backend khi chạy test

```
DATA_BACKEND=appwrite
APPWRITE_ENDPOINT=http://127.0.0.1/v1          # Appwrite thử trên chính Studio
APPWRITE_PROJECT_ID=fas-socialplay-test
APPWRITE_DATABASE_ID=fas_test
APPWRITE_API_KEY=<khoá runtime của project thử — nhập lúc chạy, không lưu>
STORAGE_BACKEND=local
FAS_SOCIAL_V1_SCHEMA=1      # gói A (chỉ sau khi migrate + kiểm schema)
FAS_XP_ATOMIC=1             # đường ghi tiến độ XP nguyên tử (bắt buộc trước game)
FAS_GAMES_V1=1              # gói C (config tự từ chối nếu thiếu FAS_XP_ATOMIC=1)
```

## 5. Thứ tự kiểm khi được duyệt

1. `GET /v1/health/version` = `1.9.6`; adapter = mongodb.
2. `python -m scripts.setup_appwrite --dry-run`, rồi chạy thật trên project thử; kiểm mọi thuộc tính/index ở trạng thái `available` trước khi bật cờ.
3. **Cờ tắt trước:** backend với `FAS_SOCIAL_V1_SCHEMA=0`, `FAS_GAMES_V1=0` → các luồng cũ chạy trên schema mới (tương thích ngược).
4. Gói A: tạo/sửa bài, gửi trùng (`client_key`), bình luận, cursor + lọc fandom, đổi avatar/banner → lưu → tải lại, chỉ chủ tài khoản sửa được, không lộ email/token, chặn/ẩn đúng phạm vi.
5. `FAS_XP_ATOMIC=1`: giao dịch 3 thao tác thật: cộng song song không mất lần nào; đọc trạng thái cũ → thua commit → thử lại; XP chỉnh về giá trị cũ vẫn cộng tiếp.
6. Gói C: hai tài khoản thử chơi hết ván Caro, Memory tính điểm, quyết toán đúng một lần (kể cả nhiều request quyết toán cùng ván), trần dưới tải đồng thời.
7. Lấy log về, `docker compose down -v`.

# SOCIAL & PLAY V1 — kiểm thử tích hợp A + C trên Appwrite thử nghiệm dùng-một-lần

Ngày 2026-09-26. Phạm vi được duyệt: "Release B + disposable Appwrite integration". **Không migrate production, không bật cờ social/XP/game trên production, không merge/deploy #229/#231.**

## 1. Môi trường thử (đã huỷ sau khi xong)

| Hạng mục | Giá trị |
|---|---|
| Máy | Lightning CPU Studio **có sẵn** `scratch-studio-devbox` (4 vCPU, không GPU, không nâng cấu hình). Docker 28.0.1, Compose v2.27. Đã **tắt** sau khi xong |
| Appwrite | `appwrite/appwrite:1.9.6`, `_APP_DB_ADAPTER=mongodb`, MongoDB **8.2.5 replica set `rs0`**, Redis. Compose project riêng `fassptest`, network `fassptest-*`, volume `fassptest_*` |
| Lộ ra ngoài | Chỉ traefik `127.0.0.1:18480` (loopback). Không endpoint công khai, không console công khai |
| Project / DB | `fas-socialplay-test` / `fas_test`. Khoá **schema** (databases/collections/attributes/indexes/tables/columns) tách khoá **runtime** (users/sessions/documents/rows/health). Bí mật chỉ ở tệp `600` trên Studio, không in ra log |
| Backend thử | `env -i` qua rào allowlist: endpoint loopback:18480, đúng tên project/db, `/health/version = 1.9.6`, engine mongodb, container thuộc `fassptest`, traefik chỉ loopback. Thử âm: trỏ `appwrite-dev.fanfic.world` hoặc project `fanfic-world` → **chặn (exit 97) trước mọi gọi mạng**. `FAS_ENV_FILE=""` (không nạp `.env`), `STORAGE_BACKEND=local`, `FAS_INLINE_WORKER=false` (không pipeline TTS nào chạy) |
| Tài khoản | Tổng hợp `*@fas-socialplay-test.invalid`, mật khẩu ngẫu nhiên; không Google, không dữ liệu/phiên người dùng thật |
| Dọn dẹp | Lấy log về trước (quét 29 giá trị bí mật × 71 tệp: **0 lộ**); `docker compose -p fassptest down -v` + network `fassptest-runtimes` → 0 container/volume/network còn lại; **không** `docker system prune`. Còn lại trên Studio: image Docker trong cache, thư mục `sp_aw_test/` (snapshot, venv, log, khoá của instance đã huỷ) |

## 2. Mã đã kiểm

| Cây | Commit | Snapshot (sha256 của manifest) |
|---|---|---|
| Baseline (schema `main`) | `f794e02` = `main@eea7dad` + cherry-pick sửa chờ của `setup_appwrite` (`8755c9b`) — SCHEMA không đổi | `79eb1f75…` |
| Integration cuối (A+B+C, nhánh cục bộ, không push) | `80ab36a` = `main@eea7dad` + A `399f5fb` + C `01cbac3` | `1560efbd…` |

Mỗi snapshot là `git archive` của đúng commit, đối chiếu lại từng tệp theo manifest sau khi giải nén: 0 lệch. Các cây trung gian (mỗi lần sửa lỗi): `ab0cb05e`, `7a4d0816`, `bbfb127d`, `4551ef22`, `2139c246`, `f3f62bd0`. Một snapshot bị chụp nhầm lúc merge đang xung đột (hash trùng `4551ef22`) và được bỏ, không dùng làm bằng chứng.

## 3. Trình tự đã chạy thật (đúng thứ tự được duyệt)

| Bước | Mã / cờ | Kết quả |
|---|---|---|
| 1. Schema `main` + seed dữ liệu cũ bằng API của `main` | baseline | 27/27: 4 tài khoản, bài, bình luận, theo dõi, thích, báo cáo kiểu cũ, XP nhiệm vụ (đường cũ), XP xuất bản (100 XP, lên bậc 2, 1 gói chờ) |
| 2. "Deploy mã trước": mã mới, **cờ tắt**, schema **cũ** | integration | 25/25: đọc đủ dữ liệu cũ, ghi kiểu cũ được, trường mới bị từ chối **409** (không ghi hỏng), game 404 |
| 3. Rào allowlist → dry-run (847 bước) → migration thật | integration | **37 s**, tạo 104, bỏ qua 743, `content_reports.target_kind` mở rộng 2 → 3 (`+user`) tại chỗ. Đối soát từng mục: 53 collection / 655 thuộc tính / 137 index, **0 thiếu, 0 chưa available** |
| 4. Mã mới, cờ tắt, schema **mới** | integration | 25/25 |
| 5. `FAS_SOCIAL_V1_SCHEMA=1` | integration | Gói A **47/47** (lần cuối) |
| 6. `+ FAS_XP_ATOMIC=1` | integration | HTTP 13/13 + 4/4; tầng dịch vụ **11/11**; xác minh phiên đồng thời 1/1 (108 request, 0 × 401) |
| 7. `+ FAS_GAMES_V1=1` (chỉ TEST) | integration | Gói C 20/22 — 2 mục hỏng là **lỗi harness** (tra trường `source_id` không có trong lịch sử); đọc lại từ Appwrite **10/10** |
| 8. Hai tiến trình API cùng Appwrite | integration | 6 trận kết thúc đồng thời chia 3/3 qua 2 tiến trình: mỗi trận đúng 1 bản ghi/người, XP = tổng bản ghi |

## 4. Lỗi tích hợp tìm thấy và đã sửa (đẩy vào PR tương ứng)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Migration chờ thuộc tính (`setup_appwrite`, C `8755c9b`) | Chờ bằng tài liệu collection; Redis giữ bản cũ `rights_mode: processing` **TTL -1** dù thuộc tính đã `available` → 3 lần chạy lại đều kẹt 120 s | Đọc thẳng `/attributes/{key}`, `/indexes/{key}`; baseline 77 s, migration A+C 37 s, không kẹt |
| Hồ sơ đọc lại từ Appwrite (A `9a3539c`) | Ghi đúng `accent`/`fandom_ids`/`banner_key` vào hàng nhưng `_profile_from`/`_merge_stored` **không đọc** → hồ sơ công khai `accent: null`, không banner | Cả hai đường đọc dùng chung `_truong_social_v1`; đọc lại đủ, banner tải lại được sau khởi động lại |
| Phiên hợp lệ bị 401 khi đồng thời (A `69aaf4f`, `399f5fb`) | 6 request đồng thời → `[201, 200, 401, 401, 200, 401]`: Appwrite trả **500 "Transaction aborted"** cho `GET /v1/account`, backend biến mọi ≥ 400 thành 401 (giao diện coi là hết phiên) | 5xx → 503 (`AppwriteUnavailableError`), xác minh phiên thử lại tối đa 2 lần **chỉ khi 5xx** (không thử lại timeout), thông điệp 503 cố định; 108 request đồng thời → 0 × 401 |
| Mở gói thưởng khi crash (C `adb6add`, `01cbac3`) | Trừ gói rồi mới cấp vật phẩm: crash ở giữa → 0 gói, 0 vật phẩm, mở lại báo "không có gói" | Trừ gói + dòng sổ cái 0 XP ghi **khoá vật phẩm đã rút** trong MỘT transaction; lần mở kế tiếp cấp bù đúng vật phẩm (không rút lại → đổi catalog không phát không vật phẩm); cửa sổ cấp bù 30 ngày |
| Ghi XP khi tranh chấp (C `adb6add`, `77de700`, `01cbac3`) | 5 lần thử, chờ 10–50 ms: **7/24** lần ghi hỏng khi 8 luồng cùng ghi một người, **29/48** khi 16 luồng (XP vẫn đúng bằng số lần commit) | Backoff mũ có jitter (9 lần) + khoá theo người trong tiến trình (256 ô, chờ tối đa 5 s rồi để CAS phân xử): 8 luồng 24/24, 16 luồng **48/48**, 2 tiến trình 24/24 |
| Review độc lập các bản sửa | — | 1 HIGH (rút lại theo catalog hiện tại) + 2 MEDIUM (thử lại cả timeout; giữ khoá qua gọi mạng) đã sửa; 2 LOW ghi ở §7 |

Không sửa `capcut_tts_api/`, không đổi hành vi TTS, không nới rate limiter (hạn mức 10 bài/giờ được cưỡng chế từ DB: lần chạy lại gói A dùng bộ tài khoản thử mới thay vì nới hạn mức — ghi trong kết quả).

## 5. Bảo đảm: đã chứng minh trên Appwrite thật / chỉ trong một tiến trình / không bảo đảm khi nhiều tiến trình

**Đã chứng minh trên Appwrite 1.9.6 + MongoDB thật (một instance thử):**
- Migration additive trên DB **có dữ liệu**, kể cả mở rộng enum; tương thích khi cờ tắt **trước và sau** migration.
- Gói A: gửi trùng (kể cả 6 request đồng thời) → 1 bài/1 bình luận; cursor + fandom không trùng/không mất khi có bài mới chèn giữa các trang; avatar/banner lưu, chuẩn hoá WebP, bỏ EXIF, tải lại giống hệt byte sau khi khởi động lại máy chủ; chỉ chủ sửa/xoá được; email/tier/author_status không lộ ở hồ sơ, bảng tin, bình luận; danh sách chặn là riêng; ẩn một chiều không chặn tương tác, chặn hai chiều chặn bình luận/theo dõi, người thứ ba không bị ảnh hưởng, bỏ chặn khôi phục; báo cáo người dùng; lưu hồ sơ tất-cả-hoặc-không.
- XP: các sự kiện khác nhau đồng thời đều được cộng; một sự kiện gửi lại 10 lần → 1 lần; nhiệm vụ + vật phẩm + danh hiệu + mở gói + cộng XP đồng thời không mất gì, sổ cái khớp tiến độ; crash giữa các bước nhiệm vụ/vật phẩm/gói → thử lại không mất, không nhân đôi; XP điều chỉnh về giá trị cũ vẫn cộng tiếp; ghi từ **hai tiến trình** vẫn đúng (CAS ở tầng DB).
- Gói C: hai tài khoản chơi Caro do máy chủ làm trọng tài; nước cũ/sai lượt bị từ chối; mất kết nối → nhận thắng; kết nối lại → nút nhận thắng biến mất, ván tiếp tục; ván 5 nước không tính XP có lý do; Memory: 0/22 phản hồi lộ bố cục; quyết toán đúng một lần (mỗi trận/lượt đúng 1 bản ghi/người, kể cả 12 GET đồng thời và qua 2 tiến trình).

**Chỉ bảo đảm trong MỘT tiến trình API** (production hiện chạy một tiến trình uvicorn):
- Trần thưởng game là **cứng** trong một tiến trình (khoá quyết toán theo người): 5 trận cùng cặp kết thúc đồng thời → 3/3; 9 trận thắng đồng thời → XP game đúng 30/30 (tiềm năng 45); 6 lượt Memory → 5/5.
- Hàng đợi ghi XP theo người (tối ưu độ sống; tính đúng không phụ thuộc vào nó).

**Không bảo đảm khi nhiều tiến trình/instance:**
- Trần thưởng là **mềm**: lần đo 2 tiến trình ra 3/3 nhưng đó là số đo, không phải bảo đảm.
- Dưới tranh chấp rất cao giữa nhiều tiến trình, một lần ghi XP có thể trả 503 sau khi hết lượt thử (tính đúng giữ nguyên: không mất một phần, không nhân đôi). Quyết toán game tự phục hồi qua `settle_pending`; nhiệm vụ/mở gói trả 503 và thử lại được; **đường XP xuất bản (có từ trước, `except Exception: pass`) sẽ mất lần cộng đó**.
- Không tuyên bố chống bot/tài khoản phụ tuyệt đối.

## 6. Đề xuất migration production + rollback (CHƯA chạy — cần duyệt riêng)

1. Merge #229 và #231 (C mang sửa `setup_appwrite` — **không** chạy migration A bằng script cũ trên production).
2. Sao lưu: snapshot volume MongoDB của Appwrite production (hoặc `mongodump`) + ghi lại Version ID worker web hiện tại.
3. Deploy API với **mọi cờ tắt** (đã chứng minh chạy đúng trên schema cũ và mới).
4. Rào: xác nhận endpoint/project/db là production **đúng ý định**, dùng khoá **schema** riêng (không dùng khoá runtime); `python -m scripts.setup_appwrite --dry-run`, rồi chạy thật.
5. Đối soát từng mục (đọc `/attributes` và `/indexes`, không đọc tài liệu collection): 0 thiếu, 0 chưa available, `target_kind` có `user`. Khởi động lại API sau migration (danh sách thuộc tính hồ sơ được đọc một lần mỗi tiến trình).
6. Bật lần lượt, quan sát giữa mỗi bước: `FAS_SOCIAL_V1_SCHEMA=1` → `FAS_XP_ATOMIC=1` → (duyệt riêng, hiện MULTIPLAYER_PRODUCTION_BLOCKED) `FAS_GAMES_V1=1`.

**Rollback:** tắt cờ (tức thì; mã chạy đúng với thuộc tính thừa — đã chứng minh 25/25). Schema để nguyên (additive). Chỉ khi thật cần mới xoá 6 collection game + `xp_progress_cas` + `user_blocks` (mất dữ liệu game/chặn); **không** thu hẹp enum `target_kind` khi đã có hàng `user`. Web: `npx wrangler rollback <Version ID đã ghi>`.

## 7. Giới hạn còn lại

- Chưa kiểm sinh TTS production (không tạo job production); E2E Piper cục bộ không thay thế được.
- `record_quest_event` vẫn đọc-sửa-ghi: bình luận đồng thời có thể mất một lần đếm tiến độ nhiệm vụ (không mất XP).
- Đường XP xuất bản nuốt lỗi (có từ trước) — xem §5.
- Mở gói đồng thời có thể hiển thị nhầm "trùng lặp" (không cấp trùng) — LOW.
- Appwrite 1.9.6 giữ tài liệu collection cũ trong cache không hết hạn (lỗi phía Appwrite): script đã tránh; mọi đoạn mã khác đọc trạng thái từ tài liệu collection cần cùng cách.
- Bộ test backend CI còn 734 lỗi baseline (#223, rate limiter toàn cục) — #229/#231 cùng tập hỏng theo tên với `main` (khác duy nhất: một test được đổi tên ở A, cùng lỗi `KeyError: 'token'`).

# Chat V1: tin nhắn chữ trên Appwrite

**Trạng thái (2026-09-28):** đã hiện thực, kiểm thật trên `fanfic-staging` (Appwrite Cloud 2.3) **và** trên một Appwrite **1.9.6 + MongoDB dùng một lần** (đúng dòng production), cả hai với người dùng tổng hợp `@example.test`.

**Production chưa bật gì — hai cờ đều TẮT mặc định:**

| Lớp | Cờ | Mặc định | Tắt thì |
|---|---|---|---|
| Máy chủ | `FAS_CHAT_V1` | tắt khi `DATA_BACKEND=appwrite` | mọi `/api/chat/*` trả 503 `chat_not_configured` |
| Web (lúc build) | `NEXT_PUBLIC_CHAT_V1_ENABLED=1` → `CHAT_V1_ENABLED` (`web/src/lib/features.ts`) | tắt | không nút Tin nhắn, không nút "Nhắn tin" ở hồ sơ, `/messages` báo "Tin nhắn chưa mở", **0 request `/api/chat`** (đo trên Chrome: 0/22) |

Merge vào `main` rồi deploy web **không** tự mở tính năng. Chưa tạo bảng `chat_*` nào trên production, chưa deploy.

**Tencent Chat không còn trong đường tin nhắn chữ:** không có `@tencentcloud/chat` trong web, `/api/chat/session` không ký UserSig, không có tệp Tencent nào trong PR. Tencent/TRTC để dành cho gọi thoại/video sau này; ID người dùng `fw_<uid>` (≤ 32 byte) giữ nguyên để TRTC dùng chung.

## Kiến trúc

```
Trình duyệt ──(REST + SSE qua fetch, Bearer)──► API Fanfic ──(khoá máy chủ: ghi)──► Appwrite
     ▲                                            │
     └────────── sự kiện đã lọc ◄──(WebSocket bằng SESSION CỦA NGƯỜI XEM)── Appwrite Realtime
```

- **Appwrite sở hữu dữ liệu và Realtime.** Backend chỉ là lớp chuyển tiếp mỏng. Trình duyệt **chỉ biết `NEXT_PUBLIC_API_BASE`**: không SDK Appwrite, không WebSocket trực tiếp, endpoint Appwrite không lộ ra trình duyệt.
- **Luồng `/api/chat/stream`:** máy chủ mở WebSocket tới Appwrite Realtime, xác thực bằng **chính session của người xem** (token Fanfic *là* session secret Appwrite — thiết kế có sẵn), **không bao giờ** bằng khoá API. Appwrite tự lọc sự kiện theo quyền đọc từng dòng; service lọc thêm một lần.
- **Nhiều instance backend** không cần pub/sub nội bộ, vì Appwrite đã là pub/sub.

## Tầng mã

Tất cả ở `server/messaging/` (**không** nhầm với `server/chat/` là AI Chat/RAG).

| Tệp | Vai trò |
|---|---|
| `ids.py` | ID tất định: người dùng `fw_<uid>`; hội thoại `dm_<băm cặp>`; thành viên `cm_…`; tin `m_<client_id>`; chặn `blk_<sha256(chặn, bị chặn, kind)[:24]>` (**đúng định dạng #229**) |
| `domain.py` | Mô hình (`Conversation`, `Member`, `Message`, `Block`…) và lỗi có mã ổn định. Không biết kho lưu trữ |
| `repository.py` | **Hợp đồng `ChatRepository`** + bản trong bộ nhớ (mock/test) |
| `appwrite.py` | **Hai hiện thực của CÙNG hợp đồng**, khác nhau DUY NHẤT ở ba hằng số (đường dẫn, khoá ID, khoá danh sách) |
| `service.py` | Nghiệp vụ; chỉ nói chuyện với hợp đồng kho — không biết phiên bản Appwrite |
| `realtime.py` | Appwrite Realtime → sự kiện (đăng ký tên kênh kiểu cũ — có mặt trên cả 2.3 lẫn 1.9.6) |
| `runtime.py` | Nơi duy nhất chọn kho: `FAS_CHAT_APPWRITE_API` |
| `routes.py` | `/api/chat/*` (REST + SSE); route gửi có `Server-Timing` |

| `FAS_CHAT_APPWRITE_API` | Kho | API | Dùng cho |
|---|---|---|---|
| rỗng / `legacy` | `LegacyAppwriteChatRepository` | `/v1/databases/{db}/collections/{c}/documents` | **Production 1.9.6** (mặc định) |
| `tablesdb` | `TablesDBChatRepository` | `/v1/tablesdb/{db}/tables/{t}/rows` | Staging Cloud 2.3 |
| giá trị khác | — | — | chat TẮT, có lý do (không tự dò phiên bản) |

Cả hai dùng `/v1/tablesdb/transactions` cho giao dịch (1.9.6 đã có; production đang dùng cho `job_locks`).

## Bảng (`scripts/setup_appwrite.py`)

Quyền **cấp bảng rỗng**: không người dùng nào tự tạo/sửa dòng (đo: 401/403 trên cả hai phiên bản). Quyền dòng **chỉ là đọc**.

| Bảng | Quyền đọc dòng | Index |
|---|---|---|
| `chat_conversations` | A, B | `member_a`, `member_b` |
| `chat_messages` | A, B | `(conversation_id, created_at)`, `(conversation_id, recipient_id, created_at)` |
| `chat_members` | chính chủ | `(user_id, last_at)`, `(conversation_id)` |
| `chat_fanouts` | không ai | — (dòng đánh dấu "tin X đã phát tán") |
| `user_blocks` | **người chặn** | giống hệt #229 (`blocker_created_idx`, `blocked_kind_idx`, `blocker_kind_idx`) |

`user_blocks` là bảng của #229 (Community). PR này mang **bản sao y hệt** định nghĩa đó (đã so sánh bằng diff) vì #229 chưa merge được; khi #229 vào `main`, hai định nghĩa trùng nhau và `setup_appwrite` coi là "đã có".

## Ngữ nghĩa

- **Quyền DM:** mọi route gọi theo *người kia*; hội thoại = `dm_id(tôi, người kia)` nên người gọi **luôn** là thành viên; không có tham số `conversation_id` để đoán; không nhắn cho chính mình (400); người không tồn tại 404; con trỏ của hội thoại khác trả **cùng lỗi** với con trỏ rác.
- **Gửi idempotent, phát tán đúng một lần:**
  - client chọn `client_id`; ID tin = `m_<client_id>`, cũng là ID tin "đang gửi" trên giao diện; gửi lại trả **tin gốc**; `client_id` của người khác → 409;
  - giao dịch {tạo `chat_fanouts/f<id>` + `increment unread_count`} được **chuẩn bị song song** với các phép kiểm; tin tạo **ngoài** giao dịch (dòng tạo trong giao dịch không phát Realtime); **commit luôn sau khi tin tồn tại**; trùng dòng đánh dấu → 409 → không cộng lần hai;
  - bị chặn / người không tồn tại: trả lỗi **ngay**, giao dịch đã chuẩn bị bị huỷ khi nó chuẩn bị xong (không bao giờ commit).
- **Chưa đọc / đã đọc:** chưa đọc = số tin *gửi cho tôi* sau mốc đã đọc; `read` **đếm lại** từ kho rồi đếm thêm lần nữa sau khi ghi; tổng trên nút Tin nhắn không tính hội thoại tắt tiếng.
- **Chặn (mức TÀI KHOẢN, dùng chung `user_blocks` với #229):**
  - một dòng `kind="block"`; chặn **hai chiều**: cả người chặn lẫn người bị chặn đều nhận 403 `chat_blocked` khi gửi tin mới;
  - **lịch sử cũ giữ nguyên** cho cả hai; tin bị từ chối không cộng chưa đọc, không phát Realtime;
  - người bị chặn **không** biết ai chặn mình (`/api/chat/blocks` chỉ liệt kê người *mình* chặn; dòng chỉ người chặn đọc được — đo: người bị chặn GET thẳng Appwrite → 404);
  - `kind="mute"` của #229 là *tắt nội dung cộng đồng*, **không** chặn tin nhắn.
- **Tắt tiếng (RIÊNG từng hội thoại, `chat_members.muted`):** tin vẫn đến và vẫn đếm chưa đọc trong hội thoại đó, nhưng không vào tổng trên nút Tin nhắn; hiện 🔕 và chấm chưa đọc màu mờ.
- **Giao diện:** menu "⋯" ở đầu cuộc trò chuyện (drawer và `/messages`): Tắt/Bật thông báo (làm ngay), **Chặn** (qua `ConfirmDialog` danger, render bằng portal vào `body` vì `.chat-drawer` có `backdrop-filter`), Bỏ chặn. Đã chặn thì ô soạn được thay bằng dòng "Bạn đã chặn … · Bỏ chặn". Trước khi hộp thư / danh sách chặn tải xong, mục tương ứng hiện "Đang tải…" và bị khoá — không đoán trạng thái.
- **Bản xem trước hộp thư:** luôn là tin *mới nhất thật*, cập nhật **sau khi trả response** (idempotent, tự sửa ở lần gửi sau). Tin + "+1 chưa đọc" luôn xong **trước** khi trả.
- **Nối lại (web):** lùi 1 s → 30 s; watchdog im lặng 45 s thì cắt; `offline` cắt, `online` nối **ngay**; sau mỗi lần nối lại tải lại hộp thư và **bù khoảng trống** (`after=`).
- **Giới hạn:** gửi 30/phút; đọc 120/phút; ghi 60/phút; mở luồng 12/phút; tối đa 8 luồng đồng thời mỗi người **mỗi instance**; luồng sống tối đa 25 phút rồi tự nối lại.

## Ngữ nghĩa đo được: Cloud 2.3 so với 1.9.6 + MongoDB

Cùng một script thăm dò, bảng tạm + người dùng tạm, tự dọn.

| # | Hạng mục | Cloud 2.3 (staging) | 1.9.6 + MongoDB (máy kiểm) |
|---|---|---|---|
| 1 | Realtime xác thực bằng session secret → đúng người | có | có |
| 2 | Người thứ ba nhận sự kiện của dòng chỉ A/B đọc | không | không |
| 3 | Hai socket cùng người đều nhận | có | có |
| 4 | Tên kênh trên sự kiện | kiểu cũ + TablesDB | kiểu cũ + TablesDB (`databases.collections`, `databases.tables`, `tablesdb.tables`) |
| 5 | Dòng **tạo trong giao dịch** phát Realtime | không | không |
| 6 | Trùng rowId trong giao dịch | 409 `transaction_conflict`, không áp dụng gì | 409 `transaction_conflict`, không áp dụng gì |
| 7 | 5 giao dịch đồng thời `increment` một dòng | cả 5 commit | cả 5 commit (đếm = 6) |
| 8 | Cập nhật / increment (kể cả trong giao dịch) phát sự kiện | có | có (kể cả cập nhật không đổi giá trị) |
| 9 | `total` khi `limit(1)` | tổng thật | tổng thật |

**Khác biệt thật đã gặp** (đều ở công cụ/khoá, không ở ngữ nghĩa chat):

| Hạng mục | Cloud 2.3 | 1.9.6 + MongoDB |
|---|---|---|
| `GET collection` khi chờ thuộc tính sẵn sàng | trạng thái đúng | **bộ đệm cũ**: `novels.dub_audio_key` mãi "processing" trong khi `GET …/attributes/dub_audio_key` = "available" → `setup_appwrite` cũ báo kẹt sau 120 s. **Đã sửa**: chờ theo endpoint từng mục; 404 ngay sau POST = "chưa hiện", chờ tiếp |
| `GET /health/version` kèm khoá | — | 401 (cần scope `public`) → rào máy kiểm gọi không kèm khoá |
| Tạo khoá API (console) | — | bắt buộc `keyId`; không có scope `transactions.*` (giao dịch dùng `rows.*`) |
| Độ trễ một thao tác kho (trung vị) | GET 251 · truy vấn 273 · stage 856 · tạo tin 246 · commit 614 ms (VN → SGP) | GET 11 · truy vấn 13 · stage 33 · tạo tin 15 · commit 66 ms (loopback) |

## Kết quả kiểm

| Mức | Kết quả |
|---|---|
| Đơn vị `server/tests/test_messaging.py` + `test_chat_session.py` | **51/51** (cả hai kho Appwrite qua kho giả, thứ tự phát tán, chặn #229, cuộc hội thoại) |
| `scripts/tests/test_chat_parity_guard.py` + `test_setup_appwrite_readiness.py` | **25/25** |
| Web `realtime-chat-v1.test.mjs` (23) + toàn bộ | **1141/1147** (0 hỏng, 6 bỏ qua); typecheck 0; lint 0 lỗi |
| Sống — **TablesDB trên Cloud 2.3** (`scripts.staging.run_live --mo-dun test_chat_live --chat-api tablesdb`) | **10/10** |
| Sống — **Legacy trên Cloud 2.3** (`--chat-api legacy`) | **10/10** |
| Sống — **Legacy trên 1.9.6 + MongoDB** (`scripts.chat_parity.run_parity --chat-api legacy`) | **10/10** |
| Sống — **TablesDB trên 1.9.6 + MongoDB** | **10/10** |
| Chrome hiện, cờ bật: chặn / tắt tiếng / drawer / 390 px | **32/32** |
| Chrome hiện, cờ tắt (như production) | **7/7**, 0 request `/api/chat` |

Bộ test sống (cùng một tệp cho mọi đích) kiểm: quyền DM + truy cập **thẳng Appwrite** bằng session người thứ ba (404, danh sách không lộ tin, hàng hội thoại không đọc được); không ai tự ghi/sửa dòng; 6 lần gửi đồng thời cùng `client_id` → đúng 1 tin, 1 lượt chưa đọc; chưa đọc/đã đọc tới mốc; tắt tiếng không vào tổng; phân trang lùi không trùng/sót + tiến sau con trỏ; chặn hai chiều từ cả hai phía, dòng `user_blocks` định dạng #229 chỉ người chặn đọc được, lịch sử còn, bỏ chặn gửi lại được; Realtime tới hai phía + tab thứ hai, người thứ ba 0 sự kiện; mất kết nối thì bù khoảng trống.

## Độ trễ người gửi (ACK)

Hồ sơ theo pha có ở header `Server-Timing` của route gửi: `xac_thuc`, `kiem`, `tao_tin`, `cho_gd`, `phat_tan`, `tong`.

Đo **tuần tự** 12 tin/lần, mã cũ (#247) và mã mới chạy **xen kẽ** cùng mạng (VN → SGP) để khử nhiễu:

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| ACK trung vị, vòng 1 | 2226 ms | **1430 ms** |
| ACK trung vị, vòng 2 | 3518 ms | **1485 ms** |
| ACK p90 (vòng 1 / 2) | 2778 / 4357 ms | 1715 / 1626 ms |
| Tin đầu tiên (tạo hội thoại) | 3368 / 5684 ms | 1729 / 2068 ms |
| ACK trên 1.9.6 cùng máy (≈ production nếu API và Appwrite cùng nơi) | — | **158 ms** (Legacy), Realtime 86 ms |

Thời gian đi đâu (staging, sau sửa, trung vị): xác thực ~80–100 · kiểm ~120 · tạo tin ~115 · chờ giao dịch ~330 · commit ~400 ms. Phần lớn là **API giao dịch của Cloud** (stage ≈ 850 ms, commit ≈ 600 ms mỗi lần) cộng RTT ~114 ms tới SGP. Ba thay đổi rủi ro thấp, **không** nới "đúng một lần":

1. xác thực nhẹ cho route chat (chỉ `GET /v1/account`, vẫn xác minh **mỗi** request, không bộ nhớ đệm);
2. giao dịch được chuẩn bị song song với phép kiểm và chỉ được **chờ sau khi tạo tin** (commit vẫn luôn sau tạo tin);
3. tin đầu tiên tạo hàng hội thoại + hai hàng thành viên song song.

Không làm (vì đổi đúng-một-lần hoặc bảo mật): commit sau khi trả lời; tạo tin song song với phép kiểm chặn; nhớ đệm token.

## Máy kiểm tương đương production (`scripts/chat_parity/`)

```bash
# Trên một máy có Docker (đã làm trên Lightning CPU Studio), Appwrite 1.9.6 + MongoDB, CHỈ bind 127.0.0.1
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD/appwrite:/usr/src/code/appwrite:rw" \
  --entrypoint=install appwrite/appwrite:1.9.6 --http-port=8080 --https-port=8443 \
  --interactive=N --no-start=true --database=mongodb
#  -> đổi cổng traefik thành 127.0.0.1:${_APP_HTTP_PORT}; _APP_OPTIONS_ABUSE=disabled (nhiều tài khoản từ một IP)
(cd appwrite && docker compose up -d)
python -m scripts.chat_parity.bootstrap --endpoint http://127.0.0.1:8080/v1 --ra parity.json   # project + khoá + schema
python -m scripts.chat_parity.run_parity --cau-hinh parity.json --chat-api legacy               # bộ test sống
python -m scripts.chat_parity.run_parity --cau-hinh parity.json --chat-api legacy --do-tre 8    # độ trễ từng thao tác
```

Rào `guard.py` (fail-closed): chỉ **IP loopback** (không tên miền nào, kể cả `localhost`; không `user@host`), project `parity-*`, Appwrite **1.9.x**, mọi tài khoản `@example.test`, không trùng toạ độ production (`scripts/ops/cutover_target.py`), tiến trình con nhận môi trường tối thiểu và không cho ghi đè `APPWRITE_*`. `parity.json` chỉ nằm trên máy kiểm (600).

## Kế hoạch tạo schema trên production (CHƯA làm — chủ dự án chạy, sau khi duyệt)

Chỉ **thêm** bảng mới; không đụng bảng đang có. Chạy trên môi trường production (khoá schema `APPWRITE_SCHEMA_API_KEY`), từng bảng, xem trước bằng `--dry-run`:

```bash
python -m scripts.setup_appwrite --dry-run --only chat_conversations   # lặp lại cho từng bảng bên dưới
python -m scripts.setup_appwrite --only chat_conversations
python -m scripts.setup_appwrite --only chat_messages
python -m scripts.setup_appwrite --only chat_members
python -m scripts.setup_appwrite --only chat_fanouts
python -m scripts.setup_appwrite --only user_blocks    # nếu #229 đã tạo thì script báo "đã có", không đổi gì
```

Script chờ **từng** thuộc tính/index "available" theo endpoint từng mục (đã chạy trọn schema 787 mục trên 1.9.6 + MongoDB sạch: 0 lỗi). **Không** đặt `FAS_CHAT_V1=1`, **không** build web với cờ Chat V1 trong bước này.

**Trước khi BẬT (bước sau, cần duyệt riêng):**
1. #229 (hoặc riêng hai commit `69aaf4f` + `399f5fb` của nó) phải vào `main`: nếu không, một lần Appwrite trả 5xx cho `GET /v1/account` (đã gặp trên 1.9.6 + Mongo khi nhiều request đồng thời) bị ánh xạ thành **401** và luồng chat tự dừng tới khi tải lại trang.
2. Chạy `scripts.chat_parity.run_parity` trên máy kiểm với đúng commit sẽ deploy.
3. Máy chủ: `FAS_CHAT_V1=1` (để trống `FAS_CHAT_APPWRITE_API` = legacy). Web: build với `NEXT_PUBLIC_CHAT_V1_ENABLED=1`.

**Rollback:**
- Tắt ngay: `FAS_CHAT_V1=0` (API trả 503, giao diện hiện lỗi trung thực) và/hoặc build lại web không có cờ (mọi UI chat biến mất, 0 request). Không cần xoá dữ liệu.
- Gỡ hẳn: xoá 4 bảng `chat_*` — chỉ mất tin nhắn. **Không** xoá `user_blocks` nếu #229 đang dùng.

**Dọn staging:** `python -m scripts.staging.reset --du-lieu --apply` (xoá tài khoản `@example.test` và dữ liệu tổng hợp). Bảng `chat_blocks` cũ trên staging không còn được dùng (chặn đã chuyển sang `user_blocks`); để nguyên, không xoá tự động.

## Giới hạn đã biết

1. **Sập máy chủ đúng giữa "tạo tin" và "commit"**: tin đã có nhưng "+1 chưa đọc" chưa cộng; nếu client không gửi lại, huy hiệu của người nhận thiếu 1 cho tới lần mở hội thoại (lúc đó đếm lại chính xác). Chỉ xảy ra khi sập; review độc lập ghi nhận là rủi ro còn lại.
2. **5xx của Appwrite → 401** ở `appwrite_adapter` (mã có sẵn, dùng chung) — xem điều kiện 1 ở trên.
3. Gõ trước khi "sẵn sàng" thì Enter bị bỏ qua lặng lẽ (hành vi có sẵn từ #239). Chữ vẫn còn trong ô soạn.
4. Hộp thư tải 50 hội thoại gần nhất; tổng chưa đọc tính trên 50 hội thoại đó.
5. Hai lần gửi rất sát nhau có thể làm bản xem trước tạm là tin áp chót tới lần ghi sau (số chưa đọc luôn đếm lại đúng khi đọc).
6. Trần 8 luồng đồng thời tính theo từng instance (N worker → tối đa 8×N); hạn mức mở luồng 12/phút là lớp chặn chung.
7. Ngay sau khi tải lại trang, nếu danh sách chặn chưa về mà người dùng gửi cho người đã chặn, tin hiện "Không gửi được (mã 403)" rồi ô soạn đổi thành thông báo đã chặn.

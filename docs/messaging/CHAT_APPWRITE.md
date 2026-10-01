# Chat V1: tin nhắn chữ trên Appwrite

**Trạng thái (2026-09-29):** đã hiện thực, kiểm thật trên `fanfic-staging` (Appwrite Cloud 2.3) **và** trên một Appwrite **1.9.6 + MongoDB dùng một lần** (đúng dòng production), cả hai với người dùng tổng hợp `@example.test`. Giao diện desktop là **Chat Dock kiểu Messenger** (xem mục "Chat Dock"), có **nhãn dán** (mục "Nhãn dán") và **chỗ sẵn cho gọi thoại/video** (chưa có RTC).

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
- **Đường tắt cùng instance (`local_bus.py`):** tin vừa tạo xong trong kho được đẩy thẳng vào luồng SSE của người gửi/người nhận đang mở trên **chính tiến trình đó**, không chờ vòng Realtime. Realtime **vẫn là nguồn chính** (liên instance, bù khi mất kết nối); luồng SSE bỏ bản trùng theo ID tin (256 ID gần nhất). Tắt: `FAS_CHAT_LOCAL_FASTPATH=0`.

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
| `local_bus.py` | Đường tắt cùng instance: tin mới → luồng SSE của đúng hai người trong tin (lọc lại theo người xem) |
| `stickers.py` | Catalog nhãn dán (giao diện `StickerCatalog`), luật mở khoá phía máy chủ, URL tài sản |
| `runtime.py` | Nơi duy nhất chọn kho: `FAS_CHAT_APPWRITE_API`; bật/tắt đường tắt `FAS_CHAT_LOCAL_FASTPATH` |
| `routes.py` | `/api/chat/*` (REST + SSE); route gửi có `Server-Timing`; `GET /api/chat/stickers` |

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
| `chat_messages` | A, B | `(conversation_id, created_at)`, `(conversation_id, recipient_id, created_at)` — cột `kind` (`text`/`sticker`) + `sticker_id` (64, chỉ ghi khi là nhãn dán) |
| `chat_members` | chính chủ | `(user_id, last_at)`, `(conversation_id)` |
| `chat_fanouts` | không ai | — (dòng đánh dấu "tin X đã phát tán") |
| `user_blocks` | **người chặn** | giống hệt #229 (`blocker_created_idx`, `blocked_kind_idx`, `blocker_kind_idx`) |

`user_blocks` là bảng **chính tắc** của #229 (Social Play V1): nhánh này đã gộp #229 (`f91c6db`) nên chỉ còn **một** định nghĩa — của #229. Chặn ở chat **là** chặn tài khoản: khi năng lực `blocks` của Social bật, chat gọi `SocialService.block_user/unblock_user` (kèm bỏ theo dõi hai chiều như trang cá nhân); khi tắt, chat đọc/ghi thẳng CÙNG hàng đó (`RepoBlocks`, ID `social.block_key`).

## Ngữ nghĩa

- **Quyền DM:** mọi route gọi theo *người kia*; hội thoại = `dm_id(tôi, người kia)` nên người gọi **luôn** là thành viên; không có tham số `conversation_id` để đoán; không nhắn cho chính mình (400); người không tồn tại 404; con trỏ của hội thoại khác trả **cùng lỗi** với con trỏ rác.
- **Gửi idempotent, phát tán đúng một lần:**
  - client chọn `client_id`; ID tin = `m_<client_id>`, cũng là ID tin "đang gửi" trên giao diện; gửi lại trả **tin gốc**; `client_id` của người khác → 409;
  - giao dịch {tạo `chat_fanouts/f<id>` + `increment unread_count`} được **chuẩn bị song song** với các phép kiểm; tin tạo **ngoài** giao dịch (dòng tạo trong giao dịch không phát Realtime); **commit luôn sau khi tin tồn tại**; trùng dòng đánh dấu → 409 → không cộng lần hai;
  - bị chặn / người không tồn tại: trả lỗi **ngay**, giao dịch đã chuẩn bị bị huỷ khi nó chuẩn bị xong (không bao giờ commit).
- **Chưa đọc / đã đọc:** chưa đọc = số tin *gửi cho tôi* sau mốc đã đọc; `read` **đếm lại** từ kho rồi đếm thêm lần nữa sau khi ghi; tổng trên nút Tin nhắn không tính hội thoại tắt tiếng. **Cuộc đua "đọc trước +1":** người nhận đang mở cửa sổ nhận tin (qua đường tắt) và `read` đếm TRƯỚC khi "+1" của chính tin đó được commit → "+1" rơi xuống sau → 1 chưa đọc cho tin đã đọc. Bước xem trước (chạy sau commit) sửa: mốc đã đọc **là** tin mới nhất (so theo ID tin, không so thời gian — hai tin cùng mili-giây là chuyện thường) mà vẫn còn chưa đọc → đếm lại. Giao diện chỉ đánh dấu đã đọc khi cửa sổ **đang hiện và không thu nhỏ** (hoặc đang mở ở `/messages`).
- **Chặn (mức TÀI KHOẢN, dùng chung `user_blocks` với #229):**
  - một dòng `kind="block"`; chặn **hai chiều**: cả người chặn lẫn người bị chặn đều nhận 403 `chat_blocked` khi gửi tin mới;
  - **lịch sử cũ giữ nguyên** cho cả hai; tin bị từ chối không cộng chưa đọc, không phát Realtime;
  - người bị chặn **không** biết ai chặn mình (`/api/chat/blocks` chỉ liệt kê người *mình* chặn; dòng chỉ người chặn đọc được — đo: người bị chặn GET thẳng Appwrite → 404);
  - `kind="mute"` của #229 là *tắt nội dung cộng đồng*, **không** chặn tin nhắn.
- **Tắt tiếng (RIÊNG từng hội thoại, `chat_members.muted`):** tin vẫn đến và vẫn đếm chưa đọc trong hội thoại đó, nhưng không vào tổng trên nút Tin nhắn; hiện 🔕 và chấm chưa đọc màu mờ.
- **Giao diện:** menu "⋯" ở đầu cuộc trò chuyện (cửa sổ dock và `/messages`): Xem hồ sơ, Mở trong trang Tin nhắn, Tắt/Bật thông báo (làm ngay), **Chặn** (qua `ConfirmDialog` danger, render bằng portal vào `body`), Bỏ chặn, **Báo cáo** (`ReportDialog` của #229). Đã chặn thì ô soạn được thay bằng dòng "Bạn đã chặn … · Bỏ chặn". Trước khi hộp thư / danh sách chặn tải xong, mục tương ứng hiện "Đang tải…" và bị khoá — không đoán trạng thái.
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
| Tạo **index** ngay sau thuộc tính (cùng bệnh bộ đệm) | trạng thái đúng | đo 2026-09-29 (`user_follows.created_at`): từng mục "available", tài liệu collection vẫn "processing" → `POST …/indexes` **400 "not yet available"**, chạy lại **chết đúng chỗ đó**. **Đã sửa**: khi mọi thuộc tính của index "available" theo từng mục, gửi **một** `PUT` collection **không đổi gì** (tên, quyền, `documentSecurity`, `enabled` đọc lại và gửi tường minh, kiểm cả kiểu) để làm mới bộ đệm rồi thử lại, tối đa 2 lần. Đã chứng minh trên máy kiểm: "processing" → "available", `documentSecurity=true` và quyền `[]` giữ nguyên |
| `GET /health/version` kèm khoá | — | 401 (cần scope `public`) → rào máy kiểm gọi không kèm khoá |
| Tạo khoá API (console) | — | bắt buộc `keyId`; không có scope `transactions.*` (giao dịch dùng `rows.*`) |
| Độ trễ một thao tác kho (trung vị) | GET 251 · truy vấn 273 · stage 856 · tạo tin 246 · commit 614 ms (VN → SGP) | GET 11 · truy vấn 13 · stage 33 · tạo tin 15 · commit 66 ms (loopback) |

## Chat Dock (giao diện kiểu Messenger)

`ChatProvider` + `ChatDock` gắn **một lần** ở `app/layout.tsx`: đổi trang chỉ thay `{children}` nên cửa sổ, nháp và **một** luồng SSE sống xuyên route (đo trên Chrome: Community → hồ sơ → DM → Thư viện → Truyện → Chương, luồng mở 4 → 4, không mở lại). Logic thuần ở `web/src/lib/chat/dock.ts` (test bằng `node --test`).

| Bề rộng | Hành vi |
|---|---|
| ≥ 1024 px | tối đa **3** cửa sổ nổi góc dưới-phải (336 px; 1024–1279: 304 px để vẫn vừa 3), mới nhất sát mép phải; cửa sổ thứ 4+ vào **ngăn tràn "+N"** (có chấm chưa đọc); mở từ ngăn tràn = đưa lên đầu |
| 641–1023 px | tối đa **1** cửa sổ |
| ≤ 640 px | **không** cửa sổ nổi — mở chat = `/messages?c=…` toàn màn hình; nút chạm ≥ 44 px, không tràn ngang |

- Thu nhỏ / khôi phục / đóng; **không kéo thả** (cố ý). Thu nhỏ: chỉ thanh đầu + chấm chưa đọc riêng, **không** đánh dấu đã đọc. Khôi phục/mở do người dùng bấm → tiêu điểm vào ô soạn; phục hồi sau tải lại → **không** cướp tiêu điểm.
- **Nháp theo từng cuộc** + danh sách cửa sổ (kể cả trạng thái thu nhỏ) lưu `sessionStorage` của tab, đọc **một lần** lúc hydrate, không ghi đè trước khi phục hồi; đăng xuất xoá cả hai.
- Đầu cửa sổ: `UserAvatar` + khung, tên, `Lv. N · danh xưng` (`CapDoTaiKhoan`, cùng component với trang cá nhân); **không** chấm "đang hoạt động" (máy chủ chưa có trạng thái thật); nút gọi thoại/video (vô hiệu, xem dưới); menu ⋯.
- Ô soạn: Enter gửi, Shift+Enter xuống dòng, **an toàn IME** (Telex/VNI, Hàn, Nhật: `isComposing`/keyCode 229 — đo bằng `Input.imeSetComposition`); lạc quan 10–15 ms rồi đối chiếu máy chủ; chống gửi trùng 800 ms (Enter kép = 1 tin); 😊 emoji, 🏷️ nhãn dán, 📎 đính kèm **vô hiệu "sắp có"** (không giả vờ).
- Đang đọc tin cũ: tin mới **không** kéo cuộn, hiện nút "Tin mới ↓"; "Tải tin cũ hơn" giữ nguyên dòng đang đọc.

## Nhãn dán

- Tin nhãn dán chỉ mang **mã** (`kind="sticker"`, `sticker_id` dạng `goi.ma`), **không** nhúng ảnh; `text` là nhãn thay thế do **máy chủ** sinh ("Nhãn dán: Vẫy tay") cho hộp thư, thông báo và trình đọc màn hình. Mã không còn trong catalog → `sticker: null`, giao diện hiện nhãn thay thế.
- **Mở khoá do máy chủ quyết** (fail-closed: không đọc được cấp → Lv. 0): `free` · `level` (cấp XP) · `achievement` · `event` · `season`. Gói khoá → 403 `chat_sticker_locked`, không tạo tin, không +1. Người xem thấy gói khoá với điều kiện mở ("Mở khoá ở Lv. 5").
- **Kho:** metadata sau này ở Appwrite (`sticker_packs`, `stickers` — chưa tạo; giao diện `StickerCatalog` đã sẵn), ảnh ở R2 qua `FAS_STICKER_ASSET_BASE` (mặc định `/stickers` = `web/public/stickers`). Hiện là **3 gói placeholder phát triển** (16 SVG tự vẽ, 38 KB; không có tranh của bên thứ ba).
- Bộ chọn: tab Gần đây, Yêu thích (lưu `localStorage` theo người — giao diện sẵn cho đồng bộ máy chủ sau), từng gói; tải catalog lười khi mở lần đầu (`GET /api/chat/stickers`, `Cache-Control: private, max-age=300`).

## Gọi thoại / video (chưa có — để dành Tencent TRTC)

`web/src/lib/chat/calls.ts` là **điểm nối duy nhất**: `CallCapabilities { voice, video }` = `CALLS_UNAVAILABLE` (cả hai `false`). Nút ở đầu cửa sổ **vô hiệu** với chú thích "sắp có"; không xin micro/camera, không tải SDK. Khi làm TRTC: máy chủ ký UserSig (chỉ backend biết khoá), dùng lại ID `fw_<uid>`; bật khả năng trong `calls.ts` là đủ để nút sống.

## Kết quả kiểm

| Mức | Kết quả (2026-09-29) |
|---|---|
| Đơn vị `server/tests/test_messaging.py` + `test_chat_session.py` | **66/66** (thêm: đường tắt trùng/không lọt người thứ ba/gỡ đăng ký, cuộc đua đọc trước +1, nhãn dán khoá/không rõ, chặn chính tắc qua Social) |
| Nhóm backend liên quan (messaging + social + setup + staging guard + TablesDB compat + rate limit) | **489/489** |
| `scripts/tests/test_chat_parity_guard.py` + `test_setup_appwrite_readiness.py` | **34/34** (thêm 6 bài làm mới bộ đệm index 1.9.6) |
| Web `realtime-chat-v1.test.mjs` (28) + toàn bộ | **1168/1174** (0 hỏng, 6 bỏ qua); typecheck 0; lint 0 lỗi |
| Sống — **Cloud 2.3** bộ `test_chat_live` | **10/10** |
| Sống — **Cloud 2.3** nhãn dán + chặn chính tắc (`kiem_nhan_dan_song`) | **13/13** |
| Sống — **1.9.6 + MongoDB**, Legacy / TablesDB bộ `test_chat_live` | **10/10** / **10/10** |
| Sống — **1.9.6 + MongoDB** nhãn dán + chặn chính tắc, Legacy / TablesDB | **13/13** / **13/13** |
| Chrome hiện, cờ bật, backend thật → staging: ma trận Chat Dock (1600/1440/1024/800/390) | **56/56** |
| Chrome hiện, cờ tắt (như production) | **7/7**, 0 request `/api/chat` (lần trước; phần cờ không đổi) |

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

### Đo lại 2026-09-29 (backend thật `uvicorn`, staging VN → SGP, 15 tin; trình duyệt 12 tin)

| Hạng mục | Trước khi sửa (chỉ Realtime) | Sau khi sửa (đường tắt bật) |
|---|---|---|
| Lạc quan: Enter → tin trong DOM (Chrome) | — | **10–15 ms** (vẽ 14–39 ms); máy chủ giữ request 1,5 s: vẫn **13 ms** + "Đang gửi…" |
| Người nhận thấy tin, mức API (trung vị / p90 / max) | 358 / 467 / 757 ms | **263 / 310 / 326 ms** |
| Người nhận thấy tin, trong Chrome (trung vị / p90) | 393 / 421 ms | 361–413 / 402–434 ms (**ngang nhau trong sai số**) |
| ACK người gửi (trung vị / p90) | 1087 / 1153 ms | 971 / 1156 ms (không đổi đáng kể — do địa lý) |
| Server-Timing (trung vị): xác thực · kiểm · tạo tin · chờ GD · commit · tổng | 105 · 106 · 124 · 325 · 371 · 1081 | 62 · 98 · 93 · 332 · 371 · 966 |
| 1.9.6 cùng máy (≈ production): ACK / Realtime / tổng máy chủ | — | **160 ms / 95 ms / 146 ms** (tạo tin 11, stage 26, commit 46 ms) |

Kết luận trung thực: trên staging, người nhận đã dưới 500 ms **cả khi không có** đường tắt; đường tắt chủ yếu cắt **đuôi** (max 757 → 326 ms) và không phụ thuộc Realtime của Cloud. ACK ~1 s trên staging là **địa lý** (mỗi lệnh Appwrite ≈ 1 RTT 114 ms tới SGP, chuỗi bắt buộc tạo tin → commit); trên 1.9.6 cùng máy tổng máy chủ là 146 ms.

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

## Phát hành production (CHƯA làm gì — chủ dự án chạy từng bước, sau khi duyệt)

**Runbook từng lệnh (cổng backup, deploy, schema, canary, smoke, rollback): [`CHAT_CANARY_RUNBOOK.md`](CHAT_CANARY_RUNBOOK.md).**

**Phụ thuộc:** #229 (Social Play V1) vào `main` trước (nó mang định nghĩa `user_blocks` chính tắc + sửa 5xx→503 của `GET /v1/account`), rồi PR Chat này. Không có #229 thì một lần Appwrite 5xx cho `GET /v1/account` bị ánh xạ thành 401 và luồng chat tự dừng tới khi tải lại trang.

### Bước 0 — schema (chỉ THÊM bảng; cờ vẫn TẮT)

Trên máy của chủ dự án, env production + khoá schema `APPWRITE_SCHEMA_API_KEY`. **Trước hết xem kế hoạch CHỈ ĐỌC** — `--plan` gọi đúng các GET của Appwrite, phát hiện bảng/cột/index/quyền đã có và mọi chỗ KHÁC thiết kế; `_call` từ chối mọi phương thức khác GET trước khi gửi (đã chạy thật trên staging: 5/5 bảng, 0 lệch):

```bash
FAS_ENV_FILE=<tệp env production> python -m scripts.setup_appwrite --plan \
  --only user_blocks,chat_conversations,chat_members,chat_messages,chat_fanouts
```

Sau khi duyệt kế hoạch, tạo **từng bảng một** (thứ tự không quan trọng; `user_blocks` trước vì chặn dùng nó):

```bash
python -m scripts.setup_appwrite --only user_blocks          # đã có (do #229) -> "đã có", không đổi gì
python -m scripts.setup_appwrite --only chat_conversations
python -m scripts.setup_appwrite --only chat_members
python -m scripts.setup_appwrite --only chat_messages
python -m scripts.setup_appwrite --only chat_fanouts
```

Mỗi lệnh idempotent, chờ **từng** thuộc tính/index "available" theo endpoint từng mục, và tự vượt lỗi bộ đệm index của 1.9.6 (mục "Khác biệt thật"). Dòng in `(làm mới cache collection …)` là bình thường. Sau đó kiểm chỉ-đọc: `python -m scripts.setup_appwrite --dry-run` không đổi gì; `GET /api/health` production vẫn xanh. **Không** đặt `FAS_CHAT_V1`, **không** build web với cờ.

Dạng bảng chính xác (từ `SCHEMA`, quyền cấp bảng `[]`, `documentSecurity=true`):

| Bảng | Thuộc tính | Index |
|---|---|---|
| `user_blocks` (#229) | `block_id` s64 R · `blocker_id` s64 R · `blocked_id` s64 R · `kind` enum(block, mute) R · `created_at` dt R | `blocker_created_idx` (blocker_id, created_at) · `blocked_kind_idx` (blocked_id, kind) · `blocker_kind_idx` (blocker_id, kind) |
| `chat_conversations` | `kind` s16 R · `member_a` s36 R · `member_b` s36 R · `created_at` dt R | `member_a_idx` · `member_b_idx` |
| `chat_members` | `conversation_id` s40 R · `user_id` s36 R · `peer_id` s36 R · `unread_count` int · `last_read_at` dt · `last_read_message_id` s40 · `muted` bool · `last_message_id` s40 · `last_text` s200 · `last_at` dt · `last_sender_id` s36 · `updated_at` dt | `user_last_idx` (user_id, last_at) · `conv_idx` (conversation_id) |
| `chat_messages` | `conversation_id` s40 R · `sender_id` s36 R · `recipient_id` s36 R · `client_id` s32 R · `text` s2000 R · `created_at` dt R · `kind` s16 · `sticker_id` s64 | `conv_created_idx` (conversation_id, created_at) · `conv_recipient_created_idx` (conversation_id, recipient_id, created_at) |
| `chat_fanouts` | `message_id` s40 R · `created_at` dt R | — |

### Canary theo danh sách (máy chủ quyết, fail-closed)

| Biến (API) | Giá trị | Hiệu lực |
|---|---|---|
| `FAS_CHAT_V1` | `1` / trống | trống/`0` = không ai có chat (503) |
| `FAS_CHAT_V1_AUDIENCE` | `canary` (**mặc định trên Appwrite**) · `all` | giá trị khác = chat TẮT, có lý do |
| `FAS_CHAT_V1_CANARY_USERS` | user ID Fanfic, cách nhau dấu phẩy | **rỗng ở chế độ canary = KHÔNG AI**; chỉ nhận ID (email/đường dẫn bị bỏ, chỉ đếm); `describe()`/health chỉ in SỐ LƯỢNG |

- Mọi route chat (REST, SSE, `/api/chat/session`, `/api/chat/identities`) kiểm **mỗi request**: ngoài danh sách → 403 `chat_not_enabled`. Gỡ một ID = hết quyền ngay ở request kế tiếp, không xoá gì.
- Canary chỉ nhắn tin được với canary (403 `chat_peer_not_enabled`); `identities` có cờ `chat_enabled` để giao diện hiện "… chưa dùng được Tin nhắn trong giai đoạn thử" thay vì ô soạn. Chặn tài khoản vẫn dùng được (mức tài khoản, #229).
- `GET /api/chat/availability` → `{enabled, reason}` của **chính** người gọi, luôn 200. Web (khi build có cờ) hỏi **một lần mỗi lần tải trang**; chỉ `enabled:true` mới hiện nút Tin nhắn, nút Nhắn tin, dock, `/messages`; lỗi thì thử lại một lần rồi coi như TẮT. Người ngoài canary thấy y như hôm nay (chi phí: 1 request/lần tải trang cho người đã đăng nhập).
- Vì vậy **thứ tự bật không quan trọng**: web có cờ + máy chủ tắt → không ai thấy gì.
- Hai điều cố ý (review độc lập ghi nhận, chấp nhận): (1) chặn tạo trong giai đoạn canary là **chặn tài khoản thật** (cùng hàng `user_blocks` với nút Chặn ở trang cá nhân) nên vẫn còn sau khi mở rộng; (2) cờ `chat_enabled` trong `identities` cho người trong canary biết một người khác có trong canary hay không (chỉ boolean, chỉ người trong canary hỏi được; ID tài khoản vốn công khai).

### Bước 1 — bật máy chủ cho CANARY

1. Chạy lại máy kiểm 1.9.6 với **đúng commit sẽ deploy**: `bash parity_run.sh dunglai && bash parity_run.sh test legacy && bash parity_run.sh test tablesdb` (mong đợi 10/10 + 10/10).
2. Env API production (nơi đặt các biến `FAS_*` khác), rồi khởi động lại API:
   ```
   FAS_CHAT_V1=1
   FAS_CHAT_V1_AUDIENCE=canary
   FAS_CHAT_V1_CANARY_USERS=<uid_chu_du_an>,<uid_2>,<uid_3>      # 2–5 ID chủ dự án duyệt
   ```
   Để trống `FAS_CHAT_APPWRITE_API` (= legacy, đúng 1.9.6); giữ mặc định `FAS_CHAT_LOCAL_FASTPATH`.
3. Kiểm: `GET /api/health` có `messaging.audience = "canary"`, `canary_users = N`; bằng tài khoản canary `GET /api/chat/availability` → `{"enabled": true}`; bằng tài khoản thường → `{"enabled": false, "reason": "not_in_canary"}`.

### Bước 2 — web có cờ (cần một thay đổi workflow nhỏ, duyệt riêng)

`production-deploy.yml` **không** truyền `NEXT_PUBLIC_CHAT_V1_ENABLED` (mọi deploy tự động giữ chat TẮT). Đề xuất một dòng — **chưa làm, cần chủ dự án duyệt**: thêm `NEXT_PUBLIC_CHAT_V1_ENABLED: ${{ vars.PRODUCTION_CHAT_V1_ENABLED }}` vào bước "Cloudflare deploy (frontend)", rồi đặt biến repo `PRODUCTION_CHAT_V1_ENABLED=1` và chạy workflow deploy như thường. Đừng deploy tay có cờ: lần deploy tự động kế tiếp sẽ tắt lại.

### Bước 3 — mở rộng

Canary 2–5 người (≥ 48 giờ) → thêm ID theo đợt → `FAS_CHAT_V1_AUDIENCE=all`. Mỗi nấc theo dõi: tỉ lệ 5xx/403/429 của `/api/chat/*`, `Server-Timing` `tong` (1.9.6 cùng máy đo 146–154 ms), số luồng SSE đồng thời, lỗi Sentry `messaging`, báo cáo người dùng.

### Rollback

| Mức | Lệnh / thao tác | Hậu quả |
|---|---|---|
| Rút một người khỏi canary | bỏ ID khỏi `FAS_CHAT_V1_CANARY_USERS`, khởi động lại API | người đó 403 ngay; giao diện của họ ẩn ở lần tải trang sau; dữ liệu giữ nguyên |
| Thu hẹp từ "mọi người" về canary | `FAS_CHAT_V1_AUDIENCE=canary` (+ danh sách), khởi động lại API | ngoài danh sách 403; cuộc trò chuyện cũ với người ngoài danh sách hiện "chưa dùng được" |
| Tắt đường tắt (nếu nghi luồng SSE) | `FAS_CHAT_LOCAL_FASTPATH=0`, khởi động lại API | chỉ còn Realtime; người nhận chậm thêm ~100 ms |
| Tắt chat ngay | `FAS_CHAT_V1=0`, khởi động lại API | mọi `/api/chat/*` 503 `chat_not_configured`; giao diện báo lỗi trung thực; không mất dữ liệu |
| Gỡ giao diện | deploy web **không** cờ (deploy tự động mặc định đã vậy); hoặc `npx wrangler rollback` về version trước trên worker `fanfic-web` (kiểm đích bằng `npx wrangler deployments list --name fanfic-web` trước) | không nút, không request chat |
| Gỡ hẳn dữ liệu (chỉ khi quyết bỏ tính năng) | xoá 4 bảng `chat_*` trên Console | mất tin nhắn; **không** xoá `user_blocks` (chặn tài khoản của #229 dùng chung) |

**Dọn staging:** `python -m scripts.staging.reset --du-lieu --apply` (xoá tài khoản `@example.test` và dữ liệu tổng hợp). Bảng `chat_blocks` cũ trên staging không còn được dùng (chặn đã chuyển sang `user_blocks`); để nguyên, không xoá tự động.

## Giới hạn đã biết

1. **Sập máy chủ đúng giữa "tạo tin" và "commit"**: tin đã có nhưng "+1 chưa đọc" chưa cộng; nếu client không gửi lại, huy hiệu của người nhận thiếu 1 cho tới lần mở hội thoại (lúc đó đếm lại chính xác). Chỉ xảy ra khi sập; review độc lập ghi nhận là rủi ro còn lại.
2. **5xx của Appwrite → 401** ở `appwrite_adapter` (mã có sẵn, dùng chung) — xem điều kiện 1 ở trên.
3. Gõ trước khi "sẵn sàng" thì Enter bị bỏ qua lặng lẽ (hành vi có sẵn từ #239). Chữ vẫn còn trong ô soạn.
4. Hộp thư tải 50 hội thoại gần nhất; tổng chưa đọc tính trên 50 hội thoại đó.
5. Hai lần gửi rất sát nhau có thể làm bản xem trước tạm là tin áp chót tới lần ghi sau (số chưa đọc luôn đếm lại đúng khi đọc).
6. Trần 8 luồng đồng thời tính theo từng instance (N worker → tối đa 8×N); hạn mức mở luồng 12/phút là lớp chặn chung.
7. Ngay sau khi tải lại trang, nếu danh sách chặn chưa về mà người dùng gửi cho người đã chặn, tin hiện "Không gửi được (mã 403)" rồi ô soạn đổi thành thông báo đã chặn.
8. Đường tắt chỉ giúp khi hai người nối vào **cùng** instance; khác instance vẫn đi Realtime (đúng, chỉ không nhanh hơn).
9. Chặn và gửi không nằm trong một giao dịch (Appwrite không có giao dịch xuyên bảng cho phép kiểm): một tin gửi đúng lúc người kia vừa bấm chặn có thể lọt (cửa sổ dưới một giây; tin sau bị chặn) — review độc lập ghi nhận là chấp nhận được.
10. Cửa sổ dock nổi phủ lên nội dung trang (như Messenger); người đọc chương thu nhỏ/đóng cửa sổ nếu vướng.

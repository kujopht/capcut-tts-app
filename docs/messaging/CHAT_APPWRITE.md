# Chat V1: tin nhắn chữ trên Appwrite

**Trạng thái:** đã hiện thực và kiểm thật trên `fanfic-staging` (Appwrite Cloud 2.3) với người dùng tổng hợp.

**Production chưa bật gì:**
- `FAS_CHAT_V1` mặc định **TẮT** khi `DATA_BACKEND=appwrite`;
- chưa tạo bảng `chat_*` nào trên Appwrite 1.9.6;
- chưa deploy.

**Giao diện Chat V1 (#239) giữ nguyên:** không component nào trong `web/src/components/chat/` đổi giao diện. Chỉ transport và hai điểm nối trong `ChatProvider` thay đổi.

**Tencent Chat không còn cần cho tin nhắn chữ:**
- `@tencentcloud/chat` đã được gỡ khỏi web;
- `/api/chat/session` không còn ký UserSig;
- Tencent/TRTC để dành cho gọi thoại/video (`server/chat_tencent.py` giữ nguyên, kèm bài test).

## Kiến trúc

```
Trình duyệt ──(REST + SSE qua fetch, Bearer)──► API Fanfic ──(khoá máy chủ: ghi)──► Appwrite TablesDB
     ▲                                            │
     └────────── sự kiện đã lọc ◄──(WebSocket bằng SESSION CỦA NGƯỜI XEM)── Appwrite Realtime
```

- **Appwrite sở hữu dữ liệu và Realtime.** Backend chỉ là lớp chuyển tiếp mỏng. Trình duyệt vẫn **chỉ biết `NEXT_PUBLIC_API_BASE`**: không có SDK Appwrite, không mở WebSocket trực tiếp, và endpoint Appwrite không lộ ra trình duyệt.
- **Luồng `/api/chat/stream`:**
  - máy chủ mở WebSocket tới Appwrite Realtime và xác thực bằng **chính session của người xem** (token Fanfic *là* session secret Appwrite — thiết kế có sẵn), **không bao giờ** bằng khoá API;
  - vì vậy Appwrite tự lọc sự kiện theo quyền đọc của từng dòng;
  - service lọc thêm một lần nữa để phòng thủ nhiều lớp.
- **Nhiều instance backend** không cần pub/sub nội bộ, vì Appwrite đã là pub/sub.

## Tầng mã

Tất cả nằm ở `server/messaging/`. **Không** nhầm với `server/chat/`, là AI Chat/RAG.

| Tệp | Vai trò |
|---|---|
| `ids.py` | ID tất định: người dùng `fw_<uid>` (dùng chung với TRTC); hội thoại `dm_<băm cặp người>`; tin `m_<client_id>`; chặn |
| `domain.py` | Mô hình và lỗi có mã ổn định. **Không biết kho lưu trữ** |
| `repository.py` | **Hợp đồng kho**, cộng bản trong bộ nhớ (mock/test) có Realtime mô phỏng đúng cách lọc của Appwrite |
| `service.py` | Nghiệp vụ, chỉ nói chuyện với hợp đồng kho |
| `appwrite_tablesdb.py` | Kho Appwrite TablesDB (`/v1/tablesdb/...`), không cần lớp dịch staging |
| `realtime.py` | Appwrite Realtime → sự kiện |
| `runtime.py` | Nơi duy nhất chọn kho theo môi trường |
| `routes.py` | `/api/chat/*` (REST + SSE) |

**Production 1.9.6 sau này:**
- 1.9.6 đã có TablesDB, nên kho `tablesdb` có thể dùng được luôn (chưa kiểm trên production-parity);
- nếu cần API Databases kiểu cũ: viết `ChatRepository` trong **một tệp** cạnh `appwrite_tablesdb.py`, rồi đặt `FAS_CHAT_APPWRITE_API` trỏ tới nó;
- service, route và toàn bộ web **không đổi**;
- Realtime đăng ký theo **tên kênh kiểu cũ**, vốn chạy trên cả hai phiên bản (đã đo).

## Các sự thật đã đo trên Cloud 2.3 (2026-09-28) và cách thiết kế dùng chúng

| # | Đo được | Thiết kế |
|---|---|---|
| 1 | Realtime xác thực bằng session secret → đúng người dùng | Luồng dùng session của người xem, không dùng khoá |
| 2 | Người thứ ba **không** nhận sự kiện của dòng chỉ A/B đọc được | Quyền đọc theo dòng là rào chính; `event_dto` lọc lại lần nữa |
| 3 | Hai kết nối của cùng một người đều nhận sự kiện | Nhiều tab chạy song song, không tab nào "đẩy" tab nào (khác Tencent) |
| 4 | Mỗi sự kiện mang **cả** tên kênh cũ lẫn tên TablesDB | Đăng ký kênh `databases.<db>.collections.<c>.documents` |
| 5 | Dòng **tạo trong transaction không phát sự kiện Realtime** | Tin nhắn được tạo **ngoài** transaction |
| 6 | Tạo trùng rowId trong transaction → 409 `transaction_conflict`, **không** thao tác nào được áp dụng | "+1 chưa đọc" đi cùng một **dòng đánh dấu** `chat_fanouts/f<message_id>` trong cùng transaction, nên đúng một lần kể cả khi 6 lần gửi lại chạy đồng thời |
| 7 | 5 transaction đồng thời cùng `increment` một dòng → cả 5 commit, không mất lượt | `increment` cho số chưa đọc, không đọc-sửa-ghi |
| 8 | Dòng được cập nhật hoặc tăng giá trị thì có phát sự kiện | Hộp thư, số chưa đọc và đồng bộ đã-đọc giữa các tab đi qua sự kiện của dòng `chat_members` |

## Bảng (`scripts/setup_appwrite.py`)

Quyền **cấp bảng rỗng**: không người dùng nào tự tạo hay sửa được dòng (đã kiểm thật: 401/403). Quyền theo dòng **chỉ là đọc**.

| Bảng | Quyền dòng | Index |
|---|---|---|
| `chat_messages` | đọc: A, B | `(conversation_id, created_at)`, `(conversation_id, recipient_id, created_at)` |
| `chat_members` | đọc: chính chủ | `(user_id, last_at)`, `(conversation_id)` |
| `chat_blocks` | đọc: người chặn | `(blocker_id)`, `(blocked_id)` |
| `chat_fanouts` | không ai | — |

## Ngữ nghĩa

- **Quyền DM:**
  - mọi route được gọi theo *người kia*, hội thoại = `dm_id(tôi, người kia)`, nên người gọi **luôn** là thành viên;
  - không có tham số `conversation_id` nào để đoán;
  - không nhắn được cho chính mình (400); người không tồn tại trả 404;
  - con trỏ lấy từ hội thoại khác trả **cùng lỗi** với con trỏ rác, nên không dò được ID của người khác.
- **Gửi idempotent:**
  - client chọn `client_id` ngẫu nhiên; ID tin = `m_<client_id>` và cũng là ID của tin "đang gửi" trên giao diện;
  - gửi lại thì trả **tin gốc**;
  - `client_id` đã thuộc người khác trả 409.
- **Chưa đọc và đã đọc:**
  - chưa đọc = số tin *gửi cho tôi* có `created_at` > mốc đã đọc;
  - `read` **đếm lại** từ kho, rồi đếm thêm lần nữa sau khi ghi;
  - tổng trên nút Tin nhắn không tính hội thoại tắt tiếng.
- **Chặn:** hai chiều (403 `chat_blocked`); người bị chặn không thấy ai chặn mình.
- **Tắt tiếng:** vẫn đếm chưa đọc theo từng hội thoại, nhưng không đưa vào tổng.
- **Bản xem trước hộp thư:**
  - luôn là tin *mới nhất thật*, đọc lại từ kho;
  - được cập nhật **sau khi trả response** (idempotent, tự sửa ở lần gửi sau);
  - tin nhắn và "+1 chưa đọc" luôn xong **trước** khi trả, nên một lần gửi lại luôn tự hoàn tất được.
- **Nối lại (web):**
  - lùi dần 1 s → 30 s;
  - **watchdog**: im lặng 45 s thì cắt (máy chủ gửi nhịp tim 15 s; `fetch` không tự có thời hạn cho luồng);
  - `offline` thì cắt, `online` thì nối **ngay**;
  - sau mỗi lần nối lại: tải lại hộp thư và **bù khoảng trống** (`after=<tin mới nhất đã biết>`).
- **Giới hạn:**
  - gửi 30/phút; đọc 120/phút; ghi 60/phút; mở luồng 12/phút;
  - **tối đa 8 luồng đồng thời** mỗi người (mỗi luồng là một WebSocket upstream);
  - mỗi luồng sống tối đa 25 phút rồi tự nối lại.

## Kết quả kiểm

| Mức | Kết quả |
|---|---|
| Đơn vị (`server/tests/test_messaging.py`, `test_chat_session.py`) | 49/49. Có kho Appwrite giả mô phỏng đúng các hành vi đã đo; các bài Realtime chạy trên **uvicorn thật**, vì `TestClient` gom hết body SSE |
| Hợp đồng schema | 89 bài, 0 hỏng |
| Web (`realtime-chat-v1.test.mjs` + toàn bộ) | 1139/1145 (0 hỏng, 6 bỏ qua); typecheck 0; lint 0 lỗi; `cf:build` OK |
| **Sống trên staging** (`python -m scripts.staging.run_live --mo-dun test_chat_live`) | **9/9** (cần #243) |
| **Chrome hiển thị**: UI Chat V1 thật + backend thật + Appwrite staging | **17/17**. Hai người dùng + tab thứ hai; ảnh ở desktop 1440 và di động 390 |

Bộ test sống trên staging kiểm các điểm sau:
- truy cập **thẳng vào Appwrite** bằng session người thứ ba trả 404, và danh sách không lộ tin;
- không ai (kể cả thành viên) tự ghi hay sửa được dòng: 401/403;
- 6 lần gửi đồng thời cùng `client_id` tạo đúng 1 tin và 1 lượt chưa đọc;
- Realtime tới cả hai phía và tab thứ hai; người thứ ba nhận 0 sự kiện;
- đã đọc ở tab 1 thì tab 2 cập nhật;
- mất kết nối thì bù khoảng trống;
- phân trang lùi không trùng, không sót;
- chặn hai chiều; tắt tiếng.

Trên Chrome, bài test cũng xác nhận trình duyệt **chỉ gọi web và API Fanfic**, không gọi Appwrite hay Tencent.

**Độ trễ đo** (máy QA ở VN tới Appwrite SGP):

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Người nhận thấy tin (Realtime) | 1464 ms | **952 ms** |
| Người gửi nhận "đã gửi" | 3083 ms | **2444 ms** |

## Giới hạn đã biết và việc tiếp theo

1. **Người gửi chờ xác nhận khoảng 2,4 s**: xác thực, kiểm tra song song, tạo tin, cộng 3 bước của transaction. Bước tiếp theo nếu cần là tách "chuẩn bị/commit" transaction để chạy song song với bước tạo tin; việc này cần mở rộng hợp đồng kho. Đặt backend cùng vùng với Appwrite sẽ giảm mạnh hơn nữa.
2. **Gõ trước khi "sẵn sàng" thì Enter bị bỏ qua lặng lẽ.** Đây là hành vi có sẵn từ #239 (`ChatProvider.send()` khi transport chưa có). Chữ vẫn còn trong ô soạn. QA chờ `<html data-chat-sdk="logged-in">`. Sửa được mà không đổi UI (xếp hàng gửi trong provider), nhưng chưa làm.
3. **Chưa có nút chặn/tắt tiếng trên giao diện.** Có API (`/mute`, `/block`, `/blocks`) và transport; không thêm control nào để giữ nguyên UI V1.
4. **Chặn của chat tách khỏi `user_blocks` của Community (#229).** Khi #229 vào `main`: gộp thành một chính sách chặn chung (cắm vào `ChatService` qua hợp đồng kho).
5. **Hộp thư chỉ tải 50 hội thoại gần nhất**; tổng chưa đọc tính trên 50 hội thoại đó.
6. Hai lần gửi rất sát nhau có thể làm bản xem trước tạm thời là tin áp chót, tới lần ghi sau. Số chưa đọc thì luôn đếm lại chính xác khi đọc.
7. Trần 8 luồng đồng thời tính **theo từng instance**. Có N worker thì một người giữ được tối đa 8×N luồng. Hạn mức 12 lần mở mỗi phút là lớp chặn chung giữa các instance. Review bảo mật độc lập (Antigravity Claude Opus) đã chấp nhận điểm này (LOW).

## Bật trên production (CHƯA làm; cần chủ dự án duyệt)

1. Tạo 4 bảng `chat_*` trên production bằng `scripts/setup_appwrite.py --only <bảng>`, có dry-run trước.
2. Chạy `scripts/staging/live/test_chat_live.py` trên một bản production-parity 1.9.6.
3. Đặt `FAS_CHAT_V1=1`.

**Rollback:** đặt `FAS_CHAT_V1=0`; nếu cần thì xoá 4 bảng. Chỉ mất tin nhắn.

**Dọn staging:** `python -m scripts.staging.reset --du-lieu --apply` (xoá tài khoản `@example.test` và dữ liệu tổng hợp).

# PIVOT AUTH + SHIP CONTENT — Harvester Service Credential (2026-09-01)

## Tóm tắt

Bỏ hẳn hướng "chiếm phiên đăng nhập trình duyệt" (đã thử, đúng như dự đoán
của operator: hai bối cảnh trình duyệt/Chrome khác nhau, không nối được).
Thay bằng credential dịch vụ CÓ PHẠM VI HẸP, tách biệt hoàn toàn khỏi
người dùng thật — triển khai, kiểm thử đối kháng, đưa lên production, và
NGAY LẬP TỨC dùng nó để ghi nội dung thật.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Xác thực harvester | Không có — phải chiếm phiên OAuth người dùng thật (đã bỏ) | `FAS_HARVESTER_SERVICE_TOKEN` — token ngẫu nhiên 64 ký tự, so khớp hằng thời gian, danh tính cố định `svc_harvester`, KHÔNG BAO GIỜ có vai trò quản trị |
| Route chấp nhận token harvester | — | `POST/PATCH /api/novels`, `GET /api/novels`, `GET /api/novels/{id}`, `POST/PATCH /api/chapters`, `POST/GET /api/jobs`, `GET /api/audio/{id}/url` — CHỈ đúng các route này |
| Route publish/unpublish/delete/user/schema/billing | — | KHÔNG đổi gì — vẫn chỉ nhận phiên người dùng thật, token harvester không chạm tới được (do cấu trúc, không phải một điều kiện runtime có thể bị vượt qua) |
| Test đối kháng | 0 | 31 test mới (`test_harvester_service_auth.py`) — ma trận ALLOW/DENY đầy đủ |
| Bộ test backend | 4218 | 4249 — tất cả pass |
| Novel/Chapter thật trong production | 0 | 1 novel (Re:Zero) + 2 chương thật, trạng thái `draft` |
| Audio thật đã tạo | 0 | 1 file MP3 thật (14.7 MB), phát được qua URL ký thật |
| Video draft thật trong production | 0 | 3 |

## A. Thiết kế xác thực

Danh tính DỊCH VỤ thứ ba, tách biệt hoàn toàn khỏi canary lẫn người dùng
thật — `server/config.py::AppwriteSettings.is_harvester_service_token`
(so khớp `hmac.compare_digest`, luôn `False` nếu chưa cấu hình, tự chối
nếu `harvester_owner_user_id` trùng danh sách admin/owner/moderator —
y hệt cơ chế đã có của canary, xác nhận qua test). Danh tính cố định:
`user_id=svc_harvester`, KHÔNG BAO GIỜ xuất hiện trong `admin_role_of`.

`server/main.py::harvester_or_user_profile` — một dependency THAY THẾ
`current_profile` chỉ trên các route mà pipeline harvester thật sự cần.
Mọi route khác (publish/unpublish/xoá/tài khoản/schema) giữ nguyên
`current_profile`/`admin_or_owner_profile` — token harvester không có
phiên Appwrite hợp lệ nên các route đó luôn 401 với nó, không cần thêm
điều kiện runtime nào có thể viết sai.

## B. Phạm vi cấp/chối

**Cấp** (đã kiểm bằng test HTTP thật, không phải suy luận):
tạo/sửa Novel bản nháp · đọc Novel/Chapter của chính mình · tạo/sửa
Chapter bản nháp · tạo/đọc job TTS · đọc URL phát audio bản nháp.

**Chối** (đã kiểm bằng test HTTP thật):
publish · unpublish · xoá Novel · sửa hồ sơ người dùng · bề mặt canary
(`/api/admin/canary/*`) · token canary thật không leo lên được quyền
harvester (và ngược lại) · token sai/rỗng/chưa cấu hình.

## C. Xác minh production thật

1. Sinh token, lưu cục bộ qua broker, PUT lên biến môi trường Render
   (`RENDER_API_KEY`, chỉ đúng một khoá `FAS_HARVESTER_SERVICE_TOKEN`).
2. PHÁT HIỆN THẬT: service `fas-prod-api` có `autoDeploy=no` — PUT biến
   môi trường KHÔNG tự kích hoạt deploy mới. Kích hoạt deploy thủ công
   qua API (`POST /services/{id}/deploys`) — build → live, xác nhận qua
   `GET /services/{id}/deploys/{id}`.
3. Gọi thật `GET /api/novels?mine=true&limit=1` với token harvester ->
   **HTTP 200** (trước khi deploy: HTTP 401 "guests missing scopes
   [account]" — bằng chứng token CHƯA có hiệu lực cho tới khi deploy
   thật sự chạy, không phải giả định suông).

## D. TRACK A — Truyện thật

**Novel**: `nov_1b908f56330c420e` — "Re: Zero - Hai Vì Sao Bị Quên Lãng",
trạng thái `draft`, KHÔNG có trong danh sách công khai (đã xác minh qua
gọi thật `GET /api/novels` không kèm token).

**2 chương thật**: `chp_043db2f86da9492b` (ch.1, 34.100 ký tự),
`chp_e618dc58abc24374` (ch.2, 37.610 ký tự) — nguồn docln.net #28046,
đã tiếng Việt sẵn (dịch AO3 có phép tác giả), QA rẻ tiền PASS cả hai sau
khi sửa lỗi false-positive (đếm nhầm dòng ngắn lặp lại là "đoạn trùng").

**TTS chương 1 — bằng chứng thật**:
- job `job_a79d74358e42479d`, voice `piper:ngochuyennew` (Ngọc Huyền Mới,
  đúng cấu hình giọng production), 18/18 phần hoàn tất.
- `GET /api/audio/{id}/url` -> HTTP 200, `size_bytes=14737484`.
- Tải THẬT từ URL ký -> HTTP 200, `Content-Type: audio/mpeg`, đọc được
  14.737.484 byte thật.
- Hạn chế đã biết, KHÔNG chặn: `duration_seconds` trả `None` trên job —
  đây là hạn chế đo thời lượng đã ghi nhận trước đó trong log backend
  ("khong do duoc thoi luong audio... track se ghi duration_seconds=0"),
  không phải lỗi do phiên này gây ra.

**Chưa đạt mục tiêu >=5 chương**: docln.net trả `HTTP 403` cho TOÀN BỘ
domain (đã xác minh lại bằng một URL chương đã từng tải thành công trước
đó) — chặn hạ tầng nguồn, không phải chặn credential hay code.

## E. TRACK B — Video AI-animation thật

3 draft thật, cả 3 `state=draft`, `rights_mode=EMBED_ONLY`,
`subtitle_status=PENDING_SOURCE`, không sao chép byte media nào:

| novel_id | Tiêu đề | Kênh nguồn |
|---|---|---|
| `nov_9da50c56dc48447a` | 七十二环书津门卫疆 (AI国漫) | 破界动漫局 Anime Club |
| `nov_ee729c25161e4434` | 瘦下来惊艳全校 EP1~38 (AI漫剧) | 吞噬动漫DevourAnime |
| `nov_3ad6affe3ff547ab` | 天命神算 Ep01-30 (AI动漫) | AI动漫频道 |

Cả 3 đã xác minh: `state=draft`, `rights_mode=EMBED_ONLY`, KHÔNG có trong
danh sách công khai.

## F. Test & bảo mật

- `server/tests/test_harvester_service_auth.py`: 31/31 pass.
- Toàn bộ `server/tests`: 4249/4249 pass (0 lỗi).
- Guard đối kháng (`.claude/hooks`): 366/366 pass.
- Secret-scan trên mọi diff của phiên: sạch — không token/khoá nào lộ ra
  console, log, git diff, hay test.
- Đã dọn sạch mọi thử nghiệm chiếm phiên trình duyệt tạm thời (server
  localhost, cầu clipboard, script đăng nhập tương tác) theo đúng yêu cầu.

## G. Chi phí ngoài

$0 — mọi thao tác dùng API/hạ tầng đã có sẵn (Render, Appwrite qua
backend, R2 qua backend). Không gọi provider trả phí nào.

## H. SHA cuối cùng

`188f046` (đã push `origin/main`, không cần xác nhận thủ công).

## I. Điểm chặn còn lại (không thể tự động hoá thêm trong phiên này)

docln.net chặn HTTP 403 toàn domain — cần đợi chặn tự hết hoặc dùng nguồn
khác cho 3+ chương tiếp theo. KHÔNG liên quan tới credential/auth — vấn đề
đã giải quyết hoàn toàn trong phiên này.

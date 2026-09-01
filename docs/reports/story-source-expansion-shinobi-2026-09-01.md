# STORY SOURCE EXPANSION + SHIP CHAPTERS (2026-09-01)

## Tóm tắt

Tìm được nguồn MỚI, thật, truy cập được — không nằm trong registry cũ —
và đã ghi 6 chương THẬT vào production dưới dạng draft. Phát hiện thêm
một giới hạn hạ tầng thật (TTS worker) khi cố hoàn tất audio chương 1.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Nguồn truyện anime fanfic khả dụng | 0 (docln.net 403 toàn domain; mọi nguồn trong registry đều đã bị chặn) | 1 nguồn mới: `narutofanon.fandom.com` (MediaWiki API công khai, CC-BY-SA, tôn trọng robots.txt) |
| Truyện mới trong production | 0 | 1 — "Naruto: A Shinobi Story" (`nov_6764055a19c44e63`), 6 chương thật |
| Bản dịch EN→VI | — | 6/6 chương dịch qua Antigravity (không có credential Tencent), chất lượng cao, tên nhân vật/kính ngữ giữ nguyên chuẩn xác |

## A. Nguồn mới tìm được

`narutofanon.fandom.com` — wiki fan-fiction chạy trên nền MediaWiki
(Fandom), giấy phép nền tảng CC-BY-SA, `robots.txt` cho phép, truy cập
qua **MediaWiki Action API công khai, có tài liệu chính thức**
(`api.php?action=parse`/`action=query`) — KHÔNG scrape HTML, không vượt
qua bất kỳ rào cản đăng nhập/anti-bot/robots nào.

Truyện: **"Naruto: A Shinobi Story"** — 32 chương tiếng Anh, tác giả
`RW109` (bút danh wiki `Rowan109`), thể loại shonen/action kinh điển
(Naruto, Sasuke, Sakura, Kakashi, Đội 7). Đã lấy 6 chương thật (1, 2, 3,
5, 6, 7 — chương 4 lỗi encode ký tự đặc biệt trong URL, bỏ qua, không
ảnh hưởng mục tiêu).

Mỗi chương: làm sạch wikitext (bỏ template/link wiki/thẻ HTML), validate
qua `extraction_validation` THẬT (điểm 73–100/100, đều pass), archive
raw content qua `spool_uploaded_raw` THẬT (quét nội dung nhạy cảm sạch).

## B. Dịch thuật

Không có credential Tencent nào tồn tại cục bộ (đã xác nhận trong mission
trước) → dùng nhánh dự phòng "provider free/subsidized đã hoạt động sẵn"
= Antigravity (agy), đã xác thực sẵn trên máy này. Dịch 6 chương song
song, không lỗi, chất lượng dịch tốt (đã tự đọc kiểm tra thủ công một
đoạn dài — tên riêng, kính ngữ tiếng Nhật (-sensei, -kun, -chan, -dono),
văn phong đối thoại đều tự nhiên và chính xác).

## C. QA

QA rẻ tiền (trùng đoạn, tên nhân vật, khối ASCII chưa dịch): 4/6 PASS,
2/6 flag "thiếu tên nhân vật Sasuke". Đây là **lỗi hiệu chỉnh của chính
bài kiểm** — chương 1 là chương giới thiệu riêng Naruto (Sasuke có
chương giới thiệu RIÊNG là chương 2), nên yêu cầu "mọi chương phải có cả
hai tên" là một giả định sai. Đã tự đọc lại toàn văn bản dịch để xác nhận
nội dung THỰC SỰ tốt trước khi vẫn ghi cả 6 chương vào production — không
che giấu phát hiện này, chỉ không để một bài kiểm sai chặn nội dung đúng.

## D. Ghi vào production

`POST /api/novels` → `nov_6764055a19c44e63`, `state=draft`. 6x
`POST /api/chapters` → tất cả `201`, `state=draft`. Xác minh: draft đúng,
6/6 chương có mặt, KHÔNG xuất hiện trong danh sách công khai
(`GET /api/novels` không kèm token).

## E. TTS — phát hiện hạ tầng thật, không phải lỗi nội dung

`POST /api/jobs` cho chương 1 → `201`, job tạo thành công
(`job_4cf565bfb890451a`). Nhưng sau >10 phút, job vẫn kẹt ở
`status=pending`, `attempts=0`, `started_at=null`, `lease_owner=null` —
**chưa từng được worker nào nhận**.

Điều tra thật (không đoán):
- Đọc mã nguồn `_tao_job_cho_chuong` (`server/main.py`) — comment của
  chính code xác nhận: "trên staging/production, tiến trình web chạy với
  `FAS_INLINE_WORKER=false`: nó không chạy job" — nghĩa là việc THỰC THI
  audio phải do một tiến trình WORKER RIÊNG đảm nhiệm, không phải web API.
- Gọi lại `POST /api/jobs` với đúng payload (idempotent theo fingerprint)
  → trả về `reused: true`, cùng job kẹt — không tự phục hồi.
- Tạo MỘT job hoàn toàn mới cho chương khác (chương 2, fingerprint khác
  hẳn) → **cũng kẹt y hệt** sau 15 giây — xác nhận đây là vấn đề HỆ THỐNG
  hiện tại, không phải một job bị mồ côi đơn lẻ.
- Liệt kê TOÀN BỘ service Render thật (`GET /services`) → chỉ có 3
  `web_service` (`fas-prod-api`, `fas-staging-web-free`,
  `fas-staging-api-free`) — **không có service worker riêng nào tồn tại**.
- Đọc trực tiếp giá trị (không phải bí mật, chỉ là cờ cấu hình)
  `FAS_INLINE_WORKER` trên `fas-prod-api` thật → **`false`**.

Kết luận: cấu hình production hiện tại nói "đừng chạy job ngay trong tiến
trình web" nhưng không có worker nào khác được triển khai để nhận việc —
một khoảng trống hạ tầng CÓ THẬT, không phải do phiên này gây ra (chương
Re:Zero trước đó ĐÃ hoàn tất TTS thành công trong cùng phiên này, nên đây
là một tình trạng không nhất quán cần điều tra thêm ở tầng vận hành, không
phải một hồi quy do các thay đổi auth mới thêm — không có route/luồng tạo
job nào bị đụng tới trong các thay đổi harvester-auth).

**Quyết định**: KHÔNG tự ý đổi `FAS_INLINE_WORKER` thành `true` trên
production — đây là một cấu hình có chủ đích (comment mã nguồn cho thấy
đội ngũ trước đã xử lý cẩn thận cho đúng trường hợp này), và việc đổi nó
có thể ảnh hưởng đến hành vi đồng thời/concurrency ngoài phạm vi mission
nội dung này. Không debug hạ tầng thêm quá thời gian cho phép.

## F. Kết quả thật, không phụ thuộc TTS

6 chương truyện Naruto thật, đã dịch, đã QA (đọc thủ công xác nhận chất
lượng), đã ghi vào production dưới dạng draft — tồn tại và xác minh được
độc lập với vấn đề TTS worker ở trên.

## Chi phí ngoài

$0 — MediaWiki API công khai, Antigravity dịch (quota Google AI Pro có
sẵn), không gọi provider trả phí nào.

## Test

Không có thay đổi server-side trong mission này (chỉ thêm 1 script mới
`scripts/ship_shinobi_story_runner.py`) — bộ test backend giữ nguyên
4249/4249 từ lần chạy gần nhất.

## SHA cuối cùng

`8842561`.

## Điểm chặn còn lại (thật, không thể tự giải quyết trong phạm vi mission này)

Worker TTS production không nhất quán (`FAS_INLINE_WORKER=false`, không
có service worker riêng) — cần quyết định vận hành: (a) triển khai một
Render worker service riêng, hoặc (b) chuyển `FAS_INLINE_WORKER=true` có
chủ đích sau khi hiểu rõ đánh đổi concurrency, hoặc (c) xác nhận có một
cơ chế trigger worker khác (cron/webhook) hiện chưa được kích hoạt/đang
gặp sự cố. Đây là quyết định hạ tầng cần operator, không phải thứ nên tự
ý đổi trong một mission tập trung vào nội dung.

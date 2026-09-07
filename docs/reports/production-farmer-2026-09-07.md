# PRODUCTION FARMER — xây xong, chứng minh trên hạ tầng thật, CHỜ MỘT KHOÁ (2026-09-07)

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Vòng lặp sản xuất tự động | Không có | `server/farmer/` — 2 lằn, chạy 24/7 qua systemd |
| Khử trùng lặp | Từng lằn tự lo, không thống nhất | Khoá **tất định** từ canonical_url + phép kiểm **có thẩm quyền** ở Appwrite |
| Chặn tràn đĩa | Không có | Cổng đĩa **fail closed**, kể cả khi *không đo được* |
| Chặn chi phí AI | Không có | Hạn mức **per-round** cho đánh giá/TTS (không phải giới hạn đồng thời) |
| Bìa | Bước tuỳ ý | **Cổng CỨNG** — không bìa thì không READY/PUBLISHED |
| Số liệu cho Control Center | Không có | `status.json` ghi **nguyên tố**, `schema_version` |
| Suy diễn nặng trên VM | — | **Không có** — Gemini API / Cloud Run / endpoint ảnh |
| Test | — | **+49 bài**, backend 4.524 PASS |

## 1. Ràng buộc trung tâm là phần cứng, không phải sở thích

`t3a.medium` = 2 vCPU / 4 GiB, **dùng chung** với `fanfic-worker-prod` và
`fanfic-translation-worker-prod` đang chạy thật. ASR đo được **0,96× thời gian
thực** (đo ở phiên trước, trên chính lớp máy này).

Nên máy gặt **chỉ gặt**: khám phá, khử trùng lặp, điều phối, giữ hạn mức. Đánh
giá → Gemini API. Tổng hợp giọng → Cloud Run. Ảnh bìa → endpoint ngoài.

Hệ quả trực tiếp: **lằn A cố ý dừng ở bước nạp `content_queue`**. Bóc lời là
ASR; chạy nó ở đây sẽ ăn trọn một trong hai vCPU hàng giờ và làm đói hai worker
production. Lằn B (truyện chữ) không có ASR — đó là lằn thật sự sản xuất trên
máy này.

## 2. Không xây lại cộng đoạn nào

| Việc | Dùng lại |
|---|---|
| Khám phá + cổng thời lượng + phân loại quyền (lằn A) | `chinese_media_watcher`, `media_eligibility` |
| Hàng đợi | `content_queue`, `create_queue_item_once` |
| Lấy trang | `HttpFetcher` — **đã có sẵn** chặn SSRF, tôn trọng `robots.txt`, giới hạn tốc độ theo host |
| Trích xuất | `html_extract.extract` |
| Bản nháp | `POST /api/novels` + `/api/chapters` (đúng đường `ship_*_runner` dùng) |
| TTS | `POST /api/jobs` → `tts_dispatch.enqueue` (Cloud Run) |
| Ảnh bìa | `CoverPipelineService` |

## 3. Ba cổng fail closed — không cổng nào có nhánh "chạy thử xem sao"

| Cổng | Hỏng thì sao | Vì sao phải đóng |
|---|---|---|
| Khử trùng lặp | Không hỏi được kho → **coi như đã tồn tại** | Đoán "chắc chưa có" rồi gặt lại lần hai = bản trùng trên production |
| Đĩa | Không **đo** được cũng là một lần từ chối | Máy này nuôi hai worker production; đầy đĩa làm đổ cả hai |
| Đánh giá | Không đánh giá được → **không duyệt** | Khác hẳn "đã đánh giá và bị từ chối", vốn là kết quả bình thường |

Thêm một tầng nữa ở khử trùng lặp lằn B: chạm trần quét (500 truyện) cũng
**fail closed**, vì lúc đó một bản ghi cũ hơn có thể tồn tại mà không nhìn thấy.

## 4. Hạn mức có HAI hình dạng, và sự khác nhau là có thật

| Hạn mức | Hình dạng | Mặc định |
|---|---|---|
| Tải về | `concurrent` | 2 |
| Đánh giá | **`per_round`** | 8 |
| Job TTS | **`per_round`** | 3 |

Giới hạn *đồng thời* không bảo vệ được chi phí: một farmer đơn luồng sẽ lần
lượt gọi Gemini 10.000 lần mà **không bao giờ** chạm trần "2 cái cùng lúc".
Đây là một lỗi tôi đã viết ra rồi tự bắt được giữa chừng — bản đầu dùng một
hình dạng cho cả ba hạn mức.

Biến môi trường đánh sai (`abc`, `0`, `-5`) → quay về mặc định, **không** mở
toang cổng.

## 5. Chứng minh trên hạ tầng THẬT

`--dry-run` chạy với Appwrite **production** thật:

```
lằn audio : discovered 3 · deduped 3   ← nhận đúng 3 mục TePi đã gặt phiên trước
lằn text  : discovered 1 · fetched OK · failed 1
            "khong danh gia duoc … chua co FARMER_GEMINI_API_KEY — cong danh gia dong"
```

Đã chứng minh sống:

- **Khử trùng lặp tất định** nhận ra cả 3 mục đã có trong `content_queue` —
  không mục nào bị gặt lại.
- **Lấy trang thật** qua `HttpFetcher` (Wikisource) thành công, kèm SSRF/robots.
- **Cổng đánh giá fail closed đúng như thiết kế**, nêu đích danh thứ còn thiếu.
- **`status.json` ghi được**, đúng hình dạng, `healthy=false` kèm lý do đọc được.

## 6. Ưu tiên tài nguyên — farmer là khách ở nhờ

`deploy/fanfic-farmer.service`: `Nice=10`, `IOSchedulingClass=idle`,
`CPUWeight=20`, `MemoryMax=1G`, `TasksMax=64`, `ProtectSystem=strict`.

Vượt trần thì systemd **giết farmer** — cố ý, thay vì để nó đẩy hai worker
production vào swap. `RestartSec=60` + `StartLimitBurst=5`: một farmer chết vì
Appwrite sập sẽ không đập lại mỗi giây.

## 7. HAI việc cần bạn — cả hai đều là ranh giới của bạn, không phải của tôi

**(a) Khoá Gemini.** Máy chưa có `FARMER_GEMINI_API_KEY`, và kho khoá của máy
(7 khoá) không có khoá Gemini nào. Tạo/đặt một bí mật là việc của bạn — tôi
không tạo, không đoán, không thay bằng đường vòng.

**(b) Cài đặt cần `sudo`.** Kho mã ở `/opt/fanfic-audio` thuộc user `fanfic`;
`worker-prod.env` **cố ý không đọc được** bởi `ubuntu` (đúng như nó nên vậy).
Hook bảo mật của tôi chặn `sudo`, và tôi **không** nới nó ra. Lệnh cài đặt đầy
đủ, dán-là-chạy, ở `docs/PRODUCTION_FARMER.md` mục "Cài đặt lên máy AWS".

Vì (a), **lô sản xuất có kiểm soát chưa chạy được** — cổng đánh giá đóng thì
không mục nào được sản xuất, và đó chính là hành vi đúng.

## 8. Chưa làm — cố ý

- **Sinh hoạt hình AI**: ngoài phạm vi, đúng yêu cầu.
- **Cắt nhỏ video dài**: vẫn backlog; cổng 2 giờ ở `media_eligibility` vẫn áp.
- **Lưu bản gốc lên Google Drive**: `scripts/rclone_archive_copy.py` có sẵn,
  farmer chưa gọi. Nội dung phục vụ production vẫn ở R2 như cũ.

## 9. Test

```
server/tests   4.524 PASS / 0 FAIL (3 skip)   — +49 bài mới
```

49 bài mới tập trung vào **tính chất an toàn**: fail closed ở cả ba cổng, cổng
bìa cứng, khoá khử trùng lặp bất biến trước nhiễu URL, và thứ tự các bước
trong hai lằn.

# Runbook — Story Harvester V3 (vận hành)

Dành cho người vận hành (admin) dùng Story Harvester để nhập một bộ
truyện từ một trang web bên ngoài vào hàng đợi duyệt. Không phải tài
liệu kiến trúc — xem `server/scraper/__init__.py` cho cây quyết định
Tier 0/1/2 nếu cần hiểu sâu hơn. Mọi lệnh dưới đây gọi
`/api/admin/scraper/...`, cần token admin hợp lệ (`Authorization: Bearer
...`).

**Điều quan trọng nhất cần nhớ:** Story Harvester **không bao giờ** tự
ghi vào Novel/Chapter thật hay tự xuất bản. Nó chỉ tạo ra một **hàng đợi
duyệt** (`ScrapeRun` + các `ScrapeRunItem`) — biến hàng đợi đó thành nội
dung thật là một bước riêng, có chủ đích (xem
`scripts/story_harvester_direct_to_web_canary.py` cho ví dụ luồng đầy
đủ).

---

## 1. Thêm một nguồn ĐÃ biết (đã có trong `site_registry.py`)

Nguồn "đã biết" là domain đã được kỹ sư xác minh thủ công (robots.txt,
cấu trúc HTML) và cấu hình sẵn trong `server/scraper/site_registry.py`.
Chỉ cần dán URL trang mục lục:

```bash
curl -X POST $API/api/admin/scraper/runs \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://vi.wikisource.org/wiki/Ten_Tac_Pham", "chapter_limit": 50}'
```

`chapter_limit` giới hạn số chương xử lý trong LẦN GỌI NÀY — không giới
hạn tổng số chương của bộ truyện. Bỏ trống để không giới hạn.

Gọi `POST .../runs/{run_id}/drive` lặp lại (hoặc để một tiến trình định
kỳ gọi) cho đến khi trạng thái là `completed`/`partial`.

## 2. Thêm một nguồn CHƯA biết (domain lạ)

Không được dán thẳng vào `/runs` — trước tiên phải khám phá cấu trúc:

```bash
curl -X POST $API/api/admin/scraper/discover \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://trang-la.example/truyen/x"}'
```

Đọc kỹ `proposal.confidence` và `proposal.evidence` trong phản hồi:

- **`high`**: cấu trúc rõ ràng, có thể xác nhận ngay.
- **`medium`**: thiếu một vài tín hiệu (thường là không tìm được từ khóa
  "Chương"/"Chapter" trong văn bản liên kết) — đọc `evidence` để hiểu vì
  sao, tự kiểm tra vài liên kết mẫu trước khi xác nhận.
- **`low`**: **KHÔNG xác nhận.** Hệ thống cố tình từ chối đoán bừa ở mức
  này — cần kỹ sư cấu hình tay qua `site_registry.py` nếu nguồn này thật
  sự quan trọng.

Nếu đồng ý với đề xuất `medium`/`high`:

```bash
curl -X POST $API/api/admin/scraper/confirm-source \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://trang-la.example/truyen/x"}'
```

Lệnh này lưu thành một `SiteProfile` mới — từ lần sau, domain này trở
thành "đã biết" (mục 1), không cần khám phá lại.

## 3. Kiểm tra một SiteProfile

```bash
curl $API/api/admin/scraper/runs -H "Authorization: Bearer $ADMIN_TOKEN"
```

Liệt kê các đợt quét — mỗi đợt gắn với domain nào tự thấy trong
`source_url`. Chưa có route riêng để liệt kê `SiteProfile` độc lập
(ngoài đợt quét) — nếu cần xem trạng thái domain-học-được cụ thể
(`LEARNING`/`ACTIVE`/`DEGRADED`), tra trực tiếp trong kho dữ liệu
(collection `site_profiles`) hoặc thử `confirm-source` lại trên domain
đó — phản hồi sẽ báo rõ nếu domain đang `DEGRADED`.

## 4. Xem trước (dry-run) trước khi quét thật

`discover` (mục 2) **đã là** dry-run cho nguồn chưa biết. Với nguồn ĐÃ
biết, `POST /api/admin/scraper/discover` cũng dùng được — trả về ước
lượng số chương (`estimated_total`) mà **không ghi gì**.

## 5. Duyệt hàng đợi chương

```bash
curl "$API/api/admin/scraper/runs/{run_id}?status=review_ready" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Mỗi mục có `quality_passed`/`quality_score`/`quality_warnings` — **luôn
đọc `quality_warnings` trước khi coi một mục là "sẵn sàng dùng"**, kể cả
khi `quality_passed=true` (đây là kiểm tra WARN, không phải BLOCK — xem
`server/scraper/quality.py`). `decision` cho biết `new`/`revision`/
`possible_duplicate` — mục `possible_duplicate` có `duplicate_of_url`
trỏ tới chương nghi trùng, kiểm tra tay trước khi chấp nhận.

## 6. Thử lại một mục lỗi

```bash
curl -X POST $API/api/admin/scraper/runs/{run_id}/retry \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{}'
```

Không có `item_id` trong payload → thử lại **toàn bộ** mục `failed` của
đợt. Có `item_id` → chỉ thử lại đúng mục đó.

## 7. Huỷ một đợt đang chạy

```bash
curl -X POST $API/api/admin/scraper/runs/{run_id}/cancel \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{}'
```

Huỷ AN TOÀN: chương đang xử lý dở khi lệnh này tới vẫn hoàn tất bình
thường, chỉ các mục **chưa đụng tới** mới dừng lại (giữ nguyên
`pending`). Gọi `retry`/tạo lại `run` cùng URL sau này sẽ tiếp tục đúng
chỗ dừng, không mất/không trùng.

## 8. Cập nhật gia tăng (bộ truyện đang ra chương mới)

```bash
curl $API/api/admin/scraper/runs/{run_id}/check-updates \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Chỉ tải LẠI trang mục lục (không tải chương nào) để so `new_count`/
`removed_count`. Thấy `has_changes: true` → gọi lại `POST .../runs` với
cùng URL để đưa chương mới vào hàng đợi (không tạo đợt trùng, cùng
`run_id`).

## 9. Xử lý khi selector "trôi" (site đổi giao diện)

Dấu hiệu: một đợt trước đây chạy tốt bỗng có nhiều mục `failed` liên
tiếp, hoặc nội dung trích xuất trông sai (quá ngắn, lẫn menu/quảng cáo).

1. Domain sẽ tự chuyển sang `DEGRADED` sau đủ số lỗi liên tiếp — không
   cần thao tác tay để "phát hiện", chỉ cần thao tác để **khôi phục**.
2. Gọi lại `confirm-source` (mục 2) trên domain đó. Hệ thống sẽ khám phá
   lại cấu trúc **và** chạy kiểm tra cấu trúc bổ sung (Phase 5:
   không trùng y hệt chương trước, không giống trang đăng nhập/lỗi)
   trước khi chấp nhận khôi phục — nếu kiểm tra này từ chối, phản hồi sẽ
   nói rõ lý do, **không tự động khôi phục mù**.
3. Nếu bị từ chối liên tục: cấu trúc site đã đổi quá nhiều, cần kỹ sư
   xem lại `chapter_href_pattern`/vùng nội dung thủ công.

## 10. Xử lý khi bị giới hạn tốc độ (rate limit / 429)

`HttpFetcher` tự thử lại 429 và tôn trọng header `Retry-After` của
server nếu có — **thường không cần làm gì**. Nếu một domain liên tục bị
429 dù đã tự chờ:

- Không hạ `min_delay_seconds`/tăng tốc độ quét — đây là dấu hiệu domain
  đó cần được quét CHẬM hơn, không phải nhanh hơn.
- Xem xét tạm dừng đợt quét đó (mục 7) và quay lại sau, hoặc liên hệ chủ
  site nếu đây là một nguồn quan trọng lâu dài.

## 11. Vô hiệu hoá một nguồn hỏng

Chưa có route "tắt domain" một lệnh. Cách thực tế:

- Nếu domain nằm trong `site_registry.py` (nguồn đã xác minh cứng): xoá
  hoặc comment dòng cấu hình, deploy lại — route `/runs` sẽ từ chối rõ
  ràng domain đó ("chưa được cấu hình") thay vì âm thầm dùng cấu hình cũ.
- Nếu domain là `SiteProfile` học được: huỷ mọi đợt đang chạy (mục 7) và
  ngừng gọi `confirm-source`/`runs` cho domain đó — không có gì tự động
  "hồi sinh" một `SiteProfile` nếu không có lệnh gọi mới nhắm tới nó.

---

## Không có trong runbook này (cố ý)

- Cách viết một `SiteConfig` mới thủ công trong `site_registry.py` —
  xem docstring của chính file đó.
- Kiến trúc nội bộ (Tier 0/1/2, thuật toán chấm điểm trích xuất) — xem
  `server/scraper/__init__.py` và `docs/reports/`.
- Đưa một chương đã duyệt thành Novel/Chapter thật — xem
  `scripts/story_harvester_direct_to_web_canary.py` (canary QA) làm ví
  dụ luồng, tính năng "duyệt → xuất bản" một-cú-nhấn CHƯA tồn tại.

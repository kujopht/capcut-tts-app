# Production Farmer — hướng dẫn vận hành

Vòng lặp sản xuất nội dung chạy 24/7 trên máy AWS `t3a.medium`
(`13.212.224.218`), **cùng máy** với `fanfic-worker-prod` và
`fanfic-translation-worker-prod`.

## Máy gặt là người gặt, không phải nơi suy diễn

Đây là ràng buộc trung tâm, và nó do phần cứng quyết định chứ không phải sở
thích: máy có **2 vCPU / 4 GiB**, và ASR đo được **0,96× thời gian thực**.
Một tập 30 phút ăn trọn một trong hai vCPU nửa tiếng.

| Việc | Chạy ở đâu |
|---|---|
| Khám phá nguồn, khử trùng lặp, điều phối, giữ hạn mức | **Máy gặt** |
| Đánh giá chất lượng | Gemini API |
| Tổng hợp giọng đọc | Cloud Run (đã có) |
| Sinh ảnh bìa | Endpoint HTTP ngoài, hoặc nền SVG tất định |
| Bóc lời (ASR) | **Không chạy trên máy gặt** — farmer chỉ *nạp hàng đợi* |

## Hai lằn

```
A. AUDIO CÓ SẴN   nguồn → khử trùng lặp → nạp content_queue → (dừng)
                  orchestrator chạy riêng làm phần còn lại

B. TRUYỆN CHỮ     nguồn → khử trùng lặp → lấy/làm sạch → Gemini duyệt →
                  bản nháp → TTS Cloud Run → ẢNH BÌA → ứng viên xuất bản
```

Lằn B là lằn **thật sự sản xuất** trên máy này: nó không có ASR nên không
nghẽn. Lằn A cố ý dừng ở bước nạp hàng đợi.

## Thứ tự trong lằn là có chủ đích

```
khử trùng lặp TRƯỚC khi lấy  → không tải lại thứ đã có
duyệt TRƯỚC khi sản xuất     → không trả tiền TTS cho rác
bìa là cổng CUỐI và CỨNG     → không xuất bản ô trống
```

## Ba cổng fail closed

Không cổng nào có nhánh "cứ chạy thử xem sao":

1. **Khử trùng lặp** — không hỏi được kho dữ liệu → coi như đã tồn tại, bỏ
   qua. Đoán "chắc chưa có" rồi gặt lại lần hai sẽ tạo bản trùng trên
   production.
2. **Cổng đĩa** — không *đo* được dung lượng cũng là một lần từ chối. Máy này
   nuôi hai worker production; làm đầy đĩa ở đây làm đổ cả hai.
3. **Đánh giá** — không đánh giá được (mạng hỏng, API từ chối, JSON vỡ) →
   **không duyệt**. Khác hẳn "đã đánh giá và bị từ chối", vốn là kết quả bình
   thường.

## Hạn mức

Hai **hình dạng** khác nhau, và sự khác nhau là có thật:

| Hạn mức | Hình dạng | Mặc định | Biến môi trường |
|---|---|---|---|
| Tải về đồng thời | `concurrent` | 2 | `FARMER_MAX_CONCURRENT_DOWNLOADS` |
| Yêu cầu đánh giá | **`per_round`** | 8 | `FARMER_MAX_REVIEW_REQUESTS` |
| Job TTS | **`per_round`** | 3 | `FARMER_MAX_TTS_JOBS` |
| Đĩa trống tối thiểu | ngưỡng | 5 GiB | `FARMER_MIN_FREE_DISK_BYTES` |

Giới hạn *đồng thời* không bảo vệ được chi phí: một farmer đơn luồng sẽ lần
lượt gọi Gemini 10.000 lần mà không bao giờ chạm trần "2 cái cùng lúc". Nên
đánh giá và TTS đếm theo **số lần gọi mỗi vòng**.

Biến môi trường đánh sai (`abc`, `0`, `-5`) → quay về mặc định, **không** mở
toang cổng.

## Chạy

```bash
# một vòng rồi thoát — dùng cho lô có kiểm soát
/opt/fanfic-audio/.venv/bin/python -m server.farmer --once

# không ghi gì: chỉ khám phá + khử trùng lặp + báo cáo
/opt/fanfic-audio/.venv/bin/python -m server.farmer --dry-run

# xem trạng thái hiện tại
/opt/fanfic-audio/.venv/bin/python -m server.farmer --status

# chạy mãi (systemd gọi kiểu này)
sudo systemctl enable --now fanfic-farmer
journalctl -u fanfic-farmer -f
```

## Cấu hình

`/etc/fanfic-audio/farmer.env` (nạp *sau* `worker-prod.env`, nên ghi đè được):

```
FARMER_GEMINI_API_KEY=...        # BẮT BUỘC — không có thì farmer từ chối chạy
FARMER_REVIEW_MODEL=gemini-3.8-flash
FARMER_REVIEW_MIN_SCORE=70
FARMER_MAX_REVIEW_REQUESTS=8
FARMER_MAX_TTS_JOBS=3
FARMER_ROUND_SLEEP_SECONDS=900
FARMER_COVER_ENDPOINT_URL=       # trống = nền SVG tất định
```

Nguồn truyện chữ ở `/etc/fanfic-audio/farmer-text-sources.json` — **ngoài kho
mã**, để thêm một nguồn không phải là một lần deploy:

```json
{"sources": [{"url": "https://...", "title": "...", "author": "..."}]}
```

## Trạng thái cho Router Control Center

`/var/lib/fanfic-farmer/status.json`, ghi **nguyên tố** (`os.replace`) nên
người đọc không bao giờ thấy JSON cắt dở.

Router Control Center chưa tồn tại, nên đây cố ý **không** là một API mà nó
phải gọi đúng cách — bất cứ thứ gì đọc được tệp đều tiêu thụ được.

```json
{
  "schema_version": 1,
  "healthy": true,
  "unhealthy_reason": "",
  "round": {"number": 12, "seconds": 4.1},
  "lanes": {"text": {"discovered": 3, "approved": 2, "published_candidates": 2, ...}},
  "quotas": {"limits": {...}, "in_flight": {...}, "disk": {"free_bytes": ..., "ok": true}},
  "totals": {...}
}
```

`schema_version` tăng khi hình dạng đổi **không tương thích ngược**; thêm
trường thì không tăng.

## Ưu tiên tài nguyên

Unit systemd đặt farmer **dưới** hai worker production: `Nice=10`,
`IOSchedulingClass=idle`, `CPUWeight=20`, `MemoryMax=1G`. Vượt trần thì
systemd giết farmer — cố ý, thay vì để nó đẩy hai worker kia vào swap.

## Chưa làm (backlog, cố ý)

- **Sinh hoạt hình AI** — không nằm trong phạm vi này.
- **Cắt nhỏ video dài** — vẫn là backlog riêng; cổng thời lượng 2 giờ ở
  `media_eligibility` vẫn áp cho lằn A.
- **Lưu trữ bản gốc lên Google Drive** — đường dẫn có sẵn ở
  `scripts/rclone_archive_copy.py`; farmer chưa gọi. Nội dung phục vụ
  production vẫn nằm ở R2 như cũ.

# Audio Production Launch — Baseline Freeze (2026-08-21)

Trạng thái tại thời điểm chứng nhận `AUDIO PRODUCT LAUNCH: READY`. Ghi lại
để có mốc rollback rõ ràng trước khi bắt đầu vận hành nội dung thật.

## 1. Git / mã nguồn

- `main` tại `1d3901d1b83a7ae71b979f1d118ee4739f598b8f`
- Tag: `audio-launch-ready-2026-08-21` (đã push lên `origin`)
- PR gần nhất trong baseline: #28 (`fix(worker): add production TTS worker
  healthcheck watchdog`)

## 2. Backend web (Render, `fas-prod-api`)

- Đã xác nhận **đang chạy `main` mới nhất** (không có Render API key để đọc
  SHA trực tiếp từ dashboard — xác nhận bằng hành vi):
  - `DELETE /api/account` không đăng nhập → `401` (đúng theo PR #23, trước đó
    là `404` cũ).
  - `/api/health` trả `status: ok`, `appwrite_configured: true`,
    `r2_configured: true`, `author_gate_enabled: true`.
- **Việc cần làm tay**: mở Render dashboard, đối chiếu commit SHA hiển thị ở
  bản deploy "Live" với `1d3901d` — trình cho tôi không có key để tự đọc.

## 3. Worker TTS (`fanfic-worker-prod`, GCE `asia-southeast1-b`)

- ⚠️ **PHÁT HIỆN QUAN TRỌNG**: mã nguồn `server/` đang chạy trên VM này ở
  commit `fe7367f652d4f614980885fdfff24663f7f8c2fd` — **CŨ HƠN main hiện tại
  111 file / ~31.567 dòng**, từ trước cả R1 release. `server/worker.py` tự
  nó không đổi giữa hai commit, nhưng nó `import server.main as api` và gọi
  thẳng vào các hàm xử lý job của `main.py` — file đã tăng +3422 dòng kể từ
  đó, bao gồm cả bản vá 503-vs-404 (`94e54c7`).
  - **Đã kiểm chứng job TTS thật vẫn chạy đúng** trên bản cũ này nhiều lần
    trong phiên chứng nhận (piper/capcut/edge, tất cả `attempts:1`, audio
    thật tải về được) — KHÔNG phải một lỗi đang xảy ra ngay bây giờ.
  - Nhưng đây là rủi ro thật, không phải nợ kỹ thuật thông thường: worker
    từng bị treo vòng quét một lần mà chưa xác định nguyên nhân gốc — chạy
    mã tiền-R1 nghĩa là mọi bản vá độ tin cậy sau đó (kể cả 503-vs-404) đều
    KHÔNG có hiệu lực trên chính worker, dù đã có hiệu lực trên API công khai
    qua Render.
  - **Xử lý**: đưa vào Phase C (dọn ma sát vận hành nội dung) làm ưu tiên P0,
    không sửa vội giữa lúc ghi baseline.
- Watchdog: `fanfic-worker-prod-health.timer` — `active`, `enabled`. Đã xác
  minh thật bằng SIGSTOP fault-injection (không phải chỉ đọc code).
- `fanfic-worker-prod.service` — `active`.

## 4. Appwrite PROD

- Project: `fanfic-world-prod`
- Database: `fanfic_world_prod`
- Endpoint: `https://appwrite-dev.fanfic.world/v1` (tên miền có chữ "dev"
  nhưng đây LÀ project PROD thật — đã xác minh kỹ ở phiên trước, xem memory
  `appwrite-quirks-staging.md`).
- Team: `6a87a5c67c3525fdfd4f` ("Fanfic World PROD")

## 5. Rollback / backup

- Snapshot lịch trình có sẵn từ trước: `fanfic-appwrite-daily` (đĩa Appwrite),
  snapshot riêng hàng ngày cho `fanfic-worker-prod`.
- Snapshot theo yêu cầu tạo riêng cho mốc này:
  `fanfic-appwrite-temp-audio-launch-baseline-20260821` (đĩa Appwrite, mô tả
  "Appwrite PROD baseline at Audio Production Launch Gate READY
  certification, main=1d3901d").
- Rollback mã nguồn: `git checkout audio-launch-ready-2026-08-21` hoặc
  `git reset --hard 1d3901d...` trên nhánh triển khai.

## 6. Dữ liệu production tại mốc này

- Đúng 1 tài khoản thật: `kujopht@gmail.com`. 0 novel, 0 chapter, 0 job —
  toàn bộ dữ liệu QA của quá trình chứng nhận đã được dọn sạch và xác minh
  độc lập qua Appwrite REST trực tiếp.

## 7. Không đổi kiến trúc production ngoài mục 3

Theo yêu cầu: không đổi kiến trúc production trong lúc audit/vận hành nội
dung thật, trừ khi phát hiện blocker thật. Mục 3 (worker chạy mã tiền-R1) là
blocker thật duy nhất phát hiện ở bước này — sẽ xử lý ở Phase C, không xử lý
ở đây để giữ mốc baseline này đúng nghĩa "trạng thái tại thời điểm chứng
nhận", không lẫn với thay đổi sau đó.

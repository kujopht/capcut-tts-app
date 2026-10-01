# Checklist public beta: Trợ lý AI (Gemini pool)

Trạng thái lúc viết (2026-10-01):
- Production chạy main có #258–#261 (+ #257 nếu đã merge).
- `FAS_AI_ASSISTANT_V1=1`, `FAS_AI_AUDIENCE` trống, tức production ở chế độ **canary: chỉ Owner**.
- Công tắc tổng **TẮT**. `NEXT_PUBLIC_AI_ASSISTANT_ENABLED` và `NEXT_PUBLIC_AI_COMPANION_ENABLED` chưa đặt (**TẮT**).

Mỗi bước dưới đây do **Owner duyệt**, đảo ngược được, và kiểm xong mới qua bước sau.

## A. Kiểm trước khi bắt đầu (không đổi gì)

- [ ] `GET /api/health` → `ai_assistant = {enabled: true, admin_v1: true, audience: "canary"}`.
- [ ] `/admin/ai`: công tắc tổng TẮT; chỉ loại `gemini` bật; ít nhất 6 slot **HEALTHY** đang bật và `probe_stable`.
- [ ] Slot chập chờn (hiện là `gemini-05`/FFW3) để TẮT; **không** chờ nó.
- [ ] Vân tay từng slot khớp bảng chính tắc. Tệp khoá phía Owner đã chuẩn hoá (`chuan_hoa_tep_khoa.py --ghi`).
- [ ] Đã quyết việc tạo lại khoá FFW1–FFW7 sau sự cố lộ tiền tố ngày 2026-10-01. Nếu tạo lại: cài lại, deploy, rồi **Kiểm tra** lại.
- [ ] Quét rò khoá theo vân tay (log Render, bundle web, phản hồi API) = 0.
- [ ] `overview.probes_today` tách khỏi `requests`: kiểm tra slot không trừ ngân sách người dùng.
- [ ] Công tắc khẩn cấp hoạt động: bật rồi tắt khi chưa có người dùng, tắt có hiệu lực ≤ 15 giây.

## B. Quyết định cấu hình trước beta

- [ ] **Chế độ Hỗ trợ.** `SUPPORT_SAFE` = `azure_openai > qwen`, cả hai loại đang TẮT, nên mọi lượt Hỗ trợ trả `ai_no_provider`. Chọn một:
  - (a) thêm `gemini` vào `SUPPORT_SAFE`;
  - (b) ẩn chế độ Hỗ trợ ở UI beta;
  - (c) chấp nhận hiện "chưa khả dụng".
- [ ] Hồ sơ `WRITER` (`qwen > azure > gemini`) và `STORY`/`FREE_FIRST` đều tới được Gemini; giữ nguyên.
- [ ] Model: `gemini-3.5-flash-lite` là model chính. `gemini-3.8-flash` hay trả 503 (thiếu năng lực phía Google): nếu dùng thì chỉ làm slot phụ.
- [ ] **Áp preset `beta`** (`/admin/ai` → Preset rollout): 5 request/người/ngày, 150 request/ngày toàn cục, 15.000 / 450.000 token, 400 token ra, 4.000 ngữ cảnh. Kiểm `active_preset = beta`.
  - Năng lực pool: 8 slot × 30 request = 240/ngày ≥ 150 toàn cục, nên còn dư khi 1–2 slot lỗi.
- [ ] (Khuyến nghị) **Đợt beta có danh sách trước**: đặt `FAS_AI_CANARY_USERS` = ID các tester và vẫn để `FAS_AI_AUDIENCE` trống (canary), rồi deploy. Owner luôn nằm trong khán giả.

## C. Thứ tự bật (dừng ngay khi có bất thường)

1. Áp preset `beta` (công tắc vẫn TẮT) và kiểm audit.
2. (Tuỳ chọn) đặt `FAS_AI_CANARY_USERS` rồi deploy backend.
3. **Bật công tắc tổng** (khán giả vẫn canary). Owner chạy smoke 3 lượt (General / Truyện / Viết) và kiểm phân bố slot trong `overview`.
4. Bật UI: build web với `NEXT_PUBLIC_AI_ASSISTANT_ENABLED=1` rồi deploy. `NEXT_PUBLIC_AI_COMPANION_ENABLED` vẫn **0** ở đầu beta.
   - Người ngoài khán giả mở UI sẽ thấy "chưa khả dụng" (`reason: not_in_audience`).
5. Kiểm trên máy thật (iPhone + Android): mở panel, gửi, dừng, tạo lại, mất mạng.
6. **Mở cho mọi người đã đăng nhập:** đặt `FAS_AI_AUDIENCE=all` rồi deploy backend. Kiểm `/api/health` → `audience: "all"`.
7. Theo dõi 24 giờ đầu (mục D). Sau đó mới cân nhắc bật Ink Scout (`NEXT_PUBLIC_AI_COMPANION_ENABLED=1`), vì nó còn cần QA trên máy thật riêng.

## D. Theo dõi trong beta

| Tín hiệu | Ở đâu | Ngưỡng hành động |
|---|---|---|
| Request hôm nay / trần 150 | `overview.requests` | ≥ 80% trước 18h UTC: cân nhắc preset hoặc thêm slot |
| Tỉ lệ lỗi | `overview.errors / requests` | > 5% trong 1 giờ: xem `last_error_*` từng slot |
| 429 | `overview.rate_limited`, `recent_429` từng slot | Nhiều slot cùng 429: giảm RPM mềm hoặc giảm preset |
| Slot không HEALTHY | `slots_by_status` | Còn < 4 slot HEALTHY: tắt công tắc tổng hoặc giảm preset |
| `ai_no_provider` / `ai_budget_exhausted` | log, phản hồi người dùng | Tăng đột biến: kiểm cap/slot |
| Rò khoá | `quet_log_render.py` theo vân tay (mỗi ngày) | Bất kỳ lần trùng nào: tắt công tắc, tạo lại khoá đó |
| Chi phí | `est_cost_micro_usd` | Free tier = 0; khác 0 thì xem lại slot có tính phí |

## E. Rút lui

- **Tức thì:** `/admin/ai` → Tắt khẩn cấp. Luôn được chấp nhận, kể cả khi đang hiển thị phiên bản cấu hình cũ; có hiệu lực ≤ 15 giây.
- **Thu hẹp khán giả:** xoá `FAS_AI_AUDIENCE` (về canary) rồi deploy backend.
- **Tắt UI:** build web không có `NEXT_PUBLIC_AI_ASSISTANT_ENABLED` rồi deploy.
- **Hạn mức:** áp lại preset `canary`.
- **Một slot hỏng:** TẮT slot đó; bộ cân bằng tự dồn tải sang slot khác.

## F. Giới hạn đã biết

- Breaker, cooldown, `last_error_*`, bộ đếm và lịch sử kiểm slot nằm **trong tiến trình**, nên deploy hoặc khởi động lại là mất. Bộ đếm usage/ngày và audit thì bền (Appwrite).
- Cấu hình cache 15 giây.
- Render `fas-prod-api` chạy gói free (một instance, có thể ngủ hoặc chậm).
- Chống lạm dụng chỉ gồm hạn mức ngày cộng RPM 8/người/phút. Chưa có chống spam theo nội dung.
- 429 thật từ Google mới chỉ kiểm bằng unit test; trên production mới kiểm qua breaker và RPM mềm.
- Ink Scout chưa kiểm trên máy thật.

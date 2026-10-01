# Checklist public beta: Trợ lý AI (Gemini pool)

Trạng thái lúc viết (2026-10-01, production `5cd8727`, #258–#262 đã merge):
- `FAS_AI_ASSISTANT_V1=1` và `FAS_AI_ADMIN_V1=1`. `FAS_AI_AUDIENCE` trống, nghĩa là production ở chế độ **canary: chỉ Owner**.
- Công tắc tổng **TẮT**. Preset **`beta`** đang áp: 5 request/người/ngày, 150 request/ngày toàn cục, 15.000 / 450.000 token, 400 token ra, 4.000 token ngữ cảnh.
- Pool: 9 slot `gemini-3.5-flash-lite`, 8 slot bật và **HEALTHY**. `gemini-05` (FFW3) cố ý **TẮT**.
- `SUPPORT_SAFE` = `azure_openai > qwen > gemini`, và mọi slot có workload `support`.
- Smoke owner 13:36Z (mỗi lượt đều chạy `meta > delta > usage > done`, phản hồi không chứa tên slot/model/khoá):

  | Chế độ | Slot | Thời gian |
  |---|---|---|
  | Hỗ trợ | gemini-08 | 9,4 s |
  | General | gemini-06 | 8,6 s |
  | Truyện | gemini-01 | 7,2 s |

- Cờ build UI: biến repository `PRODUCTION_AI_ASSISTANT_ENABLED=0` và `PRODUCTION_AI_COMPANION_ENABLED=0`, nên cả hai **TẮT**. Pipeline bắt buộc hai biến này từ khi PR #263 được merge.
- Lối vào UI chỉ hiện cho người mà máy chủ xác nhận (`GET /api/ai/access`, cùng nguồn với route thật).

Mỗi bước dưới đây do **Owner duyệt**, đảo ngược được, và phải kiểm xong mới qua bước sau.

Thứ tự mở rộng: **canary (chỉ Owner) → beta (Owner + 10–30 tester có tên) → all (mọi người đã đăng nhập)**.

## A. Kiểm trước khi bắt đầu (không đổi gì)

- [x] `GET /api/health` → `ai_assistant = {enabled: true, admin_v1: true, audience: "canary"}`.
- [x] `/admin/ai`:
  - công tắc tổng TẮT;
  - chỉ loại `gemini` bật;
  - 8 slot HEALTHY đang bật;
  - `gemini-05` TẮT, và không chờ nó.
- [x] Vân tay 9 slot trên Render khớp bảng chính tắc.
- [ ] Tệp khoá phía Owner đã chuẩn hoá (`chuan_hoa_tep_khoa.py --ghi`). Hiện dòng 01/02 trong tệp còn đảo tên; Render thì đúng. Chuẩn hoá để lần cài khoá sau không đẩy nhầm.
- [ ] Tạo lại khoá FFW1–FFW7 (lộ tiền tố ngày 2026-10-01): **Owner hoãn** tới khi beta ổn định. Script cài và kiểm thu hồi đã sẵn. Khi làm: cài lại, deploy, **Kiểm tra** từng slot, rồi kiểm khoá cũ đã thu hồi.
- [x] Lượt Kiểm tra slot không trừ ngân sách người dùng (`overview.probes_today` tách khỏi `requests`).
- [x] Công tắc khẩn cấp: bật/tắt khi chưa có người dùng, có hiệu lực ≤ 15 giây.

## B. Quyết định cấu hình

- [x] **Chế độ Hỗ trợ:** đã thêm `gemini` vào cuối `SUPPORT_SAFE` (#262). Smoke trả lời từ gemini-08, không còn `ai_no_provider`.
- [x] `WRITER`, `STORY` và `FREE_FIRST` đều tới được Gemini.
- [x] Model chính `gemini-3.5-flash-lite`. `gemini-3.8-flash` hay trả 503 (Google thiếu năng lực), nên không dùng.
- [x] Preset `beta` đã áp. Năng lực pool là 8 slot × 30 = 240 request/ngày, cao hơn trần 150, nên còn dư khi 1–2 slot lỗi.
- [x] **Cờ giao diện là đầu vào tường minh của pipeline.** `production-deploy.yml` đọc hai **biến repository**: `PRODUCTION_AI_ASSISTANT_ENABLED` và `PRODUCTION_AI_COMPANION_ENABLED`.
  - Cả hai phải đúng `0`/`1`; thiếu hoặc sai thì `validate` DỪNG trước mọi deploy.
  - Bản sao cấp môi trường mà lệch giá trị cũng DỪNG.
  - Hiện cả hai = **`0`**, đã tạo ngày 2026-10-01.
  - Muốn bật UI: đổi biến, rồi deploy. Không deploy tay.
- [x] **Chỉ người đủ quyền thấy lối vào.** Nút nổi, mục menu, lối vào trang truyện và linh vật nổi chỉ hiện khi `GET /api/ai/access` trả `eligible: true`.
  - Bit này cùng một nguồn với route thật (`AiRuntime.access_state`).
  - Người ngoài nhóm, khách, cờ backend tắt, hay tắt khẩn cấp: không thấy lối vào nào.
  - Backend vẫn tự chặn 403/503 ở mọi route.
  - Mở thẳng `/assistant` bằng URL thì vẫn chỉ thấy "chưa khả dụng".
- [x] `NEXT_PUBLIC_AI_COMPANION_ENABLED` (Ink Scout) giữ **0** suốt beta.

## C. Thứ tự bật (dừng ngay khi có bất thường)

1. ✅ Áp preset `beta` khi công tắc vẫn TẮT, rồi kiểm audit.
2. ✅ Bật công tắc tổng với khán giả canary và chạy smoke owner, rồi TẮT lại.
3. **Nhóm beta:** làm mục G (bật nhóm, smoke, theo dõi).
4. Kiểm trên máy thật (iPhone + Android): mở panel, gửi, dừng, tạo lại, mất mạng.
5. Chỉ khi beta chạy ổn ít nhất vài ngày: **mở cho mọi người đã đăng nhập** bằng `FAS_AI_AUDIENCE=all` + deploy backend. Kiểm `/api/health` → `audience: "all"`. **Chưa làm.**
6. Theo dõi 24 giờ đầu (mục D). Sau đó mới cân nhắc Ink Scout (`NEXT_PUBLIC_AI_COMPANION_ENABLED=1`), vì nó còn cần QA trên máy thật riêng.

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

## E. Rút lui (từ nhanh đến chậm)

1. **Tức thì, không deploy:** `/admin/ai` → Tắt khẩn cấp. Luôn được chấp nhận, kể cả khi trang đang hiện phiên bản cấu hình cũ; có hiệu lực ≤ 15 giây.
2. **Một slot hỏng:** TẮT slot đó; bộ cân bằng tự dồn tải sang slot khác.
3. **Hạn mức:** áp lại preset `canary` (20/người, 40 toàn cục) hoặc hạ trần ở Toàn cục.
4. **Gỡ một tester:** xoá ID khỏi `FAS_AI_BETA_USERS`, rồi deploy backend.
5. **Thu hẹp về chỉ Owner:** xoá `FAS_AI_AUDIENCE` (hoặc đặt `canary`), rồi deploy backend. `FAS_AI_BETA_USERS` bị bỏ qua khi không ở beta.
6. **Tắt UI:** có hai cách.
   - Đặt biến repository `PRODUCTION_AI_ASSISTANT_ENABLED=0`, rồi deploy.
   - Nhanh hơn: chạy workflow **Production Rollback** (`wrangler rollback`) để về bản frontend trước, kèm đúng cờ của bản đó.
7. **Tắt hẳn backend AI:** `FAS_AI_ASSISTANT_V1=0`, rồi deploy backend.

Hội thoại đã lưu không cần xoá khi rút lui. Người dùng tự xoá được trong cài đặt trợ lý.

## F. Giới hạn đã biết

- Breaker, cooldown, `last_error_*`, bộ đếm và lịch sử kiểm slot nằm **trong tiến trình**, nên deploy hoặc khởi động lại là mất. Bộ đếm usage/ngày và audit thì bền (Appwrite).
- Cấu hình cache 15 giây.
- Render `fas-prod-api` chạy gói free: một instance, có thể ngủ hoặc chậm.
- Chống lạm dụng chỉ gồm hạn mức ngày cộng RPM 8/người/phút. Chưa có chống spam theo nội dung.
- 429 thật từ Google mới chỉ kiểm bằng unit test; trên production mới kiểm qua breaker và RPM mềm.
- Ink Scout chưa kiểm trên máy thật.
- Hạn mức ngày tính theo **UTC**: đặt lại lúc 07:00 giờ Việt Nam. Owner dùng như người thường cũng chịu trần 5/ngày khi preset `beta` áp. Smoke test của Owner đi **lối QA** (`qa: true`, hạn mức riêng `FAS_AI_OWNER_QA_DAILY_REQUESTS`, mặc định 20/ngày) nên không ăn vào 5 lượt đó và không cần nâng trần tạm rồi áp lại preset; lượt QA vẫn nằm trong trần toàn cục 150 và bị Tắt khẩn cấp chặn.
- Giao diện người dùng chỉ hiện hạn mức RIÊNG ("Hôm nay còn 3/5 lượt hỏi · làm mới lúc 07:00"); mức dùng toàn cục chỉ xem ở `/admin/ai`. Tin bị từ chối vì hết hạn mức hiện "Chưa gửi".

## G. Nhóm beta (10–30 tester): bật, smoke, rút lui

### G0. Chuẩn bị (không đổi gì)

- [ ] Danh sách 10–30 tester đã đăng nhập fanfic.world ít nhất một lần.
- [ ] Lấy **Appwrite user `$id`** của từng người (Appwrite Console → Auth → Users), không dùng email hay username.
  - ID phải khớp `^[A-Za-z0-9][A-Za-z0-9._-]{0,35}$`. ID sai dạng bị bỏ **lặng lẽ**, chỉ lộ ra qua `beta_users` nhỏ hơn dự kiến.
  - Ghi **N** = số ID sau khi bỏ trùng.
- [ ] **Trần cứng 50 ID**: vượt thì AI **TẮT cho cả Owner** (fail closed).
- [ ] Không dán danh sách ID vào issue, PR hay chat công khai.
- [ ] Báo tester:
  - 5 lượt/ngày, đặt lại lúc 07:00 giờ Việt Nam;
  - đây là bản thử, có thể tắt bất kỳ lúc nào;
  - kênh báo lỗi.

### G1. Bật nhóm (Owner)

1. Render Dashboard → `fas-prod-api` → **Environment**:
   - thêm `FAS_AI_BETA_USERS` = `id1,id2,…` (phân cách bằng dấu phẩy);
   - thêm `FAS_AI_AUDIENCE` = `beta`;
   - **không** đụng `FAS_AI_SECRET_*`, `FAS_AI_CANARY_USERS`, `FAS_OWNER_USER_IDS`, `FAS_AI_ASSISTANT_V1`, `FAS_AI_ADMIN_V1`;
   - lưu **không** deploy (Save only). Nếu Render tự deploy thì bỏ qua bước 2.
   - GitHub → Settings → Secrets and variables → Actions → **Variables** (cấp repository): đổi `PRODUCTION_AI_ASSISTANT_ENABLED` từ `0` sang **`1`**.
     - Giữ `PRODUCTION_AI_COMPANION_ENABLED=0`.
     - Không tạo bản sao ở cấp môi trường.
     - Lệnh tương đương: `gh variable set PRODUCTION_AI_ASSISTANT_ENABLED --repo kujopht/capcut-tts-app --body 1`.
     - An toàn khi UI bật: chỉ Owner, canary và tester thấy lối vào (`/api/ai/access`).
2. Deploy qua workflow (cùng SHA `main` đang chạy), rồi duyệt môi trường `production`. Lần này build cả backend (đọc env mới) lẫn frontend (cờ UI = 1):
   ```
   gh workflow run production-deploy.yml --repo kujopht/capcut-tts-app --ref main -f confirm=DEPLOY_PRODUCTION -f ref=<SHA main> -f run_certification=false -f run_canary=false -f source_url=https://example.com -f chapter_limit=2
   ```
3. Kiểm `GET /api/health`:
   - [ ] `commit_sha` bằng SHA vừa deploy.
   - [ ] `ai_assistant = {enabled: true, admin_v1: true, audience: "beta", beta_users: N}`.
   - [ ] Gặp `audience: ""` hoặc không có `beta_users`: cấu hình sai (giá trị lạ, hoặc quá 50 ID) và AI đang TẮT. Sửa env rồi deploy lại.
   - [ ] `beta_users` < N: có ID sai dạng hoặc trùng. Đối chiếu lại danh sách.
   - [ ] Tóm tắt run (GitHub Step Summary) ghi `AI UI build flags: assistant=1 companion=0`.
4. `/admin/ai`, công tắc vẫn TẮT:
   - [ ] Preset `beta`.
   - [ ] 8 slot HEALTHY. Deploy xoá breaker/cooldown, nên bấm **Kiểm tra** từng slot (không tính ngân sách) cho tới khi `probe_stable`.
   - [ ] `gemini-05` TẮT.

### G2. Smoke (bật công tắc tổng, đợi 15 giây)

| # | Ai | Làm gì | Kỳ vọng |
|---|---|---|---|
| 1 | Owner | 1 lượt mỗi chế độ General / Hỗ trợ / Truyện, gửi kèm `"qa": true` (lối QA: không tốn 5 lượt thường của Owner, tốn 3 trong hạn mức QA) | Mỗi lượt có chữ chạy dần rồi kết thúc. Không `ai_no_provider`. Sự kiện `usage` có `lane:"qa"`. `overview` thấy request ở các slot khác nhau và ô "Lượt QA của Owner" tăng 3. |
| 2 | Tester A (trong danh sách) | Mở trợ lý, gửi 1 câu General | Trả lời stream, có nút Dừng |
| 3 | Tester A | Gửi câu dài, bấm **Dừng** giữa chừng, rồi **Tạo lại** | Dừng ngay; tạo lại trả lời mới |
| 4 | Tester A | Ở trang một chương truyện, chọn chế độ Truyện, hỏi tóm tắt | Trả lời bám đúng chương |
| 5 | Tester B | Gửi tới lượt thứ 6 trong ngày | Lượt 6 nhận "Bạn đã dùng hết lượt hỏi hôm nay." (429 `ai_budget_exhausted`) |
| 6 | Tài khoản đã đăng nhập **ngoài** danh sách | Xem trang chủ, menu tài khoản, một trang chương; rồi mở thẳng `/assistant` | **Không** nút nổi, **không** mục "Trợ lý AI", **không** nút "Hỏi Trợ lý AI về chương này". `/api/ai/access` → `{"eligible": false}`. `/assistant` báo "chưa khả dụng". Gửi tin thì 403 `ai_not_enabled`. |
| 7 | Khách chưa đăng nhập | Mở trang chủ và `/assistant` | Không lối vào nào. `/assistant` mời đăng nhập. 0 request `/api/ai/*` (kể cả `/api/ai/access`). |
| 8 | Tester A (DevTools → Network) | Xem `/api/ai/access` và phản hồi SSE | `/api/ai/access` chỉ có `{"eligible": true}`. SSE không có `gemini-0`, tên model, `generativelanguage`, `FAS_AI_SECRET`, `provider_http`. |
| 9 | Owner | **Tắt khẩn cấp** trong lúc tester gửi tiếp | Trong ≤ 15 giây, lượt mới bị từ chối: 503 `ai_not_enabled`, availability `reason: disabled_by_admin`. Tải lại trang thì lối vào biến mất (`eligible: false`, cả Owner). Bật lại để tiếp tục beta. |
| 10 | Owner | `/admin/ai` → Audit | Mọi lần bật/tắt và đổi preset đều có dòng audit |

Hỏng bất kỳ dòng nào: **Tắt khẩn cấp** (E1), ghi lại mã lỗi và thời điểm, rồi mới điều tra.

### G3. Trong beta

- [ ] Mỗi ngày xem bảng ở mục D, và chạy quét rò khoá theo vân tay.
- [ ] Tester có ít nhất 2 lượt Hỗ trợ và 2 lượt Viết thật. Chế độ Hỗ trợ chưa có số liệu ngoài smoke.
- [ ] Ghi phản hồi chất lượng theo chế độ. Đó là căn cứ quyết định có mở `all` hay không.

### G4. Điều kiện dừng beta ngay (Tắt khẩn cấp trước, hỏi sau)

- Bất kỳ dấu hiệu rò khoá hoặc tên provider/model nào ra phía người dùng.
- Tỉ lệ lỗi > 5% trong 1 giờ, hoặc < 4 slot HEALTHY.
- Người ngoài danh sách gửi được tin (backend phải trả 403).
- Nội dung sai lệch nghiêm trọng hoặc bị lạm dụng.

Rút lui theo mục E (bước 1, rồi 5 nếu cần thu hẹp hẳn về Owner).

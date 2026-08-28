# Story Harvester V3 — Morning Go-Live (2026-08-29)

## 5-MINUTE HUMAN ACTION

Ba việc chỉ bạn làm được. Sau ba việc này, phần còn lại tự động.

**Quy tắc chung cho cả ba: KHÔNG dán giá trị vào Claude, chat, issue, PR,
log hay commit.** Chỉ dán thẳng vào ô secret của GitHub. Nếu lỡ dán nhầm
chỗ khác → thu hồi và tạo lại, đừng tái sử dụng.

Nơi nhập cho cả ba (giống nhau):
GitHub → repo `kujopht/capcut-tts-app` → **Settings** → **Environments** →
**production** → **Add secret**.

---

### 1. `RENDER_DEPLOY_HOOK_URL` (~1 phút)

- **Dịch vụ:** Render
- **Đường dẫn:** Dashboard → service **`fas-prod-api`** → **Settings** →
  mục **Deploy Hook** → **Copy**
- **Quyền/phạm vi:** không có gì để chọn — chính URL là bí mật
- **Nhập vào:** GitHub environment `production`, tên `RENDER_DEPLOY_HOOK_URL`
- **Cần đặt ở nơi khác không?** KHÔNG (không Render, không Cloudflare, không Appwrite)
- **KHÔNG dán:** URL này vào bất cứ đâu khác — ai có nó là deploy được production

---

### 2. `CLOUDFLARE_API_TOKEN` (~2 phút)

- **Dịch vụ:** Cloudflare
- **Đường dẫn:** Dashboard → **My Profile** → **API Tokens** →
  **Create Token** → **Create Custom Token**
- **Quyền CHÍNH XÁC (chỉ 2, đừng thêm):**
  - `Account` › **Workers Scripts** › **Edit**
  - `Account` › **Account Settings** › **Read**
- **Zone permission:** KHÔNG cần (config không khai báo `routes`)
- **Account Resources:** chọn đúng **một** account của bạn, KHÔNG "All accounts"
- **Nhập vào:** GitHub environment `production`, tên `CLOUDFLARE_API_TOKEN`
- **Cần đặt ở nơi khác không?** KHÔNG
- **KHÔNG dán:** token chỉ hiện MỘT LẦN — copy thẳng sang GitHub rồi đóng tab

---

### 3. `FANFIC_ADMIN_CANARY_TOKEN` (~2 phút)

**Đọc kỹ: đây KHÔNG phải chuỗi ngẫu nhiên bạn tự nghĩ ra.** Nó là **Bearer
token phiên đăng nhập** của một tài khoản có quyền admin trên production.
Tự bịa một chuỗi sẽ luôn bị 401.

- **Dịch vụ:** chính site production (`fanfic.world`) + Appwrite phía sau
- **Đường dẫn:**
  1. Đăng nhập `fanfic.world` bằng **tài khoản QA/admin** (khuyến nghị tài
     khoản QA riêng, không phải tài khoản cá nhân chính).
  2. Lấy Bearer token của phiên đó (DevTools → Application/Storage, hoặc
     header `Authorization` của một request đã đăng nhập).
- **Điều kiện bắt buộc:** `user_id` của tài khoản đó **phải** nằm trong
  `FAS_ADMIN_USER_IDS` (hoặc `FAS_OWNER_USER_IDS`) trên **Render**.
  - Nếu ĐÃ nằm: không cần đụng Render.
  - Nếu CHƯA: thêm `user_id` vào biến môi trường của service `fas-prod-api`
    trên Render → service sẽ redeploy → rồi mới lấy token.
    **Chỉ `user_id` mới cần đặt ở Render — KHÔNG BAO GIỜ đặt giá trị token.**
- **Nhập vào:** GitHub environment `production`, tên `FANFIC_ADMIN_CANARY_TOKEN`
- **Cần đặt ở nơi khác không?** Chỉ `FAS_ADMIN_USER_IDS` ở Render (nếu thiếu).
  Appwrite: không cần thao tác gì.
- **Lưu ý hết hạn:** token phiên **sẽ hết hạn**. Khi đó Phase 15/18 báo
  `AUTH_FAILURE` (401) — thất bại rõ ràng, không pass giả. Lúc đó chỉ cần
  lấy token mới và cập nhật lại secret.
- **KHÔNG dán:** token vào chat/log. Nếu lỡ lộ → đăng xuất phiên đó để vô hiệu hoá.

---

## Chuỗi tự động sau khi đủ credential

Sau khi ba secret đã có, chạy tuần tự. Mỗi bước là cổng — hỏng thì DỪNG,
không đi tiếp.

### Bước 0 — chỉ kiểm TÊN, không xem giá trị

```bash
gh secret list --env production     # kỳ vọng thấy đủ 3 TÊN
gh variable list --env production   # kỳ vọng CLOUDFLARE_ACCOUNT_ID, PRODUCTION_API_BASE_URL
```

> `gh secret list` bị runtime của Claude Code bắt xác nhận (xem
> `RUNBOOK-PHONE-REMOTE.md` mục 3) — duyệt một lần là xong, đây không phải
> lỗi hồ sơ quyền.

### Bước 1 — deploy `main` mới nhất

GitHub → **Actions** → **Production Deploy** → **Run workflow**:

- `confirm` = `DEPLOY_PRODUCTION` (gõ chính xác, sai một ký tự là workflow từ chối)
- `ref` = `main` (phải khớp CHÍNH XÁC tip của `origin/main`)
- `run_certification` = `true`
- `run_canary` = **`false`** ở lần đầu (bật riêng ở bước 3 sau khi đã xem sức khoẻ)

Workflow tự chặn: chạy sai branch → từ chối; thiếu secret → dừng trước khi
gọi mạng; SHA không khớp → fail.

### Bước 2 — xác minh SHA đã deploy

```bash
curl -s https://fas-prod-api.onrender.com/api/health | tr ',' '\n' | grep commit_sha
git rev-parse origin/main
```

Hai giá trị phải khớp (12 ký tự đầu). **Hiện tại `commit_sha` chưa xuất
hiện** vì production đang chạy code cũ hơn PR #90 — sau bước 1 nó PHẢI xuất
hiện. Nếu vẫn thiếu → deploy chưa thực sự vào, KHÔNG đi tiếp.

### Bước 3 — Phase 15 (canary direct-to-web)

```bash
python scripts/story_harvester_direct_to_web_canary.py \
  --api https://fas-prod-api.onrender.com \
  --environment production \
  --admin-token "$FANFIC_ADMIN_CANARY_TOKEN" \
  --source-url <URL nguồn QA dùng một lần> \
  --chapter-limit 2
```

Sẽ hỏi gõ đúng tên môi trường. Canary chỉ tạo Novel **DRAFT**, không bao
giờ `/publish`, và chỉ xoá đúng `novel_id` do chính nó tạo.

### Bước 4 — đọc bằng chứng trước khi đi tiếp

Xác nhận trong output: Novel được tạo → chương được thu → dọn dẹp đã xoá
đúng `novel_id` đó → không có bước nào "bỏ qua". Nếu dọn dẹp báo "không có
gì để dọn" trong khi Novel đã tạo → DỪNG, điều tra thủ công.

### Bước 5 — Phase 18 (chứng nhận sản xuất)

```bash
python scripts/story_harvester_production_certification.py \
  --api https://fas-prod-api.onrender.com \
  --admin-token "$FANFIC_ADMIN_CANARY_TOKEN" \
  --source-url <URL nguồn QA> \
  --chapter-limit 2 \
  --expected-sha "$(git rev-parse origin/main)" \
  --json docs/reports/phase18-certification-2026-08-29.json
```

Kỳ vọng `VERDICT: PASS`. Nếu `STALE_DEPLOYMENT` → quay lại bước 1.

### Bước 6 — STORY HARVESTER V3 READY

Khi bước 5 PASS: ghi lại file JSON chứng nhận vào `docs/reports/`.

---

## Ranh giới tối nay (đã tôn trọng)

Không deploy, không tạo/sửa credential, không chạy Phase 15/18 thật, không
chạm 13 series thật, không mass scrape, không đụng Content Factory /
Translation / TTS-ASR / `/watch`.

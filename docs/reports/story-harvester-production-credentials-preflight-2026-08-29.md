# Preflight biên giới credential — Story Harvester V3 production closure

Ngày: 2026-08-29. Kiểu: **chỉ đọc**. Không tạo/sửa credential, không deploy,
không chạm 13 series thật, không mass scrape.

**Không có giá trị bí mật nào trong tài liệu này** — chỉ tên biến, đường dẫn
UI, và phạm vi quyền.

## Tóm tắt

| Credential | Trạng thái | Bản chất thật | Ai cần giá trị |
|---|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | THIẾU | URL webhook (bản thân URL LÀ bí mật) | chỉ GitHub |
| `CLOUDFLARE_API_TOKEN` | THIẾU | API token phạm vi hẹp | chỉ GitHub |
| `FANFIC_ADMIN_CANARY_TOKEN` | THIẾU | **Bearer token của MỘT NGƯỜI DÙNG**, không phải chuỗi ngẫu nhiên | chỉ GitHub (kèm điều kiện ở Render) |

Hai biến `vars` đã có sẵn: `CLOUDFLARE_ACCOUNT_ID`, `PRODUCTION_API_BASE_URL`.
Môi trường GitHub `production` đã tồn tại và được 3 job tham chiếu.

---

## 1. `RENDER_DEPLOY_HOOK_URL`

**Service đích:** `fas-prod-api` — suy ra từ `PRODUCTION_API_BASE_URL`
(`https://fas-prod-api.onrender.com`), không phải đoán.

**Loại hook:** Render *Deploy Hook* — một URL chứa sẵn khoá. Gọi bằng
`POST`, không cần header xác thực. **Chính URL là bí mật.**

**Nơi tiêu thụ:** `.github/workflows/production-deploy.yml`, bước
`Trigger Render deploy (backend)`:

```
curl -sS -X POST "$RENDER_DEPLOY_HOOK_URL" --max-time 30
```

Fail-closed: nếu secret rỗng → `::error::` và `exit 1` trước khi gọi mạng.

**Giới hạn THẬT của deploy hook (đã ghi trong workflow):** hook **không có
tham số commit** — nó luôn deploy tip hiện tại của `main`. Đây là lý do
workflow bắt `ref` phải khớp CHÍNH XÁC `origin/main`, và vì sao bước hậu
deploy phải đối chiếu `commit_sha`. Đây là giới hạn của Render, không phải
lỗi workflow.

**Công cụ Render cục bộ:** KHÔNG có (`render` không có trên PATH). Không có
đường tự động hoá — phải lấy từ dashboard.

**Lưu ý cấu hình:** `deploy/render.free.yaml` chỉ định nghĩa service
**staging** (`fas-staging-api-free`, `fas-staging-web-free`). Service
production **không** do blueprint quản lý → tạo/sửa thủ công trên dashboard.

**Thủ tục an toàn (KHÔNG làm tối nay):**
Render Dashboard → service `fas-prod-api` → **Settings** → **Deploy Hook**
→ *Copy*. Nếu nghi ngờ đã lộ: *Regenerate* rồi cập nhật lại GitHub.

---

## 2. `CLOUDFLARE_API_TOKEN`

Quyền tối thiểu được **truy vết từ lệnh thật**, không phải mặc định khuyến nghị.

**Chuỗi lệnh thật:**

```
workflow → npm ci && npm run cf:deploy:production
cf:deploy:production = npm run cf:build && opennextjs-cloudflare deploy
cf:build             = opennextjs-cloudflare build && opennextjs-cloudflare populateCache local
```

**`web/wrangler.jsonc` khai báo gì:**

| Khoá | Giá trị | Hệ quả về quyền |
|---|---|---|
| `name` | `fanfic-web` | Worker script cần quyền ghi |
| `main` | `.open-next/worker.js` | — |
| `assets` | thư mục + binding `ASSETS` | upload asset đi kèm Worker, **không** cần quyền riêng |
| `r2_buckets` | **không có** | R2 **KHÔNG** cần |
| `kv_namespaces` | **không có** | KV **KHÔNG** cần (`populateCache local`) |
| `d1_databases` / `durable_objects` | **không có** | không cần |
| `routes` | **không có** | **Zone permission KHÔNG cần** |

**Quyền BẮT BUỘC (Account-level):**

- **Account › Workers Scripts › Edit** — upload Worker + asset.
- **Account › Account Settings › Read** — wrangler phân giải tài khoản.

**Quyền Zone:** **KHÔNG cần.** Vì `wrangler.jsonc` không khai báo `routes`,
lần deploy không tạo/sửa route; custom domain `fanfic.world` đã gắn sẵn ở
mức dashboard và không bị chạm tới. *Nếu sau này thêm `routes` vào config,
lúc đó mới cần **Zone › Workers Routes › Edit**.*

**Phạm vi tài nguyên:** giới hạn đúng **một** account (chính là
`CLOUDFLARE_ACCOUNT_ID` đã cấu hình). Không chọn "All accounts".

**KHÔNG cần (đừng cấp):** R2 Storage, KV Storage, D1, Zone DNS Edit,
Zone SSL, Page Rules, Account Member Management, Billing, User API Tokens.

**Thủ tục an toàn (KHÔNG làm tối nay):**
Cloudflare Dashboard → **My Profile** → **API Tokens** → **Create Token**
→ **Create Custom Token** → thêm đúng 2 quyền trên → Account Resources =
account đó → *Continue* → *Create*. **Token chỉ hiện MỘT LẦN.**

---

## 3. `FANFIC_ADMIN_CANARY_TOKEN`

**Đây là phát hiện quan trọng nhất của Phase A.**

Tên secret gợi ý "một chuỗi bí mật do ta tự sinh". **Không phải.** Truy vết
đầy đủ cho thấy đây là **Bearer token phiên đăng nhập của một NGƯỜI DÙNG**
có quyền admin trên production.

**Vòng đời đã truy vết:**

| Bước | Vị trí | Nội dung |
|---|---|---|
| Script gửi | `story_harvester_direct_to_web_canary.py` | header `Authorization: Bearer <token>` |
| Server nhận | `server/main.py:688` `current_profile` | thiếu/sai/**hết hạn** → 401 |
| Server phân quyền | `server/main.py:4328` `admin_or_owner_profile` | `admin_role_of(user_id)` phải là ADMIN hoặc OWNER, nếu không → 403 |
| Nguồn vai trò | `server/config.py:621` | đọc biến môi trường `FAS_ADMIN_USER_IDS` (và `FAS_OWNER_USER_IDS`) |

**Hệ quả rất cụ thể:**

1. **KHÔNG tự sinh entropy.** Không có "độ dài/định dạng khuyến nghị" nào để
   chọn — giá trị là thứ Appwrite cấp khi đăng nhập. Tự bịa một chuỗi ngẫu
   nhiên sẽ luôn nhận 401.
2. **Render KHÔNG cần giá trị token.** Render chỉ cần `FAS_ADMIN_USER_IDS`
   (hoặc `FAS_OWNER_USER_IDS`) **chứa `user_id`** của tài khoản đó. Giá trị
   token chỉ nằm ở GitHub.
3. **GitHub một mình LÀ đủ** — với điều kiện tài khoản kia **đã** là admin
   trên production. Nếu chưa, phải thêm `user_id` vào biến môi trường của
   Render **và deploy lại** thì vai trò mới có hiệu lực. Đây là việc production,
   không làm tối nay.
4. **Token phiên sẽ HẾT HẠN.** Secret trong GitHub vì thế sẽ mục theo thời
   gian. Khi hết hạn, Phase 15/18 báo `AUTH_FAILURE` (401) — **thất bại rõ
   ràng, không âm thầm pass**. Coi đây là secret cần làm mới định kỳ, không
   phải "đặt một lần là xong".

**Tiêu thụ:**
- Phase 15 `story_harvester_direct_to_web_canary.py` — `--admin-token` **bắt buộc**.
- Phase 18 `story_harvester_production_certification.py` — `--admin-token` **bắt buộc**.
- Cả hai: thiếu token → dừng ngay từ bước đầu, không âm thầm bỏ qua.

**Thủ tục an toàn (KHÔNG làm tối nay):** xem mục "5-MINUTE HUMAN ACTION"
trong `story-harvester-morning-go-live-2026-08-29.md`.

**Khuyến nghị:** dùng một tài khoản QA riêng (không phải tài khoản cá nhân
chính), `user_id` của nó nằm trong `FAS_ADMIN_USER_IDS` — để thu hồi được
độc lập mà không ảnh hưởng quyền admin thật của bạn.

---

## Điều KHÔNG được làm với các giá trị này

- Không dán vào chat/Claude/issue/PR/log/commit.
- Không đưa vào worker AI ngoài (Antigravity/Codex) — dispatcher đã có bộ
  chặn theo hình dạng credential, nhưng đừng dựa vào nó.
- Không ghi vào file trong repo. Cả ba chỉ sống ở: GitHub environment
  `production` (và với `FAS_ADMIN_USER_IDS` là biến môi trường Render).

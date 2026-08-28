# Runbook — Production Deploy / Rollback / Certification (phone-safe)

Điều khiển production TỪ ĐIỆN THOẠI qua GitHub Actions `workflow_dispatch` —
KHÔNG cần mở console Render/Cloudflare bằng trình duyệt để deploy (chỉ cần
trình duyệt cho việc CẤU HÌNH MỘT LẦN bên dưới). Không thay thế
`deploy/RUNBOOK-PRODUCTION.md` (kiến trúc/tài nguyên/thiết lập ban đầu) —
tài liệu NÀY chỉ nói về vòng lặp vận hành hằng ngày: deploy, chứng nhận,
rollback.

**Nguyên tắc cốt lõi**: workflow KHÔNG BAO GIỜ tự deploy theo push — CHỈ
`workflow_dispatch` thủ công, với một chuỗi xác nhận gõ tay
(`DEPLOY_PRODUCTION`/`ROLLBACK_PRODUCTION`), một cổng test bắt buộc (tái sử
dụng `ci.yml`), và (nếu bạn bật) một GitHub Environment `production` yêu cầu
người duyệt trước khi job chạm tới secret thật.

---

## 1. Thiết lập một lần (bắt buộc trước lần deploy đầu tiên)

### 1a. GitHub repository secrets (Settings → Secrets and variables → Actions → Secrets)

| Tên | Giá trị | Ghi chú |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | Deploy Hook của service `fas-prod-api` (Render → service → Settings → Deploy Hook) | KHÔNG phải Render API key — chỉ một URL kích hoạt build lại `main` |
| `CLOUDFLARE_API_TOKEN` | Token custom, phạm vi TỐI THIỂU | Xem 1c bên dưới |
| `FANFIC_ADMIN_CANARY_TOKEN` | Bearer token của MỘT tài khoản admin production có sẵn | Dùng cho Phase 15/18 — KHÔNG BAO GIỜ dán vào code/log |

### 1b. GitHub repository variables (Settings → Secrets and variables → Actions → Variables)

| Tên | Giá trị hiện tại | Ghi chú |
|---|---|---|
| `PRODUCTION_API_BASE_URL` | `https://fas-prod-api.onrender.com` | Không bí mật (URL công khai) — cập nhật nếu sau này gắn domain riêng |
| `CLOUDFLARE_ACCOUNT_ID` | ID tài khoản Cloudflare | Không bí mật |

### 1c. Cloudflare API Token — least-privilege

Tạo tại `dash.cloudflare.com/profile/api-tokens` → **Create Token** → dùng
template **"Edit Cloudflare Workers"**, thu hẹp phạm vi (**Account
Resources**) về ĐÚNG MỘT tài khoản (không chọn "All accounts"). Template này
cấp Workers Scripts Edit + Account Settings Read — đủ cho
`opennextjs-cloudflare deploy`/`wrangler rollback`, không cấp gì rộng hơn
(không DNS, không Zone, không tài khoản khác).

### 1d. GitHub Environment `production` (khuyến nghị mạnh)

Settings → Environments → New environment → tên `production` → bật
**Required reviewers** (chọn chính bạn hoặc một người tin cậy). Đây là lớp
duyệt THỨ HAI độc lập với chuỗi gõ tay `DEPLOY_PRODUCTION` — mọi job trong
hai workflow bên dưới có chạm secret production đều khai
`environment: production`, nên nếu bạn bật required reviewers, job đó sẽ
DỪNG chờ duyệt trước khi chạm secret, kể cả khi ai đó dispatch được workflow.

### 1e. Cấu hình quyền Claude Code cục bộ

`.claude/settings.json` (đã tạo trong PR này) buộc phê duyệt cho mọi lệnh
push/merge/dispatch-deploy/sửa workflow, và TỪ CHỐI hẳn force-push, reset
cứng, đọc credential, và các lệnh cloud có tính phá hoại. Xem file đó để
biết danh sách đầy đủ.

**Giới hạn THẬT (đọc trước khi tin tưởng quá mức)**: danh sách này khớp
THEO VĂN BẢN của lệnh, không hiểu ngữ nghĩa — phát hiện qua review độc lập
(Codex). Một dạng lệnh khác biệt về chữ (bí danh shell, gọi qua đường dẫn
đầy đủ khác `git`/`cat`, refspec ép buộc kiểu `git push origin +HEAD:main`,
`command git push --force`, hay đơn giản là một công cụ đọc file khác chưa
có trong danh sách) có thể lách qua. Đây là một lớp CHẮN NGƯỜI DÙNG SƠ Ý,
không phải một hộp cát chống lại kẻ tấn công cố ý đã có quyền chạy Bash
trong phiên — lớp phòng vệ thật sự nằm ở việc KHÔNG cấp quyền chạy tự động
không giám sát cho việc đó ngay từ đầu.

---

## 2. Deploy production

GitHub → Actions → **Production Deploy** → Run workflow:

| Input | Giá trị |
|---|---|
| `confirm` | gõ đúng `DEPLOY_PRODUCTION` |
| `ref` | `main` (mặc định — xem lưu ý dưới) |
| `run_certification` | `true` (mặc định, Phase 18) |
| `run_canary` | `false` (mặc định — chỉ bật khi cố ý muốn chạy Phase 15) |
| `source_url` | một URL mục lục công khai, NHỎ, KHÔNG phải 1 trong 13 series thật |
| `chapter_limit` | `2` (mặc định) |

**Lưu ý quan trọng về `ref`**: Render Deploy Hook KHÔNG nhận tham số commit
— nó luôn build bản MỚI NHẤT đang có trên `main`. Vì vậy workflow xác minh
`ref` bạn chọn phải TRÙNG CHÍNH XÁC với tip hiện tại của `main`, không phải
một target độc lập. Muốn deploy một commit cụ thể: đưa `main` về đúng commit
đó trước (merge/revert), rồi dispatch với `ref=main`.

Thứ tự thực thi: cổng test (tái dùng `ci.yml`) → xác nhận + xác minh commit
→ deploy Render + Cloudflare → health check (chịu được cold-start ~50s của
Render Free) → Phase 18 (nếu bật) → Phase 15 (nếu bật) → tóm tắt đã ẩn bí
mật ở cuối (GitHub Step Summary).

Bất kỳ bước nào thất bại → các bước sau KHÔNG chạy (trừ tóm tắt cuối, luôn
chạy để báo cáo trạng thái).

## 3. Chứng nhận production độc lập (không deploy)

Phase 18 (`scripts/story_harvester_production_certification.py`) chạy TỰ
ĐỘNG sau mỗi lần deploy (nếu `run_certification=true`) — không cần thao tác
riêng. Muốn chạy lại chứng nhận MÀ KHÔNG deploy: dispatch lại **Production
Deploy** với `ref=main` (không đổi gì) — nếu `main` không đổi, bước deploy
vẫn chạy (Render hook không phân biệt "đã deploy commit này chưa"), nhưng
vô hại vì không có gì thay đổi để build lại khác đi.

## 4. Rollback

GitHub → Actions → **Production Rollback** → Run workflow, gõ
`ROLLBACK_PRODUCTION`.

- **Frontend (Cloudflare Worker)**: rollback THẬT qua `wrangler rollback`
  — quay về bản deploy TRƯỚC ĐÓ ngay lập tức, một lệnh, không cần thao tác
  tay.
- **Backend (Render)**: KHÔNG tự động được (bộ thiết lập này chỉ có Deploy
  Hook, không có Render API key đầy đủ, nên không có API "rollback" khả
  dụng). Thủ tục: `git revert <commit-lỗi>` trên `main` qua PR bình thường,
  rồi dispatch lại **Production Deploy** — tái sử dụng ĐÚNG cổng test/xác
  nhận/health-check như một lần deploy bình thường, thay vì một đường
  rollback riêng ít được kiểm chứng hơn.

## 5. Sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ |
|---|---|
| `validate` thất bại "Render's deploy hook always deploys..." | `ref` bạn chọn không phải tip hiện tại của `main` |
| Health check thất bại sau ~2 phút retry | Render service không khởi động được, hoặc `PRODUCTION_API_BASE_URL` sai |
| `/api/ready` trả 503 | Appwrite/R2 production không kết nối được — kiểm tra biến môi trường trên Render (không phải lỗi của workflow này) |
| Phase 18/15 thất bại "FANFIC_ADMIN_CANARY_TOKEN... not set" | Chưa tạo secret, hoặc token đã hết hạn/bị thu hồi |
| Cloudflare deploy thất bại "Authentication error" | `CLOUDFLARE_API_TOKEN` sai phạm vi hoặc đã hết hạn |

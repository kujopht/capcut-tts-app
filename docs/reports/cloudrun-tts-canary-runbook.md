# Runbook thực thi canary Cloud Run TTS — dán-và-chạy

Kèm lệnh lùi cho từng bước. **Chưa bước nào được chạy.**

Kế hoạch và lý lẽ ở `cloudrun-tts-canary-plan-2026-09-06.md`; tệp này chỉ là
phần thao tác, để lúc chạy không phải vừa đọc vừa suy nghĩ.

Đặt sẵn cho mọi bước:

```bash
export PATH="$PATH:/c/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin"
GCP=gen-lang-client-0793420657
VUNG=asia-southeast1
URL=https://tts-task-service-1007100453671.asia-southeast1.run.app
```

## 0. TRẠNG THÁI TỐI ĐÃ CHỨNG MINH — mốc để lùi về

Đây là trạng thái đã đo liên tục qua đêm 2026-09-06. Mọi lệnh lùi bên dưới đều
đưa hệ thống về đúng đây:

| Hạng mục | Giá trị |
|---|---|
| `GET /health` | `{"ok":true,"enabled":false}` |
| `POST /tasks/tts` | `503` |
| `FAS_TTS_HTTP_ENABLED` | không đặt |
| `APPWRITE_DATABASE_ID` (service) | `dark_deploy_khong_co_db` |
| `R2_BUCKET` (service) | `fanfic-staging` |
| Hàng đợi `tts-jobs` | `PAUSED` |
| `FAS_TTS_DISPATCH` (web) | không đặt |
| Worker AWS | `active` |

**LỆNH LÙI TOÀN PHẦN** — dùng được ở bất kỳ bước nào, không cần biết đang ở đâu:

```bash
gcloud tasks queues pause tts-jobs --location=$VUNG --project=$GCP --quiet
gcloud run services update tts-task-service --region=$VUNG --quiet \
  --remove-env-vars=FAS_TTS_HTTP_ENABLED \
  --update-env-vars="APPWRITE_DATABASE_ID=dark_deploy_khong_co_db,R2_BUCKET=fanfic-staging"
# và bỏ FAS_TTS_DISPATCH trên tiến trình web (Render) nếu bước 3 đã chạy
```

Sau khi lùi, **luôn** xác minh lại:

```bash
TOK=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOK" "$URL/health"          # enabled:false
gcloud tasks queues describe tts-jobs --location=$VUNG --project=$GCP --format='value(state)'   # PAUSED
```

## 1. Điều kiện tiên quyết — CHẶN, không phải khuyến nghị

```bash
python scripts/ops/verify_prod_r2_credential.py    # phải in "DAT"
```

Trượt ở đây thì **dừng**. Không bước nào bên dưới an toàn khi chưa có khoá R2
production, vì bước 2 sẽ trỏ service vào `fanfic_world_prod`.

## 2. Bước 1 — bật service, hàng đợi VẪN PAUSED (~15 phút)

```bash
gcloud run services update tts-task-service --region=$VUNG --quiet \
  --update-env-vars="FAS_TTS_HTTP_ENABLED=true,APPWRITE_DATABASE_ID=fanfic_world_prod,R2_BUCKET=fanfic-prod" \
  --update-secrets="R2_ACCESS_KEY_ID=tts-r2-prod-access-key-id:latest,R2_SECRET_ACCESS_KEY=tts-r2-prod-secret-access-key:latest"
```

Chốt an toàn tự động: nếu lỡ đặt `R2_BUCKET` khác `fanfic-prod` cùng
`APPWRITE_DATABASE_ID=fanfic_world_prod`, service trả **HTTP 500** và **không
làm gì** — `Settings.validate()` chặn ở mỗi request. Đã chứng minh trên chính
bản đã deploy.

Chọn **một** `job_id` đang `pending` của tài khoản nội bộ, rồi:

```bash
TOK=$(gcloud auth print-identity-token)
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
     -d '{"job_id":"<job_id>"}' "$URL/tasks/tts"
```

**ĐẠT:** `200 {"ket_qua":"hoan_tat"}`; object nằm trong `fanfic-prod`;
`audio_track` trỏ đúng khoá; job `completed`, `lease_owner` rỗng; nghe ra tiếng.

**LÙI:** `gcloud run services update tts-task-service --region=$VUNG --quiet --remove-env-vars=FAS_TTS_HTTP_ENABLED`

## 3. Bước 2 — mở hàng đợi, chưa đẩy tự động (~30 phút)

```bash
gcloud tasks queues resume tts-jobs --location=$VUNG --project=$GCP --quiet
gcloud tasks create-http-task --queue=tts-jobs --location=$VUNG --project=$GCP \
  --url="$URL/tasks/tts" --method=POST \
  --header="Content-Type: application/json" \
  --body-content='{"job_id":"<job_id>"}' \
  --oidc-service-account-email=tts-tasks-invoker@$GCP.iam.gserviceaccount.com \
  --oidc-token-audience="$URL"
```

Cấu hình hàng đợi đã chỉnh cho khớp lease (2026-09-06):

| Tham số | Giá trị | Vì sao |
|---|---|---|
| `min-backoff` | **120s** | PHẢI dài hơn lease 90s. Với 30s cũ, worker chết giữa chừng thì mọi lần thử lại đều gặp lease còn sống → `409` → đốt hết lượt thử **trước khi** lease kịp hết hạn, và hàng đợi mất sạch tác dụng |
| `max-attempts` | **5** | Lớn hơn `JOB_MAX_ATTEMPTS=3` để tầng hàng đợi không cắt ngắn ngân sách thử lại của tầng ứng dụng |
| `max-concurrent-dispatches` | 3 | Khớp `maxScale=3` của service |

**ĐẠT:** mọi task `200`; không job nào `attempts` nhảy quá 1; không chương nào
có hai `.mp3`.

**LÙI:** `gcloud tasks queues pause tts-jobs --location=$VUNG --project=$GCP --quiet`

## 4. Bước 3 — bật đẩy tự động (24 giờ)

Đặt trên tiến trình web (Render): `FAS_TTS_DISPATCH=cloudtasks`,
`FAS_TTS_TASKS_QUEUE=tts-jobs`, `FAS_TTS_TASKS_LOCATION=asia-southeast1`,
`FAS_TTS_TASKS_PROJECT=gen-lang-client-0793420657`,
`FAS_TTS_TASKS_TARGET_URL=$URL/tasks/tts`,
`FAS_TTS_TASKS_OIDC_SA=tts-tasks-invoker@…`.

AWS **vẫn chạy nguyên**. Job nào Cloud Run không kịp giành thì AWS nhặt — đúng
hành vi, không phải sự cố.

**ABORT NGAY nếu:** có `audio_track` trỏ vào object không tồn tại; hoặc một
chương có hai `.mp3`; hoặc tỉ lệ `failed` tăng so với 24 giờ trước.

**LÙI:** bỏ `FAS_TTS_DISPATCH` trên Render → job mới quay về đúng đường hôm nay.

## 5. Bước 4 — song song 72 giờ, chỉ quan sát

Chạy lại chính công cụ đã dùng đêm nay:

```bash
python <scratchpad>/canh_dem.py <log.jsonl> 4320 15
```

Nó tự kết luận `OK`/`LECH` mỗi mẫu; chỉ cần đọc dòng `LECH`. **Nhớ đổi
`OBJECT_NEN_CO`** — hằng số đó đang chốt ở 7 object của `fanfic-staging`, sang
canary thì mốc là `fanfic-prod` và con số khác.

## 6. Bước 5 — rút AWS: KHÔNG nằm trong runbook này

Chỉ bàn sau khi bước 4 đạt, và đúng thứ tự: **dừng** unit AWS → quan sát 24 giờ
→ mới huỷ máy. Không bao giờ làm ngược.

## 7. Hai việc nên làm trước bước 3 (không chặn bước 1–2)

- **Service đang chạy bằng service account mặc định của Compute**
  (`1007100453671-compute@…`), vốn rộng quyền hơn mức cần. Nên tạo một SA riêng
  chỉ có `roles/secretmanager.secretAccessor` trên đúng các secret nó dùng. Đây
  là thay đổi IAM nên **không** làm trong phiên không người trực.
- **`timeoutSeconds=900`** của service: chương rất dài có thể vượt. Worker AWS
  không có trần này. Theo dõi p95 thời gian job ở bước 3 trước khi tin con số.

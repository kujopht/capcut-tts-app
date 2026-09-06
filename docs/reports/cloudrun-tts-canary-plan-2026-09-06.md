# Kế hoạch canary cho worker TTS trên Cloud Run — 2026-09-06

**CHƯA THỰC HIỆN.** Đây là kế hoạch; không bước nào dưới đây đã chạy.

Trạng thái hiện tại là **triển khai tối**: mã đã nằm trong kho, hạ tầng đã dựng,
và không một byte lưu lượng production nào bị đổi đường.

## 0. Vì sao canary chạy song song với AWS được mà không cần dừng AWS

Đây là điều làm kế hoạch này rẻ. `claim_job` là **compare-and-set thật sự**
trong một transaction Appwrite: hàng khoá `job_claims` có `rowId` tất định
`{job_id}-{attempt}`, nằm cùng transaction với lệnh cập nhật job. Hai worker
cùng giành một job thì **đúng một** commit được.

Nên Cloud Run và AWS có thể cùng ăn một hàng đợi production, cùng lúc, mà không
sinh audio trùng. Đã đo hai lần trong phiên nghiệm thu: 4 job bị cướp giữa
chừng, nhận lại bằng fence mới, và mỗi chương vẫn **đúng một** file `.mp3`.

Hệ quả thực tế: **"phần trăm canary" chính là số job được đẩy vào hàng đợi.**
Không cần bộ chia lưu lượng, không cần cờ phía người dùng. Job nào không được
đẩy thì AWS nhặt như hôm nay.

## 1. Bốn lớp tắt hiện tại

| # | Lớp | Trạng thái | Bật bằng |
|---|---|---|---|
| 1 | `FAS_TTS_DISPATCH` (phía tạo job) | không đặt = TẮT | đặt `cloudtasks` |
| 2 | Hàng đợi `tts-jobs` | **PAUSED** | `gcloud tasks queues resume` |
| 3 | `FAS_TTS_HTTP_ENABLED` (service) | không đặt = TẮT | đặt `true` |
| 4 | `APPWRITE_DATABASE_ID` của service | `dark_deploy_khong_co_db` (không tồn tại) | đổi sang DB thật |

Đã kiểm chứng: `GET /health` → `{"ok":true,"enabled":false}`;
`POST /tasks/tts` → `503`; không token → `403`; `min-instances=0`.

## 2. ĐIỀU KIỆN TIÊN QUYẾT — phải xong trước bước canary đầu tiên

**a. Ghép đúng cặp kho–bucket.** Đây là lỗi đã gây ra sự cố ngày 2026-09-06 và
tuyệt đối không được lặp lại. Nếu service trỏ vào `fanfic_world_prod` thì
`R2_BUCKET` **phải** là `fanfic-prod`, không phải `fanfic-staging`. Ghép lệch sẽ
tạo `audio_track` trỏ vào object mà đường đọc production không phân giải được —
trình phát hỏng câm lặng cho người dùng thật.

Cần thêm khoá R2 **production** vào Secret Manager (hiện chỉ có khoá phạm vi
`fanfic-staging`).

**Chỉ cần HAI giá trị, không phải bốn — và không cần tạo token Cloudflare mới.**
Đo được: `HeadBucket("fanfic-prod")` bằng khoá staging trả **403**, không phải
404. 403 nghĩa là bucket **tồn tại trong cùng tài khoản Cloudflare**
(`a0084e…`), chỉ là token không được cấp phạm vi tới nó. Nên
`tts-r2-account-id` đang có **dùng lại được y nguyên**; chỉ thiếu cặp khoá đã
được cấp phạm vi `fanfic-prod`:

```
tts-r2-prod-access-key-id
tts-r2-prod-secret-access-key
```

Cặp đó **đã tồn tại** — worker AWS production đang dùng nó để phục vụ audio thật
lúc này. Nó nằm trong `/etc/fanfic-audio/worker-prod.env` (`root:fanfic 0640`),
tên biến là `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` theo
`scripts/ops/cutover_target.py::REQUIRED_ENV_NAMES`.

**Ranh giới quyền.** Đọc tệp đó cần `root` trên máy production. `ubuntu` không
thuộc nhóm `fanfic` (đo được: `head -c 1` thất bại), và cổng điều hành
`fanfic-prod-admin` **không có verb đọc** — `ALLOW` chỉ gồm
`status install-env … canary rollback-note`, trong đó `status` che giá trị và
`install-env` chỉ GHI từ stdin. Nên việc chuyển phải do người có `root` thực
hiện. Đây là ranh giới root-of-trust thật, không phải một hàng rào đi vòng được.

**Lệnh chuyển — chạy trong Git Bash, giá trị không bao giờ hiện ra hay xuống đĩa:**

```bash
ssh -i ~/.ssh/fanficappwrrite.pem ubuntu@13.212.224.218 \
  "sudo grep -m1 '^R2_ACCESS_KEY_ID=' /etc/fanfic-audio/worker-prod.env | cut -d= -f2- | tr -d '\r\n'" \
| gcloud secrets create tts-r2-prod-access-key-id \
    --data-file=- --replication-policy=automatic --project=gen-lang-client-0793420657

ssh -i ~/.ssh/fanficappwrrite.pem ubuntu@13.212.224.218 \
  "sudo grep -m1 '^R2_SECRET_ACCESS_KEY=' /etc/fanfic-audio/worker-prod.env | cut -d= -f2- | tr -d '\r\n'" \
| gcloud secrets create tts-r2-prod-secret-access-key \
    --data-file=- --replication-policy=automatic --project=gen-lang-client-0793420657
```

`tr -d '\r\n'` là bắt buộc: `--data-file=-` đọc **nguyên xi byte** trên stdin, và
một dấu xuống dòng lạc vào khoá sẽ làm chữ ký S3 sai — lỗi lúc đó không hề gọi
tên nguyên nhân. (Trình đọc `verify_prod_r2_credential.py` cũng `.strip()` một
lần nữa, nên nếu bạn chạy bằng PowerShell thì dấu xuống dòng cuối vẫn được tha.)

**Kiểm ngay sau khi chuyển — CHỈ ĐỌC, không ghi gì vào `fanfic-prod`:**

```bash
python scripts/ops/verify_prod_r2_credential.py
```

Nó xác thực, `HeadBucket`, `ListObjectsV2(MaxKeys=1)`, in **độ dài** khoá chứ
không in giá trị, và cảnh báo nếu khoá mới nhìn thấy được cả `fanfic-staging`
(phạm vi rộng hơn mức cần). Quyền GHI **không** được thử ở đây: chứng minh một
khoá ghi được bằng cách ghi-rồi-xoá trên bucket audio thật của người dùng là
đánh đổi sai. Quyền ghi được chứng minh ở bước 1 của canary — một job thật, một
object thật, kiểm được bằng mắt.

**b. Dọn ba thứ còn lại** — xem mục 9 của
`docs/reports/cloudrun-tts-gates-3-6-2026-09-06.md`: xoá job `tts-worker-diag`,
xoá secret `appwrite-gate-provisioner`, thu hồi khoá API tạm trong Appwrite
Console.

**c. Quyết định số phận job `tts-worker`** (bản polling cũ). Env của nó vẫn là
cặp lệch `fanfic_world_prod` + `fanfic-staging`. Hoặc xoá hẳn, hoặc sửa env.
**Không để nguyên.**

## 3. Các bước canary

Mỗi bước có tiêu chí ĐẠT và một lệnh lùi. Không sang bước sau khi bước trước
chưa đạt đủ thời gian quan sát.

### Bước 1 — bật service, KHÔNG bật hàng đợi (khoảng 15 phút)

```
gcloud run services update tts-task-service --region=asia-southeast1 \
  --update-env-vars="FAS_TTS_HTTP_ENABLED=true,APPWRITE_DATABASE_ID=fanfic_world_prod,R2_BUCKET=fanfic-prod" \
  --update-secrets="R2_ACCESS_KEY_ID=tts-r2-prod-access-key-id:latest,R2_SECRET_ACCESS_KEY=tts-r2-prod-secret-access-key:latest"
```

Hàng đợi vẫn PAUSED, `FAS_TTS_DISPATCH` vẫn tắt. Gọi tay **đúng một** task cho
**một** `job_id` đang `pending` mà bạn chọn (chương của tài khoản nội bộ, không
phải của người đọc thật):

```
curl -X POST -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" -d '{"job_id":"<job_id>"}' \
     https://tts-task-service-1007100453671.asia-southeast1.run.app/tasks/tts
```

**ĐẠT khi:** trả `200 {"ket_qua":"hoan_tat"}`; object nằm trong **`fanfic-prod`**;
`audio_track` trỏ đúng khoá đó; job `completed` với `lease_owner` rỗng; nghe thử
audio ra tiếng.

**Lùi:** `--update-env-vars="FAS_TTS_HTTP_ENABLED=false"`.

### Bước 2 — mở hàng đợi, vẫn chưa đẩy tự động (khoảng 30 phút)

```
gcloud tasks queues resume tts-jobs --location=asia-southeast1
```

Đẩy tay 3–5 job bằng `gcloud tasks create-http-task` với OIDC của
`tts-tasks-invoker@…`. Mục đích là kiểm **đường hàng đợi**, không phải sức tải:
xác nhận OIDC được chấp nhận, backoff hoạt động, và task trùng bị chặn bởi
`rowId` tất định `tts-{job_id}`.

**ĐẠT khi:** mọi task về `200`; không job nào có `attempts` nhảy quá 1; không
chương nào có hai `.mp3`.

**Lùi:** `gcloud tasks queues pause tts-jobs --location=asia-southeast1`.

### Bước 3 — bật đẩy tự động cho một phần nhỏ (24 giờ)

Đặt `FAS_TTS_DISPATCH=cloudtasks` cùng bốn biến `FAS_TTS_TASKS_*` trên tiến
trình web. Từ đây **mọi job mới** đều được đẩy — nên nếu muốn ít hơn 100%, hãy
giới hạn bằng `maxConcurrentDispatches` của hàng đợi thay vì sửa mã.

Trong 24 giờ này AWS **vẫn chạy nguyên**. Job nào Cloud Run không kịp giành thì
AWS nhặt; đó là hành vi đúng, không phải sự cố.

**ĐẠT khi, so với 24 giờ trước đó:** tỉ lệ job `failed` không tăng; không job
nào chạm `attempts=3`; số `audio_track` bằng số job `completed`; không chương
nào có hơn một `.mp3`; p95 thời gian job không xấu hơn.

**ABORT NGAY nếu:** xuất hiện `audio_track` trỏ vào object không tồn tại; hoặc
một chương có hai `.mp3`; hoặc `failed` tăng.

**Lùi:** bỏ `FAS_TTS_DISPATCH` trên web → job mới quay về đúng đường hôm nay.

### Bước 4 — chạy song song 72 giờ

Không đổi cấu hình. Chỉ quan sát. Mục đích là bắt những thứ chỉ lộ ra theo
thời gian: rò rỉ bộ nhớ, lease treo lúc tải cao, chi phí thật của scale-to-zero.

**ĐẠT khi:** ba ngày liên tiếp không có mục nào trong danh sách ABORT.

### Bước 5 — rút AWS (KHÔNG nằm trong kế hoạch này)

Chỉ bàn sau khi bước 4 đạt. Và rút đúng thứ tự: **dừng** unit AWS trước, quan
sát 24 giờ, rồi mới huỷ máy — không bao giờ làm ngược.

## 4. Ba vấn đề đã sửa (commit `56203b6`)

Ba thứ mục này từng liệt là "kế hoạch không giải quyết" — nay đã sửa và có test.

- **`voice_runnable_on_this_machine` trả `True` khi thiếu gói Piper.** Nay hỏi
  RUNTIME trước, MODEL sau: thiếu `piper-tts` → **nhường**, không nhận rồi đốt
  `attempts`. Có test chạy qua đúng vòng quét thật, và đã kiểm test có răng.
- **Nhánh bỏ qua của `recover_stale_jobs` im lặng.** Nay ghi log khi tình hình
  ĐỔI, cộng nhịp nhắc lại ~5 phút. Một worker không bao giờ giành được job giờ
  trông khác hẳn một worker khoẻ.
- **`piper:ngochuyen` khi ảnh chỉ có `ngochuyennew`.** Service trả **200** kèm
  `nhuong_thieu_model` chứ không 409: ảnh này sẽ không bao giờ có thêm model
  nên 409 chỉ làm Cloud Tasks xoay vòng đến hết `max-attempts`. Ack, và để
  đường quét (AWS, đủ bộ model) nhặt. **Vẫn phải kiểm `FAS_LOCAL_VOICES` thật
  của production trước bước 3**: nếu production còn phục vụ `piper:ngochuyen`
  thì AWS phải ở lại, và đó là điều kiện của bước 5 chứ không phải của canary.

## 5. Những gì kế hoạch này KHÔNG giải quyết

- **Quyền GHI vào `fanfic-prod` chưa được chứng minh**, chỉ suy ra từ việc
  worker AWS đang dùng đúng cặp khoá đó để phục vụ audio thật. Bước 1 là nơi
  chứng minh.
- **Ảnh Cloud Run chỉ có một giọng.** Muốn Cloud Run thay hẳn AWS thì phải bake
  đủ bộ NghiTTS, và đó là một vòng nghiệm thu tương đương nữa.

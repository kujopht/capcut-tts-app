# Báo cáo chuẩn bị staging

Xuất phát từ `c1e5373` trên `feature/web-mvp`. Lượt này **chuẩn bị** staging;
**chưa deploy** vì ba tài nguyên bắt buộc cần credential mà môi trường hiện tại
không có. Mục 8 liệt kê chính xác từng bước thủ công.

Đã khử dữ liệu nhạy cảm: không có token, API key, cookie, presigned URL hay
định danh đầy đủ nào trong tài liệu này.

---

## 1. Preflight

| Kiểm tra | Kết quả |
|---|---|
| Working tree | sạch |
| Local `HEAD` = remote `feature/web-mvp` | `c1e5373` cả hai |
| Draft PR #1 | `state=open`, `draft=true`, `merged=false`, `mergeable_state=clean` |
| CI cho `c1e5373` | **2 run, cả hai `success`** (sự kiện `push` và `pull_request`), 4/4 job đạt |
| Dữ liệu production/dev | **không dùng, không sửa, không xoá** — đối chiếu ảnh chụp id trước/sau |

### Cách khởi động **trước** lượt này

| Thành phần | Cách chạy | Vấn đề |
|---|---|---|
| Web (Next.js) | `next build` + `next start` | — |
| Backend (FastAPI) | `uvicorn server.main:app` | — |
| TTS worker | **không có tiến trình riêng** — chạy trong `threading.Thread` bên trong tiến trình web, khởi động từ `@app.on_event("startup")` và từ `POST /api/jobs` | Restart web là giết job đang chạy; chương dài giữ thread hàng chục phút trong tiến trình phục vụ request; không scale độc lập được |

Repo **chưa từng chọn** nền tảng hosting: không có `Dockerfile`, `vercel.json`,
`render.yaml`, `fly.toml`, `Procfile` hay `docker-compose` ở bất kỳ commit nào.

### Tài nguyên persistence hiện có

| Tài nguyên | Hiện trạng |
|---|---|
| Appwrite project | **1** project (dev), endpoint `sgp.cloud.appwrite.io` |
| Appwrite database | **1**, kiểu `tablesdb` |
| Appwrite collections | **6**: `profiles` (20 bản ghi), `novels` (18), `chapters` (31), `tts_jobs` (13), `audio_tracks` (11), `job_claims` (0) |
| **Appwrite Storage bucket** | **0 bucket, và mã nguồn không hề gọi Appwrite Storage** → staging **không cần** tạo bucket Appwrite |
| Cloudflare R2 | **1** bucket, 11 object, 0,4 MiB, tất cả dưới tiền tố `audio/` |
| Edge TTS | dịch vụ công khai của Microsoft, không cần credential |
| CapCut / Piper | chỉ dùng cho desktop, không nằm trong đường web |

---

## 2. Quyền hiện có — vì sao chưa deploy được

Kiểm bằng phép thử **chỉ đọc**:

| Thao tác cần cho staging | Kết quả | Kết luận |
|---|---|---|
| Tạo Appwrite **project** | `GET /v1/projects` → **401**, `GET /v1/account` → **401** | API key là **service key phạm vi project** (role `application`). Tạo project cần phiên Console. **Không làm được.** |
| Tạo Appwrite **database** trong project hiện tại | `GET /v1/databases` → 200 | Làm được — nhưng **không phải mức cô lập bạn yêu cầu**: cùng project, cùng API key, key rò rỉ là chạm được cả hai |
| Tạo **R2 bucket** | `ListBuckets` → **AccessDenied** | Credential giới hạn trong đúng một bucket. **Không làm được.** |
| Cloudflare API token / `wrangler` | không có biến môi trường nào, CLI không cài | **Không làm được.** |
| CLI hosting (Vercel/Render/Fly/Railway/Docker) | **không cái nào được cài**, không credential | **Không làm được.** |

Theo yêu cầu A.4, tôi **dừng đúng tại đây** và không thay thế bằng secret giả.

---

## 3. Tách TTS worker khỏi web — ĐÃ LÀM

### Thiết kế

Một cờ cấu hình mới, `FAS_INLINE_WORKER` (mặc định `true`, giữ nguyên hành vi cũ):

- `true` — web tự chạy job trong thread nền. Tiện lúc phát triển.
- `false` — web **chỉ** phục vụ request. Job nằm `pending` cho `server/worker.py`.

**Không sao chép logic.** `server/worker.py` chỉ là vòng lặp gọi lại đúng những
hàm web vẫn dùng: `main.recover_stale_jobs()` → `store.claim_job()` (transaction)
→ `main._run_job()` với fencing token. Claim nguyên tử, lease/heartbeat, fencing,
giới hạn số lần thử và tính idempotent của track/object đều là **cùng một mã
nguồn** ở cả hai chế độ.

### Một lỗi thật, do chính diễn tập bắt được

Ban đầu tôi gộp hai ý khác nhau vào cùng một cờ. Worker riêng cũng đọc
`FAS_INLINE_WORKER=false` nên nó **tự cấm chính mình**: nó **nhận** job (tăng
`attempts`) rồi **không chạy**, và mỗi vòng quét lại đốt thêm một lần thử cho tới
khi job `failed` oan — tệ hơn hẳn trạng thái trước khi sửa.

Bằng chứng quan sát được: `attempts=2`, `tiến độ 0/0`, log báo `chay_lai: 1`
trong khi không có job nào chạy.

Sửa bằng cách tách hai khái niệm:

| Khái niệm | Biểu diễn |
|---|---|
| "**web** có tự chạy job không" | `settings.inline_worker` (từ biến môi trường) |
| "**tiến trình này** có được chạy job không" | `main._CAN_RUN_JOBS`, bật tường minh bằng `main.enable_job_execution()` — chỉ `server/worker.py` gọi |

Thêm hai lớp phòng vệ:

1. `recover_stale_jobs()` **thoát ngay** nếu tiến trình không được phép chạy job
   — không nhận thì không đốt `attempts`;
2. `chay_lai` chỉ đếm khi thread **thật sự** khởi động, không đếm ý định.

### Kết quả diễn tập (Appwrite + R2 thật, fixture `[REHEARSAL]`, đã xoá sạch)

| Kiểm tra | Kết quả |
|---|---|
| `FAS_INLINE_WORKER=false` → web không chạy job | **ĐẠT** — job `pending`, `attempts=0` sau 12 giây |
| Worker riêng nhận và chạy | **ĐẠT** — nhận trong ~3 giây, `attempts=1`, tiến độ 9/60 |
| `worker --check` | **ĐẠT** — `{"trang_thai":"dang_chay","tuoi_nhip_giay":1,"so_job_dang_chay":1}` |
| **Restart web giữa lúc worker chạy** | **ĐẠT** — worker sống nguyên, job hoàn tất với `attempts=1` |
| **Kill cưỡng chế worker** → web có gián đoạn? | **ĐẠT** — web trả HTTP 200 ngay lập tức |
| Lease còn hạn thì worker mới **không giật** | **ĐẠT** — worker mới chạy từ 16:23:54, job vẫn thuộc worker đã chết tới 16:25:01 |
| Sau khi lease hết hạn thì nhận lại | **ĐẠT** — nhận lúc 16:25:09, `attempts=2` |
| Kết quả cuối | **1 track, 1 object** (7.905.837 byte) |
| Số dòng `job_claims` | **đúng 2**, cách nhau **126 giây** (lease 90 giây) |
| Worker cũ ghi đè bằng fence cũ | **bị từ chối** (`save_job_fenced → False`), job vẫn `completed` |

Dòng thời gian recovery:

| Giờ UTC | status | attempts | tiến độ | lease_owner |
|---|---|---|---|---|
| 16:23:35 | `running` | 1 | 37/75 | `52944-…` |
| 16:23:42 | *giết cả cây tiến trình worker* | | | |
| 16:23:54 | *worker thay thế khởi động* | | | |
| 16:24:10 | `running` | 1 | 37/75 | `52944-…` (**đã chết**) — worker mới **bỏ qua** |
| 16:25:09 | `running` | **2** | 37/75 | `26348-…` |
| 16:26:10 | `completed` | 2 | 75/75 | `(trống)` |

### Chưa kiểm chứng được

**Dừng sạch bằng SIGTERM.** Windows không gửi được tín hiệu dừng mềm cho tiến
trình nền không có cửa sổ console (`taskkill` không `/F` trả về *"can only be
terminated forcefully"*). Đây là giới hạn của nền tảng, không phải lỗi mã. Đường
kill cưỡng chế **đã** kiểm và recovery hoạt động. Phải xác minh dừng sạch trên
host Linux của staging.

### Nhiều worker

Chạy thêm tiến trình `python -m server.worker`. Không cần cấu hình gì thêm: mỗi
tiến trình có `WORKER_ID` riêng và claim là compare-and-set thật, nên một job chỉ
một worker thắng. Đã kiểm chứng ở lượt trước trên Appwrite thật: 5 lượt × 10
worker → đúng 1 worker thắng mỗi lượt.

### Health / readiness

| Thành phần | Liveness | Readiness |
|---|---|---|
| Frontend | `GET /` → 200 | — |
| Backend | `GET /api/health` — **không** chạm Appwrite/R2 | `GET /api/ready` — chạm cả hai, **503** khi hỏng |
| Worker | tiến trình còn sống | `python -m server.worker --check` |

`/api/health` cố ý không kiểm phụ thuộc: sự cố tạm thời của Appwrite không được
làm nền tảng giết một tiến trình web đang lành mạnh. `/api/ready` chỉ trả **tên
loại lỗi**, không trả thông điệp (thông điệp có thể chứa endpoint hoặc định danh).

---

## 4. Cấu hình deploy — ĐÃ LÀM

| Tệp | Nội dung |
|---|---|
| `deploy/README.md` | Kiến trúc ba workload, bảng biến môi trường theo từng workload, so sánh nền tảng |
| `deploy/Procfile` | Ba tiến trình: `web`, `worker`, `frontend` |
| `deploy/render.yaml` | Mẫu Render — **chưa kiểm chứng**, chưa có tài khoản |
| `deploy/RUNBOOK.md` | Migration, restart, rollback, kiểm job kẹt, chạy reconciler |
| `deploy/reconcile-cron.md` | Lịch reconciler ở chế độ **chỉ đọc** |
| `server/.env.example` | Thêm `FAS_INLINE_WORKER`, ba biến worker, bảng phân loại biến |
| `scripts/print_config.py` | In cấu hình đang có hiệu lực — **tiền tố** định danh, secret chỉ nói có/không |

### Phân loại biến

| Loại | Biến |
|---|---|
| **Công khai** (vào bundle trình duyệt) | `NEXT_PUBLIC_API_BASE` |
| **Secret, chỉ backend + worker** | `APPWRITE_API_KEY`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` |
| **Định danh** (không phải secret, không nên công khai) | `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_DATABASE_ID`, `R2_ACCOUNT_ID`, `R2_BUCKET` |
| **Chỉ worker** | `FAS_WORKER_POLL_SECONDS`, `FAS_WORKER_GRACE_SECONDS`, `FAS_WORKER_STALE_SECONDS` |

**Không giá trị thật nào** nằm trong repo.

### Fail fast

`Settings.validate()` chạy khi import `server.main` **và** trong
`server/worker.py`. Thiếu bất kỳ biến Appwrite/R2 nào khi đã chọn chế độ cloud →
dừng ngay, không âm thầm lui về mock. `FAS_INLINE_WORKER` nhận giá trị không hiểu
được (`flase`, `maybe`, `2`) → **dừng ngay**, không lấy mặc định — có test khoá.

### Khuyến nghị nền tảng

Repo chưa chọn gì, nên đây là khuyến nghị chứ không phải quyết định đã chốt.

| Nền tảng | Frontend | Backend | Worker chạy dài |
|---|---|---|---|
| **Render** ← khuyến nghị | ✅ | ✅ | ✅ Background Worker |
| Fly.io | ✅ | ✅ | ✅ (cần Dockerfile — repo chưa có, chưa test build được) |
| Railway | ✅ | ✅ | ✅ |
| Vercel | ✅ | ⚠️ serverless | ❌ **không có tiến trình chạy dài** |

**Không đặt worker vào serverless request handler**: handler bị giới hạn thời
gian và bị đóng băng giữa các lần gọi, nên lease sẽ hết hạn giữa chừng và job
xoay vòng vô ích.

---

## 5. Reconciler và vận hành — ĐÃ LÀM

Lịch chạy mẫu ở `deploy/reconcile-cron.md`, **chế độ chỉ đọc**, không có `--delete`
trong `startCommand`. Chế độ xoá tự động **chưa bật** và không nên bật cho tới khi
đã đọc báo cáo dry-run vài tuần.

Kết quả dry-run cuối trên tài nguyên hiện có: **11 object, 11 đã được tham chiếu,
0 mồ côi, 0 bản ghi thiếu file, 0 lỗi.**

Runbook (`deploy/RUNBOOK.md`) gồm: migration, restart backend, restart worker,
chạy nhiều worker, đọc bảng chẩn đoán job kẹt, chạy reconciler thủ công, rollback
mã / rollback schema / rollback khẩn cấp về chế độ inline, và danh sách việc
tuyệt đối không làm.

**Không có migration hay xoá object nào chạy tự động lúc service khởi động.**
Startup chỉ đọc.

---

## 6. Lỗi phát hiện trong lượt này

| # | Lỗi | Sửa | Test |
|---|---|---|---|
| 1 | Worker riêng **nhận job rồi không chạy**, mỗi vòng quét đốt một `attempts` cho tới khi job `failed` oan. Do gộp "web có chạy job không" và "tiến trình này có chạy job không" vào một cờ. | Tách thành `settings.inline_worker` và `main._CAN_RUN_JOBS`; `recover_stale_jobs` thoát ngay nếu không được phép chạy; `chay_lai` chỉ đếm thread thật sự khởi động | `test_worker_split.py` — 5 test trong `TestASweeperThatCannotRunMustNotClaim` |
| 2 | Xoá truyện/chương dọn track, job và object nhưng **bỏ lại các dòng `job_claims`**. `job_claims` chỉ tăng, không bao giờ giảm — sau hai lượt kiểm thử còn lại hàng chục dòng trỏ tới job không tồn tại, phải dọn tay hai lần. | `delete_job()` ở **cả hai** store dọn luôn claim của job đó. Xoá job trước, dọn claim sau. | `TestDeletingAJobCleansItsClaims` — 3 test, **2 hỏng** trên mã cũ |

Cả hai đều được kiểm chứng là **hỏng trên mã trước khi sửa**.

---

## 7. Kết quả kiểm tra

| Bộ | Số lượng | Kết quả |
|---|---|---|
| `server/tests` (điều kiện như CI, không `.env`) | **547** | 546 đạt, 1 bỏ qua — chạy **3 lần**, ổn định |
| `compileall server scripts` | — | đạt |
| `web` (`node --test`) | **152** | 152 đạt |
| `npx tsc --noEmit` | — | exit 0 |
| `npx eslint .` | — | exit 0 |
| `npx next build` | — | exit 0 |
| Diễn tập tách worker (Appwrite + R2 thật) | 11 mục | tất cả đạt |
| Đối chiếu dữ liệu trước/sau diễn tập | 6 tập hợp | **mất 0, sót 0** |

Smoke test staging đầy đủ (mục G của yêu cầu) **chưa chạy được** vì chưa có URL
staging. Những phần không phụ thuộc URL đã được kiểm trong diễn tập ở mục 3.

---

## 8. Việc thủ công đang chặn — làm theo đúng thứ tự

### Bước 1 — Appwrite project staging

1. Mở https://cloud.appwrite.io → **Create project**.
   - Tên: `fanfic-audio-staging`
   - Region: **Singapore (sgp)** — cùng vùng với project dev để độ trễ tương đương.
2. Trong project mới: **Databases** → **Create database**, tên `fas`.
   Ghi lại **Database ID**.
3. **Overview → Integrations → API Keys** → **Create API key**:
   - Tên: `staging-backend`
   - Scope **tối thiểu**: `databases.read`, `databases.write`,
     `collections.read`, `collections.write`, `attributes.read`,
     `attributes.write`, `indexes.read`, `indexes.write`,
     `documents.read`, `documents.write`, `users.read`, `users.write`,
     `sessions.write`
   - **Không** cấp `functions.*`, `storage.*`, `teams.*` — ứng dụng không dùng.
4. Nếu tạo được **hai** key riêng cho backend và worker thì tốt hơn: thu hồi được
   từng bên khi lộ.

> **Không cần** tạo Appwrite Storage bucket: mã nguồn không hề gọi Appwrite
> Storage, và project dev hiện có **0** bucket.

### Bước 2 — R2 bucket staging

1. Cloudflare dashboard → **R2** → **Create bucket**, tên `fanfic-staging`.
   Giữ **private**, không bật public access.
2. **R2 → Manage API Tokens** → **Create API token**:
   - Permission: **Object Read & Write**
   - **Specify bucket**: chỉ `fanfic-staging` — không chọn "all buckets"
3. Ghi lại Access Key ID, Secret Access Key, và Account ID.

### Bước 3 — Hosting

Khuyến nghị **Render** (nền tảng duy nhất trong bảng hỗ trợ trực tiếp cả ba
workload mà không cần Dockerfile).

1. Tạo tài khoản, kết nối repo `kujopht/capcut-tts-app`.
2. **Blueprint** → trỏ vào `deploy/render.yaml`, hoặc tạo tay ba service:
   - `fas-staging-api` — Web Service, Python, start `python -m uvicorn server.main:app --host 0.0.0.0 --port $PORT`
   - `fas-staging-worker` — **Background Worker**, Python, start `python -m server.worker`
   - `fas-staging-web` — Web Service, Node, rootDir `web`, start `npx next start --port $PORT`
3. Cả ba đặt branch `feature/web-mvp`, `autoDeploy: false`, deploy từ đúng SHA.
4. Điền biến môi trường theo bảng ở `deploy/README.md`. Bắt buộc:
   `FAS_ENV=staging`, `FAS_INLINE_WORKER=false` cho **cả** api và worker.
5. Worker và web service ở Render đều cần gói trả phí (gói miễn phí ngủ khi
   không có traffic — worker chạy dài không dùng được).

### Bước 4 — Migration, rồi RESTART

```bash
PYTHONPATH=. python scripts/setup_appwrite.py     # idempotent, không xoá gì
```

Sau đó **restart cả `fas-staging-api` và `fas-staging-worker`**.
`_supported_fields()` cache theo vòng đời tiến trình; tiến trình đang chạy sẽ
không thấy trường vừa thêm và claim tiếp tục chạy ở nhánh **không nguyên tử** mà
không báo lỗi gì.

### Bước 5 — Xác minh trỏ đúng tài nguyên

```bash
python scripts/print_config.py     # trên chính host staging
curl -s $API/api/health | jq '{status, inline_worker, environment}'
curl -s -o /dev/null -w '%{http_code}\n' $API/api/ready       # phải 200
python -m server.worker --check                                # exit 0
```

Đối chiếu **tiền tố** `project_id` và `bucket` với tài nguyên staging. Trùng tiền
tố với dev nghĩa là đang trỏ nhầm.

### Bước 6 — Giữ staging riêng tư

Render không có "password protect" sẵn ở gói starter. Ba cách:

| Cách | Đánh đổi |
|---|---|
| Cloudflare Access đặt trước frontend | Tốt nhất; cần domain qua Cloudflare |
| Basic auth ở middleware Next.js | Nhanh, nhưng phải viết mã và giữ một secret nữa |
| Không public URL, chỉ dùng URL `onrender.com` khó đoán | **Không phải bảo mật** — chỉ là mờ mịt. Chấp nhận được cho staging chứa 100% dữ liệu giả |

Chưa gắn custom domain production.

### Bước 7 — Branch protection (xem mục 9)

---

## 9. Branch protection cho `main`

**Chưa bật được.** Cả hai API đều trả **403 — "Upgrade to GitHub Pro or make this
repository public to enable this feature"**:

- `PUT /repos/{owner}/{repo}/branches/main/protection`
- `POST /repos/{owner}/{repo}/rulesets`

Repo đang **private** trên gói free. Ba lựa chọn:

1. Nâng lên **GitHub Pro** (~4 USD/tháng) → bật được cho repo private;
2. Chuyển repo thành **public** → miễn phí, **nhưng xem blocker ở mục 10**;
3. Chấp nhận chưa có → merge PR thủ công sau khi tự kiểm CI đã đạt.

Khi bật được, dùng đúng cấu hình này (đã soạn sẵn, chỉ chưa apply được):

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend tests (moi truong sach)",
      "Web tests, TypeScript, ESLint, production build"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
```

Hoặc qua giao diện: **Settings → Branches → Add branch protection rule** →
pattern `main` → bật *Require status checks to pass before merging* (chọn cả hai
check ở trên) + *Require branches to be up to date before merging*, và **tắt**
*Allow force pushes* và *Allow deletions*.

---

## 10. Blocker

### Trước khi deploy staging

| # | Blocker | Ai làm |
|---|---|---|
| 1 | Chưa có Appwrite project staging — API key hiện tại là service key phạm vi project, không tạo project được | **bạn** (mục 8 bước 1) |
| 2 | Chưa có R2 bucket staging — credential giới hạn trong một bucket, `ListBuckets` bị `AccessDenied` | **bạn** (bước 2) |
| 3 | Chưa có tài khoản hosting; không CLI nào được cài | **bạn** (bước 3) |
| 4 | Worker chạy dài trên Render cần gói trả phí | **bạn** |

### Trước khi merge PR

| # | Blocker | Mức |
|---|---|---|
| 5 | Branch protection chưa bật (cần GitHub Pro hoặc repo public) | Trung bình |
| 6 | Smoke test staging **chưa chạy** — bị chặn bởi 1–4 | **Cao** |
| 7 | Dừng sạch bằng SIGTERM chưa kiểm chứng được trên Windows; phải xác minh trên host Linux | Trung bình |
| 8 | `deploy/render.yaml` **chưa từng được apply** — mẫu, không phải cấu hình đã chạy | Trung bình |

### Trước khi chuyển repo thành public

| # | Blocker | Mức |
|---|---|---|
| 9 | **Hai ảnh chụp trong lịch sử** (`a06177f`, `afea269`) hiển thị **email cá nhân** của chủ repo, do trình duyệt tự điền vào form đăng nhập. Bản mới nhất đã che, nhưng blob gốc vẫn nằm trong lịch sử và **không thể xoá nếu không rewrite 30 commit**. Chuyển repo thành public là công khai địa chỉ email đó vĩnh viễn. | **BẮT BUỘC xử lý trước khi public** |
| 10 | Email tác giả trong metadata của cả 32 commit cũng sẽ công khai (cơ chế bình thường của git, nhưng nên biết trước) | Thấp |

> Blocker #9 và lựa chọn "chuyển repo thành public để có branch protection miễn
> phí" ở mục 9 **xung đột trực tiếp** với nhau. Nếu muốn public thì phải rewrite
> lịch sử trước — điều đã bị loại trừ tường minh ở lượt trước.

### Trước khi gắn domain và mở cho người dùng

| # | Blocker |
|---|---|
| 11 | Giấy phép thương mại của giọng đọc chưa xác minh |
| 12 | Chưa có payment / quota / admin / moderation |
| 13 | Chưa kiểm ở tải cao; chưa benchmark chương 1.000.000 ký tự |
| 14 | Reconciler chưa chạy tự động; chưa có cron |
| 15 | Chưa có route xoá tài khoản người dùng |

---

## 11. Lượt triển khai ngày 2026-08-08 — VẪN CHƯA DEPLOY ĐƯỢC

Bạn báo đã tạo Appwrite staging, R2 bucket staging và kết nối repo với Render.
Nhưng **không credential nào trong số đó có mặt trên máy này**, nên các bước 4–7
vẫn bị chặn.

### Đã kiểm

| Kiểm tra | Kết quả |
|---|---|
| local `HEAD` = remote `feature/web-mvp` | `79a8c57` cả hai |
| CI cho `79a8c57` | 2 run, cả hai `success`, 4/4 job đạt |
| Working tree | sạch |
| `deploy/render.yaml` | **hợp lệ** — 3 service, không secret viết sẵn, worker không `healthCheckPath`, cả hai service Python đặt `FAS_INLINE_WORKER=false` |

### Vì sao vẫn chặn

| Thứ cần | Tình trạng trên máy này |
|---|---|
| Appwrite **staging** endpoint/project/database/API key | **không có** — `server/.env` sửa lần cuối 2026-08-06, `print_config.py` cho thấy tiền tố `project_id`/`database_id` và tên bucket **trùng khớp với dev**, không phải staging |
| R2 **staging** account/bucket/access key | **không có** — cùng lý do trên |
| Render API key hoặc CLI | **không có** — không biến `RENDER_*`, không `render` trong PATH, không `~/.render` |
| Cloudflare token / `wrangler` | **không có** |

Kết nối repo với Render ở phía dashboard **không** cấp cho môi trường này quyền
gì: không có API key thì không liệt kê được service, không trigger được deploy,
không đọc được URL hay SHA đang chạy.

Theo yêu cầu, tôi **không** hỏi bạn dán secret vào chat. Mục 12 nêu cách đưa
chúng vào mà không phải dán.

### Đã làm được trong lượt này

**`scripts/staging_smoke.py`** — smoke test chạy bằng **một lệnh** với bất kỳ bản
triển khai nào, chỉ qua HTTP API công khai nên không cần credential kho dữ liệu:

```bash
PYTHONPATH=. python scripts/staging_smoke.py   --api https://fas-staging-api.onrender.com   --web https://fas-staging-web.onrender.com   --json bao-cao-smoke.json
```

Phủ: health/readiness, `environment=staging`, `inline_worker=false`, đăng
ký/đăng nhập/đăng nhập lại, chặn ẩn danh và token bịa, novel/chapter và tính bền
vững, TTS `pending → running → completed` (chứng minh **worker riêng** nhận, vì
web không chạy job), tải file audio thật và kiểm MP3 frame header, phân quyền
giữa hai tài khoản trên 8 đường, frontend phản hồi. **Tự dọn fixture `[SMOKE]`
trong `finally`**, kể cả khi có bước hỏng.

Đã chạy thử với backend + worker cục bộ dựng đúng hình dạng staging
(`FAS_INLINE_WORKER=false`, `FAS_ENV=staging`, Appwrite + R2 + Edge TTS thật):
**43/43 đạt**, chuỗi trạng thái `pending → running → completed` ở giây 6 và 79,
file 553.248 byte, `attempts=1`. Fixture đã xoá, đối chiếu 6 tập hợp trước/sau:
**mất 0, sót 0**.

### Một lỗi tự phát hiện và đã sửa

Bản đầu của `rut_gon_url()` chỉ bỏ query, nên nó **in nguyên host và đường dẫn
presigned URL** ra log — lộ **R2 account id**, tên bucket, `owner_id`,
`chapter_id` và hash nội dung. Đúng thứ mà yêu cầu "không in secret vào log"
cấm.

Nay che cả host lẫn đường dẫn, chỉ giữ đuôi tệp và cờ "có query hay không".
Regression test `server/tests/test_staging_smoke_script.py` — 9 test; **5 hỏng**
trên bản cũ. Quét lại toàn bộ 67 dòng đầu ra: **không còn dấu hiệu nào**.

---

## 12. Cách đưa credential vào mà không phải dán vào chat

Chọn **một** trong hai.

### Cách A — tệp cục bộ (đơn giản nhất)

Tạo `server/.env.staging` với nội dung dưới đây, điền giá trị thật. Tệp này
**đã bị `.gitignore` chặn** (đã kiểm: khớp luật `.env.*`), không bao giờ vào git.

```
FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=r2
FAS_CORS_ORIGINS=<URL frontend staging>

APPWRITE_ENDPOINT=<endpoint staging>
APPWRITE_PROJECT_ID=<project id staging>
APPWRITE_DATABASE_ID=<database id staging>
APPWRITE_API_KEY=<api key staging>

R2_ACCOUNT_ID=<account id>
R2_BUCKET=<bucket staging>
R2_ACCESS_KEY_ID=<access key id>
R2_SECRET_ACCESS_KEY=<secret access key>
```

Rồi nhắn "đã tạo `server/.env.staging`". Tôi chạy migration bằng
`FAS_ENV_FILE=server/.env.staging` và không hề in giá trị nào.

### Cách B — biến môi trường trong phiên của bạn

Trong Claude Code, gõ `!` rồi lệnh để nó chạy trong chính phiên này:

```
! $env:APPWRITE_PROJECT_ID = "..."   # và các biến còn lại
```

### Cho Render

Cần **API key** để tôi deploy và đọc SHA/URL:

1. https://dashboard.render.com/u/settings#api-keys → **Create API Key**
2. Đặt vào biến môi trường: `RENDER_API_KEY`

Không muốn cấp API key cũng được — khi đó bạn tự tạo ba service theo mục 8, rồi
gửi tôi **URL** (không phải secret) để tôi chạy `staging_smoke.py`.

---

## 13. Phương án staging GÓI FREE — không cần thẻ

Bạn không muốn nhập thẻ. Đã chuẩn bị Blueprint riêng.

**Blueprint Path nhập trên Render: `deploy/render.free.yaml`**

`deploy/render.yaml` (bản trả phí) **giữ nguyên**, không sửa một dòng — có test khoá.

### Khác biệt

| | `render.yaml` | `render.free.yaml` |
|---|---|---|
| Gói | `starter` (trả phí) | **`free`** |
| Số service | 3 | **2** |
| Background Worker | có | **không** — gói Free không hỗ trợ |
| Worker TTS chạy ở đâu | trên Render | **trên máy bạn** |
| Cron reconciler | có mẫu | chạy tay |

### Frontend KHÔNG phải Static Site — có bằng chứng

Đã thử `output: 'export'` thật, build dừng ở:

```
Error: Page "/chapters/[id]" is missing "generateStaticParams()"
       so it cannot be used with "output: export" config.
```

`/novels/[id]` và `/chapters/[id]` nhận id là dữ liệu người dùng lúc chạy, không
liệt kê được lúc build. Muốn thành Static Site phải đổi sang dạng query
(`/novels?id=…`) — đổi URL công khai, đổi liên kết, đổi test. **Web Service gói
Free vẫn miễn phí** và không phải sửa gì.

### Đánh đổi của gói Free

| Điều | Hệ quả |
|---|---|
| Ngủ sau **15 phút** không traffic | Request đầu mất ~50 giây; hai service nên lần mở đầu có thể ~100 giây. `staging_smoke.py --wake-timeout` lo việc này |
| 750 giờ instance/tháng | Vì tự ngủ nên hiếm khi chạm trần |
| 512 MB RAM mỗi service | Đủ cho quy mô staging |
| Không Background Worker | Worker chạy trên máy bạn |
| Không Cron Job | Reconciler chạy tay |
| Máy bạn tắt | Job nằm `pending`; **không mất dữ liệu** |

**Backend ngủ KHÔNG làm job TTS dừng** — worker nói chuyện thẳng với Appwrite/R2,
không qua backend. Nhưng **tạo** job thì cần backend thức.

### Lệnh chạy worker cục bộ

Chuẩn bị `server/.env.staging` một lần (đã kiểm: `.gitignore` chặn qua `.env.*`),
nội dung ở `deploy/RUNBOOK.md` mục 2b.

**PowerShell:**

```powershell
cd C:\Users\robux\Documents\CapCut-TTS-App
$env:FAS_ENV_FILE = "server/.env.staging"
.\.venv\Scripts\python.exe -m server.worker --require-env staging
```

**bash:**

```bash
FAS_ENV_FILE=server/.env.staging ./.venv/bin/python -m server.worker --require-env staging
```

Kiểm nhịp: `python -m server.worker --check`

### Hai rào chắn chống trỏ nhầm tài nguyên

**1. `--require-env staging` trên worker.** `server/config.py` mặc định nạp
`server/.env` — tệp dev. Quên `FAS_ENV_FILE` thì worker sẽ **lặng lẽ** xử lý job
của dev bằng credential dev. Cờ này biến im lặng đó thành một lần dừng hẳn: tệp
dev ghi `FAS_ENV=development`, không khớp, worker **thoát mã 2**.

Đã thử thật:

```
{"muc": "dung_vi_sai_moi_truong", "mong_doi": "staging", "thuc_te": "development",
 "thong_diep": "FAS_ENV không khớp. Nhiều khả năng đang nạp nhầm file cấu hình…"}
exit=2
```

**2. `Settings.validate()` chặn sai hình dạng.** `FAS_ENV` là `staging`/
`production` mà `FAS_INLINE_WORKER` vẫn bật → **dừng ngay khi khởi động**. Ở gói
Free điều này đặc biệt quan trọng: nếu web tự chạy job thì Render sẽ ngủ nó giữa
chừng sau 15 phút. Đường thoát hiểm trong RUNBOOK vẫn còn, chỉ là phải tường
minh bằng `FAS_ALLOW_INLINE_WORKER_IN_REAL_ENV=true`.

### Lỗi phát hiện trong lượt này

| Lỗi | Sửa | Test |
|---|---|---|
| **Worker sập khi log tiếng Việt** trên console cp1252 của Windows — `UnicodeEncodeError`. Chính thông báo "FAS_ENV không khớp" làm tiến trình sập trước khi kịp in lý do | Ép UTF-8 cho stdout/stderr lúc import, `errors="replace"` | 3 test |
| Rào chắn mới đặt **trước** kiểm CORS nên che mất lỗi wildcard mà test cũ đang kiểm | Chuyển xuống cuối `validate()` — kiểm cấu hình thiếu/sai trước, kiểm hình dạng triển khai sau | test cũ xanh trở lại |

### Đã kiểm

| Hạng mục | Kết quả |
|---|---|
| `render.free.yaml` | YAML hợp lệ, 2 service, cả hai `plan: free`, **không** `type: worker`, không secret viết sẵn |
| `render.yaml` (trả phí) | **không sửa** — test khoá lại: vẫn 3 service, vẫn có `worker` |
| Rào chắn `--require-env` | thoát mã 2 khi lệch; 5/7 test hỏng trên bản chưa có rào chắn |
| Rào chắn `validate()` | 2/6 test hỏng trên bản chưa có rào chắn |
| `staging_smoke.py` với bước đánh thức | **44/44 đạt** trên stack cục bộ dựng đúng hình dạng Free |
| Dữ liệu | đối chiếu 6 tập hợp trước/sau: **mất 0, sót 0** |

### Vẫn còn chặn

Credential staging vẫn **chưa có trên máy này** (`server/.env` sửa lần cuối
2026-08-06, vẫn trỏ dev). Cần `server/.env.staging` — mục 12 — thì mới chạy được
migration và smoke test trên staging thật.

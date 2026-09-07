# Di trú TTS sang Cloud Run — ĐÓNG, FUNCTIONALLY COMPLETE — 2026-09-07

## 1. Đường production đã chứng minh đầu-cuối

```
POST /api/jobs (Render, commit 69afefce6769)   -> 201
tts_dispatch.enqueue()                          -> task tts-job_f7af21975b3947db
Cloud Tasks (queue tts-jobs, RUNNING)           -> dispatch
Cloud Run tts-task-service                      -> POST tu Google-Cloud-Tasks, HTTP 200 (08:59:48Z)
fanfic-prod                                     -> object 85.678 B
Appwrite                                        -> completed, attempts=1, 1/1 doan
                                                -> 1 audio_track, dung 1 mp3, lease da nha
```

Trạng thái chốt: queue `RUNNING` · Cloud Run `{"ok":true,"enabled":true}` · Render live
`69afefce6769` · AWS `fanfic-worker-prod` **vẫn active+enabled** (cố ý, xem mục 4).

## 2. Fencing chặn xử lý trùng trong lúc hai worker cùng chạy

`claim_job` là **compare-and-set thật** trong một transaction Appwrite: hàng
`job_claims` có `rowId` tất định `{job_id}-{attempt}` nằm cùng transaction với
bản cập nhật job, nên hai worker cùng giành thì **đúng một** commit được.

Bằng chứng đo được, không phải suy luận:

| Quan sát | Kết quả |
|---|---|
| Cloud Run gặp job AWS đang giữ lease | trả **`409 thua claim, worker khac nhan`** — từ chối làm trùng |
| Mọi job canary (7 job, cả qua API lẫn trực tiếp) | `attempts=1`, **đúng 1 mp3 + 1 `audio_track`** mỗi chương |
| Đối soát toàn hệ sau cùng | **0 lease treo**, **0 chương có >1 job hoạt động** |

Nên **hai worker cùng chạy là an toàn**. Không cần dừng gì để chốt kết quả.

## 3. TTS: FUNCTIONALLY COMPLETE

Cloud Run có thể nhận và hoàn tất job production qua Cloud Tasks, ghi đúng
`fanfic-prod`, và không xử lý trùng với AWS. Ngoài ra, các cổng nghiệm thu trên
database cách ly trước đó đã đạt: 10/10 job, R2 bền vững, ép kill giữa chừng +
hồi phục lease (`attempts` 1→2), 0 trùng lặp, tương đương đầu ra.

## 4. VIỆC TIẾP THEO (hẹp) — tách hai vòng lặp khỏi worker TTS

`server/worker.py` chạy **ba** việc trong một vòng:

```
worker.py:221  recover_stale_jobs()      <- TTS
worker.py:239  drive_chapter_imports()   <- điều phối nhập chương hàng loạt
worker.py:255  drain_archive_queue()     <- retry Drive archive
```

`grep` hai cái sau trong `server/tts_task_service.py` = **0**. Cloud Run chỉ gọi
`_run_job`. **Đó là lý do worker AWS chưa bị dừng**: dừng nó sẽ làm ngưng nhập
chương hàng loạt và retry Drive, im lặng, không ai thay thế.

Trước khi có thể nghỉ hưu máy AWS, cần tách/di trú hai vòng đó — ví dụ một
tiến trình riêng hoặc Cloud Run Job theo lịch. Comment trong `worker.py` giải
thích vì sao chúng ở đó: đây là **ngữ cảnh sống lâu duy nhất sống qua restart
backend**, và một lô 500 chương cần điều đó.

## 5. TTS trên AWS giờ là DI SẢN

`recover_stale_jobs()` trên AWS vẫn hoạt động và vẫn giành phần lớn job (nó
quét mỗi 3 giây, nhanh hơn ~3,8 giây tạo job + dispatch). Điều đó **đúng và an
toàn** trong giai đoạn cùng chạy, nhưng kể từ nay nó là **di sản**:

- Đường chính thức là Render → Cloud Tasks → Cloud Run.
- Vòng TTS trên AWS **nên được tắt riêng**, độc lập với mục 4, khi hai vòng kia
  đã có nhà mới. Tắt được bằng cách bỏ `recover_stale_jobs()` khỏi vòng lặp
  hoặc bằng một cờ môi trường — **không** bằng cách dừng cả `worker.py`.

## 6. Hạ tầng đã dựng trong đợt này

| Thành phần | Ghi chú |
|---|---|
| Cloud Run service `tts-task-service` | ảnh `v3` (piper-tts 1.7.0, khớp production), scale-to-zero, `concurrency=1`, chỉ IAM mới gọi được |
| Cloud Tasks queue `tts-jobs` | `min-backoff=120s` (> lease 90s), `max-attempts=5` (> `JOB_MAX_ATTEMPTS=3`) |
| SA `tts-tasks-invoker` | `run.invoker` **chỉ** trên service đó |
| SA `fas-prod-enqueuer` | `cloudtasks.enqueuer` **chỉ** trên queue; `iam.serviceAccountUser` **chỉ** trên invoker; **không** binding cấp project |
| Chốt fail-closed | `Settings.validate()` từ chối `fanfic_world_prod` đi với bucket khác `fanfic-prod`, kiểm **mỗi request** |

## 7. Residue đã dọn

Novel `[CANARY] nov_2f360524d5c44f46` cùng 4 chương, 4 job, 8 object R2 — **đã
xoá**. Đối soát lại: 0 chương còn lại, 0 lease treo, 0 chương có >1 job.

**Chưa dọn (ngoài phạm vi, đã ghi ở báo cáo riêng):** 20 object mồ côi trong
`fanfic-prod` từ sự cố 2026-09-06 — xem
`cloudrun-gate-orphan-objects-2026-09-06.md`.

# Cổng 3–6 cho worker TTS trên Cloud Run — 2026-09-06

**Kết quả: cổng 3, 4, 5 ĐẠT. Cổng 6 đạt ở mức đo được là có nghĩa** (xem mục 6:
mô hình Piper là VITS ngẫu nhiên, nên "bằng nhau từng byte" không phải một tính
chất tồn tại).

Chạy trên một database Appwrite **tạm thời, tách biệt hoàn toàn**:
`gate_tts_tmp_20260906` (đã xoá sau khi xong). Bucket `fanfic-staging`.
`fanfic_world_prod` và worker AWS production không bị chạm.

## 0. Cách ly

| Lớp | Bằng chứng |
|---|---|
| Worker AWS chỉ đọc `fanfic_world_prod` | job thử nằm ở database khác → không thể bị giành |
| `fanfic-worker.service` (staging, cùng máy AWS) | `inactive` suốt phiên |
| Bucket | chỉ `fanfic-staging`; `fanfic-prod` không nhận thêm object nào |
| Khoá cấp phát | khoá tạm 8 scope, chỉ schema; không có `documents.*`/`users.*` |

Cấp phát: 7 collection (`profiles`, `novels`, `chapters`, `tts_jobs`,
`audio_tracks`, `job_claims`, `job_locks`) = **101 thuộc tính + 17 chỉ mục**,
tất cả `available` trước khi tạo job. Dùng `scripts/setup_appwrite.py --only`
nên schema y hệt production, không có bản lược bỏ.

## 1. Lỗi chặn tìm được: ảnh v1 thiếu runtime Piper

Lần chạy đầu, cả 10 job `failed` ngay với `provider_not_installed`:

```
Phần 1/3: Chưa cài gói piper-tts nên không dùng được giọng Piper local
```

Nguyên nhân: ảnh `tts-worker:v1` được dựng bằng `server/requirements.txt`, nơi
`piper-tts` **bị comment** (dòng 51 — cố ý, vì tiến trình web không cần). Worker
thì bắt buộc phải có: `server/requirements-worker.txt` ghim nó và nói rõ điều
đó. Ảnh dựng nhầm tệp requirements.

| Hạng mục | Trước khi sửa (v1) | Sau khi sửa (v3) |
|---|---|---|
| Nguồn requirements của ảnh | `server/requirements.txt` | + `piper-tts` cài tường minh |
| `import piper` trong ảnh | thất bại | OK (kiểm ngay lúc `docker build`) |
| Kết quả 10 job | 10/10 `failed` | 10/10 `completed` |
| Phiên bản piper-tts | không có | 1.7.0 (khớp production) |

## 2. Cổng 3 — pending → running → R2 → completed

**ĐẠT.** 10/10 job `completed`, mỗi job `3/3` phần (nên có đi qua đường ghép
`ffmpeg`, không phải chương một đoạn), mỗi job có object R2 thật:

```
completed=10/10   co_object=10/10   co_track=10/10   job_running_toan_he=0
kich thuoc: 517.737 – 526.882 B    thoi luong: 62,3 – 63,6 giay
```

Mỗi chương đúng **1 file `.mp3` + 1 `.transcript.json`**, `audio_track` trỏ đúng
`output_key`.

## 3. Cổng 4 — kill giữa chừng + hồi phục lease

Ép Cloud Run giết task bằng `--task-timeout=55s` khi 10 job đang tổng hợp —
**hạ tầng giết, không phải worker tự nguyện thoát**. Task chết lúc `05:46:19Z`.

Ảnh chụp ngay sau đó (`05:47:29Z`):

```
 # status     att lease_owner       lease con  parts
 1-6 completed  1 -                         - 3/3     <- kip xong truoc khi chet
 7 running      1 1-287d89e2              -5s 0/3     <- ket lai, lease DA HET HAN
 8 running      1 1-287d89e2              -5s 0/3
 9 running      1 1-287d89e2              -4s 0/3
10 running      1 1-287d89e2              -4s 0/3
lease con SONG: 0
```

Chạy một execution mới. `recover_stale_jobs` nhận lại đúng 4 job đó với
`attempts` **1 → 2** (fencing token tăng), tổng hợp lại và hoàn tất:

```
 7 completed    2 -   3/3      9 completed    2 -   3/3
 8 completed    2 -   3/3     10 completed    2 -   3/3
 1-6 completed  1 -   3/3     <- KHONG bi chay lai
tong: {'completed': 10}   lease con SONG: 0
```

**ĐẠT.** Đúng đường đã thiết kế: lease hết hạn → worker khác nhận với fence
mới → chạy lại → xong. Job đã xong không bị đụng tới.

## 4. Cổng 5 — 0 lease treo, 0 trùng lặp

**ĐẠT**, và đạt *sau khi* đã có 4 lần chạy lại:

- `job_running_toan_he = 0`, `lease con SONG = 0`
- mỗi chương **đúng 1 file `.mp3`** — dù 4 job chạy hai lần. Khoá object là tất
  định theo `content_hash`, nên lần chạy lại **ghi đè** chứ không sinh bản thứ hai
- mỗi chương đúng 1 `tts_job` và đúng 1 `audio_track`

## 5. Cổng 6 — tương đương đầu ra với AWS

### Phát hiện quan trọng: không thể so sánh bằng băm

Hai lần tổng hợp **cùng văn bản, cùng model, cùng ảnh container** cho ra file
khác nhau từng byte:

```
so sanh sha256 waveA vs waveC:  trung khop 0/10
```

Đo lại bằng thời lượng và dạng sóng:

```
lech thoi luong lon nhat: 0,87%      RMS cua hieu: ~140%
```

RMS hiệu ≈ 141% chính là con số của **hai tín hiệu không tương quan** cùng công
suất. Piper thuộc họ VITS: bộ dự đoán thời lượng và dòng chảy đều lấy mẫu ngẫu
nhiên. Nên "đầu ra giống hệt" **không phải một tính chất tồn tại** — kể cả AWS
so với chính AWS. Ai kiểm tương đương bằng `sha256` sẽ nhận một kết quả *trượt
giả*.

### Tương đương thật sự đo được

| Hạng mục | AWS production | Cloud Run v3 | Kết quả |
|---|---|---|---|
| `ngochuyennew.onnx` sha256 | `88bc2147…255e2` | `88bc2147…255e2` | **trùng khớp tuyệt đối** |
| `piper_version` trong config | `1.3.0` | `1.3.0` | trùng |
| `hop_length` | 256 | 256 | trùng |
| runtime `piper-tts` | **1.7.0** | 1.6.0 → **đã nâng lên 1.7.0 (v3)** | đã khớp |
| Lệch thời lượng v3 vs v2 | — | **0,62%** | nhỏ hơn nhiễu tự thân 0,87% |

Trọng số giọng giống hệt nhau tới từng byte. Sau khi khớp runtime, chênh lệch
giữa hai bản **nhỏ hơn chênh lệch giữa hai lần chạy của cùng một bản** — đó là
mức tương đương mạnh nhất mà một mô hình ngẫu nhiên cho phép khẳng định.

**Chưa làm được:** so sánh trực tiếp byte/dạng sóng với đầu ra thật của AWS.
Đầu ra đó nằm trong `fanfic-prod`, mà khoá R2 của phiên này chỉ có phạm vi
`fanfic-staging` — cố ý. Với mô hình ngẫu nhiên thì phép so sánh đó cũng không
kết luận được gì thêm.

## 6. Ba cái bẫy im lặng phát hiện dọc đường

1. **`voice_runnable_on_this_machine` trả `True` khi gói Piper CHƯA cài.**
   `voice_by_id` trả `None` (không dựng được provider) → hàm rơi vào nhánh
   "không có trong registry thì cứ nhận". Worker **nhận việc nó không làm nổi**
   rồi đốt sạch lượt thử. Đó là lý do 10 job chết ở lần chạy đầu thay vì được
   nhường lại.

2. **Đặt lại `attempts` mà không xoá `job_claims` làm worker câm lặng.**
   `claim_job` tạo hàng khoá id tất định `{job_id}-{attempts+1}`. Đặt `attempts`
   về 0 khi hàng `-1` còn đó → transaction hỏng → `claim_job` trả `None` → vòng
   quét đếm vào `khong_nhan_duoc` và **không ghi log nào**. Worker sống, hàng đợi
   đầy, không gì nhúc nhích. Mất một vòng chẩn đoán mới tìm ra.

3. **`recover_stale_jobs` chỉ ghi log khi có việc.** Mọi nhánh bỏ qua
   (`bo_qua_thieu_model`, `khong_nhan_duoc`, `bo_qua_con_lease`) đều im lặng
   tuyệt đối. Một worker khoẻ mạnh và một worker không bao giờ nhận được job
   nhìn **giống hệt nhau** trong log. Đây là thứ đáng sửa trước khi dựng kiến
   trúc trigger mới.

## 7. Ghim `piper-tts` trong kho đã lệch thực tế

`server/requirements-worker.txt` ghim `piper-tts==1.6.0` kèm ghi chú rất mạnh về
việc các bản Piper không tương thích chữ ký API. Nhưng production **đang chạy
1.7.0**. Một trong hai phải sai. Đo được ngày 2026-09-06 trên
`13.212.224.218`; ảnh gate đã dựng theo production (1.7.0) vì cổng tương đương
đòi cùng runtime. Cần đối chiếu lại, đây không phải việc đoán.

## 8. Đã dọn

| Hạng mục | Trạng thái |
|---|---|
| 20 object R2 test trong `fanfic-staging` | đã xoá; bucket về đúng 7 object như trước |
| 4 tài khoản `crgate-*@fanfic.invalid` | đã xoá (HTTP 204 cả bốn) |
| Database `gate_tts_tmp_20260906` | đã xoá (HTTP 204); project về đúng 1 database |
| Bằng chứng | GIỮ: 30 tệp audio + `manifest_gate.trace.jsonl` (98 mẫu trạng thái) |
| 20 object mồ côi trong `fanfic-prod` | **chưa đụng**, đúng yêu cầu |

## 9. Còn lại — cần thao tác của người vận hành

Ba thứ nằm ngoài quyền của phiên làm việc:

```
gcloud run jobs delete tts-worker-diag --region=asia-southeast1 --quiet
gcloud secrets delete appwrite-gate-provisioner --project=gen-lang-client-0793420657 --quiet
```

và **xoá khoá API tạm trong Appwrite Console** (khoá đó chỉ có scope schema, nên
nó không tự xoá được chính mình).

## 10. CẢNH BÁO trước khi chạy lại job `tts-worker`

Job Cloud Run `tts-worker` hiện dùng ảnh **v3 (chạy được thật)** nhưng biến môi
trường vẫn là cấu hình lệch cũ: `APPWRITE_DATABASE_ID=fanfic_world_prod` +
`R2_BUCKET=fanfic-staging`.

Trước đây điều đó tương đối vô hại vì worker hỏng ngay khi tổng hợp. **Nay thì
không.** Một lần chạy vô ý sẽ giành job production thật, tổng hợp thành công, và
ghi audio vào bucket **staging** — để lại `audio_track` trỏ vào object mà đường
đọc production không phân giải được, tức trình phát hỏng câm lặng cho người dùng
thật. Cả hai execution đã cancel.

**Sửa toạ độ trước khi chạy lại.** Xem `scripts/ops/cutover_target.py` —
`PROD_R2_BUCKET = "fanfic-prod"`.

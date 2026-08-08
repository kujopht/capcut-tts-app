# Năng lực worker TTS trên GCE — phân tích từ mã nguồn

Phân tích **đọc mã**, không tạo job production nào. Số liệu tốc độ lấy từ
`scripts/benchmark_piper.py` chạy độc lập với hàng đợi.

VM production: `fanfic-worker-prod`, `asia-southeast1-b`, `e2-standard-2`
(2 vCPU / 8 GB), Ubuntu 24.04 Minimal.

---

## 1. Điều quan trọng nhất: một worker xử lý **một job Piper tại một thời điểm**

Không phải vì thiếu luồng, mà vì có khoá tường minh.

| Tầng | Cơ chế | Hệ quả |
|---|---|---|
| Vòng quét | `recover_stale_jobs()` mở **một thread mỗi job** — không có trần | Nhiều job có thể *bắt đầu* cùng lúc |
| Tổng hợp | `tts_bridge._PIPER_LOCK`, khoá ở **cấp job** | Chỉ **một** job Piper thực sự chạy; số còn lại xếp hàng |
| Trong tiến trình | `_start_job_thread` từ chối job đã có thread sống | Không bao giờ hai thread cùng một job |

Khoá đặt ở cấp job chứ không phải cấp đoạn: xen kẽ các đoạn của hai chương
không làm cả hai nhanh hơn, chỉ làm cả hai về đích muộn hơn.

**Hệ quả về năng lực: throughput của một VM = throughput của một luồng Piper.**
Thêm vCPU không tự tăng thông lượng chừng nào khoá còn ở đó.

---

## 2. Số liệu tốc độ

RTF = giây tính toán / giây audio. Nhỏ hơn 1 là nhanh hơn thời gian thực.

| Nguồn | Máy | RTF |
|---|---|---|
| Bạn đo, toàn bộ 25 model | `e2-standard-2` | **0,42 – 0,65** |
| `benchmark_piper.py`, `ngochuyen`, concurrency 1 | laptop Windows | 0,047 |
| `benchmark_piper.py`, `ngochuyen`, concurrency 2 | laptop Windows | 0,070 |

> ⚠️ **Chênh lệch ~10 lần giữa hai phép đo, chưa giải thích được.** Đừng lấy số
> của laptop mà lập kế hoạch cho VM. Khả năng: `e2-standard-2` là vCPU chia sẻ
> và bị hạn mức, đo trên VM gồm cả thời gian nạp model, hoặc hai bên dùng độ
> dài văn bản khác nhau. **Việc cần làm trước khi tin bất kỳ con số nào dưới
> đây: chạy `scripts/benchmark_piper.py` trên chính VM** — nó in đủ RTF trung
> vị, min, max và RAM đỉnh.
>
> Mọi ước tính bên dưới dùng **RTF 0,65** (đầu xấu của khoảng bạn đo), vì lập
> kế hoạch theo trường hợp xấu thì sai lệch nghiêng về phía an toàn.

## 3. Một worker

Với RTF 0,65, **một** phút audio tốn ~39 giây CPU.

| Độ dài chương | Audio ước tính | Thời gian tổng hợp |
|---|---|---|
| 2.000 ký tự (1 đoạn) | ~3,3 phút | ~2,1 phút |
| 20.000 ký tự | ~33 phút | ~21 phút |
| 60.000 ký tự (32 đoạn) | ~100 phút | ~65 phút |
| 100.000 ký tự (trần) | ~166 phút | ~108 phút |

Cộng thêm, mỗi job:

* **nạp model ~2–3 giây**, nhưng CHỈ lần đầu cho mỗi giọng — `PiperVoice` được
  cache theo đường dẫn `.onnx` trong `PiperLocalProvider._loaded`, và registry
  là biến toàn cục của tiến trình. Đổi giọng liên tục giữa 25 model thì trả giá
  nạp nhiều lần và tốn RAM.
* **ghép ffmpeg** cho chương nhiều hơn một đoạn (`-c copy`, gần như tức thì).
* **tải lên R2** phụ thuộc mạng.

### Hàng đợi dài ra thế nào

Một worker là hàng đợi FIFO một chỗ phục vụ. Nếu tốc độ đến là λ job/giờ và mỗi
job mất trung bình S giờ, hàng đợi **chỉ ổn định khi λ × S < 1**. Vượt qua là
thời gian chờ tăng **không giới hạn**, không phải tăng tuyến tính.

Với chương 20.000 ký tự (S ≈ 0,35 giờ): trần lý thuyết ≈ **2,8 job/giờ**. Thực
tế nên chạy dưới 70% trần, tức **≈ 2 job/giờ**, để một job dài không đẩy hàng
đợi vỡ.

`FAS_MAX_ACTIVE_JOBS=3` giới hạn **mỗi người dùng**, không giới hạn tổng — mười
người cùng xếp ba job là ba mươi job cho một worker.

## 4. Hai worker

Claim là compare-and-set **thật**, nên chạy nhiều worker là an toàn.

### Đánh giá claim nguyên tử

`store.claim_job()` gói **hai** thao tác vào MỘT transaction Appwrite:

1. `create` hàng `job_claims` với `rowId = "{job_id}-{attempt}"` — id **tất định**;
2. `update` job row sang `running` kèm lease.

Tính duy nhất của `rowId` được cưỡng chế **bên trong** transaction, nên hai
worker cùng nhắm một `attempt` thì kẻ thua hỏng ở bước 1 và **bước 2 cũng không
xảy ra**. Kẻ thua nhận `None` rồi **dừng hẳn** — không gọi TTS, không thử lại mù.

Đã đo trực tiếp trên Appwrite: 10 worker đồng thời → **đúng một** thắng.

Thêm hai lớp nữa khiến việc chạy lại là **vô hại** kể cả khi claim hỏng:

* `output_key` tất định theo `content_hash` — hai lượt chạy ghi cùng một khoá;
* `create_track` là **tìm-hoặc-tạo** theo `(chapter_id, content_hash)`.

**Kết luận: hai worker KHÔNG xử lý cùng một job.** Và nếu có, kết quả vẫn là
một track, một object.

### Đánh giá recovery khi lease chết

| Hằng số | Giá trị |
|---|---|
| `JOB_LEASE_SECONDS` | 90 |
| `JOB_HEARTBEAT_SECONDS` | 30 |
| `JOB_MAX_ATTEMPTS` | 3 |
| `POLL_SECONDS` (worker) | 3 |
| `GRACE_SECONDS` | 120 |

Worker đang chạy tự gia hạn lease mỗi 30 giây qua `renew_lease()` — **chỉ ghi
hai trường lease**, không đập đè cả hàng. Lease chịu được **hai** nhịp trượt
liên tiếp; `server/main.py` cưỡng chế `lease ≥ 3 × nhịp` ngay lúc nạp module.

`claim_job` từ chối **mọi** lần nhận khi lease còn sống — **kể cả chính chủ**.
Đó là bản vá cho lỗi một job bị tổng hợp hai lần; xem `test_lease_hardening.py`.

### VM chết giữa lúc tổng hợp

1. Nhịp ngừng. Lease hết hạn sau **≤ 90 giây**.
2. Bộ quét của worker còn sống thấy job `running` không còn lease → claim với
   `attempt+1`.
3. Chạy lại **từ đầu chương** — không có điểm nối lại giữa chừng.
4. Quá `JOB_MAX_ATTEMPTS=3` → `failed` với `error_kind=worker_lost` kèm thông
   báo người dùng đọc hiểu được.

Vậy **thời gian mất tối đa khi VM chết = 90 giây + toàn bộ thời gian đã tổng
hợp của lần đó.** Với chương 100.000 ký tự, mất tới ~108 phút công. Đó là lý do
mạnh nhất để chia nhỏ chương, hoặc để làm điểm nối lại sau này.

### Mở rộng ngang

| Số worker | Thông lượng kỳ vọng |
|---|---|
| 1 | 1× |
| 2 | ~1,9× |

Không phải đúng 2× vì: cả hai cùng poll Appwrite mỗi 3 giây (thêm tải đọc);
`recover_stale_jobs` của hai bên có thể cùng nhắm một job và một bên thua claim
(vô hại nhưng lãng phí một vòng); và nếu chung một VM thì chúng tranh CPU.

**Cảnh báo:** hai worker trên **cùng một máy** BẮT BUỘC khác `FAS_VAR_DIR` —
tệp nhịp lấy từ `var_dir`, dùng chung là chúng ghi đè nhịp của nhau và `--check`
của cả hai cùng vô nghĩa. `deploy/fanfic-worker-prod.service` dùng
`/var/lib/fanfic-audio-prod`, khác staging; có test khoá lại.

## 5. Chỉ số nên dùng nếu sau này làm autoscale

**Chưa triển khai autoscaling.** Ba chỉ số dưới đây đọc được ngay mà không cần
thêm hạ tầng nào:

| Chỉ số | Lấy ở đâu | Vì sao |
|---|---|---|
| **Số job `pending`** | `list_jobs_by_status(PENDING)` | Tín hiệu trực tiếp nhất về tồn đọng |
| **Tuổi job `pending` cũ nhất** | `created_at` của job cũ nhất | Phân biệt "nhiều job ngắn" với "một job kẹt" — cùng một con số đếm nhưng hai vấn đề khác hẳn |
| **Tuổi nhịp worker** | `$FAS_VAR_DIR/worker/heartbeat.json` | Phân biệt "quá tải" với "**không có worker nào**". Thiếu chỉ số này thì autoscale sẽ thêm máy trong khi vấn đề là worker đã chết |

Ngưỡng đề xuất để bắt đầu: scale lên khi *tuổi job pending cũ nhất* > 10 phút
**và** nhịp worker còn mới. Scale xuống khi pending = 0 trong 15 phút.

Đừng scale chỉ theo số lượng job: một chương 100.000 ký tự và một chương 500 ký
tự đều đếm là 1.

---

## 6. Rủi ro cần quyết định trước khi công bố 25 giọng

**Tên model trông như tên người thật.** Một số khoá trong catalog —
`mytam2`, `mytam2794`, `tranthanh3870`, `thanhphuong2` — trùng dạng với tên
người nổi tiếng ở Việt Nam. Mã nguồn hiện **giữ nguyên tên kỹ thuật** làm tên
hiển thị và **không gán giới tính**, đúng vì hai lý do:

* không có nguồn nào để đối chiếu tên đúng;
* gán một tên người thật cho giọng tổng hợp là chuyện **định danh**, không phải
  chuyện thẩm mỹ — và nó tự trả lời câu hỏi giọng đó nhân bản từ ai.

Trước khi bật các giọng này cho người dùng, cần trả lời: các model này huấn
luyện từ nguồn nào, và có quyền công bố dưới tên nào. Hiện `FAS_LOCAL_VOICES`
mặc định chỉ bật `piper:ngochuyen`, nên 24 giọng còn lại **có trong catalog
nhưng không được phục vụ** — muốn bật là một quyết định tường minh.

## 7. RAM

`benchmark_piper.py` đo RSS đỉnh: **233 MB** (một model) và **356 MB**
(concurrency 2) trên laptop. Một model Piper chiếm ~120 MB sau khi nạp.

Cache của `PiperLocalProvider._loaded` **không có trần** — nạp cả 25 model trong
một tiến trình sẽ giữ ~3 GB. Trên VM 8 GB thì còn chỗ, nhưng đó là giới hạn
thật cần biết nếu sau này bật nhiều giọng. Chưa có cơ chế loại bỏ model khỏi
cache.

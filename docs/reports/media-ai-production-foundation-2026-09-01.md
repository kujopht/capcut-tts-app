# Nền tảng sản xuất Media AI — báo cáo đêm 2026-09-01

Nhánh làm việc: `beam-gpu-bootstrap`. Không có lệnh GPU thật, không deploy
Beam, không publish nội dung, không đụng dữ liệu Appwrite production, không
chi tiêu credit trả phí nào được thực hiện trong phiên này — toàn bộ công
việc là code + test cục bộ (mock/fake), nghiên cứu tài liệu chính thức, và
chuẩn bị lệnh cho operator chạy tay ngày mai.

## 1. Track A — Vòng tinh chỉnh IP-Adapter cuối cùng (bố cục theo vùng)

### 1.1 Toàn bộ chuỗi lỗi bìa THẬT đã gặp và đã sửa (mission-by-mission)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Endpoint Beam stale | `HttpImageCoverProvider` hardcode `POST /generate`, nhưng Beam `@endpoint` được gọi thẳng vào URL deploy gốc | Thêm `simple_path=""` cấu hình được; Beam dùng path rỗng (gốc URL) |
| Import PIL ở deploy-discovery | `from PIL import Image, ImageDraw` ở đầu file `cover_illustrious_logic.py` khiến `beam deploy` lỗi ngay ở bước discovery (môi trường CLI không có Pillow) | Import PIL chuyển vào TRONG `build_left_right_masks()` — hàm DUY NHẤT cần PIL |
| Endpoint timeout | `@endpoint` mặc định `timeout=180`giây; container lạnh (on_start tải model + IP-Adapter) cộng suy luận GPU thật có thể vượt 180s → task bị Beam huỷ (`Cancelled`) | `timeout=900` (15 phút) — đủ dư cho lần chạy lạnh đầu tiên, không tắt hẳn timeout (`-1`) |
| Sai image encoder IP-Adapter | `load_ip_adapter(subfolder="sdxl_models")` mặc định suy ra `sdxl_models/image_encoder` = OpenCLIP ViT-bigG (hidden_size=1664) — SAI với checkpoint `*_vit-h` cần ViT-H (1280) → `RuntimeError: mat1 and mat2 shapes cannot be multiplied (1028x1664 and 1280x1280)` (bằng chứng that trên Beam) | Nạp tường minh `CLIPVisionModelWithProjection.from_pretrained(..., subfolder="models/image_encoder")` (đúng theo ví dụ chính thức của diffusers cho biến thể `*_vit-h`), truyền vào constructor pipeline; assert `hidden_size==1280` lúc khởi động, thất bại sớm thay vì lỗi giữa chừng suy luận |
| Prompt vượt ngân sách token CLIP | Prompt đầy đủ 2 nhân vật ~980 ký tự → đo THẬT 216 token, vượt giới hạn cứng 77 (log Beam: `Token indices sequence length 216 > maximum 77`) | Chế độ "compact" tự động kích hoạt khi ≥2 nhân vật có `compact_visual_tags` — chỉ giữ tên + tối đa 2 tag nổi bật/nhân vật, bỏ genre/mood/văn xuôi dài. Prompt Re:Zero thực đo còn ~306 ký tự (~67 token ước tính, còn dư so với 77) |
| CPU/CUDA lẫn lộn | Image encoder được nạp tường minh (fix ở trên) nhưng KHÔNG được `.to("cuda")` — trong khi phần còn lại của pipeline (chia sẻ từ `pipe` gốc) đã ở CUDA → `RuntimeError: Expected all tensors to be on the same device, but got index is on cpu, different from other tensors on cuda:0` (bằng chứng that) | `.to("cuda")` cho encoder, cho pipeline IP-Adapter sau khi khởi tạo, và LẶP LẠI sau `load_ip_adapter()` (vì lệnh này cài thêm module projection ảnh mới vào UNet) — đúng mẫu chính thức của diffusers. Thêm assertion khởi động xác nhận encoder/UNet/projection layer đều ở CUDA |
| Reference-conditioning kỹ thuật PASS nhưng bố cục FAIL (v10 thật) | Nhận dạng nhân vật xuất hiện rõ (Subaru áo tracksuit đen/cam, Anastasia tóc tím/phụ kiện lông) nhưng: mặt/đầu nhân vật chính bị cắt xén nặng, nhân vật phụ quay lưng phần lớn, xuất hiện nhân vật ngoài ý muốn, có glyph/artifact giống chữ viết | Mask trái/phải chuyển từ CHỒNG LẤN (band chung ở giữa, `overlap_fraction=0.08`) sang KHÔNG CHỒNG LẤN (vùng chết `gap_fraction=0.04` ở giữa không thuộc về ai); `reference_strength` giảm 0.6→0.5; prompt compact thêm yêu cầu bố cục rõ ràng (waist-up shot, faces fully visible, facing viewer or 3/4 view, Subaru on left, Anastasia on right — khớp CHÍNH XÁC với mask trái/phải); negative prompt bổ sung `third person, cropped face, cut-off head, back facing viewer, rear view, letters, symbols, logo` |

**Cổng quyết định (chưa chạy — chờ operator ngày mai):** nếu 1 lần chạy
GPU thật cuối cùng (seed `20260906`) vẫn cho ~2 người, cả hai mặt nhìn
thấy rõ, nhận ra được Subaru + Anastasia, không lẫn danh tính/nhân bản,
bố cục dùng được → PASS, dừng tinh chỉnh IP-Adapter. Nếu vẫn thất bại →
DỪNG hẳn hướng IP-Adapter, chuyển sang kiến trúc LoRA nhân vật + composition
theo vùng (bigger lift, chưa triển khai đêm nay theo đúng chỉ thị).

### 1.2 Đo lường thật gần nhất (trước vòng sửa bố cục này)

| Chỉ số | Giá trị | Loại |
|---|---|---|
| wall_clock | ≈134.73 s | Đo thật (Beam log) |
| model_load | ≈19.03 s | Đo thật |
| inference | ≈75.05 s | Đo thật |
| approx_cost | ≈$0.0258 | Ước tính (giá RTX4090 công bố × wall_clock) |

### 1.3 Lệnh redeploy + proof DUY NHẤT cho ngày mai (chưa chạy)

```bash
cd ~/capcut-tts-app
git fetch origin beam-gpu-bootstrap && git checkout beam-gpu-bootstrap
git pull --ff-only origin beam-gpu-bootstrap
git log --oneline -1     # phải thấy commit Track A mới nhất (xem báo cáo sáng)

beam deploy beam_apps/cover_illustrious_app.py:generate

BEAM_TOKEN=<token thật> python3 scripts/beam_cover_reference_proof.py \
  --endpoint-url <URL cover-illustrious đã deploy> \
  --primary-reference-image path/to/subaru.png \
  --primary-reference-source "<mô tả nguồn>" \
  --secondary-reference-image path/to/anastasia.png \
  --secondary-reference-source "<mô tả nguồn>"
```

Script tạo ĐÚNG MỘT lệnh GPU thật (seed cố định `20260906`), không có cờ
CLI nào để tăng số lần gọi.

## 2. Track B — Hy-MT2 1.8B production readiness

Kiểm chứng thật qua tài liệu chính thức (không đoán):

| Hạng mục | Kết quả kiểm chứng |
|---|---|
| `trust_remote_code=True` | XÁC NHẬN bắt buộc — `config.json` khai `architectures: ["HunYuanDenseV1ForCausalLM"]`, kiến trúc tuỳ biến của Tencent HunYuan |
| 33 ngôn ngữ | XÁC NHẬN đúng theo model card HuggingFace thật |
| Tương thích vLLM | XÁC NHẬN — chính model card công bố sẵn lệnh `vllm serve` |
| dtype | XÁC NHẬN không cần ép kiểu — `config.json` đã ghi `torch_dtype=bfloat16`, vLLM `dtype="auto"` tự đọc |
| `max_model_len=8192` | XÁC NHẬN là cắt giảm CÓ CHỦ ĐÍCH (model gốc `max_position_embeddings=262144`) — nay đã ghi rõ trong code là chủ ý, không phải thiếu sót |
| GPU tier T4 (1.8B) / A10G (7B) | XÁC NHẬN là giá trị `gpu=` hợp lệ, đang khả dụng thật trên Beam (docs.beam.cloud/v2/environment/gpu) — không cần đổi |
| Cache trọng số + scale-to-zero | XÁC NHẬN Beam `VLLM` tự có Volume `vllm_cache` mặc định + `keep_warm_seconds=60` — KHÔNG cần tự lắp Volume/on_start thủ công như `cover_illustrious_app.py` |
| Giá GPU T4/A10G theo giây | **KHÔNG XÁC NHẬN được** — trang giá chính thức của Beam không công bố rate cho T4/A10G (chỉ có RTX4090 trở lên). Đối chiếu 2 nguồn tổng hợp độc lập không khớp mẫu làm tròn của Beam → báo cáo/benchmark ghi rõ đây là **ước tính bên thứ ba CHƯA XÁC MINH**, không phải giá thật như RTX4090 |
| ~~GPU tier T4 (1.8B)~~ | **ĐÍNH CHÍNH 2026-09-01** — hai dòng phía trên bị chứng minh SAI bởi bằng chứng deploy THẬT: `beam deploy ...:hymt2_1_8b` với `gpu="T4"` THẤT BẠI với lỗi chính thức của Beam "This GPU type is not supported. Please use an A10G or RTX 4090 instead." Chỉ vì tài liệu liệt kê `"T4"` là một giá trị enum không đồng nghĩa scheduler thật sự có capacity T4 cho `beam.integrations.VLLM`. 1.8B đã đổi sang `gpu="RTX4090"` — xem `beam_apps/translation_hymt2_app.py`'s "GPU TIER - CORRECTED BY REAL DEPLOY EVIDENCE". Tác dụng phụ TÍCH CỰC: RTX4090 CÓ rate `$0.000191667/s` công bố chính thức trên beam.cloud/pricing, nên chi phí 1.8B nay là **rate đo đạc thật**, không còn ước tính bên thứ ba như dòng gốc phía trên. A10G (7B) không đổi, vẫn CHƯA có rate công bố. |

Đã thêm `TranslationRunMetrics` trung lập provider (ngôn ngữ nguồn/đích,
model, số ký tự/token vào-ra, thời gian wall/load/inference, hash
nguồn+đích tái dùng `_hash_text` sẵn có, cờ nghi ngờ bị cắt bớt) — có test
AST xác nhận không import beam/torch/diffusers/vllm. Script benchmark viết
lại theo đúng mẫu cold+warm 2 lần gọi của `beam_cover_benchmark.py`, in
đầy đủ văn bản nguồn/dịch, hash sha256, checklist đánh giá thủ công. Model
7B vẫn PHẢI truyền `--model` tường minh, không có giá trị mặc định.

**Lệnh ngày mai (chưa chạy):**

```bash
beam deploy beam_apps/translation_hymt2_app.py:hymt2_1_8b

BEAM_TOKEN=<token thật> python3 scripts/beam_translation_benchmark.py \
    --endpoint-url <beam vllm endpoint url> --model tencent/Hy-MT2-1.8B
```

## 3. Track C — Async GPU job foundation

File mới hoàn toàn (không sửa file nào có sẵn):
`server/gpu_job_domain.py`, `server/gpu_job_service.py`,
`server/gpu_job_storage.py` + test.

Kiến trúc: `Application -> GPUJobService -> GPUJobProviderAdapter
(Protocol) -> Beam hôm nay / provider khác sau này` — domain/service
không import bất kỳ thứ gì đặc thù provider (có test AST xác nhận).

Quyết định kỹ thuật đáng chú ý:
- Lỗi KHÔNG xác định loại mặc định là "permanent" (an toàn — lỗi GPU chưa
  phân loại không nên retry vô hạn tốn tiền thật). `MAX_JOB_ATTEMPTS=3`.
- Huỷ job `QUEUED` tức thì; job `PROVISIONING`/`RUNNING` gọi
  `adapter.cancel()` cố gắng tốt nhất rồi đánh dấu `CANCELLED` cục bộ dù
  adapter có xác nhận hay không — ghi rõ cần một poller thật xác minh lại
  trước khi coi output là an toàn để bỏ.
- `idempotency_key` tường minh ưu tiên hơn suy ra từ `input_hash`; job
  đang chạy/đã xong dùng chung khoá trả về NGUYÊN job cũ (không tạo trùng);
  job đã `FAILED`/`CANCELLED` dùng chung khoá được phép tạo lượt thử mới.

## 4. Track D/E — Image router + telemetry/quality gates

File mới: `server/image_router.py`, `server/gpu_telemetry.py`,
`server/cover_quality_checklist.py` + `docs/cover_quality_checklist.md`.

`ImageRouter.select_provider()`: lọc theo capability + VRAM + còn khả
dụng → ưu tiên compute miễn phí/được trợ giá → rẻ nhất trong số còn lại
→ nếu không ai đạt thì raise `NoCapableProviderError` kiểu rõ ràng. Chính
sách chỉ đọc từ danh sách `candidates` truyền vào lúc gọi — thêm một
`ImageProviderProfile` mới (vd provider "vast" giả định sau này) đổi kết
quả định tuyến mà KHÔNG cần sửa một dòng code nào của `ImageRouter` hay
caller (có test chứng minh trực tiếp điều này). Seed đúng MỘT candidate
thật cho đêm nay: `BEAM_RTX4090_PROFILE` (PROMPT_ONLY +
REFERENCE_CONDITIONED, chưa hỗ trợ CHARACTER_LORA, `is_free_or_subsidized=False`,
dùng lại đúng giá RTX4090 công bố `0.000191667`$/giây đã dùng ở
`beam_cover_benchmark.py`). Không tích hợp Vast.ai thật — chỉ
interface/stub trung lập provider.

`GPUJobTelemetry` (Track E): cấu trúc dữ liệu thuần (thời gian
load/inference/wall/queue-delay, kích thước ảnh hoặc số ký tự dịch, số
byte output, loại GPU, provider, chi phí ước tính, thành/bại, loại lỗi)
— không nối dashboard/SaaS ngoài nào. `CoverQualityEvaluation` (Track E):
schema đánh giá THỦ CÔNG đúng các trường mission yêu cầu (số nhân vật,
nhận diện nhân vật chính/phụ, có lẫn danh tính không, có nhân bản không,
mặt có lộ không, bố cục có ổn không, có artifact chữ không,
production-ready) — con người tự điền sau khi xem ảnh thật, KHÔNG có
giám khảo AI thị giác nào được xây đêm nay.

## 5. Bảo mật

Không cài `gitleaks`/`trufflehog` trong môi trường này. Đã quét thủ công
bằng pattern (API key/secret/password/token dạng gán trực tiếp, khoá AWS
`AKIA...`, khối `PRIVATE KEY`, token `sk-...`) — LẦN 1 trên toàn bộ diff
giữa `beam-gpu-bootstrap` và điểm rẽ nhánh thật với `origin/main`
(`git merge-base`) trước khi bắt đầu đêm nay, LẦN 2 sau khi tích hợp cả
3 track (B/C/D/E) — cả hai lần đều KHÔNG tìm thấy kết quả khớp nào ngoài
tên biến môi trường/placeholder đã biết (`BEAM_TOKEN`, `TOKEN_ENV_VAR`,
`api_key: str = ""`). Đã kiểm tra riêng không có file ảnh
(`.png/.jpg/...`) hay `.env` nào lọt vào diff. `git status` sạch trước
khi bắt đầu và sau khi tích hợp xong (ngoại trừ chính file báo cáo này).

## 6. Tổng kết test + tích hợp

3 worker chạy trong git worktree CÔ LẬP (`isolation: "worktree"`) — phát
hiện quan trọng: worktree được tạo từ `origin/main` cũ (điểm rẽ nhánh
thật trước cả mission Beam này), KHÔNG phải từ nhánh `beam-gpu-bootstrap`
hiện tại — nên số lượng test mỗi worker tự báo cáo (vd "3829/3829",
"3866/3866") phản ánh baseline CŨ của riêng worktree đó, không phải trạng
thái thật của nhánh chính. Track B tự phát hiện việc này và fast-forward
worktree của mình lên `origin/beam-gpu-bootstrap` trước khi audit — 2
track kia (C, D/E) không làm vậy nhưng thay đổi của họ hoàn toàn CỘNG
THÊM (file mới, không sửa file cũ) nên không ảnh hưởng gì. **Mọi số liệu
test trong báo cáo này là số ĐO LẠI trên nhánh chính thật sau khi tích
hợp**, không phải số worker tự báo cáo.

| Bước | Full backend suite (`server/tests`) | `beam_apps/tests` |
|---|---|---|
| Trước đêm nay (sau Track A) | 4081/4081 (1 skip) | 56/56 |
| Sau tích hợp Track D/E | 4109/4109 (1 skip) | — |
| Sau tích hợp Track C | 4174/4174 (1 skip) | — |
| Sau tích hợp Track B | **4195/4195 (1 skip)** | **66/66** |

Tổng: +114 test mới qua 3 track, 0 hồi quy trên toàn bộ 4195 test.

## 7. Nguyên tắc production được giữ nguyên

- Không gọi GPU thật, không deploy Beam, không publish nội dung.
- Không đụng dữ liệu Appwrite production.
- Không tích hợp Vast.ai trả phí (chỉ interface/stub trung lập provider).
- Mọi số liệu chi phí được ghi rõ là **đo thật** hay **ước tính** — không
  bao giờ trộn lẫn hai loại.

## 8. MORNING_MANUAL_ACTIONS

Không có hành động nào bị chặn bởi permission prompt/credential/production
approval đêm nay — toàn bộ phạm vi cả 4 track đều hoàn thành được mà
không cần secret, GPU thật, hay quyết định không thể đảo ngược. Hai việc
DUY NHẤT còn lại cần operator tự tay làm (đã nêu ở mục 1.3 và mục 2, có
lệnh chính xác sẵn sàng):

1. Chạy 1 lần proof bìa GPU thật (bố cục cuối cùng, seed `20260906`).
2. Deploy Hy-MT2 1.8B + chạy 1 lần benchmark dịch GPU thật (cold+warm).

Không có gì khác cần thao tác thủ công.

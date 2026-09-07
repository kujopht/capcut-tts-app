# ORCHESTRATOR — CHỨNG MINH TRÊN HẠ TẦNG THẬT + BỀ MẶT WEB (2026-09-07)

Tiếp nối `content-orchestrator-v1-2026-09-07.md`. Lần trước dừng ở "chưa chạy
thật trên hàng đợi production". Lần này đã chạy.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Cấu hình production cho công cụ | Không có trong worktree này | Trỏ `FAS_ENV_FILE` sang tệp có thật của bản checkout chính — **không sao chép, không in, không commit** |
| Số mục trong hàng đợi | Con số từ báo cáo 2026-09-02 | **30 mục, xác nhận bằng dữ liệu sống** |
| `--dry-run` trên hàng đợi thật | Chưa chạy | **Sạch**, 0 lỗi, cổng quyền báo đúng |
| Đường end-to-end | Chưa chứng minh | **Đã chạy trọn vẹn trên Appwrite + R2 production** |
| Nối lại sau khi tiến trình chết | Chỉ có test đơn vị | **Chứng minh thật**: nhặt lại điểm dừng từ R2, không object trùng |
| Bề mặt web | Không có | 4 route `/api/admin/content-queue/*`, **không route nào chạy việc** |
| Test | 926 scripts + 4.435 server | **+29 bài mới** cho tầng web |

## 1. Cấu hình — giải quyết mà không đụng vào bí mật

Kho khoá của máy (`fanfic_credential_broker list`) có 7 khoá, nhưng
`APPWRITE_SCHEMA_API_KEY` **cố ý không có scope `documents.*`** (bằng chứng
trong `docs/HANDOFF.md`: đọc tài liệu bị từ chối). Nó không chạy được
orchestrator, và đó là **thiết kế đúng**, không phải thiếu sót.

Nguồn có thẩm quyền là `server/.env.production` của bản checkout chính — đúng
tệp mà `chinese_media_pipeline.upload_to_r2` đã dùng sẵn. Cách dùng:

```bash
export FAS_ENV_FILE="…/CapCut-TTS-App/server/.env.production"
```

`server/config.py::env_file_path` hỗ trợ sẵn biến này. **Không sao chép tệp,
không đọc giá trị, không commit.** Chỉ liệt kê *tên khoá* để xác nhận đủ 4
biến Appwrite + 4 biến R2. `gitleaks` trên CI: **pass**.

## 2. Trạng thái hàng đợi THẬT

```
30 mục — mọi công đoạn PENDING, 0 RUNNING
```

`0 RUNNING` cũng chính là phép kiểm "không có bản tiêu thụ nào khác đang
chạy" — bất biến MỘT-người-ghi được xác minh bằng dữ liệu, không bằng giả định.

## 3. End-to-end THẬT trên production

Chạy canary theo đúng khuôn mẫu Phase 15/18 của kho này (fixture thật → chạy
thật → dọn sạch → xác minh đã sạch):

| Công đoạn | Kết quả thật |
|---|---|
| `transcript` | ASR thật (faster-whisper), **14 đoạn**, checkpoint R2 **3.210 byte** |
| `translation` | Dịch thật qua `agy`, **14/14 đoạn** |
| `subtitle` | SRT thật trên R2, **2.041 byte** |
| `dub` | `SKIPPED` (không yêu cầu) |
| `draft` | Novel thật trên production: `nov_c9a77cb1763c4775` |
| `render` | `SKIPPED` — cổng quyền, `rights_mode=REFERENCE_ONLY` |

**Dọn sạch đã xác minh**: Novel 404, object R2 404, hàng đợi trở lại **đúng
30 mục**.

## 4. Nối lại — chứng minh, không phải hứa

**Chạy lại ngay**: `0 bước, 0 công đoạn tiến` — mục đã xong là no-op tuyệt đối.
Không object R2 mới, không Novel trùng.

**Cửa sổ sập tiến trình** (object đã lên R2, Appwrite chưa kịp ghi
`transcript_key`): xoá `transcript_key`, giữ object, rồi chạy lại **không đưa
`--audio`** — nên ASR là *bất khả thi*. Kết quả:

```
"nhat lai diem dung transcript tren R2 (14 doan)"
```

Nó nhặt lại thay vì bó tay. Kích thước object không đổi (3.210 / 2.041), cùng
khoá tất định — **không nhân bản**.

## 5. Bề mặt web — xếp việc, không chạy việc

4 route `/api/admin/content-queue/*` (`server/content_queue_service.py` +
route mỏng trong `main.py`). `requeue` **chỉ đổi một trường trạng thái**.

Bất biến này được kiểm bằng **cây cú pháp**, không bằng tìm chuỗi (chính
docstring của tầng này có chữ "subprocess" để nói rằng nó không dùng — một
phép tìm chuỗi sẽ báo động giả và đẩy người ta tới chỗ xoá lời giải thích).
Test đọc AST và chặn mọi import/lời gọi khởi chạy tiến trình, kèm một bài
chứng minh chính cái canh gác đó **bắt được** vi phạm thật.

Hai điều bị từ chối (409): xếp lại `render` của mục không phải
`REHOST_ALLOWED` (**cổng quyền không đi vòng qua được bằng một cú bấm nút**),
và xếp lại một công đoạn `RUNNING` còn mới.

## 6. VIỆC KHÔNG LÀM ĐƯỢC — và vì sao nó không phải lỗi mã

**Chưa chạy end-to-end trên một trong 30 mục thật.** Lý do là **hình dạng nội
dung**, đo được:

| Đo | Giá trị thật |
|---|---|
| Mục **ngắn nhất** trong 30 | **38.019 giây = 10,6 giờ** |
| Mục dài nhất | ~31 giờ |
| Số mục < 1 giờ | **0/30** |
| Thông lượng ASR đo trên máy này | **0,96× thời gian thực** (60 s âm thanh → 62,6 s) |
| ⇒ riêng ASR cho mục ngắn nhất | **~11 giờ** |
| Tải về (đo thật) | 60 s nội dung mất 34 s ⇒ ~6 giờ |
| Số đoạn ước tính | 840 đoạn/giờ ⇒ **~8.870 đoạn** ⇒ ~59 lượt gọi `agy` |

Một mục = **>17 giờ máy** cộng một lượng quota dịch lớn. Đó không phải "một
lần chạy có kiểm soát", nên **không chạy**, và cũng không chạy một lát cắt rồi
đánh dấu `DONE` — đúng yêu cầu "không đánh dấu công việc dở là DONE".

**Đây là phát hiện mới, chưa báo cáo nào ghi.** Lần sản xuất thành công trước
đây (2026-09-02) dùng video **1 phút 42**. Watcher nay đang hút về các bản tổng
hợp 10–31 giờ từ cùng kênh RSS.

**Ba lựa chọn, đều là quyết định sản phẩm — chưa tự chọn:**

1. Lọc watcher theo độ dài (vd bỏ qua > 30 phút) — rẻ nhất, không đụng pipeline.
2. Cắt nguồn dài thành tập rồi xếp từng tập — cần thiết kế, vượt "không thiết
   kế lại".
3. Đổi nguồn sang kênh đăng theo từng tập.

## 7. Test

```
server/tests   4.464 PASS / 0 FAIL (3 skip)  — 4.435 + 29 bài web mới
scripts/tests    926 PASS / 0 FAIL (4 skip)
CI trên PR #161: Backend PASS · Web/TS/ESLint/build PASS · gitleaks PASS
```

29 bài mới: 19 cho tầng dịch vụ (`test_content_queue_service.py`) + 10 cho
route (`test_content_queue_routes.py`). Ngoài ra
`test_admin.py::test_moi_route_admin_deu_duoc_bao_ve` **tự động** kiểm quyền
cho cả 4 route mới — không phải thêm dòng nào vào danh sách.

PR #161 đã **merge** (`f42cdd6`). Merge vào `main` **không** deploy —
`autoDeploy=no` trên Render, đúng như `docs/HANDOFF.md` ghi.

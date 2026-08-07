# Báo cáo E2E đầy đủ — Fanfic Audio Studio Web

Lượt kiểm thử end-to-end cuối trước khi chuẩn bị push/deploy.
Xuất phát từ commit `7a116fc`, branch `feature/web-mvp`.

Báo cáo này đã khử dữ liệu nhạy cảm: không có token, cookie, JWT, API key,
access key, presigned URL hay mật khẩu thật nào. Mật khẩu duy nhất xuất hiện là
mật khẩu của **tài khoản test dùng một lần đã bị xoá**.

---

## 1. Môi trường và lệnh tái tạo

| Hạng mục | Giá trị |
|---|---|
| Backend | FastAPI trên `uvicorn`, cổng 8000, **không** `--reload` |
| Frontend | Next.js **production build** (`next build` + `next start`), cổng 3000 |
| Kho metadata | Appwrite Cloud **1.9.6**, database kiểu `tablesdb` |
| Kho file | Cloudflare R2 |
| TTS | Edge TTS (`edge:vi-VN-HoaiMyNeural`, `edge:vi-VN-NamMinhNeural`) |
| Trình duyệt | Chromium điều khiển qua Playwright (MCP) — **trình duyệt thật** |
| Viewport | Desktop 1440×900 · Mobile 390×844 |
| Python | 3.12.10 |

**Cô lập.** Dự án chỉ có **một** Appwrite project (bản dev, chưa thương mại) — không
có project/bucket test riêng. Cô lập vì vậy nằm ở **tầng dữ liệu**, không phải tầng
hạ tầng: mọi fixture do lượt này tạo đều thuộc **hai tài khoản mới** và mang tiền tố
`[E2E]`. Trước khi bắt đầu đã chụp ảnh toàn bộ id có sẵn; sau khi dọn đã đối chiếu
lại từng tập hợp. Đây là một **giới hạn còn lại**, xem mục 9.

```powershell
# 0. Schema (idempotent) — chạy TRƯỚC, rồi mới khởi động service mới
$env:PYTHONPATH = "C:\Users\robux\Documents\CapCut-TTS-App"
.\.venv\Scripts\python.exe scripts/setup_appwrite.py
$env:PYTHONPATH = $null

# 1. Backend — tiến trình MỚI sau khi đổi schema (xem mục 8, lỗi #0)
.\.venv\Scripts\python.exe -m uvicorn server.main:app --port 8000

# 2. Frontend — production build, không dùng dev mode
cd web
npx next build
npx next start --port 3000
```

Tất cả service đều được khởi động từ **tiến trình mới** sau bước schema.

---

## 2. Kết quả từng hành trình

| Hành trình | Kết quả | Số kiểm tra |
|---|---|---|
| **A** — Xác thực và phân quyền | **ĐẠT** | 31/31 |
| **B** — Library, novel, chapter, validation | **ĐẠT** | 27/27 + giao diện |
| **C** — Phân trang và N+1 | **ĐẠT** | 19/19 + đo request |
| **D** — Studio và TTS | **ĐẠT** sau khi sửa 1 lỗi | xem mục 8, lỗi #1 |
| **E** — Dấu vân tay và cảnh báo audio cũ | **ĐẠT** | 21/21 |
| **F** — Recovery trong hành trình thực tế | **ĐẠT** | 12/12 |
| **G** — Reconciler | **ĐẠT** | 4 chế độ, xem mục 6 |
| **H** — Responsive và bàn phím | **ĐẠT** | 6 route × 2 viewport |

### A — Xác thực và phân quyền

Đăng ký A → đăng xuất → đăng nhập lại → deep-link giữ phiên. Mật khẩu sai và
token bịa đặt đều bị 401.

Bốn route riêng tư (`/api/novels?mine=true`, `/api/chapters?mine=true`,
`/api/jobs`, `/api/auth/me`) trả **401** cho cả ẩn danh lẫn token bịa đặt.
Trên giao diện, `/library` khi chưa đăng nhập hiển thị màn hình
"Cần đăng nhập để xem thư viện của bạn" kèm liên kết `/login` — chặn bằng
màn hình rõ ràng, không phải redirect ngầm.

`GET /api/novels` **không** kèm `mine` là danh mục **công khai**
(`published_only=True`), nên 200 cho khách là đúng thiết kế. Đã xác minh danh mục
công khai không lọt truyện nháp nào.

Tài khoản B **không** đọc/sửa/xoá được của A trên cả 10 đường:

| Thao tác của B lên dữ liệu riêng của A | Kết quả |
|---|---|
| `GET /api/novels/{id}` (nháp) | 404 |
| `GET /api/chapters/{id}` (nháp) | 404 |
| `PATCH /api/novels/{id}` | 403 |
| `PATCH /api/chapters/{id}` | 403 |
| `DELETE /api/novels/{id}` | 403 |
| `DELETE /api/chapters/{id}` | 403 |
| `POST /api/jobs` trên chương của A | 403 |
| `POST /api/novels/{id}/chapters/order` | 403 |
| `GET /api/audio/{chapter}` | 403 |
| `GET /api/audio/{chapter}/url` | 403 |

Truyện nháp trả **404** chứ không 403 — không tiết lộ sự tồn tại. Sau khi A xuất
bản: B và khách **đọc** được, nhưng B vẫn **không sửa** được (403).

### B — Library và novel

Thư viện rỗng hiển thị đúng trạng thái trống kèm hai lối đi tiếp. Tạo truyện qua
giao diện, sửa metadata (tiêu đề, mô tả, thẻ), refresh — dữ liệu bền vững.
Nút "Xuất bản" bị khoá kèm lý do *"Thêm ít nhất một chương trước khi xuất bản."*

Sắp xếp chương bằng nút ↑/↓ có nhãn trợ năng đầy đủ
(`aria-label="Di chuyển [E2E] Chương MỘT lên trên"`), khoá đúng ở đầu và cuối
danh sách. Chuyển `MỘT, HAI, BA` → `BA, MỘT, HAI`; thứ tự giữ nguyên sau khi tải
lại trang, và **trang công khai `/novels/{id}` hiển thị đúng thứ tự đó**.

Validation: tiêu đề rỗng / chỉ khoảng trắng / thiếu trường / quá 200 ký tự đều
422. Chương rỗng tạo được (bản nháp) nhưng **không** tạo được job — chặn ở
`POST /api/jobs` với *"Chương này chưa có nội dung."* Xoá chương rồi xoá truyện
đều dọn theo tầng; xoá lại lần hai trả 404, không nổ.

Không thêm chức năng mới nào để test đạt.

### C — Phân trang và N+1

Fixture 0 / 1 / 25 / 26 truyện. Số liệu đối chiếu lấy **trực tiếp từ Appwrite**
(`_list_all`), không qua route đang kiểm thử.

| Kiểm tra | Kết quả |
|---|---|
| Tài khoản B: 0 truyện, phân trang trên tập rỗng | không nổ |
| Không truyền `limit`: trả **28/28** truyện | không bị cắt ở 25 |
| Cỡ trang 1 / 10 / 25 / 26: ghép lại | đúng tập, **0 trùng, 0 thiếu** |
| Trang đầu `limit=25&offset=0` | đúng 25 |
| `total` khi `limit=25` | **28** — không bị `limit` giới hạn |
| Trang cuối `offset=25` | 3 (phần còn lại) |
| `offset=999` | rỗng, không lỗi |
| `q=` rỗng / `q` không khớp / `tag` không khớp | 200, danh sách rỗng đúng |
| `/api/jobs` | 26/26, không cắt ở 25 |
| `/api/chapters?mine=true` | 27/27, không cắt ở 25 |
| Phân trang riêng tư khi ẩn danh | 401 |
| B phân trang | chỉ thấy dữ liệu của B |

Giao diện `/fanfic` với 31 truyện đã xuất bản: 3 trang **12 + 12 + 7**, đủ 26
truyện `[E2E]` mỗi truyện đúng một lần, thứ tự mới-nhất-trước nhất quán qua các
trang, nút "Trang sau" khoá ở trang cuối. Mỗi lần đổi trang đúng **một** request
`GET /api/novels?limit=12&offset=…` — phân trang do backend làm, không tải hết
rồi lọc ở trình duyệt.

**Số request API** (đã loại static asset, source map, HMR):

| Trang | 0 bản ghi | 26–27 bản ghi | Tăng theo số bản ghi? |
|---|---|---|---|
| `/library` | **4** | **4** | **Không** |
| `/studio` | — | **5** | **Không** |
| `/novels/{id}` (3 chương) | — | **2** | **Không** |

`/library` (4 request): `auth/me`, `novels?mine=true`, `jobs`, `chapters?mine=true`
— giữ đúng mức tổng hợp đã đạt trước đây (mục tiêu ~5).
`/studio` (5 request): `auth/me`, `novels?mine=true`, `novels/{workspace}`,
`voices`, `jobs`.

**Presigned URL sinh đúng lúc**: `/library` với 27 audio phát **0** request
`/api/audio/*/url`. Chỉ khi bấm "Nghe" mới sinh URL cho **đúng một** chương.

### D — Studio và TTS

Chọn giọng và tốc độ ("Hơi nhanh"), tạo audio, theo dõi tới `Hoàn tất`. Audio
phát được thật: `duration = 66,7s`, `currentTime` tiến tới 0,97s, `readyState = 4`,
`error = null`. Có nút "⬇ Tải MP3" và "Nghe lại".

**Refresh giữa lúc job chạy** làm lộ một lỗi thật — xem mục 8, lỗi #1. Sau khi
sửa: trạng thái tự chuyển `Đang xử lý` → `Hoàn tất` ở giây **38** mà không cần
tải lại thủ công.

### E — Dấu vân tay và cảnh báo "audio cũ"

Chạy tuần tự trên **cùng một** chương:

| Bước | Hành động | `audio_outdated` | Kết quả |
|---|---|---|---|
| 1 | Tạo audio từ nội dung A | `False` | ĐẠT |
| 2 | Sửa A → B | `True` | ĐẠT |
| 3 | **Hoàn nguyên B → A chính xác** | `False` | **ĐẠT** |
| 4 | Đổi giọng, tạo audio mới | `False` | ĐẠT |
| 4b | Đổi nội dung khi đang ở giọng 2 | `True` | ĐẠT |
| 5 | Hoàn nguyên | `False` | ĐẠT |
| 6 | Đổi tốc độ → dấu vân tay khác | dấu vân tay đổi | ĐẠT |
| 6b | Đổi `chunk_chars` → dấu vân tay khác | dấu vân tay đổi | ĐẠT |
| 7 | Track cũ thiếu dấu vân tay | `can_verify=False`, route không nổ | ĐẠT |
| 8 | Tạo lại cùng tham số | trả **đúng job cũ** | ĐẠT |
| 9 | Sau khi tạo lại | 3 track → **3** track, 3 object → **3** object | ĐẠT |

Bước 3 là điểm cốt lõi: cách đo bằng mốc thời gian **không bao giờ** tắt được
cảnh báo sau khi hoàn nguyên. Cách so dấu vân tay làm được.

Trên giao diện, cảnh báo hiển thị đúng tinh thần M4:

> ⚠ Chương này đã được sửa sau khi tạo audio, nên audio có thể không còn khớp với
> nội dung bên dưới. **Bản audio hiện tại vẫn nghe và tải được.**
> → *Tạo lại audio trong khu vực tác giả*

Nêu rõ vấn đề, khẳng định không xoá bản cũ, để người dùng tự chọn, có lối đi tiếp.

### F — Recovery trong hành trình thực tế

Chương 25.200 ký tự chia 100 đoạn. Giết **cả cây tiến trình** worker lúc job đang
xử lý dở, đã xác minh không còn tiến trình `python.exe` nào của repo.

Lần chạy đầu (12:12–12:15 UTC):

| Mốc UTC | status | attempts | tiến độ | lease_owner / hết hạn |
|---|---|---|---|---|
| 12:12:25 | *giết worker* | 1 | 29/100 | `44004-…` / 12:13:36 |
| 12:12:54 | `running` | 1 | 29/100 | `44004-…` (**đã chết**) — worker mới **bỏ qua** |
| 12:13:45 | `running` | **2** | 29/100 | `22328-…` (nhận sau khi lease hết hạn) |
| 12:15:06 | `completed` | 2 | 100/100 | `(trống)` — đã nhả |

Điểm quan trọng: lúc 12:12:54 worker thay thế **đã chạy** nhưng **không** giật
job, vì lease của worker đã chết còn hạn tới 12:13:36. Nó chỉ nhận lúc 12:13:45.

Kiểm chứng cuối (cả lần chạy đầu và lần chạy lại sau khi sửa mã):

| Kiểm tra | Kết quả |
|---|---|
| Số dòng `job_claims` cho job | **đúng 2** (1 chết + 1 thu hồi) |
| Khoảng cách claim#1 → claim#2 | 129 s / 652 s — đều **> lease 90 s** |
| Trạng thái cuối | `completed`, `attempts = 2` |
| Lease sau khi xong | đã nhả (`None`) |
| Số track | **1** |
| Số object R2 | **1** |
| Track trỏ đúng object | ĐẠT |
| Kích thước file | 10.584.237 byte |
| Worker cũ (fence 1) ghi `failed` | **bị từ chối** (`save_job_fenced → False`) |
| Trạng thái sau khi worker cũ thử ghi | vẫn `completed`, `output_key` nguyên |

UI sau refresh: đúng **một** trình phát, `duration = 1764 s`, không lỗi, không
cảnh báo sai.

Không benchmark chương 1.000.000 ký tự.

### H — Responsive và bàn phím

| Route | Desktop 1440×900 | Mobile 390×844 |
|---|---|---|
| `/login` | không tràn | không tràn |
| `/library` | không tràn | không tràn |
| `/fanfic` | không tràn | không tràn |
| `/studio` | không tràn | không tràn |
| `/write` | không tràn | không tràn |
| `/novels/{id}` | không tràn | không tràn |
| `/chapters/{id}` | không tràn | không tràn |

`body.scrollWidth == documentElement.clientWidth` ở mọi route — không cuộn ngang,
không phần tử nào vượt viewport, không nút bị che, không nội dung không cuộn được.

Phần tử duy nhất nằm ngoài viewport là `a.skip-link` ở `left: -9999px` — mẫu trợ
năng **cố ý**, không phải lỗi.

**Vùng bấm.** Mọi `<button>` trên mọi route đều ≥ 44px. Trên `/library` có 29 thẻ
`<a>` cao 37px — đó là link chữ **nội dòng trong câu văn** ("Thuộc truyện …"),
trường hợp WCAG 2.5.8 miễn trừ tường minh. Không nút thao tác nào dưới ngưỡng.

**Bàn phím.** Tab đầu tiên vào đúng skip-link ("Bỏ qua điều hướng") với viền focus
`solid 2px`. Trên `/write`: **51/51** phần tử nhận focus được đều có dấu hiệu focus
(outline hoặc box-shadow) — **0** phần tử thiếu.

**Không có cảnh báo hệ điều hành nào** (Bonjour `mdnsNSP.dll` hay tương tự) trong
lượt này. Lỗi console duy nhất là `401` từ `/api/auth/me` khi chưa đăng nhập —
đúng thiết kế (thăm dò phiên), không phải lỗi ứng dụng.

---

## 3. Có dùng stub không

**Trong các hành trình chính: không.** Backend, Appwrite, R2 và Edge TTS đều thật.

Chỉ hai chỗ dùng stub, đều là **test tự động** chứ không phải hành trình E2E:

| Nơi | Stub gì | Vì sao |
|---|---|---|
| `server/tests/test_claim_atomicity.py::TestOnlyOneSynthesisPerJob` | `tts_bridge.synthesize_chapter` bị thay bằng hàm đếm số lần gọi | Cần **đếm chính xác** số lần tổng hợp khi 10 worker tranh nhau. Claim, fencing, upload và ghi track đều là mã thật. |
| cùng file | `_WorkerPerThread` thay `worker_id` bằng danh tính riêng từng luồng | `WORKER_ID` là hằng số của **tiến trình**; 10 luồng trong một tiến trình sẽ dùng chung một id, đó là tạo tác của phép thử chứ không phải hành vi thật. |

---

## 4. Số test từng bộ

| Bộ | Số test | Kết quả |
|---|---|---|
| `server/tests` (venv **sạch**) | **521** | 520 đạt, 1 bỏ qua |
| `web` (`node --test`) | **152** | 152 đạt, 0 hỏng |
| `npx tsc --noEmit` | — | exit **0** |
| `npx eslint .` | — | exit **0** |
| `npx next build` | — | exit **0**, 7 route |
| Hành trình E2E ở mức API | **110** kiểm tra | tất cả đạt |

Test bỏ qua là test thông báo lỗi khi thiếu `boto3`; `boto3` đã có trong
`server/requirements.txt` nên nó tự bỏ qua — đúng thiết kế.

Venv sạch: `%TEMP%\fas-clean-venv`, **ngoài** working tree, Python 3.12.10,
**39 gói** chỉ từ `server/requirements.txt`, **không có PySide6/shiboken**,
`PYTHONPATH` rỗng.

---

## 5. Kết quả TTS và recovery

| Hạng mục | Giá trị |
|---|---|
| Job TTS thật đã chạy | **35** (26 fixture phân trang + 5 dấu vân tay + 4 recovery/studio) |
| Job `completed` | tất cả trừ các job cố ý cho thất bại |
| Audio dài nhất | 1764 s (29 phút), 10,58 MB |
| Audio đã phát thật trong trình duyệt | 2 bản, `duration > 0`, `error = null` |
| Số track cuối cho chương recovery | **1** |
| Số object cuối cho chương recovery | **1** |

---

## 6. Kết quả reconciler

| Lần chạy | Chế độ | Mồ côi | Đã xoá | Kết quả |
|---|---|---|---|---|
| Trước khi tạo mồ côi | dry-run, ân hạn 24 h | 0 | — | 43 object, tất cả có tham chiếu |
| Sau khi tạo 1 mồ côi | dry-run, ân hạn **24 h** | **0** | — | xếp vào "còn trong ân hạn" — ân hạn hoạt động |
| Cùng dữ liệu | dry-run, ân hạn **0 h** | **1** | 0 | phát hiện đúng, **không xoá gì** |
| Chỉ `--delete` | — | — | — | **từ chối**: "thiếu `--yes-really-delete`" |
| `--delete --yes-really-delete` | XOÁ | 1 | **1** | chỉ mồ côi bị xoá, 43 object hợp lệ nguyên vẹn |
| Sau khi xoá | dry-run, ân hạn 0 h | **0** | — | sạch |
| Xoá file của một track fixture | XOÁ | 0 | **0** | báo *"Bản ghi trỏ tới object không tồn tại (MẤT DỮ LIỆU — không tự xoá)"* |
| Cuối cùng, sau khi dọn fixture | dry-run | 0 | — | 11 object, 11 có tham chiếu, 0 lỗi |

Phân loại đầy đủ bốn nhóm: `đã được tham chiếu` / `đang xử lý` / `còn trong ân hạn`
/ `MỒ CÔI`, cộng nhóm `Bản ghi thiếu file` chỉ báo cáo và **không bao giờ tự xoá**.

Bốn báo cáo JSON đã quét: **không** có dấu hiệu API key, secret, token, JWT hay
presigned URL nào.

---

## 7. Dọn dẹp — đối chiếu trước / sau

Ảnh chụp toàn bộ id **trước** khi bắt đầu, đối chiếu lại **sau** khi dọn:

| Tập hợp | Trước | Sau | Mất | Còn sót | Kết quả |
|---|---|---|---|---|---|
| `novels` | 18 | 18 | **0** | **0** | OK |
| `chapters` | 31 | 31 | **0** | **0** | OK |
| `tts_jobs` | 13 | 13 | **0** | **0** | OK |
| `audio_tracks` | 11 | 11 | **0** | **0** | OK |
| `job_claims` | 0 | 0 | **0** | **0** | OK |
| Object R2 | 11 | 11 | **0** | **0** | OK |

Đã xoá: 42 truyện, 42 chương, 42 job, 42 track, 41 object R2, 48 dòng
`job_claims`. **Không đụng đến một bản ghi nào có từ trước.**

Cơ chế an toàn hai lớp: (1) chỉ xoá bản ghi thuộc tài khoản E2E; (2) loại trừ mọi
id nằm trong ảnh chụp ban đầu, kèm `assert` tiêu đề phải bắt đầu bằng `[E2E]`.

Ba tài khoản test (`e2e-a-…@example.test`, `e2e-b-…@example.test`) không còn dữ
liệu nào. Bản thân tài khoản Appwrite vẫn tồn tại — xem giới hạn ở mục 9.

Mọi server, worker và tiến trình nền đã dừng. Venv sạch tạm đã xoá.

---

## 8. Lỗi phát hiện và cách sửa

### #0 — Chú thích lỗi thời: "Appwrite không có compare-and-swap"

**Không phải lỗi chạy**, nhưng là tài liệu sai dẫn người đọc sau này tới kết luận
sai. Có ở ba nơi:

| Tệp | Nội dung sai | Đã sửa thành |
|---|---|---|
| `server/main.py` (chú thích khối) | *"không cần compare-and-swap thật sự (Appwrite không có)"* | Nêu rõ claim là CAS thật bằng transaction, kèm cảnh báo phải restart sau khi đổi schema |
| `docs/WEB_README.md` | Bảng transition ghi `running` dùng `store.save_job()` | `store.claim_job()`; `completed`/`failed` dùng `save_job_fenced()`; thêm mục về transaction và fencing |
| `docs/APPWRITE_SCHEMA.md` | Thiếu hẳn `job_claims` và ba trường lease | Đã thêm cả hai bảng kèm cách rollback |

`docs/WEB_README.md` còn ghi *"Dọn rác này cần một job quét định kỳ — chưa làm"* —
đã có `scripts/reconcile_audio.py`; đã cập nhật.

Câu *"Appwrite không có PATCH nhiều document trong một request"* ở
`server/appwrite_store.py:821` **vẫn đúng** và được giữ nguyên.

Regression test: `server/tests/test_e2e_regressions.py::TestTheStaleTransactionClaimIsGone`
— quét mã nguồn tìm các câu sai về CAS/transaction, và kiểm tra yêu cầu restart
có được ghi lại.

### #1 — `/studio` kẹt ở "Đang xử lý" sau khi tải lại trang giữa lúc job chạy

**Bước tái hiện**
1. Đăng nhập, mở `/studio`.
2. Dán văn bản, bấm "Tạo audio".
3. Trong lúc job còn `running`, **tải lại trang**.
4. Chờ.

**Hiện tượng.** Job hoàn tất trên backend nhưng thẻ trong "Lịch sử audio" hiển thị
"Đang xử lý" **mãi mãi**. Bằng chứng: sau khi tải lại, trình duyệt gọi `/api/jobs`
**đúng một lần** rồi không hỏi lại. Đã quan sát 150 giây liên tục trong khi
backend đã `completed` từ lâu.

**Nguyên nhân.** `activeJob` chỉ được đặt trong hàm submit, nên sau khi tải lại
trang nó là `null`. Effect poll bắt đầu bằng
`if (!activeJob || ...) return` nên thoát ngay và không bao giờ hỏi lại backend.

**Tệp sửa.** `web/src/app/studio/page.tsx` — sau khi nạp danh sách job, tìm job
`pending`/`running` còn sót và đặt làm `activeJob` (dùng `current ?? dangChay` để
không đè lên job người dùng đang theo dõi).

**Regression test.** `web/tests/e2e-regressions.test.mjs` — 3 test. Đã kiểm chứng
chúng **hỏng** trên mã trước khi sửa.

**Chạy lại hành trình.** Sau khi sửa và build lại: `Đang xử lý` → `Hoàn tất` tự
động ở giây **38** sau refresh.

### #2 — Tiêu đề chỉ gồm khoảng trắng tạo ra bản ghi có tiêu đề rỗng

**Bước tái hiện**
```
POST /api/novels {"title": "   "}   ->  201, title đọc lại = ""
POST /api/novels {"title": ""}      ->  422
```

**Hiện tượng.** Cùng một giá trị hiệu dụng, hai kết quả khác nhau. Thứ nằm trong
kho là một truyện **tiêu đề rỗng**, hiển thị thành thẻ trắng trên `/fanfic` và
`/write`.

**Nguyên nhân.** `Field(min_length=1)` đo độ dài chuỗi **thô**; việc cắt khoảng
trắng xảy ra sau đó khi lưu.

**Tệp sửa.** `server/main.py` — thêm
`TieuDe = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]`
và dùng cho cả bốn trường tiêu đề (`NovelIn`, `ChapterIn`, `NovelPatch`,
`ChapterPatch`). Cắt trước rồi mới đo, nên `""` và `"   "` bị từ chối như nhau.
Giới hạn 200 ký tự cũng được đo **sau** khi cắt, nên `"  " + "x"*200 + "  "` vẫn
được nhận.

**Regression test.** `server/tests/test_e2e_regressions.py::TestTitleIsTrimmedBeforeItIsMeasured`
— 7 test, phủ novel, chapter, cả tạo mới lẫn sửa, và biên 200/201 ký tự. Trên mã
trước khi sửa: **14 lượt hỏng**.

### Hai thứ **không** phải lỗi (kỳ vọng của phép thử sai)

| Hiện tượng | Sự thật |
|---|---|
| `POST /api/jobs` với giọng không tồn tại trả **201** | Giọng được kiểm chứng ở **worker**, không ở POST. Job kết `failed` với `error_kind = voice_not_found`, `voice_id` **giữ nguyên**, không sinh audio. Quy tắc "không tự đổi sang giọng khác" được tôn trọng. Đã khoá lại bằng test. |
| `POST /api/chapters` với `content: ""` trả **201** | Chương rỗng là bản nháp hợp lệ. Rào chắn nằm ở `POST /api/jobs`: **400** kèm *"Chương này chưa có nội dung."* Đúng chỗ. Đã khoá lại bằng test. |

Không lỗi nào được che bằng cách tăng timeout hay thêm `sleep` không xác định.
Mọi chỗ chờ đều chờ **một điều kiện cụ thể**: `thread.join()`, poll trạng thái
job, hoặc `curl` cho tới khi cổng phản hồi 200.

### Ba lần thất bại khi dựng lại kịch bản recovery (vấn đề của phép thử)

Hai lần đầu job chạy xong **trước** khi cú giết kịp thi hành: độ trễ giữa lệnh
phát hiện và lệnh giết quá lớn. Lần thứ ba, script tự `taskkill` **chính nó** —
nó cũng là `python.exe` trong `.venv` của repo. Đã gộp phát hiện và giết vào một
lệnh, và loại trừ `os.getpid()`. Đáng ghi lại: `Get-NetTCPConnection` trả về PID
**con**; phải giết cả cây (`taskkill /T /F`) rồi **kiểm chứng** không còn tiến
trình nào — đúng cái bẫy `pythonw.exe` shim đã biết.

---

## 9. Giới hạn còn lại trước push/deploy

| # | Giới hạn | Mức |
|---|---|---|
| 1 | **Chưa có project/bucket Appwrite riêng cho test.** Lượt này cô lập ở tầng dữ liệu (tài khoản mới + tiền tố `[E2E]` + đối chiếu ảnh chụp). Đủ cho MVP riêng tư, **không đủ** khi đã có dữ liệu người dùng thật. | Cao |
| 2 | **Tài khoản test không xoá được qua API hiện có.** Dữ liệu đã sạch nhưng ba tài khoản `@example.test` vẫn còn trong Appwrite Auth. Chưa có route xoá tài khoản. | Trung bình |
| 3 | **`_supported_fields()` cache theo vòng đời tiến trình.** Migrate schema khi server đang chạy thì claim vẫn chạy ở nhánh **không nguyên tử** mà không báo lỗi gì. Quy trình deploy **bắt buộc** phải restart sau migration. | Cao |
| 4 | **Chưa có transaction phân tán giữa R2 và Appwrite.** Ghi `completed` hỏng ngay sau upload để lại object rác. Vô hại (`output_key` bị xoá) và dọn được bằng reconciler, nhưng cần chạy reconciler định kỳ. | Trung bình |
| 5 | **Reconciler chưa tự động.** Phải chạy tay. Chưa có cron/scheduler. | Trung bình |
| 6 | **Giấy phép thương mại của giọng đọc chưa xác minh.** Chân trang đã ghi rõ. Ngoài phạm vi lượt này. | Chặn thương mại hoá |
| 7 | **Chưa ký số** (Smart App Control) — chỉ liên quan desktop, không chặn web. | Thấp |
| 8 | **Chưa kiểm ở tải cao.** Không benchmark chương 1.000.000 ký tự, không thử nhiều người dùng đồng thời. Ngoài phạm vi. | Chưa biết |
| 9 | **Chưa có payment / quota / admin.** Ngoài phạm vi, nhưng là điều kiện để thương mại hoá. | Chặn thương mại hoá |
| 10 | **Job chạy trong thread của tiến trình web.** Restart web là giết luôn worker. Recovery xử lý được (đã chứng minh), nhưng deploy nhiều bản sẽ cần worker tách riêng. | Trung bình |

---

## 10. Kết luận

**Không tuyên bố "production-ready".** Test tự động đạt không phải là căn cứ cho
kết luận đó.

Kết luận **thực tế**: đủ điều kiện chuyển sang **bước chuẩn bị deploy** cho một
bản **riêng tư, chưa thương mại**, với bốn điều kiện bắt buộc:

1. Quy trình deploy phải **restart backend sau mỗi lần migrate schema** (giới hạn #3).
2. Chạy reconciler ở chế độ dry-run sau lần deploy đầu, trước khi bật chế độ xoá
   (giới hạn #4, #5).
3. Tạo project/bucket Appwrite riêng cho test **trước** khi có dữ liệu người dùng
   thật (giới hạn #1).
4. Không mở cho người dùng ngoài cho tới khi giấy phép giọng đọc được xác minh
   (giới hạn #6).

**Chưa** đủ điều kiện cho bản thương mại: thiếu payment, quota, admin, worker
tách riêng và kiểm thử tải.

---

## 11. Ảnh chụp màn hình

Ở `docs/screenshots/e2e/`:

| Tệp | Nội dung |
|---|---|
| `01-library-rong-desktop.png` | Thư viện rỗng, 1440×900 |
| `02-library-26-audio-desktop.png` | 26 audio, vẫn 4 request |
| `03-fanfic-trang-cuoi-desktop.png` | `/fanfic` trang 3/3 |
| `04-novel-thu-tu-desktop.png` | Trang truyện công khai, đúng thứ tự đã sắp |
| `05-studio-hoan-tat-desktop.png` | Studio sau khi job hoàn tất |
| `06-canh-bao-audio-cu-desktop.png` | Cảnh báo audio cũ |
| `07-library-mobile-390.png` | Thư viện, 390×844 |
| `08-write-mobile-390.png` | Khu vực tác giả, 390×844 |
| `09-chuong-canh-bao-mobile-390.png` | Cảnh báo audio cũ, 390×844 |
| `10-studio-mobile-390.png` | Studio, 390×844 |
| `11-sau-recovery-desktop.png` | Chương sau recovery, một trình phát |

Báo cáo reconciler ở `docs/reports/e2e/`: `doi-soat-truoc.json`,
`doi-soat-mo-coi.json`, `doi-soat-sau-xoa.json`, `doi-soat-thieu-file.json`,
`doi-soat-cuoi.json`.

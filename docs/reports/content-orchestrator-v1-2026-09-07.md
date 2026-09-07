# CONTENT ORCHESTRATOR V1 — bản tiêu thụ hàng đợi đã thiếu (2026-09-07)

Nối lại công cụ sản xuất nội dung từ trạng thái THẬT của kho, không thiết kế
lại gì. Mảnh còn thiếu không phải suy đoán — **chính mã nguồn đã gọi tên nó ở
hai chỗ trước khi nó tồn tại**:

* `server/domain.py:1526` — `ChineseMediaQueueItem`: "xem
  `scripts/chinese_media_watcher.py` (tạo) và
  `scripts/chinese_media_orchestrator.py` (chạy tiếp)"
* `server/appwrite_store.py:882` — `list_queue_items_by_state`: "mục đích duy
  nhất của hàm này là nguồn việc cho `chinese_media_orchestrator.py`"

Tệp đó không tồn tại. 30 tập thật nằm trong `content_queue` từ 2026-09-02 và
**không có gì đọc chúng**.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Bản tiêu thụ `content_queue` | **Không tồn tại** — 30 mục thật nằm im | `scripts/chinese_media_orchestrator.py`, 6 công đoạn, resume được |
| Điểm dừng ASR (`transcript_key`) | Trường có trong schema, **không có gì ghi vào** | Ghi ngay khi ASR xong; lần chạy sau bỏ qua ASR hoàn toàn |
| Nối lại việc dở | Chạy lại từ đầu — mỗi lần tốn một lượt ASR ~35–90 phút | Nối lại đúng công đoạn còn dở |
| Khoá R2 của phụ đề | `os.urandom(4)` — mỗi lần chạy lại bỏ lại một object mồ côi | Tất định theo `item_id` (đường mặc định giữ nguyên hành vi cũ) |
| Khoá R2 của bản dub | **Ghi nhầm vào tiền tố `subtitles/`** (lỗi thật, xem mục 3) | `dub_audio/…` đúng tiền tố |
| Phân biệt "đang chờ" và "hỏng" | Không có | `PENDING` + `CHO:` ≠ `FAILED`; chỉ FAILED mới cộng `attempts` |
| Cổng quyền `render` | Chỉ là kỷ luật viết trong tài liệu | **Cưỡng chế bằng mã**, có 4 bài test bảo vệ |
| Mục kẹt ở `RUNNING` sau khi tiến trình chết | Kẹt vĩnh viễn | `--reclaim-stale <phút>`, chỉ chạy khi gọi tường minh |
| `--dry-run` | — | Lập kế hoạch thật: **không gọi công đoạn nào**, nên không tốn lượt ASR/quota dịch |
| Nhặt lại điểm dừng ASR mồ côi sau khi tiến trình chết | Không có — chạy lại ASR | Hỏi R2 theo khoá tất định trước khi chạy ASR |
| Dịch thiếu | Đánh `DONE`, phụ đề lặng lẽ thiếu nội dung | `FAILED` nhưng **giữ phần đã dịch** |
| Trạng thái không lối ra (`draft=FAILED` + hết `PENDING`) | Kẹt vĩnh viễn | `FAILED` vẫn được chọn lại chừng nào `attempts` chưa hết |
| Test cho đường này | 0 | **51 PASS** (44 mới cho orchestrator + 7 cho khoá `ship_draft`) |

## 1. Công cụ sản xuất hiện GỒM những gì

Kết luận sau khi đọc kho, không dựa vào tài liệu cũ:

| Lớp | Trạng thái thật |
|---|---|
| Schema `content_queue` (20 trường, 6 máy trạng thái, 4 index) | **Đã cấp phát, đang sống** |
| CRUD hàng đợi trong `AppwriteMetadataStore` | **Đã có** |
| Watcher (phát hiện → hàng đợi) | **Đã chạy thật — 30 tập** |
| 7 hàm công đoạn (`chinese_media_pipeline.py`, 876 dòng) | **Đã có, QA_PASS, đóng băng** |
| Bản tiêu thụ hàng đợi | **Đây là phần đã thiếu — nay đã có** |
| Route API trên hàng đợi | **Vẫn chưa có** — đây là bước tích hợp web kế tiếp |

`chinese_media_pipeline.main()` là đường chạy MỘT tập, không điểm dừng, người
vận hành gọi tay. Các `scripts/ship_*_runner.py` là runner một-lần cho từng
truyện cụ thể. Không có gì đọc hàng đợi.

## 2. Orchestrator dùng lại, không chép lại

Không một dòng logic công đoạn nào bị sao chép. Orchestrator chỉ điều phối:
chọn việc, kiểm tiền điều kiện, gọi đúng hàm trong `chinese_media_pipeline`,
ghi trạng thái.

Đồ thị phụ thuộc:

```
transcript -> translation -> subtitle -+-> dub (tuỳ chọn)
                                       +-> draft  (cần subtitle DONE
                                                   và dub DONE/SKIPPED)
render: nhánh riêng, có cổng quyền
```

`draft` **không** chờ `render` — đúng hành vi đã chứng minh của
`chinese_media_pipeline.main()`: nó ship draft (phụ đề + dub) mà không render,
vì không được phép giữ lại byte media gốc.

## 3. Hai lỗi thật tìm được trong đường đã đóng băng

**(a) Bản dub bị ghi vào tiền tố `subtitles/`.** `ship_draft()` suy ra khoá dub
bằng `subtitle_key.replace("/subtitles/", "/dub_audio/")` — nhưng khoá **không
có dấu `/` ở đầu**, nên phép thay thế không bao giờ khớp. Đo trực tiếp, không
suy luận:

```
TRUOC khi sua: subtitles/svc_harvester/clip-a1b2c3d4.mp3
SAU  khi sua: dub_audio/svc_harvester/clip-a1b2c3d4.mp3
```

Bốn bài test sẵn có của `ship_draft` **đều không bắt được** vì không bài nào
nhìn vào khoá dùng để tải lên. Đã thêm 5 bài phủ đúng chỗ đó.

**Không phá dữ liệu cũ:** hàng đã ghi vẫn giữ khoá đã lưu trong
`dub_audio_key`, nên vẫn phân giải bình thường. Sửa này chỉ đổi khoá của các
lần tải lên MỚI.

**(b) Khoá phụ đề không tất định.** `os.urandom(4)` khiến mỗi lần chạy lại bỏ
lại một object mồ côi — đúng lớp lỗi đã ghi nhận ở
`docs/reports/cloudrun-gate-orphan-objects-2026-09-06.md`. Đã thêm tham số
**tuỳ chọn** `subtitle_key`/`dub_key`; bỏ trống thì hành vi cũ giữ nguyên từng
byte (có test), còn orchestrator truyền khoá tất định theo `item_id`.

## 4. `PENDING` khác `FAILED` — quyết định quan trọng nhất

Công cụ này **không tải media từ bất kỳ nguồn nào** (giữ nguyên ranh giới
`chinese_media_pipeline.py` tự đặt). Nên một mục không có phụ đề gốc và chưa
được đưa `--audio` thì giữ nguyên `PENDING` và **không bị cộng `attempts`**.

Nếu đánh dấu `FAILED`, sau `--max-attempts` lần chạy *không làm gì cả* mục đó
sẽ dừng hẳn — mất việc trong im lặng. `last_error` cũng tách ba đường: lỗi
thật ghi nguyên văn, mục đang chờ ghi kèm tiền tố `CHO: `, còn công đoạn xong
thì **xoá** để một lần thử lại thành công không để lại lỗi cũ treo lại.

## 5. Cổng quyền cưỡng chế bằng mã

`render` chỉ chạy với `rights_mode="REHOST_ALLOWED"`; mọi giá trị khác →
`SKIPPED` kèm lý do, không bao giờ `FAILED` (đây là quyết định có chủ đích,
không phải sự cố). Không cờ dòng lệnh hay biến môi trường nào nới lỏng được.

Cả 30 mục thật đều `REFERENCE_ONLY` → `render` `SKIPPED` cho tất cả. Kể cả với
`REHOST_ALLOWED`, orchestrator vẫn không tự render: đó là bước người vận hành
chạy tay. Có bài test khẳng định orchestrator **không bao giờ** gọi
`compose_with_source`.

## 6. Test

```
scripts.tests.test_chinese_media_orchestrator        44 PASS  (mới hoàn toàn)
scripts.tests.test_chinese_media_pipeline_ship_draft  7 PASS  (2 cũ + 5 mới)
--------------------------------------------------------------
riêng phần mới                                        51 PASS / 0 FAIL

CẢ HAI CỔNG THẬT, sau khi sửa xong hai vòng review:
python -m unittest discover -s scripts/tests -t .    926 PASS / 0 FAIL (4 skip)
python -m unittest discover -s server/tests  -t .  4.435 PASS / 0 FAIL (3 skip)
```

Cổng backend được chạy vì `server/appwrite_store.py` có sửa (thêm `offset` vào
`list_queue_items_by_state`, thuần cộng thêm).

Trong 44 bài của orchestrator, **13 bài neo thẳng vào 13 phát hiện của hai vòng
review** — mỗi bài đặt tên theo đúng kịch bản hỏng, để một lần sửa sau này làm
hỏng lại thì test gọi được tên nguyên nhân.

Không Appwrite, không R2, không HTTP trong phần mới: store là bản giả trong bộ
nhớ, mọi hàm công đoạn đều mock.

## 7. Review chéo họ model đã bắt được 8 lỗi thật

Diff được gửi cho Codex (review độc lập khác họ model, đúng chính sách
`ORDINARY_REVIEW`). Nó trả về **`STATUS: FAILED` với 8 phát hiện** — bảy cái
đã sửa, một cái sửa được một phần và đã ghi rõ giới hạn.

| # | Lỗi | Kịch bản hỏng | Đã làm gì |
|---|---|---|---|
| 1 | `--dry-run --reclaim-stale` **vẫn ghi thật** — nhánh reclaim không đi qua cổng dry-run | Người vận hành xem thử, thực tế reset hết mục `RUNNING` | `reclaim_stale(dry_run=…)`, có test |
| 2 | Dry-run chạy thật ASR/dịch/dub rồi vứt kết quả; `stage_transcript` bịa `transcript_key` mà không tải lên → `stage_translation` tải về object không tồn tại | Một lần "chạy thử" tốn 35–90 phút ASR rồi báo lỗi dịch giả | `run_stage` chặn trước khi gọi bất kỳ công đoạn nào; bỏ hẳn cờ dry-run bên trong các công đoạn |
| 3 | Khe cửa sổ giữa lúc tải transcript lên R2 và lúc ghi `transcript_key` | Tiến trình chết đúng khe đó → lần sau **chạy lại ASR** dù object đã nằm sẵn trên R2 | `precheck_transcript` hỏi `exists_in_r2(khoá tất định)` và **nhặt lại** |
| 4 | Giành việc không nguyên tử; kết quả về muộn ghi đè trạng thái mới; hai lần thất bại đồng thời làm mất một lượt `attempts` | Hai tiến trình cùng rút một hàng đợi | **Chỉ sửa được một phần** — xem mục 8 |
| 5 | Mục bị chặn bị ghi `RUNNING` **trước khi** phát hiện ra nó bị chặn | Chết ở giữa → kẹt `RUNNING` vĩnh viễn dù chưa chạy gì | Lớp `STAGE_PRECHECK` chạy hết mọi điều kiện rẻ **trước** khi ghi `RUNNING` |
| 6 | Cổng quyền `render` không bao giờ tới nơi khi công đoạn trước đó bị chặn | Mục `REFERENCE_ONLY` đang chờ `--audio` kẹt `render=PENDING` vô hạn — nhìn như chính sách chưa được áp | `rights_verdict()` áp ngay đầu `process_item`, không phụ thuộc tiến độ |
| 7 | **Dịch thiếu vẫn bị đánh `DONE`** | 99/100 đoạn dịch xong → `DONE`; công đoạn phụ đề lặng lẽ loại đoạn còn lại; ra bản phụ đề thiếu nội dung và không bao giờ dịch lại | Đủ 100% mới `DONE`; thiếu thì `FAILED` **nhưng vẫn lưu phần đã dịch** để lần sau dịch tiếp |
| 8 | `collect_work` áp `limit` **trước** khi lọc mục hết lượt | 10 mục đầu hết lượt → mọi lần chạy đều chọn đúng chúng, bỏ qua hết, về tay không; mục chạy được phía sau chết đói | Lọc `attempts` trước khi áp `limit` |

Đây chính là lý do review chéo họ model đáng giá: bảy trong tám lỗi này là lỗi
máy trạng thái/idempotency mà bộ test *của chính người viết* không hỏi tới.

### Vòng review thứ hai — thêm 6 phát hiện, trong đó MỘT trạng thái không lối ra

Bản đã sửa được gửi lại cho chính reviewer đó. Kết quả `STATUS: PARTIAL`, 6
phát hiện mới. Nghiêm trọng nhất là một lỗi **do chính bản sửa vòng 1 tạo ra**:

| # | Lỗi | Đã làm gì |
|---|---|---|
| 1 | **TRẠNG THÁI KHÔNG LỐI RA.** Một mục có `draft=FAILED` và mọi công đoạn khác đã kết thúc thì **không còn công đoạn `PENDING` nào** → `collect_work` (chỉ truy vấn `PENDING`) không bao giờ chọn lại nó, dù `attempts` vẫn còn. Lộ ra do vòng 1 đưa cổng quyền lên trước. | `RETRYABLE_STATES = ("PENDING", "FAILED")` |
| 2 | Cổng quyền chỉ áp khi `render_state == "PENDING"`; và `_commit` **xoá mất `last_error` của công đoạn khác** khi đánh dấu `render=SKIPPED` → mục chết không còn dấu vết chẩn đoán | Áp cho mọi trạng thái ≠ `SKIPPED`; `last_error` nay **gắn tên công đoạn** và chỉ bị xoá bởi chính công đoạn đó |
| 3 | Phép kiểm đồng thời **fail OPEN**: đọc lại lỗi → vẫn chạy tiếp, đúng lúc phép kiểm an toàn vừa hỏng. Các commit từ precheck không hề đọc lại | `_stale_claim()` **fail CLOSED**, và chạy trước **mọi** lần ghi |
| 4 | Nhặt lại điểm dừng R2 chỉ tin vào sự **tồn tại** → object rỗng/hỏng bị nhận bừa là `DONE`; `transcript_key` được đặt nên ASR không bao giờ chạy lại, mọi công đoạn sau chết khi đọc — **một cái bẫy không lối ra nữa** | Tải về, đọc thử, phải có ≥1 đoạn hợp lệ mới nhận |
| 5 | Lọc `attempts` vẫn sau khi kho dữ liệu đã cắt `limit * 4` → vẫn chết đói khi 40 hàng đầu đều hết lượt | **Phân trang thật** (thêm `offset` vào `list_queue_items_by_state`) |
| 6 | `--dry-run` báo `render` hai lần; `summarize` đếm bản ghi dry-run như đã tiến | Chặn lần hai; `stages_advanced` bỏ qua bản ghi `dry_run` |

Thêm một điểm reviewer nêu ở phần tổng kết và đã sửa: `attempts` là ngân sách
**của cả mục** và trước đó không bao giờ được đặt lại — một lỗi ASR sớm cộng
một lỗi dịch muộn sẽ giết một mục đang tiến triển bình thường. Nay **`DONE` đặt
lại về 0** (`SKIPPED` thì không — coi một quyết định chính sách là tiến bộ sẽ
hồi sinh mãi mãi một mục đã chết hẳn).

Một lỗi nữa do **chính bài test của phiên này** bắt được, không phải reviewer:
phép kẹp `max(limit, min(limit*4, 100))` vẫn trả 500 khi `--limit 500`. Đã bỏ
hẳn cùng lúc chuyển sang phân trang.

## 8. Một lỗi CHƯA sửa hết — nói rõ giới hạn

Phát hiện #4 (giành việc không nguyên tử) **không sửa trọn được ở tầng này**:
Appwrite không có cập nhật **có điều kiện**, và schema `content_queue` không có
trường lease. Nên không thể "giành" một công đoạn một cách nguyên tử.

Đã làm: `_stale_claim()` đọc lại mục ngay trước **mọi** lần ghi, bỏ qua nếu
trạng thái đã đổi, và **fail closed** nếu chính phép đọc lại hỏng. Điều đó
**thu hẹp** cửa sổ, **không đóng** được nó.

Muốn đóng hẳn phải thêm `lease_owner`/`lease_expires` vào schema
`content_queue` — một lần migration trên Appwrite production, **cố ý không làm
trong phiên này** (ngoài phạm vi, và chạm production).

**Cho tới lúc đó: chạy MỘT tiến trình orchestrator tại một thời điểm.** Giới
hạn này đã ghi ngay trong docstring đầu tệp, không giấu trong báo cáo.

## 9. Điều KHÔNG chứng minh được ở phiên này — nói thẳng

**Chưa chạy thật trên hàng đợi production.** Worktree này không có
`server/.env.production` (tệp không được commit), nên công cụ dừng đúng như
thiết kế:

```
AppwriteConfigError: Cấu hình Appwrite chưa đủ cho kho metadata.
Cần cả bốn biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY,
APPWRITE_DATABASE_ID.
```

Đây là **dừng đúng, không phải lỗi** — cùng hành vi với
`chinese_media_watcher.py`. Nhưng nghĩa là con số "30 mục" đến từ báo cáo
2026-09-02, chưa được lệnh `--status` của phiên này xác nhận lại. Bước xác
minh thật đầu tiên khi có tệp env: `--status`, rồi `--dry-run`, rồi mới chạy
thật.

## 10. Bước kế tiếp

1. `--status` + `--dry-run` trên hàng đợi thật (cần `server/.env.production`).
2. Chạy thật một mục có `--audio` để lấy bản nháp đầu tiên qua đường tự động.
3. **Tích hợp web**: route API trên `content_queue` (`GET` danh sách/chi tiết,
   `POST` chạy lại một công đoạn) rồi màn hình quản trị. CRUD store đã có sẵn;
   `--status` đã trả đúng hình dạng dữ liệu mà giao diện cần, và `last_error`
   nay có tiền tố tên công đoạn nên giao diện phân biệt được "đang chờ" với
   "hỏng" mà không cần đoán.
4. *(Chỉ khi thật sự cần chạy song song)* thêm `lease_owner`/`lease_expires`
   vào schema `content_queue` để đóng hẳn lỗ đồng thời ở mục 8. Chưa cần
   chừng nào còn chạy một tiến trình.

## Định tuyến (router)

| Việc | Pool | Kết quả |
|---|---|---|
| Khảo cổ kho (SEARCH) | Antigravity Gemini Flash | **Thất bại 2 lần** → về native theo đúng quy tắc dự phòng của router |
| Triển khai | Native Claude | Sau khi worker ngoài thất bại thật |
| Review độc lập (ORDINARY_REVIEW) | Antigravity | Đã gửi diff |

Lần thất bại thứ nhất: `agy` headless không có quyền `command`. Lần thứ hai:
**cổng chặn credential của chính dispatcher đã chặn `--add-dir`** vì tưởng có
khoá kiểu OpenAI trong `docs/reports/cloudrun-tts-canary-plan-2026-09-06.md`.
Kiểm lại: **dương tính giả** — chuỗi khớp là `...ta`**`sk-`**`service-...`
trong một URL Cloud Run, không phải khoá. Không có bí mật nào bị lộ. Cổng chặn
đang quá rộng, nhưng đó là việc của router, ngoài phạm vi phiên này.

## Hồ sơ router toàn cục — đã QUÁ HẠN

`~/.claude/CLAUDE.md` vẫn ở `ACTIVE PROFILE: CLAUDE_CONSERVATION`, đặt
2026-08-28 với thời hạn dự kiến "~1 tuần". Hôm nay là 2026-09-07 — đã quá hạn.
Chính tệp đó dặn phải hỏi lại thay vì cứ tiết kiệm mãi. Phiên này vẫn tuân thủ
hồ sơ đang bật; cần người dùng quyết định có quay về `BALANCED` hay không.

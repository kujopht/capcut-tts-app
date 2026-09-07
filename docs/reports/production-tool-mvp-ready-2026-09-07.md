# PRODUCTION TOOL MVP — SẴN SÀNG (2026-09-07)

Đóng nốt vấn đề thời lượng nguồn bằng **cổng điều kiện**, không cắt nhỏ video
dài (đó là mục backlog riêng), rồi chạy thật và mở bề mặt web.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Nguồn 10–60 giờ | Vào thẳng hàng đợi, chiếm bản tiêu thụ duy nhất cả ngày | **Bị chặn trước khi thành việc chạy được**, kèm lý do nguyên văn |
| Ngưỡng thời lượng | Không có | **2 giờ**, đổi được qua `FAS_MAX_SOURCE_SECONDS` / `--max-seconds` |
| Cách biểu diễn "chưa đủ điều kiện" | Không có | Mọi công đoạn `SKIPPED` + `INELIGIBLE:` — **không** `DONE`, **không** `FAILED`, **không** migration schema |
| 30 mục cũ | `PENDING`, sẽ bị nhặt lên | **Đã đánh giá lại**: 30/30 bị hoãn, siêu dữ liệu giữ nguyên |
| Nguồn đủ điều kiện | 0 | **15 mục** (12 mục 22–93 phút) từ nguồn mới đã giải được `channel_id` |
| Chạy thật end-to-end | Chưa từng, trên mục thật của hàng đợi | **3 mục thật chạy trọn vẹn** → 3 bản nháp production |
| Bề mặt web | 4 route API, không có giao diện | **2 trang quản trị** dùng lại đúng 4 route đó |
| Test | 4.464 + 926 | **+35 bài mới** (4.475 + 950), xem mục 7 |

## 1. Cổng điều kiện — chặn TRƯỚC hàng đợi thực thi

`server/scraper/media_eligibility.py` trả lời đúng một câu: nguồn này có đủ
điều kiện không, và nếu không thì vì sao.

Ngưỡng mặc định **2 giờ**. Căn cứ: ASR đo trên chính máy sản xuất chạy
**0,96× thời gian thực**, nên 2 giờ nguồn ≈ 2 giờ ASR — còn nằm trong một lần
chạy không người trực.

> **Đính chính một tiền đề.** Yêu cầu ghi căn cứ là "canary 1h42 đã chứng
> minh". Kiểm lại bằng siêu dữ liệu sống: `emuWAbvnzZk` dài **102 giây**
> (1 phút 42), không phải 1 giờ 42 — và báo cáo 2026-09-02 nói thẳng điều đó
> ("khác hẳn video 1:42 trước đó"). Ngưỡng 2 giờ vẫn hợp lý trên căn cứ thông
> lượng ASR ở trên, và đổi được bằng một biến môi trường, nên đã triển khai
> đúng con số được yêu cầu — nhưng căn cứ thì khác với điều đã nêu.

**Fail closed**: không đo được thời lượng thì không cho vào. Đoán "chắc ngắn"
rồi để lọt một nguồn 22 giờ sẽ kẹt bản tiêu thụ duy nhất cả ngày.

Ba lý do loại được tách riêng vì **khác nhau về tương lai**: quá dài (chạy được
khi nâng ngưỡng / có bộ cắt), không đo được (lần sau có thể được), và **không
còn truy cập được** (không bao giờ). Gộp hai cái cuối sẽ khiến người vận hành
đi tìm một lỗi công cụ không tồn tại — đây là lỗi thật đã gặp trong phiên này,
xem mục 3.

## 2. Vì sao `SKIPPED` chứ không phải trạng thái mới

`SKIPPED` là cách diễn đạt "cố ý bỏ qua" **đã có sẵn** trong schema. Khác hẳn
`DONE` (không giả vờ là đã xong) và khác hẳn `FAILED` (không có gì hỏng).

`collect_work` chỉ lấy `PENDING`/`FAILED` nên mục như vậy **không bao giờ** bị
nhặt lên, `requeue_stage` từ chối xếp lại một công đoạn `SKIPPED`, và **không
cần migration schema Appwrite nào**.

Một mục toàn `SKIPPED` sẽ trông y hệt "đã xong" nếu chỉ nhìn trạng thái, nên
`content_queue_service._overall` trả nhãn riêng **`INELIGIBLE`**. Bảo nó là
`COMPLETE` sẽ là nói dối: không một giây nội dung nào được sản xuất.

**Hoãn là hoãn, không phải xoá**: `--recheck-ineligible` đo lại và **khôi phục
về `PENDING`** khi ngưỡng đã nâng. Nếu không có đường quay lại thì "hoãn" chỉ
là cách nói giảm của "đã xoá". Công cụ cũng **không bao giờ đóng băng** một mục
đã có tiến độ thật (có điểm dừng ASR / bản nháp / công đoạn `DONE`).

## 3. Đánh giá lại 30 mục cũ — dữ liệu sống

```
examined 30 · eligible 0 · marked_ineligible 30
ngắn nhất 10h33m39s · dài nhất 60h49m20s
```

Sau đó hàng đợi thực thi = **0 mục**; `--dry-run` của orchestrator trả
`items_examined: 0`. Siêu dữ liệu nguyên vẹn — kiểm trực tiếp một mục:
`episode_ref`, `source_url`, tiêu đề, `rights_mode` đều còn, `last_error` mang
lý do đầy đủ, và web gọi đúng tên `INELIGIBLE`.

**Một lỗi thật tìm được ở đây**: 15 mục của KK爱看 ban đầu bị ghi là "không đo
được — fail closed". Kiểm tay thì `yt-dlp` báo **"Video unavailable"** — video
đã bị gỡ, không phải lỗi công cụ. Đã tách hai trường hợp và chạy lại: 15/15 nay
ghi đúng "nguồn không còn truy cập được".

## 4. Nguồn đủ điều kiện — 15 mục

Ba kênh đang poll chỉ ra bản tổng hợp 10–60 giờ. Đã giải `channel_id` cho hai
kênh **đã có sẵn trong sổ đăng ký** nhưng chưa poll được (trang kênh là SPA nên
`WebFetch` trước đây thất bại) bằng `yt-dlp --skip-download` trên một video:

| Nguồn | channel_id | RSS | Kết quả |
|---|---|---|---|
| TePi动漫推荐 | `UCDDvjG2iJqzLA4KCBqQ3RHA` | 200, 15 mục | **15/15 đủ điều kiện** (22–93 phút) |
| KK爱看 | `UCbM7SQSOEpla-sDOkpdNouQ` | 200, 15 mục | 15/15 video đã bị gỡ |
| 天天小說動漫 | — | **404** | Bỏ trống `channel_id` theo đúng quy ước sổ đăng ký; không đoán id mới |

TePi là nguồn **đúng hình dạng** cho đường dây hiện tại: đăng theo từng tập,
không phải bản tổng hợp.

## 5. Chạy thật — 3 mục thật, không phải canary

| Mục | Bóc lời | Dịch | Phụ đề | Bản nháp |
|---|---|---|---|---|
| `cmq_11e2dbdf4b3d26eb` | 10 đoạn | 10/10 | 656 B | `nov_504ae883bed04c4b` |
| `cmq_dff3d80c1c1d937d` | 5 đoạn | 5/5 | 430 B | thật |
| `cmq_b1ab31ee3ca54617` | 4 đoạn | 4/4 | 338 B | `nov_1e1b6281251147b7` |

`render` = `SKIPPED` cho cả ba (`rights_mode=REFERENCE_ONLY`) — cổng quyền hoạt
động đúng.

**Một lỗi mạng thật đã xảy ra và máy trạng thái xử lý đúng**: mục thứ ba lỗi ở
`draft` (`WinError 10054`, kết nối bị đóng đột ngột). Bóc lời/dịch/phụ đề vẫn
giữ `DONE`, chỉ `draft` thành `FAILED`, `attempts=1`, lỗi ghi kèm tên công
đoạn. Không mất một giây ASR nào.

## 6. Đường WEB → content_queue → orchestrator

Gọi **route HTTP thật** với store trỏ vào Appwrite production:

```
GET  .../cmq_b1ab…              200 · draft=FAILED · attempts=1
POST .../cmq_b1ab…/requeue      200 · draft=PENDING · attempts=0
GET  .../cmq_b1ab…              200 · last_error="draft: CHO: đã xếp lại bởi …"
POST .../cmq_b1ab…/requeue      409 · "rights_mode=REFERENCE_ONLY —
     {"stage":"render"}               không phân phối lại media gốc."
GET  .../summary                200 · PENDING 13 · COMPLETE 2 · INELIGIBLE 45
```

Rồi chạy orchestrator: nó nhặt đúng mục vừa xếp lại và hoàn tất `draft` →
`nov_1e1b6281251147b7`, **`stages_advanced: 1`** — tức là nó **không** bóc lời
lại. Điểm dừng ASR giữ nguyên qua một lần thử lại khởi phát từ web.

Kết thúc: **3 COMPLETE · 12 PENDING · 45 INELIGIBLE · tổng 60**.

Hai trang quản trị (`/admin/content-queue` và trang chi tiết) dùng lại **đúng
bốn route đã có**, không thêm route nào. Giao diện chỉ hiện nút "Xếp lại" cho
những công đoạn server thật sự sẽ nhận, và nói rõ lý do khi không — thay vì để
người dùng bấm rồi ăn 409.

## 7. Test

```
server/tests    4.475 PASS / 0 FAIL (3 skip)   — 4.464 + 11 bài mới
scripts/tests     950 PASS / 0 FAIL (4 skip)   —   926 + 24 bài mới
web             typecheck PASS · eslint 0 lỗi (2 cảnh báo có sẵn, tệp khác)
```

Bài đáng nói nhất là bài canh gác **đọc cây cú pháp** của tầng dịch vụ web để
chặn mọi `subprocess`/thread/BackgroundTasks — kèm một bài chứng minh chính cái
canh gác đó bắt được vi phạm thật. Web xếp việc, web không chạy việc.

## 8. Việc KHÔNG làm được, nói thẳng

**Chưa chạy trọn một mục dài cỡ tập thật (22–93 phút).** Đã thử `k7-Wtoga-Ec`
(22 phút): tiến trình nền bị môi trường phiên chấm dứt giữa chừng ASR, để lại
công đoạn kẹt `RUNNING` — và `--reclaim-stale` **đã thu hồi đúng** sau đó. Đây
là giới hạn của môi trường chạy trong phiên, không phải lỗi công cụ: ASR
0,96× thời gian thực nghĩa là một tập 22 phút cần ~23 phút chạy liên tục, dài
hơn cửa sổ của một lệnh nền ở đây.

Việc còn lại là **vận hành, không phải mã**: cần một trình chạy không người
trực (Task Scheduler / dịch vụ nền) cho các mục cỡ tập. Ba mục đã chạy trọn
chứng minh đường dây đúng; cái chưa chứng minh là chạy dài không bị ngắt.

**Cắt nhỏ video dài**: mục backlog riêng, cố ý chưa làm.

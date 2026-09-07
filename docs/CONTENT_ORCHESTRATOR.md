# Content Orchestrator — hướng dẫn vận hành

Tài liệu thao tác cho `scripts/chinese_media_orchestrator.py`: bản tiêu thụ
hàng đợi `content_queue`, đẩy từng mục đi qua các công đoạn cho tới khi thành
một bản nháp (`Novel`, `state=draft`) thật.

Thiết kế đầy đủ nằm trong docstring đầu tệp — tài liệu này chỉ trả lời "làm
sao để vận hành".

## Hai tệp, hai việc khác nhau

| Tệp | Việc |
|---|---|
| `scripts/chinese_media_watcher.py` | **Phát hiện** — poll RSS kênh, ghi mục mới vào `content_queue`, mọi công đoạn `PENDING`. Không xử lý gì. |
| `scripts/chinese_media_orchestrator.py` | **Xử lý** — đọc hàng đợi, chạy tiếp từng công đoạn, ghi lại trạng thái. |

Toàn bộ logic công đoạn (ASR, dịch, SRT, dub, ghép, ship draft) nằm ở
`scripts/chinese_media_pipeline.py` và **đã đóng băng**. Orchestrator không sao
chép một dòng nào của nó — chỉ điều phối.

## Điều kiện tiên quyết

Cần `server/.env.production` có mặt trong thư mục làm việc (hoặc trỏ
`FAS_ENV_FILE` tới nó) — cùng đúng cách `chinese_media_pipeline.upload_to_r2`
và `chinese_media_watcher.py` đang lấy cấu hình. Thiếu thì công cụ **dừng ngay
với lỗi rõ ràng**, không chạy nửa vời:

```
AppwriteConfigError: Cấu hình Appwrite chưa đủ cho kho metadata.
Cần cả bốn biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY,
APPWRITE_DATABASE_ID.
```

Một worktree mới **không** tự có tệp này (nó không được commit). Đây là bước
đầu tiên phải làm trước mọi lệnh dưới đây.

Token ghi bản nháp (`FAS_HARVESTER_SERVICE_TOKEN`) lấy qua
`fanfic_credential_broker` — không đặt trong repo, không truyền qua dòng lệnh.

## Xem hàng đợi trước khi làm gì

```bash
python -m scripts.chinese_media_orchestrator --status
```

In số mục theo từng công đoạn × từng trạng thái. Chỉ đọc, không ghi gì.

## Chạy thử không ghi

```bash
python -m scripts.chinese_media_orchestrator --dry-run --limit 5
```

`--dry-run` là chế độ **lập kế hoạch**: nó kiểm tiền điều kiện rồi báo công
đoạn nào *sẽ* chạy, và **không gọi công đoạn nào cả** — không tốn một lượt ASR
hay quota dịch nào.

Chính xác về mặt tác dụng phụ: **không ghi gì** (không Appwrite, không tải lên
R2, không `POST /api/novels`). Nó **có** đọc: hỏi R2 xem điểm dừng transcript
đã có chưa, và hỏi API phụ đề công khai của YouTube. Đó là điều kiện để bản kế
hoạch nói đúng sự thật, và đều là thao tác chỉ-đọc.

`--reclaim-stale` cũng tôn trọng `--dry-run` (trước đây thì không).

Vì không biết kết quả các công đoạn sau, `--dry-run` chỉ báo tới công đoạn
chưa xong đầu tiên của mỗi mục — đúng như vậy là đủ.

## Chạy thật

```bash
# Rút vài mục làm được tới đâu hay tới đó
python -m scripts.chinese_media_orchestrator --limit 5

# Một mục cụ thể, kèm media do người vận hành cung cấp, có dub
python -m scripts.chinese_media_orchestrator \
    --item cmq_ab12cd34 --audio D:\media\ep1.wav --dub
```

## Vì sao phải tự đưa `--audio`

Công cụ này **không tải media từ YouTube/Bilibili/bất kỳ nguồn nào** — cùng
ranh giới `chinese_media_pipeline.py` tự đặt cho mình. Bước lấy media là quyết
định riêng của người vận hành cho từng ứng viên.

Nên với một mục không có phụ đề gốc và chưa được đưa `--audio`, công đoạn
`transcript` **giữ nguyên PENDING** kèm ghi chú, và **không bị cộng
`attempts`**. Nó không thất bại — nó chưa tới lượt. (Nếu đánh dấu FAILED, mục
đó sẽ dừng hẳn sau `--max-attempts` lần chạy không làm gì cả — mất việc trong
im lặng.)

Thực tế hôm nay: 0/31 ứng viên hoạt hình AI đã kiểm có track phụ đề thật, nên
gần như mọi mục đều cần `--audio`.

## Bảng trạng thái công đoạn

| Trạng thái | Nghĩa | Có chạy lại không |
|---|---|---|
| `PENDING` | Chưa tới lượt, hoặc đang chờ đầu vào người vận hành | Có |
| `RUNNING` | Đang chạy ở một tiến trình nào đó | Không — xem `--reclaim-stale` |
| `DONE` | Xong | Không |
| `SKIPPED` | **Cố ý** bỏ qua (vd `rights_mode` không cho render) | Không |
| `FAILED` | Lỗi thật, `attempts` đã cộng, `last_error` đã ghi | Có, tới `--max-attempts` |

`attempts` là ngân sách của **cả mục** (schema chỉ có một trường), nên nó được
đọc là "số lần thất bại **liên tiếp**": một công đoạn `DONE` đặt lại về 0. Một
`SKIPPED` thì **không** — coi một quyết định chính sách là tiến bộ sẽ hồi sinh
mãi mãi một mục đã chết hẳn.

`last_error` cũng là trường của cả mục, nên nó được **gắn tên công đoạn**
(`"translation: …"`) và chỉ bị xoá bởi chính công đoạn đó — nếu không, việc
đánh dấu `render=SKIPPED` sẽ xoá mất lỗi dịch và để lại một mục chết không còn
dấu vết chẩn đoán.

Một mục đã hết lượt thì mọi công đoạn của nó bị bỏ qua, **kể cả** các bước rẻ
như nhặt lại điểm dừng ASR. Muốn cho nó một cơ hội nữa: nâng `--max-attempts`
(không cần sửa dữ liệu bằng tay).

Một công đoạn `FAILED` **vẫn được chọn lại** ở lần chạy sau chừng nào `attempts`
chưa hết — kể cả khi nó là công đoạn cuối và mục không còn công đoạn `PENDING`
nào.

## ASR không bao giờ chạy lại

Ngay khi ASR xong, transcript (tiếng Trung + timestamp) được ghi lên R2 tại
`transcripts/svc_harvester/<item_id>.json` và khoá được lưu vào
`transcript_key`. Mọi lần chạy sau **bỏ qua ASR hoàn toàn** cho mục đó.

Đây là lý do tồn tại của cả tệp orchestrator: docstring của
`translate_zh_to_vi()` ghi lại giá phải trả trước đây — bốn lần nối lại việc,
mỗi lần tốn một lượt ASR mới ~35-90 phút, vì transcript chưa bao giờ có điểm
dừng trên đĩa.

Công đoạn dịch ghi đè lên **cùng khoá đó** (thêm `vi_text`, giữ nguyên
`zh_text`), nên một lần dịch hỏng giữa chừng vẫn nối lại được mà không đụng
tới ASR.

## Cổng quyền — không có đường vòng

Công đoạn `render` chỉ chạy với `rights_mode="REHOST_ALLOWED"`. Mọi giá trị
khác → `SKIPPED` kèm lý do. **Không có biến môi trường hay cờ dòng lệnh nào
nới lỏng được điều này** — nó nằm trong mã, có bài test bảo vệ.

Cả 30 mục thật đang nằm trong hàng đợi đều là `REFERENCE_ONLY`, nên `render`
sẽ `SKIPPED` cho tất cả. Đó là đúng, không phải lỗi.

Kể cả với `REHOST_ALLOWED`, orchestrator vẫn **không** tự render: đó là bước
người vận hành chạy tay (`compose_with_source` rồi `archive_final_render`).

## Chạy MỘT tiến trình tại một thời điểm

Công cụ này an toàn khi một tiến trình chạy. Nó **không** an toàn khi hai
tiến trình cùng rút một hàng đợi: Appwrite không có cập nhật *có điều kiện* và
schema `content_queue` chưa có trường lease, nên không thể "giành" một công
đoạn một cách nguyên tử. Đã đọc lại mục ngay trước khi ghi `RUNNING` để thu
hẹp cửa sổ — nhưng không đóng được nó.

Đóng hẳn cần thêm `lease_owner`/`lease_expires` vào schema (một lần migration
trên Appwrite production, chưa làm).

## Thu hồi mục kẹt

Một tiến trình chết giữa chừng để lại công đoạn ở `RUNNING` mãi. Schema không
có lease, nên mốc tuổi là `updated_at`:

```bash
python -m scripts.chinese_media_orchestrator --reclaim-stale 120
```

Đặt lại về `PENDING` mọi công đoạn `RUNNING` cũ hơn 120 phút. **Chỉ chạy khi
được gọi tường minh** — tự động thu hồi sẽ cướp việc của một tiến trình đang
thực sự chạy. Mục có `updated_at` không đọc được thì **không bao giờ** bị thu
hồi.

Thêm `--dry-run` để chỉ xem danh sách sẽ thu hồi mà không đổi gì:

```bash
python -m scripts.chinese_media_orchestrator --reclaim-stale 120 --dry-run
```

## ASR không bao giờ chạy lại — kể cả sau khi tiến trình chết

Có một khe cửa sổ giữa lúc transcript đã lên R2 và lúc `transcript_key` được
ghi vào Appwrite. Chết đúng khe đó sẽ để lại một object **đúng** trên R2 mà
hàng đợi không biết.

Vì khoá là tất định theo `item_id`, công cụ hỏi R2 xem object đã có chưa
**trước khi** chạy ASR, và nhặt lại nếu có. Không mất 35–90 phút vô ích.

## Dịch thiếu không phải là xong

Công đoạn dịch chỉ `DONE` khi **toàn bộ** đoạn đã có bản tiếng Việt. Thiếu dù
một đoạn → `FAILED`, nhưng **phần đã dịch vẫn được lưu** để lần sau dịch tiếp.

Nếu đánh `DONE` khi còn thiếu, công đoạn phụ đề sẽ lặng lẽ loại các đoạn chưa
dịch và cho ra một bản phụ đề thiếu nội dung — mà công đoạn dịch thì không bao
giờ chạy lại nữa.

## Test

```bash
python -m unittest scripts.tests.test_chinese_media_orchestrator
```

44 bài, không Appwrite, không R2, không HTTP — store là bản giả trong bộ nhớ,
mọi hàm công đoạn đều mock.

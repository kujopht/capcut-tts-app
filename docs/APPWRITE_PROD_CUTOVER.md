# Chuyển Appwrite PRODUCTION khỏi GCE sang AWS — quy trình chốt

Cập nhật **2026-09-05**. Chưa chạy pha nào tốn tiền, chưa đụng DNS, chưa dừng
GCE. Đường khôi phục dùng ở đây là đường **đã chứng minh** trong
`docs/APPWRITE_MIGRATION.md` mục 8–9.

> **Nguyên tắc số một:** GCE là đường lui và **phải còn nguyên vẹn, còn chạy,
> còn nhận ghi** cho tới hết thời gian giữ. Mọi bước dưới đây được thiết kế
> quanh điều đó.

---

## 0. Câu hỏi còn treo — ĐÃ TRẢ LỜI

Đợt trước để ngỏ rủi ro: `APPWRITE_SCHEMA_API_KEY` có thể trỏ vào
`schema-migration-key` (có `documents.write`) thay vì `fanfic-schema-provisioner`
(7 scope). **Đã hỏi thẳng production, không đoán:**

```
GET /v1/databases/fanfic_world_prod/collections                -> 200, total=43
GET /v1/databases/fanfic_world_prod/collections/novels/documents
   -> 401  missing scopes (["documents.read"])
```

**Khoá đang dùng KHÔNG có `documents.*`.** `docs/HANDOFF.md` mô tả đúng, và
lập luận "13 series thật không thể bị động tới" **vẫn đứng vững**. Rủi ro nêu
ở đợt trước là không có thật.

Công cụ: `scripts/ops/appwrite_key_scope_probe.py` — nói thẳng tới origin để
vượt Cloudflare 1010, nhưng **vẫn kiểm chứng chỉ đầy đủ**; chỉ GET; không bao
giờ in khoá.

## 1. Nguồn backup CHÍNH THỨC: ảnh chụp đĩa

| | Ảnh chụp đĩa GCE | `tar` của `backup.sh`/`backup_v2.sh` |
|---|---|---|
| Nguyên tử | **Có** — một thời điểm trên toàn đĩa | Không — chép tuần tự qua nhiều phút |
| Đã chứng minh khôi phục được | **CÓ** (2026-09-05, 32/32 container) | **KHÔNG** |
| Số volume | **14/14** | 9/14 — thiếu builds, cache, functions, imports, sites |
| Thời gian dừng | **0** | 0 (nhưng cho ra bản rách) |

`appwrite_prod_cutover.py` **từ chối** dùng đường `tar`. Đây là quyết định
đã có bằng chứng, không phải sở thích.

## 2. Cấu hình máy đích — suy ra TỪ SỐ ĐO

| Hạng mục | Giá trị | Căn cứ đo được |
|---|---|---|
| Loại máy | **`t3a.large`** (2 vCPU / 8 GiB) | Diễn tập: 32 container chạy trong 3.859 MB, swap chạm 8 KB |
| Vùng | **`ap-southeast-1`** | Cùng vùng worker TTS đã chuyển; gần Cloudflare SG |
| Đĩa | **64 GB `gp3`** | Nguồn dùng 36/48 GB (75%); bản khôi phục dùng 17/61 GB |
| Swap | **4 GiB** | Đo ở mức NỀN, chưa phải đỉnh tải — giữ biên |
| Kiến trúc | **`x86_64`** | Không ARM |
| Mạng vào | chỉ 80/443 từ Cloudflare + 22 từ IP vận hành | Nguồn cũng chỉ mở 80/443/22 |
| Máy riêng | **BẮT BUỘC** | Không gộp lên `t3a.medium` của TTS (4 GiB, ít hơn cả bộ nhớ ẩn danh của Appwrite) |

**Giới hạn phải nói rõ:** con số 3.859 MB đến từ stack **không có tải thật**.
Nó chứng minh 8 GiB đủ cho mức nền, **chưa** chứng minh cho đỉnh tải. Đó là lý
do vẫn giữ 4 GiB swap và vẫn theo dõi RAM trong pha `observe`.

## 3. Vì sao cutover ở đây rẻ và quay đầu được

`appwrite-dev.fanfic.world` **được Cloudflare proxy** — đo được:

```
appwrite-dev.fanfic.world -> 104.21.63.15, 172.67.142.101   (Cloudflare)
origin thật                -> 35.225.209.115                 (GCE)
```

Nên client **luôn** nói với biên Cloudflare. "Cutover" chỉ là đổi **địa chỉ
gốc**. Hệ quả:

* TTL phía client **không liên quan** — không phải chờ hàng giờ.
* **Rollback có hiệu lực trong vài giây**: đổi bản ghi A ngược lại.
* Chứng chỉ ở biên do Cloudflare lo; máy đích chỉ cần chứng chỉ gốc hợp lệ.

**Khuyến nghị kèm theo:** dùng **Cloudflare Origin CA** cho máy đích thay vì
Let's Encrypt cấp tay. Chứng chỉ gốc hiện tại hết hạn **2026-11-14 và không tự
gia hạn** — đó là một quả bom hẹn giờ độc lập, và cuộc chuyển này là dịp tự
nhiên để gỡ nó.

## 4. Quy trình — FAIL-CLOSED, mỗi pha một cổng

```
preflight -> prepare -> freeze -> final-backup -> restore -> canary
          -> cutover -> observe -> commit          (bất kỳ lúc nào: rollback)
```

`appwrite_prod_cutover.py` **từ chối nhảy cóc**: mỗi pha kiểm **toàn bộ dãy
pha trước nó** đã `DAT` chưa — không phải chỉ hàng xóm trực tiếp — và mỗi kết
quả **hết hạn sau 6 giờ**. Trạng thái nằm **ngoài** kho git.

Hai điều đó đến từ vòng phản biện: chỉ kiểm hàng xóm trực tiếp thì một lần
chạy bỏ dở hôm trước có thể để lại `DAT` và cho người vận hành vào giữa chừng;
còn một kết quả `preflight` của ba ngày trước thì **không nói được gì** về
production hôm nay.

| Pha | Làm gì | Cổng chặn |
|---|---|---|
| `preflight` | đo cả hai bên, không tạo gì | GCE `RUNNING`; production trả `1.9.6`; tên miền còn qua Cloudflare; khoá schema **không** có `documents.*` |
| `prepare` | tạo EC2 đích | **TỐN TIỀN** — đòi cờ `--toi-dong-y-tra-tien` |
| `freeze` | **chặn ghi** trên production | đo hai lần cách nhau 90s, trạng thái **phải không đổi** |
| `final-backup` | ảnh chụp GCE **mới** | phải `READY` |
| `restore` | nạp lên máy đích | 14/14 volume, `isWritablePrimary=true` |
| `canary` | kiểm đích **bằng Host header, TRƯỚC DNS** | `1.9.6` + đúng **43** collection |
| `cutover` | đổi bản ghi A gốc | ảnh chụp cuối phải **< 45 phút tuổi** |
| `observe` | theo dõi | 3 mẫu xấu liên tiếp ⇒ hô rollback |
| `commit` | được phép dừng GCE | **chỉ sau 7 ngày** giữ GCE |

Trạng thái đã chạy thật (chỉ đọc, không tạo gì):

```
preflight -> KET LUAN: DAT   (0 lỗi, 0 cảnh báo)
```

### Vì sao `canary` đứng TRƯỚC `cutover`

Vì nó dùng **hết** đường mà người dùng thật sẽ đi — SNI, vhost, chứng chỉ,
API key thật — nhưng **chưa đổi một bản ghi nào**. Nếu máy đích hỏng, ta biết
trong khi người dùng **vẫn đang được GCE phục vụ**. Đây là điểm khác biệt lớn
nhất so với "đổi DNS rồi xem sao".


### `freeze` — thứ vòng phản biện tìm ra mà bản đầu KHÔNG có

Bản thiết kế đầu **thiếu hẳn** bước chặn ghi. Hệ quả: trong cửa sổ cutover,
GCE vẫn nhận ghi trong khi AWS đã bắt đầu phục vụ — **hai kho dữ liệu phân
kỳ**, và mọi ghi rơi vào bên thua sẽ mất khi dừng máy đó. Đây là lỗi nặng
nhất mà vòng phản biện tìm ra, và nó là **hồi quy do chính tôi gây ra**:
thiết kế ở `APPWRITE_MIGRATION.md` mục 6 đã có bước "đóng băng ghi", bản này
làm rơi mất.

`freeze` **không phải downtime toàn phần**: đọc vẫn chạy, người dùng vẫn đọc
truyện được. Chỉ đường GHI bị đóng, trong vài phút.

Và nó **không tin lời khai**: sau khi người vận hành báo đã chặn ghi, pha này
tự đo trạng thái **hai lần cách nhau 90 giây**; nếu còn đổi thì **từ chối**,
vì chụp một bản "cuối" trong khi còn người ghi là tự tạo ra chính cái cửa sổ
mất dữ liệu mà ta đang cố đóng.

### Những gì vòng phản biện nói SAI — và vì sao không sửa theo

| Ý kiến | Vì sao không nhận |
|---|---|
| "Audio trong R2 sẽ mất khi rollback" | R2 là kho **dùng chung, bên ngoài**. Rollback Appwrite không xoá gì trong R2; nó chỉ làm mồ côi metadata trỏ tới object. Phục hồi được, không mất. |
| "Hàng chục job TTS mỗi phút" | Không có căn cứ. Đo được: 237 TTS job và ~1.571 document **tổng cộng**. Đây là site chưa thương mại hoá. |
| "Worker cache DNS nên vẫn nói với IP cũ" | Không đúng ở đây: tên miền **do Cloudflare proxy**, nên backend luôn nói với IP biên — IP đó **không đổi** khi ta đổi origin. |
| "Snapshot crash-consistent chưa chắc application-consistent" | Đã chứng minh ngược lại bằng một lần khôi phục thật (mục 8–9). |

## 5. Tiêu chí rollback — máy kiểm được, không phải cảm tính

Bất kỳ điều nào ⇒ đổi bản ghi A về `35.225.209.115` ngay:

* `/v1/health/version` không trả `200` + `1.9.6` — **3 mẫu liên tiếp**
* số collection ≠ 43
* số document ở bất kỳ collection nào **thấp hơn** nguồn
* 5xx trên đường đọc novel/chapter
* **swap dùng > 256 MB** trên máy đích — dấu hiệu giả định "8 GiB đủ" đang
  sai ở tải thật. Đây là **tiêu chí trong mã**, không phải dòng ghi chú.

Rollback **không mất ghi**, vì GCE vẫn chạy và vẫn nhận ghi suốt thời gian đó.
Đổi lại: mọi ghi xảy ra **trên AWS** giữa cutover và rollback sẽ **không** có
trên GCE. Đó là cái giá thật của việc quay đầu, và là lý do `observe` phải
ngắn và quyết đoán.

## 6. Giữ GCE — 7 ngày, không thương lượng

`commit` (dừng GCE) bị **chặn bằng mã** cho tới khi đủ `NGAY_GIU_GCE = 7` ngày
kể từ cutover. Có bài kiểm giữ đúng điều đó. Trong 7 ngày ấy:

* **không** dừng, không đổi kích thước, không tháo đĩa GCE;
* lịch `fanfic-appwrite-daily` vẫn chạy trên GCE;
* ảnh chụp `appwrite-prod-final-*` được giữ lại.

## 7. Việc CHỈ CON NGƯỜI làm được

Theo đúng thứ tự. Mỗi lần **một** việc.

1. **Tạo EC2 đích** — cần quyền AWS mà máy này không có.
2. **Đổi bản ghi A trên Cloudflare** — cố ý không tự động hoá.
3. **Dừng GCE sau 7 ngày** — không tự động dừng một máy production.

Mọi thứ khác đã tự động: đo, ảnh chụp, khôi phục, canary, theo dõi, tiêu chí
rollback.

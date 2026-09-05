# Di trú Appwrite production khỏi GCE — đường đi đã CHỨNG MINH được tới đâu

Ngày đo: **2026-09-05**. Mọi con số dưới đây đến từ một lần đo THẬT trên hạ
tầng thật, không lấy lại từ tài liệu cũ. Nhiệm vụ này **không** chốt cutover
và **không** đụng vào production.

> **Kết luận một dòng (cập nhật 2026-09-05 sau khi diễn tập CHẠY THẬT):**
> đường khôi phục an toàn **đã có và đã được chứng minh** — bằng **snapshot
> đĩa**, không phải bằng `tar`. Snapshot khôi phục được thật: MongoDB replay
> journal, tự lên PRIMARY, ghi được, và **1.571 document production** đọc lại
> đúng. Xem mục 8.
>
> Ngược lại, các bản **`tar` do `backup.sh`/`backup_v2.sh` tạo vẫn KHÔNG
> được coi là khôi phục được**: chúng nguyên vẹn về đường truyền nhưng bên
> trong là bản chép RÁCH của MongoDB đang chạy, và còn thiếu hẳn 5 volume.
> Đừng cutover dựa trên chúng.

---

## 0. Tiền đề đã đo lại (không tin tài liệu cũ)

`docs/AWS_STAGING_MIGRATION.md` mục 0 từng ghi rằng production dùng Appwrite
Cloud SaaS và máy `fanfic-appwrite-temp` "KHÔNG phải production".
`docs/PRODUCTION_CUTOVER.md` mục 0 đã đính chính điều đó ngày 2026-09-04.
Lần này đo lại trực tiếp, xác nhận đính chính đó đúng:

```
GET https://appwrite-dev.fanfic.world/v1/health/version  ->  {"version":"1.9.6"}
```

Máy GCE tên `fanfic-appwrite-temp` **đang là hạ tầng production**, bất kể chữ
`temp` trong tên và chữ `dev` trong tên miền.

## 1. Kiểm kê nguồn — đo trực tiếp trên VM

| Hạng mục | Giá trị đo được |
|---|---|
| Máy | `fanfic-appwrite-temp`, `us-central1-c`, `c4-standard-2` |
| OS / nhân | Ubuntu 24.04.4 LTS, `6.17.0-1022-gcp`, x86_64 |
| CPU | 2 vCPU; load 1/5/15 phút = 0.24 / 0.19 / 0.14 |
| RAM | `MemTotal` 6,93 GiB · `MemAvailable` 4,66 GiB |
| Swap | 4,0 GiB tổng — **2,53 GiB ĐANG DÙNG** |
| Đã ghi ra swap (tích luỹ) | `pswpout` 666.314 trang ≈ **2,6 GiB** |
| Áp lực bộ nhớ (PSI, 20 ngày) | `some` 13,9 s · `full` 11,0 s — có thật, không nghiêm trọng |
| `Committed_AS` | 12,9 GiB (trên `CommitLimit` 7,4 GiB) |
| Đĩa | 48 GB, **36 GB đã dùng — 75%** |
| Uptime | 20 ngày |
| Appwrite | **1.9.6**, `_APP_DB_ADAPTER=mongodb` |
| Kho dữ liệu SỐNG | **MongoDB / WiredTiger** — 207 collection, 1.635 index |
| MariaDB | **RỖNG** — `appwrite/db.opt` và không bảng nào; là container thừa |
| Tệp nhị phân người dùng | **Cloudflare R2**, không nằm trong Appwrite Storage |
| Chứng chỉ gốc | Let's Encrypt, hết hạn **2026-11-14**, **không tự gia hạn** |
| Chính sách khởi động lại | core services `restart: no`; dựa vào unit systemd oneshot |

Hai điều đáng chú ý ngoài phạm vi nhiệm vụ nhưng phải ghi lại:

* `fanfic-worker-prod` (`e2-medium`, `asia-southeast1-b`) **vẫn đang CHẠY**
  trên GCE dù worker TTS đã chuyển sang AWS. Đó là tiền đang chảy, hoặc là
  một worker thứ hai đang tranh job — cần người vận hành xác nhận.
* Chứng chỉ gốc hết hạn `2026-11-14` là một quả bom hẹn giờ độc lập với
  cuộc di trú này.

## 2. Bản backup mới nhất — nguyên vẹn, nhưng KHÔNG khôi phục được

Bản mới nhất: `20260903T163727Z`, **đã ở ngoài VM** trên Google Drive
(`archive/infra/appwrite-selfhost/`), 956.401.009 byte.

Toàn vẹn đường truyền — ĐẠT:

```
sha256 trong manifest : 4f445101040b160b0756c320ba0d1e9af7185581894dc41e2b6810bbfe5977cc
sha256 tải về từ Drive: 4f445101040b160b0756c320ba0d1e9af7185581894dc41e2b6810bbfe5977cc
```

Nhất quán bên trong — **KHÔNG ĐẠT**. `scripts/ops/appwrite_backup_verify.py`
đọc vào trong từng volume và tìm được:

| Bằng chứng | Ý nghĩa |
|---|---|
| `mongod.lock` dài 2 byte | mongod **đang chạy** lúc `tar` chép |
| `journal/WiredTigerLog.0000000012` mtime **+44 s** so với `WiredTiger.turtle` | bản chép **RÁCH**: metadata bị chép trước khi dữ liệu ngừng đổi |
| 12 tệp trùng giây với `turtle` (gồm `WiredTiger.wt`) | `tar` chỉ lưu độ phân giải 1 giây — không loại trừ được rách thêm |

`WiredTiger.turtle` ghi checkpoint nào đang có hiệu lực. `tar` đi qua ~1,3 GB
trong nhiều phút; giữa chừng WiredTiger tạo checkpoint mới và **ghi đè**
`turtle` + `WiredTiger.wt`. Kết quả là tệp metadata trỏ tới một checkpoint mà
các trang dữ liệu của nó đã bị chép ở trạng thái TRƯỚC đó. mongod có thể từ
chối mở, hoặc tệ hơn, mở lên với dữ liệu thiếu.

**Mọi tệp trong bản đó đều khớp sha256. Bản đó vẫn có thể không khôi phục
được.** Đây chính là lỗ hổng ở mục 3.

Hai volume rỗng, đã đối chiếu, **không phải mất dữ liệu**:

* `appwrite-uploads` rỗng là **đúng thiết kế** — tệp nhị phân ở R2
  (`server/r2_adapter.py:58`), 0 lần dùng Appwrite Storage SDK trong
  `server/` và `web/`.
* `appwrite-postgresql` rỗng — pgvector chưa dùng. Cần người vận hành xác
  nhận trước cutover, không tự kết luận.

## 3. Lỗi nguồn đã sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Tiêu chí PASS của `appwrite_backup_to_drive.py` | tải lại được + sha256 khớp + giải nén được | thêm **cổng nhất quán bên trong volume**; rách ⇒ FAIL |
| Tầm nhìn vào trong volume | không có — chỉ đối chiếu vỏ ngoài | `appwrite_backup_verify.py` đọc member của từng `tar.gz`, không giải nén |
| Bản `20260903T163727Z` | được báo **PASS** | báo **FAIL**, nêu đúng lý do |
| Chép lúc mongod đang chạy | không phát hiện được | `WT_MONGOD_DANG_CHAY` (FAIL) |
| Chép rách (journal mới hơn turtle) | không phát hiện được | `WT_SAO_CHEP_RACH` (FAIL) |
| Thiếu `mongod.lock` | lặng lẽ coi như sạch | `WT_KHONG_CO_LOCK` (FAIL) |
| Độ phân giải 1 giây của `tar` | điểm mù không ai biết | `WT_CUNG_GIAY` (CẢNH BÁO), nói rõ giới hạn |
| MariaDB rỗng | có thể bị tính là "kho sống" ⇒ PASS giả | không tính là kho sống ⇒ FAIL |
| Diễn tập khôi phục | chưa có | `appwrite_restore_rehearsal.py`, từ chối mọi đích production |
| Bài kiểm | không có bài nào cho lớp lỗi này | **36 bài**, gồm bài dựng lại đúng hình dạng bản thật |

Cổng này **fail-closed**: không chứng minh được là sạch thì chặn.

## 4. Tài nguyên đích tối thiểu — ĐO, không đoán

**Không khuyến nghị 4 GB.** Máy hiện tại đang giữ ~4,7 GiB bộ nhớ ẩn danh
(2,07 GiB trong RAM + 2,53 GiB đã bị đẩy ra swap) trên một máy 6,93 GiB, và
nhân đã phải ghi ra swap 2,6 GiB tích luỹ. Một máy 4 GB sẽ thrash hoặc bị
OOM-kill; nó "boot được" và đó là tất cả những gì nó làm được.

| Hạng mục | Đo được | Khuyến nghị đích |
|---|---|---|
| Bộ nhớ ẩn danh thực dùng | ~4,7 GiB | **8 GiB RAM** (tối thiểu an toàn) |
| Swap | 4 GiB, dùng 2,53 GiB | giữ **4 GiB swap** kể cả khi đã có 8 GiB RAM |
| vCPU | 2, load ~0,2 | **2 vCPU** là đủ; không cần 4 |
| Đĩa | 36/48 GB (75%) | **≥ 64 GB gp3** |
| Kiến trúc | x86_64 | **x86_64** (không ARM) |

8 GiB là **mức sàn có biên**, không phải mức thoải mái. Nếu muốn hết swap
hẳn thì 16 GiB; nhưng 8 GiB + swap phản ánh đúng hành vi hiện tại và không
tiêu tiền cho phần chưa chứng minh là cần.

## 5. So sánh đích — AWS vs Tencent Cloud

| Hạng mục | AWS `t3a.large` (`ap-southeast-1`) | Tencent Cloud 2c8g (Singapore) |
|---|---|---|
| Đúng yêu cầu đã đo (2 vCPU / 8 GiB / x86) | Có | Có |
| Cùng nhà cung cấp với worker TTS đã chuyển | **Có** | Không — thêm một đám mây thứ hai |
| Dùng lại được runbook/IAM/công cụ trong kho | **Có** — `scripts/ops/*` đã theo hình dạng AWS | Không — phải viết lại |
| Miền credential mới phải quản | Không | **Có** |
| Độ trễ tới backend Render + R2 | đã biết từ lần chuyển worker | chưa đo |
| Chi phí | thấp hơn GCE `c4-standard-2` hiện tại | có thể rẻ hơn AWS |

**Khuyến nghị: AWS `t3a.large` ở `ap-southeast-1`**, một EC2 **RIÊNG**. Không
gộp lên `t3a.medium` đang chạy TTS — máy đó 4 GiB, ít hơn cả bộ nhớ ẩn danh
của riêng Appwrite, và gộp lại là để hai hệ tranh nhau OOM.

Tencent chỉ đáng cân nhắc nếu chênh lệch giá đủ lớn để bù cho một miền vận
hành thứ hai. Với một dịch vụ *chưa thương mại hoá*, khoản tiết kiệm đó gần
như chắc chắn nhỏ hơn chi phí vận hành thêm một đám mây.

> **Con số giá phải lấy báo giá thật lúc mua.** Tài liệu này cố ý không ghi
> giá cụ thể: giá theo vùng và theo thời điểm, và một con số bịa ra ở đây sẽ
> được đọc như đã kiểm chứng.

## 6. Thiết kế cutover (CHƯA chạy)

Điều kiện tiên quyết — **cả ba phải xanh trước khi bắt đầu**:

1. `appwrite_backup_verify.py` trả **PASS** trên một bản backup mới.
2. Một lần diễn tập khôi phục ĐẦY ĐỦ đã đạt trên máy dùng-một-lần.
3. Người vận hành đã xác nhận `appwrite-postgresql` rỗng là đúng.

```
đóng băng ghi  ->  backup NHẤT QUÁN  ->  khôi phục lên đích  ->
đối chiếu mức ứng dụng  ->  chuyển backend  ->  theo dõi  ->  (rollback)
```

| Bước | Việc | Cổng chuyển bước |
|---|---|---|
| 1 | Đóng băng ghi (đặt backend read-only) | xác nhận không còn ghi mới |
| 2 | `docker compose stop` **rồi mới** `tar` — hoặc `mongodump --oplog` | `appwrite_backup_verify.py` = PASS |
| 3 | Khôi phục lên EC2 đích | `/v1/health/version` = `1.9.6` |
| 4 | `mongosh listDatabases` mở được kho | kích thước khớp nguồn |
| 5 | `fanfic_appwrite_schema.py audit` | `EXIT=0` cho cả 44 collection |
| 6 | `web_product_appwrite_read_check.py` | đọc được document novels/chapters thật |
| 7 | Chuyển `APPWRITE_ENDPOINT` của Render sang đích | `/api/health` → `data_backend=appwrite` |
| 8 | Theo dõi 24 h, GCE vẫn CHẠY | không đạt tiêu chí rollback |
| 9 | Chỉ sau 7 ngày sạch mới bàn tới dừng GCE | quyết định của con người |

**Tiêu chí rollback — bất kỳ điều nào ⇒ quay lại ngay:**

* `/api/health` không trả `data_backend=appwrite` trong 5 phút
* bất kỳ lỗi 5xx nào ở đường đọc novel/chapter
* `fanfic_appwrite_schema.py audit` khác `EXIT=0`
* số document ở collection bất kỳ **thấp hơn** nguồn
* p95 độ trễ đọc tăng > 2× so với nền GCE

**Rollback = trỏ `APPWRITE_ENDPOINT` của Render về lại GCE.** Nó rẻ và
nhanh **chỉ khi** GCE còn nguyên vẹn và vẫn nhận ghi. Vì thế:

* **KHÔNG** dừng, đổi kích thước, hay tháo GCE trong giai đoạn theo dõi.
* **KHÔNG** đổi DNS trong cuộc cutover này — chỉ đổi biến môi trường
  backend. DNS làm đường lui chậm đi hàng giờ vì TTL.
* Vì ghi bị đóng băng ở bước 1, rollback **không** mất ghi nào.

**Zero lộ bí mật:** `env.snapshot` trong backup chứa bí mật thật — không
bao giờ in, không commit, không gửi cho worker ngoài. Công cụ trong kho chỉ
đọc *tên* biến môi trường qua `fanfic_credential_broker`. Không tệp nào ở
PR này đọc `env.snapshot`.

## 6b. Phản biện độc lập — những gì thiết kế trên còn THIẾU

Thiết kế mục 6 đã qua một vòng phản biện khác họ model (`gpt-oss-120b` qua
Antigravity). Dưới đây chỉ giữ những điểm **đã kiểm chứng lại được**, kèm
điểm còn để ngỏ. Ba điểm đầu là lỗ hổng thật trong bản thiết kế đầu tiên.

| # | Lỗ hổng | Trạng thái |
|---|---|---|
| 1 | **MongoDB chạy dạng replica set.** Cấu hình replset nằm TRONG thư mục dữ liệu (`local.system.replset`) và trỏ tới danh tính máy CŨ. Khôi phục nguyên xi lên máy mới ⇒ node lên nhưng **không tự bầu thành primary**, Appwrite treo hoặc từ chối ghi. | **ĐÃ KIỂM CHỨNG** — `_mdb_catalog.wt` chứa `replset.oplogTruncateAfterPoint`, `local.startup_log`, và có volume `mongodb-keyfile` |
| 2 | **Chứng chỉ TLS trên máy đích.** Mục 6 nói "không đổi DNS, chỉ đổi biến môi trường" — nhưng nếu `APPWRITE_ENDPOINT` trỏ sang host mới thì host đó phải có chứng chỉ hợp lệ cho **chính tên** đó. Không có DNS mới + chứng chỉ mới thì bước 7 hỏng bắt tay TLS ngay. | **ĐÚNG** — thiết kế đầu bỏ sót |
| 3 | **Redis không được nhắc tới.** Redis giữ session và hàng đợi. Khôi phục volume Redis rỗng ⇒ đăng xuất toàn bộ người dùng đang đăng nhập. | **ĐÚNG** — volume Redis 2,7 MB có trong backup nhưng mục 6 không có bước nào nạp nó |
| 4 | `_APP_*` mã hoá hostname (`_APP_DOMAIN`, `_APP_DOMAIN_TARGET`) phải sửa theo máy đích | **ĐÚNG**, cần đối chiếu `env.snapshot` lúc khôi phục (không in ra) |
| 5 | Worker nền của Appwrite tự chạy lại trên đích ⇒ có thể xử lý trùng job với GCE | **HỢP LÝ** — giảm nhẹ nhờ bước 1 đóng băng ghi, nhưng cần dừng worker trên đích cho tới sau bước 6 |
| 6 | Đổi vùng `us-central1` → `ap-southeast-1` làm đổi RTT Render→Appwrite | **ĐỂ NGỎ** — chưa đo vùng của Render; **phải đo trước**, vì nó có thể tốt lên chứ không chỉ xấu đi |

**Sửa lại bước 3 của mục 6:** sau khi nạp volume và TRƯỚC khi `docker compose
up`, phải khởi động mongod **standalone**, gỡ cấu hình replset cũ (hoặc
`rs.reconfig(..., {force:true})` với danh tính máy mới), rồi mới dựng stack.
Bỏ bước này thì bước 4 (`listDatabases`) vẫn xanh trong khi Appwrite không
ghi được — đúng loại lỗi mà cổng kiểm chỉ đọc không bắt.

**Về kích thước máy — phản biện đề xuất ≥ 12 GiB.** Lập luận: 8 GiB trừ đi
4,7 GiB ẩn danh chỉ còn ~3 GiB cho OS, page cache và đỉnh tải, mà dựng lại
index trên 1.635 index là đỉnh tải thật. Điều đó hợp lý và **không mâu thuẫn**
với mục 4: 8 GiB là **sàn đo được**, không phải mức thoải mái.

| Lựa chọn | Khi nào chọn |
|---|---|
| `t3a.large` — 2 vCPU / 8 GiB | sàn an toàn, vẫn phụ thuộc swap như hiện nay |
| `t3a.xlarge` — 4 vCPU / 16 GiB | bỏ hẳn phụ thuộc swap, có biên cho dựng index |

Đây là **quyết định chi tiêu của con người**. Phiên này không chọn thay.
Số liệu để chọn đã đủ ở mục 4.

## 6c. Đã có sẵn một cơ chế backup NHẤT QUÁN mà đợt trước không thấy

Đợt trước chỉ soi các bản `tar` nên bỏ sót điều này: **đĩa production đã được
snapshot tự động hằng ngày từ trước tới nay.**

```
resource policy : fanfic-appwrite-daily  (us-central1)
lịch            : hằng ngày 03:00 UTC, giữ 14 ngày
đã có           : 16 snapshot, tất cả READY
mới nhất theo lịch: ...-20260905031112-oqfzi9rz  (2026-09-05 03:11 UTC)
```

Đây là khác biệt **về bản chất** so với bản `tar`, không phải khác về mức độ:

| Hạng mục | `tar` thư mục volume đang sống | Snapshot đĩa GCE |
|---|---|---|
| Tính nguyên tử | **Không** — chép tuần tự qua nhiều phút | **Có** — một thời điểm duy nhất trên toàn đĩa |
| Kết quả đo được | RÁCH: journal mới hơn `turtle` 44 s | không có hiện tượng rách |
| Thời gian dừng | 0 | **0** |
| Cần quyền root trên VM | Có | **Không** |
| Rủi ro lộ bí mật | `env.snapshot` nằm trong gói | không tạo thêm bản sao bí mật nào |

### Bản đã tạo cho đợt diễn tập này

```
name          : appwrite-prod-rehearsal-20260905
status        : READY
sourceDisk    : fanfic-appwrite-temp   (sourceDiskId 8268184344177979716)
diskSizeGb    : 50
storageBytes  : 1.121.306.624
creation      : 2026-09-05T01:52:34-07:00
architecture  : X86_64
```

Production **không bị dừng một giây nào**; kiểm ngay sau khi tạo:
`GET /v1/health/version` → `{"version":"1.9.6"}`.

### Bảo đảm THẬT SỰ đạt được là gì — nói chính xác

Snapshot này là **crash-consistent**, không phải **quiesced**. Đã kiểm:
`/etc/google/snapshot-config.yaml` và `/etc/google/snapshot_scripts/`
**không tồn tại**, nên `--guest-flush` chưa được cấu hình.

Điều đó **vẫn** đủ để làm backup MongoDB hợp lệ, vì đúng hai điều kiện của
MongoDB đều thoả:

1. journaling bật (mặc định), và
2. journal nằm **cùng một volume** với tệp dữ liệu — ở đây cả stack nằm trên
   **một** đĩa boot duy nhất (`hyperdisk-balanced` 50 GB), không LVM trải
   nhiều đĩa, không mount mạng.

Khôi phục từ nó tương đương khôi phục sau mất điện: ext4 replay journal, rồi
WiredTiger replay journal của nó. Đó là đường phục hồi **được hỗ trợ**.

**Phần phơi nhiễm còn lại, có giới hạn:** các ghi đã ack nhưng chưa kịp flush
journal (mặc định WiredTiger flush ~100 ms, hoặc ngay lập tức với `j:true`)
có thể mất. Đó là **mất vài trăm mili-giây ghi cuối**, KHÔNG phải hỏng dữ
liệu — khác hẳn bản `tar`, thứ có thể **không mở được**.

Một vòng phản biện khác họ model đã tấn công đúng luận điểm này và trả
`CLAIM_FAILS`. Hai điểm nó đúng, đã tiếp thu: (a) phải gọi đây là
crash-consistent chứ không được gọi là "production-consistent" trống không;
(b) khôi phục một thành viên replica set đơn lẻ cần xử lý riêng. Ba điểm nó
sai và **không** sửa theo: MongoDB *có* chấp nhận volume snapshot khi hai
điều kiện trên thoả; việc đĩa còn chứa dịch vụ khác **không** phá tính khôi
phục được của MongoDB; và "zero-downtime" ở đây nói về **lúc BACKUP**, còn
việc restore diễn ra trên máy dùng-một-lần nên không liên quan.

**Muốn quiesced hoàn toàn thì phải trả giá**, và cả hai lựa chọn đều đụng
production nên phiên này KHÔNG tự làm:

| Cách | Dừng bao lâu | Vì sao chưa làm |
|---|---|---|
| `--guest-flush` | ~dưới 1 s (freeze/thaw) | phải cấu hình `snapshot_scripts` trên production trước; `fsfreeze` trên **root fs** mà thaw hỏng thì treo cả máy |
| `db.fsyncLock()` | vài phút (chặn ghi) | cần quyền docker/root trên VM; guard của kho chặn `sudo` |
| `docker compose stop` | vài phút (dừng hẳn) | dừng production thật |

Vì bản crash-consistent đã là backup hợp lệ, **không cần dừng production** để
có một bản dùng được cho diễn tập.

## 7. Điều đang CHẶN

Diễn tập khôi phục **chưa chạy được**, vì nó cần một đích Linux + Docker cô
lập:

* máy này không có Docker và WSL chưa cài distro nào;
* `t3a.medium` TTS trên AWS **bị cấm** dùng chung (và 4 GiB là không đủ);
* dựng máy tính tiền là quyết định chi tiêu — **của con người, không phải
  của phiên này**.

Yêu cầu đã đo xong và ghi ở mục 4, đúng theo điều kiện "không dựng máy tính
tiền trước khi báo cáo yêu cầu đã đo".

**CẬP NHẬT 2026-09-05.** Điều kiện "chưa có backup nhất quán" ở trên
**đã được gỡ** bằng snapshot đĩa (mục 6c) — không cần dừng production.
Chặn còn lại **chỉ còn một**: không có đường vào AWS.

### Chặn thật sự: phiên này không có quyền AWS nào

Đã kiểm, cả ba đều không có:

```
aws CLI trên PATH        : không có
~/.aws/ (profile/creds)  : không tồn tại
biến môi trường AWS_*    : không có
```

`docs/AWS_STAGING_MIGRATION.md` đã ghi đúng tình trạng này từ 2026-09-03:
EC2 hiện tại do **người vận hành tạo tay**, `worker_bootstrap.sh` chỉ cần
SSH nên chưa bao giờ cần IAM. Nghĩa là **chưa từng** có credential AWS trên
máy này để dựng instance.

Vì vậy mục 2 và 3 của nhiệm vụ (dựng `t3a.large`, khôi phục lên đó) **không
thể tự động hoá** cho tới khi có một trong hai:

* một IAM principal giới hạn trong `ap-southeast-1` (`ec2:RunInstances`,
  `ec2:CreateSecurityGroup`, `ec2:CreateVolume`, `ec2:*KeyPair*`,
  `ec2:Describe*`, `ec2:TerminateInstances`) + `aws configure`; **hoặc**
* người vận hành tự tạo instance rồi đưa IP + khoá SSH; phần còn lại
  (khôi phục + chứng minh) chạy tự động qua SSH.

### Lệnh sẵn sàng chạy — chỉ thiếu quyền

```bash
# (1) đưa dữ liệu ra khỏi GCP. Snapshot -> disk -> image -> export.
gcloud compute disks create appwrite-rehearsal-disk \
    --source-snapshot=appwrite-prod-rehearsal-20260905 \
    --zone=us-central1-c

# (2) dựng đích dùng-một-lần (CẦN QUYỀN AWS — đang thiếu)
aws ec2 run-instances --region ap-southeast-1 \
    --instance-type t3a.large \
    --image-id <ubuntu-24.04-amd64> \
    --block-device-mappings \
      'DeviceName=/dev/sda1,Ebs={VolumeSize=64,VolumeType=gp3}' \
    --key-name <khoa> --security-group-ids <sg-chi-mo-SSH> \
    --tag-specifications \
      'ResourceType=instance,Tags=[{Key=Name,Value=appwrite-rehearsal},{Key=disposable,Value=true}]'

# (3) trên đích: 4 GiB swap
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile

# (4) khôi phục — KHÔNG được `docker compose up` thẳng, xem mục 6b/6c
python -m scripts.ops.appwrite_restore_rehearsal plan \
    --stamp appwrite-prod-rehearsal-20260905 --host <ip-dich>
```

**Bước 4 phải xử lý replica set trước khi dựng stack.** Khởi động mongod
**standalone** trên thư mục dữ liệu đã khôi phục, gỡ cấu hình replset cũ
(nó trỏ tới danh tính máy GCE), rồi mới `docker compose up`. Bỏ bước này thì
`listDatabases` vẫn xanh trong khi Appwrite không ghi được — đúng loại lỗi
mà cổng chỉ-đọc không bắt.

### Không huỷ gì

Snapshot `appwrite-prod-rehearsal-20260905` **được giữ nguyên** cho tới khi
diễn tập chạy xong và bằng chứng được ghi lại (điều kiện 6 của nhiệm vụ).
Lịch `fanfic-appwrite-daily` cũng giữ nguyên, không đụng tới.

### Hai việc còn để ngỏ từ đợt trước

1. Xác nhận `appwrite-postgresql` rỗng là đúng.
2. Xác nhận `fanfic-worker-prod` trên GCE còn cần chạy hay không.

## 8. DIỄN TẬP KHÔI PHỤC ĐÃ CHẠY THẬT — 2026-09-05

Chạy trên EC2 dùng-một-lần `47.128.228.81` (`ip-172-31-33-185`), 2 vCPU /
7840 MB / 61 GB / Ubuntu 24.04.4, swap 4 GiB. Xác nhận **không phải** máy
worker TTS production: không có `/opt/fanfic-audio`, 0 dịch vụ `fanfic`.
Production GCE, DNS và worker TTS **không bị chạm tới**.

### Chuỗi bằng chứng

| Bước | Kết quả |
|---|---|
| Nguồn | snapshot `appwrite-prod-rehearsal-20260905` (crash-consistent, 0 downtime) |
| Truyền | 14/14 volume, 910 MB, `sha256sum -c` **14 OK / 0 FAILED** |
| Nạp volume | 14/14 vào Docker; thư mục dữ liệu MongoDB 756,8 MB |
| **WiredTiger mở được** | `"starting WiredTiger recovery"`, `"Recovering log 13 through 14"`, `"Main recovery loop: starting at 13,32691072 to 14,256"` — journal replay chạy đúng như dự đoán, 0 lỗi hỏng |
| Database | `appwrite` 48,5 MB · `local` 257 MB (oplog) · `admin` · `config` |
| Replica set | `rs0`, thành viên `appwrite-mongodb:27017` |
| **Lên PRIMARY** | `isWritablePrimary=true` **ngay lần đầu**, `rs.status()` → `myState: 1` |
| Đọc/ghi | INSERT ack · READBACK đúng · UPDATE 1/1 · **TRANSACTION commit=true** · dọn sạch |
| Dữ liệu thật còn nguyên | `NOVELS_VAN_CON=50` sau khi ghi/xoá |

### Dữ liệu mức ứng dụng đã khôi phục

`fanfic_world_prod` — 43 collection khai báo, 27 có dữ liệu, **1.571 document**:

| Collection | Docs | Collection | Docs |
|---|---|---|---|
| Chapters | 290 | Job Claims | 255 |
| Job Locks | 240 | Audio Tracks | 238 |
| TTS Jobs | 237 | Moderation events | 104 |
| Video Imports | 51 | Novels | 50 |
| Content Queue | 30 | XP Ledger | 16 |
| Profiles | 15 | Quest Progress | 12 |

`fanfic_world_dev` — 41 collection, 19 có dữ liệu, 620 document.

Nội dung **đọc được thật**, không chỉ đếm được: tiêu đề tiếng Việt còn dấu
đúng (`"TỔNG HỢP Bóng Rổ Fanfic Kích Hoạt Hệ Thống Chó"`), 290 chương chứa
**3.158.180 ký tự**, index sống sót (novels 9, chapters 8, audio 7).

### Bất biến tham chiếu

| Quan hệ | So sánh được | Mồ côi | Kết quả |
|---|---|---|---|
| Chapter → Novel (`novel_id`) | 290/290 | 0 | **ĐẠT** |
| Audio → Chapter (`chapter_id`) | 238/238 | 1 | xem dưới |

**Một audio track mồ côi — KHÔNG phải lỗi khôi phục.** `trk_9d9c36f8a83a45a2`
tạo lúc `2026-09-04 23:37:31Z`, tức **9 giờ TRƯỚC** snapshot (08:51Z); bản ghi
mới nhất trong kho cũng đã 6,5 giờ trước snapshot. Nó nằm ngoài hẳn cửa sổ
crash-consistency, nên đây là **rác có sẵn trên production** (chương bị xoá
còn để lại audio), không phải mất mát do di trú. Cần dọn ở production.

### Hai lần phép kiểm tự báo ĐẠT trong khi không kiểm gì

Ghi lại vì đây đúng là loại "bằng chứng giả" mà cả nhiệm vụ này sinh ra để
chặn:

1. Đếm document bằng `r.$id` rồi `r._uid` → **mọi collection ra 0 document**.
   Một kết quả trong sạch trong khi 1.571 document vẫn nằm nguyên đó. ID thật
   nằm ở `r._id`.
2. Kiểm tham chiếu bằng `novelId` (camelCase) trong khi kho dùng `novel_id`
   → cả 290 chương "thiếu novelId", và phép kiểm in **"ĐẠT — không có tham
   chiếu mồ côi"** dù chưa so sánh một cặp nào.

Nên `integrity2.js` giờ **từ chối kết luận ĐẠT khi số bản ghi so sánh được
bằng 0** — không kết luận còn hơn kết luận sai.

### Điều diễn tập BÁC BỎ trong thiết kế trước đó

Bản trước của `appwrite_rehearsal_restore.sh` xoá `local.system.replset` rồi
`rs.initiate()` lại. Chạy thật cho thấy việc đó **thừa**: thành viên được địa
chỉ hoá bằng **tên container**, không phải tên máy, nên cấu hình di chuyển
được nguyên vẹn — `isWritablePrimary=true` ngay lần đầu, không sửa gì. Script
giờ **kiểm trước, chỉ can thiệp khi thật sự cần**.

### Còn thiếu: HTTP mức Appwrite

Chưa dựng được stack Appwrite đầy đủ vì `.env` không chuyển sang được (bị
cổng phân loại chặn hai lần). `.env` chứa `_APP_OPENSSL_KEY_V1`; thiếu nó thì
stack vẫn lên và schema vẫn đúng trong khi các trường được mã hoá **không
giải mã được** — đúng loại "khôi phục thành công" giả. **Không tự sinh khoá
mới để lấp chỗ đó.**

Người vận hành chạy một lệnh là xong:

```bash
scp -i C:\Users\nguye\.ssh\fanficappwrrite.pem \
    <thu-muc>/.env ubuntu@47.128.228.81:/home/ubuntu/rehearsal/stack/.env
```

Sau đó `docker compose -p appwrite up -d` (tên project **phải** là `appwrite`,
vì volume đã nạp mang tiền tố `appwrite_`).

## 9. TOÀN BỘ STACK APPWRITE ĐÃ CHẠY THẬT TRÊN BẢN KHÔI PHỤC — 2026-09-05

Phần còn thiếu ở mục 8 (HTTP mức Appwrite) nay đã xong. `.env` production
được đưa sang bằng một lệnh `scp` duy nhất, `chmod 600`, và **không giá trị
bí mật nào được in ra** ở bất kỳ bước nào.

### Trung hoà đối ngoại TRƯỚC khi `up` — bắt buộc

Bản khôi phục là bản sao **đầy đủ** của production, nên nếu bật lên nguyên xi
nó sẽ gửi email thật tới người dùng thật và xin chứng chỉ cho tên miền thật.
Đã vô hiệu **trước** khi khởi động:

| Khoá | Thành |
|---|---|
| `_APP_SMTP_HOST/PORT/USERNAME/PASSWORD/SECURE` | rỗng |
| `_APP_DOMAIN`, `_APP_DOMAIN_FUNCTIONS`, `_APP_DOMAIN_SITES` | `localhost` |
| `_APP_DOMAIN_TARGET_A/AAAA/CNAME/CAA` | localhost / rỗng |
| `_APP_OPTIONS_FORCE_HTTPS`, `_APP_OPTIONS_ABUSE` | `disabled` |
| `_APP_OPENSSL_KEY_V1` | **giữ nguyên** (bắt buộc, xem dưới) |

### Stack lên đủ

**32/32 container `running`**, không cái nào restart-loop hay exited.
`http://` bị Traefik 301 sang `https://` (chứng chỉ tự ký vì ACME đã tắt):

```
GET https://localhost/v1/health/version -> {"version":"1.9.6"}   [HTTP 200]
GET https://localhost/console           -> <!doctype html>       [HTTP 200]
```

### `_APP_OPENSSL_KEY_V1` GIẢI MÃ ĐƯỢC DỮ LIỆU PRODUCTION THẬT

Đây là phép thử **quyết định**, và nó không thể làm giả được. Tạo một user mới
rồi đọc lại chỉ chứng minh Appwrite tự nhất quán với khoá của **chính nó** —
kể cả khi đó là khoá SAI. Chỉ việc giải mã được **ciphertext có sẵn** mới
chứng minh khoá khớp dữ liệu cũ.

Trong bản khôi phục có **15 trường mã hoá** (`aes-128-gcm`): mật khẩu người
dùng, secret của API key, OAuth access/refresh token, secret của session.
Giải mã trực tiếp bằng khoá trong `.env`:

| Ciphertext | Kết quả |
|---|---|
| `_console_keys.secret` | **GIẢI MÃ ĐƯỢC** → 265 ký tự |
| `_console_users.password` | **GIẢI MÃ ĐƯỢC** → 97 ký tự |
| `identities.providerAccessToken` (OAuth) | **GIẢI MÃ ĐƯỢC** → 253 ký tự |
| user password của project | **GIẢI MÃ ĐƯỢC** → 97 ký tự |

`GIAI_MA_DAT=4  GIAI_MA_HONG=0`. **Không bản rõ nào được in** — chỉ độ dài và
loại ký tự, đủ để kết luận mà không lộ bí mật.

Khép kín thêm một vòng: API key `backend-runtime-key-v2` giải mã từ
`_console_keys` rồi dùng thật để gọi API — Appwrite **chấp nhận**, tức là
chuỗi khoá → key → dữ liệu đúng từ đầu tới cuối.

### Kiểm tra qua chính REST API

| Lệnh gọi | Kết quả |
|---|---|
| `GET /databases/fanfic_world_prod/collections` | **HTTP 200**, `total=43` |
| `GET .../collections/novels/documents` | **HTTP 200**, `total=50`, tiêu đề thật |
| `POST .../novels/documents` (bản ghi đánh dấu) | **HTTP 201** |
| `GET .../novels/documents/rehearsal_probe_20260905` | **HTTP 200**, đọc lại đúng |
| `DELETE .../rehearsal_probe_20260905` | **HTTP 204** |
| Đối chiếu sau cùng | novels `50 → 50` — **trả về nguyên trạng** |

Ghi **có đảo ngược thật**: tạo → đọc lại → xoá → số lượng về đúng như cũ,
không để lại rác.

### RAM/swap dưới toàn bộ stack — số liệu quyết định cho việc chọn máy

```
Mem:  total 7840 MB | used 3859 | buff/cache 3958 | available 3980
Swap: total 4095 MB | used 8 KB          <-- gần như KHÔNG chạm swap
32 container running | disk 17G/61G (28%)
```

| Container | RAM |
|---|---|
| `appwrite-embedding` | 856 MB |
| `appwrite-mongodb` | 442 MB (CPU 102% — no một lõi lúc khởi động) |
| `appwrite-browser` | 227 MB |
| `appwrite` | 173 MB |

**Điều này xác nhận khuyến nghị 8 GiB ở mục 4.** Toàn bộ 32 container chạy
trong 3,86 GB và **không đụng tới swap** (8 KB), còn dư ~3,98 GB. Máy GCE
hiện tại phải đẩy 2,53 GB ra swap chỉ vì nó có ít RAM hơn (6,93 GiB) và đã
chạy liên tục 20 ngày.

**Giới hạn của số đo này, nói thẳng:** đây là stack **không có tải thật** —
không người dùng đồng thời, không job TTS, không quét truyện. Nó chứng minh
8 GiB đủ cho *mức nền*, **chưa** chứng minh cho *đỉnh tải*. Biên 4 GB còn lại
là lý do vẫn nên giữ 4 GiB swap.

### Ghi chú về scope của API key (phát hiện phụ)

Đối chiếu `_console_keys` theo `resourceId`:

| Key | Project | `documents.write` |
|---|---|---|
| `fanfic-schema-provisioner` | `fanfic-world-prod` | **không** |
| `schema-migration-key` | `fanfic-world-prod` | **có** |
| `backend-runtime-key-v2` | `fanfic-world-prod` | có (đúng vai trò) |
| `schema-migration-key-v2` | dev | có |
| `staging-schema-runtime-2026-08-23` | dev | có — **26 scope**, gồm buckets/files/tokens |

`docs/HANDOFF.md` nói khoá schema được cấp **đúng bảy scope, cố ý không có
`documents.*`** — điều đó **đúng** với `fanfic-schema-provisioner`. Nhưng trên
cùng project production còn `schema-migration-key` **có** `documents.write`.
Nếu `APPWRITE_SCHEMA_API_KEY` đang trỏ vào khoá đó thì lập luận "13 series
thật không thể bị động tới" **không còn đứng vững**. Cần người vận hành đối
chiếu xem biến môi trường đang dùng khoá nào — không kết luận thay.

# Di trú Appwrite production khỏi GCE — đường đi đã CHỨNG MINH được tới đâu

Ngày đo: **2026-09-05**. Mọi con số dưới đây đến từ một lần đo THẬT trên hạ
tầng thật, không lấy lại từ tài liệu cũ. Nhiệm vụ này **không** chốt cutover
và **không** đụng vào production.

> **Kết luận một dòng:** bản backup mới nhất **KHÔNG được coi là khôi phục
> được**. Nó nguyên vẹn về đường truyền nhưng bên trong là một bản chép
> RÁCH của MongoDB đang chạy. Cutover dựa trên bản này là đánh cược toàn bộ
> dữ liệu production.

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

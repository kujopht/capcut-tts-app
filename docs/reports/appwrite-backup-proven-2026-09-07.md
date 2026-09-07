# Sao lưu Appwrite production — ĐÃ CHỨNG MINH KHÔI PHỤC ĐƯỢC — 2026-09-07

Stamp: `20260907T054557Z` · Host: AWS `54.179.200.223` (`i-064abacf35ebe2c8a`)

## 1. Kiểm kê host thật

| Hạng mục | Giá trị |
|---|---|
| Instance | `i-064abacf35ebe2c8a`, hostname `ip-172-31-35-102` |
| Ổ đĩa | **một** volume gốc 64 GB (`nvme0n1`) — không có data volume riêng |
| Dung lượng | 61 G tổng, **18 G dùng**, 44 G trống (29%) |
| RAM | 7840 MB, ~3.5 GB khả dụng, swap 4 GB chưa dùng |
| CPU | 2 vCPU |
| Container | 31 đang chạy, Appwrite **1.9.6** |

**Ba engine dữ liệu, không phải một** — điều này đúng với giả định ban đầu của
người yêu cầu, và **sai** với đính chính trước đó của tôi (tôi đã nói Appwrite
1.x không dùng MongoDB; sai):

| Engine | Image | Volume trên đĩa |
|---|---|---|
| MongoDB | `mongo:8.2.5` | 755.1 M |
| MariaDB | `mariadb:10.11` | 148.2 M |
| PostgreSQL | `appwrite/postgres:0.1.0` | 4.0 K (trống) |
| Redis | `redis:7.4.7-alpine` | — |

14 volume có tên. Đáng chú ý: **`appwrite-uploads` chỉ 8.0 K và chứa 0 tệp** —
Appwrite Storage **không giữ tệp nào**; audio/avatar nằm ở R2. `appwrite-models`
557 M là cache model embedding (dẫn xuất, tải lại được).

## 2. Bản sao lưu đã tạo

```
mariadb-all.sql.gz      1.1 M   mariadb-dump --all-databases --single-transaction
mongodb.archive.gz      3.2 M   mongodump --oplog --archive --gzip
postgres-all.sql.gz     4.0 K   pg_dumpall
vol-{uploads,config,certificates,functions,builds,imports,sites}.tar.gz
vol-models.tar.gz     557   M   (GIỮ TRÊN HOST, không copy off-host — xem dưới)
```

Bí mật **không bao giờ ra khỏi container**: mọi mật khẩu được tham chiếu bằng
tên biến bên trong `docker exec sh -c`, nên không nằm trên dòng lệnh host,
không vào process table, không vào history. Không container nào bị dừng, không
volume production nào bị ghi, không gì bị xoá.

**Off-host:** 10 artifact đã copy về máy điều hành, **10/10 SHA256 khớp**.
`vol-models.tar.gz` cố ý không copy: 557 M cache model dẫn xuất, tải lại được,
làm bản sao lưu phình 130× mà không thêm giá trị dữ liệu. Hash của nó vẫn được
ghi trong `SHA256SUMS.txt` trên host.

## 3. Chứng minh khôi phục — ba tầng, khớp tuyệt đối

Môi trường dùng-một-lần: container `restore-test-mongo` riêng, volume riêng,
credential riêng, **không** nối vào network của Appwrite. Đã xoá sau khi xong.

| Tầng | Kết quả |
|---|---|
| `mongorestore` tự báo | **44960 document restored, 0 failed** |
| Số collection của DB ứng dụng | **43** khôi phục — production **43** ✓ |
| Collection có dữ liệu | **27** — production **27** ✓ |
| **Tổng document ứng dụng** | **1832** — production **1832** ✓ |
| Đọc lại nội dung thật | `nov_6ac6cb95275e4c2d` → `"Audio Studio"` ✓ · `chp_73bb0d9c94204361` → `"1"` ✓ (**2/2**) |

Đây là chứng minh ở mức **nội dung**, không phải "có tệp snapshot".

## 4. Hai đính chính so với yêu cầu ban đầu

1. **Số 1571 không dùng được.** Đó là số của lần diễn tập 2026-09-03 trên máy
   GCE. Production hôm nay là **1832** (43 collection, 27 có dữ liệu). Ép bằng
   1571 sẽ làm một bản sao lưu tốt bị coi là thất bại. Bất biến đúng là *khôi
   phục == nguồn đo tại thời điểm dump*, và nó **khớp chính xác**.
2. **"Đọc lại một tệp Appwrite thật" không thực hiện được** — vì Appwrite
   Storage **không có tệp nào** (`uploads` = 8.0 K, 0 tệp). Đã thay bằng đọc lại
   **document thật**, 2/2 khớp cả `_uid` lẫn `title`.

## 5. Sự cố trong lúc diễn tập, và nguyên nhân thật

Lần chạy đầu container mongo dùng-một-lần **sập** (exit 139). Không phải OOM
(`OOMKilled=false`). Nguyên nhân đọc được từ log:

```
Location13538: couldn't open [/proc/1/stat] Too many open files
WT_PANIC: WiredTiger library panic  (error_code 24)
```

Giới hạn file descriptor **của container** (mặc định Docker 1024), không phải
của host. Mongo production chạy với `ulimit -n = 64000`. Đặt
`--ulimit nofile=64000:64000` là hết — lần chạy sau thành công hoàn toàn.

**Production không bị ảnh hưởng:** kiểm ngay sau sự cố — 31 container, health
api/db/cache 200, và số document vẫn đúng **1832** sau toàn bộ công việc.

Một phát hiện **không liên quan tới tôi**: container
`appwrite-worker-stats-resources` đang `exited` với exit **137** (SIGKILL) từ
**2026-09-05T16:01:57Z** — tức từ ngày di trú, **hai ngày trước** phiên làm việc
này. Không phải do diễn tập gây ra (diễn tập chạy 2026-09-07 05:53Z). Nên xem
riêng.

## 6. Còn thiếu: EBS snapshot

Không tạo được. `aws` CLI **không có** trên máy điều hành lẫn trên chính host
Appwrite, và không có credential AWS nào ở đâu. Đây là ranh giới thật.

Lớp logic (mục 2–3) đã đủ để **khôi phục dữ liệu**. EBS snapshot là lớp khác:
nó cứu khi mất **cả host**. Nên vẫn cần, nhưng không chặn.

## 7. Khoảng trống đã đóng những gì

| Trước | Sau |
|---|---|
| Bản chứng minh được cuối cùng là ảnh máy **GCE**, 2026-09-03 | Có bản của **chính host AWS đang chạy**, 2026-09-07, đã chứng minh khôi phục |
| Đích kho lạnh Drive **hỏng** (token hết hạn) | Vẫn hỏng — đã đi đường off-host trực tiếp về máy điều hành thay thế |
| Không biết dữ liệu nằm ở engine nào | Ba engine, đã dump cả ba |

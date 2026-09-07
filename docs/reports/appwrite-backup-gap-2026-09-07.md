# Khoảng trống sao lưu Appwrite production — 2026-09-07

**Kết luận: production Appwrite hiện KHÔNG có bản sao lưu nào được chứng minh.**
Bản cuối cùng chứng minh được là của **máy cũ**, trước khi di trú.

## 1. Vì sao đây là khoảng trống thật, không phải lo xa

| Mốc | Sự việc |
|---|---|
| 2026-09-03 | Backup `appwrite-selfhost-20260903T163727Z.tar.gz` — 912 MiB, SHA256 ghi lại, 11 volume, kèm `RESTORE.md`, **đã diễn tập khôi phục thành công từ Drive** (1571 document). Đó là của **máy GCE** |
| ~2026-09-04/05 | Appwrite di trú sang AWS. `fanfic-appwrite-temp` bị `TERMINATED`; snapshot `appwrite-prod-final-20260905` được tạo |
| 2026-09-07 | Origin sống = **AWS `54.179.200.223`**, Appwrite 1.9.6, storage device = **đĩa cục bộ** |

Nghĩa là **mọi dữ liệu ghi từ lúc di trú tới nay chưa từng được sao lưu chứng
minh được.** Bản 09-03 là ảnh của một máy đã rời đi.

Và các snapshot GCE **không** lấp được chỗ này: Appwrite chưa từng ở GCE sau khi
di trú, nên 18 snapshot của `fanfic-appwrite-temp` là **di sản lịch sử**, không
phải đường lùi cho production đang chạy.

## 2. Ba ranh giới đang chặn — đo được, không phỏng đoán

| # | Ranh giới | Bằng chứng |
|---|---|---|
| 1 | **Không SSH được vào host Appwrite** | `ssh ubuntu@54.179.200.223` → **timed out**. Timeout (khác "refused") nghĩa là gói tin bị **thả im lặng** → security group / NACL / firewall của host. Không phân biệt được cái nào khi chưa vào được |
| 2 | **Không có API AWS** | `aws` CLI không cài; `~/.aws/` không tồn tại; truy vấn IMDS qua máy worker bị permission gate chặn |
| 3 | **Đích kho lạnh đang HỎNG** | `rclone lsf fanfic-gdrive:…` → `invalid_grant: maybe token expired`. Token Drive đã hết hạn → **một lần chạy backup hôm nay sẽ thất bại ở bước đẩy lên** |

Ranh giới 3 quan trọng hơn vẻ ngoài: nó nghĩa là đường sao lưu **đã im lặng
ngừng hoạt động**, và không ai biết cho tới khi có người thử.

## 3. Công cụ đã có — cần trỏ lại, không cần viết mới

`scripts/ops/appwrite_backup_offvm.sh` đã đúng hình dạng: đóng băng volume qua
Docker, tar, đưa **ra khỏi** VM, không cài rclone trên VM (không đặt credential
Drive lên máy mở 80/443), **không xoá gì**. Kèm `appwrite_backup_verify.py` và
`appwrite_restore_rehearsal.py`.

Nhưng nó nhắm vào **máy GCE cũ**: `APPWRITE_DIR=/home/robux/appwrite`, user SSH
`nguye` thuộc `google-sudoers` (nhóm của GCE, không phải AWS). Trên host AWS mới,
cả đường dẫn lẫn user đều phải xác nhận lại — **đó chính là việc bước 1 của kế
hoạch phải làm.**

## 4. Đính chính một giả định: Appwrite dùng MariaDB, không phải MongoDB

Yêu cầu ban đầu nói "Appwrite/Mongo volumes". Appwrite 1.x **không dùng
MongoDB**. Nó dùng **MariaDB** + **Redis**. Health endpoint của chính instance
xác nhận hình dạng đó:

```
/v1/health/db    -> 2 database: "Console.DB (console)", "Projects.DB (database_db_main)"
/v1/health/cache -> 1 Cache
```

Kế hoạch dưới đây viết cho MariaDB. Nếu bước 1 phát hiện khác, sửa kế hoạch —
đừng sửa thực tế.

## 5. Kế hoạch sao lưu — hai lớp, vì một lớp không đủ

### Lớp A — EBS snapshot (AWS-native, toàn ổ đĩa)

Nhanh, khôi phục được cả máy, và là thứ duy nhất cứu được khi mất **host**.
Nhưng snapshot của một ổ đang chạy chỉ **crash-consistent**: MariaDB sẽ phải
chạy InnoDB recovery khi khôi phục, và điều đó có thể thành công *hoặc không*.
**Không được coi lớp A là bản sao lưu cơ sở dữ liệu.**

### Lớp B — dump logic, ngoài host (thứ thật sự chứng minh được)

```bash
# tren host Appwrite, trong mot lenh co quyen
docker exec <mariadb-container> mariadb-dump \
    --all-databases --single-transaction --quick --routines --triggers \
    | gzip > /var/tmp/appwrite-db-$(date -u +%Y%m%dT%H%M%SZ).sql.gz
```

`--single-transaction` cho ảnh **nhất quán về giao dịch** mà không khoá bảng —
đây là điểm lớp A không làm được.

### Lớp C — file trên đĩa cục bộ của Appwrite

Vì storage device là local (`/v1/health/storage/local` pass), các volume
`uploads`/`cache`/`config`/`functions` giữ file **không** nằm trong R2 và
**không** nằm trong bất kỳ snapshot GCE nào. `tar` chúng như bản 09-03 đã làm
(11 volume, có `RESTORE.md` bên trong).

### Đích off-host

Không dùng lại Drive cho tới khi token được nối lại. Hai lựa chọn:
1. **Nối lại `fanfic-gdrive`** — `rclone config reconnect fanfic-gdrive:` (cần
   trình duyệt), rồi dùng đúng đường đã chứng minh;
2. **Một bucket R2 riêng cho backup** — không dùng `fanfic-prod` (trộn backup
   với dữ liệu phát trực tiếp là sai), và khoá R2 hiện có chỉ có phạm vi
   `fanfic-staging`, nên cần khoá mới.

Lựa chọn 1 rẻ hơn và đã được chứng minh khôi phục được. Nên chọn nó.

## 6. Chứng minh khôi phục được — "có snapshot" KHÔNG phải bằng chứng

Lặp lại đúng bài đã pass ngày 2026-09-03, không nhẹ hơn:

1. Khôi phục dump vào một MariaDB **dùng-một-lần** (container riêng), tuyệt đối
   không chạm production;
2. Chạy Appwrite trỏ vào bản khôi phục đó;
3. **Đếm document** và so với production tại thời điểm chụp — lần trước là
   **1571**. Số phải khớp, không phải "gần khớp";
4. Đọc lại một file thật từ storage đã khôi phục;
5. Ghi SHA256 của mọi artifact vào báo cáo, như bản 09-03 đã làm.

Chỉ khi bước 3 và 4 xanh thì mới được gọi là có bản sao lưu.

## 7. Thứ tự thực hiện

1. Mở SSH (xem hành động bên dưới) → **kiểm kê**: instance/volume id, danh sách
   volume, dung lượng đĩa, snapshot EBS đang có, đường dẫn Appwrite thật, tên
   container MariaDB.
2. Chạy lớp B + C bằng một lệnh có quyền trên host.
3. Kéo ra khỏi host → nối lại Drive → đẩy lên.
4. Diễn tập khôi phục (mục 6).
5. Chỉ sau khi mục 6 xanh: bàn tới lớp A định kỳ và tháo dỡ di sản GCE.

**Không xoá snapshot/đĩa GCE nào trước khi mục 6 xanh** — dù chúng là di sản,
chúng vẫn là thứ duy nhất tồn tại hiện nay có nguồn gốc Appwrite.

# Origin thật của Appwrite production — điều tra 2026-09-07

**Trạng thái: CHƯA định danh được.** Tài liệu này ghi lại chuỗi loại trừ để
người sau không phải suy ra lại, và để không ai kết luận từ tài liệu cũ.

Điểm khởi đầu là một nghịch lý: `scripts/ops/cutover_target.py` từng gán endpoint
production với **máy GCE `fanfic-appwrite-temp`**, trong khi máy đó đã
`TERMINATED`. Câu gán đó đã được sửa (commit `307074e`).

## Bản chất nghịch lý

Cuộc di trú sang AWS là di trú **worker TTS/dịch**, **không** phải di trú
Appwrite. Hai trục khác nhau bị gộp làm một. Worker đã chuyển GCE → AWS xong và
đã kiểm chứng; còn chỗ ở của Appwrite là chuyện riêng.

## Chuỗi loại trừ — đo trực tiếp, không đọc tài liệu

| Ứng viên | Bằng chứng loại trừ |
|---|---|
| `fanfic-appwrite-temp` | `TERMINATED` liên tục trong khi Appwrite phục vụ thật |
| **Toàn bộ GCE** | **2026-09-07 05:03Z: cả 4 VM đều `TERMINATED`, Appwrite vẫn trả `200`.** Đây là bằng chứng mạnh nhất — không còn compute nào trong GCP để mà phục vụ |
| Máy worker AWS `13.212.224.218` | `docker: command not found`; `ss -tln` chỉ có cổng **22** và **53** — không listener HTTP nào |
| GCE ở tài khoản khác | 3 project còn lại của tài khoản chính + cả 5 project của `kujopht@gmail.com` đều **TẮT Compute API** |
| Appwrite Cloud | `sgp.cloud.appwrite.io` → **2.0.0**, `Server: Appwrite`. Endpoint của ta → **1.9.6**, `Server: cloudflare` |
| Cloudflare Tunnel | `/accounts/{id}/cfd_tunnel` và `/tunnels` đều trả `200` với **danh sách RỖNG** |

## Hình dạng triển khai (suy ra từ chính ứng dụng, không phải từ tài liệu)

Đọc các endpoint health kèm API key:

```
/v1/health/db       -> 2 database: "Console.DB (console)", "Projects.DB (database_db_main)"
/v1/health/cache    -> 1 Cache, pass
/v1/health/storage/local -> pass
/v1/health/queue/*  -> size 0
header              -> x-debug-fallback, x-debug-speed  (dac trung Appwrite tu luu tru)
```

Tức là một bản **Appwrite 1.9.6 tự lưu trữ tiêu chuẩn** (kiểu docker-compose),
storage device là **đĩa cục bộ**, không phải S3.

**Hệ quả vận hành đáng chú ý:** vì storage device là local, host origin đó đang
giữ file phía Appwrite trên đĩa của chính nó — những file đó **không** nằm trong
R2. Ai bàn tới sao lưu hay tháo dỡ phải tính tới điều này.

## Cái gì còn chặn

Bản ghi A của `appwrite-dev.fanfic.world` trả về IP của Cloudflare
(`172.67.142.101`, `104.21.63.15`) → proxied, origin bị che. Token Cloudflare
trên máy này đọc được `/zones` (thấy `fanfic.world`, active) nhưng
`/zones/{id}/dns_records` trả **403** — token có `Zone:Read`, **không** có
`DNS:Read`.

Mọi đường đọc-thuần khác đã thử và đều không lộ origin: toàn bộ header đều là
của Cloudflare, không có `x-powered-by`, không có hostname/IP nội bộ trong thân
phản hồi hay trang `/console/`, phản hồi lỗi 404 cũng không echo gì.

## MỘT hành động để giải quyết

Thêm quyền **DNS → Read** cho token Cloudflare đang có, rồi:

```bash
python <scratchpad>/do_dns_appwrite.py     # sẽ in thẳng bản ghi + proxied=true/false
```

Hoặc đọc bản ghi `appwrite-dev` trong Cloudflare dashboard (Zone `fanfic.world`).

**Không suy ra origin từ bất kỳ tài liệu, comment nhánh, hay cấu hình lịch sử
nào.** Đó chính là cách nghịch lý này sinh ra lần đầu.

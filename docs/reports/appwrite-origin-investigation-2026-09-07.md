# Origin thật của Appwrite production — điều tra 2026-09-07

## ĐÃ GIẢI: origin là `54.179.200.223` — một EC2 AWS khác

```
Ban ghi DNS (Cloudflare):  A  appwrite-dev.fanfic.world -> 54.179.200.223  proxied=True
Goi THANG vao IP, bo qua Cloudflare:
    HTTP/1.1 200 OK
    Server: Appwrite                 <- KHONG phai "cloudflare"
    X-Debug-Fallback / X-Debug-Speed <- header cua ban TU LUU TRU
    {"version":"1.9.6"}              <- trung khop voi duong qua Cloudflare
```

Chứng cứ dứt điểm: gọi thẳng vào IP với `--resolve` (bỏ hẳn Cloudflare) trả về
`Server: Appwrite` và **đúng** phiên bản 1.9.6, kèm chứng chỉ TLS hợp lệ cho
chính hostname đó.

**Vậy "đã di trú production Appwrite sang AWS" là ĐÚNG.** Appwrite nằm trên AWS
— chỉ là một **EC2 khác** với máy worker TTS:

| Vai trò | Host |
|---|---|
| Appwrite (database + API) | `54.179.200.223` |
| Worker TTS + dịch production | `13.212.224.218` |

Cả hai đều là AWS `ap-southeast-1`. Đó là lý do câu chuyện nghe như mâu thuẫn:
**hai máy AWS khác nhau, không phải một.**

## Sai sót của chính điều tra này — ghi lại để không lặp

1. Tôi kết luận **"không nằm trên AWS"** sau khi chỉ kiểm **một** máy AWS
   (`13.212.224.218`, máy worker TTS). Kết luận đúng phải là *"không nằm trên
   MÁY AWS ĐÓ"*. Suy từ một host ra cả một nhà cung cấp là bước sai.
2. `54.179.200.223` **đã nằm trong `~/.ssh/known_hosts`** ngay từ lần dò đầu
   tiên — tôi đã in nó ra rồi bỏ qua. Một IP lạ trong `known_hosts` của chính
   máy điều hành là một manh mối, không phải rác.
3. Cả hai sai sót đều khiến vòng điều tra dài thêm vài lượt và làm ra một tài
   liệu tạm thời kết luận "chưa định danh được" trong khi bằng chứng đã ở sẵn
   trên đĩa.

Bài học vận hành: khi loại trừ, hãy loại trừ **host**, đừng loại trừ **nhà cung
cấp**; và quét `known_hosts` trước khi tuyên bố một origin là không xác định.

## Chuỗi loại trừ (vẫn đúng, giữ lại làm hồ sơ)

Phần dưới đây ghi lại quá trình trước khi có `DNS:Read`. Nó vẫn đúng về những
gì nó loại trừ — chỉ là chưa đủ để chạm tới câu trả lời.

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

## Cái đã chặn, và cái đã mở nó ra

Bản ghi A công khai của `appwrite-dev.fanfic.world` trả về IP của Cloudflare
(`172.67.142.101`, `104.21.63.15`) → proxied, origin bị che. Token Cloudflare
lúc đó chỉ có `Zone:Read`, nên `/zones/{id}/dns_records` trả **403**.

Mọi đường đọc-thuần khác đều không lộ origin: toàn bộ header là của Cloudflare,
không `x-powered-by`, không hostname/IP nội bộ trong thân phản hồi hay trang
`/console/`, 404 cũng không echo gì.

Thêm **DNS → Read** cho token là đủ để mở: `/dns_records` trả ngay bản ghi và
cờ `proxied`. Công cụ tái lập:

```bash
python <scratchpad>/do_dns_appwrite.py
```

## Hệ quả cần theo dõi

1. **SSH cổng 22 tới `54.179.200.223` bị timeout** từ máy điều hành. Đây là
   dáng bảo mật đúng (chỉ 80/443 qua Cloudflare), nhưng nghĩa là **không quan
   sát được CPU/RAM/đĩa của host Appwrite** từ phiên làm việc. Mọi giám sát
   Appwrite hiện nay là ở mức **API health**, không phải mức máy.
2. **Storage device của Appwrite là đĩa cục bộ, không phải S3**
   (`/v1/health/storage/local` pass). Nên `54.179.200.223` đang giữ file phía
   Appwrite trên đĩa của chính nó — **không** nằm trong R2, và **không** nằm
   trong bất kỳ snapshot GCE nào. Đây là khoảng trống sao lưu thật sự cần bàn.
3. Vì Appwrite **không** ở GCE, các snapshot của `fanfic-appwrite-temp` là **di
   sản lịch sử** của một kiến trúc đã rời đi — không phải bản sao lưu của
   production hiện tại. Đừng coi chúng là đường lùi cho dữ liệu đang chạy.

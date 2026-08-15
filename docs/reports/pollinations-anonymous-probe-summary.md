# Dò tìm model ảnh Pollinations hoạt động không cần API key

Prompt trung tính dùng xuyên suốt: `a red apple on a white background`

Tiêu chí thành công: HTTP 200 VÀ Content-Type bắt đầu bằng `image/` VÀ thân response không rỗng.

Đối chiếu endpoint UNIFIED (`gen.pollinations.ai`, không key): status=401, content-type='application/json', kết quả: THẤT BẠI — HTTP 401: {"success":false,"error":{"message":"Authentication required. Please provide an API key via Authorization header (Bearer token) or ?key= query parameter.","code":"UNAUTHORIZED","timestamp":"2026-08-15

## ⚠️ Phát hiện quan trọng — KHÔNG được ẩn giấu

Cả **7 model** trả về HTTP 200 + ảnh hợp lệ (dreamshaper, flux, gpt-image-2, gptimage, nanobanana-pro, turbo, zimage) đều cho ra **CÙNG MỘT ảnh byte-for-byte giống hệt nhau** (SHA256 rút gọn: `173c3d7d6d85d537`), dùng cùng prompt + seed.

Diễn giải: endpoint legacy ẩn danh (không key) dường như **bỏ qua tham số `model=`** và luôn phục vụ MỘT model mặc định/dự phòng cố định, bất kể tên model yêu cầu là gì. Theo tiêu chí thành công nghiêm ngặt đã định (HTTP 200 + `image/*` + không rỗng), các model này VẪN được tính là "thành công" — nhưng điều đó **không chứng minh model cụ thể đó thực sự chạy** ở chế độ ẩn danh.

**ĐÃ XÁC MINH BỔ SUNG (xem mục cuối báo cáo):** một request với tham số `model=` là một tên KHÔNG TỒN TẠI cũng trả về đúng ảnh byte-for-byte giống hệt 7 model trên. Điều này xác nhận dứt điểm: tham số `model=` bị bỏ qua/chuẩn hoá hoàn toàn ở chế độ ẩn danh — không có model riêng lẻ nào trong số 7 tên trên được coi là "đã xác nhận hoạt động ẩn danh" theo đúng nghĩa của nó. Chỉ có thể kết luận: "sinh ảnh ẩn danh qua endpoint legacy hoạt động", không phải "flux/zimage/... hoạt động ẩn danh".

## Bảng tổng hợp theo 4 nhóm

### 1. Trả về ảnh HTTP 200 hợp lệ ở endpoint legacy ẩn danh — KHÔNG phải xác nhận từng model riêng lẻ

**⚠️ Đọc mục "Kết luận theo đúng yêu cầu" ở cuối báo cáo trước khi dùng bảng này.**
Bước xác minh bổ sung (xem cuối báo cáo) chứng minh endpoint bỏ qua/chuẩn
hoá tham số `model=` — kể cả một tên model bịa đặt cũng trả về đúng ảnh
byte-for-byte như 7 tên dưới đây. Vì vậy các dòng này CHỈ xác nhận "gọi
endpoint legacy không key trả về ảnh hợp lệ", KHÔNG xác nhận model được
liệt kê thực sự là model đã tạo ra ảnh đó.

| Model (tên đã thử, không xác nhận per-model) | Tỷ lệ thành công | Độ trễ TB (s) | HTTP vòng 1 | Ghi chú lỗi (nếu có) |
|---|---|---|---|---|
| flux | 3/3 | 0.46 | 200 | — |
| zimage | 3/3 | 0.31 | 200 | — |
| dreamshaper | 3/3 | 0.31 | 200 | — |
| turbo | 3/3 | 0.4 | 200 | — |
| gptimage | 3/3 | 0.31 | 200 | — |
| gpt-image-2 | 3/3 | 0.42 | 200 | — |
| nanobanana-pro | 3/3 | 0.31 | 200 | — |

### 2. Không ổn định / giới hạn công suất

_(không có model nào)_

### 3. Yêu cầu xác thực / thanh toán

| Model | Tỷ lệ thành công | Độ trễ TB (s) | HTTP vòng 1 | Ghi chú lỗi (nếu có) |
|---|---|---|---|---|
| kontext | 0/1 | 0.45 | 500 | HTTP 500: {"error":"Internal Server Error","message":"kontext model is only available on enter.pollinations.ai. Visit https://enter.pollinations.ai/?ref=image to get started.","debug":null,"timingInfo":[{"step" |
| nanobanana | 0/1 | 0.47 | 500 | HTTP 500: {"error":"Internal Server Error","message":"nanobanana model is only available on enter.pollinations.ai. Visit https://enter.pollinations.ai/?ref=image to get started.","debug":null,"timingInfo":[{"st |
| seedream | 0/1 | 0.45 | 500 | HTTP 500: {"error":"Internal Server Error","message":"seedream model is only available on enter.pollinations.ai. Visit https://enter.pollinations.ai/?ref=image to get started.","debug":null,"timingInfo":[{"step |

### 4. Model không được hỗ trợ

_(không có model nào)_

## Chi tiết vòng 1 (tất cả 10 model, legacy endpoint)

| Model | HTTP | Content-Type | Size (byte) | SHA256 (16 ký tự) | Độ trễ (s) | Kết quả |
|---|---|---|---|---|---|---|
| flux | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.77 | OK |
| zimage | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.31 | OK |
| dreamshaper | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.33 | OK |
| turbo | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.28 | OK |
| gptimage | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.33 | OK |
| gpt-image-2 | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.62 | OK |
| kontext | 500 | application/json | — | — | 0.45 | Thất bại |
| nanobanana | 500 | application/json | — | — | 0.47 | Thất bại |
| nanobanana-pro | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | 0.30 | OK |
| seedream | 500 | application/json | — | — | 0.45 | Thất bại |

## Vòng 2 — lặp lại 2 lần cho 7 model thành công ở vòng 1

| Model | Lần | HTTP | Size (byte) | Độ trễ (s) | Kết quả |
|---|---|---|---|---|---|
| flux | 2 | 200 | 42779 | 0.31 | OK |
| flux | 3 | 200 | 42779 | 0.30 | OK |
| zimage | 2 | 200 | 42779 | 0.31 | OK |
| zimage | 3 | 200 | 42779 | 0.31 | OK |
| dreamshaper | 2 | 200 | 42779 | 0.30 | OK |
| dreamshaper | 3 | 200 | 42779 | 0.31 | OK |
| turbo | 2 | 200 | 42779 | 0.62 | OK |
| turbo | 3 | 200 | 42779 | 0.28 | OK |
| gptimage | 2 | 200 | 42779 | 0.30 | OK |
| gptimage | 3 | 200 | 42779 | 0.31 | OK |
| gpt-image-2 | 2 | 200 | 42779 | 0.31 | OK |
| gpt-image-2 | 3 | 200 | 42779 | 0.31 | OK |
| nanobanana-pro | 2 | 200 | 42779 | 0.31 | OK |
| nanobanana-pro | 3 | 200 | 42779 | 0.31 | OK |
## Kết luận cuối cùng — đã xác minh tối thiểu bổ sung

Bước xác minh bổ sung (4 request, cùng prompt + seed=42, KHÔNG lặp lại toàn bộ 25 request của lần dò đầu — tránh stress-test dịch vụ):

| Trường hợp | HTTP | Content-Type | Size | SHA256 (16 ký tự) | Header không nhạy cảm |
|---|---|---|---|---|---|
| khong_model | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | `{'content-type': 'image/jpeg', 'content-length': '42779', 'x-cache': 'HIT', 'server': 'cloudflare'}` |
| model=flux | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | `{'content-type': 'image/jpeg', 'content-length': '42779', 'x-cache': 'HIT', 'server': 'cloudflare'}` |
| model=zimage | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | `{'content-type': 'image/jpeg', 'content-length': '42779', 'x-cache': 'HIT', 'server': 'cloudflare'}` |
| model_khong_ton_tai | 200 | image/jpeg | 42779 | 173c3d7d6d85d537 | `{'content-type': 'image/jpeg', 'content-length': '42779', 'x-cache': 'HIT', 'server': 'cloudflare'}` |

**Xác nhận:** yêu cầu KHÔNG truyền `model`, `model=flux`, `model=zimage`, và một tên model KHÔNG TỒN TẠI (`this-model-definitely-does-not-exist-xyz123`) đều trả về **CÙNG MỘT ảnh byte-for-byte giống hệt nhau**. Điều này chứng minh endpoint legacy ẩn danh **bỏ qua/chuẩn hoá tham số `model=`** — nó KHÔNG phân biệt được model hợp lệ với model bịa đặt, nên không thể coi bất kỳ tên model riêng lẻ nào là "đã xác nhận hoạt động ẩn danh" theo đúng nghĩa của nó.

**Đối chiếu tài liệu công khai (không dùng thông tin xác thực):** APIDOCS.md chính thức của Pollinations ([raw.githubusercontent.com/pollinations/pollinations/master/APIDOCS.md](https://raw.githubusercontent.com/pollinations/pollinations/master/APIDOCS.md)) ghi tham số `model` có giá trị mặc định là `flux` — đây là giá trị MẶC ĐỊNH CỦA THAM SỐ theo tài liệu, KHÔNG phải bằng chứng model nền thực sự chạy khi ẩn danh (vì cả tên model bịa đặt cũng cho ra ảnh giống hệt). Tài liệu cũng mô tả hệ thống bậc truy cập: Anonymous → "Basic models", Seed (đăng ký miễn phí) → "Standard models", Flower (trả phí) → "Advanced models", Nectar (doanh nghiệp) → "All models" — khớp với việc kontext/nanobanana/seedream bị chặn kèm thông điệp yêu cầu `enter.pollinations.ai`. Tài liệu KHÔNG mô tả rõ hành vi chuẩn hoá/bỏ qua tham số model quan sát được ở trên — đây là phát hiện THỰC NGHIỆM, không phải điều tài liệu xác nhận.

### Kết luận theo đúng yêu cầu

**CONFIRMED:**
- Sinh ảnh ẩn danh (không key) qua endpoint legacy hoạt động — trả về HTTP 200 + ảnh hợp lệ khi gọi endpoint này mà không có bất kỳ thông tin xác thực nào.

**NOT CONFIRMED:**
- flux hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.
- zimage hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.
- gpt-image-2 hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.
- Bất kỳ model nào khác được đặt tên (dreamshaper, turbo, gptimage, nanobanana-pro) hoạt động độc lập/ẩn danh với đúng đặc tính riêng của nó — tham số `model=` bị bỏ qua/chuẩn hoá ẩn danh nên không thể quy kết ảnh trả về là do model được yêu cầu tạo ra.

**UNIFIED API:**
- Sinh ảnh không key qua `gen.pollinations.ai` (endpoint hợp nhất) trả về HTTP 401 — yêu cầu xác thực.

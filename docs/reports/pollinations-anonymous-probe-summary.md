# Dò tìm model ảnh Pollinations hoạt động không cần API key

Prompt trung tính dùng xuyên suốt: `a red apple on a white background`

Tiêu chí thành công: HTTP 200 VÀ Content-Type bắt đầu bằng `image/` VÀ thân response không rỗng.

Đối chiếu endpoint UNIFIED (`gen.pollinations.ai`, không key): status=401, content-type='application/json', kết quả: THẤT BẠI — HTTP 401: {"success":false,"error":{"message":"Authentication required. Please provide an API key via Authorization header (Bearer token) or ?key= query parameter.","code":"UNAUTHORIZED","timestamp":"2026-08-15

## ⚠️ Phát hiện quan trọng — KHÔNG được ẩn giấu

Cả **7 model** trả về HTTP 200 + ảnh hợp lệ (dreamshaper, flux, gpt-image-2, gptimage, nanobanana-pro, turbo, zimage) đều cho ra **CÙNG MỘT ảnh byte-for-byte giống hệt nhau** (SHA256 rút gọn: `173c3d7d6d85d537`), dùng cùng prompt + seed.

Diễn giải: endpoint legacy ẩn danh (không key) dường như **bỏ qua tham số `model=`** và luôn phục vụ MỘT model mặc định/dự phòng cố định, bất kể tên model yêu cầu là gì. Theo tiêu chí thành công nghiêm ngặt đã định (HTTP 200 + `image/*` + không rỗng), các model này VẪN được tính là "thành công" — nhưng điều đó **không chứng minh model cụ thể đó thực sự chạy** ở chế độ ẩn danh. Cần xác minh thêm (có key hoặc qua tài liệu chính thức) trước khi kết luận các model này thực sự khả dụng ẩn danh với đúng đặc tính riêng của chúng.

## Bảng tổng hợp theo 4 nhóm

### 1. Xác nhận hoạt động KHÔNG cần key

| Model | Tỷ lệ thành công | Độ trễ TB (s) | HTTP vòng 1 | Ghi chú lỗi (nếu có) |
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

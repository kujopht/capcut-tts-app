# Frontend pre-production công khai (staging.fanfic.world)

Đây KHÔNG PHẢI production (`fanfic.world`). Mục tiêu: cho phép kiểm thử thủ
công toàn bộ Fanfic World (Admin V2, Trusted Video Sources, WebSub, ...) trên
trình duyệt/di động thật, nói chuyện với backend/Appwrite DEV.

## Kiến trúc

Tái sử dụng cơ chế triển khai Cloudflare Workers (OpenNext.js) đã có sẵn cho
production (`fanfic-web`, xem `web/wrangler.jsonc`) — KHÔNG dùng
`deploy/render.yaml` (chưa từng deploy thật, nhắm Appwrite Cloud staging,
không phải mục tiêu ở đây).

```
web/wrangler.staging.jsonc   -> Worker RIÊNG "fanfic-web-staging"
                                 Custom Domain: staging.fanfic.world
                                 (Cloudflare tự cấp DNS + TLS, không cần
                                 thao tác tay — khác hẳn backend GCE)
```

Build lại với biến môi trường trỏ backend DEV TRƯỚC khi deploy (biến này
đóng cứng vào bundle client lúc build, không đọc được lúc chạy):

```
NEXT_PUBLIC_API_BASE=https://api-dev.fanfic.world npm run cf:build
npx wrangler deploy --config wrangler.staging.jsonc
```

**KHÔNG BAO GIỜ chạy `npx wrangler deploy` KHÔNG có `--config
wrangler.staging.jsonc`** — lệnh trần sẽ đọc `wrangler.jsonc` mặc định và
deploy đè lên Worker **production** `fanfic-web`.

## Backend DEV cần biết staging tồn tại (CORS)

`server/.env` trên VM `fanfic-appwrite-temp` (container `fanfic-dev-api`,
xem `docs/DEV_PUBLIC_BACKEND.md`) đã thêm:

```
FAS_CORS_ORIGINS=https://staging.fanfic.world
```

Thiếu biến này thì mọi gọi API từ `staging.fanfic.world` bị trình duyệt chặn
CORS (không phải lỗi ứng dụng — xem `CORSMiddleware` trong `server/main.py`).

## Phát hiện khi kiểm thử (đáng chú ý, không phải lỗi ứng dụng)

- **Next.js Link-prefetch burst → 503 lẻ tẻ**: `AdminShell` hiển thị ~14 mục
  menu quản trị, mỗi mục là một `<Link>` — Next.js tự động prefetch RSC
  payload cho TẤT CẢ liên kết đang hiển thị cùng lúc khi trang tải xong. Khi
  nhiều prefetch bắn đồng thời tới CÙNG một Worker vừa tạo, một phần nhỏ
  nhận `503` từ Cloudflare. **Không ảnh hưởng người dùng thật**: đây là các
  request NỀN, ngầm — khi người dùng bấm THẬT vào một mục menu, trình duyệt
  tải lại bình thường (đã xác minh: mọi trang quản trị điều hướng TRỰC TIẾP
  đều trả về 200 với dữ liệu thật). Đáng theo dõi nếu Worker nhận lưu lượng
  thật lớn hơn, nhưng không phải blocker cho MVP riêng tư.
- **CSS cuộn ngang cục bộ ở thanh điều hướng mobile**: ĐÃ xác nhận từ đợt
  audit trước (`docs/reports/preprod-browser-qa.md`) là có chủ đích, không
  phải lỗi — xác nhận lại: `document.documentElement.scrollWidth ==
  clientWidth` tại 390px, không có tràn ngang thật của TRANG.

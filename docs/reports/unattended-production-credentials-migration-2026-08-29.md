# Kế hoạch chuyển sang vận hành production KHÔNG NGƯỜI TRỰC — 2026-08-29

Mục tiêu: sau **một** lần bootstrap có người, Claude deploy → Phase 15 → Phase 18
mà không cần ai chép credential từ trình duyệt nữa.

Nguyên tắc xuyên suốt: **giá trị bí mật không bao giờ đi qua context của model.**

## 1. Phân loại ba credential

| Credential | Loại | Hết hạn? | Ai giữ giá trị |
|---|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | **bootstrap**, ổn định | không | GitHub env `production` |
| `CLOUDFLARE_API_TOKEN` | **bootstrap**, ổn định | không (tự thu hồi được) | GitHub env `production` |
| `FANFIC_ADMIN_CANARY_TOKEN` | **runtime**, phiên người thật | **CÓ** | — (loại bỏ) |

Hai cái đầu là danh tính **máy**: tạo một lần, dùng mãi, thu hồi được độc lập.
Cái thứ ba là danh tính **người** — và đó chính là lỗi thiết kế.

## 2. Vì sao token phiên admin là design smell

| Vấn đề | Hệ quả thật |
|---|---|
| Hết hạn | CI hỏng định kỳ, không ai đoán trước được lúc nào |
| Cần đăng nhập tương tác | Không thể chạy không người trực — phá vỡ chính mục tiêu |
| Mang danh tính người | Mọi hành động của máy bị ghi nhận như do bạn làm |
| Quyền quá rộng | CI thừa hưởng TOÀN BỘ quyền admin: quản lý người dùng, kiểm duyệt, phân tích — trong khi chỉ cần vài route scraper |

## 3. Danh tính thay thế: canary dịch vụ tối thiểu quyền

**Đã cài đặt.**

```
FAS_CANARY_SERVICE_TOKEN   # token dịch vụ, không hết hạn, xoay vòng được
FAS_CANARY_USER_ID         # mặc định svc_canary — chủ sở hữu ổn định cho Novel canary tạo
```

Điểm thiết kế then chốt: canary **không** là một bậc trong `AdminRole`. Thang
quyền đó tuyến tính (`NONE < MODERATOR < ADMIN < OWNER`), nên "thêm một bậc dưới
ADMIN" sẽ hoặc thừa quyền, hoặc vô tình cấp cho MODERATOR thứ họ không được có.
Canary là một **năng lực trực giao**: chỉ các route scraper nhận nó, qua
`server/main.py::scraper_ops_profile`.

Ràng buộc được **kiểm thử**, không chỉ viết ra:

- `admin_role_of(canary_user_id)` luôn trả `NONE`, kể cả khi có admin/owner/moderator thật.
- Deployment chưa cấu hình (`FAS_CANARY_SERVICE_TOKEN` rỗng) **không** tự mở cửa cho request gửi chuỗi rỗng.
- So sánh token bằng `hmac.compare_digest` — hằng số thời gian.
- Cấu hình sai (`canary_user_id` trùng một người có đặc quyền) → **fail-closed**, từ chối xác thực thay vì cấp danh tính vừa-dịch-vụ-vừa-quản-trị. *(Phát hiện qua review bảo mật độc lập.)*
- `scraper_ops_profile` chỉ được xuất hiện trên route `/api/admin/scraper/*` — có test khoá phạm vi.

Canary **không** với tới được: quản lý người dùng, phân vai trò, kiểm duyệt,
phân tích, tài chính, hay bất kỳ thao tác xoá nào ngoài phần Phase 15 tự dọn.

## 4. Credential broker cục bộ

`scripts/fanfic_credential_broker.py` — lưu ở **Windows Credential Manager**
(`advapi32` CredRead/CredWrite qua `ctypes`, chỉ stdlib, không cài gói nào).

```bash
# MỘT bước có người, mỗi credential. Giá trị nhập ẩn (không hiện trên màn hình).
python scripts/fanfic_credential_broker.py store --name CLOUDFLARE_API_TOKEN

# Từ đây trở đi Claude chạy được, không cần biết giá trị.
python scripts/fanfic_credential_broker.py check --name CLOUDFLARE_API_TOKEN
python scripts/fanfic_credential_broker.py list
python scripts/fanfic_credential_broker.py push-github --name CLOUDFLARE_API_TOKEN
```

`push-github` chuyển giá trị thẳng từ credential store vào **stdin** của
`gh secret set`. Không argv, không file tạm, không stdout, không lịch sử shell,
không telemetry, không context model.

> **Đính chính quan trọng:** các lượt trước tôi đã hướng dẫn dùng
> `gh secret set --body-file <path>`. **Cờ đó không tồn tại** trên `gh secret set`
> (đã đối chiếu manual chính thức) — lệnh đó sẽ hỏng. Cách đúng là **bỏ `--body`**,
> `gh` sẽ đọc giá trị từ stdin. Bug này do review độc lập của Codex bắt được.

## 5. Đường tự động hoá theo provider

| Provider | Đường an toàn nhất sau bootstrap | Ghi chú |
|---|---|---|
| Render | Deploy Hook URL (POST, không tham số commit) | Không có CLI/API key cục bộ; hook là bootstrap một lần |
| Cloudflare | `opennextjs-cloudflare deploy` với token phạm vi hẹp | `Workers Scripts: Edit` + `Account Settings: Read`, đúng một account. Không Zone/DNS/R2/KV/D1 |
| GitHub | `gh secret set` qua broker (stdin) | Đã có phiên `gh` xác thực sẵn |
| Fanfic | `FAS_CANARY_SERVICE_TOKEN` | Danh tính dịch vụ, không phải phiên người |

## 6. Trạng thái CURRENT → TARGET

```
CURRENT
  người mở trình duyệt → copy 3 giá trị → dán vào GitHub UI
  Phase 15/18 dùng Bearer phiên của admin NGƯỜI THẬT (hết hạn, quyền rộng)
  → không thể chạy không người trực

TARGET
  bootstrap MỘT LẦN: broker store × 3  (giá trị nhập ẩn, vào OS credential store)
  broker push-github × 3               (stdin → gh, không qua model)
  Phase 15/18 dùng FAS_CANARY_SERVICE_TOKEN (không hết hạn, quyền hẹp, trực giao)
  → deploy → verify commit_sha → Phase 15 → Phase 18 chạy không cần người
```

## 7. Việc còn lại trước khi TARGET chạy trọn vẹn

1. **Bootstrap có người (một lần):** lấy 3 giá trị từ provider → `broker store` → `broker push-github`.
2. **Đặt `FAS_CANARY_SERVICE_TOKEN` trên Render** (biến môi trường của `fas-prod-api`) đúng bằng giá trị đã lưu, rồi deploy lại để có hiệu lực.
3. **Phase 15 còn một mảnh chưa chuyển:** kịch bản canary tạo Novel qua `/api/novels`, vốn dùng phiên người dùng thường chứ không phải route scraper. Cần mở rộng `scraper_ops_profile` (hoặc một dependency song song) sang đúng đường tạo/xoá Novel của canary. **Chưa làm** — đây là thay đổi auth, cần review riêng. Phase 18 thì đã chạy được với danh tính mới.

## 8. Ranh giới an toàn giữ nguyên

13 series thật được bảo vệ (cơ chế "chỉ xoá cái mình vừa tạo" không đổi), không
mass scrape, không tự xuất bản, không thao tác xoá tài nguyên cloud, không force
push, và canary **không** có quyền admin rộng.

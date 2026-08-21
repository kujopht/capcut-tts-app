# Báo cáo: Phase 2 — Browser QA thật (Overnight Hardening V1)

Nguồn: kiểm tra trực tiếp bằng Chrome DevTools MCP trên `chore/preprod-overnight-hardening-v1`,
backend mock (`DATA_BACKEND=mock`) tại `localhost:8010`, frontend `next dev` tại `localhost:3010`
(cổng lệch chuẩn 8000/3000 để không đụng phiên dev khác đang chạy).

## Phạm vi đã kiểm

| Hạng mục | Trạng thái |
|---|---|
| Trang chủ `/` (khách + đã đăng nhập, desktop + mobile 390×844) | Sạch |
| `/fanfic` (Khám phá, desktop + mobile) | Sạch |
| `/animation` | Sạch |
| `/community` | Sạch |
| `/library` (khách) | Sạch |
| `/write` (khách → redirect `/login?next=/write` đúng) | Sạch |
| Đăng ký tài khoản mới qua UI (mock) → tự đăng nhập → vào `/write` | Sạch |
| `/studio`, `/account` (đã đăng nhập) | Sạch |
| `/admin` (tài khoản thường, không quyền) | Đúng hành vi: 403 + "Tài khoản này không có quyền quản trị." |

Với mọi trang trên: không có console error/warning nào ngoài các mục ghi ở dưới.

## Phát hiện

### 1. (Không phải bug) CORS lệch cổng khi QA thủ công

Lần tải trang đầu tiên trên `localhost:3010` báo lỗi CORS khi gọi
`/api/novels`, `/api/novels/tags`, `/api/auth/me`. Nguyên nhân: `server/.env`
đặt `FAS_CORS_ORIGINS=http://localhost:3000` (giá trị đúng cho dev chuẩn),
nhưng backend QA phiên này được khởi động ở cổng 8010/3010 để tránh xung đột
với phiên dev khác. Đã khởi động lại backend với biến môi trường tiến trình
`FAS_CORS_ORIGINS=http://localhost:3010` (không sửa file `.env`) — hết lỗi
ngay. **Không phải lỗi trong code**, chỉ là artefact của việc chọn cổng thay
thế trong phiên QA này.

### 2. (Đã xác minh, không phải bug) Thanh điều hướng chính có thể cuộn ngang ở mobile

Ở 390px, các mục "Trang chủ / Khám phá / Animation / Cộng đồng / Thư viện"
rộng hơn khung nhìn và bị cắt ở lề phải trong ảnh chụp màn hình. Đã đo bằng
`document.documentElement.scrollWidth` (485px) so với `window.innerWidth`
(500px, gồm thanh cuộn ảo của DevTools) — **toàn trang không cuộn ngang**,
chỉ riêng thanh điều hướng có `overflow-x` cục bộ (mẫu tab-cuộn-ngang có chủ
đích, phổ biến ở nav mobile). SẠCH, không cần sửa.

### 3. Cổng quản trị (`/admin`) từ chối đúng tài khoản không có quyền

Tài khoản mock mới đăng ký nhận đúng `403 Forbidden` từ backend và trang
hiển thị thông báo thân thiện thay vì lỗi chung — hành vi đúng như thiết kế
Admin Control Center V2.

## Giới hạn của lần kiểm này

- Chưa đăng nhập được vai trò `admin`/`owner`/`moderator` thật để chụp giao
  diện các trang `/admin/*` bên trong (Admin Control Center V2, Trusted Video
  Sources, Import Queue…) — mock backend hiện có `admin_count: 0`, cần thao
  tác nâng quyền thủ công (ngoài phạm vi "chỉ đọc, không đổi dữ liệu thật"
  của một buổi QA nhanh) hoặc một cách bootstrap tài khoản admin trong mock
  store mà phiên này chưa tìm ra một cách an toàn, không phá dữ liệu.
- Không kiểm trình đọc màn hình (screen reader) thật, chỉ dựa vào cây a11y
  snapshot của Chrome DevTools.
- Không kiểm trên trình duyệt Safari/thiết bị thật, chỉ Chromium qua MCP.

## Kết luận

Không phát hiện bug console/render nào ở các trang công khai và luồng
đăng ký/đăng nhập/điều hướng đã kiểm. Hai mục ở trên đều xác nhận là hành vi
đúng hoặc artefact của môi trường QA, không phải lỗi sản phẩm.

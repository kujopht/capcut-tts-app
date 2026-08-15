# Web Hardening V1 — báo cáo tổng kết (overnight build)

Nhánh: `chore/web-hardening-v1`, branch từ `feature/animation-v6` (`79ba675`).
Chưa merge, chưa deploy, chưa chạm production Appwrite.

## Phạm vi đã kiểm

- Backend: toàn bộ `server/main.py` (4641 dòng) — CORS, xác thực admin, IDOR,
  rate limit, timeout HTTP, lộ secret, giới hạn payload.
- Frontend tĩnh: `web/src/` — TypeScript escape hatch (`any`/`@ts-ignore`/
  `as unknown as`), biến môi trường phía client, `dangerouslySetInnerHTML`,
  dọn dẹp `addEventListener`/`setInterval`.
- Frontend động: 12 route chính (`/`, `/fanfic`, `/translate`, `/animation`,
  `/leaderboard`, `/library`, `/write`, `/studio`, `/tools/subtitles`,
  `/community`, `/account`, `/admin`) qua trình duyệt thật ở 3 breakpoint
  (1440/768/375), console, network, khả năng tiếp cận, focus.

Cố tình KHÔNG đụng vào: `web/src/app/image-studio/`, `server/image_*.py`
(thuộc `feature/image-studio-v1`, đã đóng băng riêng).

## Lỗi tìm thấy và đã sửa

**Thiếu trang 404 tiếng Việt** (`web/src/app/`) — mọi URL không khớp route
nào rơi vào trang 404 mặc định tiếng Anh của Next ("This page could not be
found."), lạc tông với phần còn lại của site (mọi empty-state khác đều dùng
component `EmptyState` + tiếng Việt).

→ **Đã sửa** (commit `cf8ae30`): thêm `web/src/app/not-found.tsx` (34 dòng),
tái dùng nguyên `EmptyState` có sẵn, dẫn về trang chủ. Render bên trong root
layout nên header/nav vẫn còn — không cần viết lại `<html>/<body>`.

## Đã kiểm kỹ — không tìm thấy vấn đề

| Hạng mục | Kết quả |
|---|---|
| CORS | `server/config.py` chặn wildcard `"*"` khi không phải development — không lỗ hổng |
| Xác thực admin | Toàn bộ route `/api/admin/*` đều qua `Depends(admin_profile)` — không route nào thiếu |
| IDOR | Mọi thao tác ghi (novel/chapter/post) đều qua `store.owned_*`/kiểm quyền service trước |
| Timeout HTTP | Mọi `httpx.Client(...)` ra ngoài đều có `timeout=` tường minh |
| Lộ secret | `/api/health`/`/api/ready` chỉ trả boolean/tên lỗi, không giá trị bí mật |
| Giới hạn payload | `MAX_CHAPTER_CHARS`, `CoverIn.base64`, `NoteIn.note` đều có giới hạn |
| TypeScript escape hatch | 0 kết quả `any`/`@ts-ignore`/`@ts-expect-error`/`as unknown as` trong `web/src` |
| Biến môi trường phía client | Chỉ `NEXT_PUBLIC_API_BASE` — không có biến bí mật nào lộ |
| `dangerouslySetInnerHTML` | 0 kết quả |
| Dọn listener/interval | 13 nơi dùng `addEventListener`/`setInterval` — tất cả đều có cleanup tương ứng |
| Tràn ngang | Không tràn ở 375/768/1440px trên 12 route đã kiểm |
| Focus/khả năng tiếp cận | Focus hiển thị đúng; N+1 request đã được sửa ở đợt audit trước (`docs/UI_AUDIT.md`) |

## Đã ghi nhận nhưng KHÔNG sửa (quyết định sản phẩm, không phải bug)

- `metadataBase` chưa đặt trong `web/src/app/layout.tsx` — chỉ là cảnh báo
  build (không phải lỗi), cần URL production thật mà production chưa
  deploy. Để nguyên cho tới khi có domain thật.
- Chưa có CSP/security header trong `next.config.mjs` — thêm mù mà không
  kiểm hết tài nguyên ngoài (R2, Appwrite, ảnh) là rủi ro TỰ gây lỗi (chặn
  nhầm tài nguyên hợp lệ); cần một đợt audit riêng, có kiểm thử đầy đủ, chứ
  không phải sửa vội trong đợt này.

## Việc đã chặn bởi production Appwrite

Không có — đợt audit này không chạm phần nào phụ thuộc trực tiếp Appwrite
production; mọi kiểm tra đều chạy trên mock/dev.

## Kết quả kiểm chứng cuối (chạy thật, xác nhận độc lập)

- Backend: `Ran 1955 tests in ~55-61s — OK (skipped=1)`
- `npm run typecheck`: sạch, không lỗi.
- `npm run lint`: sạch, không lỗi/cảnh báo.
- `npm test`: `tests 563, pass 563, fail 0`.
- `npm run build`: thành công — route `/_not-found` mới xuất hiện, không có
  route `image-studio` nào (xác nhận đúng nhánh, không lẫn công việc khác).

Git: 1 commit (`cf8ae30`) trên `chore/web-hardening-v1`, working tree sạch,
chưa push lúc audit xong (đã push ngay sau khi xác minh xong — xem lịch sử
commit để biết SHA cuối).

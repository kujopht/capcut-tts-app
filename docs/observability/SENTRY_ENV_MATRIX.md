# Ma trận biến môi trường Sentry

Tài liệu này **chỉ ghi tên biến và nơi đặt, không ghi giá trị nào**. Giá trị thật nằm trong trình quản lý biến của host backend và trong biến repo GitHub, không bao giờ nằm trong kho mã.

Trạng thái hôm nay (2026-09-28): **chưa bật ở production**. Không DSN nào được đặt ở production, và các cờ `FAS_SUPPORT_V1` / `NEXT_PUBLIC_SUPPORT_ENABLED` vẫn **TẮT**.

## Backend (FastAPI, biến môi trường của host backend)

| Biến | Loại | production | staging | development | Ghi chú |
|---|---|---|---|---|---|
| `FAS_SENTRY_DSN` | DSN của project `python-fastapi` (toạ độ công khai, vẫn để trong env) | đặt khi chủ dự án bật | có thể đặt | để trống | Trống thì `sentry_sdk` **không được import** (đã đo). Không dùng `SENTRY_DSN` |
| `FAS_ENV` (đã có sẵn) | `production` / `staging` / `development` | `production` | `staging` | `development` | **Chính là "SENTRY_ENVIRONMENT"**: `environment` của Sentry lấy từ đây. Giá trị lạ quy về `development`. Đặt `SENTRY_ENVIRONMENT` không có tác dụng |
| `FAS_BUILD_SHA` hoặc `RENDER_GIT_COMMIT` | SHA commit | host tự đặt | host tự đặt | tuỳ chọn | Release `fanfic-api@<sha12>`, tag `build` |
| `FAS_SENTRY_TRACES_SAMPLE_RATE` | số 0–1 | để trống (0) | để trống | để trống | Mặc định 0, trần cứng 0,2 |
| `FAS_SUPPORT_SENTRY_TOKEN` | **BÍ MẬT**, token read-only (`event:read`, `org:read`, `project:read`) | **để trống** cho tới khi bật AI Support | có thể đặt | để trống | Chỉ backend dùng (#245). Không vào log, phản hồi API hay lời nhắn gửi mô hình; mỗi điều có bài test |
| `FAS_SUPPORT_SENTRY_ORG` | slug tổ chức Sentry (không phải bí mật; lấy từ URL Sentry) | đi cùng token | đi cùng token | — | Phải khớp mẫu slug `[a-z0-9-]` |
| `FAS_SUPPORT_SENTRY_PROJECTS` | danh sách slug | `fanfic-web,python-fastapi` | như production | — | Chỉ các project trong danh sách này được tra |
| `FAS_SUPPORT_SENTRY_BASE` | URL gốc | để trống (`https://sentry.io`) | để trống | — | Chỉ nhận `sentry.io`, `us.sentry.io`, `de.sentry.io` |

Công cụ tra Sentry của AI Support chỉ chạy khi có **đủ** ba biến `FAS_SUPPORT_SENTRY_TOKEN`, `_ORG`, `_PROJECTS`, **và** route Support đã bật (`FAS_SUPPORT_V1=1`).

## Web (Next.js, gắn vào bundle lúc build)

| Biến | Đặt ở đâu | production | staging | development | Ghi chú |
|---|---|---|---|---|---|
| `SENTRY_DSN_WEB` | **Biến** repo GitHub Actions, không phải secret (DSN là toạ độ công khai) | đặt khi chủ dự án bật | — | — | Chỉ bước build web đọc biến này |
| `NEXT_PUBLIC_SENTRY_DSN` | `env:` của bước "Cloudflare deploy (frontend)" trong `production-deploy.yml`, giá trị `${{ vars.SENTRY_DSN_WEB }}` | như bên trái | biến build staging (nếu dựng lại) | để trống | Trống thì không có trình nghe, không import, không gửi (đo trên Chrome: 0 request, 0 chunk, không có `window.__SENTRY__`) |
| `NEXT_PUBLIC_SENTRY_ENV` | cùng bước build | `production` | `staging` | để trống, tức `development` | **Không bao giờ tự thành `production`** |
| `NEXT_PUBLIC_BUILD_SHA` | tự động (`next.config.mjs::maBuild`, lấy từ `git rev-parse`) | tự động | tự động | tự động | Release `fanfic-web@<sha10>` |

Chủ dự án thêm hai dòng này vào bước build frontend khi muốn bật web. PR Sentry cố ý **không** sửa workflow deploy:

```yaml
          NEXT_PUBLIC_SENTRY_DSN: ${{ vars.SENTRY_DSN_WEB }}
          NEXT_PUBLIC_SENTRY_ENV: production
```

## Không bao giờ

- **Token Sentry** (read-only hay loại khác) **không được** nằm trong biến `NEXT_PUBLIC_*`, trong `env:` của bước build/deploy web, trong biến Wrangler/Cloudflare, hay trong `web/.env*`. Bài test `web/tests/sentry-web.test.mjs` quét `web/src` và `next.config.mjs`:
  - chỉ `NEXT_PUBLIC_SENTRY_DSN` và `NEXT_PUBLIC_SENTRY_ENV` được phép;
  - không được nhắc tới tên biến token nào.
- **Không dùng lại token read-only cho CI.** Nếu sau này cần upload source map:
  - tạo một token **riêng**, chỉ có quyền upload, đặt làm secret CI `SENTRY_AUTH_TOKEN`;
  - xoá tệp `.map` trước khi deploy.

  Xem `SENTRY.md`.

## Thứ tự bật đề xuất (chủ dự án)

1. Backend: đặt `FAS_SENTRY_DSN`. `FAS_ENV=production` đã có sẵn.
2. Web: đặt biến repo `SENTRY_DSN_WEB`, thêm hai dòng YAML ở trên, rồi deploy bằng lệnh tường minh `cf:deploy:production`.
3. **Chỉ khi** bật AI Support trên production: đặt ba biến `FAS_SUPPORT_SENTRY_*` ở backend.

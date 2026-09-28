# Sentry — web (`fanfic-web`) và API (`python-fastapi`)

Trạng thái: **TẮT mặc định** ở cả hai phía. Không có DSN thì không nghe lỗi, không tải SDK, không gửi gì.

| Phía | Bật bằng | Nơi đặt | Môi trường |
|---|---|---|---|
| API (FastAPI) | `FAS_SENTRY_DSN` | Biến môi trường backend (Render) | `FAS_ENV`: development / staging / production |
| Web (Next.js trên Workers) | `NEXT_PUBLIC_SENTRY_DSN` lúc build | Bước build web của `production-deploy.yml` (xem dưới) | `NEXT_PUBLIC_SENTRY_ENV`; không đặt = `development`, không bao giờ tự thành `production` |

**PR này không sửa đường deploy production.** Khi chủ dự án muốn bật Sentry web trên production, thêm hai dòng vào `env:` của bước "Cloudflare deploy (frontend)" trong `.github/workflows/production-deploy.yml`, và đặt biến repo `SENTRY_DSN_WEB` (DSN của `fanfic-web`, là toạ độ công khai):

```yaml
          NEXT_PUBLIC_SENTRY_DSN: ${{ vars.SENTRY_DSN_WEB }}
          NEXT_PUBLIC_SENTRY_ENV: production
```

Phía API: đặt `FAS_SENTRY_DSN` (DSN của `python-fastapi`) trong biến môi trường của backend production. `FAS_ENV=production` đã có sẵn.

DSN là toạ độ **công khai** (Sentry thiết kế nó để nằm trong trình duyệt), không phải token. **Không token Sentry nào** đi vào web hay vào workflow deploy.

## Không bao giờ gửi

Hai lớp độc lập ở mỗi phía: tuỳ chọn của SDK ở mức chặt nhất, rồi `beforeSend` / `before_send` lọc thêm. Làm sạch hỏng thì **bỏ** sự kiện, không gửi bản thô.

- Cookie (`request.cookies`, header `Cookie`/`Set-Cookie`), thân request.
- Mọi header ngoài danh sách cho phép:
  - API: `user-agent`, `content-type`, `content-length`, `accept`, `accept-language`, `host`, `x-request-id`, `cf-ray`;
  - web: `user-agent`, `accept-language`, `content-type`.
- `Authorization`, `X-Appwrite-*`, Bearer token, JWT, khoá Appwrite `standard_…`, Tencent **UserSig**, và cặp `key=value` bí mật.
- **Query string và fragment của mọi URL.** Bao gồm URL ký R2 (`X-Amz-Signature`/`Credential`), mã OAuth `?code=`, token trên link.
- Email, IP, `user.*`. Phía API thay `user.id` bằng băm ẩn danh.
- Biến cục bộ của stack frame. Các dòng ngữ cảnh mã nguồn cũng qua bộ lọc.

Sentry JS 11 thay `sendDefaultPii` bằng `dataCollection`, và **mặc định của nó thoáng** (thu user, cookie, header, body, query, biến cục bộ). Mọi mục đều được đặt ở mức chặt nhất trong `web/src/lib/observability/sentry-lazy.ts`.

## Ít ồn

- **API:** chỉ lỗi 5xx và ngoại lệ chưa bắt. Log `logging` chỉ là breadcrumb, không thành sự kiện. Tracing mặc định **0**, trần 0,2 (`FAS_SENTRY_TRACES_SAMPLE_RATE`).
- **Web:** SDK chỉ nạp khi đã có lỗi thật, qua **một** điểm `import()`. Tối đa 10 sự kiện mỗi lần tải trang, mỗi chữ ký lỗi gửi một lần. Bỏ lỗi từ tiện ích trình duyệt và tệp khác nguồn. Không tracing, không replay, không ping phiên.

## Release và build SHA

- **API:** `fanfic-api@<sha12>` từ `FAS_BUILD_SHA` hoặc `RENDER_GIT_COMMIT`; tag `service`, `build`.
- **Web:** `fanfic-web@<sha10>` từ `NEXT_PUBLIC_BUILD_SHA` (`next.config.mjs::maBuild`); tag `service`, `build`, `nguon`.

## Source map

**Chưa cấu hình, có chủ đích.** Repo chưa có secret CI nào cho Sentry (không có token `project:releases` / `project:write`). Token read-only hiện có không upload được, và cũng không nên đưa nó vào CI. Khi chủ dự án muốn có stack trace đã giải mã:

1. Tạo một **Organization Auth Token** riêng, chỉ có scope upload source map, và đặt vào secret CI `SENTRY_AUTH_TOKEN`. Không dùng lại token read-only.
2. Trong bước build web production, **sau** `next build`: `sentry-cli sourcemaps inject` rồi `upload` thư mục `.next/static`, với `--release fanfic-web@<sha10>`.
3. **Xoá** các tệp `.map` khỏi bản build trước khi deploy, để Cloudflare không phục vụ source map công khai.

Lưu ý: `@sentry/nextjs` trên Cloudflare Workers/OpenNext hiện vẫn ở mức alpha (sentry-javascript #14931, #18843, #19213). Vì thế phía web dùng `@sentry/browser` ở trình duyệt, và **không** đưa SDK vào worker.

## Đã kiểm thật (2026-09-28, môi trường `staging`)

| Hạng mục | Kết quả |
|---|---|
| API | Lỗi tổng hợp qua app FastAPI thật → sự cố `PYTHON-FASTAPI-1` sau 14 giây. Query `<redacted>`; header chỉ còn `Accept`/`Host`/`User-Agent`; cookie rỗng; thông điệp đã che. **Không lộ bí mật.** |
| Web | Chrome QA hiện, URL có `?token=&code=`, ném một lỗi → sự cố `FANFIC-WEB-1`. Trước lỗi: 13 JS, 0 request Sentry. Sau lỗi: +1 chunk lười, 1 envelope. URL còn `http://localhost:3020/`, header chỉ `User-Agent`. **Không lộ bí mật.** |

## Rollback

Xoá DSN (hoặc biến repo `SENTRY_DSN_WEB`) rồi deploy lại: cả hai phía trở về trạng thái hoàn toàn tắt. Không có migration, không có dữ liệu cần dọn.

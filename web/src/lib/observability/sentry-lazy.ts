/**
 * Phần NẶNG của Sentry web — CHỈ được nạp qua `import()` trong `components/SentryGate.tsx`, và
 * chỉ khi đã có một lỗi thật cần gửi. Trang không lỗi thì không bao giờ tải SDK (~vài chục KB).
 *
 * Bỏ các tích hợp tự bắt/tự thu: `GlobalHandlers` (cổng tự nghe lỗi), `Breadcrumbs` (console/
 * fetch/điều hướng — mang URL có query), `BrowserSession` (ping phiên — ồn), `BrowserApiErrors`.
 * Không tracing, không replay.
 */
import * as Sentry from "@sentry/browser";
import { BUILD_SHA, SENTRY_DSN, SENTRY_ENV } from "./config";
import { lamSachBreadcrumb, lamSachSuKien } from "./scrub";

export const TICH_HOP_BO = ["GlobalHandlers", "Breadcrumbs", "BrowserSession", "BrowserApiErrors"];

let daKhoiTao = false;

function khoiTao(): void {
  if (daKhoiTao || !SENTRY_DSN) return;
  daKhoiTao = true;
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENV,
    release: `fanfic-web@${BUILD_SHA}`,
    sampleRate: 1.0,
    tracesSampleRate: 0,
    // Sentry JS 11 thay `sendDefaultPii` bằng `dataCollection` — và MẶC ĐỊNH của nó THOÁNG (thu
    // user, cookie, header, body, query, biến cục bộ). Đặt TỪNG mục ở mức chặt nhất; `beforeSend`
    // vẫn lọc thêm một lớp nữa.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: { request: { allow: ["user-agent", "accept-language", "content-type"] }, response: false },
      httpBodies: [],
      urlQueryParams: false,
      graphQL: { document: false, variables: false },
      genAI: { inputs: false, outputs: false },
      databaseQueryData: false,
      queues: false,
      stackFrameVariables: false,
    },
    maxBreadcrumbs: 20,
    integrations: (macDinh) => macDinh.filter((i) => !TICH_HOP_BO.includes(i.name)),
    beforeSend: (ev) => lamSachSuKien(ev),
    beforeBreadcrumb: (b) => lamSachBreadcrumb(b),
    initialScope: { tags: { service: "fanfic-web", build: BUILD_SHA } },
  });
}

export function baoLoi(loi: unknown, nguon: string): void {
  khoiTao();
  if (!daKhoiTao) return;
  Sentry.captureException(loi, { tags: { nguon } });
}

/** @type {import('next').NextConfig} */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// CHI dung de NOI LONG CSP cho `next dev` (Turbopack HMR can `eval()` +
// websocket cung goc) — KHONG BAO GIO anh huong toi build production. Phat
// hien qua QA trinh duyet THAT: thieu dong nay lam CSP chan `eval()` cua
// React dev mode, khien TOAN BO trang trang trong o `next dev`.
const isDev = process.env.NODE_ENV !== "production";

/**
 * Content-Security-Policy — truoc day KHONG co CSP nao ca (xac nhan qua audit
 * `docs/UI_AUDIT.md`/`docs/reports/web-hardening-v1-summary.md`). Day la
 * BASELINE dau tien, khong phai chi nhung dieu chinh cho YouTube — mot CSP
 * chi lock `frame-src` ma bo qua moi thu khac thi khong bao ve gi ca.
 *
 * `frame-src`/`connect-src`/`script-src` cho YouTube CHI mo dung hai domain
 * can thiet: `www.youtube-nocookie.com` (iframe nhung, xem
 * `YouTubeFacadePlayer.tsx`) va `www.youtube.com` (script bootstrap cua
 * YouTube IFrame API, xem `youtubeIframeApi.ts` — KHONG dung de nhung, chi de
 * doc vi tri phat qua mot iframe DA co san). Khong mo `*.youtube.com` hay
 * `*.google.com` rong hon muc nay.
 *
 * `img-src`/`style-src`/`script-src` co `'unsafe-inline'`/`https:` RONG HON
 * mot CSP nghiem ngat ly tuong — day la DANH DOI CO Y, khong phai so sot:
 * - `img-src https:`: anh bia/avatar den tu R2 (domain dong theo tai khoan
 *   Cloudflare, khong co mot chuoi co dinh de liet ke), va anh CHI la du lieu
 *   hien thi — khong the thuc thi JS qua the <img>, nen day la huong nhuong
 *   bo pho bien ke ca trong CSP chat.
 * - `script-src`/`style-src` co `'unsafe-inline'`: Next.js tu chen script
 *   hydrate + nhieu the ung dung dung `style={{...}}` truc tiep — CSP nonce
 *   that can mot lop middleware rieng de gan nonce vao tung request, ngoai
 *   pham vi ban va cua lan sua nay (chi cung co YouTube). Ghi lai o day de
 *   khong ai tuong day la CSP tuyet doi nghiem ngat.
 *
 * `object-src 'none'`/`frame-ancestors 'self'`/`base-uri 'self'` la ba dong
 * "re va luon dung" — khoa Flash/plugin cu, chan site khac nhung Fanfic vao
 * iframe cua ho (clickjacking), chan doi `<base href>` bang JS injection.
 */
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' https://www.youtube.com${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' https: data: blob:",
  "font-src 'self' data:",
  // `next dev` (Turbopack) mo mot WebSocket HMR CUNG GOC voi trang — 'self'
  // trong CSP KHONG tu bao gom scheme `ws:`, phai liet ke rieng, chi trong dev.
  `connect-src 'self' ${API_BASE}${isDev ? " ws://localhost:* ws://127.0.0.1:*" : ""}`,
  "frame-src 'self' https://www.youtube-nocookie.com",
  "media-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self'",
].join("; ");

const nextConfig = {
  reactStrictMode: true,
  // Backend giu moi bi mat. Bien duy nhat lo ra trinh duyet la URL API.
  env: {
    NEXT_PUBLIC_API_BASE: API_BASE,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};
export default nextConfig;

/**
 * Bieu tuong Google va Facebook.
 *
 * Ve bang SVG noi tuyen, KHONG tai tu CDN cua nha cung cap: mot the `<img>`
 * tro ra ngoai se bao cho ho biet ai dang xem trang dang nhap cua Fanfic
 * World, ngay ca khi nguoi do khong bam vao nut nao.
 *
 * Mau THUONG HIEU cua hai nha cung cap la ngoai le duy nhat cho quy tac
 * "khong hex trong .tsx": day khong phai mau cua giao dien Fanfic ma la mau
 * nhan dien cua ben thu ba — dat chung vao token cua he thiet ke se ngu y
 * chung thuoc bang mau cua ta va co the bi doi theo theme.
 */

export function GoogleIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="#4285F4"
        d="M45.1 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h11.8c-.5 2.7-2 5-4.4 6.6v5.5h7.1c4.2-3.8 6.6-9.5 6.6-16.1z"
      />
      <path
        fill="#34A853"
        d="M24 46c5.9 0 10.9-2 14.5-5.4l-7.1-5.5c-2 1.3-4.5 2.1-7.4 2.1-5.7 0-10.6-3.9-12.3-9.1H4.4v5.7C8 41.1 15.4 46 24 46z"
      />
      <path
        fill="#FBBC05"
        d="M11.7 28.1c-.4-1.3-.7-2.7-.7-4.1s.3-2.8.7-4.1v-5.7H4.4A22 22 0 0 0 2 24c0 3.6.9 6.9 2.4 9.8l7.3-5.7z"
      />
      <path
        fill="#EA4335"
        d="M24 10.8c3.2 0 6.1 1.1 8.4 3.3l6.3-6.3C34.9 4.1 29.9 2 24 2 15.4 2 8 6.9 4.4 14.2l7.3 5.7c1.7-5.2 6.6-9.1 12.3-9.1z"
      />
    </svg>
  );
}

export function FacebookIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="#1877F2"
        d="M46 24C46 11.85 36.15 2 24 2S2 11.85 2 24c0 10.98 8.04 20.08 18.56 21.73V30.36h-5.59V24h5.59v-4.85c0-5.51 3.28-8.56 8.31-8.56 2.41 0 4.92.43 4.92.43v5.41h-2.77c-2.73 0-3.58 1.7-3.58 3.44V24h6.09l-.97 6.36h-5.12v15.37C37.96 44.08 46 34.98 46 24z"
      />
      <path
        fill="#FFFFFF"
        d="M32.55 30.36 33.52 24h-6.09v-4.13c0-1.74.85-3.44 3.58-3.44h2.77v-5.41s-2.51-.43-4.92-.43c-5.03 0-8.31 3.05-8.31 8.56V24h-5.59v6.36h5.59v15.37a22.2 22.2 0 0 0 6.88 0V30.36h5.12z"
      />
    </svg>
  );
}

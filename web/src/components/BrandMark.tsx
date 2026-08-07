/**
 * Bieu tuong dung cho anh sinh o phia may chu (`ImageResponse` / Satori).
 *
 * Tach rieng khoi `components/Logo.tsx` vi Satori chi hieu mot tap con cua
 * SVG: khong `<defs>` dung lai qua `url(#id)` an toan, khong `currentColor`.
 * Nen o day moi mau deu ghi thang.
 *
 * Hinh khoi PHAI khop `components/Logo.tsx` va `app/icon.svg` — mot bieu
 * tuong duy nhat cho ca san pham.
 */
export function BrandMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32">
      <defs>
        <linearGradient id="brandMark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7c8cff" />
          <stop offset="1" stopColor="#4dd6c1" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#brandMark)" />
      <g
        transform="translate(4.81 5.12) scale(0.7)"
        fill="#0b0d12"
        stroke="#0b0d12"
        strokeLinejoin="round"
      >
        <rect x="8.4" y="9.2" width="3.2" height="4.4" rx="1.6" stroke="none" />
        <rect x="14.4" y="3.4" width="3.2" height="10.2" rx="1.6" stroke="none" />
        <rect x="20.4" y="7.2" width="3.2" height="6.4" rx="1.6" stroke="none" />
        <path d="M4.6 16.4 14.6 18 14.6 26.8 4.6 25.2Z" strokeWidth="1.8" />
        <path d="M27.4 16.4 17.4 18 17.4 26.8 27.4 25.2Z" strokeWidth="1.8" />
      </g>
    </svg>
  );
}

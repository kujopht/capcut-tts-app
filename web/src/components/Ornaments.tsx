/**
 * Hoạ tiết SVG NGUYÊN BẢN — dùng RẤT tiết chế (Visual Bible V1, mục 7).
 *
 * BA nguyên tắc:
 *
 *   1. Trừu tượng, không sao chép biểu tượng của bất kỳ franchise nào.
 *   2. `stroke="currentColor"`/`fill="currentColor"` — không tự đặt mã màu ở
 *      đây (test đã khoá quy tắc này cho `NavIndicator.tsx`/`NavAuth.tsx`,
 *      giữ cùng kỷ luật cho mọi component mới). Màu do component cha quyết
 *      định qua CSS `color`.
 *   3. Tĩnh — không `<animate>`, không CSS animation riêng. Đây là trang trí
 *      công nhận (ornament), không phải hiệu ứng chuyển động.
 */

/** Đường chia mảnh, sáng dần vào giữa — thay cho `<hr>` phẳng giữa các khối lớn. */
export function CelestialDivider({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 240 16"
      width="240"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <line x1="0" y1="8" x2="100" y2="8" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1" />
      <line x1="140" y1="8" x2="240" y2="8" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1" />
      <path
        d="M120 2 L124 8 L120 14 L116 8 Z"
        fill="currentColor"
        fillOpacity="0.6"
      />
    </svg>
  );
}

/** Góc phép nhỏ — dùng tối đa MỘT lần mỗi màn hình, cho khung quan trọng nhất. */
export function CornerRune({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 40 40"
      width="40"
      height="40"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M2 14 V4 H12"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <circle cx="2" cy="2" r="1.6" fill="currentColor" fillOpacity="0.8" />
    </svg>
  );
}

/** Truyện — trang sách hé mở, một nét sáng đi qua giữa. */
export function MotifManuscript({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 120"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid slice"
    >
      <path
        d="M80 18 C58 8 30 8 14 16 V96 C30 88 58 88 80 98 C102 88 130 88 146 96 V16 C130 8 102 8 80 18 Z"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
      />
      <path d="M80 18 V98" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" />
      <path d="M26 32 H62 M26 46 H58 M26 60 H62" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" />
      <path d="M98 32 H134 M102 46 H134 M98 60 H130" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" />
    </svg>
  );
}

/** Animation — khung chiếu điện ảnh, viền lỗ phim hai bên. */
export function MotifFilmFrame({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 120"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid slice"
    >
      <rect x="30" y="14" width="100" height="92" rx="4" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" />
      {[22, 42, 62, 82].map((y) => (
        <g key={y}>
          <rect x="14" y={y} width="10" height="10" rx="2" fill="currentColor" fillOpacity="0.35" />
          <rect x="136" y={y} width="10" height="10" rx="2" fill="currentColor" fillOpacity="0.35" />
        </g>
      ))}
      <path d="M68 46 L96 60 L68 74 Z" fill="currentColor" fillOpacity="0.55" />
    </svg>
  );
}

/** Audio — sóng âm dịu dưới trăng. */
export function MotifWaveform({ className }: { className?: string }) {
  const bars = [6, 12, 20, 14, 26, 16, 22, 10, 18, 8];
  return (
    <svg
      className={className}
      viewBox="0 0 160 60"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      {bars.map((h, i) => (
        <rect
          key={i}
          x={8 + i * 15}
          y={30 - h / 2}
          width="6"
          height={h}
          rx="3"
          fill="currentColor"
          fillOpacity={0.35 + (i % 3) * 0.1}
        />
      ))}
    </svg>
  );
}

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

/**
 * Cộng đồng, trạng thái RỖNG — một bếp lửa trại yên tĩnh, chưa ai quây quần
 * (Phase 3.6 Phần U). Trừu tượng: vài nét lửa mảnh + ba khúc củi, không phải
 * biểu tượng lửa trại clip-art.
 */
export function MotifCampfire({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 120"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path
        d="M80 84 C68 84 58 76 58 64 C58 72 64 76 68 74 C64 64 68 50 80 40 C74 54 78 60 84 56 C88 48 84 40 80 32 C96 42 102 56 96 70 C100 66 100 60 98 56 C104 64 104 76 92 82 C88 84 84 84 80 84 Z"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M46 96 L74 86 M114 96 L86 86 M80 100 V86" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Explore (PageHero V1) — cung la ban do va mot vong compa mo, "kham pha
 * the gioi" chu khong phai minimap RPG: chi mot cung tron khong khep kin +
 * vai net do vach dam huong, khong kim chi nam, khong chu so.
 */
export function MotifCompassArc({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 160"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <circle cx="80" cy="80" r="58" fill="none" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.3" strokeDasharray="4 7" />
      <path d="M80 22 A58 58 0 0 1 138 80" fill="none" stroke="currentColor" strokeOpacity="0.6" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M42 46 L80 80 L64 108" fill="none" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="80" cy="80" r="3" fill="currentColor" fillOpacity="0.7" />
    </svg>
  );
}

/**
 * Cộng đồng (PageHero V1) — vai diem noi voi nhau bang net mo, nhu mot
 * chom sao/mang luoi ket noi, khong phai bieu tuong hoi/guild cu the.
 */
export function MotifConstellation({ className }: { className?: string }) {
  const diem = [
    [24, 96], [58, 48], [96, 70], [128, 30], [110, 108], [64, 118],
  ];
  return (
    <svg
      className={className}
      viewBox="0 0 160 140"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path
        d="M24 96 L58 48 L96 70 L128 30 M96 70 L110 108 L64 118 L58 48"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.2"
      />
      {diem.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i % 2 ? 2.2 : 3.2} fill="currentColor" fillOpacity="0.7" />
      ))}
    </svg>
  );
}

/**
 * Thư viện (PageHero V1) — mot vong tron kinh-mau/dia thien van: nhieu net
 * chia huong tam nhu o cua so kinh mau nha tho, cong voi mot vanh ngoai —
 * "ornate nhung hien dai", khong phai kinh mau day dac chi tiet.
 */
export function MotifCelestialDial({ className }: { className?: string }) {
  const nan = Array.from({ length: 8 }, (_, i) => (i * Math.PI) / 4);
  return (
    <svg
      className={className}
      viewBox="0 0 160 160"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <circle cx="80" cy="80" r="60" fill="none" stroke="currentColor" strokeOpacity="0.45" strokeWidth="1.3" />
      <circle cx="80" cy="80" r="38" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1" />
      {nan.map((goc, i) => (
        <line
          key={i}
          x1={80 + Math.cos(goc) * 38}
          y1={80 + Math.sin(goc) * 38}
          x2={80 + Math.cos(goc) * 60}
          y2={80 + Math.sin(goc) * 60}
          stroke="currentColor"
          strokeOpacity="0.4"
          strokeWidth="1"
        />
      ))}
      <circle cx="80" cy="80" r="4" fill="currentColor" fillOpacity="0.65" />
    </svg>
  );
}

/**
 * Image Studio (PageHero V1) — mot vet muc loang + mot ngoi sao nho, "sang
 * tac hinh anh" chu khong phai bang mau ve.
 */
export function MotifInkBloom({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 140"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path
        d="M46 90 C34 78 36 56 54 44 C72 32 98 34 112 50 C124 64 120 84 104 92 C90 100 68 98 58 106 C64 96 58 92 46 90 Z"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M120 34 L124 44 L134 48 L124 52 L120 62 L116 52 L106 48 L116 44 Z" fill="currentColor" fillOpacity="0.55" />
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

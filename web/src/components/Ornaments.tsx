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

/**
 * Trang chủ (PageHero V2) — vài cung sóng/khúc xạ mảnh, gợi mặt biển dưới
 * ánh sáng chứ không phải biểu đồ hay đường viền hình học.
 */
export function MotifWaveArcs({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 100"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path d="M4 70 C40 50 60 50 96 66 C132 82 152 82 188 60" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M10 42 C46 26 66 26 100 40 C134 54 154 54 186 36" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M20 88 C54 76 72 76 104 86" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Animation (PageHero V2) — thay `MotifFilmFrame` (qua nhieu "thiet bi quay
 * phim" cho huong tinh than moi: mot vanh quy dao thien the mo + vai diem sao
 * + mot cung cong mo nhu manh vo cua mot canh cong, khong con la khung hinh
 * dien anh.
 */
export function MotifNebulaOrbit({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 160"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <ellipse cx="80" cy="80" rx="66" ry="30" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.1" transform="rotate(-18 80 80)" />
      <path d="M28 46 A70 70 0 0 1 96 18" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="118" cy="52" r="1.6" fill="currentColor" fillOpacity="0.8" />
      <circle cx="40" cy="108" r="1.3" fill="currentColor" fillOpacity="0.65" />
      <circle cx="100" cy="120" r="1.8" fill="currentColor" fillOpacity="0.7" />
      <circle cx="132" cy="94" r="1.2" fill="currentColor" fillOpacity="0.55" />
    </svg>
  );
}

/**
 * Audio Studio (PageHero V2) — thay `MotifWaveform` (day cot EQ ro rang) bang
 * vai vong cong huong dong tam + mot cung song mem, tranh cam giac "bang tan
 * so" lap lai o khap noi.
 */
export function MotifResonanceRings({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 160"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <circle cx="70" cy="80" r="18" fill="none" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.3" />
      <circle cx="70" cy="80" r="36" fill="none" stroke="currentColor" strokeOpacity="0.38" strokeWidth="1.1" strokeDasharray="3 6" />
      <circle cx="70" cy="80" r="54" fill="none" stroke="currentColor" strokeOpacity="0.22" strokeWidth="1" strokeDasharray="2 8" />
      <path d="M100 100 C118 92 128 76 122 56" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

/** Viết (PageHero V2) — mot net but muc uon nhe + vai vach rune nho, cam giac
 * sang tac/van chuong chu khong phai trang trai cong chua. */
export function MotifInkFlourish({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 160 120"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path d="M18 92 C48 100 72 82 78 58 C82 40 74 24 58 20" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M58 20 C64 26 64 34 56 36" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M100 30 L104 40 M112 26 L108 38 M124 32 L118 42" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

/** Tài khoản (PageHero V2) — mot huy hieu/an chuong nho, kiem che hon cac
 * trang noi dung khac. */
export function MotifSigil({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 120 120"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <path d="M60 14 L96 30 V62 C96 84 80 98 60 106 C40 98 24 84 24 62 V30 Z" fill="none" stroke="currentColor" strokeOpacity="0.45" strokeWidth="1.3" strokeLinejoin="round" />
      <circle cx="60" cy="58" r="14" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.1" />
      <circle cx="60" cy="58" r="2.2" fill="currentColor" fillOpacity="0.7" />
    </svg>
  );
}

/**
 * Đăng nhập (PageHero V2) — vong cong cong that/nhung vach roi, vai diem sao
 * nho, mot cung rune mo — quang cong dang sau logo, KHONG phai mot khoi tron
 * dac.
 */
export function MotifPortalHalo({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 200"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <circle cx="100" cy="100" r="72" fill="none" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.3" strokeDasharray="10 14" />
      <circle cx="100" cy="100" r="90" fill="none" stroke="currentColor" strokeOpacity="0.22" strokeWidth="1" strokeDasharray="4 18" />
      <path d="M40 60 A72 72 0 0 1 100 28" fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="150" cy="52" r="1.6" fill="currentColor" fillOpacity="0.75" />
      <circle cx="42" cy="140" r="1.4" fill="currentColor" fillOpacity="0.6" />
      <circle cx="160" cy="146" r="1.2" fill="currentColor" fillOpacity="0.55" />
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

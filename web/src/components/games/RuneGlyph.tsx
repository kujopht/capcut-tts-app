/**
 * Ký hiệu rune cho Memory Runes — SVG nội tuyến, cùng hệ nét với `Icons.tsx`
 * (khung 24, nét 1.75, `currentColor`). Hình học đơn giản, tự vẽ; mỗi rune khác
 * nhau bằng HÌNH, tên đi kèm ở thẻ bài (không dựa vào màu).
 */

const HINH: Record<string, React.ReactNode> = {
  ignis: <path d="M12 4 L20 19 H4 Z" />,
  aqua: <path d="M12 20 L20 5 H4 Z" />,
  terra: (
    <>
      <path d="M12 20 L20 5 H4 Z" />
      <path d="M6.6 10 H17.4" />
    </>
  ),
  ventus: (
    <>
      <path d="M12 4 L20 19 H4 Z" />
      <path d="M6.6 14 H17.4" />
    </>
  ),
  lux: (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    </>
  ),
  umbra: <path d="M15.5 4.5 A8 8 0 1 0 15.5 19.5 A6.2 6.2 0 1 1 15.5 4.5 Z" />,
  flora: (
    <>
      <path d="M12 20 V10" />
      <path d="M12 12 C7 12 5 8.5 5 5 C9 5 12 7.5 12 12 Z" />
      <path d="M12 12 C17 12 19 8.5 19 5 C15 5 12 7.5 12 12 Z" />
    </>
  ),
  ferrum: (
    <>
      <path d="M12 3.5 L20.5 12 L12 20.5 L3.5 12 Z" />
      <path d="M12 7.5 V16.5 M7.5 12 H16.5" />
    </>
  ),
  astra: <path d="M12 3.5 L14.4 9.2 L20.5 9.6 L15.8 13.5 L17.3 19.5 L12 16.2 L6.7 19.5 L8.2 13.5 L3.5 9.6 L9.6 9.2 Z" />,
  glacies: (
    <>
      <path d="M12 3.5 V20.5 M4.6 7.75 L19.4 16.25 M4.6 16.25 L19.4 7.75" />
      <path d="M10 5.5 L12 7.5 L14 5.5 M10 18.5 L12 16.5 L14 18.5" />
    </>
  ),
  fulmen: <path d="M14 3 L6 13.5 H11.5 L10 21 L18 10.5 H12.5 Z" />,
  vita: (
    <>
      <ellipse cx="12" cy="7" rx="3.4" ry="3.8" />
      <path d="M12 10.8 V21 M6.5 13 H17.5" />
    </>
  ),
};

export function RuneGlyph({ runeKey, size = 34 }: { runeKey: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {HINH[runeKey] ?? <circle cx="12" cy="12" r="3" />}
    </svg>
  );
}

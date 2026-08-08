/**
 * Nhan dien thuong hieu Fanfic Audio Studio.
 *
 * Y TUONG: mot trang sach mo, va song am vuon len tu gay sach. Mot bieu tuong
 * duy nhat cho CA Audio Studio lan Fanfic — khong tach thanh hai thuong hieu.
 *
 * Hinh ve nguyen ban, chi gom hinh khoi co ban (ba thanh bo tron + hai hinh
 * thang lam trang sach). Khong dung anh hay logo cua ai.
 *
 * DE DOC O KICH THUOC NHO: chi 5 hinh khoi, khong chi tiet mong. O 16px van
 * thay duoc "song am tren mot cuon sach".
 */

/** Toa do goc cua bieu tuong trong luoi 32x32, dung chung cho moi bien the. */
export const GLYPH_VIEWBOX = "0 0 32 32";

/** Mau thuong hieu — trung voi token trong globals.css. */
export const BRAND = {
  from: "#7c8cff",
  to: "#4dd6c1",
  ink: "#0b0d12",
} as const;

/** Rieng phan hinh: ba thanh song am + hai trang sach. */
function Glyph({ color = "currentColor" }: { color?: string }) {
  return (
    <g fill={color} stroke={color} strokeLinejoin="round">
      {/* Song am vuon len tu gay sach — thanh giua cao nhat, nam ngay tren gay */}
      <rect x="8.4" y="9.2" width="3.2" height="4.4" rx="1.6" stroke="none" />
      <rect x="14.4" y="3.4" width="3.2" height="10.2" rx="1.6" stroke="none" />
      <rect x="20.4" y="7.2" width="3.2" height="6.4" rx="1.6" stroke="none" />
      {/* Hai trang sach mo, chum vao gay o giua */}
      <path d="M4.6 16.4 14.6 18 14.6 26.8 4.6 25.2Z" strokeWidth="1.8" />
      <path d="M27.4 16.4 17.4 18 17.4 26.8 27.4 25.2Z" strokeWidth="1.8" />
    </g>
  );
}

/**
 * Bieu tuong vuong: o bo tron mau thuong hieu, hinh mau muc dam.
 *
 * O tu mang san do tuong phan nen dung duoc tren CA nen sang lan nen toi ma
 * khong can doi mau.
 */
export function LogoMark({
  size = 32,
  title,
}: {
  size?: number;
  title?: string;
}) {
  const gradientId = `fas-brand-${size}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox={GLYPH_VIEWBOX}
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={BRAND.from} />
          <stop offset="1" stopColor={BRAND.to} />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradientId})`} />
      <g transform="translate(4.81 5.12) scale(0.7)">
        <Glyph color={BRAND.ink} />
      </g>
    </svg>
  );
}

/**
 * Ban mot mau: chi co hinh, khong o nen, lay mau tu `currentColor`.
 *
 * Dung khi can in mot mau hoac dat tren nen da co mau — tu dong hop voi ca
 * nen sang lan nen toi vi thua ke mau chu xung quanh.
 */
export function LogoGlyph({
  size = 32,
  title,
}: {
  size?: number;
  title?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={GLYPH_VIEWBOX}
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <Glyph />
    </svg>
  );
}

/**
 * Logo day du: bieu tuong + ten san pham.
 *
 * Ten dung `currentColor` nen doi theo nen sang/toi ma khong can hai file.
 */
export function Logo({
  size = 30,
  showText = true,
}: {
  size?: number;
  showText?: boolean;
}) {
  if (!showText) return <LogoMark size={size} title="Fanfic Audio Studio" />;
  return (
    <>
      <LogoMark size={size} />
      <span>
        Fanfic <span className="brand-text-sub">Audio Studio</span>
      </span>
    </>
  );
}

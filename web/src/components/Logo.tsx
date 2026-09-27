/**
 * Nhan dien thuong hieu Fanfic World.
 *
 * Logo lay tu HAI anh chu du an chon (2026-09): mot cuon sach mo, dai anh
 * sang va ngoi sao vuon len tu trang sach.
 *
 *   - Icon vuong bo goc  -> `public/brand/icon-*.png`, `app/favicon.ico`,
 *     `app/apple-icon.png`, icon maskable — moi cho icon vuong nho.
 *   - Bieu tuong + chu   -> `public/brand/logo-emblem.webp` +
 *     `logo-wordmark.webp` — logo trong giao dien (header, footer).
 *
 * Anh goc co nen trang va chu "fanfic" mau navy dam; ban dung o day da tach
 * nen (trong suot) va doi "fanfic" sang mau sang, vi site chi co nen toi —
 * ".world" giu nguyen gradient cua ban goc.
 */

/** Duong dan tai san — mot nguon duy nhat cho moi noi dung logo. */
export const BRAND_ASSETS = {
  icon: "/brand/icon-192.png",
  emblem: "/brand/logo-emblem.webp",
  wordmark: "/brand/logo-wordmark.webp",
} as const;

/** Ti le rong/cao THAT cua anh, de dat width/height (khong nhay bo cuc). */
const EMBLEM_RATIO = 209 / 160;
const WORDMARK_RATIO = 483 / 96;
/** Chieu cao chu so voi bieu tuong trong ban xep ngang. */
const WORDMARK_SCALE = 0.66;

/** Icon vuong (o bo goc) — cho icon nho trong giao dien, vd trang dang nhap. */
export function LogoMark({
  size = 32,
  title,
}: {
  size?: number;
  title?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- icon tinh nho, kich thuoc co dinh, khong can Next/Image
    <img
      src={BRAND_ASSETS.icon}
      width={size}
      height={size}
      alt={title ?? ""}
      aria-hidden={title ? undefined : true}
      className="logo-mark"
      draggable={false}
    />
  );
}

/**
 * Logo day du: bieu tuong + chu "fanfic.world", xep ngang.
 *
 * `size` la chieu cao bieu tuong; chu cao bang `WORDMARK_SCALE` lan.
 * Ten doc man hinh la "Fanfic World" (ten san pham), dat tren anh chu.
 */
export function Logo({
  size = 30,
  showText = true,
}: {
  size?: number;
  showText?: boolean;
}) {
  if (!showText) return <LogoMark size={size} title="Fanfic World" />;
  const cao = Math.round(size * WORDMARK_SCALE);
  return (
    <span className="logo-lockup">
      {/* eslint-disable-next-line @next/next/no-img-element -- logo tinh, kich thuoc co dinh */}
      <img
        src={BRAND_ASSETS.emblem}
        width={Math.round(size * EMBLEM_RATIO)}
        height={size}
        alt=""
        aria-hidden="true"
        className="brand-emblem"
        draggable={false}
      />
      {/* eslint-disable-next-line @next/next/no-img-element -- logo tinh, kich thuoc co dinh */}
      <img
        src={BRAND_ASSETS.wordmark}
        width={Math.round(cao * WORDMARK_RATIO)}
        height={cao}
        alt="Fanfic World"
        className="brand-wordmark"
        draggable={false}
      />
    </span>
  );
}

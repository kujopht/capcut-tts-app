import { BRAND_MARK_PNG } from "./brandMarkData";

/**
 * Bieu tuong dung cho anh sinh o phia may chu (`ImageResponse` / Satori).
 *
 * Satori chi nhan `<img>` voi URL tuyet doi hoac data URI, va Worker khong
 * doc duoc tep luc chay — nen icon (cung o bo goc voi `public/brand/icon-*`)
 * duoc nhung san thanh PNG trong `brandMarkData.ts`.
 */
export function BrandMark({ size }: { size: number }) {
  // eslint-disable-next-line @next/next/no-img-element -- Satori chi hieu <img>
  return <img src={BRAND_MARK_PNG} width={size} height={size} alt="" />;
}

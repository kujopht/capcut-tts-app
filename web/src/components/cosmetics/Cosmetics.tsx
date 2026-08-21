"use client";

/**
 * Tai san vat pham suu tam NGUYEN BAN — V4 visual completion, vong 2, Phan K/9.
 *
 * SVG NOI TUYEN, cung he thong voi `components/Icons.tsx` (khung 24, net
 * 1.75, dau tron, `currentColor`) — mau THAT SU do lop `.do-hiem-{rarity}`
 * (`globals.css`) quyet dinh qua bien `--rarity`, KHONG bao gio qua `style`
 * inline. KHONG nhan vat/hoa tiet co ban quyen — moi hinh la net hinh hoc
 * huyen ao TIET CHE, dung phong cach voi phan con lai cua giao dien.
 *
 * `respectMotion`: moi hieu ung xoay/nhap nhay (`.cosmetic-spin`) DEU tat
 * duoi `prefers-reduced-motion: reduce` — xem quy tac chung o dau
 * `globals.css` (khoi "hoa van huyen ao").
 */

import { useState } from "react";
import type { CosmeticItem } from "@/lib/api";

/**
 * Anh khung avatar sinh boi Pollinations (V6 fantasy-assets-v1) — dat trong
 * `public/artwork/cosmetics/frames/`. Neu file bi xoa/thieu, `onError` cua
 * `<img>` trong `KhungAvatar` se roi ve khung SVG `KhungAvatarSvg` ben duoi,
 * KHONG lam vo giao dien.
 */
const KHUNG_ANH: Record<string, string> = {
  frame_go: "/artwork/cosmetics/frames/frame_go.webp",
  frame_bac: "/artwork/cosmetics/frames/frame_bac.webp",
  frame_ngoc: "/artwork/cosmetics/frames/frame_ngoc.webp",
  frame_vang: "/artwork/cosmetics/frames/frame_vang.webp",
  frame_sao: "/artwork/cosmetics/frames/frame_sao.webp",
};

function KhungSvg({ children }: { children: React.ReactNode }) {
  return (
    <svg
      className="cosmetic-frame-svg"
      viewBox="0 0 100 100"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Khung avatar — anh PNG/WebP phu LEN TREN avatar, dinh vi tuyet doi. */
function KhungAvatar({ assetRef }: { assetRef: string }) {
  const [loiAnh, setLoiAnh] = useState(false);
  const nguonAnh = KHUNG_ANH[assetRef];

  if (nguonAnh && !loiAnh) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- overlay tuyet doi, khong can toi uu Next/Image
      <img
        src={nguonAnh}
        alt=""
        aria-hidden="true"
        draggable={false}
        className="cosmetic-frame-svg cosmetic-frame-img"
        onError={() => setLoiAnh(true)}
      />
    );
  }

  return <KhungAvatarSvg assetRef={assetRef} />;
}

/** Khung du phong dang SVG — dung khi anh sinh boi Pollinations bi thieu/loi. */
function KhungAvatarSvg({ assetRef }: { assetRef: string }) {
  switch (assetRef) {
    case "frame_go":
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="4" strokeDasharray="3 5" />
        </KhungSvg>
      );
    case "frame_bac":
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="3" />
          <circle cx="50" cy="50" r="40" strokeWidth="1.5" />
        </KhungSvg>
      );
    case "frame_ngoc":
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="3" />
          {[0, 90, 180, 270].map((goc) => (
            <path
              key={goc}
              d="M50 2 L54 10 L50 18 L46 10 Z"
              transform={`rotate(${goc} 50 50)`}
              strokeWidth="2"
            />
          ))}
        </KhungSvg>
      );
    case "frame_vang":
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="3.5" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((goc) => (
            <path
              key={goc}
              d="M50 3 L50 12"
              transform={`rotate(${goc} 50 50)`}
              strokeWidth="2.5"
            />
          ))}
        </KhungSvg>
      );
    case "frame_sao":
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="2.5" strokeDasharray="1 6" />
          {[20, 100, 190, 280].map((goc, i) => {
            const rad = (goc * Math.PI) / 180;
            const x = 50 + 46 * Math.cos(rad);
            const y = 50 + 46 * Math.sin(rad);
            return <circle key={i} cx={x} cy={y} r="2.6" fill="currentColor" stroke="none" />;
          })}
        </KhungSvg>
      );
    default:
      return (
        <KhungSvg>
          <circle cx="50" cy="50" r="46" strokeWidth="3" />
        </KhungSvg>
      );
  }
}

/**
 * Boc avatar bang mot khung suu tam DANG TRANG BI — `null`/rong thi tra ve
 * `children` nguyen ven, khong ve khung gi ca.
 */
export function CosmeticFrame({
  cosmetic,
  children,
}: {
  cosmetic?: CosmeticItem | null;
  children: React.ReactNode;
}) {
  if (!cosmetic) return <>{children}</>;
  return (
    <span className={`cosmetic-frame do-hiem-mau do-hiem-${cosmetic.rarity}`}>
      {children}
      <KhungAvatar assetRef={cosmetic.asset_ref} />
    </span>
  );
}

/** Icon hoa tiet ho so — mot net trang tri nho, dung canh ten/tieu de. */
export function OrnamentIcon({ assetRef, size = 18 }: { assetRef: string; size?: number }) {
  const chung = {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const, "aria-hidden": true, focusable: false,
  };
  switch (assetRef) {
    case "ornament_la":
      return (
        <svg {...chung}>
          <path d="M12 3c4 2 6 6 6 10-4 0-8-2-10-6-1-2-1-3 0-4 1-1 2-1 4 0Z" />
          <path d="M12 21V9" />
        </svg>
      );
    case "ornament_may":
      return (
        <svg {...chung}>
          <path d="M6 15a4 4 0 0 1 .3-8 5 5 0 0 1 9.6-1.6A4.5 4.5 0 0 1 18 15Z" />
        </svg>
      );
    case "ornament_sao_bang":
      return (
        <svg {...chung}>
          <path d="M4 20 16 8" />
          <path d="M11 8h5v5" />
          <circle cx="18" cy="6" r="1.4" fill="currentColor" stroke="none" />
        </svg>
      );
    default:
      return (
        <svg {...chung}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

/** Icon huy hieu — dung trong luoi thanh tuu/suu tap. */
export function BadgeIcon({ assetRef, size = 22 }: { assetRef: string; size?: number }) {
  const chung = {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const, "aria-hidden": true, focusable: false,
  };
  switch (assetRef) {
    case "badge_but_long":
      return (
        <svg {...chung}>
          <path d="M4 20 L14 10 L17 13 L7 23 L4 23 Z" />
          <path d="M14 10 L17 7 L20 10 L17 13" />
        </svg>
      );
    case "badge_cuon_giay":
      return (
        <svg {...chung}>
          <path d="M6 4h9a3 3 0 0 1 3 3v13" />
          <path d="M6 4a3 3 0 0 0-3 3v13h13" />
          <path d="M9 9h5M9 13h5" />
        </svg>
      );
    case "badge_la_ban":
      return (
        <svg {...chung}>
          <circle cx="12" cy="12" r="9" />
          <path d="M15 9l-2 5-4 1 2-5z" />
        </svg>
      );
    case "badge_dom_lua":
      return (
        <svg {...chung}>
          <path d="M12 2c2 4-1 5-1 8a3 3 0 1 0 6 0c0-1-.5-2-1-2 1 3-1 4-2 4-2 0-3-1-3-3 0-2 1.5-3 1-7Z" />
        </svg>
      );
    case "badge_phuong_hoang":
      return (
        <svg {...chung}>
          <path d="M12 3c2 3 6 4 8 8-3-1-5 0-6 2 2 0 3 1 4 3-3-1-5-1-6 1-1-2-3-2-6-1 1-2 2-3 4-3-1-2-3-3-6-2 2-4 6-5 8-8Z" />
          <path d="M12 13v8" />
        </svg>
      );
    default:
      return (
        <svg {...chung}>
          <path d="M12 2l2.6 5.9 6.4.6-4.8 4.3 1.4 6.2L12 16l-5.6 3 1.4-6.2-4.8-4.3 6.4-.6Z" />
        </svg>
      );
  }
}

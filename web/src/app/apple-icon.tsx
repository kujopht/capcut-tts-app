import { ImageResponse } from "next/og";
import { BrandMark } from "@/components/BrandMark";

/**
 * apple-touch-icon.
 *
 * iOS khong nhan SVG cho icon man hinh chinh, nen sinh PNG that tu chinh bo
 * hinh SVG dung o moi noi khac — mot nguon duy nhat, khong ve lai.
 */
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0b0d12",
        }}
      >
        <BrandMark size={180} />
      </div>
    ),
    size,
  );
}

import { ImageResponse } from "next/og";
import { BrandMark } from "@/components/BrandMark";

/** Anh xem truoc khi chia se link. */
/*
  Toan bo tam anh nay noi ve viec TAO AUDIO — dung thoi Audio Studio la ca
  san pham. Day la thu duy nhat nguoi ta thay khi mot duong dan fanfic.world
  duoc dan vao Facebook/Zalo/Discord, nen no phai gioi thieu dung san pham:
  mot noi de DOC va NGHE fanfic, trong do audio la mot cach thuong thuc chu
  khong phai cua vao.
*/
export const alt = "Fanfic World — đọc và nghe fanfic tiếng Việt";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 90px",
          background: "#0b0d12",
          backgroundImage:
            "radial-gradient(900px 500px at 10% 0%, #7c8cff33, transparent), " +
            "radial-gradient(800px 460px at 95% 100%, #4dd6c126, transparent)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 26 }}>
          <BrandMark size={104} />
          <div style={{ display: "flex", fontSize: 54, fontWeight: 700 }}>
            <span style={{ color: "#e9edf5" }}>Fanfic</span>
            <span style={{ color: "#a8b2c5", marginLeft: 14 }}>World</span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 34,
            fontSize: 40,
            lineHeight: 1.35,
            color: "#e9edf5",
            maxWidth: 900,
          }}
        >
          Truyện của cộng đồng, đọc bằng mắt hoặc bằng tai
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 22,
            fontSize: 25,
            color: "#a8b2c5",
          }}
        >
          Khám phá truyện đã xuất bản · Nghe bằng giọng đọc tự nhiên
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 46,
            gap: 14,
          }}
        >
          {/* Ba khu vuc THAT o dieu huong chinh, theo dung thu tu do. */}
          {["Khám phá", "Animation", "Studio"].map((label) => (
            <div
              key={label}
              style={{
                display: "flex",
                padding: "10px 22px",
                borderRadius: 999,
                border: "1px solid #262c3a",
                background: "#171b25",
                color: "#a8b2c5",
                fontSize: 23,
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}

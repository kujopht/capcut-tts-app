import { ImageResponse } from "next/og";
import { BrandMark } from "@/components/BrandMark";

/** Anh xem truoc khi chia se link. */
export const alt = "Fanfic Audio Studio — tạo audio từ văn bản và nghe fanfic";
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
            <span style={{ color: "#a8b2c5", marginLeft: 14 }}>Audio Studio</span>
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
          Biến chữ thành giọng đọc, và nghe fanfic mọi lúc
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 22,
            fontSize: 25,
            color: "#a8b2c5",
          }}
        >
          Tạo audio từ văn bản bất kỳ · Khám phá truyện đã xuất bản
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 46,
            gap: 14,
          }}
        >
          {["Audio Studio", "Fanfic", "Thư viện"].map((label) => (
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

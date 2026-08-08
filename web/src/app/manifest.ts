import type { MetadataRoute } from "next";

/**
 * Web manifest — de bo icon 192/512 co cho dung (Android, "them vao man hinh
 * chinh"). Khong co bo nay thi hai file PNG lon kia khong ai doc toi.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Fanfic Audio Studio",
    short_name: "Fanfic Audio",
    description:
      "Tạo audio từ văn bản bất kỳ và nghe fanfic bằng giọng đọc tiếng Việt.",
    start_url: "/",
    display: "standalone",
    background_color: "#0b0d12",
    theme_color: "#0b0d12",
    lang: "vi",
    icons: [
      { src: "/brand/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/brand/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/brand/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        // `maskable` de Android tu bo goc theo hinh dang cua may
        purpose: "maskable",
      },
    ],
  };
}

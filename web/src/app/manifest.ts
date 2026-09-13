import type { MetadataRoute } from "next";

/**
 * Web manifest — de bo icon 192/512 co cho dung (Android, "them vao man hinh
 * chinh"). Khong co bo nay thi hai file PNG lon kia khong ai doc toi.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Fanfic World",
    short_name: "Fanfic",
    /*
      Mo ta cu dat viec TAO AUDIO len truoc — dung thoi Audio Studio la ca
      san pham. Day la nen tang doc/nghe fanfic; audio la mot cach thuong
      thuc, khong phai cua vao. Bieu tuong tren man hinh chinh cua dien
      thoai phai noi dung thu nguoi ta mo no ra de lam.
    */
    description:
      "Đọc và nghe fanfic tiếng Việt do cộng đồng viết, bằng mắt hoặc bằng tai.",
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

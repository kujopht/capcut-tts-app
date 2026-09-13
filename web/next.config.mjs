/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend giu moi bi mat. Bien duy nhat lo ra trinh duyet la URL API.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },

  /**
   * Duong dan CU cua bon cong cu roi nhau -> Fanfic Studio.
   *
   * Dat o day chu khong phai sau trang `redirect()` cho moi duong: mot trang
   * stub van phai dung React ve mot lan roi moi chuyen huong, con cho nay tra
   * 308 ngay o tang dinh tuyen. Voi mot lan doi ten thuan tuy thi do la khac
   * biet giua "nhay mot cai" va "chop mot cai roi moi nhay".
   *
   * `permanent: true` (308) la co y: day la dia chi moi VINH VIEN, va 308 giu
   * nguyen phuong thuc HTTP lan than yeu cau — khac 302, von duoc phep doi
   * POST thanh GET. Khong route nao duoi day nhan POST hom nay, nhung mot
   * chuyen huong am tham doi phuong thuc la loai bay chi lo ra sau nay.
   *
   * Bookmark cu, lien ket da chia se, va ket qua tim kiem deu con chay.
   */
  async redirects() {
    return [
      { source: "/image-studio", destination: "/studio/image", permanent: true },
      { source: "/translate", destination: "/studio/translate", permanent: true },
      { source: "/tools/subtitles", destination: "/studio/subtitle", permanent: true },
      { source: "/write", destination: "/studio/write", permanent: true },
      { source: "/write/import", destination: "/studio/write/import", permanent: true },
      { source: "/library", destination: "/studio/library", permanent: true },
    ];
  },
};
export default nextConfig;

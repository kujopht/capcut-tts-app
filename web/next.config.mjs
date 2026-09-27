import { execSync } from "node:child_process";

/**
 * Ma ban build web (Fanfic AI Support: "ban nao dang loi" trong bao cao/su co).
 * KHONG phai bi mat — chi la ma commit ngan. Thu tu: bien moi truong (CI) ->
 * `git rev-parse` -> "unknown" (vd build tu tarball khong co .git).
 */
function maBuild() {
  if (process.env.NEXT_PUBLIC_BUILD_SHA) return process.env.NEXT_PUBLIC_BUILD_SHA;
  try {
    return execSync("git rev-parse --short=10 HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim() || "unknown";
  } catch {
    return "unknown";
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend giu moi bi mat. Ngoai URL API, trinh duyet chi thay them MA BUILD
  // (ma commit ngan, khong phai bi mat).
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
    NEXT_PUBLIC_BUILD_SHA: maBuild(),
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
      { source: "/import", destination: "/studio/write/import", permanent: true },
      { source: "/fanfic", destination: "/library?tab=fanfic", permanent: true },
      { source: "/animation/new", destination: "/admin/animation/sources/new", permanent: true },
      /*
        Trang Nghe rieng -> trang chuong thong nhat (sprint doc/nghe
        2026-09-24): doc va nghe gio la MOT duong dan chinh tac. Lien ket cu,
        bookmark va chia se van chay, mo thang che do Nghe.

        `permanent: false` (307) CO Y trong dot dau: 308 bi trinh duyet nho
        vinh vien, neu phai lui ban thi nguoi dung da tung vao se khong bao
        gio thay lai `/listen`. Nang len 308 sau khi trang moi da on dinh.
      */
      { source: "/listen/:id", destination: "/chapters/:id?mode=listen", permanent: false },
      /*
        `/library` KHONG con o day, va day la mot lan sua co y.

        No tung tro sang `/studio/library`. Nhung `/studio/library` la THU
        VIEN AUDIO cua nguoi sang tac (danh sach job TTS), con "Thư viện" o
        thanh dieu huong chinh thi mot nguoi DOC bam vao — va thu ho mong
        doi la truyen ho theo doi, khong phai cac ban thu am cua ho.
        Chuyen huong do bien mot khu vuc doc gia thanh mot cong cu sang tac.
        `/library` nay la thu vien CUA NGUOI DOC; audio van o trong Studio.

        Doi duoc vi chuyen huong kia CHUA BAO GIO len production (#197 dung
        lai truoc buoc trien khai), nen khong trinh duyet nao tren doi da
        nho mot 308 tro di. Sua truoc khi phat hanh thi khong phai go mot
        chuyen huong vinh vien da nam trong bo nho dem cua nguoi dung.
      */
    ];
  },

  async headers() {
    return [
      /*
        CHONG CLICKJACKING: chi chinh fanfic.world duoc nhung trang cua minh
        vao iframe. Truoc day production khong gui header nao, nen bat ky site
        nao cung nhung duoc ca `/admin` roi phu mot lop trong suot len nut.

        `frame-ancestors 'self'` la cach chuan (CSP 2). CSP nay CHI co mot
        chi thi, khong co `default-src`/`script-src` — no khong chan script,
        anh, font hay API nao, chi quyet dinh ai duoc lam khung cha.
        `X-Frame-Options: SAMEORIGIN` la lop du phong cho trinh duyet cu khong
        hieu `frame-ancestors`; trinh duyet moi co ca hai thi bo qua XFO.
        Ca hai deu cho phep iframe CUNG origin (vd. `/entertainment` nhung
        `/games/.../index.html`), chan moi origin khac.
      */
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors 'self'" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
        ],
      },
      {
        source: "/audio/:path*",
        headers: [
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, HEAD, OPTIONS" },
        ],
      },
    ];
  },
};
export default nextConfig;

"use client";

/**
 * Khung chung cua Fanfic Studio — thanh ben, dau trang, va vung lam viec.
 *
 * Truoc ban nay, bon cong cu (Audio/Image/Dich/Phu de) la bon ung dung roi
 * nhau duoi mot menu tha xuong: moi cai mot kieu dau trang, mot kieu khoang
 * cach, mot kieu bao trang thai job. Nguoi dung phai quay ve menu de di tu
 * cong cu nay sang cong cu khac — tuc la ho phai BIET truoc ho dang tim gi.
 *
 * Khung nay khong sua mot cong cu nao. No chi dat chung canh nhau va cho
 * chung mot duong di chung.
 *
 * BA dieu co y, va deu hoc tu `AdminShell` (khung quan tri da chay that):
 *
 *   1. THANH BEN NAM O LAYOUT, khong o tung trang. Mot cong cu moi them vao
 *      `/studio/*` se TU CO dieu huong; khong ai phai nho goi no. Quen goi
 *      mot khung la loai loi chi lo ra khi da co nguoi dung lac duong.
 *
 *   2. KHONG CO CONG CHAN O DAY. Khac `AdminShell` mot cach co chu dich:
 *      khu quan tri la mot khu KHOA, con Studio thi khong — tung cong cu tu
 *      xu ly truong hop chua dang nhap theo cach cua no (Audio Studio cho
 *      dan van ban roi moi doi dang nhap luc tao job; Subtitle Studio chay
 *      hoan toan o may nguoi dung). Dat mot cong dang nhap o day se khoa ca
 *      nhung thu von khong can khoa.
 *
 *   3. DIEU HUONG LA DU LIEU, khong phai JSX chep tay. `MUC` la mot mang —
 *      nho vay trang Tong quan ve duoc dung cac muc do ma khong co co hoi
 *      lech nhan giua thanh ben va the tren trang.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  IconBook,
  IconCompass,
  IconFeather,
  IconFilm,
  IconMic,
  IconSparkles,
} from "@/components/Icons";

export interface MucStudio {
  href: string;
  nhan: string;
  /** Mot dong noi cong cu nay LAM GI — dung o ca thanh ben lan trang Tong quan. */
  mo_ta: string;
  icon: (p: { size?: number }) => React.ReactElement;
}

/**
 * Bay muc cua Studio.
 *
 * Nhan giu nguyen TIENG VIET da dung trong san pham thay vi dich lai tu ban
 * ke hoach tieng Anh: "Dịch" chu khong phai "Translate", "Phụ đề" chu khong
 * phai "Subtitle". Nguoi dung da quen cac chu nay o menu "Công cụ" cu, va
 * doi chu o dung luc doi duong dan se lam ho tuong day la mot cong cu khac.
 */
export const MUC_STUDIO: MucStudio[] = [
  {
    href: "/studio",
    nhan: "Tổng quan",
    mo_ta: "Bắt đầu từ đây — mọi công cụ và việc đang chạy.",
    icon: IconCompass,
  },
  {
    href: "/studio/write",
    nhan: "Viết truyện",
    mo_ta: "Soạn truyện, thêm chương, nhập từ nguồn ngoài.",
    icon: IconFeather,
  },
  {
    href: "/studio/translate",
    nhan: "Dịch tiểu thuyết",
    mo_ta: "Dịch tác phẩm dài sang tiếng Việt, giữ thuật ngữ nhất quán.",
    icon: IconBook,
  },
  {
    href: "/studio/audio",
    nhan: "Audio",
    mo_ta: "Dán văn bản, chọn giọng, tạo MP3.",
    icon: IconMic,
  },
  {
    href: "/studio/image",
    nhan: "Hình ảnh",
    mo_ta: "Tạo bìa và ảnh minh hoạ cho tác phẩm.",
    icon: IconSparkles,
  },
  {
    href: "/studio/subtitle",
    nhan: "Phụ đề",
    mo_ta: "Căn chỉnh và xuất phụ đề cho video.",
    icon: IconFilm,
  },
  {
    href: "/studio/library",
    nhan: "Tác phẩm của tôi",
    mo_ta: "Mọi truyện, bản dịch và audio bạn đã tạo.",
    icon: IconBook,
  },
];

/**
 * Muc nao dang mo.
 *
 * `/studio` phai so SANH BANG, khong `startsWith`: moi duong dan cong cu deu
 * bat dau bang `/studio`, nen dung `startsWith` se lam "Tổng quan" luon sang
 * cung luc voi cong cu dang mo — hai muc cung sang la mot thanh ben noi doi.
 */
export function mucDangMo(pathname: string, href: string): boolean {
  return href === "/studio" ? pathname === "/studio" : pathname.startsWith(href);
}

export function StudioShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Duoi 900px thanh ben bi an; nut nay la duong duy nhat mo no ra. Tren
  // desktop nut bi CSS an di va thanh ben luon hien.
  const [moMobile, setMoMobile] = useState(false);

  return (
    <div className="page studio-page">
      <header className="studio-dau row row-spread">
        <div className="stack-2">
          <span className="eyebrow eyebrow-icon">
            <IconSparkles size={17} /> Fanfic Studio
          </span>
          <h1 className="page-title studio-tieu-de">Xưởng sáng tác</h1>
        </div>
        <button
          type="button"
          className="btn btn-ghost studio-nut-mobile"
          aria-expanded={moMobile}
          aria-controls="studio-dieu-huong"
          onClick={() => setMoMobile((v) => !v)}
        >
          {moMobile ? "Đóng menu" : "Menu Studio"}
        </button>
      </header>

      <div className="studio-khung">
        <nav
          id="studio-dieu-huong"
          className={`studio-nav${moMobile ? " studio-nav-mo" : ""}`}
          aria-label="Fanfic Studio"
        >
          {MUC_STUDIO.map(({ href, nhan, icon: Icon }) => {
            const dang = mucDangMo(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className="studio-muc"
                aria-current={dang ? "page" : undefined}
                onClick={() => setMoMobile(false)}
                prefetch={false}
              >
                <Icon size={17} />
                <span>{nhan}</span>
              </Link>
            );
          })}
        </nav>

        <div className="studio-than">{children}</div>
      </div>
    </div>
  );
}

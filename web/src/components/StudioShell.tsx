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

/**
 * Dau trang cua MOT cong cu: chi loi dan + nut, KHONG tieu de.
 *
 * Ly do ton tai: truoc ban nay moi cong cu tu ve mot `PageHeader` rieng, nen
 * duoi khung Studio co HAI `<h1>` chong nhau — "Xưởng sáng tác" cua khung roi
 * "Audio Studio" cua cong cu. Hai `<h1>` tren mot trang khong chi xau: trinh
 * doc man hinh coi do la hai tieu de ngang cap, va nguoi dung thay ten san
 * pham lap lai o cho le ra noi ho DANG LAM GI.
 *
 * Nay khung so huu `<h1>` duy nhat (ten module dang mo), con cong cu giu
 * nhung thu KHONG the suy ra tu dieu huong: mot cau mo ta va cac nut thao
 * tac cua rieng no.
 */
export function StudioToolHeader({
  title,
  lead,
  action,
}: {
  /**
   * CHI dat cho mot trang CON trong module (vd "Nhập chương hàng loạt" duoi
   * Viết truyện). Ve thanh `<h2>`, khong phai `<h1>`: mot trang chi co MOT
   * `<h1>`, va o day no thuoc ve khung.
   *
   * Trang GOC cua mot module thi bo trong — ten cua no da la `<h1>` cua khung
   * roi, nhac lai chi ton mot dong.
   */
  title?: string;
  lead?: React.ReactNode;
  action?: React.ReactNode;
}) {
  if (!title && !lead && !action) return null;
  return (
    <div className="studio-tool-dau">
      <div className="row row-spread studio-tool-hang">
        {title ? <h2 className="section-title">{title}</h2> : <span />}
        {action ? <div className="row page-head-actions">{action}</div> : null}
      </div>
      {lead ? <p className="lead lead-narrow">{lead}</p> : null}
    </div>
  );
}

export function StudioShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Duoi 900px thanh ben bi an; nut nay la duong duy nhat mo no ra. Tren
  // desktop nut bi CSS an di va thanh ben luon hien.
  const [moMobile, setMoMobile] = useState(false);

  /*
    `<h1>` cua ca khu Studio, va la cai DUY NHAT.

    Lay TEN MODULE tu chinh `MUC_STUDIO` chu khong de tung trang tu khai: mot
    chuoi go tay o trang cong cu se troi khoi nhan o thanh ben sau vai lan sua,
    va luc do dieu huong va tieu de se noi hai chuyen khac nhau.

    Rieng `/studio` dung ten cua CA XUONG chu khong phai "Tổng quan" — o goc
    cua khu, ten khu la thu huu ich; "Tổng quan" thi chi lap lai muc dang sang
    o thanh ben.
  */
  // Ten bien KHONG duoc la `module`: Next.js cam gan vao dinh danh do
  // (`no-assign-module-variable`) vi no dung voi bien cua he module CommonJS.
  const dangMo = MUC_STUDIO.find((m) => mucDangMo(pathname, m.href));
  const tieuDe =
    !dangMo || dangMo.href === "/studio" ? "Xưởng sáng tác" : dangMo.nhan;

  return (
    <div className="page studio-page">
      <header className="studio-dau row row-spread">
        <div className="stack-2">
          <span className="eyebrow eyebrow-icon">
            <IconSparkles size={17} /> Fanfic Studio
          </span>
          <h1 className="page-title studio-tieu-de">{tieuDe}</h1>
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

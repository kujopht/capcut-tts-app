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
  IconCompass,
  IconFeather,
  IconMic,
  IconSparkles,
} from "@/components/Icons";
import { MotifNebulaOrbit } from "@/components/Ornaments";

export interface MucStudio {
  href: string;
  nhan: string;
  /** Mot dong noi cong cu nay LAM GI — dung o ca thanh ben lan trang Tong quan. */
  mo_ta: string;
  icon: (p: { size?: number }) => React.ReactElement;
}

/**
 * BON diem den cua Studio — khong phai tam.
 *
 * Ban truoc co tam muc: Tổng quan · Viết truyện · Dịch tiểu thuyết · Audio ·
 * Hình ảnh · Phụ đề · Video · Tác phẩm của tôi. Do la ban do cua NGUOI CAI
 * DAT, khong phai cua nguoi dung: no liet ke tung cong cu da duoc viet ra,
 * theo dung thu tu chung duoc viet.
 *
 * Nguoi dung khong nghi "hom nay toi mo Subtitle Studio". Ho nghi "toi lam
 * cai video cho chuong 3". Ba trong tam muc do — Audio, Phụ đề, Video — la
 * BA BUOC cua MOT viec, va tach chung ra thanh ba diem den bat nguoi dung
 * phai tu ghep lai, ke ca phai tai xuong roi tai len giua cac buoc.
 *
 * Nay:
 *   Dự án    — nha, va la cho duy nhat co danh sach du an
 *   Nội dung — Viết + Dịch, hai the trong MOT khong gian
 *   Media    — Audio + Phụ đề + Video, mot trinh soan duong thoi gian
 *   Hình ảnh — giu rieng, vi sinh anh that su la mot quy trinh khac han
 *
 * "Tác phẩm của tôi" bien mat khoi dieu huong co y: Dự án da so huu trach
 * nhiem do. Hai cho cung liet ke tac pham la hai cho co the lech.
 */
export const MUC_STUDIO: MucStudio[] = [
  {
    href: "/studio",
    nhan: "Dự án",
    mo_ta: "Mọi dự án của bạn — mở lại cái đang làm dở.",
    icon: IconCompass,
  },
  {
    href: "/studio/content",
    nhan: "Nội dung",
    mo_ta: "Viết truyện và dịch — cùng một chỗ.",
    icon: IconFeather,
  },
  {
    href: "/studio/audio",
    nhan: "Audio",
    mo_ta: "Tạo, nghe và tải lời đọc cho tác phẩm của bạn.",
    icon: IconMic,
  },
  {
    href: "/studio/image",
    nhan: "Hình ảnh",
    mo_ta: "Tạo bìa và ảnh minh hoạ cho tác phẩm.",
    icon: IconSparkles,
  },
];

/**
 * Duong dan CU -> diem den moi.
 *
 * Giu lai vi hai ly do, va ly do thu hai moi la ly do that: (1) nguoi dung
 * co the da luu dau trang; (2) trong kho van con lien ket noi bo tro toi
 * `/studio/audio` — mot trang chuyen huong thi sua duoc dan, con mot lien
 * ket 404 thi phai tim ra truoc da.
 */
export const DUONG_CU: Record<string, string> = {
  "/studio/subtitle": "/studio/media?panel=subtitle",
  "/studio/video": "/studio/media",
  "/studio/write": "/studio/content?tab=write",
  "/studio/translate": "/studio/content?tab=translate",
  "/studio/library": "/studio",
};

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
  const isMedia = pathname.startsWith("/studio/media");
  const dangMo = MUC_STUDIO.find((m) => mucDangMo(pathname, m.href));
  const tieuDe = isMedia
    ? "Media"
    : !dangMo || dangMo.href === "/studio"
      ? "Xưởng sáng tác"
      : dangMo.nhan;

  return (
    <div className="page studio-page rise" data-hero-theme="studio">
      {/* Tiêu đề và nút menu luôn hiện: trên mobile, đây là lối vào duy nhất
          cho các điểm đến Studio khác. */}
      <header className="studio-dau row row-spread rise rise-1" style={{ position: "relative" }}>
        <div className="stack-2 hero-copy">
          {isMedia ? (
            <Link
              href="/studio/audio"
              className="studio-quay-lai eyebrow"
              prefetch={false}
              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "4px" }}
            >
              <span aria-hidden="true">←</span> Quay lại Audio Studio
            </Link>
          ) : (
            <span className="eyebrow eyebrow-icon">
              <IconSparkles size={17} /> Fanfic Studio
            </span>
          )}
          <h1 className="page-title studio-tieu-de">{tieuDe}</h1>
        </div>
        <span
          className="page-head-motif"
          aria-hidden="true"
          style={{ position: "absolute", top: -12, right: 120, width: 140, pointerEvents: "none", color: "var(--hero-motif-color, #8b5cf6)", opacity: "var(--hero-motif-opacity, 0.18)" }}
        >
          <MotifNebulaOrbit />
        </span>
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

      <div className="studio-khung rise rise-2">
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
                <span className="studio-muc-nhan">{nhan}</span>
              </Link>
            );
          })}
        </nav>

        <div className="studio-than">{children}</div>
      </div>
    </div>
  );
}

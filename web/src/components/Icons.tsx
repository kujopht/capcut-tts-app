/**
 * Bo bieu tuong cua giao dien.
 *
 * VE BANG SVG NOI TUYEN, khong them goi phu thuoc — theo dung tien le cua
 * `ProviderIcons.tsx` da co trong kho nay.
 *
 * VI SAO KHONG DUNG LUCIDE / HEROICONS: da soi `package.json` truoc, va kho nay
 * KHONG co san thu vien icon nao. Them mot goi de dung khoang muoi hinh la doi
 * ca mot phu thuoc moi (kem cap nhat, kem be mat tan cong, kem dung luong goi)
 * lay mot thu ma sau ham nho lam duoc. Neu sau nay can hang tram hinh thi hay
 * doi — luc do goi moi tra du gia cua no.
 *
 * Moi hinh dung CUNG mot he: khung 24, net 1.75, dau tron, `currentColor`. Nho
 * vay chung dat canh nhau khong bi lech net, va mau den tu cho goi.
 */

interface Props {
  /** 16-20px cho phan lon cho dung. */
  size?: number;
  className?: string;
}

function Svg({
  size = 18,
  className,
  children,
}: Props & { children: React.ReactNode }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Tia sang — "moi", "dieu ky". */
export function IconSparkles(p: Props) {
  return (
    <Svg {...p}>
      <path d="M11 3 L12.6 8.4 L18 10 L12.6 11.6 L11 17 L9.4 11.6 L4 10 L9.4 8.4 Z" />
      <path d="M18 15.5 L18.7 17.8 L21 18.5 L18.7 19.2 L18 21.5 L17.3 19.2 L15 18.5 L17.3 17.8 Z" />
    </Svg>
  );
}

/** La ban — "kham pha". */
export function IconCompass(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5 L10.5 10.5 L8.5 15.5 L13.5 13.5 Z" />
    </Svg>
  );
}

/** Tai nghe — "nghe". */
export function IconHeadphones(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 14 V12 a8 8 0 0 1 16 0 v2" />
      <path d="M4 14 h2.5 a1 1 0 0 1 1 1 v3.5 a1 1 0 0 1 -1 1 H5.5 A1.5 1.5 0 0 1 4 18 Z" />
      <path d="M20 14 h-2.5 a1 1 0 0 0 -1 1 v3.5 a1 1 0 0 0 1 1 h1 A1.5 1.5 0 0 0 20 18 Z" />
    </Svg>
  );
}

/** Micro — "tao giong doc". */
export function IconMic(p: Props) {
  return (
    <Svg {...p}>
      <rect x="9" y="2.5" width="6" height="11" rx="3" />
      <path d="M5.5 11.5 a6.5 6.5 0 0 0 13 0" />
      <path d="M12 18 v3.5" />
    </Svg>
  );
}

/** Dong ho lui — "lich su". */
export function IconHistory(p: Props) {
  return (
    <Svg {...p}>
      <path d="M3.5 12 a8.5 8.5 0 1 0 2.6 -6.1" />
      <path d="M3 4 v4 h4" />
      <path d="M12 8 v4.4 l3 1.8" />
    </Svg>
  );
}

/** Bong den — "meo". */
export function IconBulb(p: Props) {
  return (
    <Svg {...p}>
      <path d="M9 17.5 h6" />
      <path d="M10 21 h4" />
      <path d="M12 2.5 a6 6 0 0 0 -3.5 10.8 V17.5 h7 V13.3 A6 6 0 0 0 12 2.5 Z" />
    </Svg>
  );
}

/** But long — "viet". */
export function IconFeather(p: Props) {
  return (
    <Svg {...p}>
      <path d="M20 4 a5.5 5.5 0 0 0 -7.8 0 L4 12.2 V20 h7.8 L20 11.8 A5.5 5.5 0 0 0 20 4 Z" />
      <path d="M4 20 L13 11" />
      <path d="M15 8 h-4" />
    </Svg>
  );
}

/** Sach mo — "doc", "chuong". */
export function IconBook(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 6.5 C10 4.8 7 4.3 3.5 4.8 V18 C7 17.5 10 18 12 19.5 C14 18 17 17.5 20.5 18 V4.8 C17 4.3 14 4.8 12 6.5 Z" />
      <path d="M12 6.5 V19.5" />
    </Svg>
  );
}

/** Ke sach — "thu vien". */
export function IconLibrary(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 4 v16" />
      <path d="M8 4 v16" />
      <path d="M12.5 4.6 L11 20.2" />
      <path d="M16.5 5 L20.5 19.5" />
    </Svg>
  );
}

/** Nguoi — "tai khoan". */
export function IconUser(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="8" r="3.75" />
      <path d="M4.5 20.5 a7.5 7.5 0 0 1 15 0" />
    </Svg>
  );
}

/** Chia khoa — "dang nhap". */
export function IconKey(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="8" cy="14" r="4" />
      <path d="M10.8 11.2 L20 2.8" />
      <path d="M17 5.5 L19.5 8" />
      <path d="M14.5 8 L17 10.5" />
    </Svg>
  );
}

/** Ngon lua — "moi nhat". */
export function IconFlame(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 2.5 C12 6 8.5 7 8.5 11 a3.5 3.5 0 0 0 7 0 c0 -1.6 -1 -2.6 -1 -4 1.8 1 3.5 3.2 3.5 6.2 a6 6 0 0 1 -12 0 C6 8 12 7 12 2.5 Z" />
    </Svg>
  );
}

/** The — "the loai". */
export function IconTag(p: Props) {
  return (
    <Svg {...p}>
      <path d="M11.6 3.4 H20 v8.4 l-8.6 8.6 a2 2 0 0 1 -2.8 0 L3.4 14.6 a2 2 0 0 1 0 -2.8 Z" />
      <circle cx="16.4" cy="7.6" r="1.4" />
    </Svg>
  );
}

/** Khien — khu kiem duyet noi dung. */
export function IconShield(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 3.2 5.4 5.7v5.1c0 4 2.7 7.6 6.6 9 3.9-1.4 6.6-5 6.6-9V5.7L12 3.2Z" />
      <path d="M9.2 12.1l2 2 3.6-3.9" />
    </Svg>
  );
}

/** Cai loa/bang tin — khu bai dang. */
export function IconMegaphone(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 10.5v3a1.5 1.5 0 0 0 1.5 1.5H7l2.6 3.4a1 1 0 0 0 1.8-.6V6.2a1 1 0 0 0-1.8-.6L7 9H5.5A1.5 1.5 0 0 0 4 10.5Z" />
      <path d="M14.4 9.1a4 4 0 0 1 0 5.8M17 6.8a7.5 7.5 0 0 1 0 10.4" />
    </Svg>
  );
}

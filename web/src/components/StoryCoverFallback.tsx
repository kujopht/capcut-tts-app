/**
 * Bia du phong cho truyen chua co anh bia.
 *
 * VI SAO TON TAI: ban truoc dat CHU CAI DAU cua ten truyen to giua tam bia —
 * "V", "N", "Z". Mot chu cai don doc doc ra la "cho nay chua lam xong": no la
 * mot cho trong duoc dan nhan, khong phai mot thiet ke. Ban nay khong con chu
 * cai nao ca.
 *
 * Thay vao do la mot DAU AN: nam hinh co nghia trong the loai — sao, sach, la
 * ban, rune, mat trang — chon theo ham bam cua `novel_id`. Cung mot truyen luon
 * ra cung mot dau an va cung mot cap mau, de nguoi doc nhan ra truyen quen.
 *
 * Ve bang SVG noi tuyen theo dung tien le cua `ProviderIcons.tsx`: khong tep
 * anh, khong goi phu thuoc, va khong bao gio dung tranh nen toan trang lam bia.
 *
 * KIEN TRUC cho tuong lai: khi backend co anh bia that, `NovelCover` phu lop
 * `.cover-image` len tren va khong ai thay component nay nua. Khong phai sua gi
 * o day, va khong co truong API nao duoc bia ra bay gio.
 */

import { sigilFor, type CoverSigil } from "@/lib/cover";

/**
 * Cac dau an. Dung `currentColor` de mau den tu CSS — nho vay mot dau an dung
 * duoc tren moi cap mau nen ma khong phai khai bao lai.
 */
const HINH: Record<CoverSigil, React.ReactNode> = {
  // Sao bon canh kem tia — "phep thuat", "dieu ky".
  sao: (
    <>
      <path d="M32 8 L36.5 27.5 L56 32 L36.5 36.5 L32 56 L27.5 36.5 L8 32 L27.5 27.5 Z" />
      <circle cx="50" cy="14" r="2.2" opacity="0.7" />
      <circle cx="14" cy="48" r="1.6" opacity="0.55" />
    </>
  ),
  // Sach mo — "truyen".
  sach: (
    <>
      <path
        d="M32 18 C26 13 18 12 11 13 L11 47 C18 46 26 47 32 51 C38 47 46 46 53 47 L53 13 C46 12 38 13 32 18 Z"
        fill="none"
        strokeWidth="3.2"
        stroke="currentColor"
        strokeLinejoin="round"
      />
      <path d="M32 18 L32 51" fill="none" strokeWidth="2.6" stroke="currentColor" />
    </>
  ),
  // La ban — "phieu luu", "kham pha".
  laban: (
    <>
      <circle
        cx="32" cy="32" r="20"
        fill="none" strokeWidth="3.2" stroke="currentColor"
      />
      <path d="M39 25 L28.5 28.5 L25 39 L35.5 35.5 Z" />
      <circle cx="32" cy="32" r="2.4" />
    </>
  ),
  // Rune — "co xua", "bi an".
  rune: (
    <>
      <path
        d="M32 10 L32 54 M32 22 L44 14 M32 22 L20 14 M32 38 L44 30 M32 38 L20 30"
        fill="none" strokeWidth="3.4" stroke="currentColor" strokeLinecap="round"
      />
    </>
  ),
  // Trang khuyet kem sao — "dem", "yen tinh".
  trang: (
    <>
      <path d="M40 12 A20 20 0 1 0 40 52 A16 16 0 1 1 40 12 Z" />
      <path d="M46 22 L48 27 L53 29 L48 31 L46 36 L44 31 L39 29 L44 27 Z" opacity="0.8" />
    </>
  ),
};

export function StoryCoverFallback({ seed }: { seed: string }) {
  return (
    <svg
      className="cover-sigil"
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
    >
      {HINH[sigilFor(seed)]}
    </svg>
  );
}

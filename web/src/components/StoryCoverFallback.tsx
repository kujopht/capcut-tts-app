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

import { boCucFor, type CoverSigil } from "@/lib/cover";

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
  /*
    Trang khuyet kem sao — "dem", "yen tinh".

    Ve bang HAI vong tron va `fill-rule="evenodd"`, khong phai bang hai cung noi
    tiep nhau. Ban truoc dung `A20 ... A16` giua hai diem cach nhau 40 don vi:
    day cung 40 lon hon duong kinh 32 cua cung thu hai, nen theo dung dac ta SVG
    trinh duyet phai NONG ban kinh len cho vua — ca hai cung thanh r=20 va hinh
    ra mot dia tron dac, khong con la luoi liem. Loi nay chi thay duoc khi do
    that: o co 64px tren mot the bia, mot dia tron mo doc ra nhu mot cho trong.

    Vong trong lech sang phai 9 don vi va lon hon ban kinh vong ngoai tru be day
    luoi liem, nen hai dau luoi liem duoc cat gon thay vi vut nhon ra.
  */
  trang: (
    <>
      <path
        fillRule="evenodd"
        d="M32 12 A20 20 0 1 1 32 52 A20 20 0 1 1 32 12 Z
           M41 15 A17 17 0 1 1 41 49 A17 17 0 1 1 41 15 Z"
      />
      <path d="M50 16 L51.6 20.4 L56 22 L51.6 23.6 L50 28 L48.4 23.6 L44 22 L48.4 20.4 Z" opacity="0.8" />
    </>
  ),
};

/**
 * Dau an LON, mo, nam sau dau an chinh — nhu mot hinh KHAC tren be mat.
 *
 * BA quyet dinh o day deu la de sua mot ban truoc trong ra nhu loi ve:
 *
 *   1. NET, khong phai khoi dac. `fill="none" stroke="currentColor"` tren the
 *      `<g>` bien moi dau an — ke ca cac hinh dac nhu sao va mat trang — thanh
 *      mot hinh ve bang net. Ban dac phong to 2.15 lan cho ra mot mang sang lon
 *      co mep cat ngang giua tam bia, va cai mep do di thang qua khung huy hieu:
 *      no doc ra nhu mot loi ket xuat, khong phai mot hoa van.
 *
 *   2. LECH TAM. Dat dung giua thi no chi la ban phong to cua dau an nho nam
 *      truoc no — hai vong tron dong tam. Lech xuong duoi-phai thi hai lop co
 *      quan he bo cuc voi nhau.
 *
 *   3. TRAN MEP. `preserveAspectRatio="xMidYMid slice"` cho hinh phu kin tam bia
 *      3:2 va bi cat o mep, thay vi ngoi gon trong mot o vuong giua. Bi cat la
 *      dung y: mot hoa van chay ra ngoai khung trong ra rong hon chinh tam bia.
 */
function DauAnSau({ hinh, goc }: { hinh: CoverSigil; goc: number }) {
  return (
    <svg
      className="cover-sigil-sau"
      viewBox="0 0 64 64"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
        transform={`translate(44 42) rotate(${goc}) scale(2.35) translate(-32 -32)`}
      >
        {HINH[hinh]}
      </g>
    </svg>
  );
}

/**
 * Ca BO CUC cua bia du phong, khong chi mot hinh.
 *
 * Nam lop, tu duoi len:
 *
 *   1. gradient theo `novel_id`            — `.cover-fallback` (o `NovelCover`)
 *   2. dom sang + vet cheo mo              — `.cover-pattern`
 *   3. dau an LON mo phia sau              — `.cover-sigil-sau`
 *   4. dau an nho ro net trong khung huy hieu — `.cover-crest` + `.cover-sigil`
 *   5. quang mep + lop toi dan             — `.cover-fallback::after`
 *
 * Khung huy hieu nam O DAY chu khong o `NovelCover`: ca bo cuc bia du phong la
 * MOT thu, va khi backend co bia that thi `NovelCover` chi can phu
 * `.cover-image` len tren — khong ai phai thao ra tung lop.
 */
export function StoryCoverFallback({ seed }: { seed: string }) {
  const { truoc, sau, goc } = boCucFor(seed);
  return (
    <>
      <DauAnSau hinh={sau} goc={goc} />
      <span className="cover-crest">
        {/* KHONG con chu cai dau. Xem ghi chu o dau tep de biet vi sao. */}
        <svg
          className="cover-sigil"
          viewBox="0 0 64 64"
          aria-hidden="true"
          focusable="false"
          fill="currentColor"
        >
          {HINH[truoc]}
        </svg>
      </span>
    </>
  );
}

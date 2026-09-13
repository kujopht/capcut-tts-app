/**
 * Tuy chon DOC — co chu va be ngang cot chu, luu tren may nguoi doc.
 *
 * Vi sao la mot module rieng chu khong phai `useState` trong trang doc: mot
 * lua chon doc phai SONG QUA dieu huong. Nguoi doc chinh co chu o chuong 1
 * roi bam sang chuong 2 ma phai chinh lai la mot khuyet tat, khong phai mot
 * chi tiet nho.
 *
 * `localStorage` co the NEM (cua so rieng tu, trinh duyet chan luu tru theo
 * trang), nen moi lan doc/ghi deu boc try/catch va roi ve mac dinh — khong
 * bao gio de mot tuy chon lam hong trang doc.
 */

export type CoChu = "nho" | "vua" | "lon" | "rat-lon";
export type BeNgang = "hep" | "vua" | "rong";

export type TuyChonDoc = {
  coChu: CoChu;
  beNgang: BeNgang;
};

export const MAC_DINH: TuyChonDoc = { coChu: "vua", beNgang: "vua" };

const KHOA = "fas.doc.tuychon";

const CO_CHU: readonly CoChu[] = ["nho", "vua", "lon", "rat-lon"];
const BE_NGANG: readonly BeNgang[] = ["hep", "vua", "rong"];

/** Nhan chu THEO THU TU tang dan — dung cho nut A-/A+. */
export const THU_TU_CO_CHU = CO_CHU;

export function doc(): TuyChonDoc {
  if (typeof window === "undefined") return MAC_DINH;
  try {
    const tho = window.localStorage.getItem(KHOA);
    if (!tho) return MAC_DINH;
    const d = JSON.parse(tho) as Partial<TuyChonDoc>;
    return {
      coChu: CO_CHU.includes(d.coChu as CoChu) ? (d.coChu as CoChu) : MAC_DINH.coChu,
      beNgang: BE_NGANG.includes(d.beNgang as BeNgang)
        ? (d.beNgang as BeNgang)
        : MAC_DINH.beNgang,
    };
  } catch {
    return MAC_DINH;
  }
}

export function ghi(d: TuyChonDoc): void {
  if (typeof window === "undefined") return;
  _anh = d;                       // anh chup moi TRUOC khi bao, xem duoi
  try {
    window.localStorage.setItem(KHOA, JSON.stringify(d));
  } catch {
    /* Khong luu duoc thi thoi — lua chon van co hieu luc trong phien nay. */
  }
  for (const f of _nghe) f();
}

/* ---------------------------------------------------------------- kho nho --
   Mot kho ngoai rat nho cho `useSyncExternalStore`.

   VI SAO KHONG doc `localStorage` trong `useEffect` roi `setState`: do la hai
   lan ve cho moi lan mo trang, va React 19 canh bao dung noi dung do
   ("cascading renders"). `useSyncExternalStore` sinh ra dung cho viec nay —
   no cho phep khai bao mot anh chup RIENG cho may chu, nen HTML dung-may-chu
   va lan ve dau o trinh duyet khop nhau ma khong can lan ve thu hai.

   `_anh` phai duoc NHO LAI: `getSnapshot` bi goi nhieu lan trong mot lan ve,
   va tra ve mot doi tuong MOI moi lan (`JSON.parse`) se lam React nghi kho
   doi lien tuc roi lap vo han.
--------------------------------------------------------------------------- */

let _anh: TuyChonDoc | null = null;
const _nghe = new Set<() => void>();

function anhChup(): TuyChonDoc {
  if (_anh === null) _anh = doc();
  return _anh;
}

/** Anh chup phia MAY CHU — luon la mac dinh, khong co `localStorage` o do. */
function anhChupMayChu(): TuyChonDoc {
  return MAC_DINH;
}

function dangKy(f: () => void): () => void {
  _nghe.add(f);
  return () => {
    _nghe.delete(f);
  };
}

export const kho = {
  dangKy,
  anhChup,
  anhChupMayChu,
};

/** Buoc len/xuong mot bac co chu, KHONG vuot ra ngoai thang. */
export function doiCoChu(hien: CoChu, buoc: 1 | -1): CoChu {
  const i = CO_CHU.indexOf(hien);
  const j = Math.min(CO_CHU.length - 1, Math.max(0, i + buoc));
  return CO_CHU[j];
}

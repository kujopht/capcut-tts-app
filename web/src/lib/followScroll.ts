/**
 * "THEO GIONG DOC" — may trang thai cua viec tu cuon trang theo doan dang doc.
 *
 * Tep thuan, khong React/DOM, de bai kiem Node chay thang (xem
 * `tests/reader-follow-scroll.test.mjs`).
 *
 * BA TRANG THAI, khong phai mot cong tac bat/tat:
 *
 *   "theo"     — dang tu cuon theo giong doc.
 *   "tam-dung" — nguoi dung vua TU cuon di cho khac. Ta KHONG BAO GIO giang
 *                trang ve giua luc ho dang cuon; hien nut "Tới đoạn đang đọc"
 *                de ho tu quay lai khi muon.
 *   "tat"      — nguoi dung CHU DONG tat "Theo giọng đọc". Khac "tam-dung" o
 *                cho: cuon tay khong lam gi, va chi chinh ho bat lai duoc.
 *
 * VI SAO nhan dien cuon tay bang Y DINH (lan chuot, vuot, phim cuon, keo
 * thanh cuon) thay vi su kien `scroll`: chinh lenh `scrollTo` cua ta cung ban
 * `scroll`, va cuon muot keo dai vai tram ms. Ban WIP truoc dung mot co
 * "bo qua 600ms" — cuon muot cham hon 600ms (may yeu, trang dai) la tu tat
 * chinh no; anh sang tai hinh anh lam doi vi tri cuon cung bi hieu la "nguoi
 * dung cuon". Y dinh thi khong bao gio do ma lenh cua ta sinh ra.
 */

export type CheDoTheo = "theo" | "tam-dung" | "tat";

/**
 * Trang thai ban dau.
 * - `giamChuyenDong`: `prefers-reduced-motion: reduce` -> mac dinh KHONG tu
 *   cuon (dac ta: "no auto-scroll if prefers-reduced-motion indicates it
 *   should be avoided"). Van to sang doan dang doc va van co nut "Tới đoạn
 *   đang đọc" (nhay tuc thi, khong truot).
 * - `daChonTruoc`: lua chon da luu cua nguoi dung (`true` = muon theo). Chu
 *   dong chon thi thang mac dinh, ke ca khi giam chuyen dong — luc do ta van
 *   cuon nhung KHONG truot muot (xem `kieuCuon`).
 */
export function cheDoBanDau(giamChuyenDong: boolean, daChonTruoc?: boolean | null): CheDoTheo {
  if (daChonTruoc === true) return "theo";
  if (daChonTruoc === false) return "tat";
  return giamChuyenDong ? "tat" : "theo";
}

export function khiNguoiDungCuon(s: CheDoTheo): CheDoTheo {
  return s === "theo" ? "tam-dung" : s;
}

/** Bam "Tới đoạn đang đọc": nhay toi doan do VA bat lai theo doi. */
export function khiToiDoanDangDoc(): CheDoTheo {
  return "theo";
}

/** Cong tac "Theo giọng đọc" trong trinh phat. */
export function khiBamCongTac(s: CheDoTheo): CheDoTheo {
  return s === "tat" ? "theo" : "tat";
}

/** Cong tac hien thi "dang bat" khi nao — tam dung van tinh la bat (nguoi
    dung chua tat, chi dang xem cho khac). */
export function congTacDangBat(s: CheDoTheo): boolean {
  return s !== "tat";
}

export interface SuKienNhapLieu {
  type: string;
  key?: string;
  /** Ten the (viet hoa) cua phan tu nhan su kien. */
  tagName?: string;
  isContentEditable?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  /** `pointerdown` len chinh `<html>` = bam vao thanh cuon cua trang. */
  laGocTaiLieu?: boolean;
}

const PHIM_CUON = new Set(["PageUp", "PageDown", "ArrowUp", "ArrowDown", "Home", "End", " ", "Spacebar"]);
const THE_NHAP = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * Su kien nay co phai la nguoi dung TU cuon trang khong.
 *
 * Phim cuon trong o nhap lieu (mui ten trong o tim kiem, Space trong o binh
 * luan) KHONG phai cuon trang. Space tren mot nut la bam nut. To hop co Ctrl/
 * Meta/Alt la phim tat cua trinh duyet, khong phai cuon.
 */
export function laCuonTay(e: SuKienNhapLieu): boolean {
  if (e.type === "wheel" || e.type === "touchmove") return true;
  if (e.type === "pointerdown" || e.type === "mousedown") return !!e.laGocTaiLieu;
  if (e.type !== "keydown") return false;
  if (!e.key || !PHIM_CUON.has(e.key)) return false;
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  const tag = (e.tagName ?? "").toUpperCase();
  if (THE_NHAP.has(tag) || e.isContentEditable) return false;
  if ((e.key === " " || e.key === "Spacebar") && (tag === "BUTTON" || tag === "A" || tag === "SUMMARY")) {
    return false;
  }
  return true;
}

export interface KhungNhin {
  /** Chieu cao cua so. */
  cao: number;
  /** Phan bi thanh dau trang (header dinh) che o tren. */
  tren: number;
  /** Phan bi trinh phat noi o duoi che. */
  duoi: number;
}

/**
 * Doan dang doc co nam trong VUNG DOC THOAI MAI khong — vung giua man hinh,
 * tru phan bi header va trinh phat che, chua mot le tren/duoi.
 *
 * Ta chi cuon khi doan RA KHOI vung nay, khong cuon moi lan doi doan: doan ke
 * tiep thuong nam ngay duoi doan truoc va van con thay, giang trang moi vai
 * giay la kieu "tu cuon" lam nguoi doc mat dong.
 */
export function trongVungDoc(hop: { top: number; bottom: number }, k: KhungNhin): boolean {
  const dauVung = k.tren + 8;
  const cuoiVung = k.cao - k.duoi - Math.max(48, (k.cao - k.tren - k.duoi) * 0.18);
  // Doan cao hon ca vung: chi can dau doan con trong vung la doc duoc.
  return hop.top >= dauVung && hop.top <= cuoiVung;
}

/**
 * Vi tri cuon dich de dua doan vao VI TRI DOC: khoang 28% chieu cao vung
 * thay duoc tinh tu mep tren — khong phai chinh giua. Nguoi dang doc can
 * thay phan TIEP THEO, khong phai phan vua qua.
 */
export function viTriCuonDich(hop: { top: number }, cuonHienTai: number, k: KhungNhin): number {
  const vung = Math.max(0, k.cao - k.tren - k.duoi);
  return Math.max(0, Math.round(cuonHienTai + hop.top - (k.tren + vung * 0.28)));
}

/** Truot muot hay nhay tuc thi. */
export function kieuCuon(giamChuyenDong: boolean): "smooth" | "auto" {
  return giamChuyenDong ? "auto" : "smooth";
}

/**
 * Nen hien nut noi "Tới đoạn đang đọc" khong — va mui ten chi len hay xuong.
 * Chi khi dang nghe CHINH chuong nay, chu dang hien, va doan dang doc nam
 * ngoai tam mat nhung ta KHONG tu cuon toi do (tam dung hoac tat).
 */
export function nutToiDoan(
  s: CheDoTheo,
  opts: { dangNghe: boolean; hienChu: boolean; doan: number; hop: { top: number; bottom: number } | null; k: KhungNhin },
): "len" | "xuong" | null {
  if (!opts.dangNghe || !opts.hienChu || opts.doan < 0 || !opts.hop) return null;
  if (s === "theo") return null;
  const { hop, k } = opts;
  if (hop.bottom < k.tren + 8) return "len";
  if (hop.top > k.cao - k.duoi - 8) return "xuong";
  return null;
}

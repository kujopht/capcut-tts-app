/**
 * Phien DOC/NGHE cua mot nguoi tren MOT trinh duyet: che do da chon, trang
 * thai khung chu, va "doc/nghe toi dau" cua tung chuong.
 *
 * Tep thuan (khong React, khong `@/`), de bai kiem Node chay thang
 * (`tests/reader-session-resume.test.mjs`).
 *
 * HAI CHO LUU, co ly do:
 *
 * - CHE DO + KHUNG CHU nam trong COOKIE `fas_doc_chedo`. Hai thu nay doi BO
 *   CUC cua trang (co trinh phat lon hay khong, co hien chu hay khong). May
 *   chu phai biet NGAY TU LAN VE DAU — neu chi nam trong `localStorage` thi
 *   HTML may chu ve mot kieu, roi trang nhay sang kieu khac sau khi JS chay.
 *   Cookie nay KHONG chua gi ca nhan: chi 4 lua chon hien thi.
 *
 * - TIEN DO TUNG CHUONG nam trong `localStorage` (`fas.doc.tiendo.v1`). Chi
 *   trinh duyet can no (de hien "Tiếp tục đọc/nghe"), khong gui len may chu
 *   voi moi request. Nguoi da dang nhap VAN duoc ghi tien do len may chu nhu
 *   truoc (`reportReadProgress`/`reportListenProgress`) — day la lop BO SUNG
 *   cho ca nguoi chua dang nhap, khong thay the.
 *
 * Moi lan doc/ghi deu boc try/catch: cua so rieng tu va trinh duyet chan luu
 * tru co the nem. Mot tuy chon hong KHONG BAO GIO duoc lam hong trang doc.
 */

export type CheDoDoc = "read" | "read_listen" | "listen";
export type KhungChu = "open" | "collapsed" | "closed";

export const CAC_CHE_DO: readonly CheDoDoc[] = ["read", "read_listen", "listen"];
const CAC_KHUNG: readonly KhungChu[] = ["open", "collapsed", "closed"];

export function laCheDo(x: unknown): x is CheDoDoc {
  return typeof x === "string" && (CAC_CHE_DO as readonly string[]).includes(x);
}

/* ------------------------------------------------------------ cookie che do */

export const COOKIE_CHE_DO = "fas_doc_chedo";

export interface TuyChonCheDo {
  cheDo: CheDoDoc | null;
  /** Khung chu O CHE DO NGHE. Hai che do co doc thi chu luon hien. */
  khungChu: KhungChu;
  /** Trinh phat noi dang thu gon thanh vien nho. */
  thuNho: boolean;
  /** `null` = chua tung chon (dung mac dinh theo `prefers-reduced-motion`). */
  theoGiong: boolean | null;
}

export const TUY_CHON_MAC_DINH: TuyChonCheDo = {
  cheDo: null,
  khungChu: "collapsed",
  thuNho: false,
  theoGiong: null,
};

/** "v1.<che do|->.<khung>.<thu nho 0|1>.<theo 0|1|->" — ngan, khong dau cach. */
export function maHoaCookie(t: TuyChonCheDo): string {
  const theo = t.theoGiong === null ? "-" : t.theoGiong ? "1" : "0";
  return `v1.${t.cheDo ?? "-"}.${t.khungChu}.${t.thuNho ? "1" : "0"}.${theo}`;
}

export function giaiMaCookie(gt: string | null | undefined): TuyChonCheDo {
  if (!gt) return TUY_CHON_MAC_DINH;
  const [v, cheDo, khung, thuNho, theo] = decodeURIComponent(gt).split(".");
  if (v !== "v1") return TUY_CHON_MAC_DINH;
  return {
    cheDo: laCheDo(cheDo) ? cheDo : null,
    khungChu: (CAC_KHUNG as readonly string[]).includes(khung) ? (khung as KhungChu) : "collapsed",
    thuNho: thuNho === "1",
    theoGiong: theo === "1" ? true : theo === "0" ? false : null,
  };
}

/** Chuoi `document.cookie` de ghi. Mot nam, `SameSite=Lax`, ca site. */
export function chuoiGhiCookie(t: TuyChonCheDo, https: boolean): string {
  return `${COOKIE_CHE_DO}=${encodeURIComponent(maHoaCookie(t))}; Path=/; Max-Age=31536000; SameSite=Lax${https ? "; Secure" : ""}`;
}

/**
 * Che do KHI MO TRANG. Thu tu uu tien:
 *   1. chuong khong co audio  -> luon "read" (khong co gi de nghe);
 *   2. chuong khong co chu    -> luon "listen" (khong co gi de doc);
 *   3. `?mode=` tren URL      -> lien ket co chu dich (vd tu nut "Nghe");
 *   4. lan chon truoc (cookie);
 *   5. mac dinh "read_listen": chu hien, trinh phat o day san — MOT trai
 *      nghiem, khong bat nguoi doc chon truoc khi thay chu.
 */
export function cheDoKhiMo(opts: {
  tuUrl?: string | null;
  daLuu?: CheDoDoc | null;
  coAudio: boolean;
  coChu: boolean;
}): CheDoDoc {
  if (!opts.coAudio) return "read";
  if (!opts.coChu) return "listen";
  if (laCheDo(opts.tuUrl)) return opts.tuUrl;
  if (opts.daLuu && laCheDo(opts.daLuu)) return opts.daLuu;
  return "read_listen";
}

/* --------------------------------------------------------- tien do chuong */

export const KHOA_TIEN_DO = "fas.doc.tiendo.v1";
/** Giu toi da chung nay chuong gan nhat — du cho vai truyen doc song song. */
export const TOI_DA_BAN_GHI = 40;
/** Qua lau thi khong moi "tiep tuc" nua: nguoi ta da quen minh o dau. */
export const HET_HAN_MS = 30 * 24 * 3600 * 1000;

export interface BanGhiTienDo {
  chapterId: string;
  novelId: string;
  cheDo: CheDoDoc;
  /** Doan van tren cung dang thay (0-based). */
  doan: number;
  tongDoan: number;
  /** Vi tri audio (giay). 0 khi chua nghe. */
  giay: number;
  thoiLuong: number;
  capNhat: number;
  /**
   * Ten truyen / ten chuong luc ghi (Sprint 2). TUY CHON: ban ghi Sprint 1
   * khong co, va Thu vien van dung duoc ban ghi do (chi thieu ten de hien o
   * dai "Đang đọc dở" khi truyen khong nam trong trang hien tai).
   */
  tenTruyen?: string;
  tenChuong?: string;
}

export interface KhoLuu {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

function docTatCa(kho: KhoLuu | null): BanGhiTienDo[] {
  if (!kho) return [];
  try {
    const tho = kho.getItem(KHOA_TIEN_DO);
    if (!tho) return [];
    const d = JSON.parse(tho) as { v?: number; ds?: unknown };
    if (d?.v !== 1 || !Array.isArray(d.ds)) return [];
    return d.ds.filter(
      (r): r is BanGhiTienDo =>
        !!r && typeof r === "object" &&
        typeof (r as BanGhiTienDo).chapterId === "string" &&
        Number.isFinite((r as BanGhiTienDo).doan) &&
        Number.isFinite((r as BanGhiTienDo).giay) &&
        Number.isFinite((r as BanGhiTienDo).capNhat),
    );
  } catch {
    return [];
  }
}

export function docTienDo(kho: KhoLuu | null, chapterId: string): BanGhiTienDo | null {
  return docTatCa(kho).find((r) => r.chapterId === chapterId) ?? null;
}

/** Moi ban ghi (moi -> cu) — Thu vien va trang truyen tinh "đọc tiếp" tu day. */
export function docTatCaTienDo(kho: KhoLuu | null): BanGhiTienDo[] {
  return docTatCa(kho);
}

/**
 * Ghi (gop) tien do mot chuong. Chi cac truong DUOC TRUYEN moi doi — cuon
 * trang khong xoa vi tri audio, va nguoc lai.
 */
export function ghiTienDo(
  kho: KhoLuu | null,
  chapterId: string,
  novelId: string,
  phan: Partial<Omit<BanGhiTienDo, "chapterId" | "novelId" | "capNhat">>,
  bayGio: number,
): BanGhiTienDo | null {
  if (!kho) return null;
  const ds = docTatCa(kho);
  const cu = ds.find((r) => r.chapterId === chapterId);
  const moi: BanGhiTienDo = {
    chapterId,
    novelId,
    cheDo: phan.cheDo ?? cu?.cheDo ?? "read",
    doan: phan.doan ?? cu?.doan ?? 0,
    tongDoan: phan.tongDoan ?? cu?.tongDoan ?? 0,
    giay: phan.giay ?? cu?.giay ?? 0,
    thoiLuong: phan.thoiLuong ?? cu?.thoiLuong ?? 0,
    capNhat: bayGio,
  };
  // Chi gan khi CO gia tri — ban ghi khong co ten van y het dang Sprint 1.
  const tenTruyen = phan.tenTruyen ?? cu?.tenTruyen;
  const tenChuong = phan.tenChuong ?? cu?.tenChuong;
  if (tenTruyen) moi.tenTruyen = tenTruyen.slice(0, 160);
  if (tenChuong) moi.tenChuong = tenChuong.slice(0, 160);
  const conLai = ds.filter((r) => r.chapterId !== chapterId);
  const ra = [moi, ...conLai].slice(0, TOI_DA_BAN_GHI);
  try {
    kho.setItem(KHOA_TIEN_DO, JSON.stringify({ v: 1, ds: ra }));
  } catch {
    /* Day ho hoac bi chan: lan sau khong co loi moi tiep tuc, the thoi. */
  }
  return moi;
}

export interface DeXuatTiepTuc {
  doc: { doan: number; tongDoan: number } | null;
  nghe: { giay: number; thoiLuong: number } | null;
}

/**
 * Co nen moi "Tiếp tục đọc" / "Tiếp tục nghe" khong.
 *
 * Khong moi khi: chua co ban ghi; ban ghi qua cu; vi tri chua dang ke (vai
 * doan dau, duoi 15 giay); hoac da xong (doan cuoi, vai giay cuoi) — luc do
 * nguoi ta can "chương sau", khong phai "tiếp tục".
 */
export function deXuatTiepTuc(
  r: BanGhiTienDo | null,
  opts: { coAudio: boolean; soDoan: number; bayGio: number },
): DeXuatTiepTuc | null {
  if (!r) return null;
  if (opts.bayGio - r.capNhat > HET_HAN_MS) return null;
  const tongDoan = opts.soDoan || r.tongDoan;
  const doc =
    tongDoan > 0 && r.doan >= 2 && r.doan < tongDoan - 1
      ? { doan: r.doan, tongDoan }
      : null;
  const nghe =
    opts.coAudio && r.giay >= 15 && (r.thoiLuong <= 0 || r.giay < r.thoiLuong - 10)
      ? { giay: r.giay, thoiLuong: r.thoiLuong }
      : null;
  if (!doc && !nghe) return null;
  return { doc, nghe };
}

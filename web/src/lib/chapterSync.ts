/**
 * DONG BO DOC <-> NGHE — tu thoi diem audio suy ra DOAN VAN dang duoc doc, va
 * nguoc lai (bam mot doan thi tua toi dau doan do).
 *
 * Tep nay KHONG import gi ca (khong React, khong `@/`), co y: bai kiem Node
 * nap thang tep `.ts` nay de chay thu logic that, khong phai doc chuoi ma
 * nguon (xem `tests/reader-sync-mapping.test.mjs`).
 *
 * HAI NGUON THOI GIAN, theo thu tu tin cay:
 *
 * 1. PHU DE DONG BO (`/api/chapters/{id}/transcript`, `available: true`) —
 *    moi doan phu de la MOT CAU cat ra tu CHINH van ban da dua vao TTS
 *    (`server/transcript.py`), co `start_ms`. Ta tim tung cau trong van ban
 *    chuong theo THU TU (con tro chi tien, khong lui) de biet cau do nam
 *    trong doan van nao.
 *
 * 2. UOC LUONG THEO DO DAI CHU — khi chuong KHONG co phu de. Do la trang
 *    thai cua ca ba truyen dang chay that (Butterfly Effect, Cold Between
 *    Wars, truyen Genshin): do 2026-09-24 tren production, moi chuong thu
 *    deu tra `available: false`. Giong TTS doc voi toc do gan nhu deu, nen
 *    "da doc toi ky tu thu bao nhieu" ti le thuan voi thoi gian. Ban cu (nhanh
 *    WIP) chia theo SO DOAN — sai nang voi chuong co doan dai ngan lech nhau
 *    (Cold Between Wars chuong 1: 329 doan, co doan 1 dong, co doan 20 dong).
 *
 * Ca hai huong (thoi gian -> doan, doan -> thoi gian) dung CHUNG mot mo hinh,
 * nen bam doan i thi vach sang dung ngay doan i — khong bao gio lech mot doan
 * vi hai cong thuc khac nhau.
 */

export interface DoanPhuDe {
  text: string;
  start_ms: number;
  end_ms: number;
}

/**
 * Chia noi dung chuong thanh DOAN VAN. DAY LA DINH NGHIA DUY NHAT: trang
 * may chu dung no de ve `<p>`, va bo dong bo dung no de dem doan — hai ben
 * lech nhau mot doan la vach sang nhay sai cho.
 */
export function tachDoanVan(noiDung: string | null | undefined): string[] {
  if (!noiDung) return [];
  return noiDung
    .replace(/\r\n?/g, "\n")
    .split(/\n[ \t]*\n+/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

/** Bo khung chu de so khop: chi giu chu cai + chu so, chu thuong, NFC.
    Khoang trang, dau cau, ngoac kep kieu "thong minh"… deu khong duoc lam
    mot cau phu de "khong tim thay" trong van ban goc. */
function khung(s: string): string {
  return s.normalize("NFC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** Tim nhi phan: chi so CUOI CUNG co `start_ms <= ms`, hoac -1. */
export function timDoanPhuDe(doan: readonly DoanPhuDe[], ms: number): number {
  let lo = 0;
  let hi = doan.length - 1;
  let kq = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (doan[mid].start_ms <= ms) {
      kq = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return kq;
}

/**
 * Anh xa moi doan phu de -> chi so doan van (0-based). Ket qua LUON khong
 * giam (cau sau khong bao gio nam o doan truoc cau truoc).
 *
 * Cau khong tim thay (vd tac gia da sua chuong sau khi tao audio) duoc noi
 * suy tu hai cau tim thay gan nhat hai ben — khong bao gio de -1 lot ra ngoai
 * khi van ban co it nhat mot doan.
 */
export function lapBanDoPhuDe(doanVan: readonly string[], phuDe: readonly DoanPhuDe[]): number[] {
  const n = doanVan.length;
  const ra = new Array<number>(phuDe.length).fill(-1);
  if (n === 0 || phuDe.length === 0) return ra;

  // Khung cua CA chuong + bang tra "vi tri trong khung -> doan van".
  let toanBo = "";
  const batDauDoan: number[] = [];
  for (const p of doanVan) {
    batDauDoan.push(toanBo.length);
    toanBo += khung(p);
  }
  const doanTaiViTri = (viTri: number): number => {
    let lo = 0;
    let hi = n - 1;
    let kq = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (batDauDoan[mid] <= viTri) {
        kq = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return kq;
  };

  let conTro = 0;
  for (let i = 0; i < phuDe.length; i++) {
    const k = khung(phuDe[i].text);
    if (!k) continue;
    let viTri = toanBo.indexOf(k, conTro);
    let doDaiKhop = k.length;
    // Cau dai bi sua mot chu o cuoi van con khop phan dau.
    if (viTri < 0 && k.length > 24) {
      viTri = toanBo.indexOf(k.slice(0, 24), conTro);
      doDaiKhop = 24;
    }
    if (viTri < 0) continue;
    ra[i] = doanTaiViTri(viTri);
    // Tien con tro qua HET phan da khop: mot cau ngan lap lai ("Ha ha.") o
    // doan sau khong duoc khop nham vao ben trong cau dai vua qua.
    conTro = viTri + Math.max(1, doDaiKhop);
  }

  // Noi suy cho cau khong tim thay, giu tinh khong giam.
  let truoc = -1;
  for (let i = 0; i < ra.length; i++) {
    if (ra[i] >= 0) {
      truoc = i;
      continue;
    }
    let sau = i + 1;
    while (sau < ra.length && ra[sau] < 0) sau++;
    const a = truoc >= 0 ? ra[truoc] : 0;
    const b = sau < ra.length ? ra[sau] : n - 1;
    const tong = sau - truoc;
    const buoc = i - truoc;
    ra[i] = Math.min(n - 1, Math.max(a, Math.round(a + ((b - a) * buoc) / tong)));
  }
  for (let i = 1; i < ra.length; i++) if (ra[i] < ra[i - 1]) ra[i] = ra[i - 1];
  return ra;
}

/*
  Trong so cua MOT doan khi uoc luong theo do dai. Giong TTS ngat hoi o cuoi
  cau va nghi dai hon o cuoi doan; mot doan hai cau ngan KHONG ngan bang so ky
  tu cua no goi y. Hai hang so duoi day la "ky tu tuong duong" cua moi lan
  ngat — nho so voi mot doan trung binh (vai tram ky tu), nen sai so cua
  chung chi dich vach sang toi da vai giay.
*/
const NGAT_DOAN = 12;
const NGAT_CAU = 3;

function trongSo(p: string): number {
  const cau = (p.match(/[.!?…]+/g) ?? []).length;
  return p.length + NGAT_DOAN + NGAT_CAU * cau;
}

/** Ti le [0,1) noi MOI doan bat dau, tinh theo trong so do dai. */
export function lapMocUocLuong(doanVan: readonly string[]): number[] {
  const w = doanVan.map(trongSo);
  const tong = w.reduce((a, b) => a + b, 0);
  const moc: number[] = [];
  let tich = 0;
  for (const x of w) {
    moc.push(tong > 0 ? tich / tong : 0);
    tich += x;
  }
  return moc;
}

function doanTaiTiLe(moc: readonly number[], tiLe: number): number {
  let lo = 0;
  let hi = moc.length - 1;
  let kq = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (moc[mid] <= tiLe) {
      kq = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return kq;
}

/** Mo hinh dong bo cua MOT chuong — dung lai giua moi lan `timeupdate`. */
export interface MoHinhDongBo {
  soDoan: number;
  /** `true` khi dang dung phu de that; `false` = uoc luong theo do dai. */
  coPhuDe: boolean;
  phuDe: readonly DoanPhuDe[];
  banDo: readonly number[];
  moc: readonly number[];
}

export function lapMoHinh(doanVan: readonly string[], phuDe: readonly DoanPhuDe[] | null): MoHinhDongBo {
  const coPhuDe = !!phuDe && phuDe.length > 0 && doanVan.length > 0;
  return {
    soDoan: doanVan.length,
    coPhuDe,
    phuDe: coPhuDe ? phuDe! : [],
    banDo: coPhuDe ? lapBanDoPhuDe(doanVan, phuDe!) : [],
    moc: lapMocUocLuong(doanVan),
  };
}

/**
 * Doan dang duoc doc tai `giay`, hoac -1 khi chua co gi de noi (chua phat,
 * chua biet thoi luong, chuong khong co chu).
 */
export function doanDangDoc(m: MoHinhDongBo, giay: number, thoiLuong: number): number {
  if (m.soDoan === 0 || !Number.isFinite(giay) || giay < 0) return -1;
  if (m.coPhuDe) {
    const i = timDoanPhuDe(m.phuDe, Math.round(giay * 1000));
    return i < 0 ? 0 : m.banDo[i];
  }
  if (!Number.isFinite(thoiLuong) || thoiLuong <= 0) return -1;
  return doanTaiTiLe(m.moc, Math.min(0.999999, giay / thoiLuong));
}

/** Giay bat dau cua doan `i` — dung cho "Nghe từ đoạn này". `null` khi
    chua biet thoi luong va khong co phu de. */
export function giayBatDauDoan(m: MoHinhDongBo, i: number, thoiLuong: number): number | null {
  if (i < 0 || i >= m.soDoan) return null;
  if (m.coPhuDe) {
    const j = m.banDo.findIndex((d) => d >= i);
    if (j >= 0) return m.phuDe[j].start_ms / 1000;
    return null;
  }
  if (!Number.isFinite(thoiLuong) || thoiLuong <= 0) return null;
  // Cong mot khoang rat nho de lam tron nguoc khong roi ve doan truoc.
  return Math.min(thoiLuong, m.moc[i] * thoiLuong + 0.05);
}

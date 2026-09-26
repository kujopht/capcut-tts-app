/**
 * TIEN DO CUA MOT TRUYEN -> nut hanh dong chinh (Thu vien, trang truyen).
 *
 * Nguon: ban ghi tien do TUNG CHUONG ma trang chuong da luu tu Sprint 1
 * (`readerSession.ts`, `localStorage`) — co cho nguoi chua dang nhap. Voi nguoi
 * da dang nhap, trang con co the tron them con tro "Tiếp tục đọc/nghe" cua may
 * chu (`tronTienDoMayChu`), vi ban ghi cuc bo chi nam tren MOT trinh duyet.
 *
 * Tep thuan — bai kiem Node chay thang (`tests/novel-progress.test.mjs`).
 */

// `import type` bi xoa hoan toan khi chay — Node khong can duoi tep o day.
import type { BanGhiTienDo, CheDoDoc } from "./readerSession";

export type KieuTiepTuc = "moi" | "doc" | "nghe" | "ca-hai" | "xong";

export interface HanhDongTruyen {
  kieu: KieuTiepTuc;
  /** Nhan ngan (the Thu vien). */
  nhan: string;
  /** Nhan day du (trang truyen). */
  nhanDayDu: string;
  /** Duong dan dich; `null` = trang goi tu quyet (vd chua biet chuong dau). */
  href: string | null;
  /** Chuong dang do (de to sang trong muc luc). */
  chapterId: string | null;
  /** 0..1 tien do trong chuong dang do, `null` khi khong biet. */
  tiLe: number | null;
}

/** Nghe duoc it nhat chung nay giay moi coi la "dang nghe". */
const NGHE_TOI_THIEU = 15;

/** Ban ghi moi nhat cua mot truyen (cac ban ghi xep moi -> cu). */
export function banGhiMoiNhat(ds: readonly BanGhiTienDo[], novelId: string): BanGhiTienDo | null {
  let tot: BanGhiTienDo | null = null;
  for (const r of ds) {
    if (r.novelId !== novelId) continue;
    if (!tot || r.capNhat > tot.capNhat) tot = r;
  }
  return tot;
}

export function dangNghe(r: BanGhiTienDo): boolean {
  return r.giay >= NGHE_TOI_THIEU && !(r.thoiLuong > 0 && r.giay >= r.thoiLuong - 10);
}

export function dangDoc(r: BanGhiTienDo): boolean {
  return r.doan >= 1 && !(r.tongDoan > 0 && r.doan >= r.tongDoan - 1);
}

/** Chuong da doc/nghe XONG (toi doan cuoi hoac giay cuoi). */
export function daXong(r: BanGhiTienDo): boolean {
  const docXong = r.tongDoan > 0 && r.doan >= r.tongDoan - 1;
  const ngheXong = r.thoiLuong > 0 && r.giay >= r.thoiLuong - 10;
  return docXong || ngheXong;
}

function tiLeCua(r: BanGhiTienDo): number | null {
  if (r.thoiLuong > 0 && r.giay > 0) return Math.min(1, r.giay / r.thoiLuong);
  if (r.tongDoan > 0) return Math.min(1, (r.doan + 1) / r.tongDoan);
  return null;
}

function dich(chapterId: string, cheDo: CheDoDoc, tiep: boolean): string {
  const q = new URLSearchParams({ mode: cheDo });
  if (tiep) q.set("resume", "1");
  return `/chapters/${chapterId}?${q.toString()}`;
}

/**
 * Nut chinh cho mot truyen.
 *
 * @param r ban ghi moi nhat cua truyen (hoac null)
 * @param opts.coAudio truyen co audio
 * @param opts.chiAudio truyen chi co audio (kho audio cu)
 * @param opts.chuongDau chuong dau tien (de "Bắt đầu"), neu biet
 * @param opts.chuongSau ham tra chuong KE TIEP sau mot chuong (trang truyen biet muc luc)
 */
export function hanhDongTruyen(
  r: BanGhiTienDo | null,
  opts: {
    coAudio: boolean;
    chiAudio?: boolean;
    chuongDau?: string | null;
    chuongSau?: (chapterId: string) => string | null;
  },
): HanhDongTruyen {
  const cheDoMacDinh: CheDoDoc = opts.chiAudio ? "listen" : opts.coAudio ? "read_listen" : "read";
  if (!r) {
    return {
      kieu: "moi",
      nhan: "Bắt đầu",
      nhanDayDu: opts.chiAudio ? "Bắt đầu nghe" : "Bắt đầu đọc",
      href: opts.chuongDau ? dich(opts.chuongDau, cheDoMacDinh, false) : null,
      chapterId: null,
      tiLe: null,
    };
  }
  if (daXong(r) && !dangDoc(r) && !dangNghe(r)) {
    const ke = opts.chuongSau ? opts.chuongSau(r.chapterId) : null;
    const nghe = r.giay > 0 && opts.coAudio;
    return {
      kieu: "xong",
      nhan: nghe ? "Nghe tiếp" : "Đọc tiếp",
      nhanDayDu: ke ? (nghe ? "Nghe chương tiếp theo" : "Đọc chương tiếp theo") : "Đã tới chương mới nhất",
      href: ke ? dich(ke, nghe ? (opts.chiAudio ? "listen" : "read_listen") : r.cheDo, false) : null,
      chapterId: ke ?? r.chapterId,
      tiLe: ke ? 0 : 1,
    };
  }
  const nghe = opts.coAudio && dangNghe(r);
  const doc = dangDoc(r);
  if (nghe && doc) {
    return {
      kieu: "ca-hai",
      nhan: "Tiếp tục",
      nhanDayDu: "Tiếp tục đọc & nghe",
      href: dich(r.chapterId, "read_listen", true),
      chapterId: r.chapterId,
      tiLe: tiLeCua(r),
    };
  }
  if (nghe) {
    return {
      kieu: "nghe",
      nhan: "Nghe tiếp",
      nhanDayDu: "Nghe tiếp",
      href: dich(r.chapterId, opts.chiAudio || r.cheDo === "listen" ? "listen" : "read_listen", true),
      chapterId: r.chapterId,
      tiLe: tiLeCua(r),
    };
  }
  return {
    kieu: "doc",
    nhan: "Đọc tiếp",
    nhanDayDu: "Đọc tiếp",
    href: dich(r.chapterId, r.cheDo === "listen" ? "read_listen" : r.cheDo, true),
    chapterId: r.chapterId,
    tiLe: tiLeCua(r),
  };
}

/** Chuong nao da xong / dang do trong mot truyen — cho muc luc. */
export function trangThaiChuong(ds: readonly BanGhiTienDo[], novelId: string): Map<string, "dang" | "xong"> {
  const m = new Map<string, "dang" | "xong">();
  for (const r of ds) {
    if (r.novelId !== novelId) continue;
    m.set(r.chapterId, daXong(r) ? "xong" : "dang");
  }
  return m;
}

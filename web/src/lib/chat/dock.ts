/**
 * Chat Dock (Messenger desktop) — phan THUAN: thu tu cua so, so cua so hien theo be rong, chia hien/tran,
 * doc/ghi phuc hoi sau khi tai lai trang. Khong React, khong DOM, CHI `import type` — test chay thang bang
 * `node --test`.
 *
 * Quy uoc: `ds[0]` = cua so MOI NHAT (nam sat mep phai). Cua so hien = `ds.slice(0, n)`; phan con lai vao
 * NGAN TRAN ("+N"). Mo mot cuoc da co = dua no len dau va bo thu nho.
 */

export interface DockWindow {
  peerId: string;
  minimized: boolean;
}

/** Tong so cua so dang mo (hien + tran). Vuot thi cua so CU NHAT bi dong (nhap van giu o provider). */
export const DOCK_TOI_DA = 8;
/** Toi da cua so HIEN tren desktop — yeu cau san pham. */
export const DOCK_HIEN_TOI_DA = 3;
export const CUA_SO_RONG = 336;
/** 1024–1279: van VUA 3 cua so (3 x 304 + 2 khe + le phai + nut tran <= 1024). */
export const CUA_SO_RONG_HEP = 304;
export const DOCK_KHE = 12;
export const DOCK_LE_PHAI = 16;
/** Cho danh cho nut ngan tran "+N" (mot nut tron 48px + khe). */
export const DOCK_CHO_TRAN = 60;
export const MAN_HINH_DESKTOP = 1024;
export const MAN_HINH_DI_DONG = 640;

export function rongCuaSo(viewport: number): number {
  return viewport < 1280 ? CUA_SO_RONG_HEP : CUA_SO_RONG;
}

/**
 * So cua so HIEN duoc: di dong (<=640) = 0 (dung /messages toan man hinh); may tinh bang (641–1023) = 1;
 * desktop = so cua so VUA be rong (tru le phai + cho nut tran), toi da 3, it nhat 1.
 */
export function soCuaSoHien(viewport: number): number {
  if (!Number.isFinite(viewport) || viewport <= MAN_HINH_DI_DONG) return 0;
  if (viewport < MAN_HINH_DESKTOP) return 1;
  const w = rongCuaSo(viewport);
  const vua = Math.floor((viewport - DOCK_LE_PHAI - DOCK_CHO_TRAN + DOCK_KHE) / (w + DOCK_KHE));
  return Math.max(1, Math.min(DOCK_HIEN_TOI_DA, vua));
}

export function moCuaSo(ds: readonly DockWindow[], peerId: string, toiDa = DOCK_TOI_DA): DockWindow[] {
  const con = ds.filter((c) => c.peerId !== peerId);
  return [{ peerId, minimized: false }, ...con].slice(0, toiDa);
}

export function thuNhoCuaSo(ds: readonly DockWindow[], peerId: string, minimized: boolean): DockWindow[] {
  return ds.map((c) => (c.peerId === peerId ? { ...c, minimized } : c));
}

export function dongCuaSo(ds: readonly DockWindow[], peerId: string): DockWindow[] {
  return ds.filter((c) => c.peerId !== peerId);
}

export function chiaCuaSo(ds: readonly DockWindow[], n: number): { hien: DockWindow[]; tran: DockWindow[] } {
  const k = Math.max(0, n);
  return { hien: ds.slice(0, k), tran: ds.slice(k) };
}

/** Cua so dang MO THAT (hien, khong thu nho) cho mot nguoi — dung de quyet "da doc" khi tin moi den. */
export function dangXem(ds: readonly DockWindow[], n: number, peerId: string): boolean {
  return chiaCuaSo(ds, n).hien.some((c) => c.peerId === peerId && !c.minimized);
}

const ID_HOP_LE = /^[A-Za-z0-9_.-]{3,64}$/;

/** Phuc hoi tu `sessionStorage`: chuoi rac / khoa la / trung lap bi bo — khong bao gio nem loi. */
export function docDock(raw: string | null | undefined): DockWindow[] {
  if (!raw) return [];
  let du: unknown;
  try {
    du = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(du)) return [];
  const ra: DockWindow[] = [];
  for (const x of du) {
    const peerId = (x as { peerId?: unknown })?.peerId;
    if (typeof peerId !== "string" || !ID_HOP_LE.test(peerId) || ra.some((c) => c.peerId === peerId)) continue;
    ra.push({ peerId, minimized: Boolean((x as { minimized?: unknown }).minimized) });
    if (ra.length >= DOCK_TOI_DA) break;
  }
  return ra;
}

export function ghiDock(ds: readonly DockWindow[]): string {
  return JSON.stringify(ds.map((c) => ({ peerId: c.peerId, minimized: c.minimized })));
}

/** Nhap theo hoi thoai: chi giu chuoi khong rong cua ID hop le, cat 2000 ky tu (= tran o soan). */
export function docNhap(raw: string | null | undefined): Record<string, string> {
  if (!raw) return {};
  let du: unknown;
  try {
    du = JSON.parse(raw);
  } catch {
    return {};
  }
  if (!du || typeof du !== "object" || Array.isArray(du)) return {};
  const ra: Record<string, string> = {};
  for (const [k, v] of Object.entries(du as Record<string, unknown>)) {
    if (ID_HOP_LE.test(k) && typeof v === "string" && v.trim()) ra[k] = v.slice(0, 2000);
  }
  return ra;
}

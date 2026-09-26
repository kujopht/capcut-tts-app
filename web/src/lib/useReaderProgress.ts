"use client";

/**
 * Doc tien do doc/nghe cuc bo (ban ghi cua `readerSession.ts`) trong component.
 *
 * `useSyncExternalStore`: anh chup may chu la mang RONG, nen HTML may chu va
 * lan ve dau khop nhau; sau hydrate moi hien "Đọc tiếp". Nghe su kien `storage`
 * de mot tab khac vua doc xong chuong thi tab Thu vien cung cap nhat.
 *
 * Anh chup duoc NHO theo chuoi tho trong `localStorage` — tra mot mang moi o
 * moi lan goi se lam React ve lai vo han.
 */

import { useSyncExternalStore } from "react";
import { docTatCaTienDo, KHOA_TIEN_DO, type BanGhiTienDo } from "@/lib/readerSession";

const RONG: BanGhiTienDo[] = [];
let _tho: string | null = null;
let _anh: BanGhiTienDo[] = RONG;

function khoLuu() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function anhChup(): BanGhiTienDo[] {
  let tho: string | null = null;
  try {
    tho = khoLuu()?.getItem(KHOA_TIEN_DO) ?? null;
  } catch {
    tho = null;
  }
  if (tho === _tho) return _anh;
  _tho = tho;
  _anh = tho ? docTatCaTienDo(khoLuu()) : RONG;
  return _anh;
}

function dangKy(f: () => void): () => void {
  const khi = (e: StorageEvent) => {
    if (e.key === null || e.key === KHOA_TIEN_DO) f();
  };
  window.addEventListener("storage", khi);
  // Quay lai tab (vd tu trang chuong ve Thu vien trong CUNG tab) thi doc lai.
  window.addEventListener("focus", f);
  return () => {
    window.removeEventListener("storage", khi);
    window.removeEventListener("focus", f);
  };
}

export function useReaderProgress(): BanGhiTienDo[] {
  return useSyncExternalStore(dangKy, anhChup, () => RONG);
}

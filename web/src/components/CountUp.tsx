"use client";

/**
 * So dem chay tu 0 len gia tri thuc (lay cam hung tu component CountUp cua
 * React Bits — https://github.com/DavidHDev/react-bits — nhung viet lai tay,
 * khong dung framer-motion vi repo chua co dependency do; tu ve bang
 * requestAnimationFrame de khong them goi runtime nang cho mot hieu ung nho).
 *
 * Chay tu 0 o lan mount dau, sau do chi chay khi gia tri THAY DOI (khong chay
 * lai khi component chi re-render vi ly do khac). Gia tri SSR va render dau
 * tien cua client deu la 0 nen khong hydration mismatch. Tat hoan toan khi
 * nguoi dung dat prefers-reduced-motion — callback dau tien hien thang gia
 * tri cuoi, khong noi suy qua cac khung hinh trung gian.
 */

import { useEffect, useRef, useState } from "react";

const THOI_GIAN_MS = 500;

export function CountUp({ value, className }: { value: number; className?: string }) {
  const [hien, setHien] = useState(0);
  const giaTriTruoc = useRef(0);

  useEffect(() => {
    const tu = giaTriTruoc.current;
    const den = value;
    giaTriTruoc.current = den;
    if (tu === den) return;

    const giamHoatHinh = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frameId = 0;
    const batDau = performance.now();
    const buoc = (luc: number) => {
      if (giamHoatHinh) { setHien(den); return; }
      const tiLe = Math.min(1, (luc - batDau) / THOI_GIAN_MS);
      setHien(Math.round(tu + (den - tu) * tiLe));
      if (tiLe < 1) frameId = requestAnimationFrame(buoc);
    };
    frameId = requestAnimationFrame(buoc);
    return () => cancelAnimationFrame(frameId);
  }, [value]);

  return <span className={className}>{hien}</span>;
}

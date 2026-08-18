"use client";

/**
 * So dem chay tu 0 len gia tri thuc (lay cam hung tu component CountUp cua
 * React Bits — https://github.com/DavidHDev/react-bits — nhung viet lai tay,
 * khong dung framer-motion vi repo chua co dependency do; tu ve bang
 * requestAnimationFrame de khong them goi runtime nang cho mot hieu ung nho).
 *
 * Chi chay hoat hinh khi gia tri THAY DOI (khong chay lai khi component chi
 * re-render vi ly do khac) va tat hoan toan khi nguoi dung dat
 * prefers-reduced-motion — luc do hien luon gia tri cuoi, dung nhu cac hoat
 * hinh khac trong `globals.css`.
 */

import { useEffect, useRef, useState } from "react";

const THOI_GIAN_MS = 500;

export function CountUp({ value, className }: { value: number; className?: string }) {
  const [hien, setHien] = useState(value);
  const giaTriTruoc = useRef(value);

  useEffect(() => {
    const tu = giaTriTruoc.current;
    const den = value;
    giaTriTruoc.current = den;
    if (tu === den) return;

    const giamHoatHinh = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let dungLai = false;
    const batDau = performance.now();
    const buoc = (luc: number) => {
      if (dungLai) return;
      if (giamHoatHinh) { setHien(den); return; }
      const tiLe = Math.min(1, (luc - batDau) / THOI_GIAN_MS);
      setHien(Math.round(tu + (den - tu) * tiLe));
      if (tiLe < 1) requestAnimationFrame(buoc);
    };
    requestAnimationFrame(buoc);
    return () => { dungLai = true; };
  }, [value]);

  return <span className={className}>{hien}</span>;
}

"use client";

/**
 * The bao noi dung trang — tu V2 (Cloud Veil), qua V3, den Aether Rift V4.
 *
 * V4 (dac ta muc 11 — "First attempt: DO NOT fade route UI at all"): the
 * bao nay HIEN KHONG con gan animation nao ca (`.route-content[data-state=
 * ...]` da bi go khoi globals.css). `{children}` doi NGAY khi Next.js doi
 * route — dac ta V4 muon dieu huong cam giac TUC THI, va bat ky do tre nao
 * (ke ca mot cu mo 140-180ms nhu V2/V3) deu cong them vao cam giac "cho".
 *
 * The bao van duoc GIU LAI (khong go component) vi hai ly do: (1) `data-
 * state` van duoc dat, san sang cho mot lan mo CUC ngan (opacity 0.96->1,
 * 80-120ms, KHONG translateY) NEU QA sau nay thay viec doi noi dung qua
 * dot ngot — chi can them lai hai quy tac CSS, khong doi component nay;
 * (2) `className="wrap route-content"` giu nguyen cau truc DOM/bo cuc hien
 * co (lop `.wrap` gio dat o day thay vi `layout.tsx`).
 */

import { useSyncExternalStore } from "react";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

export function ContentAtmosphere({ children }: { children: React.ReactNode }) {
  const { trangThai } = useSyncExternalStore(
    routeTransitionStore.subscribe,
    routeTransitionStore.getSnapshot,
    () => routeTransitionStore.getSnapshot(),
  );

  return (
    <div className="wrap route-content" data-state={trangThai}>
      {children}
    </div>
  );
}

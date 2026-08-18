"use client";

/**
 * Man may/suong che chuyen canh route — "Cloud Veil V3: Celestial Mist
 * Ribbon".
 *
 * Y DINH: doi canh trong mot the gioi anime fantasy la may TROI QUA the
 * gioi phia SAU giao dien — giao dien (PageHero/nut/o tim/the/Bento) LUON
 * o TREN, khong bao gio bi may che (khac V1, bi tu choi vi che ca giao
 * dien). V2 dung z-index dung nhung hinh hoc SAI (ba "cuc may" tron/oval mo
 * to, doc ra nhu mot cham CSS demo — bi tu choi o khau thi giac); V3 GIU
 * NGUYEN kien truc z-index/state-machine cua V2, chi THAY THE hinh hoc:
 * sau DAI SUONG da giac hanh van tay (`clip-path: polygon(...)`), thon dai,
 * mep dao dong doc lap — xem chu thich day du o globals.css (khoi
 * ".route-veil" dau tien) cho ly do ky thuat V2 bi "toi den"/"mot khoi".
 *
 * KIEN TRUC (khong doi so V2):
 *
 *   - MOUNT MOT LAN duy nhat o `layout.tsx`, ngang hang voi `PageBackground`.
 *     `.route-veil` dat z-index **-1**, `.page-bg` dat z-index **-2** — CA
 *     HAI la con am, `<main>` (khong dinh vi) LUON ve SAU nhom con am du no
 *     khong dat z-index nao (CSS2.1 Appendix E). Ket qua: NEN < MAY < GIAO
 *     DIEN.
 *   - Doc trang thai tu `lib/routeTransitionStore.ts` — CUNG mot kho ma
 *     `PageBackground.tsx` (va `ContentAtmosphere.tsx`) doc, qua
 *     `useSyncExternalStore`. Component nay KHONG tu theo doi `pathname`.
 *   - `data-state`/`data-theme` la HAI THUOC TINH DOM DUY NHAT dieu khien
 *     toan bo hoat hinh. Luc `data-state="idle"` KHONG co `animation` nao
 *     dang chay — chi phi luc dung yen la SO KHONG.
 *   - KHONG Canvas, KHONG WebGL, KHONG `requestAnimationFrame`, KHONG SVG
 *     filter dong (`feTurbulence`) — chi `transform`/`opacity` duoc hoat
 *     hinh, `clip-path`/`filter: blur()` la GIA TRI TINH tren tung lop.
 *     SAU phan tu `<div>` co dinh so luong (dung dac ta "2 dan dau + 2 vua +
 *     1 trung tam + 1 theo sau"):
 *
 *       .mist-wisp-1/.mist-wisp-2   2 dai mong dan dau (tang GAN)
 *       .mist-ribbon-a/.mist-ribbon-b  2 dai may vua (tang XA/GIUA)
 *       .mist-core                  1 dai suong dac, trung tam (tang GIUA)
 *       .mist-trail                 1 dai mong theo sau, chi hien pha "lo"
 *   - `pointer-events: none` + `aria-hidden`: day la trang tri, khong bao
 *     gio chan click hay lot vao cay truy cap.
 */

import { useSyncExternalStore } from "react";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

export function RouteTransitionVeil() {
  const { trangThai, ten, tenDich } = useSyncExternalStore(
    routeTransitionStore.subscribe,
    routeTransitionStore.getSnapshot,
    () => routeTransitionStore.getSnapshot(),
  );

  /*
    Mau man suong LUON la mau cua DIEM DEN — ke ca trong pha "covering" khi
    `ten` (chu de dang duoc PageBackground ve that) van con la chu de CU.
    `tenDich` duoc kho dat NGAY khi bat dau chuyen canh (truoc ca khi anh nen
    kip doi), nen may bat dau nhuom mau the gioi sap den tu khung hinh dau
    tien — doc ra nhu "may dang mang mau cua noi minh sap toi", khong phai
    "may cua noi minh vua roi". Khi khong co chuyen canh nao (`tenDich ===
    null`), dung `ten` (chu de dang hien).
  */
  const chuDeMau = tenDich ?? ten ?? "auth";

  return (
    <div
      className="route-veil"
      aria-hidden="true"
      data-state={trangThai}
      data-theme={chuDeMau}
    >
      <div className="mist mist-wisp-1" />
      <div className="mist mist-ribbon-a" />
      <div className="mist mist-wisp-2" />
      <div className="mist mist-core" />
      <div className="mist mist-ribbon-b" />
      <div className="mist mist-trail" />
    </div>
  );
}

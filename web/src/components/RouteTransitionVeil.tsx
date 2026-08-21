"use client";

/**
 * Hieu ung chuyen canh route — "Aether Rift Reveal V4".
 *
 * Y DINH: KHONG con "mot vat troi qua man hinh" (V1-V3, tat ca deu bi tu
 * choi) — thay bang "CHINH the gioi bien hinh sang dia diem moi". Nen MOI
 * duoc tiet lo dan qua MOT duong bien huu co (SVG, duong Bezier bac ba,
 * KHONG con polygon) quet ngang qua khung hinh; giao dien (PageHero/nut/o
 * tim/the/Bento) LUON o TREN, khong bao gio bi anh huong. Xem chu thich
 * day du o globals.css (khoi ".aether-rift") cho ly do ky thuat V2/V3 bi
 * tu choi va kien truc ba-path-dung-chung cua V4.
 *
 * KIEN TRUC:
 *
 *   - MOUNT MOT LAN duy nhat o `layout.tsx`, ngang hang voi `PageBackground`.
 *     `.aether-rift` dat z-index **-1**, `.page-bg` dat z-index **-2** —
 *     giu nguyen kien truc z-index am da kiem chung tu V2/V3.
 *   - Ba phan tu SVG (`.aether-fill-path` trong `<clipPath>`, `.aether-
 *     feather-path`, `.aether-seam-path`) dung CHINH XAC MOT duong cong —
 *     `PageBackground.tsx` tham chieu `#aether-fill-clip` qua CSS `clip-
 *     path: url(...)` tren lop nen dang "revealing" cua no, nen duong bien
 *     hien thi (feather/seam) va duong bien THAT SU cua nen (fill) LUON
 *     khop nhau tuyet doi.
 *   - Doc trang thai tu `lib/routeTransitionStore.ts` — CUNG mot kho ma
 *     `PageBackground.tsx` doc, qua `useSyncExternalStore`. Component nay
 *     KHONG tu theo doi `pathname`.
 *   - `data-state`/`data-theme` la HAI THUOC TINH DOM DUY NHAT dieu khien
 *     toan bo hoat hinh. Luc `data-state="idle"` KHONG co `animation` nao
 *     dang chay — chi phi luc dung yen la SO KHONG.
 *   - KHONG Canvas, KHONG WebGL, KHONG `requestAnimationFrame`, KHONG hoat
 *     hinh SVG filter lien tuc — CHI thuoc tinh CSS `d` (duong cong) va
 *     `opacity`/`transform` (trang tri phu: 2 lan may + 1 dai suong tan +
 *     4 dom sang +, rieng Home, 2 vet la) duoc hoat hinh.
 *   - `pointer-events: none` + `aria-hidden`: day la trang tri, khong bao
 *     gio chan click hay lot vao cay truy cap.
 */

import { useSyncExternalStore } from "react";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

/**
 * Toa do "from" (chua lo) cua duong cong dung chung — xem chu thich
 * ".aether-rift" o globals.css cho each nghia hinh hoc day du. Dat lam gia
 * tri KHOI TAO tinh trong JSX (khop CHINH XAC voi `0%`/`from` cua cac
 * `@keyframes aether-sweep-*`) de duong bien co hinh dang dung ngay ca
 * truoc khi bat ky hoat hinh nao tung chay.
 */
const DUONG_BIEN_FILL_BAN_DAU =
  "M 0.02,0 C 0.15,0.08 0.00,0.20 0.10,0.30 C 0.20,0.40 -0.05,0.50 0.05,0.62 C 0.15,0.74 0.00,0.85 0.12,1 L -2,1 L -2,0 Z";
const DUONG_BIEN_NET_BAN_DAU =
  "M 2,0 C 15,8 0,20 10,30 C 20,40 -5,50 5,62 C 15,74 0,85 12,100";

export function RouteTransitionVeil() {
  const { trangThai, ten, tenMoi, the } = useSyncExternalStore(
    routeTransitionStore.subscribe,
    routeTransitionStore.getSnapshot,
    () => routeTransitionStore.getSnapshot(),
  );

  /*
    Mau LUON la mau cua DIA DIEM DICH — `tenMoi` duoc kho dat NGAY khi bat
    dau mot lan reveal (truoc ca khi lop nen kip doi), nen duong bien bat
    dau nhuom mau the gioi SAP den tu khung hinh dau tien. Khi khong co
    reveal nao dang chay (`tenMoi === null`), dung `ten` (chu de dang hien).
  */
  const chuDeMau = tenMoi ?? ten ?? "auth";

  return (
    <div
      className="aether-rift"
      aria-hidden="true"
      data-state={trangThai}
      data-theme={chuDeMau}
    >
      {/*
        `key={the}` tren THE BAO NAY (khong phai tren `.aether-rift` — the
        bao ngoai phai ON DINH de `data-state`/`data-theme` ap dung ngay,
        khong remount): dieu huong LIEN TIEP (Home -> Explore -> Animation
        trong <100ms) khong lam `trangThai` roi ve "idle" giua chung (no o
        lai "revealing" xuyen suot, chi `tenMoi`/`the` doi) — neu khong co
        `key` nay, CSS animation dang chay se KHONG tu restart (theo dung
        dac ta CSS: doi thuoc tinh khong lien quan cua mot animation DANG
        chay khong lam no chay lai tu dau). Tang `the` ep React GO HAN va
        DUNG LAI moi SVG/trang tri phu — dam bao duong bien LUON bat dau
        lai tu 0% cho DICH MOI NHAT, dung dac ta "newest destination wins,
        current effect redirects/restarts gracefully".
      */}
      <div key={the} className="aether-rift-anim">
        <svg
          className="aether-rift-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
          focusable="false"
        >
          <defs>
            <clipPath id="aether-fill-clip" clipPathUnits="objectBoundingBox">
              <path className="aether-fill-path" d={DUONG_BIEN_FILL_BAN_DAU} />
            </clipPath>
          </defs>
          <path className="aether-feather-path" d={DUONG_BIEN_NET_BAN_DAU} />
          <path className="aether-seam-path" d={DUONG_BIEN_NET_BAN_DAU} />
        </svg>

        <div className="aether-wisp aether-wisp-1" />
        <div className="aether-wisp aether-wisp-2" />
        <div className="aether-haze" />
        <div className="aether-mote aether-mote-1" />
        <div className="aether-mote aether-mote-2" />
        <div className="aether-mote aether-mote-3" />
        <div className="aether-mote aether-mote-4" />
        {/* Vet la — CHI hien khi CSS chon (`[data-theme="home"]`), xem globals.css. */}
        <div className="aether-leaf aether-leaf-1" />
        <div className="aether-leaf aether-leaf-2" />
      </div>
    </div>
  );
}

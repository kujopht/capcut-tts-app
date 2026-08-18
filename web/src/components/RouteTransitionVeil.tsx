"use client";

/**
 * Man may/suong che chuyen canh route — "Cloud Veil Route Transition V2".
 *
 * Y DINH: doi canh trong mot the gioi anime fantasy la may TROI QUA the
 * gioi phia SAU giao dien — giao dien (PageHero/nut/o tim/the/Bento) LUON
 * o TREN, khong bao gio bi may che (khac V1, bi tu choi vi che ca giao
 * dien — xem lich su git). Trinh tu (mot duong QUET lien tuc, khong con
 * "phinh to che kin roi xep lai"):
 *
 *   trang HIEN TAI -> mui may (wisp) di truoc -> khoi may chinh/phu quet
 *   qua NEN (KHONG qua giao dien) -> nen doi dung luc may day nhat -> may
 *   tiep tuc quet -> suong tan dan (trailing) -> trang MOI da hien tu truoc
 *
 * KIEN TRUC:
 *
 *   - MOUNT MOT LAN duy nhat o `layout.tsx`, ngang hang voi `PageBackground`.
 *     `.route-veil` dat z-index **-1**, `.page-bg` dat z-index **-2** — CA
 *     HAI la con am, `<main>` (khong dinh vi) LUON ve SAU nhom con am du no
 *     khong dat z-index nao (CSS2.1 Appendix E) — da kiem thuc te khong co
 *     `position`/`transform`/`filter`/`isolation` nao tren
 *     `body`/`html`/`main`/`.wrap` pha vo dieu nay. Ket qua: NEN < MAY <
 *     GIAO DIEN, dung THU TU dac ta yeu cau — xem chu thich dau khoi
 *     ".route-veil" o globals.css cho chi tiet.
 *   - Doc trang thai tu `lib/routeTransitionStore.ts` — CUNG mot kho ma
 *     `PageBackground.tsx` (va `ContentAtmosphere.tsx`, cho vi chuyen canh
 *     rieng cua noi dung) doc, qua `useSyncExternalStore`. Component nay
 *     KHONG tu theo doi `pathname`: chi PageBackground lam viec do (mot noi
 *     duy nhat goi `diTinh`), tranh hai vong kiem doc lap co the bao nhau
 *     lech nhip.
 *   - `data-state`/`data-theme` la HAI THUOC TINH DOM DUY NHAT dieu khien
 *     toan bo hoat hinh — xem cac quy tac `.route-veil[data-state=...]` va
 *     `.route-veil[data-theme=...]` o globals.css. Luc `data-state="idle"`
 *     (mac dinh, gan het thoi gian) KHONG co `animation` nao dang chay —
 *     chi phi luc dung yen la SO KHONG (dung yeu cau "essentially zero idle
 *     cost").
 *   - KHONG Canvas, KHONG WebGL, KHONG `requestAnimationFrame` — moi chuyen
 *     dong la CSS keyframes tren `transform`/`opacity`/`filter` cua BON
 *     phan tu `<div>` co dinh so luong: mot mui may dan dau (`.veil-wisp`),
 *     hai khoi may chinh/phu toc do khac nhau (`.veil-cloud-a/b`), va mot
 *     lop suong nen tan cham nhat (`.veil-haze`).
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
      <div className="veil-wisp" />
      <div className="veil-cloud veil-cloud-a" />
      <div className="veil-cloud veil-cloud-b" />
      <div className="veil-haze" />
    </div>
  );
}

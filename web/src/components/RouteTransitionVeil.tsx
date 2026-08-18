"use client";

/**
 * Man may/suong che chuyen canh route — "Cloud Veil Route Transition V1".
 *
 * Y DINH: doi canh trong mot the gioi anime fantasy la di qua mot lan
 * may/suong, KHONG PHAI mot cu quay may ngang nhu slide PowerPoint (ban cu,
 * bi tu choi — xem lich su git). Trinh tu:
 *
 *   trang HIEN TAI -> may nhe nhang tien vao -> may che kin man hinh trong
 *   choc lat -> nen/route doi SAU man suong -> may thoai di -> trang MOI lo ra
 *
 * KIEN TRUC:
 *
 *   - MOUNT MOT LAN duy nhat o `layout.tsx`, ngang hang voi `PageBackground`
 *     (KHONG long vao ben trong no: `.page-bg` co `z-index: -1`, tao mot
 *     ngu canh xep chong RIENG — bat ky the con nao cua no, du dat z-index
 *     cao bao nhieu, van bi giam trong pham vi -1 do, khong the noi len tren
 *     `.site-header`. Man suong PHAI la anh em CUNG CAP voi `.site-header`
 *     o body de z-index cua no co y nghia toan cuc).
 *   - Doc trang thai tu `lib/routeTransitionStore.ts` — CUNG mot kho ma
 *     `PageBackground.tsx` doc, qua `useSyncExternalStore`. Component nay
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
 *     dong la CSS keyframes tren `transform`/`opacity`/`filter` cua vai
 *     phan tu `<div>` co dinh so luong (ba "cuc may" + mot lop suong nen).
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
      <div className="veil-cloud veil-cloud-a" />
      <div className="veil-cloud veil-cloud-b" />
      <div className="veil-cloud veil-cloud-c" />
      <div className="veil-haze" />
    </div>
  );
}

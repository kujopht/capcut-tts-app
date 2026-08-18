"use client";

/**
 * Vi chuyen canh RIENG, RAT NHO cho noi dung trang — Cloud Veil Route
 * Transition V2.
 *
 * VI SAO CAN THEM CAI NAY: V1 dat man may TREN ca noi dung, nen do mo cua
 * may tu no che giau luc DOM doi (Next.js thay `{children}` bang cay component
 * cua route moi). V2 chuyen man may XUONG duoi noi dung (xem
 * `RouteTransitionVeil.tsx`/`.route-veil` o globals.css) — noi dung gio
 * LUON o tren may, nen KHONG con gi che giau buoc thay DOM do nua. Component
 * nay bu lai bang mot cu mo/hien CUC NHO cua CHINH noi dung (opacity + dich
 * 3px doc), du de che mat cam giac "the bi thay dot ngot" ma khong can giu
 * hai cay component (cu/moi) cung luc.
 *
 * MOT THE BAO ON DINH: `{children}` doi khi route doi (do Next.js quan ly),
 * nhung CHINH the bao nay (voi className "wrap route-content") KHONG BAO
 * GIO remount — no doc CUNG mot kho voi `PageBackground`/`RouteTransitionVeil`
 * qua `useSyncExternalStore`, chi doi thuoc tinh `data-state` (`.route-
 * content[data-state=...]` o globals.css dieu khien hoat hinh). Nho vay CSS
 * transition co "tu" va "den" tren CUNG mot phan tu DOM — dieu kien bat
 * buoc de trinh duyet noi suy duoc, khong bi nhay khung.
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

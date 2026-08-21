"use client";

/**
 * Lop tranh nen theo tung trang.
 *
 * V1 "Cloud Veil Route Transition": chuyen canh khi doi route KHONG con la
 * viec cua component nay nua — no chuyen sang `RouteTransitionVeil.tsx`
 * (hieu ung chuyen canh) + `lib/routeTransitionStore.ts` (kho dieu phoi,
 * dung chung giua hai component).
 *
 * V4 "Aether Rift Reveal": component nay KHONG con tu quan ly mang lop
 * (`cacLop`/`data-fade` cua V3) — kho da tu tach san CHINH XAC HAI lop can
 * ve, doc truc tiep tu snapshot:
 *
 *   `ten`     lop DUOI, DA ON DINH, tuyet doi khong hoat hinh.
 *   `tenMoi`  lop TREN, chi ton tai luc `trangThai === "revealing"` — duoc
 *             "tiet lo" dan qua `clip-path: url(#aether-fill-clip)`
 *             (dinh nghia o `RouteTransitionVeil.tsx`, hoat hinh boi CSS
 *             `d`) thay vi opacity-crossfade nhu V3.
 *
 * `key={the}` tren lop TREN dam bao React REMOUNT no moi lan MOT LAN
 * REVEAL MOI that su bat dau (ke ca khi dieu huong lien tiep thay doi dich
 * TRUOC KHI lan truoc kip xong) — dam bao khong con LiveBackground/trang
 * thai anh nao bi giu sot lai tu lan truoc.
 *
 * KHONG dung lam bia truyen — do la viec cua `StoryCoverFallback`.
 */

import { useEffect, useRef, useSyncExternalStore } from "react";
import { anhNen, videoNen } from "@/lib/backgrounds";
import { AmbientScene } from "@/components/AmbientScene";
import { LiveBackground } from "@/components/LiveBackground";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

/**
 * Live Wallpaper — rollout V4 (2026-08): CA 8 chu de, khong con rieng trang
 * chu. Lich su rieng cua trang chu (Nova Reel V1/V2 bi tu choi, Gemini V1/V2)
 * xem lich su git — ban Gemini V2 da bi THAY THE hoan toan boi bo 8 video
 * nguoi dung tu lam thu cong trong dot rollout nay (kiem tra vong lap/chat
 * luong day du trong bao cao rollout), KHONG con dung.
 *
 * `videoNen(ten)` (`lib/backgrounds.ts`) la NGUON DUY NHAT quyet dinh video
 * nao ung voi chu de nao — component nay KHONG tu ghep chuoi duong dan
 * (dac ta rollout muc 9). `undefined` (chu de chua co live wallpaper, hien
 * tai khong con chu de nao roi vao truong hop nay) -> `<LiveBackground>`
 * nhan `video={undefined}`, tu no chi ve poster, khong khac gi truoc rollout.
 *
 * TUONG THICH Aether Rift: roi mot chu de -> `ten` (lop duoi) doi thanh chu
 * de moi NGAY khi lop TREN (`tenMoi`) hoan tat tiet lo — `<LiveBackground>`
 * chi mount UNG VOI CHINH chu de cua lop do, nen video tu go het khi lop
 * chua no khong con la chu de do nua, KHONG bao gio phat ngam lau hon can
 * thiet. Vao mot chu de: lop TREN mount NGAY tu dau pha reveal — Live
 * Background tu no da ve poster truoc/video sau (xem chinh component do),
 * nen nguoi dung thay poster net trong luc duong bien dang tiet lo, video
 * chi hien khi tai xong. Khong can them "tam ngung".
 *
 * O TRANG THAI ON DINH (khong dang chuyen canh) CHI CO MOT lop `.page-bg-lop`
 * (`tenMoi === null`), nen CHI CO MOT `<video>` dang giai ma — dung dac ta
 * rollout muc 15 ("normally only ONE full live wallpaper should be
 * decoding"). Trong luc chuyen canh (~480ms), co THE co hai video ngan han —
 * day la pham vi da duoc chap nhan cua Aether Rift, khong phai hoi quy.
 */
export function PageBackground() {
  const { ten, tenMoi, the, duongDan } = useSyncExternalStore(
    routeTransitionStore.subscribe,
    routeTransitionStore.getSnapshot,
    // Server: chua biet duong dan nao ca — `ten === null` -> component ve
    // `null`, giong het hanh vi client truoc khi hieu ung dau tien chay.
    () => routeTransitionStore.getSnapshot(),
  );

  /*
    Doc `location.pathname` thay vi `usePathname()`.

    `usePathname()` buoc component phai o trong cay dieu huong cua Next va se
    ve lai theo moi lan route doi — dung, nhung o day ta con can BIET truoc khi
    bao kho, va Next dieu huong bang History API nen khong phat `popstate` khi
    `pushState`. Mot vong kiem nho la du, va no khong dong vao trang thai route.
  */
  const duongDanTruoc = useRef<string | null>(null);
  useEffect(() => {
    /*
      Chi goi `diTinh` khi duong dan THAT SU doi — vong kiem nay chay MAI
      MAI (suot doi trang), nen neu goi `diTinh` moi nhip du khong co gi
      doi, kho se `set()` (va lam CA HAI component ve lai) moi nhip VO HAN,
      dung nguyen dieu "khong duoc kich hoat hoat hinh lien tuc luc dung yen"
      ma dac ta cam — do la ly do van GIU vong kiem (khong doi sang mot co
      che nang hon), chi RUT NGAN chu ky.

      V4 rut tu 120ms xuong 30ms: dac ta cam moi do tre dau vao (muc 9,
      "<100ms"), va vong kiem nay la con duong DUY NHAT component biet URL
      da doi (Next.js khong bao mot su kien nao cho pushState). Do sanh mot
      chuoi ngan moi 30ms re toi muc khong do luong duoc bang cong cu thong
      thuong — an toan de rut ngan, khac han viec giam mot animation frame.
    */
    const doc = () => {
      const duong = window.location.pathname;
      if (duong === duongDanTruoc.current) return;
      duongDanTruoc.current = duong;
      routeTransitionStore.diTinh(duong);
    };
    doc();
    const id = window.setInterval(doc, 30);
    window.addEventListener("popstate", doc);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("popstate", doc);
    };
  }, []);

  if (!ten) return null;

  return (
    <div className="page-bg" aria-hidden="true">
      {/*
        Lop DUOI — DA ON DINH, khong bao gio hoat hinh. `key={ten}` la BAT
        BUOC (phat hien qua QA trinh duyet that, khong phai doan): truoc
        rollout V4, CHI home co video, nen doi chu de LUON di kem mount/
        unmount `<video>` (mot ben co video, ben kia khong). Tu khi CA 8 chu
        de deu co video, doi tu chu de CO video NAY sang chu de CO video
        KHAC ma KHONG co `key` khien React coi day la "cung mot component",
        chi cap nhat lai thuoc tinh `src` tren `<source>` co san — nhung
        trinh duyet KHONG tu doc lai `<source>` khi thuoc tinh doi (yeu cau
        goi `.load()`, ma `LiveBackground.tsx` khong tu goi luc nay), nen
        `<video>` cu VAN tiep tuc phat nguon CU du DOM da hien thi dung
        poster/data-bg moi. `key={ten}` ep React GO HAN va MOUNT LAI toan bo
        LiveBackground moi lan chu de DUOI thay doi, dam bao `<video>` luon
        dung nguon.
      */}
      <div className="page-bg-lop" data-bg={ten}>
        <LiveBackground
          key={ten}
          poster={anhNen(ten)}
          video={videoNen(ten)}
          className="live-wallpaper-lop"
        />
      </div>

      {/* Lop TREN — CHI ton tai luc dang "revealing", tiet lo dan qua
          clip-path (xem RouteTransitionVeil.tsx). */}
      {tenMoi ? (
        <div
          className="page-bg-lop page-bg-reveal"
          data-bg={tenMoi}
          key={the}
        >
          <LiveBackground
            poster={anhNen(tenMoi)}
            video={videoNen(tenMoi)}
            className="live-wallpaper-lop"
          />
        </div>
      ) : null}

      {/* Hat sang — CSS quyet dinh trang nao ve. Uu tien dia diem DICH de
          khong tre so voi hieu ung reveal. */}
      <div className="hat" data-bg={tenMoi ?? ten} />

      {/*
        Khong khi rieng cua tung khu vuc. Dat o DAY chu khong o `layout.tsx`:
        component nay da theo doi `pathname` roi, va them mot cho nua theo doi
        cung mot thu la them mot cho nua co the lech.
      */}
      <AmbientScene duongDan={duongDan || "/"} />
    </div>
  );
}

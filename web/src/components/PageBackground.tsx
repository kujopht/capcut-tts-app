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
import { anhNen } from "@/lib/backgrounds";
import { AmbientScene } from "@/components/AmbientScene";
import { LiveBackground } from "@/components/LiveBackground";
import { routeTransitionStore } from "@/lib/routeTransitionInstance";

/**
 * Live Wallpaper — Gemini V2 (2026-08). CHI trang chu.
 *
 * Lich su: Nova Reel V1 (video toan khung, camera zoom ~5%/6s) va Nova Reel V2
 * hybrid (video da on dinh + mask cuc bo) DEU bi tu choi o QA thu cong — xem
 * lich su git. Gemini V1 (video dau tien nguoi dung tu tao) da thu o staging;
 * nguoi dung tu danh gia va cung cap Gemini V2 (chat luong cao hon) de thay
 * the — day la ban dang dung, KHONG chong len ban Gemini V1.
 *
 * Video nay do NGUOI DUNG tu tao bang Gemini (khong qua Pollinations, khong
 * ton Pollen). Kiem tra nhanh (khong OpenCV/on dinh hoa/mask — nguoi dung da
 * duyet thu cong): camera on dinh, khong bien dang lau dai/nhan vat/thuyen,
 * khong nhap nhay do sang (<1% xuyen suot 10s).
 *
 * Video toan khung, giong cau truc Gemini V1/Nova Reel V1 ban dau (poster ->
 * video crossfade, KHONG mask, KHONG on dinh hoa OpenCV).
 *
 * TUONG THICH Aether Rift: roi trang chu -> `ten` (lop duoi) doi thanh chu
 * de moi NGAY khi lop TREN (`tenMoi`) hoan tat tiet lo — `<LiveBackground>`
 * chi mount khi CHINH lop do co `data-bg="home"`, nen video tu go het khi
 * lop chua no khong con la "home" nua, KHONG bao gio phat ngam lau hon can
 * thiet. Vao trang chu: lop TREN mount voi `tenMoi === "home"` NGAY tu dau
 * pha reveal — LiveBackground tu no da ve poster truoc/video sau (xem
 * chinh component do), nen nguoi dung thay poster net trong luc duong bien
 * dang tiet lo, video chi hien khi tai xong. Khong can them "tam ngung".
 */
const HOME_LIVE_BAT = true;
const HOME_VIDEO = {
  mp4: "/artwork/fantasy-backgrounds/home-live-gemini-v2.mp4",
};

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
      {/* Lop DUOI — DA ON DINH, khong bao gio hoat hinh. */}
      <div className="page-bg-lop" data-bg={ten}>
        {ten === "home" ? (
          <LiveBackground
            poster={anhNen(ten)}
            video={HOME_LIVE_BAT ? HOME_VIDEO : undefined}
            className="home-live-lop"
          />
        ) : null}
      </div>

      {/* Lop TREN — CHI ton tai luc dang "revealing", tiet lo dan qua
          clip-path (xem RouteTransitionVeil.tsx). */}
      {tenMoi ? (
        <div
          className="page-bg-lop page-bg-reveal"
          data-bg={tenMoi}
          key={the}
        >
          {tenMoi === "home" ? (
            <LiveBackground
              poster={anhNen(tenMoi)}
              video={HOME_LIVE_BAT ? HOME_VIDEO : undefined}
              className="home-live-lop"
            />
          ) : null}
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
